from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import socket
import time
import uuid
from pathlib import Path
from typing import Any


MAX_RESPONSE_BYTES = 4 * 1024 * 1024
MAX_HELLO_BYTES = 4 * 1024
# Wire protocol version.  bridge.json is a separate local config format and
# intentionally remains version 1.
PROTOCOL_VERSION = 3
SERVER_HELLO_TYPE = "server_hello"
CLIENT_HELLO_TYPE = "client_hello"
REQUEST_TYPE = "request"
TOKEN_RE = re.compile(r"^[0-9a-fA-F]{64}$")
CHALLENGE_RE = re.compile(r"^[0-9a-f]{64}$")
PROOF_RE = re.compile(r"^[0-9a-f]{64}$")
_SERVER_HELLO_CONTEXT = b"ansa-mcp/server-hello/v3\x00"
_CLIENT_REQUEST_CONTEXT = b"ansa-mcp/client-request/v3\x00"
_SERVER_RESPONSE_CONTEXT = b"ansa-mcp/server-response/v3\x00"
CONFIRMED_PRE_MUTATION_ERROR_CODES = frozenset(
    {
        "UNAUTHORIZED",
        "PROTOCOL_VERSION_UNSUPPORTED",
        "INVALID_REQUEST",
        "METHOD_NOT_ALLOWED",
        "PARAMS_INVALID",
        "PATH_NOT_ALLOWED",
        "SESSION_CHANGED",
        "PRECONDITION_FAILED",
        "FILE_EXISTS",
    }
)


class BridgeError(RuntimeError):
    pass


class BridgeOutcomeUnknown(BridgeError):
    """A persistent write may have run, but no valid response confirmed it."""

    code = "OUTCOME_UNKNOWN"

    def __init__(self, operation_id: str):
        self.operation_id = operation_id
        super().__init__(
            f"OUTCOME_UNKNOWN: operation_id={operation_id}; the write may have been "
            "applied. Inspect live state before retrying. Retry only with the same "
            "operation_id; never retry with a new operation_id."
        )


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _token_key(token: str) -> bytes:
    try:
        key = bytes.fromhex(token)
    except (TypeError, ValueError) as exc:
        raise BridgeError("ANSA bridge token is missing or invalid") from exc
    if len(key) != 32:
        raise BridgeError("ANSA bridge token is missing or invalid")
    return key


def _authentication_proof(token: str, purpose: str, value: Any) -> str:
    contexts = {
        "server_hello": _SERVER_HELLO_CONTEXT,
        "client_request": _CLIENT_REQUEST_CONTEXT,
        "server_response": _SERVER_RESPONSE_CONTEXT,
    }
    try:
        context = contexts[purpose]
    except KeyError as exc:
        raise BridgeError("Unknown ANSA bridge authentication purpose") from exc
    try:
        encoded = _canonical_json_bytes(value)
    except (TypeError, ValueError) as exc:
        raise BridgeError(f"ANSA bridge payload is not valid JSON: {exc}") from exc
    return hmac.new(_token_key(token), context + encoded, hashlib.sha256).hexdigest()


def _proof_matches(token: str, purpose: str, value: Any, proof: Any) -> bool:
    if not isinstance(proof, str) or PROOF_RE.fullmatch(proof) is None:
        return False
    try:
        expected = _authentication_proof(token, purpose, value)
    except BridgeError:
        return False
    return hmac.compare_digest(proof, expected)


