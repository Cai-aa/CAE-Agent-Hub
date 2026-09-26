from __future__ import annotations

import json
import secrets
import socket
import socketserver
import threading
from pathlib import Path
from typing import Any

import pytest

import ansa_mcp.bridge_client as bridge_client_module
from ansa_mcp.bridge_client import (
    BridgeError,
    BridgeOutcomeUnknown,
    LiveBridgeClient,
)


TOKEN = "a" * 64


class _Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, response_mode: str = "ok"):
        self.response_mode = response_mode
        self.client_hellos: list[dict[str, Any]] = []
        self.raw_client_hellos: list[bytes] = []
        self.requests: list[dict[str, Any]] = []
        self.raw_requests: list[bytes] = []
        super().__init__(("127.0.0.1", 0), _Handler)


class _Handler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        raw_client_hello = self.rfile.readline()
        if not raw_client_hello:
            return
        self.server.raw_client_hellos.append(raw_client_hello)
        client_hello = json.loads(raw_client_hello.decode("utf-8"))
        self.server.client_hellos.append(client_hello)
        client_nonce = client_hello["client_nonce"]
        challenge = secrets.token_hex(32)
        echoed_client_nonce = client_nonce
        if self.server.response_mode in {"replayed_hello", "client_nonce_mismatch"}:
            echoed_client_nonce = "f" * 64
        unsigned_hello = {
            "version": (
                1
                if self.server.response_mode == "hello_version"
                else bridge_client_module.PROTOCOL_VERSION
            ),
            "type": bridge_client_module.SERVER_HELLO_TYPE,
            "client_nonce": echoed_client_nonce,
            "challenge": challenge,
        }
        hello = {
            **unsigned_hello,
            "server_proof": bridge_client_module._authentication_proof(
                TOKEN, "server_hello", unsigned_hello
            ),
        }
        if self.server.response_mode == "bad_hello_proof":
            hello["server_proof"] = "0" * 64
        encoded_hello = (json.dumps(hello) + "\n").encode("utf-8")
        if self.server.response_mode == "bad_hello_json":
            self.wfile.write(b"not-json\n")
        elif self.server.response_mode == "oversized_hello":
            self.wfile.write(b"{" + b" " * bridge_client_module.MAX_HELLO_BYTES + b"\n")
        elif self.server.response_mode == "partial_hello":
            midpoint = len(encoded_hello) // 2
            self.wfile.write(encoded_hello[:midpoint])
            self.wfile.flush()
            self.wfile.write(encoded_hello[midpoint:])
        else:
            self.wfile.write(encoded_hello)
        self.wfile.flush()

        raw_request = self.rfile.readline()
        if not raw_request:
            return
        self.server.raw_requests.append(raw_request)
        request = json.loads(raw_request.decode("utf-8"))
        self.server.requests.append(request)
        if self.server.response_mode == "eof":
            return
        if self.server.response_mode == "bad_json":
            self.wfile.write(b"not-json\n")
            return
        response_id = request["id"]
        if self.server.response_mode == "mismatch":
            response_id = "different-request-id"
        if self.server.response_mode in {"error", "api_error", "bad_error_proof"}:
            error_code = (
                "API_ERROR"
                if self.server.response_mode == "api_error"
                else "UNAUTHORIZED"
            )
            response = {
                "version": bridge_client_module.PROTOCOL_VERSION,
                "id": response_id,
                "ok": False,
                "error": {"code": error_code, "message": "bridge rejected request"},
            }
        else:
            result = {
                "method": request["method"],
                "params": request["params"],
            }
            if self.server.response_mode == "write_ok":
                result = {"operation_id": request["params"]["operation_id"]}
            elif self.server.response_mode == "wrong_operation_id":
                result = {"operation_id": "another-operation-id"}
            response = {
                "version": (
                    1
                    if self.server.response_mode == "version"
                    else bridge_client_module.PROTOCOL_VERSION
                ),
                "id": response_id,
                "ok": True,
                "result": result,
            }
        response["challenge"] = challenge
        response["client_nonce"] = client_nonce
        response["server_proof"] = bridge_client_module._authentication_proof(
            TOKEN,
            "server_response",
            response,
        )
        if self.server.response_mode in {"bad_response_proof", "bad_error_proof"}:
            response["server_proof"] = "0" * 64
        self.wfile.write((json.dumps(response) + "\n").encode("utf-8"))


