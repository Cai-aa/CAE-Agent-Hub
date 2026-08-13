from __future__ import annotations

import argparse
import asyncio
import json
import tomllib
from datetime import datetime
from pathlib import Path
from typing import Any

from mcp import ClientSession

from mcp_heat_smoke import SERVER_NAMES, connect, read_registered_servers, response_payload


class ContractFailure(RuntimeError):
    pass


async def contract_call(
    session: ClientSession,
    server: str,
    tool: str,
    arguments: dict[str, Any],
    trace: list[dict[str, Any]],
    invoked: dict[str, set[str]],
    expected_statuses: set[str] | None = None,
) -> dict[str, Any]:
    expected = expected_statuses or {"SUCCEEDED"}
    result = await session.call_tool(tool, arguments)
    payload = response_payload(result)
    status = str(payload.get("status", "UNKNOWN"))
    passed = status in expected
    invoked[server].add(tool)
    trace.append(
        {
            "server": server,
            "tool": tool,
            "arguments": arguments,
            "expected_statuses": sorted(expected),
            "actual_status": status,
            "contract_pass": passed,
            "response": payload,
        }
    )
    marker = "PASS" if passed else "FAIL"
    print(f"[{marker}] {tool}: {status} - {payload.get('summary', '')}")
    if not passed:
        raise ContractFailure(f"{tool}: expected {sorted(expected)}, received {status}")
    return payload


async def inventory(session: ClientSession) -> dict[str, Any]:
    tools = await session.list_tools()
    resources = await session.list_resources()
    templates = await session.list_resource_templates()
    return {
        "tools": sorted(item.name for item in tools.tools),
        "resources": sorted(str(item.uri) for item in resources.resources),
        "resource_templates": sorted(str(item.uriTemplate) for item in templates.resourceTemplates),
    }


