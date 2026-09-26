from __future__ import annotations

import hmac
import json
import re
import secrets
import socket
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from .protocol import (
    AUTH_CHALLENGE_BYTES,
    CLIENT_HELLO_TYPE,
    MAX_HELLO_BYTES,
    MAX_REQUEST_BYTES,
    MAX_RESPONSE_BYTES,
    PROTOCOL_VERSION,
    REQUEST_TYPE,
    authenticated_response,
    canonical_json_bytes,
    failure,
    proof_matches,
    server_hello,
    success,
    valid_challenge,
)


REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
MAX_ACTIVE_CONNECTIONS = 32
# Idle timeout still bounds stalled response writes.  The separate absolute
# request deadline is measured from accept and is never refreshed by trickled
# request bytes, which prevents slow clients from pinning all 32 slots.
NETWORK_IDLE_TIMEOUT_SECONDS = 5.0
ABSOLUTE_REQUEST_DEADLINE_SECONDS = 5.0
MAX_ACCEPTS_PER_POLL = 4
MAX_REQUESTS_PER_POLL = 4
MAX_READS_PER_CONNECTION_PER_POLL = 4
POLL_TIME_BUDGET_SECONDS = 0.010
_READ_CHUNK_BYTES = 65_536


def _configure_listener_security(listener: socket.socket) -> None:
    """Claim the loopback port without Windows' unsafe reuse semantics."""

    if sys.platform.startswith("win"):
        exclusive = getattr(socket, "SO_EXCLUSIVEADDRUSE", None)
        if exclusive is None:
            raise RuntimeError(
                "SO_EXCLUSIVEADDRUSE is required for the ANSA MCP bridge on Windows"
            )
        listener.setsockopt(socket.SOL_SOCKET, exclusive, 1)
        return
    # POSIX SO_REUSEADDR permits a prompt restart after TIME_WAIT, but unlike
    # Winsock's option does not permit two live listeners on the same tuple.
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)


@dataclass
class _Connection:
    sock: socket.socket
    address: tuple[Any, ...]
    accepted_at: float
    last_activity: float
    client_hello: bytearray = field(default_factory=bytearray)
    client_hello_ready: bool = False
    client_hello_too_large: bool = False
    client_nonce: str | None = None
    challenge: str | None = None
    hello: bytes | None = None
    hello_offset: int = 0
    hello_sent: bool = False
    request: bytearray = field(default_factory=bytearray)
    request_ready: bool = False
    request_too_large: bool = False
    response: bytes | None = None
    response_offset: int = 0