def _write_config(path: Path, port: int, token: str = TOKEN) -> None:
    path.write_text(
        json.dumps(
            {"version": 1, "host": "127.0.0.1", "port": port, "token": token}
        ),
        encoding="utf-8",
    )


def _serve(mode: str = "ok") -> tuple[_Server, threading.Thread]:
    server = _Server(mode)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def test_authenticated_round_trip_never_sends_plaintext_token(tmp_path: Path) -> None:
    server, _ = _serve()
    try:
        config = tmp_path / "bridge.json"
        _write_config(config, server.server_address[1])
        result = LiveBridgeClient(config).call("ping", {"value": 3})

        assert result == {"method": "ping", "params": {"value": 3}}
        assert len(server.client_hellos) == 1
        assert set(server.client_hellos[0]) == {
            "version",
            "type",
            "client_nonce",
        }
        assert server.client_hellos[0]["type"] == "client_hello"
        assert TOKEN.encode("ascii") not in server.raw_client_hellos[0]
        assert b"ping" not in server.raw_client_hellos[0]
        assert len(server.requests) == 1
        assert server.requests[0]["version"] == bridge_client_module.PROTOCOL_VERSION
        assert "token" not in server.requests[0]
        assert TOKEN.encode("ascii") not in server.raw_requests[0]
        assert server.requests[0]["method"] == "ping"
        assert bridge_client_module._proof_matches(
            TOKEN,
            "client_request",
            {
                key: value
                for key, value in server.requests[0].items()
                if key != "client_proof"
            },
            server.requests[0]["client_proof"],
        )
        assert isinstance(server.requests[0]["id"], str)
        assert server.requests[0]["id"]
    finally:
        server.shutdown()
        server.server_close()


def test_client_accepts_partial_authenticated_hello(tmp_path: Path) -> None:
    server, _ = _serve("partial_hello")
    try:
        config = tmp_path / "bridge.json"
        _write_config(config, server.server_address[1])

        result = LiveBridgeClient(config).call("ping")

        assert result == {"method": "ping", "params": {}}
        assert len(server.requests) == 1
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize(
    ("mode", "message"),
    [
        ("bad_hello_json", "invalid hello JSON"),
        ("bad_hello_proof", "server authentication failed"),
        ("hello_version", "hello protocol version mismatch"),
        ("oversized_hello", "hello exceeded"),
        ("client_nonce_mismatch", "hello client nonce mismatch"),
        ("replayed_hello", "hello client nonce mismatch"),
    ],
)
def test_untrusted_server_hello_fails_before_client_sends_any_request(
    tmp_path: Path, mode: str, message: str
) -> None:
    server, _ = _serve(mode)
    try:
        config = tmp_path / "bridge.json"
        _write_config(config, server.server_address[1])

        with pytest.raises(BridgeError, match=message):
            LiveBridgeClient(config).call("ping", {"secret_input": "never-send"})

        assert server.raw_requests == []
    finally:
        server.shutdown()
        server.server_close()


def test_bad_response_proof_is_rejected_after_dispatch(tmp_path: Path) -> None:
    server, _ = _serve("bad_response_proof")
    try:
        config = tmp_path / "bridge.json"
        _write_config(config, server.server_address[1])

        with pytest.raises(BridgeError, match="response authentication failed"):
            LiveBridgeClient(config).call("ping")

        assert len(server.requests) == 1
    finally:
        server.shutdown()
        server.server_close()


def test_bad_error_response_proof_is_rejected_before_error_is_trusted(
    tmp_path: Path,
) -> None:
    server, _ = _serve("bad_error_proof")
    try:
        config = tmp_path / "bridge.json"
        _write_config(config, server.server_address[1])

        with pytest.raises(BridgeError, match="response authentication failed"):
            LiveBridgeClient(config).call("ping")
    finally:
        server.shutdown()
        server.server_close()


