from __future__ import annotations

import os
import shlex
import subprocess
import time
import queue
import threading
from pathlib import Path
from typing import Any

from .detect import find_java_exe, runs_dir
from .protocol import make_request, read_message, unwrap_response, write_message


class BridgeNotRunning(RuntimeError):
    """Raised when a bridge-backed operation is requested before startup."""


def _split_command(command: str) -> list[str]:
    return shlex.split(command, posix=os.name != "nt")


def default_bridge_command() -> list[str] | None:
    command = os.environ.get("COMSOL_MCP_BRIDGE_COMMAND")
    if command and command.strip():
        return _split_command(command)

    jar = os.environ.get("COMSOL_MCP_BRIDGE_JAR")
    if jar and Path(jar).expanduser().exists():
        java = find_java_exe()
        if java:
            return [str(java), "-jar", str(Path(jar).expanduser().resolve())]
    return None


class ComsolBridgeClient:
    def __init__(self) -> None:
        self.process: subprocess.Popen[str] | None = None
        self.command: list[str] | None = None
        self.started_at: float | None = None
        self._request_lock = threading.Lock()

    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def status(self) -> dict[str, Any]:
        return {
            "running": self.is_running(),
            "pid": self.process.pid if self.process else None,
            "returncode": self.process.poll() if self.process else None,
            "command": self.command,
            "started_at": self.started_at,
        }

    def start(self, command: list[str] | str | None = None, cwd: str | None = None) -> dict[str, Any]:
        if self.is_running():
            return {"ok": True, "already_running": True, **self.status()}

        resolved_command = _split_command(command) if isinstance(command, str) else command
        resolved_command = resolved_command or default_bridge_command()
        if not resolved_command:
            return {
                "ok": False,
                "status": "not_configured",
                "error": "Set COMSOL_MCP_BRIDGE_COMMAND or COMSOL_MCP_BRIDGE_JAR before starting the bridge.",
            }

        run_cwd = Path(cwd).expanduser().resolve() if cwd else runs_dir()
        run_cwd.mkdir(parents=True, exist_ok=True)
        self.process = subprocess.Popen(
            resolved_command,
            cwd=str(run_cwd),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self.command = [str(item) for item in resolved_command]
        self.started_at = time.time()
        return {"ok": True, "already_running": False, **self.status()}

    def stop(self) -> dict[str, Any]:
        if not self.process:
            return {"ok": True, "was_running": False}
        was_running = self.is_running()
        process = self.process
        if was_running:
            try:
                self.request("shutdown", timeout=float(os.environ.get("COMSOL_MCP_BRIDGE_TIMEOUT", "120")))
            except Exception:
                process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
        status = self.status()
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream:
                try:
                    stream.close()
                except Exception:
                    pass
        self.process = None
        return {"ok": True, "was_running": was_running, "last_status": status}

    def request(self, method: str, params: dict[str, Any] | None = None, timeout: float | None = None) -> dict[str, Any]:
        if not self.is_running() or not self.process or not self.process.stdin or not self.process.stdout:
            raise BridgeNotRunning("COMSOL bridge is not running. Call comsol_start_bridge_tool first.")

        with self._request_lock:
            payload = make_request(method, params)
            write_message(self.process.stdin, payload)
            replies: queue.Queue = queue.Queue(maxsize=1)
            stream = self.process.stdout
            def read_reply() -> None:
                try:
                    replies.put((True, read_message(stream)))
                except Exception as exc:
                    replies.put((False, exc))
            reader = threading.Thread(target=read_reply, daemon=True)
            reader.start()
            limit = float(timeout if timeout is not None else os.environ.get("COMSOL_MCP_BRIDGE_TIMEOUT", "120"))
            try:
                ok, response = replies.get(timeout=max(0.01, limit))
            except queue.Empty:
                # Invalidate this IPC process: its late reply must never be used
                # as the response to a later command. Shared server models are
                # not cleared or killed by terminating this owned API worker.
                self.process.terminate()
                self.process.wait(timeout=10)
                reader.join(timeout=2)
                raise TimeoutError(f"COMSOL bridge request {method!r} timed out after {limit:g}s; API worker terminated. Server models were not cleared.") from None
            if not ok:
                raise response
            return unwrap_response(response, payload["id"])
