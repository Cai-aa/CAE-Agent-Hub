from __future__ import annotations

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    def load_dotenv(*args: object, **kwargs: object) -> bool:
        return False

from fastmcp import FastMCP

from tools.atomistic_bridge import detect_ovito, get_job_status, list_jobs, read_job_log, run_ovito_script


load_dotenv()

INSTRUCTIONS = """Use OVITO through explicit local files only.

Check the required executable before a run. OVITO rendering is postprocessing
evidence and does not prove the upstream molecular-dynamics model or results are physically valid.
"""

mcp = FastMCP("OVITO MCP", instructions=INSTRUCTIONS)


@mcp.tool()
def ovito_detect_tool(ovito_exe: str | None = None, script_command: str | None = None) -> dict:
    """Detect OVITO GUI and independently verify OVITO Python batch capability."""
    return detect_ovito(ovito_exe, script_command)


@mcp.tool()
def ovito_run_script_tool(
    script_path: str,
    run_dir: str,
    script_command: str | None = None,
    timeout_sec: int = 3600,
) -> dict:
    """Run an explicit OVITO/ovitos Python script and retain stdout/stderr evidence."""
    return run_ovito_script(script_path, run_dir, script_command, timeout_sec)


@mcp.tool()
def atomistic_job_status_tool(job_id: str) -> dict:
    """Read status for an OVITO job launched by this MCP."""
    return get_job_status(job_id)


@mcp.tool()
def atomistic_job_log_tool(job_id: str, stream: str = "stdout", tail_chars: int = 12000) -> dict:
    """Read the stdout or stderr tail retained for a launched job."""
    return read_job_log(job_id, stream, tail_chars)


@mcp.tool()
def atomistic_list_jobs_tool(limit: int = 20) -> dict:
    """List recent LAMMPS and OVITO MCP jobs."""
    return list_jobs(limit)


@mcp.resource("atomistic://agent-instructions")
def agent_instructions() -> str:
    return INSTRUCTIONS


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
