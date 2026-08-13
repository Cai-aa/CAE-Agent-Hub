from __future__ import annotations

from pathlib import Path

import meshio
import numpy as np
import pytest

from elmer_mcp.mesh import gmsh_geo_2d, gmsh_geo_beam_2d, gmsh_geo_channel_2d, gmsh_geo_eddy_2d, parse_elmer_mesh, write_semantic_map
from elmer_mcp.service import ElmerService
from elmer_mcp.sif import (
    SUPPORTED_PROFILES,
    generate_elasticity_2d_static_sif,
    generate_heat_sif,
    generate_heat_transient_sif,
    generate_magnetodynamics_2d_harmonic_sif,
    generate_magnetodynamics_2d_transient_eddy_sif,
    generate_navier_stokes_2d_steady_sif,
    validate_sif,
)
from open_cae_core.config import OpenCAEConfig
from open_cae_core.manifests import read_json


def _write_mesh(root: Path) -> None:
    root.mkdir(parents=True)
    (root / "mesh.header").write_text("8 1 6\n1\n504 1\n", encoding="utf-8")
    nodes = [
        (1, 0, 0, 0), (2, 1, 0, 0), (3, 1, 1, 0), (4, 0, 1, 0),
        (5, 0, 0, 1), (6, 1, 0, 1), (7, 1, 1, 1), (8, 0, 1, 1),
    ]
    (root / "mesh.nodes").write_text(
        "".join(f"{node} -1 {x} {y} {z}\n" for node, x, y, z in nodes),
        encoding="utf-8",
    )
    (root / "mesh.elements").write_text("1 1 504 1 2 3 5\n", encoding="utf-8")
    faces = [
        (1, [1, 4, 8, 5]), (2, [2, 3, 7, 6]), (3, [1, 2, 6, 5]),
        (4, [4, 3, 7, 8]), (5, [1, 2, 3, 4]), (6, [5, 6, 7, 8]),
    ]
    (root / "mesh.boundary").write_text(
        "".join(
            f"{index} {boundary} 1 0 404 {' '.join(map(str, node_ids))}\n"
            for index, (boundary, node_ids) in enumerate(faces, start=1)
        ),
        encoding="utf-8",
    )


def test_coordinate_boundary_mapping(tmp_path: Path) -> None:
    mesh_dir = tmp_path / "elmer_mesh"
    _write_mesh(mesh_dir)
    summary = parse_elmer_mesh(mesh_dir)
    assert summary["semantic_boundaries"] == {
        "x_min": [1], "x_max": [2], "y_min": [3], "y_max": [4], "z_min": [5], "z_max": [6]
    }
    path = write_semantic_map(
        tmp_path / "semantic_map.json",
        summary,
        {"objects": [{"semantic_id": "cube"}]},
    )
    mapping = read_json(path)
    assert mapping["status"] == "MAPPED"
    assert mapping["body_ids"] == {"cube": 1}


def test_heat_sif_generation_and_validation(tmp_path: Path) -> None:
    case = {
        "analysis_type": "heat_steady_v1",
        "materials": {"solid": {"name": "Solid", "heat_conductivity": 1.0}},
        "boundaries": [
            {"semantic": "x_min", "temperature_k": 300.0},
            {"semantic": "x_max", "temperature_k": 400.0},
        ],
    }
    mapping = {
        "body_ids": {"cube": 1},
        "boundary_ids": {"x_min": [1], "x_max": [2]},
    }
    sif = tmp_path / "case.sif"
    sif.write_text(generate_heat_sif(case, mapping), encoding="utf-8")
    validation = validate_sif(sif)
    assert validation["valid"]
    assert "Target Boundaries(1) = 1" in sif.read_text(encoding="utf-8")


def test_transient_heat_sif_generation_and_validation(tmp_path: Path) -> None:
    case = {
        "analysis_type": "heat_transient_v1",
        "materials": {
            "solid": {
                "name": "Steel",
                "heat_conductivity": 15.0,
                "density_kg_per_m3": 8000.0,
                "heat_capacity_j_per_kg_k": 500.0,
            }
        },
        "equation": {
            "settings": {
                "time_step_count": 20,
                "time_step_s": 1.0,
                "initial_temperature_k": 300.0,
                "result_prefix": "transient_heat",
            }
        },
        "boundaries": [
            {"semantic": "x_min", "temperature_k": 400.0},
            {"semantic": "x_max", "temperature_k": 300.0},
        ],
    }
    mapping = {"body_ids": {"solid": 1}, "boundary_ids": {"x_min": [1], "x_max": [2]}}
    text = generate_heat_transient_sif(case, mapping)
    sif = tmp_path / "transient.sif"
    sif.write_text(text, encoding="utf-8")
    validation = validate_sif(sif, profile="heat_transient_v1")
    assert validation["valid"]
    assert "Simulation Type = Transient" in text
    assert "Timestep Intervals = 20" in text
    assert 'Output File Name = "../../results/transient_heat"' in text


