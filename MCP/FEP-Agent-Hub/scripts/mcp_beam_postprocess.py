from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from mcp_beam_smoke import call, connect, project_root_from_entry, read_registered_servers, write_json


async def run(project: str, config_path: Path) -> dict[str, Any]:
    servers = read_registered_servers(config_path)
    project_root = project_root_from_entry(servers["paraview"], project)
    metrics_path = project_root / "post" / "beam_load_step_metrics.json"
    if not metrics_path.is_file():
        raise FileNotFoundError("Run mcp_beam_smoke.py through the Elmer load steps first")
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    load_steps = metrics.get("load_steps", [])
    if len(load_steps) != 10 or not all(step.get("physics", {}).get("pass") for step in load_steps):
        raise RuntimeError("The ten verified beam load steps are unavailable")

    trace: list[dict[str, Any]] = []
    started = False
    animation: dict[str, Any] | None = None
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
            started = True
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
                "paraview_dataset_inspect",
                {"project": project, "proxy": "beam_warp"},
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
            animation = await call(
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
            if started:
                await call("paraview", session, "paraview_session_stop", {"project": project}, trace)

    trace_path = project_root / "evidence" / "mcp_beam_post_trace.json"
    write_json(trace_path, trace)
    summary = {
        "schema_version": "1.0",
        "project": project,
        "status": "PASS",
        "timeline": "10 real quasi-static load levels (10%..100%); not transient dynamics",
        "load_steps_passed": 10,
        "load_steps_total": 10,
        "full_load": load_steps[-1]["physics"],
        "animation_frames": animation["data"].get("validated_frame_count") if animation else 0,
        "postprocess_tool_calls": len(trace),
        "trace": str(trace_path),
    }
    if summary["animation_frames"] != 10:
        raise RuntimeError("ParaView did not validate all ten animation frames")
    write_json(project_root / "post" / "beam_case_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Finish ParaView postprocessing for an existing verified beam run")
    parser.add_argument("--project", default="simply_supported_beam_smoke_v1")
    parser.add_argument("--codex-config", type=Path, default=Path.home() / ".codex" / "config.toml")
    args = parser.parse_args()
    asyncio.run(run(args.project, args.codex_config))


if __name__ == "__main__":
    main()
