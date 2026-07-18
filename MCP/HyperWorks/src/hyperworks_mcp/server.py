from __future__ import annotations

import os
import subprocess
import time
import uuid
from pathlib import Path
from typing import Literal

from fastmcp import FastMCP

from .environment import (
    discover_installation,
    environment_report,
    normalize_installation_root,
    tool_paths,
)
from .jobs import JobService, SUCCESS_MARKER, stage_solver_input
from .live_bridge import LiveBridgeClient
from .projects import ProjectService
from .settings import Settings


INSTRUCTIONS = """Control Altair HyperWorks through typed, workspace-scoped tools.
Use get_environment before launching anything. Prefer HyperMesh batch Tcl for repeatable
pre-processing and use GUI launch only when interactive work is required. Tcl scripts are
screened against OS/process escape commands and run from isolated project/job folders.
Solver and GUI launches are side effects. Ask for approval before launching a GUI, starting
a solver, or cancelling a job. Never infer mesh quality, convergence, solver availability,
or successful completion; read the actual job status and logs. This server does not expose
arbitrary shell, PowerShell, or Python execution. The live in-application Python bridge is
available through an authenticated localhost Extension. Live entity modification, model
saving, interactive selection, GUI launch, solver launch, and cancellation are side effects.
"""

settings = Settings.from_env()
settings.ensure()
projects = ProjectService(settings)
jobs = JobService(settings)
live = LiveBridgeClient()
mcp = FastMCP("hyperworks", instructions=INSTRUCTIONS)


@mcp.tool()
def get_environment() -> dict:
    """Detect HyperMesh GUI/batch, HyperStudy, OptiStruct, Radioss, and capabilities."""
    report = environment_report(settings)
    bridge = live.status(connect_timeout=0.25)
    report["capabilities"]["live_python_bridge"] = bridge["connected"]
    report["live_bridge"] = bridge
    return report


@mcp.tool()
def configure_installation(path: str) -> dict:
    """Select an existing Altair installation for this MCP process; no system settings change."""
    root = normalize_installation_root(Path(path))
    if not root.is_dir() or not (root / "hwdesktop").is_dir():
        raise ValueError("path does not resolve to an Altair installation root")
    os.environ["HYPERWORKS_HOME"] = str(root)
    report = environment_report(settings)
    return {
        "configured": True,
        "scope": "current MCP process",
        "persistence": "Set HYPERWORKS_HOME in Codex MCP configuration.",
        **report,
    }


@mcp.tool()
def create_project(name: str) -> dict:
    """Create an isolated HyperWorks project with input, scripts, output, and runs folders."""
    return projects.create(name)


@mcp.tool()
def get_project_summary(project_id: str) -> dict:
    """Return project metadata and the current input/script inventory."""
    summary = projects.manifest(project_id)
    summary["jobs"] = jobs.list(project_id=project_id, limit=20)["jobs"]
    return summary


@mcp.tool()
def import_project_file(
    project_id: str, source_file: str, destination_name: str | None = None
) -> dict:
    """Copy an explicitly selected CAD, model, deck, or result file into project input."""
    return projects.import_file(project_id, source_file, destination_name)


@mcp.tool()
def write_tcl_script(project_id: str, name: str, content: str) -> dict:
    """Write a screened HyperMesh Tcl script; OS/process escape and *quit are blocked."""
    return projects.write_tcl(project_id, name, content)


@mcp.tool()
def run_hmbatch(project_id: str, script_name: str) -> dict:
    """Run an approved project Tcl script asynchronously with HyperMesh Batch."""
    paths = tool_paths(settings)
    hmbatch = paths["hmbatch"]
    if not hmbatch:
        raise RuntimeError("HyperMesh Batch was not detected. Set HYPERWORKS_HOME.")
    script = projects.script(project_id, script_name)
    project_root = projects.root(project_id)
    run_dir = project_root / "runs" / (
        "hmbatch_" + time.strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
    )
    run_dir.mkdir(parents=True)
    wrapper = run_dir / "__mcp_wrapper.tcl"
    script_for_tcl = script.as_posix()
    wrapper.write_text(
        "if {[catch {source {" + script_for_tcl + "}} err opts]} {\n"
        "    puts stderr $err\n"
        "    puts stderr [dict get $opts -errorinfo]\n"
        "    exit 1\n"
        "}\n"
        f'puts "{SUCCESS_MARKER}"\n',
        encoding="utf-8",
    )
    return jobs.start(
        "HMBATCH",
        project_id,
        [str(hmbatch), "-tcl", str(wrapper)],
        run_dir,
        {"script_file": str(script), "installation_root": str(discover_installation(settings))},
    )