def _electromagnetic_manifest() -> dict:
    def record(semantic: str, bbox: list[float], sources: list[dict] | None = None) -> dict:
        value = {"semantic_id": semantic, "bbox_mm": bbox, "role": "planar_face"}
        if sources:
            value["source_rectangles_mm"] = sources
        return value

    core_sources = [
        {"x_min": -40, "x_max": 40, "y_min": 20, "y_max": 35},
        {"x_min": -40, "x_max": 40, "y_min": -35, "y_max": -20},
        {"x_min": -40, "x_max": -25, "y_min": -20, "y_max": 20},
        {"x_min": -10, "x_max": 10, "y_min": -20, "y_max": 20},
        {"x_min": 25, "x_max": 40, "y_min": -20, "y_max": 20},
    ]
    return {
        "schema_version": "1.0",
        "units": "mm",
        "objects": [
            record("air", [-80, 80, -70, 70, 0, 0]),
            record("core", [-40, 40, -35, 35, 0, 0], core_sources),
            record("primary_pos", [-17, -12, -15, 15, 0, 0]),
            record("primary_neg", [12, 17, -15, 15, 0, 0]),
            record("secondary_pos", [-24, -19, -15, 15, 0, 0]),
            record("secondary_neg", [19, 24, -15, 15, 0, 0]),
        ],
    }


def _electromagnetic_case() -> dict:
    materials = {
        name: {
            "name": name,
            "relative_permeability": 1000.0 if name == "core" else 1.0,
            "electric_conductivity_s_per_m": 0.0,
        }
        for name in ("air", "core", "primary_pos", "primary_neg", "secondary_pos", "secondary_neg")
    }
    return {
        "analysis_type": "magnetodynamics_2d_harmonic_v1",
        "materials": materials,
        "excitations": {
            "primary_pos": {"current_density_re_a_per_m2": 666666.6667, "current_density_im_a_per_m2": 0},
            "primary_neg": {"current_density_re_a_per_m2": -666666.6667, "current_density_im_a_per_m2": 0},
        },
        "equation": {
            "profile": "magnetodynamics_2d_harmonic_v1",
            "settings": {
                "frequency_hz": 50,
                "primary_turns": 100,
                "secondary_turns": 50,
                "stack_depth_m": 0.02,
                "result_prefix": "baseline",
            },
        },
    }


def test_electromagnetic_profile_and_planar_gmsh_template(tmp_path: Path) -> None:
    assert "magnetodynamics_2d_harmonic_v1" in SUPPORTED_PROFILES
    text, bodies, boundaries = gmsh_geo_2d(
        tmp_path / "model.step",
        tmp_path / "model.msh",
        _electromagnetic_manifest(),
        1.5,
        coordinate_scale=0.001,
    )
    assert bodies == {"air": 1, "core": 2, "primary_pos": 3, "primary_neg": 4, "secondary_pos": 5, "secondary_neg": 6}
    assert boundaries == {"outer_boundary": 1001}
    assert "-0.08" in text and "0.16" in text
    assert 'Physical Surface("core", 2)' in text
    with pytest.raises(ValueError):
        gmsh_geo_2d(tmp_path / "model.step", tmp_path / "model.msh", _electromagnetic_manifest(), 1.5, coordinate_scale=1.0)


def test_electromagnetic_sif_generation_and_validation(tmp_path: Path) -> None:
    mapping = {
        "dimension": 2,
        "body_ids": {"air": 1, "core": 2, "primary_pos": 3, "primary_neg": 4, "secondary_pos": 5, "secondary_neg": 6},
        "boundary_ids": {"outer_boundary": [1001]},
    }
    text = generate_magnetodynamics_2d_harmonic_sif(_electromagnetic_case(), mapping)
    sif = tmp_path / "case.sif"
    sif.write_text(text, encoding="utf-8")
    validation = validate_sif(sif, profile="magnetodynamics_2d_harmonic_v1")
    assert validation["valid"]
    assert 'Procedure = "MagnetoDynamics2D" "MagnetoDynamics2DHarmonic"' in text
    assert "Current Density = Real -666666.6667" in text
    assert 'Output File Name = "../../results/baseline"' in text


