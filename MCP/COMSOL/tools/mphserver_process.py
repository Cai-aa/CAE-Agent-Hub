from __future__ import annotations

import json
import os
import socket
import subprocess
import time
from pathlib import Path
from typing import Any

from .detect import find_comsol_exe, find_mphserver_exe, runs_dir


STATE_PATH = runs_dir() / "mphserver.json"


def _safe_mkdir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _read_state() -> dict[str, Any] | None:
    if not STATE_PATH.exists():
        return None
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_state(payload: dict[str, Any]) -> None:
    _safe_mkdir(STATE_PATH.parent)
    STATE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def _process_running(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {int(pid)}", "/FO", "CSV"],
            text=True,
            capture_output=True,
            timeout=10,
        )
        return str(int(pid)) in result.stdout
    except Exception:
        return False


def build_mphserver_command(
    comsol_exe: str | None = None,
    port: int = 2036,
    extra_args: list[str] | None = None,
) -> list[str]:
    exe = Path(comsol_exe).expanduser().resolve() if comsol_exe else (find_mphserver_exe() or find_comsol_exe())
    if not exe or not exe.exists():
        raise FileNotFoundError("comsol.exe not found. Set COMSOL_EXE or COMSOL_ROOT.")
    target = [] if exe.name.lower() in {"comsolmphserver.exe", "mphserver.exe", "mphserver"} else ["mphserver"]
    command = [str(exe), *target, "-port", str(int(port))]
    if extra_args:
        command.extend(str(arg) for arg in extra_args)
    return command


def mphserver_status(host: str = "127.0.0.1", port: int = 2036) -> dict[str, Any]:
    state = _read_state() or {}
    pid = state.get("pid")
    return {
        "host": host,
        "port": int(port),
        "listening": _port_open(host, int(port)),
        "state_path": str(STATE_PATH),
        "pid": pid,
        "pid_running": _process_running(pid),
        "command": state.get("command"),
        "created_at": state.get("created_at"),
    }


def start_mphserver(
    host: str = "127.0.0.1",
    port: int = 2036,
    comsol_exe: str | None = None,
    extra_args: list[str] | None = None,
    wait_seconds: float = 20.0,
) -> dict[str, Any]:
    if _port_open(host, int(port)):
        return {"ok": True, "already_listening": True, **mphserver_status(host=host, port=port)}

    command = build_mphserver_command(comsol_exe=comsol_exe, port=port, extra_args=extra_args)
    log_dir = runs_dir() / "logs"
    _safe_mkdir(log_dir)
    stdout_path = log_dir / f"mphserver_{int(port)}.stdout.log"
    stderr_path = log_dir / f"mphserver_{int(port)}.stderr.log"
    stdout = stdout_path.open("a", encoding="utf-8", errors="replace")
    stderr = stderr_path.open("a", encoding="utf-8", errors="replace")
    proc = subprocess.Popen(
        command,
        cwd=str(runs_dir()),
        stdin=subprocess.DEVNULL,
        stdout=stdout,
        stderr=stderr,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    stdout.close()
    stderr.close()

    payload = {
        "pid": proc.pid,
        "command": command,
        "host": host,
        "port": int(port),
        "stdout": str(stdout_path),
        "stderr": str(stderr_path),
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    _write_state(payload)

    deadline = time.time() + max(0.0, float(wait_seconds))
    while time.time() < deadline:
        if _port_open(host, int(port)):
            return {"ok": True, "already_listening": False, **mphserver_status(host=host, port=port)}
        if proc.poll() is not None:
            break
        time.sleep(0.5)

    return {
        "ok": False,
        "status": "started_but_not_listening",
        "returncode": proc.poll(),
        **mphserver_status(host=host, port=port),
    }


def stop_mphserver() -> dict[str, Any]:
    state = _read_state()
    if not state or not state.get("pid"):
        return {"ok": True, "was_running": False, "message": "No MCP-owned mphserver state found."}
    pid = int(state["pid"])
    if not _process_running(pid):
        return {"ok": True, "was_running": False, "pid": pid, "message": "Recorded mphserver process is not running."}
    try:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, text=True, timeout=20)
        return {"ok": True, "was_running": True, "pid": pid}
    except Exception as exc:
        return {"ok": False, "was_running": True, "pid": pid, "error": str(exc)}