@mcp.tool()
def launch_hypermesh(
    project_id: str | None = None,
    start_with: Literal["HyperMesh", "HyperView"] = "HyperMesh",
    language: Literal["en", "zh"] = "en",
) -> dict:
    """Launch the HyperMesh/HyperView GUI. This is a side effect and may consume a license."""
    launcher = tool_paths(settings)["runhwx"]
    if not launcher:
        raise RuntimeError("HyperWorks GUI launcher was not detected")
    working_directory = (
        projects.root(project_id) / "output" if project_id else settings.workspace
    )
    command = [
        str(launcher),
        "-client",
        "HyperWorksDesktop",
        "-plugin",
        "HyperworksLauncher",
        "-profile",
        "HyperworksLauncher",
        "-l",
        language,
        "-startwith",
        start_with,
    ]
    process = subprocess.Popen(
        command,
        cwd=working_directory,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        shell=False,
    )
    return {
        "launched": True,
        "pid": process.pid,
        "application": start_with,
        "working_directory": str(working_directory),
    }


def _solver_command(
    executable: Path,
    run_input: Path,
    ncpu: int,
    solver: Literal["optistruct", "radioss"],
) -> list[str]:
    solver_args = [str(executable), str(run_input), "-ncpu", str(ncpu)]
    if solver == "optistruct":
        solver_args.append("-nobg")
    if executable.suffix.lower() in {".bat", ".cmd"}:
        # cmd.exe expects the batch launcher and all of its arguments as one
        # command string. Passing them as separate argv entries breaks when
        # either path contains spaces (for example, "Program Files").
        return ["cmd.exe", "/d", "/s", "/c", subprocess.list2cmdline(solver_args)]
    return solver_args


@mcp.tool()
def submit_solver_job(
    project_id: str,
    solver: Literal["optistruct", "radioss"],
    input_file: str,
    ncpu: int | None = None,
) -> dict:
    """Stage project input and start an approved OptiStruct or Radioss job asynchronously."""
    paths = tool_paths(settings)
    executable = paths[solver]
    if not executable:
        raise RuntimeError(
            f"{solver} launcher was not detected. Install HyperWorks Solvers or configure its executable."
        )
    ncpu = settings.default_ncpu if ncpu is None else int(ncpu)
    if not 1 <= ncpu <= settings.max_ncpu:
        raise ValueError(f"ncpu must be between 1 and {settings.max_ncpu}")
    project_root = projects.root(project_id)
    source_deck = projects.input_file(project_id, input_file)
    run_dir = project_root / "runs" / (
        solver + "_" + time.strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
    )
    run_dir.mkdir(parents=True)
    run_input = stage_solver_input(project_root, source_deck, run_dir / "input")
    command = _solver_command(executable, run_input, ncpu, solver)
    return jobs.start(
        "SOLVER",
        project_id,
        command,
        run_dir,
        {"solver": solver, "input_file": str(run_input), "ncpu": ncpu},
    )


@mcp.tool()
def get_job_status(job_id: str) -> dict:
    """Read actual process state and completion markers without estimating progress."""
    return jobs.status(job_id)


@mcp.tool()
def tail_job_log(job_id: str, lines: int = 100) -> dict:
    """Read a bounded tail of captured HyperWorks or solver output."""
    return jobs.log(job_id, lines)


@mcp.tool()
def cancel_job(job_id: str) -> dict:
    """Terminate an active job process tree and preserve existing outputs."""
    return jobs.cancel(job_id)


@mcp.tool()
def list_jobs(project_id: str | None = None, limit: int = 50) -> dict:
    """List persisted HyperWorks jobs, optionally for one project."""
    return jobs.list(project_id, limit)


@mcp.tool()
def list_job_artifacts(job_id: str) -> dict:
    """Inventory files produced in a job directory; does not interpret result values."""
    return jobs.artifacts(job_id)


@mcp.tool()
def get_live_bridge_status() -> dict:
    """Probe the authenticated in-application Python API bridge and report real connectivity."""
    return live.status(connect_timeout=1.0)


