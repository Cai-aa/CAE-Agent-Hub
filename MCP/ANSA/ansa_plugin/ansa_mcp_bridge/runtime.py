from __future__ import annotations

import os
import threading
import time
import traceback
import json
import uuid
from pathlib import Path

from .bridge import PollingBridgeServer
from .config import load_config, write_status
from .handlers import HandlerRegistry, MUTATING_METHODS
from .monitor import Monitor, VERSION, timestamp
from .dashboard import Dashboard


class BridgeRuntime:
    def __init__(self, dock_to_database: bool = False):
        self.config_path, self.config = load_config()
        self.host = self.config["host"]
        self.port = self.config["port"]
        self.token = self.config["token"]
        self.request_timeout_seconds = self.config["request_timeout_seconds"]
        self.monitor = Monitor(self.token)
        self.dashboard = None
        self._last_dashboard_tick = 0.0
        self._last_session_tick = 0.0
        self.registry = HandlerRegistry(
            self.config["allowed_roots"],
            progress_callback=self._show_demo_progress,
            step_callback=self._show_operation_step,
            enable_examples=os.environ.get("ANSA_MCP_ENABLE_EXAMPLES") == "1",
        )
        self.window = None
        self.status_label = None
        self.stop_button = None
        self.timer = None
        self.server = None
        # Compatibility for older diagnostics; network work is timer-polled
        # and no Python background thread is ever created.
        self.server_thread = None
        self.started_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        self.main_thread_id = threading.get_ident()
        self.state = "offline"
        self.timer_tick_at = None
        self.timer_tick_thread_id = None
        self._online_status_written = False
        self._shutdown_complete = True
        self._show_active = False
        self._destroy_requested = False
        self.dock_to_database = dock_to_database

    def start(self) -> dict:
        if self.server is not None:
            return self.describe(self.state)
        from ansa import guitk

        if not guitk.BCApplicationIsGuiMode():
            raise RuntimeError("ANSA MCP bridge requires ANSA GUI mode")

        self._prepare_start()
        try:
            # BCShow on a top-level BCOnExitDestroy window owns the nested GUI
            # lifetime. The plugin callback or Load Script remains blocked here
            # until the user closes the controller, so its child timer stays alive.
            self.window = guitk.BCWindowCreate(
                "ANSA MCP Bridge Runtime", guitk.constants.BCOnExitDestroy
            )
            self.dashboard = Dashboard(self, self.window)
            self.status_label = self.dashboard.status_label
            self.stop_button = guitk.BCPushButtonCreate(
                self.window, "停止桥接 / Stop bridge", self._on_stop_button, None
            )
            guitk.BCWindowSetAcceptFunction(
                self.window, self._on_window_accept, None
            )
            guitk.BCWindowSetRejectFunction(
                self.window, self._on_window_reject, None
            )
            guitk.BCWindowSetOnCloseFunction(
                self.window, self._on_window_close, None
            )

            self.timer = guitk.BCTimerCreate(self.window)
            guitk.BCTimerSetTimeoutFunction(self.timer, self._poll_network, None)
            self.server = PollingBridgeServer((self.host, self.port), self)
            guitk.BCTimerStart(self.timer, 25, False)

            self.state = "starting"
            self.refresh_session()
            write_status(self.config_path, self.describe("starting"))
            if self.dock_to_database:
                # GUITK's documented script sequence: schedule placement at
                # event-loop entry immediately before BCShow. A failed dock
                # leaves a visible floating controller, never a hidden bridge.
                guitk.BCWindowSetSaveSettings(self.window, False)
                guitk.BCTimerSingleShot(0, self._dock_window, self.window)
        except Exception:
            self._shutdown_before_window_close(guitk)
            self._request_window_destroy(guitk)
            raise

        print(f"ANSA MCP Bridge starting on {self.host}:{self.port}")
        self._show_active = True
        try:
            guitk.BCShow(self.window)
        finally:
            # BCOnExitDestroy makes every GUI child handle invalid before
            # BCShow returns. This finalizer therefore performs no guitk calls.
            self._show_active = False
            self._finalize_after_show()
        return self.describe("offline")

    def _dock_window(self, window) -> int:
        try:
            from ansa import guitk

            guitk.BCWindowSetInitTabbedPosition(
                window, "Database", guitk.constants.BCRightSide
            )
        except Exception as exc:
            self._log_error("dock-window", exc)
        return 0

    def _prepare_start(self) -> None:
        self.started_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        self.state = "offline"
        self.timer_tick_at = None
        self.timer_tick_thread_id = None
        self._online_status_written = False
        self._shutdown_complete = False
        self._show_active = False
        self._destroy_requested = False

    def describe(self, state: str | None = None) -> dict:
        value = {
            "dashboard_version": VERSION,
            "state": state or self.state,
            "pid": os.getpid(),
            "host": self.host,
            "port": self.port,
            "started_at": self.started_at,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "main_thread_id": self.main_thread_id,
            "session_nonce": self.registry.session_nonce,
            "methods": self.registry.allowed_methods,
            "config_path": str(self.config_path),
        }
        if self.timer_tick_at is not None:
            value["timer_tick_at"] = self.timer_tick_at
            value["timer_tick_thread_id"] = self.timer_tick_thread_id
        return value

    def refresh_session(self) -> bool:
        try:
            info = self.registry.get_session_info()
            app = info.get("application", {})
            self.monitor.session = self.monitor.safe({
                "version": app.get("version", "unknown") if isinstance(app, dict) else "unknown",
                "database": info["database"], "deck": info["deck"],
                "deck_name": info["deck_name"], "pid": info["pid"],
                "main_thread": info["thread_id"] == info["bridge_main_thread_id"],
                "sampled_at": timestamp(),
            })
            self.monitor.revision += 1
            return True
        except Exception as exc:
            self._log_error("session-snapshot", exc)
            return False

    def _model_snapshot(self) -> dict:
        start = time.monotonic()
        try:
            # No background or periodic entity traversal. NASTRAN uses GRID.
            _, _, session, deck = self.registry._context()
            node_type = "GRID" if str(session.DeckName(deck)).upper() == "NASTRAN" else "NODE"
            summary = self.registry.get_model_summary(
                [node_type, "__ELEMENTS__", "FACE", "__PROPERTIES__", "__MATERIALS__"]
            )
            summary["sampled_at"] = timestamp()
            summary["elapsed_seconds"] = round(time.monotonic() - start, 3)
            return self.monitor.safe(summary)
        except Exception as exc:
            return {"sampled_at": timestamp(), "error": self.monitor.safe(str(exc))}

    def refresh_model_snapshot(self) -> None:
        self.refresh_session()
        self.monitor.model = self._model_snapshot()
        self.monitor.revision += 1

    def dispatch(self, method: str, params: dict):
        """Observe authenticated requests, preserving the handler's exact outcome."""
        started = time.monotonic()
        event = self.monitor.begin(method, params)
        capture = self.monitor.capture_changes and method in MUTATING_METHODS and method not in {
            "refresh_view", "set_fixed_cantilever_phase"}
        before = self._model_snapshot() if capture else None
        self._render_dashboard()
        # Do not pump GUI events here: it could re-enter model mutation dispatch.
        result = None
        error = None
        try:
            result = self.registry.dispatch(method, params)
            return result
        except Exception as exc:
            error = exc
            raise
        finally:
            try:
                after = self._model_snapshot() if capture else None
                self.monitor.finish(event, started, result, error, before, after)
                if not capture and method in MUTATING_METHODS and method not in {"refresh_view", "set_fixed_cantilever_phase"}:
                    event["model_change"] = {"status": "disabled", "note": "Count sampling was disabled for this request."}
                    self.monitor.last_change = event["model_change"]
                self.refresh_session()
                self._render_dashboard()
            except Exception as monitor_error:
                # Monitoring must never convert a committed write into a retry.
                self._log_error("monitor", monitor_error)

    def _render_dashboard(self) -> None:
        if self.dashboard is not None:
            try:
                self.dashboard.tick()
            except Exception as exc:
                self._log_error("dashboard", exc)

    def export_monitor(self) -> Path:
        root = Path(self.config["allowed_roots"][0]).resolve()
        folder = (root / "diagnostics").resolve()
        if not folder.is_relative_to(root):
            raise ValueError("Diagnostic export escaped the allowed workspace")
        folder.mkdir(exist_ok=True)
        path = folder / ("ansa-mcp-" + time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8] + ".json")
        with path.open("x", encoding="utf-8") as stream:
            json.dump(self.monitor.export(), stream, ensure_ascii=False, indent=2, allow_nan=False)
        return path

    def _poll_network(self, timer, data) -> int:
        thread_id = threading.get_ident()
        if thread_id != self.main_thread_id:
            self._log_error(
                "poll",
                RuntimeError("ANSA MCP polling callback left the ANSA main thread"),
            )
            return 0
        if self.server is None:
            return 0
        try:
            self.server.poll()
        except Exception as exc:
            # A recurring GUI callback must stay alive after a transient
            # network failure; diagnostics retain the full traceback.
            self._log_error("poll", exc)
            return 0

        if self.timer_tick_at is None:
            self.timer_tick_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            self.timer_tick_thread_id = thread_id
            self.state = "online"
            self._update_online_label()
        if not self._online_status_written:
            try:
                write_status(self.config_path, self.describe("online"))
            except Exception as exc:
                self._log_error("online-status", exc)
            else:
                self._online_status_written = True
        if time.monotonic() - self._last_dashboard_tick >= 1.0:
            self._last_dashboard_tick = time.monotonic()
            if time.monotonic() - self._last_session_tick >= 5.0:
                self._last_session_tick = time.monotonic()
                self.refresh_session()
            self._render_dashboard()
        return 0

    def _update_online_label(self) -> None:
        if self.status_label is None:
            return
        try:
            from ansa import guitk

            guitk.BCLabelSetText(
                self.status_label,
                (
                    f"ANSA MCP bridge is online on {self.host}:{self.port}.\n"
                    "Keep this window open. Close it to stop the bridge."
                ),
            )
        except Exception as exc:
            self._log_error("status-label", exc)

    def _show_demo_progress(self, run_id: str, phase: str) -> None:
        """Show bounded workflow state in the existing visible bridge window."""
        if self.status_label is None:
            return
        from ansa import guitk

        labels = {
            "importing": "Importing fixed cantilever into this ANSA window",
            "model_visible": "Cantilever mesh is visible in ANSA",
            "exported": "Live ANSA model was exported for Abaqus",
            "solving": "Abaqus/Standard is solving; ANSA keeps the input model visible",
            "solved": "Abaqus/Standard returned; inspect solver evidence",
            "verified": "ODB checks passed; inspect results in META",
            "solver_failed": "Solver or result verification failed; inspect logs",
        }
        message = labels.get(phase)
        if message is None:
            return
        try:
            guitk.BCLabelSetText(
                self.status_label,
                f"ANSA MCP live demo {run_id[:8]}: {message}.\n"
                "Keep this bridge window open during the workflow.",
            )
        except Exception as exc:
            self._log_error("demo-progress", exc)

    def _show_operation_step(self, event: dict) -> None:
        """Show the latest generic MCP step in ANSA's visible controller."""
        if self.status_label is None:
            return
        try:
            from ansa import guitk

            label = str(event.get("label", event.get("method", "operation")))[:120]
            state = str(event.get("status", "unknown"))
            redraw = event.get("view_refresh", {})
            view = "redraw requested" if redraw.get("returned_success") else "redraw FAILED"
            guitk.BCLabelSetText(
                self.status_label,
                f"ANSA MCP step #{event['sequence']}: {label}\n"
                f"{state}; {view}. Keep this bridge window open.",
            )
        except Exception as exc:
            self._log_error("operation-step", exc)

    def _on_window_accept(self, window, data) -> int:
        from ansa import guitk

        self._shutdown_before_window_close(guitk)
        return 1

    def _on_window_reject(self, window, data) -> int:
        from ansa import guitk

        self._shutdown_before_window_close(guitk)
        return 1

    def _on_window_close(self, window, data) -> int:
        from ansa import guitk

        self._shutdown_before_window_close(guitk)
        # The on-close return is reserved; official guidance is to return 0.
        return 0

    def _on_stop_button(self, button, data) -> int:
        from ansa import guitk

        self._shutdown_before_window_close(guitk)
        self._request_window_destroy(guitk)
        return 0

    def _log_error(self, method: str, exc: Exception) -> None:
        self.monitor.add_error(method, f"{exc.__class__.__name__}: {exc}")
        path = self.config_path.with_name("bridge-errors.log")
        try:
            if path.is_file() and path.stat().st_size > 512_000:
                path.replace(path.with_suffix(".log.previous"))
            with path.open("a", encoding="utf-8") as stream:
                stream.write(self.monitor.safe(
                    f"[{time.strftime('%Y-%m-%dT%H:%M:%S%z')}] {method}: "
                    f"{exc.__class__.__name__}: {exc}\n{traceback.format_exc()}\n"
                ))
        except Exception:
            # Diagnostics must never break a GUI callback or cleanup path.
            pass

    def _shutdown_before_window_close(self, guitk) -> dict:
        """Stop live resources while the BCOnExitDestroy handles are valid."""

        if self._shutdown_complete:
            return self.describe("offline")
        # Mark first so nested/repeated X, Cancel, Enter, or Stop events cannot
        # operate on the same timer/server twice.
        self._shutdown_complete = True

        if self.timer is not None:
            timer = self.timer
            self.timer = None
            try:
                guitk.BCTimerStop(timer)
            except Exception as exc:
                self._log_error("stop-timer", exc)

        if self.server is not None:
            server = self.server
            self.server = None
            try:
                server.close()
            except Exception as exc:
                self._log_error("stop-server", exc)

        self.state = "offline"
        value = self.describe("offline")
        try:
            write_status(self.config_path, value)
        except Exception as exc:
            self._log_error("offline-status", exc)
        print("ANSA MCP Bridge stopped")
        return value

    def _request_window_destroy(self, guitk) -> None:
        """Schedule the one explicit destroy used by Stop/startup failure."""

        if self.window is None or self._destroy_requested:
            return
        self._destroy_requested = True
        try:
            guitk.BCDestroyLater(self.window)
        except Exception as exc:
            self._log_error("stop-window", exc)

    def _finalize_after_show(self) -> None:
        """Finalize after BCShow invalidated all BCOnExitDestroy GUI handles."""

        # Normal X/Cancel/Accept/Stop callbacks already stopped these resources.
        # If BCShow returned unexpectedly, do only non-GUI cleanup here.
        if self.server is not None:
            server = self.server
            self.server = None
            try:
                server.close()
            except Exception as exc:
                self._log_error("post-show-server", exc)
        self.timer = None
        self.window = None
        self.status_label = None
        self.stop_button = None
        self.dashboard = None

        if not self._shutdown_complete:
            self._shutdown_complete = True
            self.state = "offline"
            try:
                write_status(self.config_path, self.describe("offline"))
            except Exception as exc:
                self._log_error("post-show-status", exc)

    def stop(self) -> dict:
        from ansa import guitk

        value = self._shutdown_before_window_close(guitk)
        # stop() is an explicit path rather than an automatic window close, so
        # schedule exactly one destruction while the handle is still valid.
        if self._show_active:
            self._request_window_destroy(guitk)
        return value


_RUNTIME = None


def start(dock_to_database: bool = False) -> dict:
    global _RUNTIME
    if _RUNTIME is None:
        _RUNTIME = BridgeRuntime(dock_to_database=dock_to_database)
    runtime = _RUNTIME
    was_active = runtime.server is not None
    try:
        value = runtime.start()
    except Exception:
        if not was_active and _RUNTIME is runtime:
            _RUNTIME = None
        raise
    # A top-level BCShow returns only after BCOnExitDestroy has invalidated the
    # controller and its children. Drop that runtime so the next Load Script
    # creates a fresh HandlerRegistry/session_nonce and fresh GUI handles.
    if not was_active and runtime.state == "offline" and _RUNTIME is runtime:
        _RUNTIME = None
    return value


def stop() -> dict:
    global _RUNTIME
    if _RUNTIME is None:
        return {"state": "offline", "already_stopped": True}
    value = _RUNTIME.stop()
    _RUNTIME = None
    return value


def status() -> dict:
    if _RUNTIME is None:
        return {"state": "offline"}
    return _RUNTIME.describe()
