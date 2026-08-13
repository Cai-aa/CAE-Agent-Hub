from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import tomllib
from contextlib import asynccontextmanager
from datetime import datetime, timezone
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
    server: str,
    session: ClientSession,
    tool: str,
    arguments: dict[str, Any],
    trace: list[dict[str, Any]],
) -> dict[str, Any]:
    result = await session.call_tool(tool, arguments)
    payload = response_payload(result)
    trace.append({"server": server, "tool": tool, "arguments": arguments, "response": payload})
    status = payload.get("status", "UNKNOWN")
    print(f"[{status}] {tool}: {payload.get('summary', '')}", flush=True)
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


def project_root_from_entry(entry: dict[str, Any], project: str) -> Path:
    config_path = Path(entry["env"]["OPEN_CAE_CONFIG"])
    with config_path.open("rb") as stream:
        config = tomllib.load(stream)
    return Path(config["workspace"]["root"]) / project


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def archive_step(project_root: Path, step_name: str) -> list[dict[str, Any]]:
    target = project_root / "evidence" / "load_steps" / step_name
    target.mkdir(parents=True, exist_ok=True)
    sources = [
        project_root / "solver" / "case.sif",
        project_root / "solver" / "case_model.json",
        project_root / "solver" / "solver.log",
        project_root / "solver" / "solver.err.log",
    ]
    records = []
    for source in sources:
        if not source.is_file():
            continue
        output = target / source.name
        shutil.copy2(source, output)
        records.append(
            {
                "source": str(source),
                "archive": str(output),
                "size": output.stat().st_size,
                "sha256": sha256(output),
            }
        )
    return records


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_pvd(path: Path, steps: list[dict[str, Any]]) -> None:
    rows = [
        '<?xml version="1.0"?>',
        '<VTKFile type="Collection" version="0.1" byte_order="LittleEndian">',
        "  <Collection>",
    ]
    for step in steps:
        rows.append(
            f'    <DataSet timestep="{step["load_factor"]:.6g}" group="" part="0" file="{step["file"].name}"/>'
        )
    rows.extend(["  </Collection>", "</VTKFile>"])
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


async def build_geometry(session: ClientSession, project: str, trace: list[dict[str, Any]]) -> None:
    await call("freecad", session, "freecad_environment_probe", {}, trace)
    await call("freecad", session, "freecad_session_status", {}, trace)
    await call(
        "freecad",
        session,
        "freecad_document_create",
        {"project": project, "label": "FEP Simply Supported Beam 2D", "overwrite": True},
        trace,
    )
    await call(
        "freecad",
        session,
        "freecad_feature_create",
        {
            "project": project,
            "feature_type": "rectangle_face",
            "name": "Beam",
            "parameters": {"width": "1000 mm", "height": "100 mm"},
            "placement": {"position_mm": [0, 0, 0]},
        },
        trace,
    )
    await call("freecad", session, "freecad_object_inspect", {"project": project, "name": "Beam"}, trace)
    await call(
        "freecad",
        session,
        "freecad_geometry_validate",
        {"project": project, "objects": ["Beam"]},
        trace,
    )
    await call(
        "freecad",
        session,
        "freecad_export_step",
        {"project": project, "objects": ["Beam"], "semantic_ids": {"Beam": "beam"}},
        trace,
    )


