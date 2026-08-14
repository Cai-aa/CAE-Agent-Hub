from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp_beam_smoke import call, connect, project_root_from_entry, read_registered_servers, write_json


def write_pvd(path: Path, files: list[Path], time_step_s: float) -> None:
    rows = [
        '<?xml version="1.0"?>',
        '<VTKFile type="Collection" version="0.1" byte_order="LittleEndian">',
        "  <Collection>",
    ]
    for index, file in enumerate(files, start=1):
        rows.append(f'    <DataSet timestep="{index * time_step_s:.12g}" group="" part="0" file="{file.name}"/>')
    rows.extend(["  </Collection>", "</VTKFile>"])
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


async def run(project: str, config_path: Path) -> dict[str, Any]:
    servers = read_registered_servers(config_path)
    project_root = project_root_from_entry(servers["elmer"], project)
    trace: list[dict[str, Any]] = []

    async with connect(servers["freecad"]) as session:
        await call("freecad", session, "freecad_environment_probe", {}, trace)
        await call(
            "freecad",
            session,
            "freecad_document_create",
            {"project": project, "label": "FEP Transient Heat Cube", "overwrite": True},
            trace,
        )
        await call(
            "freecad",
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
        await call("freecad", session, "freecad_document_inspect", {"project": project}, trace)
        await call(
            "freecad",
            session,
            "freecad_geometry_validate",
            {"project": project, "objects": ["Cube"]},
            trace,
        )
        await call(
            "freecad",
            session,
            "freecad_export_step",
            {"project": project, "objects": ["Cube"], "semantic_ids": {"Cube": "solid"}},
            trace,
        )

    async with connect(servers["elmer"]) as session:
        await call("elmer", session, "elmer_environment_probe", {}, trace)
        await call(
            "elmer",
            session,
            "elmer_case_create",
            {"project": project, "analysis_type": "heat_transient_v1", "overwrite": True},
            trace,
        )
        await call("elmer", session, "elmer_geometry_import", {"project": project}, trace)
        await call(
            "elmer",
            session,
            "elmer_mesh_generate",
            {
                "project": project,
                "global_size_mm": 2.0,
                "order": 1,
                "dimension": 3,
                "coordinate_scale": 0.001,
                "output_format": "msh2",
            },
            trace,
        )
        await call("elmer", session, "elmer_mesh_convert", {"project": project}, trace)
        mesh = await call("elmer", session, "elmer_mesh_inspect", {"project": project}, trace)
        bounds = mesh["data"]["bounds"]
        if max(abs(bounds[1] - 0.01), abs(bounds[3] - 0.01), abs(bounds[5] - 0.01)) > 1.0e-8:
            raise RuntimeError(f"Transient heat mesh is not SI-scaled: {bounds}")
        await call(
            "elmer",
            session,
            "elmer_material_set",
            {
                "project": project,
                "body": "solid",
                "material": {
                    "name": "Stainless Steel 304 Smoke",
                    "heat_conductivity": 15.0,
                    "density_kg_per_m3": 8000.0,
                    "heat_capacity_j_per_kg_k": 500.0,
                },
            },
            trace,
        )
        await call(
            "elmer",
            session,
            "elmer_equation_set",
            {
                "project": project,
                "profile": "heat_transient_v1",
                "settings": {
                    "time_step_count": 20,
                    "time_step_s": 1.0,
                    "initial_temperature_k": 300.0,
                    "characteristic_length_m": 0.01,
                    "result_prefix": "transient_heat",
                },
            },
            trace,
        )
        await call(
            "elmer",
            session,
            "elmer_boundary_set",
            {"project": project, "selector": {"axis": "x", "side": "min"}, "condition": {"temperature": 400.0}},
            trace,
        )
        await call(
            "elmer",
            session,
            "elmer_boundary_set",
            {"project": project, "selector": {"axis": "x", "side": "max"}, "condition": {"temperature": 300.0}},
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
        await call("elmer", session, "elmer_log_inspect", {"project": project, "last_n_lines": 80}, trace)
        inspected = await call("elmer", session, "elmer_result_inspect", {"project": project}, trace)

    physics = inspected["data"]["physics_acceptance"]
    result_files = [project_root / item for item in json.loads(
        (project_root / "results" / "result_manifest.json").read_text(encoding="utf-8")
    )["files"]]
    if len(result_files) != 20 or not all(path.is_file() for path in result_files):
        raise RuntimeError("Expected 20 native transient heat VTU files")
    pvd_path = project_root / "results" / "transient_heat.pvd"
    write_pvd(pvd_path, result_files, 1.0)

    animation: dict[str, Any] | None = None
    paraview_started = False
    async with connect(servers["paraview"]) as session:
        try:
            await call("paraview", session, "paraview_environment_probe", {}, trace)
            await call("paraview", session, "paraview_session_start", {"project": project, "mode": "headless"}, trace)
            paraview_started = True
            opened = await call(
                "paraview",
                session,
                "paraview_dataset_open",
                {"project": project, "path": "results/transient_heat.pvd", "alias": "heat_time"},
                trace,
            )
            if len(opened["data"]["inspection"].get("time_steps", [])) != 20:
                raise RuntimeError("ParaView did not expose all 20 heat time steps")
            await call(
                "paraview",
                session,
                "paraview_filter_create",
                {
                    "project": project,
                    "input_proxy": "heat_time",
                    "filter_type": "slice",
                    "parameters": {"origin": [0.005, 0.005, 0.005], "normal": [0, 0, 1]},
                    "alias": "heat_midplane",
                },
                trace,
            )
            await call(
                "paraview",
                session,
                "paraview_color_by",
                {
                    "project": project,
                    "proxy": "heat_midplane",
                    "array": "temperature",
                    "association": "POINTS",
                    "preset": "Cool to Warm",
                },
                trace,
            )
            await call(
                "paraview",
                session,
                "paraview_camera_set",
                {
                    "project": project,
                    "camera": {
                        "position": [0.005, 0.005, 0.04],
                        "focal_point": [0.005, 0.005, 0.0],
                        "view_up": [0, 1, 0],
                    },
                },
                trace,
            )
            await call("paraview", session, "paraview_camera_fit", {"project": project}, trace)
            animation = await call(
                "paraview",
                session,
                "paraview_export_animation",
                {
                    "project": project,
                    "proxy": "heat_midplane",
                    "output": "post/transient_heat_steps/frame.png",
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
                    "output": "post/transient_heat_final.png",
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
                    "input_proxy": "heat_time",
                    "filter_type": "plot_over_line",
                    "parameters": {"point1": [0, 0.005, 0.005], "point2": [0.01, 0.005, 0.005], "resolution": 200},
                    "alias": "heat_centerline",
                },
                trace,
            )
            await call(
                "paraview",
                session,
                "paraview_export_csv",
                {"project": project, "proxy": "heat_centerline", "output": "post/transient_heat_centerline.csv"},
                trace,
            )
            await call(
                "paraview",
                session,
                "paraview_state_save",
                {"project": project, "output": "post/transient_heat_state.pvsm"},
                trace,
            )
            await call("paraview", session, "paraview_pipeline_inspect", {"project": project}, trace)
        finally:
            if paraview_started:
                await call("paraview", session, "paraview_session_stop", {"project": project}, trace)

    summary = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project": project,
        "status": "PASS" if physics.get("pass") and animation and animation["data"].get("validated_frame_count") == 20 else "FAIL",
        "analysis": "heat_transient_v1",
        "timeline": "20 real BDF1 transient heat time steps, dt=1 s",
        "tool_calls": len(trace),
        "job_id": solved["data"]["job_id"],
        "physics_acceptance": physics,
        "animation_frames": animation["data"].get("validated_frame_count") if animation else 0,
        "pvd": str(pvd_path),
    }
    write_json(project_root / "post" / "transient_heat_summary.json", summary)
    write_json(project_root / "evidence" / "mcp_transient_heat_trace.json", trace)
    if summary["status"] != "PASS":
        raise RuntimeError("Transient heat smoke did not pass all physics and animation gates")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a true transient heat process through registered FEP MCP servers")
    parser.add_argument("--project", default="transient_heat_process_smoke_v1")
    parser.add_argument("--codex-config", type=Path, default=Path.home() / ".codex" / "config.toml")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args.project, args.codex_config)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