def test_wrong_configured_token_fails_server_auth_without_sending_request(
    tmp_path: Path,
) -> None:
    server, _ = _serve()
    try:
        config = tmp_path / "bridge.json"
        _write_config(config, server.server_address[1], token="b" * 64)

        with pytest.raises(BridgeError, match="server authentication failed"):
            LiveBridgeClient(config).call("ping")

        assert server.raw_requests == []
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize("label", ["hello", "response"])
def test_receive_line_uses_absolute_deadline_against_slow_drip(
    monkeypatch: pytest.MonkeyPatch, label: str
) -> None:
    moments = iter([100.0, 100.01, 100.02, 100.031])
    monkeypatch.setattr(
        bridge_client_module.time, "monotonic", lambda: next(moments)
    )

    class _SlowDripConnection:
        def __init__(self) -> None:
            self.timeouts: list[float] = []

        def settimeout(self, value: float) -> None:
            self.timeouts.append(value)

        def recv(self, size: int) -> bytes:
            return b"x"

    connection = _SlowDripConnection()
    with pytest.raises(BridgeError, match=f"{label} absolute deadline expired"):
        bridge_client_module._receive_line(
            connection,
            bridge_client_module.MAX_HELLO_BYTES,
            label,
            100.03,
        )

    assert len(connection.timeouts) == 3
    assert connection.timeouts[0] > connection.timeouts[-1] > 0


@pytest.mark.parametrize(
    ("configured_timeout", "expected_read_timeout"),
    [(42, 47.0), (5, 15.0), (5000, 3605.0), ("invalid", 125.0)],
)
def test_default_socket_timeout_uses_bridge_clamp_plus_margin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    configured_timeout: Any,
    expected_read_timeout: float,
) -> None:
    observed: dict[str, Any] = {"socket_timeouts": []}

    class _Connection:
        client_hello: dict[str, Any] | None = None
        request: dict[str, Any] | None = None
        challenge = "1" * 64
        hello_sent = False

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def settimeout(self, value: float) -> None:
            observed["socket_timeouts"].append(value)

        def sendall(self, payload: bytes) -> None:
            message = json.loads(payload.decode("utf-8"))
            if message.get("type") == bridge_client_module.CLIENT_HELLO_TYPE:
                self.client_hello = message
            else:
                self.request = message

        def recv(self, size: int) -> bytes:
            if not self.hello_sent:
                assert self.client_hello is not None
                self.hello_sent = True
                unsigned_hello = {
                    "version": bridge_client_module.PROTOCOL_VERSION,
                    "type": bridge_client_module.SERVER_HELLO_TYPE,
                    "client_nonce": self.client_hello["client_nonce"],
                    "challenge": self.challenge,
                }
                hello = {
                    **unsigned_hello,
                    "server_proof": bridge_client_module._authentication_proof(
                        TOKEN, "server_hello", unsigned_hello
                    ),
                }
                return (json.dumps(hello) + "\n").encode("utf-8")

            assert self.request is not None
            unsigned_response = {
                "version": bridge_client_module.PROTOCOL_VERSION,
                "id": self.request["id"],
                "ok": True,
                "result": {"pong": True},
                "client_nonce": self.request["client_nonce"],
                "challenge": self.challenge,
            }
            response = {
                **unsigned_response,
                "server_proof": bridge_client_module._authentication_proof(
                    TOKEN, "server_response", unsigned_response
                ),
            }
            return (
                json.dumps(response) + "\n"
            ).encode("utf-8")

    def _connect(address, timeout):
        observed["connect_timeout"] = timeout
        return _Connection()

    monkeypatch.setattr(bridge_client_module.socket, "create_connection", _connect)
    config = tmp_path / "bridge.json"
    config.write_text(
        json.dumps(
            {
                "version": 1,
                "host": "127.0.0.1",
                "port": 48762,
                "token": TOKEN,
                "request_timeout_seconds": configured_timeout,
            }
        ),
        encoding="utf-8",
    )

    result = LiveBridgeClient(config).call("ping")

    assert result == {"pong": True}
    assert observed["connect_timeout"] == 5.0
    assert observed["socket_timeouts"]
    assert all(
        0 < value <= expected_read_timeout
        for value in observed["socket_timeouts"]
    )
    assert max(observed["socket_timeouts"]) > expected_read_timeout - 0.5


