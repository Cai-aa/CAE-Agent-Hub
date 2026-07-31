from __future__ import annotations

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    def load_dotenv(*args: object, **kwargs: object) -> bool:
        return False

from fastmcp import FastMCP

from tools.atomistic_bridge import detect_lammps, get_job_status, list_jobs, read_job_log, run_lammps_input


load_dotenv()

INSTRUCTIONS = """Use LAMMPS through explicit local input files only.

Check the required executable before a run. A normal LAMMPS exit, requested
step count, thermo history, and physical validation are separate gates.
"""

mcp = FastMCP("LAMMPS MCP", instructions=INSTRUCTIONS)


@mcp.tool()
def lammps_detect_tool(lammps_exe: str | None = None) -> dict:
    """Detect a local LAMMPS executable; potential files remain user-owned inputs."""
    return detect_lammps(lammps_exe)


@mcp.tool()
def lammps_run_input_tool(
    input_path: str,
    run_dir: str,
    lammps_exe: str | None = None,
    extra_args: list[str] | None = None,
    timeout_sec: int = 7200,
) -> dict:
    """Run a selected LAMMPS input deck and retain stdout/stderr evidence."""
    return run_lammps_input(input_path, run_dir, lammps_exe, extra_args, timeout_sec)


@mcp.tool()
def atomistic_job_status_tool(job_id: str) -> dict:
    """Read status for a LAMMPS job launched by this MCP."""
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
