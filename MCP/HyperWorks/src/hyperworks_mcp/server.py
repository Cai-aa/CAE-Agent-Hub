from __future__ import annotations

import os
import re
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
from .analysis_profiles import AnalysisProfileService
from .analysis_templates import AnalysisTemplateService
from .jobs import JobService, SUCCESS_MARKER, stage_solver_input
from .hyperstudy import DOE_DESIGNS, OPTIMIZATION_DESIGNS, HyperStudyService
from .live_bridge import LiveBridgeClient
from .projects import ProjectService
from .radioss_results import audit_radioss_output_files
from .reporting import write_job_report
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
saving, controlled creation, model loading, view refresh, interactive selection, GUI launch,
solver launch, and cancellation are side effects. Loading a model requires explicit
replace_current=true. The live bridge never exposes arbitrary Python or Tcl execution.
Geometry creation, CAD import, surface/tetra meshing, native Solid Map, controlled
cylindrical O-grid generation, solver-card entities, loads, load steps, and quality repair
create automatic .hm checkpoints and roll back on failure. Rigid links, RBE3 spiders,
node welds, and property-backed spot welds are checkpointed and require explicit existing
entities. Generic connector realization and fasteners remain capability-gated until their
active profile and connector controls are validated.
CAD import is limited to project-scoped STEP, IGES, and Parasolid files. Solid Map may
replace existing solid elements, so inspect the returned checkpoint before continuing.
"""

settings = Settings.from_env()
settings.ensure()
projects = ProjectService(settings)
jobs = JobService(settings)
hyperstudy = HyperStudyService(projects)
analysis_profiles = AnalysisProfileService(projects)
analysis_templates = AnalysisTemplateService(analysis_profiles)
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
def prepare_optistruct_cantilever_analysis(
    project_id: str,
    name: str,
    dimensions: list[float],
    divisions: list[int],
    youngs_modulus: float,
    poissons_ratio: float,
    density: float,
    total_force: float,
    force_direction: list[float],
    gap_contacts: list[dict] | None = None,
    output_name: str = "cantilever.fem",
) -> dict:
    """Create a complete typed SOL 101 CHEXA deck with property, load, SPC, optional CGAP contact, and H3D controls."""
    return analysis_profiles.prepare_optistruct_cantilever(
        project_id,
        name,
        dimensions,
        divisions,
        youngs_modulus,
        poissons_ratio,
        density,
        total_force,
        force_direction,
        gap_contacts,
        output_name,
    )


@mcp.tool()
def prepare_radioss_block_impact_analysis(
    project_id: str,
    name: str,
    impactor_dimensions: list[float] = [5.0, 6.0, 6.0],
    impactor_divisions: list[int] = [2, 2, 2],
    target_dimensions: list[float] = [2.0, 10.0, 10.0],
    target_divisions: list[int] = [1, 2, 2],
    initial_gap: float = 1.0,
    initial_velocity: float = 5.0,
    end_time: float = 1.0,
    output_interval: float = 0.1,
    youngs_modulus: float = 210.0,
    poissons_ratio: float = 0.3,
    density: float = 7.85e-6,
    yield_stress: float = 0.25,
    hardening_modulus: float = 0.5,
    hardening_exponent: float = 0.5,
    friction: float = 0.1,
    output_name: str = "block_impact_0000.rad",
) -> dict:
    """Create a typed Radioss LAW2/SOLID/TYPE7 impact Starter+Engine pair in kg-mm-ms units."""
    return analysis_profiles.prepare_radioss_block_impact(
        project_id,
        name,
        impactor_dimensions,
        impactor_divisions,
        target_dimensions,
        target_divisions,
        initial_gap,
        initial_velocity,
        end_time,
        output_interval,
        youngs_modulus,
        poissons_ratio,
        density,
        yield_stress,
        hardening_modulus,
        hardening_exponent,
        friction,
        output_name,
    )


@mcp.tool()
def list_analysis_templates(solver: str | None = None) -> dict:
    """List reusable, versioned analysis templates and their validation state."""
    return analysis_templates.list(solver)


@mcp.tool()
def get_analysis_template(template_id: str) -> dict:
    """Return one reusable analysis template contract and its required parameters."""
    return analysis_templates.get(template_id)


@mcp.tool()
def prepare_analysis_template(
    project_id: str,
    template_id: str,
    parameters: dict,
) -> dict:
    """Prepare a solver deck by dispatching one validated reusable template."""
    return analysis_templates.prepare(project_id, template_id, parameters)


@mcp.tool()
def get_hyperstudy_capabilities() -> dict:
    """Audit installed HyperStudy batch/Python APIs and the typed study features exposed here."""
    paths = tool_paths(settings)
    root = discover_installation(settings)
    examples = (
        root / "hwdesktop" / "hst" / "etc" / "examples" / "api" if root else None
    )
    return {
        "installation_root": str(root) if root else None,
        "hyperstudy_batch": str(paths["hyperstudy_batch"])
        if paths["hyperstudy_batch"]
        else None,
        "hyperstudy_python": str(paths["hyperstudy_python"])
        if paths["hyperstudy_python"]
        else None,
        "official_api_examples": str(examples) if examples and examples.is_dir() else None,
        "typed_study_support": {
            "internal_math_model": True,
            "continuous_variables": True,
            "expression_responses": True,
            "doe_designs": sorted(DOE_DESIGNS),
            "optimization_designs": sorted(OPTIMIZATION_DESIGNS),
            "prepare_without_execution": True,
            "generate_hstudy_with_official_python_api": bool(
                paths["hyperstudy_python"]
            ),
        },
        "not_yet_exposed": [
            "arbitrary user Python",
            "solver-specific model resource wiring",
            "automatic DOE or optimization evaluation",
        ],
    }


@mcp.tool()
def prepare_hyperstudy_math_study(
    project_id: str,
    study_name: str,
    variables: list[dict],
    responses: list[dict],
    doe: dict | None = None,
    optimization: dict | None = None,
) -> dict:
    """Prepare a validated internal-math HyperStudy setup script from typed parameters."""
    return hyperstudy.prepare_math_study(
        project_id, study_name, variables, responses, doe, optimization
    )


@mcp.tool()
def generate_hyperstudy_study(project_id: str, script_name: str) -> dict:
    """Run only an MCP-generated script through Altair hstpy to create a .hstudy file."""
    executable = tool_paths(settings)["hyperstudy_python"]
    if not executable:
        raise RuntimeError("HyperStudy Python launcher was not detected. Set HYPERWORKS_HOME.")
    script = hyperstudy.generated_script(project_id, script_name)
    project_root = projects.root(project_id)
    run_dir = project_root / "runs" / (
        "hyperstudy_api_"
        + time.strftime("%Y%m%d_%H%M%S")
        + "_"
        + uuid.uuid4().hex[:6]
    )
    run_dir.mkdir(parents=True)
    command = ["cmd.exe", "/d", "/c", "call", str(executable), str(script)]
    return jobs.start(
        "HYPERSTUDY_API",
        project_id,
        command,
        run_dir,
        {
            "script_file": str(script),
            "installation_root": str(discover_installation(settings)),
        },
    )


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
    cpu_option = "-nt" if solver == "radioss" else "-ncpu"
    solver_args = [str(executable), str(run_input), cpu_option, str(ncpu)]
    if executable.suffix.lower() in {".bat", ".cmd"}:
        # Invoke the batch file through CALL.  Passing a pre-quoted command
        # string to ``cmd /s /c`` makes cmd.exe strip/escape the outer quotes
        # when the launcher lives below "Program Files".
        return ["cmd.exe", "/d", "/c", "call", *solver_args]
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


def _solver_result_artifacts(job_id: str) -> dict:
    status = jobs.status(job_id)
    inventory = jobs.artifacts(job_id)
    categories: dict[str, list[dict]] = {
        "result": [],
        "animation": [],
        "time_history": [],
        "solver_report": [],
        "model": [],
        "restart": [],
        "other": [],
    }
    result_extensions = {".h3d", ".op2", ".d3plot", ".h5", ".hdf5"}
    report_extensions = {".out", ".stat", ".log", ".err", ".html"}
    model_extensions = {".fem", ".bdf", ".dat", ".rad", ".key"}
    restart_extensions = {".rst", ".rmd", ".hmx"}
    for item in inventory["artifacts"]:
        path = Path(item["path"])
        suffix = path.suffix.lower()
        filename = path.name
        if suffix in result_extensions:
            category = "result"
        elif re.search(r"A\d{3}$", filename, flags=re.IGNORECASE):
            category = "animation"
        elif re.search(r"T\d{2}$", filename, flags=re.IGNORECASE):
            category = "time_history"
        elif suffix in report_extensions:
            category = "solver_report"
        elif suffix in model_extensions:
            category = "model"
        elif suffix in restart_extensions:
            category = "restart"
        else:
            category = "other"
        categories[category].append(item)
    return {
        "job_id": job_id,
        "state": status["state"],
        "return_code": status.get("return_code"),
        "process_alive": status["process_alive"],
        "categories": categories,
        "result_count": len(categories["result"]),
        "report_count": len(categories["solver_report"]),
    }


@mcp.tool()
def get_solver_result_artifacts(job_id: str) -> dict:
    """Classify actual solver deck, log, H3D, OP2, report, and restart artifacts for a job."""
    return _solver_result_artifacts(job_id)


@mcp.tool()
def audit_radioss_explicit_job(
    job_id: str,
    maximum_absolute_energy_error_percent: float = 15.0,
    maximum_added_mass_percent: float = 5.0,
) -> dict:
    """Audit actual Radioss Starter/Engine termination, energy, mass, time step, volume, and penetration signals."""
    status = jobs.status(job_id)
    if status.get("metadata", {}).get("solver") != "radioss":
        raise ValueError("job_id does not identify a Radioss solver job")
    artifacts = _solver_result_artifacts(job_id)
    reports = [Path(item["path"]) for item in artifacts["categories"]["solver_report"]]
    starter_outputs = [path for path in reports if path.name.lower().endswith("_0000.out")]
    engine_outputs = [path for path in reports if path.name.lower().endswith("_0001.out")]
    if not engine_outputs:
        raise RuntimeError("No Radioss Engine *_0001.out artifact is available")
    starter_output = max(starter_outputs, key=lambda path: path.stat().st_mtime) if starter_outputs else None
    engine_output = max(engine_outputs, key=lambda path: path.stat().st_mtime)
    audit = audit_radioss_output_files(
        starter_output,
        engine_output,
        maximum_absolute_energy_error_percent,
        maximum_added_mass_percent,
    )
    return {
        "job_id": job_id,
        "state": status["state"],
        "return_code": status.get("return_code"),
        **audit,
    }


@mcp.tool()
def postprocess_solver_result_in_hyperview(
    job_id: str,
    data_type: str = "Displacement",
    data_component: str = "Mag",
    entity_type: Literal["node", "element"] = "node",
    output_name: str | None = None,
    overwrite: bool = False,
    query_limit: int = 20,
    simulation: str | int = "last",
    average_mode: Literal["none", "simple", "maximum", "minimum", "advanced", "difference"] = "none",
) -> dict:
    """Open a completed solver result in live HyperView, query contour values, and capture PNG evidence."""
    status = jobs.status(job_id)
    if status["state"] != "COMPLETED" or status.get("return_code") != 0:
        raise RuntimeError("Only a successfully completed solver job can be postprocessed")
    artifacts = _solver_result_artifacts(job_id)
    h3d_files = [
        Path(item["path"])
        for item in artifacts["categories"]["result"]
        if Path(item["path"]).suffix.lower() == ".h3d"
    ]
    if not h3d_files:
        raise RuntimeError("The completed job did not produce an H3D result")
    model_files = [
        Path(item["path"])
        for item in artifacts["categories"]["model"]
        if Path(item["path"]).suffix.lower() in {".fem", ".bdf", ".dat", ".rad", ".key"}
    ]
    result_file = max(h3d_files, key=lambda path: path.stat().st_mtime)
    # H3D contains both model topology and results.  Loading it as both sources
    # avoids a second solver-deck reader pass and keeps entity/result IDs aligned.
    model_file = result_file
    project_id = status["project_id"]
    if output_name is None:
        safe_type = "".join(char if char.isalnum() else "_" for char in data_type).strip("_")
        output_name = f"{job_id}_{safe_type or 'contour'}.png"
    output_file = projects.root(project_id) / "output" / Path(output_name).name
    if output_file.suffix.lower() != ".png":
        output_file = output_file.with_suffix(".png")
    if output_file.exists() and not overwrite:
        raise ValueError("Output screenshot already exists; set overwrite=true after approval")
    result = live.call(
        "postprocess_hyperview_result",
        {
            "model_file": str(model_file),
            "result_file": str(result_file),
            "output_file": str(output_file),
            "data_type": data_type,
            "data_component": data_component,
            "entity_type": entity_type,
            "page_title": f"MCP {job_id} {data_type}",
            "query_limit": query_limit,
            "simulation": simulation,
            "average_mode": average_mode,
        },
        timeout=900,
    )
    return {"job_id": job_id, "project_id": project_id, **result}


@mcp.tool()
def extract_solver_time_history_in_hypergraph(
    job_id: str,
    data_type: str = "Displacement",
    data_component: str = "Mag",
    entity_type: Literal["node", "element"] = "node",
    entity_ids: list[int] | None = None,
    statistic: Literal["maximum", "minimum", "mean"] = "maximum",
    output_name: str = "time_history",
) -> dict:
    """Extract all result frames to CSV and render a HyperGraph XY history with PNG evidence."""
    status = jobs.status(job_id)
    if status["state"] != "COMPLETED" or status.get("return_code") != 0:
        raise RuntimeError("Only a successfully completed solver job can be postprocessed")
    artifacts = _solver_result_artifacts(job_id)
    result_items = artifacts["categories"]["result"]
    if not result_items:
        raise RuntimeError("No supported H3D or OP2 result artifact was found")
    result_file = Path(result_items[0]["path"])
    model_candidates = artifacts["categories"]["model"]
    model_file = result_file if result_file.suffix.lower() == ".h3d" else Path(model_candidates[0]["path"])
    project_id = str(status["project_id"])
    root = projects.root(project_id)
    clean_stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(output_name).stem)[:80] or "time_history"
    result = live.call(
        "extract_hypergraph_time_history",
        {
            "model_file": str(model_file),
            "result_file": str(result_file),
            "csv_file": str(root / "output" / f"{clean_stem}.csv"),
            "image_file": str(root / "output" / f"{clean_stem}.png"),
            "data_type": data_type,
            "data_component": data_component,
            "entity_type": entity_type,
            "entity_ids": entity_ids,
            "statistic": statistic,
            "curve_label": f"{data_type} {data_component} {statistic}",
        },
        timeout=1800,
    )
    return {"job_id": job_id, "project_id": project_id, **result}


@mcp.tool()
def generate_solver_job_report(
    job_id: str,
    output_name: str = "hyperworks_job_report",
    evidence_files: list[str] | None = None,
) -> dict:
    """Generate workspace-scoped HTML and JSON evidence for one completed solver job."""
    status = jobs.status(job_id)
    if status["state"] not in {"COMPLETED", "FAILED", "CANCELLED"}:
        raise RuntimeError("Report generation requires a terminal job state")
    project_id = str(status["project_id"])
    root = projects.root(project_id)
    output_root = (root / "output").resolve()
    evidence = []
    for raw in evidence_files or []:
        path = Path(raw).resolve()
        try:
            path.relative_to(output_root)
        except ValueError as exc:
            raise ValueError("evidence_files must be inside the project output directory") from exc
        evidence.append(path)
    artifacts = _solver_result_artifacts(job_id)
    audit = None
    if str(status.get("metadata", {}).get("solver", "")).casefold() == "radioss":
        try:
            audit = audit_radioss_explicit_job(job_id)
        except Exception as exc:
            audit = {"passed": False, "audit_error": str(exc)}
    clean_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(output_name).stem)[:80] or "hyperworks_job_report"
    result = write_job_report(
        output_root,
        clean_name,
        status,
        artifacts,
        audit,
        evidence,
    )
    return {"job_id": job_id, "project_id": project_id, **result}


@mcp.tool()
def get_live_bridge_status() -> dict:
    """Probe the authenticated in-application Python API bridge and report real connectivity."""
    return live.status(connect_timeout=1.0)


@mcp.tool()
def get_live_capabilities() -> dict:
    """Return Python modules, live API methods, entity classes, and configured save roots."""
    return live.call("get_capabilities", timeout=10)


@mcp.tool()
def get_live_connection_capabilities(model_name: str | None = None) -> dict:
    """Audit connection APIs and solver-profile constraints in the live HyperMesh client."""
    return live.call(
        "get_connection_capabilities", {"model_name": model_name}, timeout=30
    )


@mcp.tool()
def get_live_safety_airbag_capabilities(model_name: str | None = None) -> dict:
    """Audit dummy, seatbelt, airbag, folding, and stitching APIs without model changes."""
    return live.call(
        "get_safety_airbag_capabilities", {"model_name": model_name}, timeout=30
    )


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
def create_live_nodes(
    coordinates: list[list[float]], model_name: str | None = None
) -> dict:
    """Create up to 5000 nodes in the live model from finite [x, y, z] coordinates."""
    return live.call(
        "create_nodes",
        {"coordinates": coordinates, "model_name": model_name},
        timeout=120,
    )


@mcp.tool()
def create_live_elements(
    node_ids: list[list[int]],
    config: int,
    solver_type: int = 1,
    auto_order: bool = False,
    model_name: str | None = None,
) -> dict:
    """Create live elements from existing node IDs using an explicit HyperMesh config/type."""
    return live.call(
        "create_elements",
        {
            "node_ids": node_ids,
            "config": config,
            "solver_type": solver_type,
            "auto_order": auto_order,
            "model_name": model_name,
        },
        timeout=300,
    )


@mcp.tool()
def create_live_material(
    name: str,
    cardimage: str | None = None,
    values: dict | None = None,
    model_name: str | None = None,
) -> dict:
    """Create one live material with explicit solver card image and bounded attributes."""
    return live.call(
        "create_material",
        {
            "name": name,
            "cardimage": cardimage,
            "values": values,
            "model_name": model_name,
        },
        timeout=120,
    )


@mcp.tool()
def create_live_solver_card_entity(
    entity_type: Literal[
        "property", "loadcol", "loadstep", "set", "constraint",
        "contactbehavior", "contactgroup", "contactsurf", "group"
    ],
    name: str,
    cardimage: str | None = None,
    values: dict | None = None,
    references: dict | None = None,
    model_name: str | None = None,
) -> dict:
    """Create a checkpointed Property, collector, load step, set, or contact solver card."""
    return live.call(
        "create_solver_card_entity",
        {
            "entity_type": entity_type,
            "name": name,
            "cardimage": cardimage,
            "values": values,
            "references": references,
            "model_name": model_name,
        },
        timeout=300,
    )


@mcp.tool()
def create_live_nodal_load(
    node_ids: list[int],
    load_kind: Literal[
        "force", "moment", "constraint", "temperature", "flux", "velocity", "acceleration"
    ],
    components: list[float],
    solver_type: int = 1,
    loadcol_id: int | None = None,
    model_name: str | None = None,
) -> dict:
    """Create a checkpointed nodal force, moment, SPC, temperature, flux, velocity, or acceleration."""
    return live.call(
        "create_nodal_load",
        {
            "node_ids": node_ids,
            "load_kind": load_kind,
            "components": components,
            "solver_type": solver_type,
            "loadcol_id": loadcol_id,
            "model_name": model_name,
        },
        timeout=300,
    )


@mcp.tool()
def create_live_pressure_load(
    entity_type: Literal["surface", "element"],
    entity_ids: list[int],
    magnitude: float,
    direction: list[float] | None = None,
    face_node_ids: list[int] | None = None,
    break_angle: float = 30.0,
    loadcol_id: int | None = None,
    model_name: str | None = None,
) -> dict:
    """Create a checkpointed pressure on explicit surfaces or solid-element faces."""
    return live.call(
        "create_pressure_load",
        {
            "entity_type": entity_type,
            "entity_ids": entity_ids,
            "magnitude": magnitude,
            "direction": direction,
            "face_node_ids": face_node_ids,
            "break_angle": break_angle,
            "loadcol_id": loadcol_id,
            "model_name": model_name,
        },
        timeout=300,
    )


@mcp.tool()
def create_live_loadstep(
    name: str,
    analysis_type_attribute: str,
    analysis_type: int | str,
    load_attribute: str | None = None,
    loadcol_id: int | None = None,
    spc_attribute: str | None = None,
    spc_loadcol_id: int | None = None,
    cardimage: str | None = None,
    values: dict | None = None,
    model_name: str | None = None,
) -> dict:
    """Create a solver-specific Load Step with explicit load/SPC collector references."""
    return live.call(
        "create_loadstep",
        {
            "name": name,
            "analysis_type_attribute": analysis_type_attribute,
            "analysis_type": analysis_type,
            "load_attribute": load_attribute,
            "loadcol_id": loadcol_id,
            "spc_attribute": spc_attribute,
            "spc_loadcol_id": spc_loadcol_id,
            "cardimage": cardimage,
            "values": values,
            "model_name": model_name,
        },
        timeout=300,
    )


@mcp.tool()
def create_live_rigid_link(
    independent_node_id: int,
    dependent_node_ids: list[int],
    dofs: int = 123456,
    model_name: str | None = None,
    refresh: bool = True,
) -> dict:
    """Create a checkpointed rigid link from one independent node to dependent nodes."""
    return live.call(
        "create_rigid_link",
        {
            "independent_node_id": independent_node_id,
            "dependent_node_ids": dependent_node_ids,
            "dofs": dofs,
            "model_name": model_name,
            "refresh": refresh,
        },
        timeout=300,
    )


@mcp.tool()
def create_live_rbe3(
    independent_node_ids: list[int],
    dependent_node_id: int | None = None,
    independent_dofs: int = 123456,
    independent_weights: list[float] | None = None,
    dependent_dofs: list[bool] | None = None,
    dependent_weight: float = 1.0,
    model_name: str | None = None,
    refresh: bool = True,
) -> dict:
    """Create a checkpointed RBE3 spider; omit dependent_node_id to use the centroid."""
    return live.call(
        "create_rbe3",
        {
            "independent_node_ids": independent_node_ids,
            "dependent_node_id": dependent_node_id,
            "independent_dofs": independent_dofs,
            "independent_weights": independent_weights,
            "dependent_dofs": dependent_dofs,
            "dependent_weight": dependent_weight,
            "model_name": model_name,
            "refresh": refresh,
        },
        timeout=300,
    )


@mcp.tool()
def create_live_weld(
    independent_node_id: int,
    dependent_node_id: int,
    length: float = 0.0,
    create_systems: bool = False,
    move_node: bool = False,
    model_name: str | None = None,
    refresh: bool = True,
) -> dict:
    """Create a checkpointed solver-profile weld element between two live nodes."""
    return live.call(
        "create_weld",
        {
            "independent_node_id": independent_node_id,
            "dependent_node_id": dependent_node_id,
            "length": length,
            "create_systems": create_systems,
            "move_node": move_node,
            "model_name": model_name,
            "refresh": refresh,
        },
        timeout=300,
    )


@mcp.tool()
def create_live_spot_weld(
    independent_node_id: int,
    dependent_node_id: int,
    config: int,
    property_name: str,
    length: float = 0.0,
    create_system: bool = False,
    move_node: bool = False,
    remesh: bool = False,
    model_name: str | None = None,
    refresh: bool = True,
) -> dict:
    """Create a checkpointed solver-profile spot weld using an existing property."""
    return live.call(
        "create_spot_weld",
        {
            "independent_node_id": independent_node_id,
            "dependent_node_id": dependent_node_id,
            "config": config,
            "property_name": property_name,
            "length": length,
            "create_system": create_system,
            "move_node": move_node,
            "remesh": remesh,
            "model_name": model_name,
            "refresh": refresh,
        },
        timeout=600,
    )


@mcp.tool()
def create_live_connector(
    location_entity_type: Literal["node", "line"],
    location_ids: list[int],
    style: Literal["spot", "seam", "area", "bolt"],
    link_entity_type: Literal["component", "surface"],
    link_ids: list[int],
    num_links: int = 2,
    tolerance: float = 0.0,
    model_name: str | None = None,
    refresh: bool = True,
) -> dict:
    """Create unrealized HyperMesh connector intent with explicit locations and links."""
    return live.call(
        "create_connector",
        {
            "location_entity_type": location_entity_type,
            "location_ids": location_ids,
            "style": style,
            "link_entity_type": link_entity_type,
            "link_ids": link_ids,
            "num_links": num_links,
            "tolerance": tolerance,
            "model_name": model_name,
            "refresh": refresh,
        },
        timeout=600,
    )


@mcp.tool()
def create_live_solid_block(
    origin: list[float],
    dimensions: list[float],
    model_name: str | None = None,
) -> dict:
    """Create an axis-aligned HyperMesh solid block after an automatic model checkpoint."""
    return live.call(
        "create_solid_block",
        {"origin": origin, "dimensions": dimensions, "model_name": model_name},
        timeout=180,
    )


@mcp.tool()
def create_live_solid_cylinder(
    base_center: list[float],
    axis: list[float],
    radius: float,
    height: float,
    model_name: str | None = None,
) -> dict:
    """Create a full cylindrical HyperMesh solid after an automatic model checkpoint."""
    return live.call(
        "create_solid_cylinder",
        {
            "base_center": base_center,
            "axis": axis,
            "radius": radius,
            "height": height,
            "model_name": model_name,
        },
        timeout=180,
    )


@mcp.tool()
def import_live_cad(
    project_id: str,
    input_name: str,
    translator: Literal["step_ct", "iges_altair", "parasolid_parasolid"] | None = None,
    options: list[str] | None = None,
    model_name: str | None = None,
) -> dict:
    """Import a project STEP, IGES, or Parasolid file through the embedded HyperMesh API."""
    input_file = projects.input_file(project_id, input_name)
    if input_file.suffix.lower() not in {".step", ".stp", ".iges", ".igs", ".x_t", ".x_b"}:
        raise ValueError("input_name must refer to a STEP, IGES, or Parasolid project input")
    return live.call(
        "import_cad",
        {
            "input_file": str(input_file),
            "translator": translator,
            "options": options,
            "model_name": model_name,
        },
        timeout=900,
    )


@mcp.tool()
def automesh_live_surfaces(
    surface_ids: list[int],
    element_size: float,
    element_type: Literal["tria", "quad", "mixed", "right_tria", "quad_only"] = "mixed",
    mesh_type: Literal[
        "proximity_curvature",
        "curvature",
        "proximity_curvature_free_edge",
        "curvature_free_edge",
    ] = "proximity_curvature",
    min_size: float | None = None,
    max_size: float | None = None,
    chordal_deviation: float | None = None,
    max_angle: float = 30.0,
    growth_rate: float = 1.2,
    keep_existing_mesh: bool = True,
    model_name: str | None = None,
) -> dict:
    """Generate curvature/proximity-controlled shell mesh on explicit live surface IDs."""
    return live.call(
        "automesh_surfaces",
        {
            "surface_ids": surface_ids,
            "element_size": element_size,
            "element_type": element_type,
            "mesh_type": mesh_type,
            "min_size": min_size,
            "max_size": max_size,
            "chordal_deviation": chordal_deviation,
            "max_angle": max_angle,
            "growth_rate": growth_rate,
            "keep_existing_mesh": keep_existing_mesh,
            "model_name": model_name,
        },
        timeout=900,
    )


@mcp.tool()
def solid_map_live_solids(
    solid_ids: list[int],
    element_size: float,
    element_type: Literal["tria", "quad", "mixed"] = "mixed",
    organize_to_current_component: bool = False,
    extra_smoothing: bool = True,
    remesh_shell_mesh: bool = False,
    continue_on_negative_jacobian: bool = False,
    model_name: str | None = None,
) -> dict:
    """Run native HyperMesh Solid Map on explicit mappable solids with rollback protection."""
    return live.call(
        "solid_map_mesh",
        {
            "solid_ids": solid_ids,
            "element_size": element_size,
            "element_type": element_type,
            "organize_to_current_component": organize_to_current_component,
            "extra_smoothing": extra_smoothing,
            "remesh_shell_mesh": remesh_shell_mesh,
            "continue_on_negative_jacobian": continue_on_negative_jacobian,
            "model_name": model_name,
        },
        timeout=1800,
    )


@mcp.tool()
def tetra_mesh_live_solids(
    solid_ids: list[int],
    element_size: float,
    min_size: float | None = None,
    max_size: float | None = None,
    growth_rate: float = 1.3,
    element_order: Literal[1, 2] = 1,
    use_existing_surface_mesh: bool = True,
    model_name: str | None = None,
    refresh: bool = True,
) -> dict:
    """Generate a native structural tetra mesh on explicit live solid IDs with rollback protection."""
    return live.call(
        "tetra_mesh_solids",
        {
            "solid_ids": solid_ids,
            "element_size": element_size,
            "min_size": min_size,
            "max_size": max_size,
            "growth_rate": growth_rate,
            "element_order": element_order,
            "use_existing_surface_mesh": use_existing_surface_mesh,
            "model_name": model_name,
            "refresh": refresh,
        },
        timeout=1800,
    )


@mcp.tool()
def repair_live_mesh_quality(
    element_ids: list[int],
    anchor_node_ids: list[int] | None = None,
    iterations: int = 5,
    method: Literal[
        "Angle", "AutoDecideWithoutQI", "AutoDecideWithQI",
        "AutoDecideWithQI_Params_locked", "QI", "Shape", "Size"
    ] = "AutoDecideWithQI_Params_locked",
    anchor_free_edges: bool = True,
    model_name: str | None = None,
    refresh: bool = True,
) -> dict:
    """Smooth selected mesh with checkpoint/rollback and before/after quality evidence."""
    return live.call(
        "repair_mesh_quality",
        {
            "element_ids": element_ids,
            "anchor_node_ids": anchor_node_ids,
            "iterations": iterations,
            "method": method,
            "anchor_free_edges": anchor_free_edges,
            "model_name": model_name,
            "refresh": refresh,
        },
        timeout=1800,
    )


@mcp.tool()
def create_live_cylindrical_ogrid(
    base_center: list[float],
    axis: list[float],
    length: float,
    radius: float,
    axial_divisions: int = 4,
    circumferential_divisions: int = 12,
    radial_layers: int = 2,
    core_ratio: float = 0.4,
    model_name: str | None = None,
    refresh: bool = True,
) -> dict:
    """Create a bounded cylindrical radial O-grid: Hex8 rings around a Penta6 core."""
    return live.call(
        "create_cylindrical_ogrid",
        {
            "base_center": base_center,
            "axis": axis,
            "length": length,
            "radius": radius,
            "axial_divisions": axial_divisions,
            "circumferential_divisions": circumferential_divisions,
            "radial_layers": radial_layers,
            "core_ratio": core_ratio,
            "model_name": model_name,
            "refresh": refresh,
        },
        timeout=900,
    )


@mcp.tool()
def get_live_mesh_quality(
    element_ids: list[int] | None = None,
    model_name: str | None = None,
) -> dict:
    """Report available live volume, Jacobian, aspect, and skew statistics without fabrication."""
    return live.call(
        "get_mesh_quality",
        {"element_ids": element_ids, "model_name": model_name},
        timeout=300,
    )


@mcp.tool()
def create_live_checkpoint(
    label: str = "manual", model_name: str | None = None
) -> dict:
    """Save a bridge-managed .hm checkpoint under the configured workspace."""
    return live.call(
        "create_checkpoint", {"label": label, "model_name": model_name}, timeout=300
    )


@mcp.tool()
def rollback_live_checkpoint(
    checkpoint_file: str,
    confirm: bool = False,
    model_name: str | None = None,
) -> dict:
    """Replace live model state with a bridge-created checkpoint; confirm=true is mandatory."""
    return live.call(
        "rollback_checkpoint",
        {
            "checkpoint_file": checkpoint_file,
            "confirm": confirm,
            "model_name": model_name,
        },
        timeout=600,
    )


@mcp.tool()
def load_live_model(
    project_id: str,
    input_name: str,
    replace_current: bool = False,
    load_cad_geometry_as_graphics: bool = False,
    model_name: str | None = None,
) -> dict:
    """Load a project .hm file into the live session; replace_current=true is mandatory."""
    input_file = projects.input_file(project_id, input_name)
    if input_file.suffix.lower() != ".hm":
        raise ValueError("input_name must refer to a .hm file in the project input directory")
    return live.call(
        "load_model",
        {
            "input_file": str(input_file),
            "replace_current": replace_current,
            "load_cad_geometry_as_graphics": load_cad_geometry_as_graphics,
            "model_name": model_name,
        },
        timeout=300,
    )


@mcp.tool()
def refresh_live_view(fit: bool = True) -> dict:
    """Redraw the live HyperMesh graphics window and optionally fit the visible model."""
    return live.call("refresh_view", {"fit": fit}, timeout=30)


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