def test_electromagnetic_material_excitation_and_result_gate(tmp_path: Path) -> None:
    config = OpenCAEConfig(workspace_root=tmp_path / "workspace")
    service = ElmerService(config)
    assert service.case_create("em", "magnetodynamics_2d_harmonic_v1").ok
    assert service.material_set("em", "core", {"relative_permeability": 1000, "electric_conductivity_s_per_m": 0}).ok
    assert not service.material_set("em", "bad", {"relative_permeability": 0, "electric_conductivity_s_per_m": 0}).ok
    assert service.excitation_set("em", "primary_pos", {"current_density_re_a_per_m2": 1, "current_density_im_a_per_m2": 0}).ok
    assert service.excitation_set("em", "primary_neg", {"current_density_re_a_per_m2": -1, "current_density_im_a_per_m2": 0}).ok
    assert service.equation_set(
        "em",
        "magnetodynamics_2d_harmonic_v1",
        {"frequency_hz": 50, "primary_turns": 100, "secondary_turns": 50, "stack_depth_m": 0.02},
    ).ok
    points = np.array([[-0.01, -0.01, 0], [0.01, -0.01, 0], [0.01, 0.01, 0], [-0.01, 0.01, 0]])
    triangles = np.array([[0, 1, 2], [0, 2, 3]])
    a_re = -0.5 * points[:, 0]
    mesh = meshio.Mesh(
        points,
        [("triangle", triangles)],
        point_data={
            "A re": a_re,
            "A im": np.zeros(4),
            "B re": np.tile([0.0, 0.5], (4, 1)),
            "B im": np.zeros((4, 2)),
        },
    )
    path = tmp_path / "em.vtu"
    mesh.write(path)
    state = service._load_state("em")
    inspection = service._inspect_result_file(path, state)
    assert inspection["valid"]
    physics = inspection["physics_acceptance"]
    assert physics["Bmax_T"] == pytest.approx(0.5)
    assert physics["V2_open_rms_V"] > 0
    assert physics["turns_ratio"] == pytest.approx(0.5)


def test_transient_eddy_profile_mesh_sif_and_structured_excitation(tmp_path: Path) -> None:
    assert "magnetodynamics_2d_transient_eddy_v1" in SUPPORTED_PROFILES
    manifest = {
        "objects": [
            {"semantic_id": "air", "bbox_mm": [-80, 80, -60, 60, 0, 0]},
            {"semantic_id": "conductor", "bbox_mm": [-20, 20, -15, 15, 0, 0]},
            {"semantic_id": "coil_pos", "bbox_mm": [-45, -37, -20, 20, 0, 0]},
            {"semantic_id": "coil_neg", "bbox_mm": [37, 45, -20, 20, 0, 0]},
        ]
    }
    geo, body_ids, boundary_ids = gmsh_geo_eddy_2d(
        tmp_path / "model.step",
        tmp_path / "model.msh",
        manifest,
        2.0,
    )
    assert body_ids == {"air": 1, "conductor": 2, "coil_pos": 3, "coil_neg": 4}
    assert boundary_ids == {"outer_boundary": 1001}
    assert 'Physical Surface("conductor", 2)' in geo
    service = ElmerService(OpenCAEConfig(workspace_root=tmp_path / "workspace"))
    assert service.case_create("eddy", "magnetodynamics_2d_transient_eddy_v1").ok
    assert service.equation_set(
        "eddy",
        "magnetodynamics_2d_transient_eddy_v1",
        {
            "time_step_count": 40,
            "time_step_s": 0.0005,
            "quarter_period_s": 0.005,
            "stack_depth_m": 0.02,
            "result_prefix": "lenz",
        },
    ).ok
    assert service.excitation_set(
        "eddy", "coil_pos", {"peak_current_density_a_per_m2": 1.0e6, "direction": 1}
    ).ok
    assert not service.excitation_set(
        "eddy", "bad", {"peak_current_density_a_per_m2": 0, "direction": 1}
    ).ok
    materials = {
        semantic: {
            "name": semantic,
            "relative_permeability": 1,
            "electric_conductivity_s_per_m": 5.8e7 if semantic == "conductor" else 0,
        }
        for semantic in ("air", "conductor", "coil_pos", "coil_neg")
    }
    case = {
        "analysis_type": "magnetodynamics_2d_transient_eddy_v1",
        "materials": materials,
        "excitations": {
            "coil_pos": {"peak_current_density_a_per_m2": 1.0e6, "direction": 1},
            "coil_neg": {"peak_current_density_a_per_m2": 1.0e6, "direction": -1},
        },
        "equation": {
            "settings": {
                "time_step_count": 40,
                "time_step_s": 0.0005,
                "quarter_period_s": 0.005,
                "stack_depth_m": 0.02,
                "result_prefix": "lenz",
            }
        },
    }
    mapping = {
        "dimension": 2,
        "body_ids": body_ids,
        "boundary_ids": {"outer_boundary": [1001]},
    }
    text = generate_magnetodynamics_2d_transient_eddy_sif(case, mapping)
    sif = tmp_path / "eddy.sif"
    sif.write_text(text, encoding="utf-8")
    validation = validate_sif(sif, profile="magnetodynamics_2d_transient_eddy_v1")
    assert validation["valid"]
    assert 'Procedure = "MagnetoDynamics2D" "MagnetoDynamics2D"' in text
    assert "Current Density = Variable Time" in text
    assert "Real MATC" not in text
    assert "0.005 1000000" in text
    assert "0.015 -1000000" in text
    assert "Timestep Intervals = 40" in text


