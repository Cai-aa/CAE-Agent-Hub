from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import shutil
import tomllib
from contextlib import asynccontextmanager
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


def archive_variant(project_root: Path, variant: str) -> list[dict[str, Any]]:
    target = project_root / "evidence" / "variants" / variant
    target.mkdir(parents=True, exist_ok=True)
    candidates = [
        project_root / "solver" / "case.sif",
        project_root / "solver" / "case_model.json",
        project_root / "solver" / "solver.log",
        project_root / "solver" / "solver.err.log",
        project_root / "mesh" / "model.geo",
        project_root / "mesh" / "mesh_manifest.json",
        project_root / "mesh" / "semantic_map.json",
        project_root / "evidence" / "logs" / "gmsh.stdout.log",
        project_root / "evidence" / "logs" / "gmsh.stderr.log",
        project_root / "evidence" / "logs" / "elmergrid.stdout.log",
        project_root / "evidence" / "logs" / "elmergrid.stderr.log",
    ]
    records = []
    for source in candidates:
        if not source.is_file():
            continue
        output = target / source.name
        if output.exists():
            output = target / f"{source.parent.name}-{source.name}"
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


async def build_geometry(session: ClientSession, project: str, trace: list[dict[str, Any]]) -> None:
    await call("freecad", session, "freecad_environment_probe", {}, trace)
    await call("freecad", session, "freecad_session_status", {}, trace)
    await call(
        "freecad",
        session,
        "freecad_document_create",
        {"project": project, "label": "FEP Transformer Induction 2D", "overwrite": True},
        trace,
    )
    rectangles = [
        ("AirOuter", -80, -70, 160, 140),
        ("CoreTop", -40, 20, 80, 15),
        ("CoreBottom", -40, -35, 80, 15),
        ("CoreLeft", -40, -20, 15, 40),
        ("CoreCenter", -10, -20, 20, 40),
        ("CoreRight", 25, -20, 15, 40),
        ("PrimaryPos", -17, -15, 5, 30),
        ("PrimaryNeg", 12, -15, 5, 30),
        ("SecondaryPos", -24, -15, 5, 30),
        ("SecondaryNeg", 19, -15, 5, 30),
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
                "placement": {"position_mm": [x0, y0, 0]},
            },
            trace,
        )
    await call(
        "freecad",
        session,
        "freecad_boolean",
        {
            "project": project,
            "operation": "fuse",
            "base": "CoreTop",
            "tools": ["CoreBottom", "CoreLeft", "CoreCenter", "CoreRight"],
            "result_name": "Core",
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
            "tools": ["Core", "PrimaryPos", "PrimaryNeg", "SecondaryPos", "SecondaryNeg"],
            "result_name": "Air",
        },
        trace,
    )
    final_objects = ["Air", "Core", "PrimaryPos", "PrimaryNeg", "SecondaryPos", "SecondaryNeg"]
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
                "Core": "core",
                "PrimaryPos": "primary_pos",
                "PrimaryNeg": "primary_neg",
                "SecondaryPos": "secondary_pos",
                "SecondaryNeg": "secondary_neg",
            },
        },
        trace,
    )


