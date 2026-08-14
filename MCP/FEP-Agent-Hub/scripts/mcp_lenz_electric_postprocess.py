from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from mcp_transformer_smoke import call, connect, project_root_from_entry, read_registered_servers


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


async def run(project: str, config_path: Path) -> dict[str, Any]:
    servers = read_registered_servers(config_path)
    project_root = project_root_from_entry(servers["paraview"], project)
    trace: list[dict[str, Any]] = []
    async with connect(servers["paraview"]) as session:
        await call("paraview", session, "paraview_environment_probe", {}, trace)
        await call(
            "paraview",
            session,
            "paraview_session_start",
            {"project": project, "mode": "headless"},
            trace,
        )
        try:
            opened = await call(
                "paraview",
                session,
                "paraview_dataset_open",
                {"project": project, "path": "results/lenz_baseline.pvd", "alias": "lenz_electric"},
                trace,
            )
            if len(opened["data"]["inspection"].get("time_steps", [])) != 40:
                raise RuntimeError("The supplemental electric-field view did not expose 40 time steps")
            await call(
                "paraview",
                session,
                "paraview_dataset_inspect",
                {"project": project, "proxy": "lenz_electric"},
                trace,
            )
            field = "electric_field_z_derived_v_per_m"
            scalar_range = await call(
                "paraview",
                session,
                "paraview_scalar_range",
                {"project": project, "proxy": "lenz_electric", "array": field, "association": "POINTS"},
                trace,
            )
            await call(
                "paraview",
                session,
                "paraview_color_by",
                {
                    "project": project,
                    "proxy": "lenz_electric",
                    "array": field,
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
                        "position": [0.0, 0.0, 0.4],
                        "focal_point": [0.0, 0.0, 0.0],
                        "view_up": [0.0, 1.0, 0.0],
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
                    "proxy": "lenz_electric",
                    "output": "post/lenz_electric_steps/frame.png",
                    "resolution": [1920, 1080],
                    "frame_rate": 20,
                    "background": [0.015, 0.025, 0.06],
                },
                trace,
            )
            image = await call(
                "paraview",
                session,
                "paraview_export_image",
                {
                    "project": project,
                    "output": "post/lenz_electric_field_z.png",
                    "resolution": [1920, 1080],
                    "background": [0.015, 0.025, 0.06],
                },
                trace,
            )
        finally:
            await call("paraview", session, "paraview_session_stop", {"project": project}, trace)
    statuses = [item["response"].get("status", "UNKNOWN") for item in trace]
    summary = {
        "status": "PASS" if all(status == "SUCCEEDED" for status in statuses) else "FAIL",
        "tool_calls": len(trace),
        "call_status_counts": {status: statuses.count(status) for status in sorted(set(statuses))},
        "field": "electric_field_z_derived_v_per_m",
        "range_v_per_m": scalar_range["data"]["range"],
        "time_steps": 40,
        "animation_frames": animation["data"]["validated_frame_count"],
        "image": image["artifacts"][0],
    }
    write_json(project_root / "evidence" / "mcp_lenz_electric_postprocess_trace.json", trace)
    write_json(project_root / "post" / "lenz_electric_postprocess_summary.json", summary)
    if summary["status"] != "PASS":
        raise RuntimeError("Supplemental electric-field ParaView MCP workflow failed")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Export the verified transient induced electric field through ParaView MCP")
    parser.add_argument("--project", default="lenz_eddy_current_smoke_v1")
    parser.add_argument("--codex-config", type=Path, default=Path.home() / ".codex" / "config.toml")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args.project, args.codex_config)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