@mcp.tool()
def get_live_capabilities() -> dict:
    """Return Python modules, live API methods, entity classes, and configured save roots."""
    return live.call("get_capabilities", timeout=10)


@mcp.tool()
def get_live_session_info() -> dict:
    """Read current and available HyperMesh models from the running desktop session."""
    return live.call("get_session_info", timeout=10)


@mcp.tool()
def get_live_model_summary(
    model_name: str | None = None, entity_types: list[str] | None = None
) -> dict:
    """Count allowlisted entity types in the current or named live HyperMesh model."""
    return live.call(
        "get_model_summary",
        {"model_name": model_name, "entity_types": entity_types},
        timeout=30,
    )


@mcp.tool()
def list_live_entities(
    entity_type: str,
    model_name: str | None = None,
    offset: int = 0,
    limit: int = 100,
    attributes: list[str] | None = None,
) -> dict:
    """List structured live entity data with pagination and explicit attribute selection."""
    return live.call(
        "list_entities",
        {
            "entity_type": entity_type,
            "model_name": model_name,
            "offset": offset,
            "limit": limit,
            "attributes": attributes,
        },
        timeout=60,
    )


@mcp.tool()
def get_live_entity(
    entity_type: str,
    entity_id: int,
    model_name: str | None = None,
    attributes: list[str] | None = None,
) -> dict:
    """Read one live HyperMesh entity by type and internal ID."""
    return live.call(
        "get_entity",
        {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "model_name": model_name,
            "attributes": attributes,
        },
        timeout=30,
    )


@mcp.tool()
def get_live_user_mark(entity_type: str, model_name: str | None = None) -> dict:
    """Read the current HyperMesh user mark for an allowlisted entity type."""
    return live.call(
        "get_user_mark",
        {"entity_type": entity_type, "model_name": model_name},
        timeout=30,
    )


@mcp.tool()
def select_live_entities_interactively(
    entity_type: str,
    message: str = "Select entities for Codex",
    highlight: bool = True,
) -> dict:
    """Open HyperMesh's interactive selector and return selected IDs; requires live user interaction."""
    return live.call(
        "interactive_select",
        {"entity_type": entity_type, "message": message, "highlight": highlight},
        timeout=900,
    )


@mcp.tool()
def set_live_entity_attributes(
    entity_type: str,
    entity_id: int,
    values: dict,
    model_name: str | None = None,
) -> dict:
    """Modify allowlisted attributes on one live entity; this is a model-changing side effect."""
    return live.call(
        "set_entity_attributes",
        {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "values": values,
            "model_name": model_name,
        },
        timeout=60,
    )


@mcp.tool()
def get_live_model_metrics(model_name: str | None = None) -> dict:
    """Query solver, total mass, center of gravity, current view, and existing entity types."""
    return live.call("get_model_metrics", {"model_name": model_name}, timeout=60)


@mcp.tool()
def save_live_model(
    project_id: str,
    output_name: str,
    model_name: str | None = None,
    overwrite: bool = False,
    do_not_write_facets: int = 0,
) -> dict:
    """Save the live model into the MCP project output directory; overwrite is explicit."""
    output = projects.root(project_id) / "output" / Path(output_name).name
    if output.suffix.lower() != ".hm":
        output = output.with_suffix(".hm")
    return live.call(
        "save_model",
        {
            "output_file": str(output),
            "model_name": model_name,
            "overwrite": overwrite,
            "do_not_write_facets": do_not_write_facets,
        },
        timeout=300,
    )


@mcp.resource("hyperworks://environment")
def environment_resource() -> dict:
    return get_environment()


@mcp.resource("hyperworks://project/{project_id}")
def project_resource(project_id: str) -> dict:
    return get_project_summary(project_id)


@mcp.resource("hyperworks://job/{job_id}")
def job_resource(job_id: str) -> dict:
    return jobs.status(job_id)


@mcp.prompt()
def preprocess_and_solve(project_id: str, solver: str = "optistruct") -> str:
    return (
        f"For HyperWorks project {project_id}, inspect the environment and project inventory. "
        "Prepare a screened Tcl preprocessing script, explain its model assumptions, and run "
        f"HyperMesh Batch. Inspect its real log and artifacts. Before starting {solver}, show "
        "the selected deck, CPU count, and solver availability and ask for approval. Monitor "
        "the returned job ID without inventing progress or convergence."
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