def _elasticity_case() -> dict:
    return {
        "analysis_type": "elasticity_2d_static_v1",
        "materials": {
            "beam": {
                "name": "Structural Steel",
                "youngs_modulus_pa": 210.0e9,
                "poisson_ratio": 0.3,
                "density_kg_per_m3": 7850,
            }
        },
        "equation": {
            "profile": "elasticity_2d_static_v1",
            "settings": {
                "beam_length_m": 1.0,
                "beam_height_m": 0.1,
                "thickness_m": 0.01,
                "load_factor": 1.0,
                "result_prefix": "beam_step_10",
            },
        },
        "boundaries": [
            {"semantic": "left_pin", "displacement_x_m": 0, "displacement_y_m": 0},
            {"semantic": "right_roller", "displacement_y_m": 0},
            {"semantic": "top_load", "traction_y_pa": -1.0e6},
        ],
    }


def test_elasticity_profile_mesh_and_sif(tmp_path: Path) -> None:
    assert "elasticity_2d_static_v1" in SUPPORTED_PROFILES
    manifest = {
        "schema_version": "1.0",
        "units": "mm",
        "objects": [{"semantic_id": "beam", "bbox_mm": [0, 1000, 0, 100, 0, 0]}],
    }
    geo, bodies, boundaries = gmsh_geo_beam_2d(
        tmp_path / "beam.step",
        tmp_path / "beam.msh",
        manifest,
        10,
        coordinate_scale=0.001,
    )
    assert bodies == {"beam": 1}
    assert boundaries["left_pin"] == 1001
    assert boundaries["right_roller"] == 1002
    assert boundaries["top_load"] == 1003
    assert 'Physical Curve("left_pin", 1001)' in geo
    assert 'Physical Curve("top_load", 1003)' in geo

    mapping = {
        "dimension": 2,
        "body_ids": {"beam": 1},
        "boundary_ids": {name: [value] for name, value in boundaries.items()},
    }
    text = generate_elasticity_2d_static_sif(_elasticity_case(), mapping)
    sif = tmp_path / "beam.sif"
    sif.write_text(text, encoding="utf-8")
    validation = validate_sif(sif, profile="elasticity_2d_static_v1")
    assert validation["valid"]
    assert 'Procedure = "StressSolve" "StressSolver"' in text
    assert "Plane Stress = Logical True" in text
    assert "Force 2 = Real -1000000" in text


def test_elasticity_result_derivation_and_gate(tmp_path: Path) -> None:
    config = OpenCAEConfig(workspace_root=tmp_path / "workspace")
    service = ElmerService(config)
    assert service.case_create("beam", "elasticity_2d_static_v1").ok
    assert service.material_set(
        "beam",
        "beam",
        {"youngs_modulus_pa": 210.0e9, "poisson_ratio": 0.3, "density_kg_per_m3": 7850},
    ).ok
    assert service.equation_set(
        "beam",
        "elasticity_2d_static_v1",
        {
            "beam_length_m": 1.0,
            "beam_height_m": 0.1,
            "thickness_m": 0.01,
            "load_factor": 1.0,
            "result_prefix": "beam",
        },
    ).ok
    assert service.boundary_set("beam", {"semantic": "top_load"}, {"traction_y_pa": -1.0e6}).ok
    points = np.array([[0, 0, 0], [1, 0, 0], [1, 0.1, 0], [0, 0.1, 0]], dtype=float)
    triangles = np.array([[0, 1, 2], [0, 2, 3]])
    displacement = np.column_stack((1.0e-4 * points[:, 0], -2.0e-4 * points[:, 1]))
    path = tmp_path / "elastic.vtu"
    meshio.Mesh(points, [("triangle", triangles)], point_data={"displacement": displacement}).write(path)
    backup = service._augment_elasticity_result(path, service._load_state("beam"))
    assert backup.is_file()
    augmented = meshio.read(path)
    assert "strain_xx_derived" in augmented.point_data
    assert "von_mises_derived_pa" in augmented.point_data


