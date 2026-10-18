from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from .config import Settings
from .service import AdamsService


settings = Settings.load()
service = AdamsService(settings)
mcp = FastMCP(
    "Adams MCP",
    instructions=(
        "Operate the local Hexagon Adams installation through safe structured tools. "
        "Probe capabilities first. Prefer project tools and batch execution. "
        "Never report a simulation as successful unless validation.status is VERIFIED."
    ),
    log_level="WARNING",
)


@mcp.tool(description="Probe the installed Adams release, View/Solver/Python/Command Server components, workspace, and live port.")
def adams_environment_probe() -> dict:
    return service.environment_probe()


@mcp.tool(description="Return the release-aware capability registry and verification state for each Adams operation.")
def adams_capabilities() -> dict:
    return service.capabilities()


@mcp.tool(description="Create an isolated, auditable Adams project and initial model CMD/manifest.")
def adams_project_create(project_id: str, model_name: str, length_unit: str = "mm", mass_unit: str = "kg", force_unit: str = "newton", time_unit: str = "sec", angle_unit: str = "deg") -> dict:
    return service.project_create(project_id, model_name, length_unit, mass_unit, force_unit, time_unit, angle_unit)


@mcp.tool(description="Inspect an isolated Adams project manifest and return its auditable CMD path.")
def adams_project_inspect(project_id: str) -> dict:
    return service.project_inspect(project_id)


@mcp.tool(description="Add a box-shaped rigid body with explicit mass and principal inertia to an isolated project.")
def adams_rigid_body_create(project_id: str, semantic_id: str, corner: list[float], size: list[float], mass: float, inertia: list[float]) -> dict:
    return service.rigid_body_create(project_id, semantic_id, corner, size, mass, inertia)


@mcp.tool(description="Add a revolute connection between two manifest parts; use 'ground' for the ground part.")
def adams_revolute_joint_create(project_id: str, semantic_id: str, i_part: str, j_part: str, location: list[float], orientation: list[float] | None = None) -> dict:
    return service.connection_create_revolute(project_id, semantic_id, i_part, j_part, location, orientation)


@mcp.tool(description="Set the project gravity vector in the selected model length/time units.")
def adams_gravity_set(project_id: str, vector: list[float]) -> dict:
    return service.gravity_set(project_id, vector)


@mcp.tool(description="Create a controlled rotational motion generator on a manifest joint.")
def adams_rotational_motion_create(project_id: str, semantic_id: str, joint_id: str, function: str) -> dict:
    return service.motion_create_rotational(project_id, semantic_id, joint_id, function)


@mcp.tool(description="Run a transient Adams/View batch simulation from an isolated project and create an evidence chain.")
def adams_simulation_run(project_id: str, analysis_name: str, end_time: float, steps: int, timeout_sec: float | None = None) -> dict:
    return service.simulation_run(project_id, analysis_name, end_time, steps, timeout_sec)


@mcp.tool(description="Execute an existing .cmd file only when it is inside the configured Adams MCP workspace.")
def adams_batch_run_cmd(cmd_path: str, timeout_sec: float | None = None) -> dict:
    return service.batch_run_cmd(cmd_path, timeout_sec)


@mcp.tool(description="Run the installed Adams 2024.1 native four-bar fixture in headless batch mode as an end-to-end bridge smoke test.")
def adams_smoke_test(timeout_sec: float = 180.0) -> dict:
    return service.smoke_test(timeout_sec)


@mcp.tool(description="Validate and summarize a numeric TXT/CSV/SPS result export inside the Adams MCP workspace.")
def adams_result_summary(result_path: str) -> dict:
    return service.result_summary(result_path)


@mcp.tool(description="Check whether the Adams/View Command Server is listening on localhost.")
def adams_live_status(port: int | None = None) -> dict:
    return service.live_status(port)


@mcp.tool(description="Evaluate an Adams expression through the localhost Command Server query protocol.")
def adams_live_query(expression: str, port: int | None = None) -> dict:
    return service.live_query(expression, port)


@mcp.tool(description="Send one allowlisted Adams/View command through the localhost Command Server. Arbitrary command prefixes are disabled by default.")
def adams_live_command(command: str, port: int | None = None) -> dict:
    return service.live_command(command, port)


@mcp.tool(description="Return validation, artifacts, hashes, and report paths for the newest Adams MCP run.")
def adams_evidence_latest() -> dict:
    return service.evidence_latest()


@mcp.resource("adams://environment", mime_type="application/json")
def environment_resource() -> str:
    return json.dumps(service.environment_probe(), ensure_ascii=False, indent=2)


@mcp.resource("adams://capabilities", mime_type="application/json")
def capabilities_resource() -> str:
    return json.dumps(service.capabilities(), ensure_ascii=False, indent=2)


@mcp.resource("adams://evidence/latest", mime_type="application/json")
def evidence_resource() -> str:
    return json.dumps(service.evidence_latest(), ensure_ascii=False, indent=2)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
