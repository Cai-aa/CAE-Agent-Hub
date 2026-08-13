from __future__ import annotations

import argparse
import asyncio
import json
import os
import tomllib
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


SERVER_NAMES = {
    "freecad": "open-cae-freecad",
    "elmer": "open-cae-elmer",
    "paraview": "open-cae-paraview",
}


def response_payload(result: Any) -> dict[str, Any]:
    if getattr(result, "isError", False):
        text = "\n".join(getattr(item, "text", "") for item in result.content)
        raise RuntimeError(text or "MCP tool returned isError=true")
    structured = getattr(result, "structuredContent", None)
    if structured:
        if set(structured) == {"result"} and isinstance(structured["result"], dict):
            return structured["result"]
        return structured
    for item in result.content:
        text = getattr(item, "text", "")
        if text:
            parsed = json.loads(text)
            return parsed.get("result", parsed) if isinstance(parsed, dict) else {"result": parsed}
    raise RuntimeError("MCP tool returned no structured or text content")


class MCPFailure(RuntimeError):
    pass


async def call(
    session: ClientSession,
    tool: str,
    arguments: dict[str, Any],
    trace: list[dict[str, Any]],
) -> dict[str, Any]:
    result = await session.call_tool(tool, arguments)
    payload = response_payload(result)
    trace.append({"tool": tool, "arguments": arguments, "response": payload})
    status = payload.get("status", "UNKNOWN")
    print(f"[{status}] {tool}: {payload.get('summary', '')}")
    if not payload.get("ok", False):
        raise MCPFailure(f"{tool}: {payload.get('summary', payload)}")
    return payload


def read_registered_servers(config_path: Path) -> dict[str, dict[str, Any]]:
    with config_path.open("rb") as stream:
        config = tomllib.load(stream)
    servers = config.get("mcp_servers", {})
    selected = {}
    for key, registered_name in SERVER_NAMES.items():
        if registered_name not in servers:
            raise RuntimeError(f"Codex MCP entry is missing: {registered_name}")
        selected[key] = servers[registered_name]
    return selected