def _decode_json_line(data: bytes, label: str) -> dict[str, Any]:
    if not data:
        raise BridgeError(f"ANSA bridge closed without returning {label}")
    try:
        value = json.loads(data.split(b"\n", 1)[0].decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise BridgeError(f"ANSA bridge returned invalid {label} JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise BridgeError(f"ANSA bridge {label} must be a JSON object")
    return value


def _remaining_timeout(deadline: float, label: str) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise BridgeError(f"ANSA bridge {label} absolute deadline expired")
    return remaining


def _receive_line(
    connection: socket.socket,
    maximum: int,
    label: str,
    deadline: float,
) -> bytes:
    data = bytearray()
    while b"\n" not in data:
        connection.settimeout(_remaining_timeout(deadline, label))
        chunk = connection.recv(65_536)
        if not chunk:
            break
        data.extend(chunk)
        if len(data) > maximum:
            raise BridgeError(f"ANSA bridge {label} exceeded {maximum} bytes")
    if data and b"\n" not in data:
        raise BridgeError(
            f"ANSA bridge closed before completing the {label} JSON line"
        )
    return bytes(data)


def default_config_path() -> Path:
    override = os.environ.get("ANSA_MCP_BRIDGE_CONFIG", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    local = os.environ.get("LOCALAPPDATA", "").strip()
    base = Path(local) if local else Path.home() / "AppData" / "Local"
    return base / "ANSAMCP" / "bridge.json"


class LiveBridgeClient:
    def __init__(self, config_path: Path | None = None):
        self.config_path = (config_path or default_config_path()).expanduser().resolve()

    def _config(self) -> dict[str, Any]:
        if not self.config_path.is_file():
            raise BridgeError(
                f"ANSA bridge config not found: {self.config_path}. "
                "Install/load the ANSA MCP bridge first."
            )
        try:
            value = json.loads(self.config_path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            raise BridgeError(f"ANSA bridge config is invalid: {exc}") from exc
        if not isinstance(value, dict):
            raise BridgeError("ANSA bridge config must be a JSON object")
        if value.get("version") != 1:
            raise BridgeError("ANSA bridge config version is unsupported")
        if value.get("host") != "127.0.0.1":
            raise BridgeError("ANSA bridge host must be 127.0.0.1")
        try:
            port = int(value.get("port", 0))
        except (TypeError, ValueError) as exc:
            raise BridgeError("ANSA bridge port is invalid") from exc
        if not 1024 <= port <= 65535:
            raise BridgeError("ANSA bridge port is invalid")
        if not TOKEN_RE.fullmatch(str(value.get("token", ""))):
            raise BridgeError("ANSA bridge token is missing or invalid")
        return value

    def call(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> Any:
        return self._call(method, params, timeout=timeout, operation_id=None)

    def call_persistent_write(
        self,
        method: str,
        params: dict[str, Any],
        *,
        operation_id: str,
        timeout: float | None = None,
    ) -> Any:
        """Call an idempotent write and fail closed if its outcome is unconfirmed.

        A failure before a connection is established is an ordinary bridge error.
        Once sending has been attempted, transport failures and malformed or
        mismatched responses cannot prove whether ANSA applied the write, so they
        become :class:`BridgeOutcomeUnknown`. Only an authenticated ``ok: false``
        code known to occur before mutation remains an ordinary
        :class:`BridgeError`; post-mutation and unknown codes do not confirm the
        outcome.
        """
        if not isinstance(operation_id, str) or not operation_id:
            raise BridgeError("Persistent writes require a non-empty operation_id")
        if params.get("operation_id") != operation_id:
            raise BridgeError(
                "Persistent write operation_id must match params.operation_id"
            )
        return self._call(
            method,
            params,
            timeout=timeout,
            operation_id=operation_id,
        )

    def _call(
        self,
        method: str,
        params: dict[str, Any] | None,
        *,
        timeout: float | None,
        operation_id: str | None,
    ) -> Any:
        config = self._config()
        if timeout is None:
            try:
                bridge_timeout = int(config.get("request_timeout_seconds", 120))
            except (TypeError, ValueError):
                bridge_timeout = 120
            # Keep this normalization identical to the in-ANSA config loader.
            bridge_timeout = max(10, min(bridge_timeout, 3600))
            effective_timeout = float(bridge_timeout + 5)
        else:
            effective_timeout = float(timeout)
            if effective_timeout <= 0:
                raise BridgeError("ANSA bridge timeout must be positive")

        call_deadline = time.monotonic() + effective_timeout

        # Keep connection establishment outside the dispatch-risk region. A refused
        # connection proves that this request could not have reached ANSA.
        try:
            connection_context = socket.create_connection(
                (config["host"], int(config["port"])),
                timeout=min(
                    _remaining_timeout(call_deadline, "connect"),
                    5.0,
                ),
            )
        except (OSError, TimeoutError) as exc:
            raise BridgeError(
                f"Cannot reach ANSA bridge at {config['host']}:{config['port']}: {exc}"
            ) from exc

        dispatch_attempted = False
        try:
            with connection_context as connection:
                client_nonce = secrets.token_hex(32)
                client_hello = {
                    "version": PROTOCOL_VERSION,
                    "type": CLIENT_HELLO_TYPE,
                    "client_nonce": client_nonce,
                }
                # This first line contains no method, params, token, or proof. It
                # supplies freshness so a recorded server hello cannot be replayed.
                connection.settimeout(
                    _remaining_timeout(call_deadline, "client hello send")
                )
                connection.sendall(_canonical_json_bytes(client_hello) + b"\n")

                # The server must prove possession of the shared secret before
                # the client transmits any request data.  The secret itself is
                # never placed in a wire message.
                hello_data = _receive_line(
                    connection,
                    MAX_HELLO_BYTES,
                    "hello",
                    call_deadline,
                )
                hello = _decode_json_line(hello_data, "hello")
                if set(hello) != {
                    "version",
                    "type",
                    "client_nonce",
                    "challenge",
                    "server_proof",
                }:
                    raise BridgeError("ANSA bridge hello schema is invalid")
                if hello.get("version") != PROTOCOL_VERSION:
                    raise BridgeError("ANSA bridge hello protocol version mismatch")
                if hello.get("type") != SERVER_HELLO_TYPE:
                    raise BridgeError("ANSA bridge hello type is invalid")
                received_client_nonce = hello.get("client_nonce")
                if (
                    not isinstance(received_client_nonce, str)
                    or not hmac.compare_digest(received_client_nonce, client_nonce)
                ):
                    raise BridgeError("ANSA bridge hello client nonce mismatch")
                challenge = hello.get("challenge")
                if not isinstance(challenge, str) or CHALLENGE_RE.fullmatch(challenge) is None:
                    raise BridgeError("ANSA bridge hello challenge is invalid")
                unsigned_hello = dict(hello)
                server_proof = unsigned_hello.pop("server_proof")
                if not _proof_matches(
                    config["token"], "server_hello", unsigned_hello, server_proof
                ):
                    raise BridgeError("ANSA bridge server authentication failed")

                unsigned_request = {
                    "version": PROTOCOL_VERSION,
                    "type": REQUEST_TYPE,
                    "id": uuid.uuid4().hex,
                    "method": method,
                    "params": params or {},
                    "client_nonce": client_nonce,
                    "challenge": challenge,
                }
                request = {
                    **unsigned_request,
                    "client_proof": _authentication_proof(
                        config["token"], "client_request", unsigned_request
                    ),
                }
                payload = _canonical_json_bytes(request) + b"\n"

                # sendall can fail after sending a prefix or the full request. From
                # this point onward a persistent write may already be executing.
                connection.settimeout(
                    _remaining_timeout(call_deadline, "request send")
                )
                dispatch_attempted = True
                connection.sendall(payload)
                response_data = _receive_line(
                    connection,
                    MAX_RESPONSE_BYTES,
                    "response",
                    call_deadline,
                )
                response = _decode_json_line(response_data, "response")

                response_proof = response.get("server_proof")
                unsigned_response = dict(response)
                unsigned_response.pop("server_proof", None)
                response_challenge = unsigned_response.get("challenge")
                response_client_nonce = unsigned_response.get("client_nonce")
                if (
                    not isinstance(response_challenge, str)
                    or not hmac.compare_digest(response_challenge, challenge)
                    or not isinstance(response_client_nonce, str)
                    or not hmac.compare_digest(response_client_nonce, client_nonce)
                    or not _proof_matches(
                        config["token"],
                        "server_response",
                        unsigned_response,
                        response_proof,
                    )
                ):
                    raise BridgeError("ANSA bridge response authentication failed")
                _remaining_timeout(call_deadline, "response verification")
        except (OSError, TimeoutError, BridgeError) as exc:
            if operation_id is not None and dispatch_attempted:
                raise BridgeOutcomeUnknown(operation_id) from exc
            raise BridgeError(
                f"Cannot reach ANSA bridge at {config['host']}:{config['port']}: {exc}"
            ) from exc
        if response.get("version") != PROTOCOL_VERSION:
            self._raise_unconfirmed_response(
                "ANSA bridge response protocol version mismatch", operation_id
            )
        if set(response) not in (
            {
                "version",
                "id",
                "ok",
                "result",
                "client_nonce",
                "challenge",
                "server_proof",
            },
            {
                "version",
                "id",
                "ok",
                "error",
                "client_nonce",
                "challenge",
                "server_proof",
            },
        ):
            self._raise_unconfirmed_response(
                "ANSA bridge response schema is invalid", operation_id
            )
        if response.get("id") != request["id"]:
            self._raise_unconfirmed_response(
                "ANSA bridge response ID mismatch", operation_id
            )
        if response.get("ok") is False:
            error = response.get("error", {})
            if not isinstance(error, dict):
                self._raise_unconfirmed_response(
                    "ANSA bridge error response is malformed", operation_id
                )
            code = error.get("code", "BRIDGE_ERROR")
            message = error.get("message", "Unknown bridge error")
            if not isinstance(code, str) or not isinstance(message, str):
                self._raise_unconfirmed_response(
                    "ANSA bridge error response is malformed", operation_id
                )
            # Only errors known to be raised before these handlers mutate ANSA
            # prove that a persistent write did not happen. API_ERROR,
            # RESPONSE_TOO_LARGE, and future/unknown codes can be produced after
            # mutation (for example during readback or response serialization).
            if (
                operation_id is not None
                and code not in CONFIRMED_PRE_MUTATION_ERROR_CODES
            ):
                raise BridgeOutcomeUnknown(operation_id)
            raise BridgeError(
                f"{code}: {message}"
            )
        if response.get("ok") is not True:
            self._raise_unconfirmed_response(
                "ANSA bridge response is missing a valid ok status", operation_id
            )
        result = response.get("result")
        if operation_id is not None and (
            not isinstance(result, dict)
            or result.get("operation_id") != operation_id
        ):
            self._raise_unconfirmed_response(
                "ANSA bridge write response did not confirm the operation_id",
                operation_id,
            )
        return result

    @staticmethod
    def _raise_unconfirmed_response(
        message: str,
        operation_id: str | None,
        cause: BaseException | None = None,
    ) -> None:
        if operation_id is not None:
            error = BridgeOutcomeUnknown(operation_id)
        else:
            error = BridgeError(message)
        if cause is not None:
            raise error from cause
        raise error

    def status(self, *, connect_timeout: float = 0.5) -> dict[str, Any]:
        status_path = self.config_path.with_name("status.json")
        persisted = None
        if status_path.is_file():
            try:
                persisted = json.loads(status_path.read_text(encoding="utf-8-sig"))
            except Exception as exc:  # status is diagnostic only
                persisted = {"state": "invalid", "error": str(exc)}
        try:
            ping = self.call("ping", timeout=connect_timeout)
            connected = True
            error = None
        except Exception as exc:
            ping = None
            connected = False
            error = str(exc)
        return {
            "connected": connected,
            "config_path": str(self.config_path),
            "status_path": str(status_path),
            "persisted_status": persisted,
            "ping": ping,
            "error": error,
        }
