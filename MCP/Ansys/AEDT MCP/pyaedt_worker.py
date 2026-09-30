from __future__ import annotations

import contextlib
import os
import sys
from typing import Any, Callable


def _bridge_configured_aedt_install() -> None:
    """Expose the configured AEDT install using PyAEDT's expected env name."""
    install_dir = os.environ.get("AEDT_INSTALL_DIR")
    version = os.environ.get("AEDT_VERSION")
    if not install_dir or not version:
        return
    try:
        year, release = version.split(".", 1)
        version_code = f"{year[-2:]}{int(release)}"
    except (TypeError, ValueError):
        return
    os.environ.setdefault(f"ANSYSEM_ROOT{version_code}", install_dir)


_bridge_configured_aedt_install()

from aedt_close_watcher import AedtCloseWatcher
from pyaedt_backend import BackendCommandError, PyAedtBackend
from worker_protocol import WorkerProtocolError, WorkerRequest, WorkerResponse


def run_request_line(
    payload: str,
    *,
    backend_factory: Callable[[], Any] = PyAedtBackend,
) -> tuple[WorkerResponse, int]:
    request_id = "unknown"
    try:
        request = WorkerRequest.from_json(payload.strip())
        request_id = request.request_id
    except WorkerProtocolError as exc:
        return WorkerResponse.failure(request_id, "invalid_request", str(exc)), 2

    try:
        backend = backend_factory()
        result = backend.execute(request.target, request.command, request.arguments)
        return WorkerResponse.success(request.request_id, result), 0
    except BackendCommandError as exc:
        return WorkerResponse.failure(request.request_id, "invalid_command", str(exc)), 1
    except Exception as exc:
        return WorkerResponse.failure(request.request_id, "backend_error", str(exc)), 1


def handle_close_intent(
    backend: Any,
    reason: str,
    *,
    exit_fn: Callable[[int], Any] = os._exit,
) -> None:
    sys.stderr.write(f"AEDT close intent detected: {reason}\n")
    try:
        backend.close_for_user_request()
    finally:
        sys.stderr.flush()
        exit_fn(0)


def run_stream(
    input_stream: Any,
    output_stream: Any,
    *,
    backend_factory: Callable[[], Any] = PyAedtBackend,
) -> int:
    backend = backend_factory()
    watcher = AedtCloseWatcher(
        session_pid=lambda: getattr(backend, "session_pid", None),
        on_close_intent=lambda reason: handle_close_intent(backend, reason),
    )
    watcher.start()
    released = False
    try:
        for payload in input_stream:
            if not payload.strip():
                continue
            try:
                request = WorkerRequest.from_json(payload.strip())
            except WorkerProtocolError as exc:
                response = WorkerResponse.failure("unknown", "invalid_request", str(exc))
            else:
                if request.command == "release_connection":
                    try:
                        with contextlib.redirect_stdout(sys.stderr):
                            released = bool(backend.release())
                        response = WorkerResponse.success(
                            request.request_id,
                            {"released": released},
                        )
                    except Exception as exc:
                        response = WorkerResponse.failure(
                            request.request_id,
                            "backend_error",
                            str(exc),
                        )
                    output_stream.write(response.to_json() + "\n")
                    output_stream.flush()
                    return 0

                with contextlib.redirect_stdout(sys.stderr):
                    response, _ = run_request_line(
                        payload,
                        backend_factory=lambda: backend,
                    )

            output_stream.write(response.to_json() + "\n")
            output_stream.flush()
        return 0
    finally:
        watcher.stop()
        if not released:
            try:
                with contextlib.redirect_stdout(sys.stderr):
                    backend.release()
            except Exception as exc:
                sys.stderr.write(f"AEDT broker release failed: {exc}\n")


def main() -> int:
    payload = sys.stdin.read()
    with contextlib.redirect_stdout(sys.stderr):
        response, exit_code = run_request_line(payload)
    sys.stdout.write(response.to_json() + "\n")
    sys.stdout.flush()
    return exit_code


def exit_without_pyaedt_cleanup(
    exit_code: int,
    *,
    exit_fn: Callable[[int], Any] = os._exit,
) -> None:
    sys.stdout.flush()
    sys.stderr.flush()
    exit_fn(exit_code)


if __name__ == "__main__":
    if "--serve" in sys.argv[1:]:
        raise SystemExit(run_stream(sys.stdin, sys.stdout))
    # Compatibility mode handles one request and intentionally skips PyAEDT's
    # process-exit callback. WorkerClient uses the persistent --serve mode.
    exit_without_pyaedt_cleanup(main())
