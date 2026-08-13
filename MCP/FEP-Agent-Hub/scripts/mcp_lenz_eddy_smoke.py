from __future__ import annotations

import argparse
import asyncio
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp_transformer_smoke import (
    MCPFailure,
    archive_variant,
    call,
    connect,
    project_root_from_entry,
    read_registered_servers,
)


PROFILE = "magnetodynamics_2d_transient_eddy_v1"


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_pvd(path: Path, files: list[Path], time_step_s: float) -> None:
    rows = [
        '<?xml version="1.0"?>',
        '<VTKFile type="Collection" version="0.1" byte_order="LittleEndian">',
        "  <Collection>",
    ]
    for index, file in enumerate(files, start=1):
        rows.append(
            f'    <DataSet timestep="{index * time_step_s:.12g}" group="" part="0" file="{file.name}"/>'
        )
    rows.extend(["  </Collection>", "</VTKFile>"])
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def write_history_csv(path: Path, history: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "step",
        "time_s",
        "source_current_density_a_per_m2",
        "source_moment_rate_a_m2_per_s",
        "induced_moment_a_m2",
        "total_moment_rate_product",
        "ramp_index",
        "ramp_start_induced_moment_a_m2",
        "incremental_induced_moment_a_m2",
        "lenz_incremental_product",
        "eddy_current_min_a_per_m2",
        "eddy_current_max_a_per_m2",
        "eddy_current_rms_a_per_m2",
        "conductor_b_mean_t",
        "joule_power_w",
        "finite",
        "file",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: row.get(field) for field in fields} for row in history)


async def build_geometry(session: Any, project: str, trace: list[dict[str, Any]]) -> None:
    await call("freecad", session, "freecad_environment_probe", {}, trace)
    await call("freecad", session, "freecad_session_status", {}, trace)
    await call(
        "freecad",
        session,
        "freecad_document_create",
        {"project": project, "label": "FEP Lenz Law Transient Eddy Current 2D", "overwrite": True},
        trace,
    )
    rectangles = [
        ("AirOuter", -80.0, -60.0, 160.0, 120.0),
        ("Conductor", -20.0, -15.0, 40.0, 30.0),
        ("CoilPos", -45.0, -20.0, 8.0, 40.0),
        ("CoilNeg", 37.0, -20.0, 8.0, 40.0),
    ]
    for name, x0, y0, width, height in rectangles:
        await call(
            "freecad",
            session,
            "freecad_feature_create",
            {
                "project": project,
                "feature_type": "rectangle_face",
                "name": name,
                "parameters": {"width": f"{width} mm", "height": f"{height} mm"},
                "placement": {"position_mm": [x0, y0, 0.0]},
            },
            trace,
        )
    await call(
        "freecad",
        session,
        "freecad_boolean",
        {
            "project": project,
            "operation": "cut",
            "base": "AirOuter",
            "tools": ["Conductor", "CoilPos", "CoilNeg"],
            "result_name": "Air",
        },
        trace,
    )
    final_objects = ["Air", "Conductor", "CoilPos", "CoilNeg"]
    for name in final_objects:
        await call("freecad", session, "freecad_object_inspect", {"project": project, "name": name}, trace)
    await call(
        "freecad",
        session,
        "freecad_geometry_validate",
        {"project": project, "objects": final_objects},
        trace,
    )
    await call(
        "freecad",
        session,
        "freecad_export_step",
        {
            "project": project,
            "objects": final_objects,
            "also_export_parts": True,
            "semantic_ids": {
                "Air": "air",
                "Conductor": "conductor",
                "CoilPos": "coil_pos",
                "CoilNeg": "coil_neg",
            },
        },
        trace,
    )