async def run(project: str, config_path: Path) -> dict[str, Any]:
    servers = read_registered_servers(config_path)
    project_root = project_root_from_entry(servers["elmer"], project)
    trace: list[dict[str, Any]] = []
    load_steps: list[dict[str, Any]] = []

    async with connect(servers["freecad"]) as session:
        tools = await session.list_tools()
        if len(tools.tools) != 15:
            raise RuntimeError(f"FreeCAD MCP exposed {len(tools.tools)} tools, expected 15")
        await build_geometry(session, project, trace)

    async with connect(servers["elmer"]) as session:
        tools = await session.list_tools()
        if len(tools.tools) != 17:
            raise RuntimeError(f"Elmer MCP exposed {len(tools.tools)} tools, expected 17")
        await call("elmer", session, "elmer_environment_probe", {}, trace)
        await call(
            "elmer",
            session,
            "elmer_case_create",
            {"project": project, "analysis_type": "elasticity_2d_static_v1", "overwrite": True},
            trace,
        )
        await call("elmer", session, "elmer_geometry_import", {"project": project}, trace)
        await call(
            "elmer",
            session,
            "elmer_mesh_generate",
            {
                "project": project,
                "global_size_mm": 10.0,
                "order": 1,
                "dimension": 2,
                "coordinate_scale": 0.001,
                "output_format": "msh2",
            },
            trace,
        )
        await call("elmer", session, "elmer_mesh_convert", {"project": project}, trace)
        await call("elmer", session, "elmer_mesh_inspect", {"project": project}, trace)
        await call(
            "elmer",
            session,
            "elmer_material_set",
            {
                "project": project,
                "body": "beam",
                "material": {
                    "name": "Structural Steel",
                    "youngs_modulus_pa": 210.0e9,
                    "poisson_ratio": 0.3,
                    "density_kg_per_m3": 7850,
                },
            },
            trace,
        )
        await call(
            "elmer",
            session,
            "elmer_boundary_set",
            {
                "project": project,
                "selector": {"semantic": "left_pin"},
                "condition": {"displacement_x_m": 0, "displacement_y_m": 0},
            },
            trace,
        )
        await call(
            "elmer",
            session,
            "elmer_boundary_set",
            {
                "project": project,
                "selector": {"semantic": "right_roller"},
                "condition": {"displacement_y_m": 0},
            },
            trace,
        )

        for index in range(1, 11):
            load_factor = index / 10.0
            prefix = f"beam_step_{index:02d}"
            await call(
                "elmer",
                session,
                "elmer_equation_set",
                {
                    "project": project,
                    "profile": "elasticity_2d_static_v1",
                    "settings": {
                        "beam_length_m": 1.0,
                        "beam_height_m": 0.1,
                        "thickness_m": 0.01,
                        "load_factor": load_factor,
                        "result_prefix": prefix,
                    },
                },
                trace,
            )
            await call(
                "elmer",
                session,
                "elmer_boundary_set",
                {
                    "project": project,
                    "selector": {"semantic": "top_load"},
                    "condition": {"traction_y_pa": -1.0e6 * load_factor},
                },
                trace,
            )
            await call("elmer", session, "elmer_sif_generate", {"project": project}, trace)
            await call("elmer", session, "elmer_sif_validate", {"project": project}, trace)
            solved = await call(
                "elmer",
                session,
                "elmer_solver_run",
                {"project": project, "mode": "serial", "timeout": 300},
                trace,
            )
            await call("elmer", session, "elmer_log_inspect", {"project": project, "last_n_lines": 40}, trace)
            inspected = await call("elmer", session, "elmer_result_inspect", {"project": project}, trace)
            candidates = sorted(
                (
                    path
                    for path in (project_root / "results").glob(f"{prefix}*.vtu")
                    if "_elmer_raw" not in path.stem
                ),
                key=lambda path: path.stat().st_mtime,
            )
            if not candidates:
                raise RuntimeError(f"No derived VTU found for {prefix}")
            result_file = candidates[-1]
            physics = inspected["data"]["physics_acceptance"]
            load_steps.append(
                {
                    "index": index,
                    "load_factor": load_factor,
                    "pressure_pa": 1.0e6 * load_factor,
                    "file": result_file,
                    "file_sha256": sha256(result_file),
                    "physics": physics,
                    "job_id": solved["data"]["job_id"],
                    "evidence_archive": archive_step(project_root, prefix),
                }
            )

    pvd_path = project_root / "results" / "beam_load_steps.pvd"
    write_pvd(pvd_path, load_steps)
    metrics_path = project_root / "post" / "beam_load_step_metrics.json"
    serializable_steps = [
        {**step, "file": str(step["file"]), "pvd_file": step["file"].name}
        for step in load_steps
    ]
    write_json(
        metrics_path,
        {
            "schema_version": "1.0",
            "analysis": "elasticity_2d_static_v1",
            "timeline": "ten independent quasi-static load levels; not a transient dynamics solve",
            "load_steps": serializable_steps,
        },
    )

    animation_response: dict[str, Any] | None = None
    paraview_started = False
    async with connect(servers["paraview"]) as session:
        tools = await session.list_tools()
        if len(tools.tools) != 17:
            raise RuntimeError(f"ParaView MCP exposed {len(tools.tools)} tools, expected 17")
        try:
            await call("paraview", session, "paraview_environment_probe", {}, trace)
            await call(
                "paraview",
                session,
                "paraview_session_start",
                {"project": project, "mode": "headless"},
                trace,
            )
            paraview_started = True
            opened = await call(
                "paraview",
                session,
                "paraview_dataset_open",
                {"project": project, "path": "results/beam_load_steps.pvd", "alias": "beam_steps"},
                trace,
            )
            if len(opened["data"]["inspection"].get("time_steps", [])) != 10:
                raise RuntimeError("ParaView did not expose all ten beam load steps")
            await call(
                "paraview",
                session,
                "paraview_dataset_inspect",
                {"project": project, "proxy": "beam_steps"},
                trace,
            )
            await call(
                "paraview",
                session,
                "paraview_filter_create",
                {
                    "project": project,
                    "input_proxy": "beam_steps",
                    "filter_type": "warp",
                    "parameters": {
                        "array": "displacement_vector_derived",
                        "association": "POINTS",
                        "scale_factor": 100.0,
                    },
                    "alias": "beam_warp",
                },
                trace,
            )
            await call(
                "paraview",
                session,
                "paraview_color_by",
                {
                    "project": project,
                    "proxy": "beam_warp",
                    "array": "von_mises_derived_pa",
                    "association": "POINTS",
                    "preset": "Cool to Warm",
                },
                trace,
            )
            await call("paraview", session, "paraview_camera_fit", {"project": project}, trace)
            animation_response = await call(
                "paraview",
                session,
                "paraview_export_animation",
                {
                    "project": project,
                    "proxy": "beam_warp",
                    "output": "post/beam_load_steps/frame.png",
                    "resolution": [1920, 1080],
                    "frame_rate": 10,
                    "background": [0.015, 0.025, 0.06],
                },
                trace,
            )
            await call(
                "paraview",
                session,
                "paraview_export_image",
                {
                    "project": project,
                    "output": "post/beam_von_mises_full_load.png",
                    "resolution": [1920, 1080],
                    "background": [0.015, 0.025, 0.06],
                },
                trace,
            )
            await call(
                "paraview",
                session,
                "paraview_filter_create",
                {
                    "project": project,
                    "input_proxy": "beam_steps",
                    "filter_type": "plot_over_line",
                    "parameters": {
                        "point1": [0.0, 0.05, 0.0],
                        "point2": [1.0, 0.05, 0.0],
                        "resolution": 200,
                    },
                    "alias": "beam_centerline",
                },
                trace,
            )
            await call(
                "paraview",
                session,
                "paraview_export_csv",
                {"project": project, "proxy": "beam_centerline", "output": "post/beam_centerline.csv"},
                trace,
            )
            await call(
                "paraview",
                session,
                "paraview_state_save",
                {"project": project, "output": "post/beam_state.pvsm"},
                trace,
            )
            await call("paraview", session, "paraview_pipeline_inspect", {"project": project}, trace)
        finally:
            if paraview_started:
                await call("paraview", session, "paraview_session_stop", {"project": project}, trace)

    trace_path = project_root / "evidence" / "mcp_beam_trace.json"
    write_json(trace_path, trace)
    full_load = load_steps[-1]["physics"]
    summary = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project": project,
        "status": "PASS" if all(step["physics"].get("pass") for step in load_steps) else "FAIL",
        "timeline": "10 real quasi-static load levels (10%..100%); not transient dynamics",
        "tool_calls": len(trace),
        "load_steps_passed": sum(bool(step["physics"].get("pass")) for step in load_steps),
        "load_steps_total": len(load_steps),
        "full_load": full_load,
        "pvd": str(pvd_path),
        "metrics": str(metrics_path),
        "animation_frames": animation_response["data"].get("validated_frame_count") if animation_response else 0,
        "trace": str(trace_path),
    }
    summary_path = project_root / "post" / "beam_case_summary.json"
    write_json(summary_path, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    if summary["status"] != "PASS" or summary["animation_frames"] != 10:
        raise RuntimeError("Beam smoke did not pass every load-step and animation-frame gate")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the simply-supported beam case through registered FEP MCP servers")
    parser.add_argument("--project", default="simply_supported_beam_smoke_v1")
    parser.add_argument("--codex-config", type=Path, default=Path.home() / ".codex" / "config.toml")
    args = parser.parse_args()
    asyncio.run(run(args.project, args.codex_config))


if __name__ == "__main__":
    main()
