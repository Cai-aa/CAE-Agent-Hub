from __future__ import annotations

import os
import re
import socket
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from aedt_target import AedtTarget
from worker_client import WorkerClient


class AedtLaunchError(RuntimeError):
    pass


_VERSION_PATTERN = re.compile(r"^20(?P<year>\d{2})\.(?P<release>\d+)$")


def _version_root_variable(version: str) -> str:
    match = _VERSION_PATTERN.fullmatch(version)
    if not match:
        raise AedtLaunchError(
            f"invalid AEDT version {version!r}; expected a value such as 2026.1"
        )
    return f"ANSYSEM_ROOT{match.group('year')}{match.group('release')}"


def resolve_aedt_executable(
    install_dir: str | Path | None,
    version: str = "2026.1",
) -> Path:
    candidates: list[Path] = []
    if install_dir:
        candidates.append(Path(install_dir))
    else:
        configured = os.environ.get("AEDT_INSTALL_DIR")
        if configured:
            candidates.append(Path(configured))
        root = os.environ.get(_version_root_variable(version))
        if root:
            candidates.append(Path(root))

    for candidate in candidates:
        executable = (
            candidate
            if candidate.name.lower() == "ansysedt.exe"
            else candidate / "ansysedt.exe"
        )
        if executable.is_file():
            return executable.resolve()
    raise AedtLaunchError(
        "Cannot locate ansysedt.exe. Set AEDT_INSTALL_DIR or "
        f"{_version_root_variable(version)} to the AEDT {version} installation directory."
    )


def _choose_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _port_is_free(port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False


def _port_is_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.25):
            return True
    except OSError:
        return False


class AedtLauncher:
    def __init__(
        self,
        *,
        worker_client: WorkerClient | None = None,
        process_factory: Callable[..., Any] = subprocess.Popen,
        choose_free_port: Callable[[], int] = _choose_free_port,
        port_is_free: Callable[[int], bool] = _port_is_free,
        port_is_open: Callable[[int], bool] = _port_is_open,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._worker_client = worker_client or WorkerClient()
        self._process_factory = process_factory
        self._choose_free_port = choose_free_port
        self._port_is_free = port_is_free
        self._port_is_open = port_is_open
        self._monotonic = monotonic
        self._sleep = sleep

    def launch(
        self,
        *,
        version: str = "2026.1",
        port: int = 0,
        install_dir: str | Path | None = None,
        non_graphical: bool = False,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        _version_root_variable(version)
        if type(port) is not int or port < 0 or port > 65535:
            raise AedtLaunchError(f"invalid gRPC port: {port!r}")
        if type(non_graphical) is not bool:
            raise AedtLaunchError("non_graphical must be a boolean")
        selected_port = self._choose_free_port() if port == 0 else port
        if not self._port_is_free(selected_port):
            raise AedtLaunchError(f"gRPC port {selected_port} is already in use")

        raw_timeout = (
            timeout
            if timeout is not None
            else os.environ.get("AEDT_LAUNCH_TIMEOUT", "120")
        )
        if isinstance(raw_timeout, bool):
            raise AedtLaunchError("launch timeout must be positive")
        try:
            effective_timeout = float(raw_timeout)
        except (TypeError, ValueError) as exc:
            raise AedtLaunchError("launch timeout must be a positive number") from exc
        if effective_timeout <= 0:
            raise AedtLaunchError("launch timeout must be positive")

        executable = resolve_aedt_executable(install_dir, version)
        command = [str(executable), "-grpcsrv", str(selected_port)]
        if non_graphical:
            command.append("-ng")
        process = self._process_factory(command, cwd=str(executable.parent))

        deadline = self._monotonic() + effective_timeout
        target = AedtTarget("port", selected_port)
        last_probe_error: Exception | None = None
        while self._monotonic() < deadline:
            returncode = process.poll()
            if returncode is not None:
                raise AedtLaunchError(
                    f"AEDT exited with code {returncode} before gRPC was ready"
                )
            if self._port_is_open(selected_port):
                try:
                    info = self._worker_client.execute(
                        target,
                        "ping",
                        {},
                        timeout=min(5.0, max(0.1, deadline - self._monotonic())),
                    )
                    reported_version = (
                        str(info.get("aedt_version", version))
                        if isinstance(info, dict)
                        else version
                    )
                    if reported_version == version:
                        reported_pid = (
                            info.get("pid") if isinstance(info, dict) else None
                        )
                        aedt_pid = (
                            reported_pid
                            if type(reported_pid) is int and reported_pid > 0
                            else int(process.pid)
                        )
                        result = {
                            "pid": aedt_pid,
                            "port": selected_port,
                            "version": version,
                            "connection_mode": "grpc",
                        }
                        if non_graphical:
                            result["non_graphical"] = True
                        return result
                except Exception as exc:  # noqa: BLE001 - vendor readiness errors vary
                    last_probe_error = exc
            self._sleep(0.25)

        release_error: Exception | None = None
        try:
            self._worker_client.release(target, timeout=2.0)
        except Exception as exc:  # noqa: BLE001 - best-effort broker cleanup
            release_error = exc
        diagnostics = []
        if last_probe_error is not None:
            diagnostics.append(f"last readiness probe failed: {last_probe_error}")
        if release_error is not None:
            diagnostics.append(f"broker cleanup failed: {release_error}")
        diagnostic_suffix = f"; {'; '.join(diagnostics)}" if diagnostics else ""
        raise AedtLaunchError(
            f"timed out after {effective_timeout:g}s waiting for AEDT gRPC port {selected_port}; "
            f"AEDT PID {process.pid} was left running for inspection{diagnostic_suffix}"
        )