def _flow_case() -> dict:
    return {
        "analysis_type": "navier_stokes_2d_steady_v1",
        "materials": {
            "fluid": {
                "name": "Newtonian Fluid",
                "density_kg_per_m3": 1000.0,
                "dynamic_viscosity_pa_s": 0.01,
            }
        },
        "equation": {
            "settings": {
                "channel_length_m": 0.1,
                "channel_height_m": 0.02,
                "mean_velocity_m_per_s": 0.05,
                "result_prefix": "channel_flow",
            }
        },
        "boundaries": [
            {"semantic": "inlet", "mean_velocity_m_per_s": 0.05},
            {"semantic": "outlet", "pressure_pa": 0.0},
            {"semantic": "walls", "velocity_x_m_per_s": 0.0, "velocity_y_m_per_s": 0.0},
        ],
    }


def test_flow_profile_mesh_and_sif(tmp_path: Path) -> None:
    assert "heat_transient_v1" in SUPPORTED_PROFILES
    assert "navier_stokes_2d_steady_v1" in SUPPORTED_PROFILES
    manifest = {
        "schema_version": "1.0",
        "units": "mm",
        "objects": [{"semantic_id": "fluid", "bbox_mm": [0, 100, 0, 20, 0, 0]}],
    }
    geo, bodies, boundaries = gmsh_geo_channel_2d(
        tmp_path / "channel.step",
        tmp_path / "channel.msh",
        manifest,
        2.0,
        coordinate_scale=0.001,
    )
    assert bodies == {"fluid": 1}
    assert boundaries == {"inlet": 1001, "outlet": 1002, "walls": 1003}
    assert 'Physical Curve("walls", 1003) = {1, 3}' in geo
    mapping = {
        "dimension": 2,
        "body_ids": {"fluid": 1},
        "boundary_ids": {name: [value] for name, value in boundaries.items()},
    }
    text = generate_navier_stokes_2d_steady_sif(_flow_case(), mapping)
    sif = tmp_path / "flow.sif"
    sif.write_text(text, encoding="utf-8")
    validation = validate_sif(sif, profile="navier_stokes_2d_steady_v1")
    assert validation["valid"]
    assert 'Procedure = "FlowSolve" "FlowSolver"' in text
    assert "Real MATC" in text
    assert "Pressure = Real 0" in text


def test_flow_result_gate_against_poiseuille_solution(tmp_path: Path) -> None:
    service = ElmerService(OpenCAEConfig(workspace_root=tmp_path / "workspace"))
    assert service.case_create("flow", "navier_stokes_2d_steady_v1").ok
    assert service.material_set(
        "flow",
        "fluid",
        {"density_kg_per_m3": 1000.0, "dynamic_viscosity_pa_s": 0.01},
    ).ok
    assert service.equation_set(
        "flow",
        "navier_stokes_2d_steady_v1",
        {"channel_length_m": 0.1, "channel_height_m": 0.02, "mean_velocity_m_per_s": 0.05},
    ).ok
    x_values = np.asarray([0.0, 0.05, 0.1])
    y_values = np.linspace(0.0, 0.02, 11)
    points = np.asarray([[x, y, 0.0] for x in x_values for y in y_values])
    triangles = []
    width = len(y_values)
    for ix in range(len(x_values) - 1):
        for iy in range(len(y_values) - 1):
            lower_left = ix * width + iy
            lower_right = (ix + 1) * width + iy
            triangles.extend(
                [
                    [lower_left, lower_right, lower_right + 1],
                    [lower_left, lower_right + 1, lower_left + 1],
                ]
            )
    relative_y = points[:, 1] / 0.02
    velocity = np.column_stack((6.0 * 0.05 * relative_y * (1.0 - relative_y), np.zeros(len(points))))
    pressure = 15.0 * (0.1 - points[:, 0])
    path = tmp_path / "flow.vtu"
    meshio.Mesh(
        points,
        [("triangle", np.asarray(triangles))],
        point_data={"velocity": velocity, "pressure": pressure},
    ).write(path)
    inspection = service._inspect_result_file(path, service._load_state("flow"))
    assert inspection["valid"]
    physics = inspection["physics_acceptance"]
    assert physics["reynolds_number"] == pytest.approx(100.0)
    assert physics["profile_relative_l2_error"] < 0.03
    assert physics["pressure_drop_relative_error"] < 1.0e-10
