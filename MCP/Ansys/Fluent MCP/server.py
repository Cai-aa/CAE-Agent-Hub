from __future__ import annotations

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - dotenv is optional at import time
    def load_dotenv(*args: object, **kwargs: object) -> bool:
        return False

from fastmcp import FastMCP

from tools.fluent_bridge import (
    detect_fluent_environment,
    get_fluent_job_status,
    launch_fluent_journal,
    list_fluent_jobs,
    read_fluent_job_log,
)
from tools.pyfluent_session import PyFluentSessionManager


load_dotenv()

INSTRUCTIONS = """You are controlling ANSYS Fluent through MCP.

Separate environment checks, process launch, and solver state. Use
fluent_detect_tool before launching anything. For live solver interaction,
launch a PyFluent session first, then validate with fluent_session_info_tool
and a small Scheme expression such as (+ 2 3). Prefer journal or case files in
a clean job directory for repeatable solves.
"""

mcp = FastMCP("Ansys Fluent MCP", instructions=INSTRUCTIONS)
sessions = PyFluentSessionManager()


def _env_int(name: str, default: int) -> int:
    value = __import__("os").environ.get(name)
    if value is None or not value.strip():
        return default
    return int(value)


def pyfluent_defaults() -> dict:
    """Read PyFluent launch defaults from the MCP environment."""
    os_environ = __import__("os").environ
    return {
        "dimension": _env_int("PYFLUENT_DIMENSION", 3),
        "precision": os_environ.get("PYFLUENT_PRECISION", "double"),
        "processor_count": _env_int("PYFLUENT_PROCESSOR_COUNT", 2),
        "mode": os_environ.get("PYFLUENT_LAUNCH_MODE", "solver"),
        "ui_mode": os_environ.get("PYFLUENT_UI_MODE", "hidden_gui"),
        "start_timeout": _env_int("PYFLUENT_START_TIMEOUT", 120),
    }


@mcp.tool()
def fluent_detect_tool() -> dict:
    """Detect fluent.exe, ansys-fluent-core, ANSYS_ROOT, and job directories."""
    return detect_fluent_environment()


@mcp.tool()
def fluent_run_journal_tool(
    journal_path: str,
    cwd: str | None = None,
    fluent_exe: str | None = None,
    dimension: str = "3",
    precision: str = "double",
    processor_count: int = 2,
    extra_args: list[str] | None = None,
) -> dict:
    """Launch a Fluent journal asynchronously in batch mode."""
    return launch_fluent_journal(
        journal_path=journal_path,
        cwd=cwd,
        fluent_exe=fluent_exe,
        dimension=dimension,
        precision=precision,
        processor_count=processor_count,
        extra_args=extra_args,
    )


@mcp.tool()
def fluent_job_status_tool(job_id: str) -> dict:
    """Return status for a Fluent journal job launched by this MCP."""
    return get_fluent_job_status(job_id)


@mcp.tool()
def fluent_job_log_tool(job_id: str, stream: str = "stdout", tail_chars: int = 12000) -> dict:
    """Read stdout or stderr for a Fluent journal job."""
    return read_fluent_job_log(job_id=job_id, stream=stream, tail_chars=tail_chars)


@mcp.tool()
def fluent_list_jobs_tool(limit: int = 20) -> dict:
    """List recent Fluent journal jobs."""
    return list_fluent_jobs(limit=limit)


@mcp.tool()
def fluent_launch_session_tool(
    session_id: str = "default",
    dimension: int | None = None,
    precision: str | None = None,
    processor_count: int | None = None,
    mode: str | None = None,
    ui_mode: str | None = None,
    start_timeout: int | None = None,
    additional_arguments: str | None = None,
) -> dict:
    """Launch and retain a live PyFluent session for interactive tools."""
    defaults = pyfluent_defaults()
    return sessions.launch_session(
        session_id=session_id,
        dimension=dimension if dimension is not None else defaults["dimension"],
        precision=precision if precision is not None else defaults["precision"],
        processor_count=processor_count if processor_count is not None else defaults["processor_count"],
        mode=mode if mode is not None else defaults["mode"],
        ui_mode=ui_mode if ui_mode is not None else defaults["ui_mode"],
        start_timeout=start_timeout if start_timeout is not None else defaults["start_timeout"],
        additional_arguments=additional_arguments,
    )


@mcp.tool()
def fluent_list_sessions_tool() -> dict:
    """List live PyFluent sessions owned by this MCP process."""
    return sessions.list_sessions()


@mcp.tool()
def fluent_session_info_tool(session_id: str = "default") -> dict:
    """Return basic metadata for a live PyFluent session."""
    return sessions.session_info(session_id)


@mcp.tool()
def fluent_execute_scheme_tool(session_id: str = "default", expression: str = "(+ 2 3)") -> dict:
    """Evaluate a Scheme expression in a live Fluent session."""
    return sessions.execute_scheme(session_id=session_id, expression=expression)


@mcp.tool()
def fluent_run_tui_tool(session_id: str = "default", command: str = "") -> dict:
    """Run a Fluent TUI command in a live PyFluent session."""
    return sessions.run_tui(session_id=session_id, command=command)


@mcp.tool()
def fluent_run_python_tool(session_id: str = "default", code: str = "") -> dict:
    """Execute Python in this MCP process with a PyFluent `session` variable."""
    return sessions.run_python(session_id=session_id, code=code)


@mcp.tool()
def fluent_close_session_tool(session_id: str = "default") -> dict:
    """Close a live PyFluent session owned by this MCP process."""
    return sessions.close_session(session_id)


@mcp.resource("fluent://agent-instructions")
def agent_instructions() -> str:
    """Fluent operating guidance for MCP clients."""
    return INSTRUCTIONS


@mcp.resource("fluent://environment")
def fluent_environment() -> dict:
    """Current Fluent environment detection."""
    return detect_fluent_environment()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