async def solve_variant(
    session: ClientSession,
    project: str,
    variant: str,
    current_rms_a: float,
    mesh_size_mm: float,
    trace: list[dict[str, Any]],
) -> dict[str, Any]:
    await call(
        "elmer",
        session,
        "elmer_case_create",
        {"project": project, "analysis_type": "magnetodynamics_2d_harmonic_v1", "overwrite": True},
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
    converted = await call("elmer", session, "elmer_mesh_convert", {"project": project}, trace)
    mesh_summary = converted["data"]["summary"]
    bounds = mesh_summary["bounds"]
    if mesh_summary["dimension"] != 2 or abs((bounds[1] - bounds[0]) - 0.16) > 1.0e-6 or abs((bounds[3] - bounds[2]) - 0.14) > 1.0e-6:
        raise MCPFailure(f"SI mesh gate failed: dimension={mesh_summary['dimension']} bounds={bounds}")
    await call("elmer", session, "elmer_mesh_inspect", {"project": project}, trace)
    for body in ("air", "core", "primary_pos", "primary_neg", "secondary_pos", "secondary_neg"):
        await call(
            "elmer",
            session,
            "elmer_material_set",
            {
                "project": project,
                "body": body,
                "material": {
                    "name": "LinearLaminatedCore" if body == "core" else "NonconductingStrandedRegion",
                    "relative_permeability": 1000 if body == "core" else 1,
                    "electric_conductivity_s_per_m": 0,
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
            "profile": "magnetodynamics_2d_harmonic_v1",
            "settings": {
                "frequency_hz": 50,
                "primary_turns": 100,
                "secondary_turns": 50,
                "stack_depth_m": 0.02,
                "flux_line_x_min_m": -0.01,
                "flux_line_x_max_m": 0.01,
                "flux_line_y_m": 0,
                "result_prefix": variant,
            },
        },
        trace,
    )
    density = 100.0 * current_rms_a / 1.5e-4
    for body, sign in (("primary_pos", 1.0), ("primary_neg", -1.0)):
        await call(
            "elmer",
            session,
            "elmer_excitation_set",
            {
                "project": project,
                "body": body,
                "excitation": {
                    "current_density_re_a_per_m2": sign * density,
                    "current_density_im_a_per_m2": 0,
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
            "condition": {"potential_re": 0, "potential_im": 0},
        },
        trace,
    )
    await call("elmer", session, "elmer_case_inspect", {"project": project}, trace)
    await call("elmer", session, "elmer_sif_generate", {"project": project}, trace)
    await call("elmer", session, "elmer_sif_validate", {"project": project}, trace)
    solver = await call(
        "elmer",
        session,
        "elmer_solver_run",
        {"project": project, "mode": "serial", "timeout": 600},
        trace,
    )
    await call("elmer", session, "elmer_job_status", {"project": project, "job_id": solver["data"]["job_id"]}, trace)
    await call("elmer", session, "elmer_log_inspect", {"project": project, "last_n_lines": 120}, trace)
    inspected = await call("elmer", session, "elmer_result_inspect", {"project": project}, trace)
    return {
        "variant": variant,
        "current_rms_A": current_rms_a,
        "mesh_size_mm": mesh_size_mm,
        "mesh": mesh_summary,
        "physics": inspected["data"]["physics_acceptance"],
        "result_artifacts": inspected.get("artifacts", []),
    }


def find_array(records: list[dict[str, Any]], pattern: str) -> str:
    regex = re.compile(pattern, re.IGNORECASE)
    for record in records:
        if regex.fullmatch(record["name"]) or regex.search(record["name"]):
            return record["name"]
    raise MCPFailure(f"Required ParaView array was not found: {pattern}; available={[item['name'] for item in records]}")


async def postprocess(
    session: ClientSession,
    project: str,
    result_path: str,
    trace: list[dict[str, Any]],
) -> dict[str, Any]:
    await call("paraview", session, "paraview_environment_probe", {}, trace)
    await call("paraview", session, "paraview_session_start", {"project": project, "mode": "headless"}, trace)
    try:
        opened = await call(
            "paraview",
            session,
            "paraview_dataset_open",
            {"project": project, "path": result_path, "alias": "transformer"},
            trace,
        )
        inspection = opened["data"]["inspection"]
        arrays = inspection["point_arrays"]
        b_re = find_array(arrays, r"b\s*re")
        b_im = find_array(arrays, r"b\s*im")
        a_re = find_array(arrays, r"a\s*re")
        a_im = find_array(arrays, r"a\s*im")
        by_array = {item["name"]: item for item in arrays}
        if by_array[b_re]["components"] < 2 or by_array[b_im]["components"] < 2:
            raise MCPFailure("ParaView did not inspect B re/im as vector fields")
        if by_array[a_re]["components"] != 1 or by_array[a_im]["components"] != 1:
            raise MCPFailure("ParaView did not inspect A re/im as scalar complex components")
        if not all(by_array[name]["finite"] for name in (a_re, a_im, b_re, b_im)):
            raise MCPFailure("ParaView detected a non-finite electromagnetic array range")
        await call("paraview", session, "paraview_dataset_inspect", {"project": project, "proxy": "transformer"}, trace)
        await call(
            "paraview",
            session,
            "paraview_color_by",
            {"project": project, "proxy": "transformer", "array": b_re, "association": "POINTS", "preset": "Cool to Warm"},
            trace,
        )
        await call(
            "paraview",
            session,
            "paraview_camera_set",
            {"project": project, "camera": {"position": [0, 0, 0.4], "focal_point": [0, 0, 0], "view_up": [0, 1, 0]}},
            trace,
        )
        await call("paraview", session, "paraview_camera_fit", {"project": project}, trace)
        await call(
            "paraview",
            session,
            "paraview_export_image",
            {"project": project, "output": "post/transformer_B_magnitude.png", "resolution": [1920, 1080], "background": [0.12, 0.12, 0.12]},
            trace,
        )
        a_range = await call(
            "paraview",
            session,
            "paraview_scalar_range",
            {"project": project, "proxy": "transformer", "array": a_re, "association": "POINTS"},
            trace,
        )
        low, high = a_range["data"]["range"]
        levels = [low + (high - low) * index / 14.0 for index in range(1, 14)]
        await call(
            "paraview",
            session,
            "paraview_filter_create",
            {"project": project, "input_proxy": "transformer", "filter_type": "contour", "parameters": {"array": a_re, "association": "POINTS", "values": levels}, "alias": "flux_lines"},
            trace,
        )
        await call(
            "paraview",
            session,
            "paraview_color_by",
            {"project": project, "proxy": "flux_lines", "array": a_re, "association": "POINTS"},
            trace,
        )
        await call("paraview", session, "paraview_camera_fit", {"project": project}, trace)
        await call(
            "paraview",
            session,
            "paraview_export_image",
            {"project": project, "output": "post/transformer_flux_lines.png", "resolution": [1920, 1080], "background": [0.12, 0.12, 0.12]},
            trace,
        )
        await call(
            "paraview",
            session,
            "paraview_filter_create",
            {"project": project, "input_proxy": "transformer", "filter_type": "glyph", "parameters": {"array": b_re, "association": "POINTS", "scale_factor": 0.012}, "alias": "B_vectors"},
            trace,
        )
        await call("paraview", session, "paraview_camera_fit", {"project": project}, trace)
        await call(
            "paraview",
            session,
            "paraview_export_image",
            {"project": project, "output": "post/transformer_B_vectors.png", "resolution": [1920, 1080], "background": [0.12, 0.12, 0.12]},
            trace,
        )
        await call(
            "paraview",
            session,
            "paraview_filter_create",
            {
                "project": project,
                "input_proxy": "transformer",
                "filter_type": "plot_over_line",
                "parameters": {"point1": [-0.01, 0.0, 0.0], "point2": [0.01, 0.0, 0.0], "resolution": 200},
                "alias": "center_limb_line",
            },
            trace,
        )
        await call(
            "paraview",
            session,
            "paraview_export_csv",
            {"project": project, "proxy": "center_limb_line", "output": "post/center_limb_flux.csv"},
            trace,
        )
        await call(
            "paraview",
            session,
            "paraview_state_save",
            {"project": project, "output": "post/transformer_state.pvsm"},
            trace,
        )
        pipeline = await call("paraview", session, "paraview_pipeline_inspect", {"project": project}, trace)
        return {
            "inspection": inspection,
            "B_arrays": {"real": b_re, "imaginary": b_im},
            "A_arrays": {"real": a_re, "imaginary": a_im},
            "pipeline": pipeline["data"],
        }
    finally:
        await call("paraview", session, "paraview_session_stop", {"project": project}, trace)


def relative_ratio_error(numerator: float, denominator: float, expected: float) -> float:
    if denominator == 0 or expected == 0:
        return float("inf")
    return abs(numerator / denominator - expected) / abs(expected)


async def run(project: str, config_path: Path) -> dict[str, Any]:
    servers = read_registered_servers(config_path)
    project_root = project_root_from_entry(servers["freecad"], project)
    trace: list[dict[str, Any]] = []
    inventories: dict[str, Any] = {}

    async with connect(servers["freecad"]) as session:
        tools = await session.list_tools()
        resources = await session.list_resources()
        templates = await session.list_resource_templates()
        inventories["freecad"] = {"tools": [item.name for item in tools.tools], "resources": len(resources.resources), "templates": len(templates.resourceTemplates)}
        if len(tools.tools) != 15:
            raise RuntimeError(f"FreeCAD MCP exposed {len(tools.tools)} tools, expected 15")
        await build_geometry(session, project, trace)

    variants = []
    archives: dict[str, Any] = {}
    async with connect(servers["elmer"]) as session:
        tools = await session.list_tools()
        resources = await session.list_resources()
        templates = await session.list_resource_templates()
        inventories["elmer"] = {"tools": [item.name for item in tools.tools], "resources": len(resources.resources), "templates": len(templates.resourceTemplates)}
        if len(tools.tools) != 17 or "elmer_excitation_set" not in inventories["elmer"]["tools"]:
            raise RuntimeError(f"Elmer MCP profile is stale: tools={len(tools.tools)}")
        await call("elmer", session, "elmer_environment_probe", {}, trace)
        for variant, current, mesh_size in (
            ("baseline", 1.0, 1.5),
            ("half_current", 0.5, 1.5),
            ("fine_mesh", 1.0, 1.25),
        ):
            result = await solve_variant(session, project, variant, current, mesh_size, trace)
            variants.append(result)
            archives[variant] = archive_variant(project_root, variant)

    by_name = {item["variant"]: item for item in variants}
    baseline = by_name["baseline"]["physics"]
    half = by_name["half_current"]["physics"]
    fine = by_name["fine_mesh"]["physics"]
    linearity = {
        "flux_ratio": baseline["flux_magnitude_Wb"] / half["flux_magnitude_Wb"],
        "Bmax_ratio": baseline["Bmax_T"] / half["Bmax_T"],
        "V2_ratio": baseline["V2_open_rms_V"] / half["V2_open_rms_V"],
    }
    linearity["max_relative_error"] = max(abs(value - 2.0) / 2.0 for value in linearity.values())
    linearity["pass"] = linearity["max_relative_error"] <= 0.03
    mesh_sensitivity = {
        "flux_relative_difference": abs(fine["flux_magnitude_Wb"] - baseline["flux_magnitude_Wb"]) / abs(fine["flux_magnitude_Wb"]),
        "Bmax_relative_difference": abs(fine["Bmax_T"] - baseline["Bmax_T"]) / abs(fine["Bmax_T"]),
        "V2_relative_difference": abs(fine["V2_open_rms_V"] - baseline["V2_open_rms_V"]) / abs(fine["V2_open_rms_V"]),
    }
    mesh_sensitivity["pass"] = mesh_sensitivity["flux_relative_difference"] <= 0.05 and mesh_sensitivity["V2_relative_difference"] <= 0.05

    baseline_files = sorted((project_root / "results").glob("baseline*.vtu"), key=lambda path: path.stat().st_mtime)
    if not baseline_files:
        raise MCPFailure("Baseline VTU disappeared before ParaView post-processing")
    baseline_relative = baseline_files[-1].relative_to(project_root).as_posix()
    async with connect(servers["paraview"]) as session:
        tools = await session.list_tools()
        resources = await session.list_resources()
        templates = await session.list_resource_templates()
        inventories["paraview"] = {"tools": [item.name for item in tools.tools], "resources": len(resources.resources), "templates": len(templates.resourceTemplates)}
        if len(tools.tools) != 17:
            raise RuntimeError(f"ParaView MCP exposed {len(tools.tools)} tools, expected 17")
        paraview = await postprocess(session, project, baseline_relative, trace)

    call_statuses = [item["response"].get("status", "UNKNOWN") for item in trace]
    overall_pass = (
        all(item["physics"].get("pass") for item in variants)
        and linearity["pass"]
        and mesh_sensitivity["pass"]
        and all(status == "SUCCEEDED" for status in call_statuses)
    )
    summary = {
        "status": "PASS" if overall_pass else "FAILED",
        "project": project,
        "model_scope": "linear 2D planar harmonic open-circuit transformer-effect smoke",
        "inventories": inventories,
        "variants": variants,
        "linearity_acceptance": linearity,
        "mesh_sensitivity_acceptance": mesh_sensitivity,
        "paraview": paraview,
        "tool_calls": len(trace),
        "call_status_counts": {status: call_statuses.count(status) for status in sorted(set(call_statuses))},
        "archives": archives,
        "limitations": [
            "linear relative permeability; no saturation or hysteresis",
            "nonconducting stranded winding regions; no skin effect or copper loss",
            "open-circuit voltage inferred from finite-element core flux; no load power or efficiency",
            "2D planar model with 20 mm assumed stack depth; no 3D end leakage",
            "finite air box with zero vector-potential outer boundary",
        ],
        "trace": trace,
    }
    metrics_output = project_root / "post" / "induction_metrics.json"
    metrics_output.write_text(
        json.dumps(
            {
                "profile": "magnetodynamics_2d_harmonic_v1",
                "variants": variants,
                "linearity_acceptance": linearity,
                "mesh_sensitivity_acceptance": mesh_sensitivity,
                "overall_pass": overall_pass,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    summary["induction_metrics_artifact"] = metrics_output.relative_to(project_root).as_posix()
    output = project_root / "evidence" / "transformer_mcp_orchestration.json"
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    summary["orchestration_evidence"] = str(output)
    return summary


async def main() -> int:
    parser = argparse.ArgumentParser(description="Execute the transformer induction smoke exclusively through FEP MCP tools")
    parser.add_argument("--project", default="transformer_induction_smoke_v1")
    parser.add_argument("--codex-config", default=str(Path(__file__).parents[1] / "private" / "codex-validation.local.toml"))
    args = parser.parse_args()
    summary = await run(args.project, Path(args.codex_config))
    print(json.dumps({key: value for key, value in summary.items() if key not in {"trace", "archives"}}, ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