async def run(project: str, config_path: Path) -> dict[str, Any]:
    servers = read_registered_servers(config_path)
    trace: list[dict[str, Any]] = []
    invoked = {name: set() for name in SERVER_NAMES}
    inventories: dict[str, dict[str, Any]] = {}

    async with connect(servers["freecad"]) as session:
        inventories["freecad"] = await inventory(session)
        async def call(tool: str, arguments: dict[str, Any], expected: set[str] | None = None) -> dict[str, Any]:
            return await contract_call(session, "freecad", tool, arguments, trace, invoked, expected)
        await call("freecad_environment_probe", {})
        await call("freecad_session_status", {})
        await call(
            "freecad_document_create",
            {"project": project, "label": "OpenCAE Full MCP Validation", "overwrite": True},
        )
        await call("freecad_document_open", {"project": project})
        await call(
            "freecad_feature_create",
            {
                "project": project,
                "feature_type": "box",
                "name": "Cube",
                "parameters": {"length": "10 mm", "width": "10 mm", "height": "10 mm"},
            },
        )
        await call(
            "freecad_feature_create",
            {
                "project": project,
                "feature_type": "cylinder",
                "name": "ToolCylinder",
                "parameters": {"radius": "1 mm", "height": "5 mm"},
            },
        )
        await call(
            "freecad_feature_create",
            {
                "project": project,
                "feature_type": "sphere",
                "name": "DisposableSphere",
                "parameters": {"radius": "1 mm"},
                "placement": {"position_mm": [30, 30, 30]},
            },
        )
        await call("freecad_object_inspect", {"project": project, "name": "Cube"})
        await call(
            "freecad_feature_update",
            {"project": project, "name": "Cube", "patch": {"label": "ValidatedCube", "length": "10 mm"}},
        )
        await call(
            "freecad_transform",
            {
                "project": project,
                "name": "ToolCylinder",
                "placement": {"position_mm": [20, 20, 0], "rotation_axis": [0, 0, 1], "rotation_deg": 0},
            },
        )
        await call(
            "freecad_boolean",
            {
                "project": project,
                "operation": "fuse",
                "base": "Cube",
                "tools": ["ToolCylinder"],
                "result_name": "BooleanTrial",
            },
        )
        await call(
            "freecad_feature_delete",
            {"project": project, "name": "DisposableSphere", "force": False},
        )
        await call("freecad_geometry_validate", {"project": project, "objects": ["Cube"]})
        await call("freecad_document_inspect", {"project": project})
        await call(
            "freecad_document_save",
            {
                "project": project,
                "output": "geometry/model_validation_copy.FCStd",
                "overwrite": True,
            },
        )
        await call(
            "freecad_export_step",
            {
                "project": project,
                "objects": ["Cube"],
                "semantic_ids": {"Cube": "cube"},
                "also_export_parts": True,
            },
        )
        await call("freecad_capture_view", {"project": project}, {"BLOCKED"})

    solver_response: dict[str, Any]
    async with connect(servers["elmer"]) as session:
        inventories["elmer"] = await inventory(session)
        async def call(tool: str, arguments: dict[str, Any], expected: set[str] | None = None) -> dict[str, Any]:
            return await contract_call(session, "elmer", tool, arguments, trace, invoked, expected)
        await call("elmer_environment_probe", {})
        await call(
            "elmer_case_create",
            {"project": project, "analysis_type": "heat_steady_v1", "overwrite": True},
        )
        await call("elmer_case_inspect", {"project": project})
        await call("elmer_geometry_import", {"project": project})
        await call(
            "elmer_mesh_generate",
            {"project": project, "global_size_mm": 2.0, "order": 1, "output_format": "msh2"},
        )
        await call("elmer_mesh_convert", {"project": project})
        await call("elmer_mesh_inspect", {"project": project})
        await call(
            "elmer_material_set",
            {
                "project": project,
                "body": "solid",
                "material": {"name": "GenericSolid", "heat_conductivity": "1 W/(m K)"},
            },
        )
        await call("elmer_equation_set", {"project": project, "profile": "heat_steady_v1"})
        await call(
            "elmer_excitation_set",
            {
                "project": project,
                "body": "solid",
                "excitation": {"current_density_re_a_per_m2": 1.0, "current_density_im_a_per_m2": 0.0},
            },
            {"BLOCKED"},
        )
        await call(
            "elmer_boundary_set",
            {
                "project": project,
                "selector": {"axis": "x", "side": "min", "object": "cube"},
                "condition": {"temperature": "300 K"},
            },
        )
        await call(
            "elmer_boundary_set",
            {
                "project": project,
                "selector": {"axis": "x", "side": "max", "object": "cube"},
                "condition": {"temperature": "400 K"},
            },
        )
        await call("elmer_sif_generate", {"project": project})
        await call("elmer_sif_validate", {"project": project})
        solver_response = await call(
            "elmer_solver_run",
            {"project": project, "mode": "serial", "processes": 1, "timeout": 180},
        )
        job_id = solver_response["data"]["job_id"]
        await call("elmer_job_status", {"project": project, "job_id": job_id})
        await call("elmer_log_inspect", {"project": project, "last_n_lines": 40})
        await call("elmer_result_inspect", {"project": project})

    paraview_started = False
    async with connect(servers["paraview"]) as session:
        inventories["paraview"] = await inventory(session)
        async def call(tool: str, arguments: dict[str, Any], expected: set[str] | None = None) -> dict[str, Any]:
            return await contract_call(session, "paraview", tool, arguments, trace, invoked, expected)
        try:
            await call("paraview_environment_probe", {})
            await call("paraview_session_start", {"project": project, "mode": "headless"})
            paraview_started = True
            await call("paraview_session_status", {"project": project})
            opened = await call(
                "paraview_dataset_open",
                {"project": project, "path": "results/case.vtu", "alias": "result"},
            )
            arrays = opened["data"]["inspection"]["point_arrays"]
            temperature = next(item["name"] for item in arrays if item["name"].lower() == "temperature")
            await call("paraview_dataset_inspect", {"project": project, "proxy": "result"})
            await call("paraview_pipeline_inspect", {"project": project})
            await call(
                "paraview_filter_create",
                {
                    "project": project,
                    "input_proxy": "result",
                    "filter_type": "slice",
                    "parameters": {"origin": [5, 5, 5], "normal": [0, 0, 1]},
                    "alias": "slice_mid",
                },
            )
            await call(
                "paraview_color_by",
                {"project": project, "proxy": "slice_mid", "array": temperature, "association": "POINTS"},
            )
            await call(
                "paraview_scalar_range",
                {"project": project, "proxy": "result", "array": temperature, "association": "POINTS"},
            )
            await call(
                "paraview_camera_set",
                {
                    "project": project,
                    "camera": {"position": [5, 5, 35], "focal_point": [5, 5, 5], "view_up": [0, 1, 0]},
                },
            )
            await call("paraview_camera_fit", {"project": project})
            await call("paraview_render", {"project": project})
            await call(
                "paraview_export_image",
                {
                    "project": project,
                    "output": "post/full_validation_temperature.png",
                    "resolution": [1920, 1080],
                },
            )
            await call(
                "paraview_export_csv",
                {"project": project, "proxy": "result", "output": "post/full_validation_temperature.csv"},
            )
            await call("paraview_export_animation", {"project": project}, {"BLOCKED"})
            await call(
                "paraview_state_save",
                {"project": project, "output": "post/full_validation_pipeline.pvsm"},
            )
        finally:
            if paraview_started:
                await call("paraview_session_stop", {"project": project})

    coverage: dict[str, Any] = {}
    for server in SERVER_NAMES:
        exposed = set(inventories[server]["tools"])
        missing = sorted(exposed - invoked[server])
        unexpected = sorted(invoked[server] - exposed)
        coverage[server] = {
            "exposed": len(exposed),
            "invoked_unique": len(invoked[server]),
            "missing": missing,
            "unexpected": unexpected,
            "pass": not missing and not unexpected,
        }
        if missing or unexpected:
            raise ContractFailure(f"{server} tool coverage mismatch: missing={missing}, unexpected={unexpected}")

    physics = solver_response["data"]["inspection"]["physics_acceptance"]
    contract_passes = sum(1 for item in trace if item["contract_pass"])
    expected_blocked = [item["tool"] for item in trace if item["actual_status"] == "BLOCKED"]
    with Path(servers["freecad"]["env"]["OPEN_CAE_CONFIG"]).open("rb") as stream:
        open_cae_config = tomllib.load(stream)
    project_root = Path(open_cae_config["workspace"]["root"]) / project
    summary = {
        "status": "PASS" if contract_passes == len(trace) and physics["pass"] else "FAILED",
        "project": project,
        "codex_config": str(config_path),
        "inventories": inventories,
        "coverage": coverage,
        "total_exposed_tools": sum(item["exposed"] for item in coverage.values()),
        "total_unique_tools_invoked": sum(item["invoked_unique"] for item in coverage.values()),
        "total_calls": len(trace),
        "contract_passes": contract_passes,
        "expected_blocked": expected_blocked,
        "physics_acceptance": physics,
        "trace": trace,
    }
    evidence_dir = project_root / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    output = evidence_dir / "mcp_full_validation.json"
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    report = evidence_dir / "mcp_full_validation.md"
    report.write_text(
        "\n".join(
            [
                "# OpenCAE MCP Full Tool Contract Validation",
                "",
                f"- Status: **{summary['status']}**",
                f"- Project: `{project}`",
                f"- Exposed tools: {summary['total_exposed_tools']}",
                f"- Unique tools invoked: {summary['total_unique_tools_invoked']}",
                f"- Contract-passing calls: {contract_passes}/{len(trace)}",
                f"- Expected blocked capabilities: {', '.join(expected_blocked)}",
                f"- Physics acceptance: {physics['pass']}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return {key: value for key, value in summary.items() if key != "trace"} | {
        "evidence": str(output),
        "report": str(report),
    }


async def main() -> int:
    parser = argparse.ArgumentParser(description="Validate every exposed OpenCAE MCP tool contract")
    parser.add_argument("--project", default=None)
    parser.add_argument("--codex-config", default=str(Path.home() / ".codex" / "config.toml"))
    args = parser.parse_args()
    project = args.project or datetime.now().strftime("mcp_full_validation_%Y%m%d_%H%M%S")
    summary = await run(project, Path(args.codex_config))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