class PollingBridgeServer:
    """JSON-lines server driven entirely by the ANSA GUI thread.

    ``poll`` never blocks. The ANSA ``BCTimer`` callback invokes it, so request
    parsing, allowlist checks, handler dispatch, and response serialization all
    happen on the same GUI thread as the ANSA API.
    """

    def __init__(self, address: tuple[str, int], runtime: Any):
        host, port = address
        if host != "127.0.0.1":
            raise ValueError("ANSA MCP bridge may only listen on 127.0.0.1")

        self.runtime = runtime
        # Attribute names are public for diagnostics/tests.  The request
        # deadline is absolute; only the idle timeout uses last_activity.
        self.read_timeout_seconds = NETWORK_IDLE_TIMEOUT_SECONDS
        self.request_deadline_seconds = ABSOLUTE_REQUEST_DEADLINE_SECONDS
        self.max_active_connections = MAX_ACTIVE_CONNECTIONS
        self._connections: dict[socket.socket, _Connection] = {}
        self._closed = False
        self._rejected_connections = 0

        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            _configure_listener_security(listener)
            listener.bind((host, int(port)))
            listener.listen(MAX_ACTIVE_CONNECTIONS + 1)
            listener.setblocking(False)
        except Exception:
            listener.close()
            raise
        self.socket = listener
        self.server_address = listener.getsockname()

    @property
    def active_connection_count(self) -> int:
        return len(self._connections)

    @property
    def rejected_connection_count(self) -> int:
        return self._rejected_connections

    def poll(self, *, now: float | None = None) -> int:
        """Accept, read, dispatch, and write without blocking.

        At most four complete requests are dispatched per timer tick. Network
        reads and writes remain non-blocking, while every handler call stays
        synchronous on the caller (ANSA GUI) thread.
        """

        if self._closed:
            return 0
        deadline = time.perf_counter() + POLL_TIME_BUDGET_SECONDS
        current = time.monotonic() if now is None else float(now)
        self._accept_available(current, deadline)

        processed = 0
        for state in list(self._connections.values()):
            if state.sock not in self._connections:
                continue

            if state.response is None and not state.request_ready:
                if current - state.accepted_at >= self.request_deadline_seconds:
                    # An absolute accept-to-request deadline is intentionally
                    # not refreshed by incoming bytes.  Closing directly also
                    # avoids spending additional time on a slow unauthenticated
                    # peer after its allocation expired.
                    self._close_connection(state)
                    continue
                if current - state.last_activity >= self.read_timeout_seconds:
                    self._close_connection(state)
                    continue

            # The peer first sends a small, strict, non-sensitive client hello.
            # Its fresh nonce is what makes a recorded server hello unusable on
            # a later connection.  No method or params are read at this stage.
            if state.client_nonce is None:
                if not state.client_hello_ready:
                    self._read_client_hello_available(state, current, deadline)
                if state.sock not in self._connections:
                    continue
                if not state.client_hello_ready:
                    continue
                if state.client_hello_too_large:
                    self._close_connection(state)
                    continue
                client_nonce = self._parse_client_hello(bytes(state.client_hello))
                if client_nonce is None:
                    self._close_connection(state)
                    continue
                state.client_nonce = client_nonce
                state.challenge = secrets.token_hex(AUTH_CHALLENGE_BYTES)
                state.hello = canonical_json_bytes(
                    server_hello(
                        self.runtime.token,
                        state.client_nonce,
                        state.challenge,
                    )
                ) + b"\n"
                if len(state.hello) > MAX_HELLO_BYTES:
                    self._close_connection(state)
                    raise RuntimeError(
                        "Authenticated server hello exceeds its wire limit"
                    )

            # The authenticated server hello must be completely written before
            # any business request bytes are read.
            if not state.hello_sent:
                self._write_hello_available(state, current)
                if state.sock not in self._connections or not state.hello_sent:
                    continue

            if state.response is None and not state.request_ready:
                self._read_available(state, current, deadline)

            if (
                state.response is None
                and state.request_ready
                and processed < MAX_REQUESTS_PER_POLL
                and time.perf_counter() <= deadline
            ):
                if state.request_too_large:
                    # The proof cannot be verified from a truncated envelope.
                    self._close_connection(state)
                    continue
                else:
                    assert state.client_nonce is not None
                    assert state.challenge is not None
                    response, request_id = self._handle_request(
                        bytes(state.request), state.client_nonce, state.challenge
                    )
                    if response is None:
                        # Malformed or invalid authentication is never answered.
                        # This fails closed and cannot become a proof oracle.
                        self._close_connection(state)
                        continue
                response_time = time.monotonic() if now is None else current
                self._set_response(state, response, request_id, response_time)
                processed += 1

            if state.response is not None:
                write_time = time.monotonic() if now is None else current
                if write_time - state.last_activity >= self.read_timeout_seconds:
                    self._close_connection(state)
                else:
                    self._write_available(state, write_time)

        return processed

    def _accept_available(self, now: float, deadline: float) -> None:
        accepted = 0
        while (
            not self._closed
            and accepted < MAX_ACCEPTS_PER_POLL
            and time.perf_counter() <= deadline
        ):
            try:
                connection, address = self.socket.accept()
            except BlockingIOError:
                return
            except OSError:
                if self._closed:
                    return
                raise

            connection.setblocking(False)
            accepted += 1
            if len(self._connections) >= self.max_active_connections:
                self._rejected_connections += 1
                connection.close()
                continue
            self._connections[connection] = _Connection(
                sock=connection,
                address=address,
                accepted_at=now,
                last_activity=now,
            )

    def _read_client_hello_available(
        self, state: _Connection, now: float, deadline: float
    ) -> None:
        reads = 0
        while (
            not state.client_hello_ready
            and reads < MAX_READS_PER_CONNECTION_PER_POLL
            and time.perf_counter() <= deadline
        ):
            remaining = MAX_HELLO_BYTES + 1 - len(state.client_hello)
            if remaining <= 0:
                state.client_hello_ready = True
                state.client_hello_too_large = True
                return
            try:
                chunk = state.sock.recv(min(_READ_CHUNK_BYTES, remaining))
            except BlockingIOError:
                return
            except (ConnectionResetError, OSError):
                self._close_connection(state)
                return
            if not chunk:
                if state.client_hello:
                    state.client_hello_ready = True
                else:
                    self._close_connection(state)
                return
            reads += 1
            state.last_activity = now
            state.client_hello.extend(chunk)
            newline = state.client_hello.find(b"\n")
            if newline >= 0:
                line_length = newline + 1
                if line_length > MAX_HELLO_BYTES:
                    state.client_hello_too_large = True
                else:
                    del state.client_hello[line_length:]
                state.client_hello_ready = True
                return
            if len(state.client_hello) > MAX_HELLO_BYTES:
                state.client_hello_too_large = True
                state.client_hello_ready = True
                return

    @staticmethod
    def _parse_client_hello(raw: bytes) -> str | None:
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError, TypeError):
            return None
        if not isinstance(value, dict) or set(value) != {
            "version",
            "type",
            "client_nonce",
        }:
            return None
        if value.get("version") != PROTOCOL_VERSION:
            return None
        if value.get("type") != CLIENT_HELLO_TYPE:
            return None
        client_nonce = value.get("client_nonce")
        if not valid_challenge(client_nonce):
            return None
        return client_nonce

    def _write_hello_available(self, state: _Connection, now: float) -> None:
        assert state.hello is not None
        try:
            sent = state.sock.send(state.hello[state.hello_offset :])
        except BlockingIOError:
            return
        except (BrokenPipeError, ConnectionResetError, OSError):
            self._close_connection(state)
            return
        if sent <= 0:
            self._close_connection(state)
            return
        state.hello_offset += sent
        state.last_activity = now
        if state.hello_offset >= len(state.hello):
            state.hello_sent = True

    def _read_available(
        self, state: _Connection, now: float, deadline: float
    ) -> None:
        reads = 0
        while (
            not state.request_ready
            and reads < MAX_READS_PER_CONNECTION_PER_POLL
            and time.perf_counter() <= deadline
        ):
            remaining = MAX_REQUEST_BYTES + 1 - len(state.request)
            if remaining <= 0:
                state.request_ready = True
                state.request_too_large = True
                return
            try:
                chunk = state.sock.recv(min(_READ_CHUNK_BYTES, remaining))
            except BlockingIOError:
                return
            except (ConnectionResetError, OSError):
                self._close_connection(state)
                return

            if not chunk:
                if state.request:
                    state.request_ready = True
                else:
                    self._close_connection(state)
                return

            reads += 1
            state.last_activity = now
            state.request.extend(chunk)
            newline = state.request.find(b"\n")
            if newline >= 0:
                line_length = newline + 1
                if line_length > MAX_REQUEST_BYTES:
                    state.request_too_large = True
                else:
                    del state.request[line_length:]
                state.request_ready = True
                return
            if len(state.request) > MAX_REQUEST_BYTES:
                state.request_too_large = True
                state.request_ready = True
                return

    def _handle_request(
        self, raw: bytes, client_nonce: str, challenge: str
    ) -> tuple[dict[str, Any] | None, str]:
        request_id = "unknown"
        method = "unknown"
        try:
            request = json.loads(raw.decode("utf-8"))
            if not isinstance(request, dict):
                return None, request_id

            # Authenticate the complete request envelope before interpreting or
            # dispatching any of its application fields.  The long-term token is
            # never present on the wire; only a challenge-bound HMAC is sent.
            client_proof = request.get("client_proof")
            unsigned_request = dict(request)
            unsigned_request.pop("client_proof", None)
            received_challenge = unsigned_request.get("challenge")
            received_client_nonce = unsigned_request.get("client_nonce")
            if (
                not valid_challenge(received_challenge)
                or not hmac.compare_digest(received_challenge, challenge)
                or not valid_challenge(received_client_nonce)
                or not hmac.compare_digest(received_client_nonce, client_nonce)
                or not proof_matches(
                    self.runtime.token,
                    "client_request",
                    unsigned_request,
                    client_proof,
                )
            ):
                return None, request_id

            request_id = str(request.get("id") or uuid.uuid4().hex)
            if not REQUEST_ID_RE.fullmatch(request_id):
                request_id = "invalid"
                return (
                    failure(
                        request_id,
                        "INVALID_REQUEST",
                        "id must contain 1-128 safe characters",
                    ),
                    request_id,
                )
            if request.get("type") != REQUEST_TYPE:
                return (
                    failure(
                        request_id,
                        "INVALID_REQUEST",
                        "Invalid authenticated request type",
                    ),
                    request_id,
                )
            expected_fields = {
                "version",
                "type",
                "id",
                "method",
                "params",
                "client_nonce",
                "challenge",
                "client_proof",
            }
            if set(request) != expected_fields:
                return (
                    failure(
                        request_id,
                        "INVALID_REQUEST",
                        "Authenticated request contains missing or unknown fields",
                    ),
                    request_id,
                )
            if request.get("version") != PROTOCOL_VERSION:
                return (
                    failure(
                        request_id,
                        "PROTOCOL_VERSION_UNSUPPORTED",
                        "Unsupported bridge protocol version",
                    ),
                    request_id,
                )

            method = request.get("method")
            params = request.get("params", {})
            if not isinstance(method, str) or not isinstance(params, dict):
                return (
                    failure(
                        request_id,
                        "INVALID_REQUEST",
                        "method must be a string and params an object",
                    ),
                    request_id,
                )
            if method not in self.runtime.registry.methods:
                return (
                    failure(
                        request_id,
                        "METHOD_NOT_ALLOWED",
                        f"Method is not allowlisted: {method}",
                    ),
                    request_id,
                )

            try:
                dispatch = getattr(self.runtime, "dispatch", self.runtime.registry.dispatch)
                result = dispatch(method, params)
                return success(request_id, result), request_id
            except FileExistsError as exc:
                return failure(request_id, "FILE_EXISTS", str(exc)), request_id
            except (ValueError, TypeError) as exc:
                message = str(exc)
                code = (
                    "PATH_NOT_ALLOWED"
                    if message.startswith("PATH_NOT_ALLOWED:")
                    else "PARAMS_INVALID"
                )
                return failure(request_id, code, message), request_id
            except RuntimeError as exc:
                message = str(exc)
                code = "API_ERROR"
                for candidate in (
                    "SESSION_CHANGED",
                    "PRECONDITION_FAILED",
                    "OUTCOME_UNKNOWN",
                ):
                    if message.startswith(candidate + ":"):
                        code = candidate
                        break
                if code == "API_ERROR":
                    self._log_dispatch_error(method, exc)
                return failure(request_id, code, message), request_id
            except Exception as exc:
                self._log_dispatch_error(method, exc)
                return (
                    failure(
                        request_id,
                        "API_ERROR",
                        f"{exc.__class__.__name__}: {exc}",
                    ),
                    request_id,
                )
        except (UnicodeDecodeError, ValueError, TypeError, json.JSONDecodeError):
            # A body that cannot carry a verifiable proof is unauthenticated.
            return None, request_id
        except Exception as exc:
            self._log_dispatch_error(method, exc)
            return (
                failure(
                    request_id, "API_ERROR", f"{exc.__class__.__name__}: {exc}"
                ),
                request_id,
            )

    def _log_dispatch_error(self, method: str, exc: Exception) -> None:
        logger = getattr(self.runtime, "_log_error", None)
        if callable(logger):
            logger(method, exc)

    def _set_response(
        self,
        state: _Connection,
        response: dict[str, Any],
        request_id: str,
        now: float,
    ) -> None:
        assert state.client_nonce is not None
        assert state.challenge is not None
        try:
            signed = authenticated_response(
                self.runtime.token,
                state.client_nonce,
                state.challenge,
                response,
            )
            encoded = canonical_json_bytes(signed) + b"\n"
        except (TypeError, ValueError) as exc:
            fallback = failure(
                request_id,
                "API_ERROR",
                f"Response is not valid JSON: {exc}",
            )
            encoded = canonical_json_bytes(
                authenticated_response(
                    self.runtime.token,
                    state.client_nonce,
                    state.challenge,
                    fallback,
                )
            ) + b"\n"
        if len(encoded) > MAX_RESPONSE_BYTES:
            fallback = failure(
                request_id,
                "RESPONSE_TOO_LARGE",
                "Response exceeds 4 MiB",
            )
            encoded = canonical_json_bytes(
                authenticated_response(
                    self.runtime.token,
                    state.client_nonce,
                    state.challenge,
                    fallback,
                )
            ) + b"\n"
        state.response = encoded
        state.response_offset = 0
        # Handler dispatch may itself take longer than the network idle timeout.
        # The completed response starts a fresh non-blocking write interval.
        state.last_activity = now

    def _write_available(self, state: _Connection, now: float) -> None:
        assert state.response is not None
        try:
            sent = state.sock.send(state.response[state.response_offset :])
        except BlockingIOError:
            return
        except (BrokenPipeError, ConnectionResetError, OSError):
            self._close_connection(state)
            return
        if sent <= 0:
            self._close_connection(state)
            return
        state.response_offset += sent
        state.last_activity = now
        if state.response_offset >= len(state.response):
            self._close_connection(state)

    def _close_connection(self, state: _Connection) -> None:
        self._connections.pop(state.sock, None)
        try:
            state.sock.close()
        except OSError:
            pass

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for state in list(self._connections.values()):
            self._close_connection(state)
        try:
            self.socket.close()
        except OSError:
            pass

    # Compatibility with the previous socketserver-based implementation.
    def shutdown(self) -> None:
        self.close()

    def server_close(self) -> None:
        self.close()


# Keep the old public name usable for diagnostic scripts and local extensions.
BridgeTCPServer = PollingBridgeServer