async def solve_variant(
    session: Any,
    project: str,
    variant: str,
    *,
    mesh_size_mm: float,
    time_step_count: int,
    time_step_s: float,
    trace: list[dict[str, Any]],
) -> dict[str, Any]:
    quarter_period_s = 0.005
    await call(
        "elmer",
        session,
        "elmer_case_create",
        {"project": project, "analysis_type": PROFILE, "overwrite": True},
        trace,
    )
    await call("elmer", session, "elmer_geometry_import", {"project": project}, trace)
    await call(
        "elmer",
        session,
        "elmer_mesh_generate",
        {
            "project": project,
            "global_size_mm": mesh_size_mm,
            "order": 1,
            "dimension": 2,
            "coordinate_scale": 0.001,
            "output_format": "msh2",
        },
        trace,
    )
    await call("elmer", session, "elmer_mesh_convert", {"project": project}, trace)
    mesh = await call("elmer", session, "elmer_mesh_inspect", {"project": project}, trace)
    mesh_summary = mesh["data"]
    bounds = mesh_summary["bounds"]
    if (
        mesh_summary["dimension"] != 2
        or abs(bounds[0] + 0.08) > 1.0e-7
        or abs(bounds[1] - 0.08) > 1.0e-7
        or abs(bounds[2] + 0.06) > 1.0e-7
        or abs(bounds[3] - 0.06) > 1.0e-7
    ):
        raise MCPFailure(f"SI mesh gate failed: dimension={mesh_summary['dimension']} bounds={bounds}")

    materials = {
        "air": {"name": "Air", "relative_permeability": 1.0, "electric_conductivity_s_per_m": 0.0},
        "conductor": {
            "name": "Copper Conductor",
            "relative_permeability": 1.0,
            "electric_conductivity_s_per_m": 5.8e7,
        },
        "coil_pos": {
            "name": "Prescribed Stranded Coil Positive",
            "relative_permeability": 1.0,
            "electric_conductivity_s_per_m": 0.0,
        },
        "coil_neg": {
            "name": "Prescribed Stranded Coil Negative",
            "relative_permeability": 1.0,
            "electric_conductivity_s_per_m": 0.0,
        },
    }
    for body, material in materials.items():
        await call(
            "elmer",
            session,
            "elmer_material_set",
            {"project": project, "body": body, "material": material},
            trace,
        )
    await call(
        "elmer",
        session,
        "elmer_equation_set",
        {
            "project": project,
            "profile": PROFILE,
            "settings": {
                "time_step_count": time_step_count,
                "time_step_s": time_step_s,
                "quarter_period_s": quarter_period_s,
                "stack_depth_m": 0.02,
                "result_prefix": variant,
            },
        },
        trace,
    )
    for body, direction in (("coil_pos", 1.0), ("coil_neg", -1.0)):
        await call(
            "elmer",
            session,
            "elmer_excitation_set",
            {
                "project": project,
                "body": body,
                "excitation": {
                    "peak_current_density_a_per_m2": 1.0e6,
                    "direction": direction,
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
            "selector": {"semantic": "outer_boundary"},
            "condition": {"potential": 0.0},
        },
        trace,
    )
    await call("elmer", session, "elmer_case_inspect", {"project": project}, trace)
    await call("elmer", session, "elmer_sif_generate", {"project": project}, trace)
    await call("elmer", session, "elmer_sif_validate", {"project": project}, trace)
    solved = await call(
        "elmer",
        session,
        "elmer_solver_run",
        {"project": project, "mode": "serial", "timeout": 900},
        trace,
    )
    await call(
        "elmer",
        session,
        "elmer_job_status",
        {"project": project, "job_id": solved["data"]["job_id"]},
        trace,
    )
    log = await call(
        "elmer",
        session,
        "elmer_log_inspect",
        {"project": project, "last_n_lines": 160},
        trace,
    )
    inspected = await call("elmer", session, "elmer_result_inspect", {"project": project}, trace)
    physics = inspected["data"]["physics_acceptance"]
    if not physics.get("pass"):
        raise MCPFailure(f"{variant} physics gate failed: {physics}")
    return {
        "variant": variant,
        "mesh_size_mm": mesh_size_mm,
        "time_step_count": time_step_count,
        "time_step_s": time_step_s,
        "mesh": mesh_summary,
        "physics": physics,
        "job_id": solved["data"]["job_id"],
        "log_summary": log["data"],
        "result_artifacts": inspected.get("artifacts", []),
    }


def relative_difference(first: float, second: float) -> float:
    denominator = max(abs(first), abs(second), 1.0e-30)
    return abs(first - second) / denominator


async def postprocess(
    session: Any,
    project: str,
    trace: list[dict[str, Any]],
) -> dict[str, Any]:
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
            {"project": project, "path": "results/lenz_baseline.pvd", "alias": "lenz_time"},
            trace,
        )
        inspection = opened["data"]["inspection"]
        if len(inspection.get("time_steps", [])) != 40:
            raise MCPFailure("ParaView did not expose all 40 native transient steps")
        names = {item["name"]: item for item in inspection.get("point_arrays", [])}
        required = {
            "magnetic_flux_density_derived_t",
            "eddy_current_density_z_derived_a_per_m2",
            "eddy_current_density_vector_derived_a_per_m2",
            "joule_power_density_derived_w_per_m3",
        }
        if not required.issubset(names) or not all(names[name]["finite"] for name in required):
            raise MCPFailure(f"Required finite transient arrays are missing: {sorted(required - names.keys())}")
        await call(
            "paraview",
            session,
            "paraview_color_by",
            {
                "project": project,
                "proxy": "lenz_time",
                "array": "eddy_current_density_z_derived_a_per_m2",
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
                "proxy": "lenz_time",
                "output": "post/lenz_steps/frame.png",
                "resolution": [1920, 1080],
                "frame_rate": 20,
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
                "output": "post/lenz_eddy_current_final.png",
                "resolution": [1920, 1080],
                "background": [0.015, 0.025, 0.06],
            },
            trace,
        )
        await call(
            "paraview",
            session,
            "paraview_color_by",
            {
                "project": project,
                "proxy": "lenz_time",
                "array": "magnetic_flux_density_derived_t",
                "association": "POINTS",
                "preset": "Cool to Warm",
            },
            trace,
        )
        await call(
            "paraview",
            session,
            "paraview_export_image",
            {
                "project": project,
                "output": "post/lenz_magnetic_flux_density.png",
                "resolution": [1920, 1080],
                "background": [0.015, 0.025, 0.06],
            },
            trace,
        )
        vector_range = await call(
            "paraview",
            session,
            "paraview_scalar_range",
            {
                "project": project,
                "proxy": "lenz_time",
                "array": "eddy_current_density_vector_derived_a_per_m2",
                "association": "POINTS",
            },
            trace,
        )
        maximum = max(abs(value) for value in vector_range["data"]["range"])
        scale_factor = 0.025 / maximum if maximum > 0 else 1.0
        await call(
            "paraview",
            session,
            "paraview_filter_create",
            {
                "project": project,
                "input_proxy": "lenz_time",
                "filter_type": "glyph",
                "parameters": {
                    "array": "eddy_current_density_vector_derived_a_per_m2",
                    "association": "POINTS",
                    "scale_factor": scale_factor,
                },
                "alias": "eddy_direction",
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
                    "position": [0.16, -0.20, 0.18],
                    "focal_point": [0.0, 0.0, 0.0],
                    "view_up": [0.0, 0.0, 1.0],
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
                "output": "post/lenz_eddy_direction_glyphs.png",
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
                "input_proxy": "lenz_time",
                "filter_type": "plot_over_line",
                "parameters": {
                    "point1": [-0.02, 0.0, 0.0],
                    "point2": [0.02, 0.0, 0.0],
                    "resolution": 240,
                },
                "alias": "conductor_centerline",
            },
            trace,
        )
        await call(
            "paraview",
            session,
            "paraview_export_csv",
            {
                "project": project,
                "proxy": "conductor_centerline",
                "output": "post/lenz_conductor_centerline.csv",
            },
            trace,
        )
        await call(
            "paraview",
            session,
            "paraview_state_save",
            {"project": project, "output": "post/lenz_transient_state.pvsm"},
            trace,
        )
        pipeline = await call(
            "paraview", session, "paraview_pipeline_inspect", {"project": project}, trace
        )
        return {
            "inspection": inspection,
            "animation_frames": animation["data"]["validated_frame_count"],
            "vector_range": vector_range["data"],
            "pipeline": pipeline["data"],
        }
    finally:
        await call("paraview", session, "paraview_session_stop", {"project": project}, trace)


