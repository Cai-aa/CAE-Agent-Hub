from __future__ import annotations

import json
import secrets
import socket
import sys
import threading
import time
from types import ModuleType, SimpleNamespace

import pytest

from ansa_mcp_bridge import bridge as bridge_module
from ansa_mcp_bridge.bridge import MAX_ACTIVE_CONNECTIONS, PollingBridgeServer
from ansa_mcp_bridge.protocol import (
    MAX_HELLO_BYTES,
    PROTOCOL_VERSION,
    REQUEST_TYPE,
    authentication_proof,
    canonical_json_bytes,
    proof_matches,
    server_hello,
)
from ansa_mcp_bridge import runtime as runtime_module


TOKEN = "b" * 64


class _Registry:
    def __init__(self) -> None:
        self.methods = {"ping": object()}
        self.allowed_methods = ["ping"]
        self.session_nonce = "test-session"
        self.calls: list[tuple[str, dict, int]] = []

    def dispatch(self, method: str, params: dict) -> dict:
        self.calls.append((method, params, threading.get_ident()))
        return {"pong": True, "echo": params}


def _start_server() -> tuple[PollingBridgeServer, SimpleNamespace]:
    runtime = SimpleNamespace(token=TOKEN, registry=_Registry())
    server = PollingBridgeServer(("127.0.0.1", 0), runtime)
    return server, runtime


class _SocketOptionRecorder:
    def __init__(self) -> None:
        self.calls: list[tuple[int, int, int]] = []

    def setsockopt(self, level: int, option: int, value: int) -> None:
        self.calls.append((level, option, value))


def test_windows_listener_uses_exclusive_address_not_reuse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    listener = _SocketOptionRecorder()
    exclusive_option = 0x7FFF
    monkeypatch.setattr(bridge_module.sys, "platform", "win32")
    monkeypatch.setattr(
        bridge_module.socket,
        "SO_EXCLUSIVEADDRUSE",
        exclusive_option,
        raising=False,
    )

    bridge_module._configure_listener_security(listener)

    assert listener.calls == [
        (bridge_module.socket.SOL_SOCKET, exclusive_option, 1)
    ]
    assert all(
        option != bridge_module.socket.SO_REUSEADDR
        for _, option, _ in listener.calls
    )


