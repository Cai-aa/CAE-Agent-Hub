from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp_beam_smoke import call, connect, project_root_from_entry, read_registered_servers, write_json


async def run(project: str, config_path: Path) -> dict[str, Any]:
    servers = read_registered_servers(config_path)
    project_root = project_root_from_entry(servers["elmer"], project)
    trace: list[dict[str, Any]] = []

    async with connect(servers["freecad"]) as session:
        await call("freecad", session, "freecad_environment_probe", {}, trace)
        await call("freecad", session, "freecad_session_status", {}, trace)
        await call(
            "freecad",
            session,
            "freecad_document_create",
            {"project": project, "label": "FEP 2D Laminar Channel", "overwrite": True},
            trace,
        )
        await call(
            "freecad",
            session,
            "freecad_feature_create",
            {
                "project": project,
                "feature_type": "rectangle_face",
                "name": "Fluid",
                "parameters": {"width": "100 mm", "height": "20 mm"},
                "placement": {"position_mm": [0, 0, 0]},
            },
            trace,
        )
        await call("freecad", session, "freecad_object_inspect", {"project": project, "name": "Fluid"}, trace)
        await call(
            "freecad",
            session,
            "freecad_geometry_validate",
            {"project": project, "objects": ["Fluid"]},
            trace,
        )
        await call(
            "freecad",
            session,
            "freecad_export_step",
            {"project": project, "objects": ["Fluid"], "semantic_ids": {"Fluid": "fluid"}},
            trace,
        )

    async with connect(servers["elmer"]) as session:
        await call("elmer", session, "elmer_environment_probe", {}, trace)
        await call(
            "elmer",
            session,
            "elmer_case_create",
            {"project": project, "analysis_type": "navier_stokes_2d_steady_v1", "overwrite": True},
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
                "dimension": 2,
                "coordinate_scale": 0.001,
                "output_format": "msh2",
            },
            trace,
        )
        await call("elmer", session, "elmer_mesh_convert", {"project": project}, trace)
        mesh = await call("elmer", session, "elmer_mesh_inspect", {"project": project}, trace)
        if mesh["data"].get("named_boundaries") != {"inlet": 1, "outlet": 2, "walls": 3}:
            raise RuntimeError(f"Unexpected channel semantic boundaries: {mesh['data'].get('named_boundaries')}")
        await call(
            "elmer",
            session,
            "elmer_material_set",
            {
                "project": project,
                "body": "fluid",
                "material": {
                    "name": "Viscous Newtonian Smoke Fluid",
                    "density_kg_per_m3": 1000.0,
                    "dynamic_viscosity_pa_s": 0.01,
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
                "profile": "navier_stokes_2d_steady_v1",
                "settings": {
                    "channel_length_m": 0.1,
                    "channel_height_m": 0.02,
                    "mean_velocity_m_per_s": 0.05,
                    "result_prefix": "channel_flow",
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
                "selector": {"semantic": "inlet"},
                "condition": {"mean_velocity_m_per_s": 0.05},
            },
            trace,
        )
        await call(
            "elmer",
            session,
            "elmer_boundary_set",
            {"project": project, "selector": {"semantic": "outlet"}, "condition": {"pressure_pa": 0.0}},
            trace,
        )
        await call(
            "elmer",
            session,
            "elmer_boundary_set",
            {
                "project": project,
                "selector": {"semantic": "walls"},
                "condition": {"velocity_x_m_per_s": 0.0, "velocity_y_m_per_s": 0.0},
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
        await call("elmer", session, "elmer_log_inspect", {"project": project, "last_n_lines": 100}, trace)
        inspected = await call("elmer", session, "elmer_result_inspect", {"project": project}, trace)

    result_manifest = json.loads((project_root / "results" / "result_manifest.json").read_text(encoding="utf-8"))
    result_path = result_manifest["files"][-1]
    physics = inspected["data"]["physics_acceptance"]
    paraview_started = False
    async with connect(servers["paraview"]) as session:
        try:
            await call("paraview", session, "paraview_environment_probe", {}, trace)
            await call("paraview", session, "paraview_session_start", {"project": project, "mode": "headless"}, trace)
            paraview_started = True
            await call(
                "paraview",
                session,
                "paraview_dataset_open",
                {"project": project, "path": result_path, "alias": "channel"},
                trace,
            )
            await call("paraview", session, "paraview_dataset_inspect", {"project": project, "proxy": "channel"}, trace)
            await call(
                "paraview",
                session,
                "paraview_color_by",
                {
                    "project": project,
                    "proxy": "channel",
                    "array": physics["velocity_field"],
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
                        "position": [0.05, 0.01, 0.2],
                        "focal_point": [0.05, 0.01, 0.0],
                        "view_up": [0, 1, 0],
                    },
                },
                trace,
            )
            await call("paraview", session, "paraview_camera_fit", {"project": project}, trace)
            await call(
                "paraview",
                session,
                "paraview_export_image",
                {
                    "project": project,
                    "output": "post/channel_velocity_magnitude.png",
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
                    "input_proxy": "channel",
                    "filter_type": "glyph",
                    "parameters": {
                        "array": physics["velocity_field"],
                        "association": "POINTS",
                        "scale_factor": 0.15,
                    },
                    "alias": "velocity_arrows",
                },
                trace,
            )
            await call(
                "paraview",
                session,
                "paraview_color_by",
                {
                    "project": project,
                    "proxy": "velocity_arrows",
                    "array": physics["velocity_field"],
                    "association": "POINTS",
                    "preset": "Cool to Warm",
                },
                trace,
            )
            await call("paraview", session, "paraview_camera_fit", {"project": project}, trace)
            await call(
                "paraview",
                session,
                "paraview_export_image",
                {
                    "project": project,
                    "output": "post/channel_velocity_vectors.png",
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
                    "input_proxy": "channel",
                    "filter_type": "plot_over_line",
                    "parameters": {"point1": [0.05, 0, 0], "point2": [0.05, 0.02, 0], "resolution": 100},
                    "alias": "midsection_profile",
                },
                trace,
            )
            await call(
                "paraview",
                session,
                "paraview_export_csv",
                {"project": project, "proxy": "midsection_profile", "output": "post/channel_midsection_profile.csv"},
                trace,
            )
            await call(
                "paraview",
                session,
                "paraview_state_save",
                {"project": project, "output": "post/channel_flow_state.pvsm"},
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
        "status": "PASS" if physics.get("pass") else "FAIL",
        "analysis": "navier_stokes_2d_steady_v1",
        "model_scope": "steady incompressible 2D laminar Poiseuille channel smoke",
        "tool_calls": len(trace),
        "job_id": solved["data"]["job_id"],
        "physics_acceptance": physics,
    }
    write_json(project_root / "post" / "channel_flow_summary.json", summary)
    write_json(project_root / "evidence" / "mcp_channel_flow_trace.json", trace)
    if summary["status"] != "PASS":
        raise RuntimeError("Channel flow smoke did not pass all physics gates")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a 2D laminar channel-flow case through registered FEP MCP servers")
    parser.add_argument("--project", default="laminar_channel_flow_smoke_v1")
    parser.add_argument("--codex-config", type=Path, default=Path.home() / ".codex" / "config.toml")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args.project, args.codex_config)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