async def run(project: str, config_path: Path, variants_mode: str) -> dict[str, Any]:
    servers = read_registered_servers(config_path)
    project_root = project_root_from_entry(servers["elmer"], project)
    trace: list[dict[str, Any]] = []
    inventories: dict[str, Any] = {}

    async with connect(servers["freecad"]) as session:
        tools = await session.list_tools()
        resources = await session.list_resources()
        templates = await session.list_resource_templates()
        inventories["freecad"] = {
            "tools": [item.name for item in tools.tools],
            "resources": len(resources.resources),
            "templates": len(templates.resourceTemplates),
        }
        await build_geometry(session, project, trace)

    variant_specs = [("lenz_baseline", 2.0, 40, 0.0005)]
    if variants_mode == "full":
        variant_specs.extend(
            [
                ("lenz_time_fine", 2.0, 80, 0.00025),
                ("lenz_mesh_fine", 1.5, 40, 0.0005),
            ]
        )
    variants: list[dict[str, Any]] = []
    archives: dict[str, Any] = {}
    async with connect(servers["elmer"]) as session:
        tools = await session.list_tools()
        resources = await session.list_resources()
        templates = await session.list_resource_templates()
        inventories["elmer"] = {
            "tools": [item.name for item in tools.tools],
            "resources": len(resources.resources),
            "templates": len(templates.resourceTemplates),
        }
        if "elmer_excitation_set" not in inventories["elmer"]["tools"]:
            raise MCPFailure("Registered Elmer MCP does not expose structured excitations")
        await call("elmer", session, "elmer_environment_probe", {}, trace)
        for variant, mesh_size, count, dt in variant_specs:
            result = await solve_variant(
                session,
                project,
                variant,
                mesh_size_mm=mesh_size,
                time_step_count=count,
                time_step_s=dt,
                trace=trace,
            )
            variants.append(result)
            archives[variant] = archive_variant(project_root, variant)

    by_name = {item["variant"]: item for item in variants}
    baseline = by_name["lenz_baseline"]["physics"]
    sensitivity: dict[str, Any] = {"executed": variants_mode == "full", "pass": variants_mode != "full"}
    if variants_mode == "full":
        time_fine = by_name["lenz_time_fine"]["physics"]
        mesh_fine = by_name["lenz_mesh_fine"]["physics"]
        sensitivity = {
            "executed": True,
            "time_step": {
                "peak_eddy_rms_relative_difference": relative_difference(
                    baseline["peak_eddy_current_rms_a_per_m2"],
                    time_fine["peak_eddy_current_rms_a_per_m2"],
                ),
                "joule_energy_relative_difference": relative_difference(
                    baseline["joule_energy_j"], time_fine["joule_energy_j"]
                ),
                "limit": 0.08,
            },
            "mesh": {
                "peak_eddy_rms_relative_difference": relative_difference(
                    baseline["peak_eddy_current_rms_a_per_m2"],
                    mesh_fine["peak_eddy_current_rms_a_per_m2"],
                ),
                "joule_energy_relative_difference": relative_difference(
                    baseline["joule_energy_j"], mesh_fine["joule_energy_j"]
                ),
                "limit": 0.10,
            },
        }
        sensitivity["time_step"]["pass"] = max(
            sensitivity["time_step"]["peak_eddy_rms_relative_difference"],
            sensitivity["time_step"]["joule_energy_relative_difference"],
        ) <= sensitivity["time_step"]["limit"]
        sensitivity["mesh"]["pass"] = max(
            sensitivity["mesh"]["peak_eddy_rms_relative_difference"],
            sensitivity["mesh"]["joule_energy_relative_difference"],
        ) <= sensitivity["mesh"]["limit"]
        sensitivity["pass"] = sensitivity["time_step"]["pass"] and sensitivity["mesh"]["pass"]

    baseline_files = sorted(
        path
        for path in (project_root / "results").glob("lenz_baseline*.vtu")
        if "_elmer_raw" not in path.stem
    )
    if len(baseline_files) != 40:
        raise MCPFailure(f"Expected 40 baseline VTUs, found {len(baseline_files)}")
    pvd_path = project_root / "results" / "lenz_baseline.pvd"
    write_pvd(pvd_path, baseline_files, 0.0005)
    history_path = project_root / "post" / "lenz_time_history.csv"
    write_history_csv(history_path, baseline["history"])

    async with connect(servers["paraview"]) as session:
        tools = await session.list_tools()
        resources = await session.list_resources()
        templates = await session.list_resource_templates()
        inventories["paraview"] = {
            "tools": [item.name for item in tools.tools],
            "resources": len(resources.resources),
            "templates": len(templates.resourceTemplates),
        }
        paraview = await postprocess(session, project, trace)

    statuses = [item["response"].get("status", "UNKNOWN") for item in trace]
    overall_pass = (
        all(item["physics"].get("pass") for item in variants)
        and sensitivity["pass"]
        and paraview["animation_frames"] == 40
        and all(status == "SUCCEEDED" for status in statuses)
    )
    summary = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project": project,
        "status": "PASS" if overall_pass else "FAIL",
        "profile": PROFILE,
        "model_scope": "linear 2D planar real-transient eddy-current Lenz-law smoke",
        "inventories": inventories,
        "variants": variants,
        "sensitivity": sensitivity,
        "paraview": paraview,
        "tool_calls": len(trace),
        "call_status_counts": {status: statuses.count(status) for status in sorted(set(statuses))},
        "artifacts": {
            "pvd": str(pvd_path),
            "history_csv": str(history_path),
        },
        "archives": archives,
        "limitations": [
            "2D planar Az formulation; induced z-current closure and end effects are represented only by the equivalent cross-section model",
            "linear isotropic permeability; no ferromagnetic core, saturation, or hysteresis",
            "constant copper conductivity; no thermal feedback or motion",
            "finite air box with zero magnetic vector potential at its outer boundary",
            "derived E, Jeddy, Joule density, and diagnostic magnetic moment are deterministic post-processing of native Elmer Az time steps",
        ],
    }
    write_json(project_root / "post" / "lenz_validation_summary.json", summary)
    write_json(project_root / "evidence" / "mcp_lenz_eddy_trace.json", trace)
    if not overall_pass:
        raise MCPFailure("Lenz-law transient eddy-current smoke did not pass all gates")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the Lenz-law transient eddy-current smoke through registered FEP MCP servers"
    )
    parser.add_argument("--project", default="lenz_eddy_current_smoke_v1")
    parser.add_argument("--codex-config", type=Path, default=Path.home() / ".codex" / "config.toml")
    parser.add_argument("--variants", choices=("baseline", "full"), default="full")
    args = parser.parse_args()
    result = asyncio.run(run(args.project, args.codex_config, args.variants))
    print(
        json.dumps(
            {key: value for key, value in result.items() if key not in {"variants", "archives", "paraview"}},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
