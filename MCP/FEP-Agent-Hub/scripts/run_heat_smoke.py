from __future__ import annotations

import argparse
import json
from datetime import datetime

from open_cae_core import EvidenceRecorder, ToolResponse, load_config
from open_cae_core.manifests import write_json
from elmer_mcp.service import ElmerService
from freecad_mcp.service import FreeCADService
from paraview_mcp.service import ParaViewService


def require(stage: str, response: ToolResponse, records: list[dict]) -> ToolResponse:
    records.append({"stage": stage, **response.to_dict()})
    print(f"[{response.status}] {stage}: {response.summary}")
    if not response.ok:
        raise RuntimeError(f"{stage}: {response.summary}")
    return response


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the real 10 mm cube OpenCAE heat smoke")
    parser.add_argument("--project", default=None, help="Safe workspace project name")
    parser.add_argument("--mesh-size", type=float, default=2.0)
    args = parser.parse_args()
    project = args.project or datetime.now().strftime("heat_smoke_%Y%m%d_%H%M%S")
    config = load_config()
    freecad = FreeCADService(config)
    elmer = ElmerService(config)
    paraview = ParaViewService(config)
    records: list[dict] = []
    status = "FAILED"
    error = None
    physics = None
    try:
        require("freecad_environment", freecad.environment_probe(), records)
        require("freecad_document_create", freecad.document_create(project, label="10 mm Cube Heat", overwrite=True), records)
        require(
            "freecad_feature_create",
            freecad.feature_create(
                project,
                "box",
                "Cube",
                {"length": "10 mm", "width": "10 mm", "height": "10 mm"},
            ),
            records,
        )
        require("freecad_geometry_validate", freecad.geometry_validate(project, ["Cube"]), records)
        require(
            "freecad_export_step",
            freecad.export_step(project, ["Cube"], semantic_ids={"Cube": "cube"}),
            records,
        )

        require("elmer_environment", elmer.environment_probe(), records)
        require("elmer_case_create", elmer.case_create(project, overwrite=True), records)
        require("elmer_geometry_import", elmer.geometry_import(project), records)
        require("elmer_mesh_generate", elmer.mesh_generate(project, args.mesh_size), records)
        require("elmer_mesh_convert", elmer.mesh_convert(project), records)
        require(
            "elmer_material_set",
            elmer.material_set(
                project,
                "solid",
                {"name": "GenericSolid", "heat_conductivity": "1 W/(m K)"},
            ),
            records,
        )
        require("elmer_equation_set", elmer.equation_set(project), records)
        require(
            "elmer_boundary_cold",
            elmer.boundary_set(
                project,
                {"axis": "x", "side": "min", "object": "cube"},
                {"temperature": "300 K"},
            ),
            records,
        )
        require(
            "elmer_boundary_hot",
            elmer.boundary_set(
                project,
                {"axis": "x", "side": "max", "object": "cube"},
                {"temperature": "400 K"},
            ),
            records,
        )
        require("elmer_sif_generate", elmer.sif_generate(project), records)
        require("elmer_sif_validate", elmer.sif_validate(project), records)
        solver = require("elmer_solver_run", elmer.solver_run(project), records)

        require("paraview_environment", paraview.environment_probe(), records)
        require("paraview_session_start", paraview.session_start(project), records)
        opened = require("paraview_dataset_open", paraview.dataset_open(project), records)
        actual_array = opened.data["inspection"]["point_arrays"][0]["name"]
        require("paraview_color_surface", paraview.color_by(project, "result", actual_array), records)
        require("paraview_camera_fit_surface", paraview.camera_fit(project), records)
        require(
            "paraview_export_surface",
            paraview.export_image(project, "post/temperature_surface.png", [1920, 1080]),
            records,
        )
        require(
            "paraview_slice",
            paraview.filter_create(
                project,
                "result",
                "slice",
                {"origin": [5, 5, 5], "normal": [1, 0, 0]},
                "slice_mid",
            ),
            records,
        )
        require("paraview_color_slice", paraview.color_by(project, "slice_mid", actual_array), records)
        require("paraview_camera_fit_slice", paraview.camera_fit(project), records)
        require(
            "paraview_export_slice",
            paraview.export_image(project, "post/temperature_slice.png", [1920, 1080]),
            records,
        )
        require(
            "paraview_export_csv",
            paraview.export_csv(project, "result", "post/temperature.csv"),
            records,
        )
        physics = solver.data["inspection"]["physics_acceptance"]
        status = "PASS" if physics["pass"] else "FAILED"
    except Exception as exc:
        error = str(exc)
    finally:
        stop = paraview.session_stop(project)
        records.append({"stage": "paraview_session_stop", **stop.to_dict()})

    project_root = config.workspace_root / project
    report_path = project_root / "evidence" / "final_report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_files = [
        path
        for path in project_root.rglob("*")
        if path.is_file()
        and path.relative_to(project_root).parts[0] in {"geometry", "mesh", "solver", "results", "post"}
    ]
    artifact_paths = sorted(path.relative_to(project_root).as_posix() for path in artifact_files)
    physics_lines = []
    if physics:
        physics_lines = [
            f"- Tmin: {physics['Tmin_K']:.9g} K",
            f"- Tmax: {physics['Tmax_K']:.9g} K",
            f"- Tmid: {physics['Tmid_K']:.9g} K",
        ]
    report_path.write_text(
        "\n".join(
            [
                "# OpenCAE 10 mm Cube Heat Smoke",
                "",
                f"- Status: **{status}**",
                f"- Project: `{project}`",
                f"- Error: `{error}`" if error else "- Error: none",
                *physics_lines,
                "",
                "## Artifacts",
                "",
                *[f"- `{value}`" for value in artifact_paths],
                "",
            ]
        ),
        encoding="utf-8",
    )
    environment = {
        record["stage"]: record.get("data", {})
        for record in records
        if record["stage"] in {"freecad_environment", "elmer_environment", "paraview_environment"}
    }
    write_json(project_root / "project.json", {"schema_version": "1.0", "project": project, "analysis": "heat_steady_v1"})
    write_json(project_root / "evidence" / "environment.json", environment)
    write_json(project_root / "evidence" / "validation.json", {"status": status, "error": error, "physics_acceptance": physics})
    recorder = EvidenceRecorder(project_root)
    recorder.record_artifacts(
        [
            *artifact_files,
            project_root / "project.json",
            project_root / "evidence" / "environment.json",
            project_root / "evidence" / "validation.json",
            report_path,
        ]
    )
    summary = {"status": status, "project": project, "error": error, "report": str(report_path), "stages": records}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
