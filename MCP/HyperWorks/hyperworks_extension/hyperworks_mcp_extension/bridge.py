from __future__ import annotations

import hmac
import json
import os
import queue
import socketserver
import threading
import time
import traceback
import uuid
from pathlib import Path
from typing import Any

from .config import load_config, write_status
from .handlers import HandlerRegistry
from .protocol import MAX_REQUEST_BYTES, PendingCall, failure, success


class _BridgeTCPServer(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, runtime):
        self.runtime = runtime
        super().__init__(address, _BridgeRequestHandler)


class _BridgeRequestHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        runtime: BridgeRuntime = self.server.runtime
        request_id = "unknown"
        try:
            raw = self.rfile.readline(MAX_REQUEST_BYTES + 1)
            if len(raw) > MAX_REQUEST_BYTES:
                response = failure(request_id, "REQUEST_TOO_LARGE", "Request exceeds 1 MB")
            elif not raw:
                return
            else:
                request = json.loads(raw.decode("utf-8"))
                request_id = str(request.get("id") or uuid.uuid4().hex)
                token = str(request.get("token", ""))
                if not hmac.compare_digest(token, runtime.token):
                    response = failure(request_id, "UNAUTHORIZED", "Invalid bridge token")
                else:
                    method = request.get("method")
                    params = request.get("params", {})
                    if not isinstance(method, str) or not isinstance(params, dict):
                        response = failure(
                            request_id, "INVALID_REQUEST", "method must be a string and params an object"
                        )
                    elif method not in runtime.registry.methods:
                        response = failure(
                            request_id, "METHOD_NOT_ALLOWED", f"Method is not allowlisted: {method}"
                        )
                    else:
                        pending = PendingCall(request_id, method, params)
                        try:
                            runtime.requests.put_nowait(pending)
                        except queue.Full:
                            response = failure(
                                request_id,
                                "QUEUE_FULL",
                                "HyperWorks main-thread request queue is full",
                            )
                        else:
                            if pending.completed.wait(runtime.request_timeout_seconds):
                                response = pending.response or failure(
                                    request_id, "EMPTY_RESPONSE", "No response was produced"
                                )
                            else:
                                pending.cancelled = True
                                response = failure(
                                    request_id,
                                    "REQUEST_TIMEOUT",
                                    "HyperWorks main-thread execution timed out",
                                )
        except Exception as exc:
            response = failure(request_id, "PROTOCOL_ERROR", str(exc))
        self.wfile.write((json.dumps(response, ensure_ascii=False) + "\n").encode("utf-8"))


class BridgeRuntime:
    def __init__(self):
        self.config_path, self.config = load_config()
        self.host = self.config["host"]
        self.port = self.config["port"]
        self.token = self.config["token"]
        self.request_timeout_seconds = self.config["request_timeout_seconds"]
        self.registry = HandlerRegistry(self.config["allowed_roots"])
        self.requests: queue.Queue[PendingCall] = queue.Queue(maxsize=100)
        self.timer = None
        self.server: _BridgeTCPServer | None = None
        self.server_thread: threading.Thread | None = None
        self.started_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")

    def start(self) -> None:
        if self.server is not None:
            return
        from PyQt6.QtCore import QTimer

        self.server = _BridgeTCPServer((self.host, self.port), self)
        self.server_thread = threading.Thread(
            target=self.server.serve_forever,
            kwargs={"poll_interval": 0.1},
            name="HyperWorksMCPNetwork",
            daemon=True,
        )
        self.server_thread.start()
        self.timer = QTimer()
        self.timer.setInterval(25)
        self.timer.timeout.connect(self._drain_requests)
        self.timer.start()
        self._status("online")
        print(f"HyperWorks MCP Bridge listening on {self.host}:{self.port}")

    def _drain_requests(self) -> None:
        for _ in range(8):
            try:
                pending = self.requests.get_nowait()
            except queue.Empty:
                return
            if pending.cancelled:
                continue
            try:
                result = self.registry.dispatch(pending.method, pending.params)
                pending.response = success(pending.request_id, result)
            except Exception as exc:
                pending.response = failure(
                    pending.request_id,
                    "API_ERROR",
                    f"{exc.__class__.__name__}: {exc}",
                )
                self._log_error(pending.method, exc)
            finally:
                pending.completed.set()

    def _log_error(self, method: str, exc: Exception) -> None:
        path = self.config_path.with_name("bridge-errors.log")
        with path.open("a", encoding="utf-8") as stream:
            stream.write(
                f"[{time.strftime('%Y-%m-%dT%H:%M:%S%z')}] {method}: "
                f"{exc.__class__.__name__}: {exc}\n{traceback.format_exc()}\n"
            )

    def _status(self, state: str) -> None:
        write_status(
            self.config_path,
            {
                "state": state,
                "pid": os.getpid(),
                "host": self.host,
                "port": self.port,
                "started_at": self.started_at,
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "methods": self.registry.allowed_methods,
                "config_path": str(self.config_path),
            },
        )

    def stop(self) -> None:
        if self.timer is not None:
            self.timer.stop()
            self.timer = None
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
        self._status("offline")
        print("HyperWorks MCP Bridge stopped")