def test_windows_listener_fails_closed_without_exclusive_option(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    listener = _SocketOptionRecorder()
    monkeypatch.setattr(bridge_module.sys, "platform", "win32")
    monkeypatch.delattr(
        bridge_module.socket, "SO_EXCLUSIVEADDRUSE", raising=False
    )

    with pytest.raises(RuntimeError, match="SO_EXCLUSIVEADDRUSE is required"):
        bridge_module._configure_listener_security(listener)

    assert listener.calls == []


def test_posix_listener_uses_reuse_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    listener = _SocketOptionRecorder()
    monkeypatch.setattr(bridge_module.sys, "platform", "linux")

    bridge_module._configure_listener_security(listener)

    assert listener.calls == [
        (
            bridge_module.socket.SOL_SOCKET,
            bridge_module.socket.SO_REUSEADDR,
            1,
        )
    ]


def test_listener_rejects_duplicate_live_bind() -> None:
    first, _ = _start_server()
    second_runtime = SimpleNamespace(token=TOKEN, registry=_Registry())
    try:
        with pytest.raises(OSError):
            PollingBridgeServer(first.server_address, second_runtime)
    finally:
        first.close()


def _receive_response(
    server: PollingBridgeServer, connection: socket.socket, timeout: float = 2.0
) -> dict:
    connection.setblocking(False)
    data = bytearray()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        server.poll()
        try:
            chunk = connection.recv(65_536)
        except BlockingIOError:
            time.sleep(0.001)
            continue
        if not chunk:
            break
        data.extend(chunk)
        if b"\n" in data:
            break
    assert b"\n" in data, bytes(data)
    return json.loads(bytes(data).split(b"\n", 1)[0].decode("utf-8"))


def _request(server: PollingBridgeServer, payload: dict) -> dict:
    with socket.create_connection(("127.0.0.1", server.server_address[1]), timeout=2.0) as connection:
        client_nonce = secrets.token_hex(32)
        client_hello = {
            "version": PROTOCOL_VERSION,
            "type": "client_hello",
            "client_nonce": client_nonce,
        }
        connection.sendall((json.dumps(client_hello) + "\n").encode("utf-8"))
        hello = _receive_response(server, connection)
        unsigned_hello = dict(hello)
        server_proof = unsigned_hello.pop("server_proof")
        assert proof_matches(TOKEN, "server_hello", unsigned_hello, server_proof)
        assert hello["client_nonce"] == client_nonce

        unsigned_request = {
            "version": payload.get("version", PROTOCOL_VERSION),
            "type": REQUEST_TYPE,
            "id": payload["id"],
            "method": payload["method"],
            "params": payload.get("params", {}),
            "client_nonce": client_nonce,
            "challenge": hello["challenge"],
        }
        request = {
            **unsigned_request,
            "client_proof": authentication_proof(
                payload.get("proof_token", TOKEN),
                "client_request",
                unsigned_request,
            ),
        }
        connection.sendall((json.dumps(request) + "\n").encode("utf-8"))
        response = _receive_response(server, connection)
        unsigned_response = dict(response)
        response_proof = unsigned_response.pop("server_proof")
        assert proof_matches(
            TOKEN, "server_response", unsigned_response, response_proof
        )
        return response


@pytest.mark.parametrize(
    ("version", "expected_code"),
    [
        (1, "PROTOCOL_VERSION_UNSUPPORTED"),
        (999, "PROTOCOL_VERSION_UNSUPPORTED"),
    ],
)
def test_socket_bridge_rejects_old_or_unknown_wire_version_before_dispatch(
    version: int, expected_code: str
) -> None:
    server, runtime = _start_server()
    try:
        response = _request(
            server,
            {
                "version": version,
                "id": "request-rejected",
                "method": "ping",
                "params": {},
            },
        )
        assert response["id"] == "request-rejected"
        assert response["ok"] is False
        assert response["error"]["code"] == expected_code
        assert runtime.registry.calls == []
    finally:
        server.close()


def test_socket_bridge_rejects_unknown_method_before_dispatch() -> None:
    server, runtime = _start_server()
    try:
        response = _request(
            server,
            {
                "version": PROTOCOL_VERSION,
                "id": "request-unknown-method",
                "method": "run_python",
                "params": {"code": "dangerous()"},
            },
        )
        assert response["id"] == "request-unknown-method"
        assert response["ok"] is False
        assert response["error"]["code"] == "METHOD_NOT_ALLOWED"
        assert runtime.registry.calls == []
    finally:
        server.close()


def test_socket_bridge_dispatches_success_on_polling_thread() -> None:
    server, runtime = _start_server()
    polling_thread_id = threading.get_ident()
    try:
        response = _request(
            server,
            {
                "version": PROTOCOL_VERSION,
                "id": "request-success",
                "method": "ping",
                "params": {"value": 7},
            },
        )
        assert response == {
            "version": PROTOCOL_VERSION,
            "id": "request-success",
            "ok": True,
            "result": {"pong": True, "echo": {"value": 7}},
            "client_nonce": response["client_nonce"],
            "challenge": response["challenge"],
            "server_proof": response["server_proof"],
        }
        assert runtime.registry.calls == [("ping", {"value": 7}, polling_thread_id)]
    finally:
        server.close()


def test_socket_bridge_times_out_idle_unauthenticated_connection() -> None:
    server, runtime = _start_server()
    server.read_timeout_seconds = 0.05
    connection = socket.create_connection(
        ("127.0.0.1", server.server_address[1]), timeout=2.0
    )
    try:
        server.poll(now=100.0)
        assert server.active_connection_count == 1
        server.poll(now=100.051)
        connection.settimeout(1.0)
        try:
            data = connection.recv(65_536)
        except ConnectionResetError:
            data = b""
        assert data == b""
        assert runtime.registry.calls == []
    finally:
        connection.close()
        server.close()


@pytest.mark.parametrize(
    "client_hello",
    [
        {"version": 2, "type": "client_hello", "client_nonce": "1" * 64},
        {"version": PROTOCOL_VERSION, "type": "wrong", "client_nonce": "1" * 64},
        {"version": PROTOCOL_VERSION, "type": "client_hello", "client_nonce": "short"},
        {
            "version": PROTOCOL_VERSION,
            "type": "client_hello",
            "client_nonce": "1" * 64,
            "extra": True,
        },
    ],
)
def test_invalid_client_hello_schema_fails_closed(client_hello: dict) -> None:
    server, runtime = _start_server()
    connection = socket.create_connection(
        ("127.0.0.1", server.server_address[1]), timeout=2.0
    )
    try:
        connection.sendall((json.dumps(client_hello) + "\n").encode("utf-8"))
        for _ in range(3):
            server.poll()
        connection.settimeout(1.0)
        try:
            data = connection.recv(65_536)
        except ConnectionResetError:
            data = b""
        assert data == b""
        assert runtime.registry.calls == []
    finally:
        connection.close()
        server.close()


def test_oversized_client_hello_fails_closed() -> None:
    server, runtime = _start_server()
    connection = socket.create_connection(
        ("127.0.0.1", server.server_address[1]), timeout=2.0
    )
    try:
        connection.sendall(b"{" + b" " * MAX_HELLO_BYTES + b"\n")
        for _ in range(3):
            server.poll()
        connection.settimeout(1.0)
        try:
            data = connection.recv(65_536)
        except ConnectionResetError:
            data = b""
        assert data == b""
        assert runtime.registry.calls == []
    finally:
        connection.close()
        server.close()


def test_socket_bridge_challenges_are_fresh_and_server_authenticated() -> None:
    server, _ = _start_server()
    connections = [
        socket.create_connection(
            ("127.0.0.1", server.server_address[1]), timeout=2.0
        )
        for _ in range(2)
    ]
    try:
        client_nonces = [secrets.token_hex(32) for _ in connections]
        for connection, client_nonce in zip(connections, client_nonces):
            connection.sendall(
                (
                    json.dumps(
                        {
                            "version": PROTOCOL_VERSION,
                            "type": "client_hello",
                            "client_nonce": client_nonce,
                        }
                    )
                    + "\n"
                ).encode("utf-8")
            )
        hellos = [_receive_response(server, connection) for connection in connections]
        assert hellos[0]["challenge"] != hellos[1]["challenge"]
        for hello, client_nonce in zip(hellos, client_nonces):
            unsigned = dict(hello)
            proof = unsigned.pop("server_proof")
            assert unsigned["version"] == PROTOCOL_VERSION
            assert unsigned["client_nonce"] == client_nonce
            assert proof_matches(TOKEN, "server_hello", unsigned, proof)
    finally:
        for connection in connections:
            connection.close()
        server.close()


def test_server_hello_is_bounded_and_partial_nonblocking_writes_resume() -> None:
    class _PartialSocket:
        def __init__(self) -> None:
            self.sent = bytearray()

        def send(self, payload: bytes) -> int:
            count = min(7, len(payload))
            self.sent.extend(payload[:count])
            return count

    server, _ = _start_server()
    sock = _PartialSocket()
    hello = canonical_json_bytes(
        server_hello(TOKEN, "1" * 64, "2" * 64)
    ) + b"\n"
    state = bridge_module._Connection(
        sock=sock,
        address=("127.0.0.1", 12345),
        accepted_at=100.0,
        last_activity=100.0,
        client_nonce="1" * 64,
        challenge="2" * 64,
        hello=hello,
    )
    try:
        assert len(hello) <= MAX_HELLO_BYTES
        while not state.hello_sent:
            server._write_hello_available(state, 100.0)
        assert bytes(sock.sent) == hello
        assert state.hello_offset == len(hello)
    finally:
        server.close()


def test_socket_bridge_invalid_client_proof_fails_closed_without_dispatch() -> None:
    server, runtime = _start_server()
    connection = socket.create_connection(
        ("127.0.0.1", server.server_address[1]), timeout=2.0
    )
    try:
        client_nonce = secrets.token_hex(32)
        connection.sendall(
            (
                json.dumps(
                    {
                        "version": PROTOCOL_VERSION,
                        "type": "client_hello",
                        "client_nonce": client_nonce,
                    }
                )
                + "\n"
            ).encode("utf-8")
        )
        hello = _receive_response(server, connection)
        unsigned = {
            "version": PROTOCOL_VERSION,
            "type": REQUEST_TYPE,
            "id": "wrong-proof",
            "method": "ping",
            "params": {},
            "client_nonce": client_nonce,
            "challenge": hello["challenge"],
        }
        request = {
            **unsigned,
            "client_proof": authentication_proof(
                "c" * 64, "client_request", unsigned
            ),
        }
        wire = (json.dumps(request) + "\n").encode("utf-8")
        assert TOKEN.encode("ascii") not in wire
        connection.sendall(wire)
        for _ in range(3):
            server.poll()
        connection.settimeout(1.0)
        assert connection.recv(65_536) == b""
        assert runtime.registry.calls == []
    finally:
        connection.close()
        server.close()


def test_absolute_request_deadline_is_not_refreshed_by_trickled_bytes() -> None:
    server, runtime = _start_server()
    server.read_timeout_seconds = 10.0
    server.request_deadline_seconds = 0.05
    connection = socket.create_connection(
        ("127.0.0.1", server.server_address[1]), timeout=2.0
    )
    try:
        server.poll(now=100.0)

        for current in (100.01, 100.02, 100.03, 100.04):
            connection.sendall(b" ")
            server.poll(now=current)
            assert server.active_connection_count == 1

        connection.sendall(b" ")
        server.poll(now=100.051)
        assert server.active_connection_count == 0
        connection.settimeout(1.0)
        try:
            closed_data = connection.recv(65_536)
        except ConnectionResetError:
            closed_data = b""
        assert closed_data == b""
        assert runtime.registry.calls == []
    finally:
        connection.close()
        server.close()


def test_socket_bridge_enforces_32_active_connection_limit() -> None:
    server, _ = _start_server()
    connections = [
        socket.create_connection(("127.0.0.1", server.server_address[1]), timeout=2.0)
        for _ in range(MAX_ACTIVE_CONNECTIONS + 1)
    ]
    try:
        # Accept work is intentionally capped at four sockets per GUI tick.
        for _ in range(9):
            server.poll()
        assert server.max_active_connections == 32
        assert server.active_connection_count == 32
        assert server.rejected_connection_count == 1

        connections[-1].settimeout(1.0)
        try:
            data = connections[-1].recv(1)
        except ConnectionResetError:
            data = b""
        assert data == b""
    finally:
        for connection in connections:
            connection.close()
        server.close()


def _install_runtime_fakes(
    monkeypatch: pytest.MonkeyPatch, tmp_path, close_mode: str = "close"
):
    events: list[tuple] = []
    statuses: list[dict] = []
    registries: list[_Registry] = []
    ansa_module = ModuleType("ansa")

    class _GuiTk:
        constants = SimpleNamespace(BCOnExitDestroy=91, BCRightSide=92)
        timer_callbacks: dict[str, object] = {}
        accept_callbacks: dict[str, object] = {}
        reject_callbacks: dict[str, object] = {}
        close_callbacks: dict[str, object] = {}
        stop_callbacks: dict[str, object] = {}
        destroyed = False
        window_count = 0
        single_shots: list[tuple] = []

        @staticmethod
        def BCApplicationIsGuiMode() -> bool:
            return True

        @classmethod
        def BCWindowCreate(cls, title: str, exit_mode: int):
            cls.window_count += 1
            cls.destroyed = False
            window = f"window-{cls.window_count}"
            events.append(("window-create", window, title, exit_mode))
            return window

        @classmethod
        def BCLabelCreate(cls, window, text: str):
            assert not cls.destroyed
            label = f"label-{window}"
            events.append(("label-create", label, window, text))
            return label

        @classmethod
        def BCPushButtonCreate(cls, window, text: str, callback, data):
            assert not cls.destroyed
            button = f"button-{window}"
            cls.stop_callbacks[window] = callback
            events.append(("button-create", button, window, text, data))
            return button

        @classmethod
        def BCWindowSetAcceptFunction(cls, window, callback, data) -> None:
            cls.accept_callbacks[window] = callback
            events.append(("accept-callback", window, data))

        @classmethod
        def BCWindowSetRejectFunction(cls, window, callback, data) -> None:
            cls.reject_callbacks[window] = callback
            events.append(("reject-callback", window, data))

        @classmethod
        def BCWindowSetOnCloseFunction(cls, window, callback, data) -> None:
            cls.close_callbacks[window] = callback
            events.append(("close-callback", window, data))

        @classmethod
        def BCTimerCreate(cls, window):
            assert not cls.destroyed
            timer = f"timer-{window}"
            events.append(("timer-create", timer, window))
            return timer

        @classmethod
        def BCTimerSetTimeoutFunction(cls, timer, callback, data) -> None:
            cls.timer_callbacks[timer] = callback
            events.append(("timer-callback", timer, data))

        @classmethod
        def BCTimerStart(cls, timer, interval: int, single_shot: bool) -> None:
            assert not cls.destroyed
            events.append(("timer-start", timer, interval, single_shot))

        @classmethod
        def BCTimerStop(cls, timer) -> None:
            # BCShow has not returned and BCOnExitDestroy handles are valid.
            assert not cls.destroyed
            events.append(("timer-stop", timer))

        @classmethod
        def BCTimerSingleShot(cls, delay, callback, data) -> None:
            cls.single_shots.append((callback, data))
            events.append(("single-shot", delay, data))

        @classmethod
        def BCWindowSetSaveSettings(cls, window, value) -> None:
            events.append(("save-settings", window, value))

        @classmethod
        def BCWindowSetInitTabbedPosition(cls, window, neighbour, side) -> None:
            events.append(("tab-position", window, neighbour, side))

        @classmethod
        def BCLabelSetText(cls, label, text: str) -> None:
            assert not cls.destroyed
            events.append(("label-set", label, text))

        @classmethod
        def BCDestroyLater(cls, window) -> None:
            assert not cls.destroyed
            events.append(("destroy-later", window))

        @classmethod
        def BCShow(cls, window) -> None:
            assert not cls.destroyed
            events.append(("show-enter", window))
            for callback, data in cls.single_shots:
                assert callback(data) == 0
            cls.single_shots.clear()
            timer = f"timer-{window}"
            assert cls.timer_callbacks[timer](timer, None) == 0
            # Subsequent ticks keep polling but must not rewrite one-time
            # timer evidence or the online status file.
            assert cls.timer_callbacks[timer](timer, None) == 0

            if close_mode == "accept":
                result = cls.accept_callbacks[window](window, None)
            elif close_mode == "reject":
                result = cls.reject_callbacks[window](window, None)
            elif close_mode == "stop":
                result = cls.stop_callbacks[window](f"button-{window}", None)
            else:
                result = cls.close_callbacks[window](window, None)
            events.append(("close-result", close_mode, result))

            # Official BCShow semantics: all BCOnExitDestroy children are
            # invalid by the time this function returns.
            cls.destroyed = True
            events.append(("show-return", window))

    ansa_module.guitk = _GuiTk
    monkeypatch.setitem(sys.modules, "ansa", ansa_module)

    config_path = tmp_path / "bridge.json"
    monkeypatch.setattr(
        runtime_module,
        "load_config",
        lambda: (
            config_path,
            {
                "host": "127.0.0.1",
                "port": 48762,
                "token": TOKEN,
                "allowed_roots": [str(tmp_path)],
                "request_timeout_seconds": 120,
            },
        ),
    )

    def _registry_factory(roots, progress_callback=None, step_callback=None, enable_examples=False):
        assert callable(progress_callback)
        assert callable(step_callback)
        registry = _Registry()
        registry.session_nonce = f"test-session-{len(registries) + 1}"
        registries.append(registry)
        return registry

    monkeypatch.setattr(runtime_module, "HandlerRegistry", _registry_factory)
    class _Dashboard:
        def __init__(self, runtime, window):
            self.status_label = _GuiTk.BCLabelCreate(window, "Dashboard")

        def tick(self):
            pass

    monkeypatch.setattr(runtime_module, "Dashboard", _Dashboard)

    def _write_status(path, value) -> None:
        snapshot = dict(value)
        statuses.append(snapshot)
        events.append(("status", snapshot["state"]))

    monkeypatch.setattr(runtime_module, "write_status", _write_status)

    class _Server:
        def __init__(self, address, runtime) -> None:
            events.append(("server-create", address))
            self.poll_thread_ids: list[int] = []

        def poll(self) -> None:
            self.poll_thread_ids.append(threading.get_ident())
            events.append(("server-poll",))

        def close(self) -> None:
            events.append(("server-close",))

    monkeypatch.setattr(runtime_module, "PollingBridgeServer", _Server)
    return events, statuses, registries, _GuiTk


@pytest.mark.parametrize(
    ("close_mode", "callback_result", "explicit_destroy_count"),
    [
        ("close", 0, 0),
        ("reject", 1, 0),
        ("accept", 1, 0),
        ("stop", 0, 1),
    ],
)
def test_runtime_bcshow_owns_lifecycle_and_cleans_before_destroy(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    close_mode: str,
    callback_result: int,
    explicit_destroy_count: int,
) -> None:
    events, statuses, _, _GuiTk = _install_runtime_fakes(
        monkeypatch, tmp_path, close_mode
    )

    runtime = runtime_module.BridgeRuntime()
    value = runtime.start()

    assert (
        "window-create",
        "window-1",
        "ANSA MCP Bridge Runtime",
        91,
    ) in events
    assert ("timer-start", "timer-window-1", 25, False) in events
    assert runtime.server_thread is None

    # Bind/listen plus timer start is only "starting". The first successful
    # GUI-thread poll is the evidence that advances status to "online".
    assert [item["state"] for item in statuses] == ["starting", "online", "offline"]
    assert "timer_tick_at" not in statuses[0]
    assert "timer_tick_thread_id" not in statuses[0]
    assert statuses[1]["timer_tick_at"]
    assert statuses[1]["timer_tick_thread_id"] == threading.get_ident()
    assert statuses[2]["timer_tick_at"] == statuses[1]["timer_tick_at"]
    assert statuses[2]["timer_tick_thread_id"] == threading.get_ident()

    assert events.index(("show-enter", "window-1")) < events.index(("server-poll",))
    assert events.index(("timer-stop", "timer-window-1")) < events.index(
        ("server-close",)
    )
    assert events.index(("server-close",)) < events.index(("status", "offline"))
    assert events.index(("status", "offline")) < events.index(
        ("show-return", "window-1")
    )
    assert ("close-result", close_mode, callback_result) in events
    assert sum(event[0] == "destroy-later" for event in events) == explicit_destroy_count

    # No cleanup method touched the now-invalid BCOnExitDestroy children after
    # BCShow returned, and every handle was forgotten exactly once.
    assert _GuiTk.destroyed is True
    assert runtime.timer is None
    assert runtime.server is None
    assert runtime.window is None
    assert runtime.status_label is None
    assert runtime.stop_button is None
    assert runtime.state == "offline"
    assert value["state"] == "offline"


def test_module_start_drops_closed_runtime_and_restarts_with_new_session(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    events, statuses, registries, _ = _install_runtime_fakes(
        monkeypatch, tmp_path, "close"
    )
    monkeypatch.setattr(runtime_module, "_RUNTIME", None)

    first = runtime_module.start()
    assert runtime_module._RUNTIME is None
    second = runtime_module.start()
    assert runtime_module._RUNTIME is None

    assert first["session_nonce"] == "test-session-1"
    assert second["session_nonce"] == "test-session-2"
    assert first["session_nonce"] != second["session_nonce"]
    assert len(registries) == 2
    assert sum(event[0] == "window-create" for event in events) == 2
    assert [item["state"] for item in statuses] == [
        "starting",
        "online",
        "offline",
        "starting",
        "online",
        "offline",
    ]


def test_plugin_runtime_tabs_panel_beside_database(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    events, statuses, _, _ = _install_runtime_fakes(monkeypatch, tmp_path)

    runtime = runtime_module.BridgeRuntime(dock_to_database=True)
    result = runtime.start()

    assert ("save-settings", "window-1", False) in events
    assert ("single-shot", 0, "window-1") in events
    assert ("tab-position", "window-1", "Database", 92) in events
    assert events.index(("show-enter", "window-1")) < events.index(
        ("tab-position", "window-1", "Database", 92)
    )
    assert [item["state"] for item in statuses] == ["starting", "online", "offline"]
    assert result["state"] == "offline"