def test_response_id_mismatch_is_rejected(tmp_path: Path) -> None:
    server, _ = _serve("mismatch")
    try:
        config = tmp_path / "bridge.json"
        _write_config(config, server.server_address[1])
        with pytest.raises(BridgeError, match="response ID mismatch"):
            LiveBridgeClient(config).call("ping")
    finally:
        server.shutdown()
        server.server_close()


def test_response_protocol_version_mismatch_is_rejected(tmp_path: Path) -> None:
    server, _ = _serve("version")
    try:
        config = tmp_path / "bridge.json"
        _write_config(config, server.server_address[1])
        with pytest.raises(BridgeError, match="protocol version mismatch"):
            LiveBridgeClient(config).call("ping")
    finally:
        server.shutdown()
        server.server_close()


def test_bridge_error_preserves_remote_code(tmp_path: Path) -> None:
    server, _ = _serve("error")
    try:
        config = tmp_path / "bridge.json"
        _write_config(config, server.server_address[1])
        with pytest.raises(BridgeError, match="UNAUTHORIZED: bridge rejected request"):
            LiveBridgeClient(config).call("ping")
    finally:
        server.shutdown()
        server.server_close()


def test_persistent_write_connect_refusal_is_not_outcome_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / "bridge.json"
    _write_config(config, 48762)

    def _refuse_connection(address, timeout):
        raise ConnectionRefusedError("refused before connect")

    monkeypatch.setattr(
        bridge_client_module.socket, "create_connection", _refuse_connection
    )
    params = {"operation_id": "save-refused-001"}

    with pytest.raises(BridgeError, match="Cannot reach ANSA bridge") as caught:
        LiveBridgeClient(config).call_persistent_write(
            "save_database",
            params,
            operation_id=params["operation_id"],
        )

    assert not isinstance(caught.value, BridgeOutcomeUnknown)


@pytest.mark.parametrize("failure_at", ["send", "recv"])
def test_persistent_write_socket_failure_after_dispatch_attempt_is_outcome_unknown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_at: str,
) -> None:
    config = tmp_path / "bridge.json"
    _write_config(config, 48762)
    sent: list[bytes] = []

    class _Connection:
        hello_sent = False
        client_hello: dict[str, Any] | None = None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def settimeout(self, value: float) -> None:
            pass

        def sendall(self, payload: bytes) -> None:
            sent.append(payload)
            message = json.loads(payload.decode("utf-8"))
            if message.get("type") == bridge_client_module.CLIENT_HELLO_TYPE:
                self.client_hello = message
            elif failure_at == "send":
                raise socket.timeout("send timed out after possible partial write")

        def recv(self, size: int) -> bytes:
            if not self.hello_sent:
                assert self.client_hello is not None
                self.hello_sent = True
                unsigned = {
                    "version": bridge_client_module.PROTOCOL_VERSION,
                    "type": bridge_client_module.SERVER_HELLO_TYPE,
                    "client_nonce": self.client_hello["client_nonce"],
                    "challenge": "2" * 64,
                }
                hello = {
                    **unsigned,
                    "server_proof": bridge_client_module._authentication_proof(
                        TOKEN, "server_hello", unsigned
                    ),
                }
                return (json.dumps(hello) + "\n").encode("utf-8")
            raise socket.timeout("response timed out")

    monkeypatch.setattr(
        bridge_client_module.socket,
        "create_connection",
        lambda address, timeout: _Connection(),
    )
    operation_id = f"create-timeout-{failure_at}"
    params = {"operation_id": operation_id}

    with pytest.raises(BridgeOutcomeUnknown) as caught:
        LiveBridgeClient(config).call_persistent_write(
            "create_entity", params, operation_id=operation_id
        )

    assert sent
    assert caught.value.operation_id == operation_id
    assert str(caught.value).startswith(
        f"OUTCOME_UNKNOWN: operation_id={operation_id};"
    )
    assert "Retry only with the same operation_id" in str(caught.value)
    assert "never retry with a new operation_id" in str(caught.value)


