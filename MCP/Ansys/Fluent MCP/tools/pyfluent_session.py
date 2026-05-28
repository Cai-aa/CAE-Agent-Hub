from __future__ import annotations

import contextlib
import io
import os
import uuid
from typing import Any


def _import_pyfluent_core() -> Any:
    try:
        import ansys.fluent.core as pyfluent
    except Exception as exc:
        raise RuntimeError(
            "ansys-fluent-core is not available in this MCP Python environment. "
            "Install the project with the [pyfluent] extra or run pip install ansys-fluent-core."
        ) from exc
    return pyfluent


class PyFluentSessionManager:
    """In-process registry for PyFluent sessions owned by this MCP server."""

    def __init__(self) -> None:
        self.sessions: dict[str, Any] = {}

    def launch_session(
        self,
        session_id: str | None = None,
        dimension: int | str = 3,
        precision: str = "double",
        processor_count: int = 2,
        mode: str = "solver",
        ui_mode: str = "hidden_gui",
        start_timeout: int = 120,
        additional_arguments: str | None = None,
        cleanup_on_exit: bool = True,
    ) -> dict[str, Any]:
        pyfluent = _import_pyfluent_core()
        resolved_id = (session_id or "fluent_" + uuid.uuid4().hex[:8]).strip()
        if not resolved_id:
            raise ValueError("session_id must not be empty")
        if resolved_id in self.sessions:
            raise ValueError(f"session already exists: {resolved_id}")

        kwargs: dict[str, Any] = {
            "dimension": int(dimension),
            "precision": precision,
            "processor_count": max(1, int(processor_count)),
            "mode": mode,
            "ui_mode": ui_mode,
            "start_timeout": int(start_timeout),
            "cleanup_on_exit": cleanup_on_exit,
        }
        fluent_path = os.environ.get("FLUENT_EXE") or os.environ.get("ANSYS_FLUENT_EXE")
        if fluent_path:
            kwargs["fluent_path"] = fluent_path
        if additional_arguments:
            kwargs["additional_arguments"] = additional_arguments

        session = pyfluent.launch_fluent(**kwargs)
        self.sessions[resolved_id] = session
        return {
            "ok": True,
            "session_id": resolved_id,
            "launch_args": kwargs,
            "info": self.session_info(resolved_id),
        }

    def list_sessions(self) -> dict[str, Any]:
        return {"sessions": sorted(self.sessions.keys()), "count": len(self.sessions)}

    def require_session(self, session_id: str = "default") -> Any:
        key = session_id or "default"
        if key not in self.sessions:
            raise KeyError(f"PyFluent session not found: {key}")
        return self.sessions[key]

    def session_info(self, session_id: str = "default") -> dict[str, Any]:
        session = self.require_session(session_id)
        version = None
        try:
            getter = getattr(session, "get_fluent_version", None)
            version = getter() if callable(getter) else None
        except Exception as exc:
            version = f"unavailable: {exc}"
        return {
            "ok": True,
            "session_id": session_id,
            "session_type": type(session).__name__,
            "fluent_version": version,
            "has_tui": hasattr(session, "tui"),
            "has_scheme_eval": hasattr(session, "scheme_eval"),
        }

    def execute_scheme(self, session_id: str, expression: str) -> dict[str, Any]:
        if not expression.strip():
            raise ValueError("expression must not be empty")
        session = self.require_session(session_id)
        result = self._call_scheme(session, expression)
        return {"ok": True, "session_id": session_id, "result": result}

    def run_tui(self, session_id: str, command: str) -> dict[str, Any]:
        if not command.strip():
            raise ValueError("command must not be empty")
        session = self.require_session(session_id)
        result: Any
        if hasattr(session, "execute_tui") and callable(session.execute_tui):
            result = session.execute_tui(command)
        elif hasattr(session, "tui") and callable(session.tui):
            result = session.tui(command)
        else:
            raise RuntimeError("This PyFluent session does not expose a callable TUI interface.")
        return {"ok": True, "session_id": session_id, "result": result}

    def run_python(self, session_id: str, code: str) -> dict[str, Any]:
        if not code.strip():
            raise ValueError("code must not be empty")
        session = self.require_session(session_id)
        stdout = io.StringIO()
        stderr = io.StringIO()
        namespace: dict[str, Any] = {"session": session, "result": None}
        try:
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                exec(code, namespace, namespace)
        except Exception as exc:
            return {
                "ok": False,
                "session_id": session_id,
                "error": str(exc),
                "stdout": stdout.getvalue(),
                "stderr": stderr.getvalue(),
            }
        return {
            "ok": True,
            "session_id": session_id,
            "return_value": namespace.get("result"),
            "stdout": stdout.getvalue(),
            "stderr": stderr.getvalue(),
        }

    def close_session(self, session_id: str = "default") -> dict[str, Any]:
        session = self.require_session(session_id)
        close_error = None
        try:
            if hasattr(session, "exit") and callable(session.exit):
                session.exit()
            elif hasattr(session, "close") and callable(session.close):
                session.close()
        except Exception as exc:
            close_error = str(exc)
        finally:
            self.sessions.pop(session_id, None)
        result = {"ok": close_error is None, "session_id": session_id, "closed": True}
        if close_error:
            result["error"] = close_error
        return result

    @staticmethod
    def _call_scheme(session: Any, expression: str) -> Any:
        evaluator = getattr(session, "scheme_eval", None)
        if callable(evaluator):
            return evaluator(expression)
        if evaluator is not None:
            for name in ("scheme_eval", "eval", "string_eval"):
                candidate = getattr(evaluator, name, None)
                if callable(candidate):
                    return candidate(expression)
        raise RuntimeError("This PyFluent session does not expose a Scheme evaluator.")