@asynccontextmanager
async def connect(entry: dict[str, Any]) -> AsyncIterator[ClientSession]:
    environment = os.environ.copy()
    environment.update({str(key): str(value) for key, value in entry.get("env", {}).items()})
    parameters = StdioServerParameters(
        command=entry["command"],
        args=[str(value) for value in entry.get("args", [])],
        env=environment,
    )
    async with stdio_client(parameters) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def run(project: str, config_path: Path) -> dict[str, Any]:
    servers = read_registered_servers(config_path)
    trace: list[dict[str, Any]] = []

    async with connect(servers["freecad"]) as session:
        tools = await session.list_tools()
        if len(tools.tools) != 15:
            raise RuntimeError(f"FreeCAD MCP exposed {len(tools.tools)} tools, expected 15")
        await call(session, "freecad_environment_probe", {}, trace)
        await call(
            session,
            "freecad_document_create",
            {"project": project, "label": "Codex MCP 10 mm Cube", "overwrite": True},
            trace,
        )
        await call(
            session,
            "freecad_feature_create",
            {
                "project": project,
                "feature_type": "box",
                "name": "Cube",
                "parameters": {"length": "10 mm", "width": "10 mm", "height": "10 mm"},
            },
            trace,
        )
        await call(session, "freecad_document_inspect", {"project": project}, trace)
        await call(
            session,
            "freecad_geometry_validate",
            {"project": project, "objects": ["Cube"]},
            trace,
        )
        await call(
            session,
            "freecad_export_step",
            {"project": project, "objects": ["Cube"], "semantic_ids": {"Cube": "cube"}},
            trace,
        )

    solver_response: dict[str, Any]
    async with connect(servers["elmer"]) as session:
        tools = await session.list_tools()
        if len(tools.tools) != 17:
            raise RuntimeError(f"Elmer MCP exposed {len(tools.tools)} tools, expected 17")
        await call(session, "elmer_environment_probe", {}, trace)
        await call(
            session,
            "elmer_case_create",
            {"project": project, "analysis_type": "heat_steady_v1", "overwrite": True},
            trace,
        )
        await call(session, "elmer_geometry_import", {"project": project}, trace)
        await call(
            session,
            "elmer_mesh_generate",
            {"project": project, "global_size_mm": 2.0, "order": 1, "output_format": "msh2"},
            trace,
        )
        await call(session, "elmer_mesh_convert", {"project": project}, trace)
        await call(session, "elmer_mesh_inspect", {"project": project}, trace)
        await call(
            session,
            "elmer_material_set",
            {
                "project": project,
                "body": "solid",
                "material": {"name": "GenericSolid", "heat_conductivity": "1 W/(m K)"},
            },
            trace,
        )
        await call(session, "elmer_equation_set", {"project": project, "profile": "heat_steady_v1"}, trace)
        await call(
            session,
            "elmer_boundary_set",
            {
                "project": project,
                "selector": {"axis": "x", "side": "min", "object": "cube"},
                "condition": {"temperature": "300 K"},
            },
            trace,
        )
        await call(
            session,
            "elmer_boundary_set",
            {
                "project": project,
                "selector": {"axis": "x", "side": "max", "object": "cube"},
                "condition": {"temperature": "400 K"},
            },
            trace,
        )
        await call(session, "elmer_sif_generate", {"project": project}, trace)
        await call(session, "elmer_sif_validate", {"project": project}, trace)
        solver_response = await call(
            session,
            "elmer_solver_run",
            {"project": project, "mode": "serial", "timeout": 180},
            trace,
        )
        await call(session, "elmer_result_inspect", {"project": project}, trace)

    paraview_started = False
    async with connect(servers["paraview"]) as session:
        tools = await session.list_tools()
        if len(tools.tools) != 17:
            raise RuntimeError(f"ParaView MCP exposed {len(tools.tools)} tools, expected 17")
        try:
            await call(session, "paraview_environment_probe", {}, trace)
            await call(session, "paraview_session_start", {"project": project, "mode": "headless"}, trace)
            paraview_started = True
            opened = await call(
                session,
                "paraview_dataset_open",
                {"project": project, "path": "results/case.vtu", "alias": "result"},
                trace,
            )
            inspection = opened["data"]["inspection"]
            arrays = inspection["point_arrays"]
            temperature = next(item["name"] for item in arrays if item["name"].lower() == "temperature")
            await call(session, "paraview_dataset_inspect", {"project": project, "proxy": "result"}, trace)
            await call(
                session,
                "paraview_color_by",
                {"project": project, "proxy": "result", "array": temperature, "association": "POINTS"},
                trace,
            )
            await call(session, "paraview_camera_fit", {"project": project}, trace)
            await call(
                session,
                "paraview_export_image",
                {
                    "project": project,
                    "output": "post/mcp_temperature_surface.png",
                    "resolution": [1920, 1080],
                },
                trace,
            )
            await call(
                session,
                "paraview_filter_create",
                {
                    "project": project,
                    "input_proxy": "result",
                    "filter_type": "slice",
                    "parameters": {"origin": [5, 5, 5], "normal": [1, 0, 0]},
                    "alias": "slice_mid",
                },
                trace,
            )
            await call(
                session,
                "paraview_color_by",
                {"project": project, "proxy": "slice_mid", "array": temperature, "association": "POINTS"},
                trace,
            )
            await call(
                session,
                "paraview_camera_set",
                {
                    "project": project,
                    "camera": {
                        "position": [35, 5, 5],
                        "focal_point": [5, 5, 5],
                        "view_up": [0, 0, 1],
                    },
                },
                trace,
            )
            await call(session, "paraview_camera_fit", {"project": project}, trace)
            await call(
                session,
                "paraview_export_image",
                {
                    "project": project,
                    "output": "post/mcp_temperature_slice.png",
                    "resolution": [1920, 1080],
                },
                trace,
            )
            await call(
                session,
                "paraview_export_csv",
                {"project": project, "proxy": "result", "output": "post/mcp_temperature.csv"},
                trace,
            )
            await call(
                session,
                "paraview_state_save",
                {"project": project, "output": "post/mcp_pipeline.pvsm"},
                trace,
            )
            await call(session, "paraview_pipeline_inspect", {"project": project}, trace)
        finally:
            if paraview_started:
                await call(session, "paraview_session_stop", {"project": project}, trace)

    physics = solver_response["data"]["inspection"]["physics_acceptance"]
    status = "PASS" if physics["pass"] else "FAILED"
    workspace = Path(servers["freecad"]["env"]["OPEN_CAE_CONFIG"])
    with workspace.open("rb") as stream:
        open_cae_config = tomllib.load(stream)
    project_root = Path(open_cae_config["workspace"]["root"]) / project
    summary = {
        "status": status,
        "project": project,
        "codex_config": str(config_path),
        "registered_servers": SERVER_NAMES,
        "physics_acceptance": physics,
        "tool_calls": len(trace),
        "trace": trace,
    }
    output = project_root / "evidence" / "mcp_orchestration.json"
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    summary["orchestration_evidence"] = str(output)
    return summary


async def main() -> int:
    parser = argparse.ArgumentParser(description="Execute the heat smoke exclusively through Codex-registered MCP tools")
    parser.add_argument("--project", default=None)
    parser.add_argument("--codex-config", default=str(Path.home() / ".codex" / "config.toml"))
    args = parser.parse_args()
    project = args.project or datetime.now().strftime("codex_mcp_heat_%Y%m%d_%H%M%S")
    summary = await run(project, Path(args.codex_config))
    print(json.dumps({key: value for key, value in summary.items() if key != "trace"}, ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