@pytest.mark.parametrize(
    "mode",
    [
        "eof",
        "bad_json",
        "bad_response_proof",
        "mismatch",
        "version",
        "ok",
        "wrong_operation_id",
    ],
)
def test_persistent_write_unconfirmed_response_is_outcome_unknown(
    tmp_path: Path, mode: str
) -> None:
    server, _ = _serve(mode)
    try:
        config = tmp_path / "bridge.json"
        _write_config(config, server.server_address[1])
        operation_id = f"save-unconfirmed-{mode}"

        with pytest.raises(BridgeOutcomeUnknown) as caught:
            LiveBridgeClient(config).call_persistent_write(
                "save_database",
                {"operation_id": operation_id},
                operation_id=operation_id,
            )

        assert caught.value.operation_id == operation_id
        assert str(caught.value).startswith(
            f"OUTCOME_UNKNOWN: operation_id={operation_id};"
        )
    finally:
        server.shutdown()
        server.server_close()


def test_persistent_write_explicit_error_is_not_outcome_unknown(
    tmp_path: Path,
) -> None:
    server, _ = _serve("error")
    try:
        config = tmp_path / "bridge.json"
        _write_config(config, server.server_address[1])
        operation_id = "update-explicit-error-001"

        with pytest.raises(
            BridgeError, match="UNAUTHORIZED: bridge rejected request"
        ) as caught:
            LiveBridgeClient(config).call_persistent_write(
                "set_entity_card_values",
                {"operation_id": operation_id},
                operation_id=operation_id,
            )

        assert not isinstance(caught.value, BridgeOutcomeUnknown)
    finally:
        server.shutdown()
        server.server_close()


def test_persistent_write_post_mutation_error_is_outcome_unknown(
    tmp_path: Path,
) -> None:
    server, _ = _serve("api_error")
    try:
        config = tmp_path / "bridge.json"
        _write_config(config, server.server_address[1])
        operation_id = "update-api-error-001"

        with pytest.raises(BridgeOutcomeUnknown) as caught:
            LiveBridgeClient(config).call_persistent_write(
                "set_entity_card_values",
                {"operation_id": operation_id},
                operation_id=operation_id,
            )

        assert caught.value.operation_id == operation_id
        assert str(caught.value).startswith(
            f"OUTCOME_UNKNOWN: operation_id={operation_id};"
        )
    finally:
        server.shutdown()
        server.server_close()


def test_persistent_write_success_returns_confirmed_result(tmp_path: Path) -> None:
    server, _ = _serve("write_ok")
    try:
        config = tmp_path / "bridge.json"
        _write_config(config, server.server_address[1])
        operation_id = "create-success-001"
        params = {"operation_id": operation_id, "entity_type": "NODE"}

        result = LiveBridgeClient(config).call_persistent_write(
            "create_entity", params, operation_id=operation_id
        )

        assert result == {"operation_id": operation_id}
    finally:
        server.shutdown()
        server.server_close()


def test_persistent_write_rejects_operation_id_mismatch_before_connect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / "bridge.json"
    _write_config(config, 48762)
    connect_called = False

    def _unexpected_connect(address, timeout):
        nonlocal connect_called
        connect_called = True
        raise AssertionError("must not connect")

    monkeypatch.setattr(
        bridge_client_module.socket, "create_connection", _unexpected_connect
    )

    with pytest.raises(BridgeError, match="must match params.operation_id"):
        LiveBridgeClient(config).call_persistent_write(
            "save_database",
            {"operation_id": "one-operation-id"},
            operation_id="another-operation-id",
        )

    assert connect_called is False


@pytest.mark.parametrize(
    ("config", "message"),
    [
        (
            {"version": 1, "host": "0.0.0.0", "port": 48762, "token": TOKEN},
            "host must be",
        ),
        (
            {"version": 1, "host": "127.0.0.1", "port": 80, "token": TOKEN},
            "port is invalid",
        ),
        (
            {
                "version": 1,
                "host": "127.0.0.1",
                "port": 48762,
                "token": "short",
            },
            "token is missing or invalid",
        ),
        (
            {"version": 2, "host": "127.0.0.1", "port": 48762, "token": TOKEN},
            "version is unsupported",
        ),
    ],
)
def test_invalid_bridge_config_fails_closed(
    tmp_path: Path, config: dict[str, Any], message: str
) -> None:
    path = tmp_path / "bridge.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(BridgeError, match=message):
        LiveBridgeClient(path).call("ping")
