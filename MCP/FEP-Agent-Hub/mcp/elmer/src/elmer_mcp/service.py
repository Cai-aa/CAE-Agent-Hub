from __future__ import annotations

import math
import os
import re
import shutil
from pathlib import Path
from typing import Any

import meshio
import numpy as np

from open_cae_core import EvidenceRecorder, SafeProcessRunner, ToolResponse, WorkspaceGuard
from open_cae_core.config import OpenCAEConfig
from open_cae_core.jobs import JobStore
from open_cae_core.manifests import read_json, write_json

from .environment import probe_elmer
from .mesh import (
    gmsh_geo,
    gmsh_geo_2d,
    gmsh_geo_beam_2d,
    gmsh_geo_channel_2d,
    gmsh_geo_eddy_2d,
    parse_elmer_mesh,
    write_semantic_map,
)
from .sif import (
    SUPPORTED_PROFILES,
    generate_elasticity_2d_static_sif,
    generate_heat_sif,
    generate_heat_transient_sif,
    generate_magnetodynamics_2d_harmonic_sif,
    generate_magnetodynamics_2d_transient_eddy_sif,
    generate_navier_stokes_2d_steady_sif,
    validate_sif,
)


def _number(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", str(value))
    if not match:
        raise ValueError(f"Expected numeric quantity: {value}")
    return float(match.group(0))


class ElmerService:
    def __init__(self, config: OpenCAEConfig) -> None:
        self.config = config
        self.guard = WorkspaceGuard(config.workspace_root)
        self.runner = SafeProcessRunner()

    def _project(self, project: str) -> Path:
        return self.guard.ensure_project(project)

    def _state_path(self, project: str) -> Path:
        return self._project(project) / "solver" / "case_model.json"

    def _load_state(self, project: str) -> dict[str, Any]:
        path = self._state_path(project)
        if not path.is_file():
            raise FileNotFoundError("Create an Elmer case first")
        return read_json(path)

    def _save_state(self, project: str, state: dict[str, Any]) -> Path:
        return write_json(self._state_path(project), state)

    def environment_probe(self) -> ToolResponse:
        data = probe_elmer(self.config)
        if data["serial_available"] and data["gmsh_available"]:
            return ToolResponse.success("Elmer serial solver, ElmerGrid, and Gmsh are available", data=data)
        return ToolResponse.blocked(
            "Elmer or Gmsh capability is incomplete",
            data=data,
            next_recommended_action="Configure [elmer] and [gmsh] executable paths",
        )

    def case_create(self, project: str, analysis_type: str = "heat_steady_v1", overwrite: bool = False) -> ToolResponse:
        if analysis_type not in SUPPORTED_PROFILES:
            return ToolResponse.blocked(
                f"Unsupported analysis profile: {analysis_type}",
                data={"supported": sorted(SUPPORTED_PROFILES)},
            )
        project_root = self._project(project)
        state_path = self._state_path(project)
        if state_path.exists() and not overwrite:
            return ToolResponse.blocked("Case already exists; set overwrite=true to recreate it")
        state = {
            "schema_version": "1.0",
            "project": project,
            "analysis_type": analysis_type,
            "status": "CASE_CREATED",
            "geometry": {},
            "mesh": {},
            "materials": {},
            "excitations": {},
            "equation": {"profile": analysis_type},
            "boundaries": [],
            "solver": {"mode": "serial"},
        }
        self._save_state(project, state)
        response = ToolResponse.success(
            "Elmer case created",
            data=state,
            artifacts=[self.guard.relative(state_path)],
        )
        EvidenceRecorder(project_root).tool_call("elmer_case_create", {"analysis_type": analysis_type}, response.to_dict())
        return response

    def case_inspect(self, project: str) -> ToolResponse:
        state = self._load_state(project)
        return ToolResponse.success("Elmer case state loaded", data=state, artifacts=[self.guard.relative(self._state_path(project))])

    def geometry_import(
        self,
        project: str,
        step: str = "geometry/model.step",
        manifest: str = "geometry/geometry_manifest.json",
    ) -> ToolResponse:
        project_root = self._project(project)
        step_path = self.guard.resolve(project_root / step, allowed_extensions={".step", ".stp"}, must_exist=True)
        manifest_path = self.guard.resolve(project_root / manifest, allowed_extensions={".json"}, must_exist=True)
        geometry = read_json(manifest_path)
        if geometry.get("schema_version") != "1.0" or not geometry.get("objects"):
            return ToolResponse.failure("geometry_manifest.json is invalid or has no objects")
        state = self._load_state(project)
        state["geometry"] = {
            "step": self.guard.relative(step_path),
            "manifest": self.guard.relative(manifest_path),
            "objects": geometry["objects"],
        }
        state["status"] = "GEOMETRY_READY"
        self._save_state(project, state)
        response = ToolResponse.success(
            "STEP geometry and semantic manifest accepted",
            data=state["geometry"],
            artifacts=[self.guard.relative(step_path), self.guard.relative(manifest_path)],
        )
        EvidenceRecorder(project_root).tool_call("elmer_geometry_import", {"step": step, "manifest": manifest}, response.to_dict())
        return response

    def mesh_generate(
        self,
        project: str,
        global_size_mm: float = 2.0,
        order: int = 1,
        algorithm: str = "default",
        output_format: str = "msh2",
        timeout: float = 300,
        dimension: int = 3,
        coordinate_scale: float = 1.0,
    ) -> ToolResponse:
        if global_size_mm <= 0 or order not in (1, 2):
            return ToolResponse.failure("global_size_mm must be positive and order must be 1 or 2")
        if dimension not in (2, 3):
            return ToolResponse.failure("dimension must be 2 or 3")
        if output_format != "msh2" or algorithm != "default":
            return ToolResponse.blocked("v0.1 supports output_format=msh2 and algorithm=default")
        project_root = self._project(project)
        state = self._load_state(project)
        if state.get("status") not in {"GEOMETRY_READY", "MESH_GENERATED", "MESH_READY"}:
            return ToolResponse.blocked("Geometry must be imported before meshing")
        environment = probe_elmer(self.config)
        gmsh = environment.get("gmsh")
        if not gmsh:
            return ToolResponse.blocked("gmsh.exe is unavailable")
        step_path = self.guard.resolve(state["geometry"]["step"], must_exist=True)
        mesh_dir = project_root / "mesh"
        geo_path = mesh_dir / "model.geo"
        msh_path = mesh_dir / "model.msh"
        physical_body_ids: dict[str, int] = {}
        physical_boundary_ids: dict[str, int] = {}
        if dimension == 2:
            manifest_path = self.guard.resolve(state["geometry"]["manifest"], must_exist=True)
            try:
                if state.get("analysis_type") == "magnetodynamics_2d_harmonic_v1":
                    geo_text, physical_body_ids, physical_boundary_ids = gmsh_geo_2d(
                        step_path,
                        msh_path,
                        read_json(manifest_path),
                        global_size_mm,
                        order,
                        coordinate_scale,
                    )
                elif state.get("analysis_type") == "magnetodynamics_2d_transient_eddy_v1":
                    geo_text, physical_body_ids, physical_boundary_ids = gmsh_geo_eddy_2d(
                        step_path,
                        msh_path,
                        read_json(manifest_path),
                        global_size_mm,
                        order,
                        coordinate_scale,
                    )
                elif state.get("analysis_type") == "elasticity_2d_static_v1":
                    geo_text, physical_body_ids, physical_boundary_ids = gmsh_geo_beam_2d(
                        step_path,
                        msh_path,
                        read_json(manifest_path),
                        global_size_mm,
                        order,
                        coordinate_scale,
                    )
                elif state.get("analysis_type") == "navier_stokes_2d_steady_v1":
                    geo_text, physical_body_ids, physical_boundary_ids = gmsh_geo_channel_2d(
                        step_path,
                        msh_path,
                        read_json(manifest_path),
                        global_size_mm,
                        order,
                        coordinate_scale,
                    )
                else:
                    return ToolResponse.blocked(
                        "The verified dimension=2 mesh path requires an electromagnetic, elasticity, or flow profile"
                    )
            except ValueError as exc:
                return ToolResponse.failure(str(exc))
        else:
            expected_scale = 0.001 if state.get("analysis_type") == "heat_transient_v1" else 1.0
            if not math.isclose(coordinate_scale, expected_scale, rel_tol=0.0, abs_tol=1.0e-12):
                return ToolResponse.blocked(
                    f"The verified 3D {state.get('analysis_type')} profile requires coordinate_scale={expected_scale}"
                )
            geo_text = gmsh_geo(step_path, msh_path, global_size_mm, order, coordinate_scale)
        geo_path.write_text(geo_text, encoding="utf-8")
        evidence = EvidenceRecorder(project_root)
        result = self.runner.run(
            gmsh,
            [str(geo_path), f"-{dimension}", "-format", "msh2", "-o", str(msh_path)],
            cwd=mesh_dir,
            stdout_log=project_root / "evidence" / "logs" / "gmsh.stdout.log",
            stderr_log=project_root / "evidence" / "logs" / "gmsh.stderr.log",
            timeout=timeout,
            evidence=evidence,
        )
        if result.exit_code != 0 or not msh_path.is_file() or msh_path.stat().st_size == 0:
            state["status"] = "MESH_ERROR"
            self._save_state(project, state)
            return ToolResponse.failure("Gmsh failed to generate a non-empty MSH file", data={"process": result.to_dict()})
        state["mesh"] = {
            "gmsh_geo": self.guard.relative(geo_path),
            "msh": self.guard.relative(msh_path),
            "global_size_mm": global_size_mm,
            "order": order,
            "dimension": dimension,
            "coordinate_scale": coordinate_scale,
            "physical_body_ids": physical_body_ids,
            "physical_boundary_ids": physical_boundary_ids,
        }
        state["status"] = "MESH_GENERATED"
        self._save_state(project, state)
        evidence.record_artifacts([geo_path, msh_path])
        response = ToolResponse.success(
            "Gmsh triangular mesh generated" if dimension == 2 else "Gmsh tetrahedral mesh generated",
            data={"process": result.to_dict(), **state["mesh"]},
            artifacts=[self.guard.relative(geo_path), self.guard.relative(msh_path)],
        )
        evidence.tool_call(
            "elmer_mesh_generate",
            {"global_size_mm": global_size_mm, "order": order, "dimension": dimension, "coordinate_scale": coordinate_scale},
            response.to_dict(),
        )
        return response

    def mesh_convert(self, project: str, timeout: float = 180) -> ToolResponse:
        project_root = self._project(project)
        state = self._load_state(project)
        msh_path = self.guard.resolve(state.get("mesh", {}).get("msh", ""), allowed_extensions={".msh"}, must_exist=True)
        environment = probe_elmer(self.config)
        grid = environment.get("elmer_grid")
        if not grid:
            return ToolResponse.blocked("ElmerGrid.exe is unavailable")
        mesh_dir = project_root / "mesh"
        elmer_mesh = mesh_dir / "elmer_mesh"
        evidence = EvidenceRecorder(project_root)
        result = self.runner.run(
            grid,
            ["14", "2", str(msh_path), "-out", str(elmer_mesh), "-autoclean", "-names"],
            cwd=mesh_dir,
            stdout_log=project_root / "evidence" / "logs" / "elmergrid.stdout.log",
            stderr_log=project_root / "evidence" / "logs" / "elmergrid.stderr.log",
            timeout=timeout,
            evidence=evidence,
        )
        header = elmer_mesh / "mesh.header"
        if result.exit_code != 0 or not header.is_file():
            state["status"] = "MESH_ERROR"
            self._save_state(project, state)
            return ToolResponse.failure("ElmerGrid conversion failed", data={"process": result.to_dict()})
        summary = parse_elmer_mesh(elmer_mesh)
        manifest_path = self.guard.resolve(state["geometry"]["manifest"], must_exist=True)
        semantic_path = mesh_dir / "semantic_map.json"
        write_semantic_map(
            semantic_path,
            summary,
            read_json(manifest_path),
            state.get("mesh", {}).get("physical_body_ids") or None,
            state.get("mesh", {}).get("physical_boundary_ids") or None,
        )
        mesh_manifest = mesh_dir / "mesh_manifest.json"
        write_json(mesh_manifest, {"schema_version": "1.0", **summary})
        state["mesh"].update(
            {
                "elmer_mesh": self.guard.relative(elmer_mesh),
                "semantic_map": self.guard.relative(semantic_path),
                "summary": summary,
            }
        )
        semantic = read_json(semantic_path)
        state["status"] = "MESH_READY" if semantic["status"] == "MAPPED" else "SEMANTIC_MAPPING_AMBIGUOUS"
        self._save_state(project, state)
        artifacts = [header, elmer_mesh / "mesh.nodes", elmer_mesh / "mesh.elements", elmer_mesh / "mesh.boundary", semantic_path, mesh_manifest]
        evidence.record_artifacts(artifacts)
        response = ToolResponse.success(
            "Elmer mesh converted and coordinate-based boundary mapping recorded",
            data={"process": result.to_dict(), "summary": summary, "semantic_map": semantic},
            artifacts=[self.guard.relative(path) for path in artifacts],
        )
        if semantic["status"] != "MAPPED":
            response.ok = False
            response.status = "BLOCKED"
            response.summary = "Mesh converted, but semantic body mapping is ambiguous"
        evidence.tool_call("elmer_mesh_convert", {}, response.to_dict())
        return response

    def mesh_inspect(self, project: str) -> ToolResponse:
        project_root = self._project(project)
        mesh_dir = project_root / "mesh" / "elmer_mesh"
        summary = parse_elmer_mesh(mesh_dir)
        return ToolResponse.success(
            "Elmer mesh topology inspected",
            data=summary,
            artifacts=[self.guard.relative(mesh_dir / "mesh.header")],
        )

    def material_set(self, project: str, body: str, material: dict[str, Any]) -> ToolResponse:
        state = self._load_state(project)
        if state.get("analysis_type") in {"heat_steady_v1", "heat_transient_v1"}:
            conductivity = _number(material.get("heat_conductivity", 0))
            if conductivity <= 0:
                return ToolResponse.failure("heat_conductivity must be positive")
            normalized = {"name": material.get("name", "GenericSolid"), "heat_conductivity": conductivity}
            if state.get("analysis_type") == "heat_transient_v1":
                density = _number(material.get("density_kg_per_m3", 0))
                heat_capacity = _number(material.get("heat_capacity_j_per_kg_k", 0))
                if density <= 0 or heat_capacity <= 0:
                    return ToolResponse.failure("Transient heat requires positive density and heat capacity")
                normalized.update(
                    {
                        "density_kg_per_m3": density,
                        "heat_capacity_j_per_kg_k": heat_capacity,
                    }
                )
        elif state.get("analysis_type") in {
            "magnetodynamics_2d_harmonic_v1",
            "magnetodynamics_2d_transient_eddy_v1",
        }:
            permeability = _number(material.get("relative_permeability", 0))
            electric_conductivity = _number(material.get("electric_conductivity_s_per_m", -1))
            if permeability <= 0:
                return ToolResponse.failure("relative_permeability must be positive")
            if electric_conductivity < 0:
                return ToolResponse.failure("electric_conductivity_s_per_m must be non-negative")
            normalized = {
                "name": material.get("name", body),
                "relative_permeability": permeability,
                "electric_conductivity_s_per_m": electric_conductivity,
            }
        elif state.get("analysis_type") == "elasticity_2d_static_v1":
            youngs_modulus = _number(material.get("youngs_modulus_pa", 0))
            poisson_ratio = _number(material.get("poisson_ratio", -1))
            density = _number(material.get("density_kg_per_m3", 0))
            if youngs_modulus <= 0:
                return ToolResponse.failure("youngs_modulus_pa must be positive")
            if not 0 <= poisson_ratio < 0.5:
                return ToolResponse.failure("poisson_ratio must be in [0, 0.5)")
            if density <= 0:
                return ToolResponse.failure("density_kg_per_m3 must be positive")
            normalized = {
                "name": material.get("name", body),
                "youngs_modulus_pa": youngs_modulus,
                "poisson_ratio": poisson_ratio,
                "density_kg_per_m3": density,
            }
        elif state.get("analysis_type") == "navier_stokes_2d_steady_v1":
            density = _number(material.get("density_kg_per_m3", 0))
            viscosity = _number(material.get("dynamic_viscosity_pa_s", 0))
            if density <= 0 or viscosity <= 0:
                return ToolResponse.failure("Fluid density and dynamic viscosity must be positive")
            normalized = {
                "name": material.get("name", body),
                "density_kg_per_m3": density,
                "dynamic_viscosity_pa_s": viscosity,
            }
        else:
            return ToolResponse.blocked("UNKNOWN_SIF_PROFILE", data={"supported": sorted(SUPPORTED_PROFILES)})
        state.setdefault("materials", {})[body] = normalized
        self._save_state(project, state)
        response = ToolResponse.success("Material stored in the structured case model", data={"body": body, "material": normalized})
        EvidenceRecorder(self._project(project)).tool_call("elmer_material_set", {"body": body, "material": material}, response.to_dict())
        return response

    def equation_set(self, project: str, profile: str = "heat_steady_v1", settings: dict[str, Any] | None = None) -> ToolResponse:
        if profile not in SUPPORTED_PROFILES:
            return ToolResponse.blocked("UNKNOWN_SIF_KEYWORD", data={"supported": sorted(SUPPORTED_PROFILES)})
        state = self._load_state(project)
        normalized_settings: dict[str, Any] = {}
        if profile == "magnetodynamics_2d_harmonic_v1":
            raw = settings or {}
            normalized_settings = {
                "frequency_hz": _number(raw.get("frequency_hz", 0)),
                "primary_turns": int(_number(raw.get("primary_turns", 0))),
                "secondary_turns": int(_number(raw.get("secondary_turns", 0))),
                "stack_depth_m": _number(raw.get("stack_depth_m", 0)),
                "flux_line_x_min_m": _number(raw.get("flux_line_x_min_m", -0.01)),
                "flux_line_x_max_m": _number(raw.get("flux_line_x_max_m", 0.01)),
                "flux_line_y_m": _number(raw.get("flux_line_y_m", 0.0)),
                "result_prefix": str(raw.get("result_prefix", "case")),
            }
            if (
                normalized_settings["frequency_hz"] <= 0
                or normalized_settings["primary_turns"] <= 0
                or normalized_settings["secondary_turns"] <= 0
                or normalized_settings["stack_depth_m"] <= 0
                or normalized_settings["flux_line_x_max_m"] <= normalized_settings["flux_line_x_min_m"]
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", normalized_settings["result_prefix"])
            ):
                return ToolResponse.failure("Invalid harmonic frequency, turns, stack depth, or flux line")
        elif profile == "magnetodynamics_2d_transient_eddy_v1":
            raw = settings or {}
            normalized_settings = {
                "time_step_count": int(_number(raw.get("time_step_count", 0))),
                "time_step_s": _number(raw.get("time_step_s", 0)),
                "quarter_period_s": _number(raw.get("quarter_period_s", 0)),
                "stack_depth_m": _number(raw.get("stack_depth_m", 0)),
                "result_prefix": str(raw.get("result_prefix", "lenz_eddy")),
            }
            total_time = normalized_settings["time_step_count"] * normalized_settings["time_step_s"]
            if (
                normalized_settings["time_step_count"] < 8
                or normalized_settings["time_step_count"] > 500
                or normalized_settings["time_step_s"] <= 0
                or normalized_settings["quarter_period_s"] <= 0
                or normalized_settings["stack_depth_m"] <= 0
                or not math.isclose(
                    total_time,
                    4.0 * normalized_settings["quarter_period_s"],
                    rel_tol=0.0,
                    abs_tol=max(1.0e-12, total_time * 1.0e-9),
                )
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", normalized_settings["result_prefix"])
            ):
                return ToolResponse.failure("Invalid transient eddy-current time, depth, or result-prefix settings")
        elif profile == "heat_transient_v1":
            raw = settings or {}
            normalized_settings = {
                "time_step_count": int(_number(raw.get("time_step_count", 0))),
                "time_step_s": _number(raw.get("time_step_s", 0)),
                "initial_temperature_k": _number(raw.get("initial_temperature_k", 0)),
                "characteristic_length_m": _number(raw.get("characteristic_length_m", 0)),
                "result_prefix": str(raw.get("result_prefix", "transient_heat")),
            }
            if (
                normalized_settings["time_step_count"] < 2
                or normalized_settings["time_step_count"] > 500
                or normalized_settings["time_step_s"] <= 0
                or normalized_settings["initial_temperature_k"] <= 0
                or normalized_settings["characteristic_length_m"] <= 0
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", normalized_settings["result_prefix"])
            ):
                return ToolResponse.failure("Invalid transient heat time settings, length, or result prefix")
        elif profile == "elasticity_2d_static_v1":
            raw = settings or {}
            normalized_settings = {
                "beam_length_m": _number(raw.get("beam_length_m", 0)),
                "beam_height_m": _number(raw.get("beam_height_m", 0)),
                "thickness_m": _number(raw.get("thickness_m", 0)),
                "load_factor": _number(raw.get("load_factor", 1.0)),
                "result_prefix": str(raw.get("result_prefix", "case")),
            }
            if (
                normalized_settings["beam_length_m"] <= 0
                or normalized_settings["beam_height_m"] <= 0
                or normalized_settings["thickness_m"] <= 0
                or not 0 < normalized_settings["load_factor"] <= 1
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", normalized_settings["result_prefix"])
            ):
                return ToolResponse.failure("Invalid beam dimensions, load factor, or result prefix")
        elif profile == "navier_stokes_2d_steady_v1":
            raw = settings or {}
            normalized_settings = {
                "channel_length_m": _number(raw.get("channel_length_m", 0)),
                "channel_height_m": _number(raw.get("channel_height_m", 0)),
                "mean_velocity_m_per_s": _number(raw.get("mean_velocity_m_per_s", 0)),
                "result_prefix": str(raw.get("result_prefix", "channel_flow")),
            }
            if (
                normalized_settings["channel_length_m"] <= 0
                or normalized_settings["channel_height_m"] <= 0
                or normalized_settings["mean_velocity_m_per_s"] <= 0
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", normalized_settings["result_prefix"])
            ):
                return ToolResponse.failure("Invalid channel dimensions, mean velocity, or result prefix")
        state["analysis_type"] = profile
        state["equation"] = {"profile": profile, "settings": normalized_settings}
        self._save_state(project, state)
        response = ToolResponse.success("Equation profile selected", data=state["equation"])
        EvidenceRecorder(self._project(project)).tool_call("elmer_equation_set", {"profile": profile, "settings": settings or {}}, response.to_dict())
        return response

    def excitation_set(self, project: str, body: str, excitation: dict[str, Any]) -> ToolResponse:
        state = self._load_state(project)
        if state.get("analysis_type") not in {
            "magnetodynamics_2d_harmonic_v1",
            "magnetodynamics_2d_transient_eddy_v1",
        }:
            return ToolResponse.blocked("Excitations are only available for verified electromagnetic profiles")
        if state.get("analysis_type") == "magnetodynamics_2d_transient_eddy_v1":
            peak = _number(excitation.get("peak_current_density_a_per_m2", 0))
            direction = _number(excitation.get("direction", 0))
            if peak <= 0 or direction not in (-1.0, 1.0):
                return ToolResponse.failure("Transient eddy excitation requires positive peak density and direction +/-1")
            normalized = {
                "peak_current_density_a_per_m2": peak,
                "direction": direction,
                "waveform": "fixed_four_ramp_triangular",
            }
            state.setdefault("excitations", {})[body] = normalized
            self._save_state(project, state)
            response = ToolResponse.success(
                "Structured transient electromagnetic excitation stored",
                data={"body": body, "excitation": normalized},
            )
            EvidenceRecorder(self._project(project)).tool_call(
                "elmer_excitation_set", {"body": body, "excitation": excitation}, response.to_dict()
            )
            return response
        current_re = _number(excitation.get("current_density_re_a_per_m2", 0))
        current_im = _number(excitation.get("current_density_im_a_per_m2", 0))
        if not math.isfinite(current_re) or not math.isfinite(current_im):
            return ToolResponse.failure("Current-density components must be finite")
        normalized = {
            "current_density_re_a_per_m2": current_re,
            "current_density_im_a_per_m2": current_im,
        }
        state.setdefault("excitations", {})[body] = normalized
        self._save_state(project, state)
        response = ToolResponse.success("Electromagnetic body excitation stored", data={"body": body, "excitation": normalized})
        EvidenceRecorder(self._project(project)).tool_call(
            "elmer_excitation_set", {"body": body, "excitation": excitation}, response.to_dict()
        )
        return response

    def boundary_set(self, project: str, selector: dict[str, Any], condition: dict[str, Any]) -> ToolResponse:
        state = self._load_state(project)
        semantic = selector.get("semantic")
        if not semantic:
            axis = str(selector.get("axis", "")).lower()
            side = str(selector.get("side", "")).lower()
            if axis not in {"x", "y", "z"} or side not in {"min", "max"}:
                return ToolResponse.failure("Boundary selector requires semantic or axis/min|max")
            semantic = f"{axis}_{side}"
        if state.get("analysis_type") in {"heat_steady_v1", "heat_transient_v1"}:
            temperature = _number(condition.get("temperature"))
            boundary = {"semantic": semantic, "temperature_k": temperature, "selector": selector}
        elif state.get("analysis_type") == "magnetodynamics_2d_harmonic_v1":
            potential_re = _number(condition.get("potential_re", 0))
            potential_im = _number(condition.get("potential_im", 0))
            if not math.isfinite(potential_re) or not math.isfinite(potential_im):
                return ToolResponse.failure("Potential components must be finite")
            boundary = {
                "semantic": semantic,
                "potential_re": potential_re,
                "potential_im": potential_im,
                "selector": selector,
            }
        elif state.get("analysis_type") == "magnetodynamics_2d_transient_eddy_v1":
            potential = _number(condition.get("potential", 0))
            if not math.isfinite(potential):
                return ToolResponse.failure("Potential must be finite")
            boundary = {"semantic": semantic, "potential": potential, "selector": selector}
        elif state.get("analysis_type") == "elasticity_2d_static_v1":
            allowed = {
                "displacement_x_m",
                "displacement_y_m",
                "traction_x_pa",
                "traction_y_pa",
            }
            selected = {key: _number(condition[key]) for key in allowed if key in condition}
            if not selected or not all(math.isfinite(value) for value in selected.values()):
                return ToolResponse.failure("Elastic boundary requires finite displacement or traction components")
            boundary = {"semantic": semantic, **selected, "selector": selector}
        elif state.get("analysis_type") == "navier_stokes_2d_steady_v1":
            if semantic == "inlet":
                mean_velocity = _number(condition.get("mean_velocity_m_per_s", 0))
                if mean_velocity <= 0 or not math.isfinite(mean_velocity):
                    return ToolResponse.failure("Flow inlet requires a positive finite mean velocity")
                boundary = {
                    "semantic": semantic,
                    "mean_velocity_m_per_s": mean_velocity,
                    "profile": "parabolic",
                    "selector": selector,
                }
            elif semantic == "outlet":
                pressure = _number(condition.get("pressure_pa", 0))
                if not math.isfinite(pressure):
                    return ToolResponse.failure("Flow outlet pressure must be finite")
                boundary = {"semantic": semantic, "pressure_pa": pressure, "selector": selector}
            elif semantic == "walls":
                velocity_x = _number(condition.get("velocity_x_m_per_s", 0))
                velocity_y = _number(condition.get("velocity_y_m_per_s", 0))
                if not math.isfinite(velocity_x) or not math.isfinite(velocity_y):
                    return ToolResponse.failure("Wall velocity components must be finite")
                boundary = {
                    "semantic": semantic,
                    "velocity_x_m_per_s": velocity_x,
                    "velocity_y_m_per_s": velocity_y,
                    "selector": selector,
                }
            else:
                return ToolResponse.failure("The verified flow profile accepts inlet, outlet, and walls boundaries only")
        else:
            return ToolResponse.blocked("UNKNOWN_SIF_PROFILE")
        boundaries = [item for item in state.get("boundaries", []) if item.get("semantic") != semantic]
        boundaries.append(boundary)
        state["boundaries"] = boundaries
        self._save_state(project, state)
        response = ToolResponse.success("Boundary condition stored; actual Elmer IDs remain evidence-backed", data=boundary)
        EvidenceRecorder(self._project(project)).tool_call("elmer_boundary_set", {"selector": selector, "condition": condition}, response.to_dict())
        return response

    def sif_generate(self, project: str) -> ToolResponse:
        project_root = self._project(project)
        state = self._load_state(project)
        semantic_path = project_root / "mesh" / "semantic_map.json"
        if not semantic_path.is_file():
            return ToolResponse.blocked("Mesh semantic_map.json is required")
        semantic_map = read_json(semantic_path)
        if semantic_map.get("status") != "MAPPED":
            return ToolResponse.blocked("SEMANTIC_MAPPING_AMBIGUOUS")
        try:
            if state.get("analysis_type") == "heat_steady_v1":
                sif_text = generate_heat_sif(state, semantic_map)
            elif state.get("analysis_type") == "heat_transient_v1":
                sif_text = generate_heat_transient_sif(state, semantic_map)
            elif state.get("analysis_type") == "magnetodynamics_2d_harmonic_v1":
                sif_text = generate_magnetodynamics_2d_harmonic_sif(state, semantic_map)
            elif state.get("analysis_type") == "magnetodynamics_2d_transient_eddy_v1":
                sif_text = generate_magnetodynamics_2d_transient_eddy_sif(state, semantic_map)
            elif state.get("analysis_type") == "elasticity_2d_static_v1":
                sif_text = generate_elasticity_2d_static_sif(state, semantic_map)
            elif state.get("analysis_type") == "navier_stokes_2d_steady_v1":
                sif_text = generate_navier_stokes_2d_steady_sif(state, semantic_map)
            else:
                return ToolResponse.blocked("UNKNOWN_SIF_PROFILE")
        except ValueError as exc:
            return ToolResponse.failure(str(exc))
        sif_path = project_root / "solver" / "case.sif"
        sif_path.write_text(sif_text, encoding="utf-8", newline="\n")
        state["solver"]["sif"] = self.guard.relative(sif_path)
        state["status"] = "SIF_GENERATED"
        self._save_state(project, state)
        EvidenceRecorder(project_root).record_artifacts([sif_path])
        response = ToolResponse.success("Structured Elmer SIF generated", artifacts=[self.guard.relative(sif_path)])
        EvidenceRecorder(project_root).tool_call("elmer_sif_generate", {}, response.to_dict())
        return response

    def sif_validate(self, project: str) -> ToolResponse:
        project_root = self._project(project)
        sif_path = project_root / "solver" / "case.sif"
        if not sif_path.is_file():
            return ToolResponse.blocked("Generate case.sif first")
        state = self._load_state(project)
        validation = validate_sif(sif_path, profile=state.get("analysis_type"))
        if validation["valid"]:
            state["status"] = "SIF_VALIDATED"
            self._save_state(project, state)
            response = ToolResponse.success("SIF structural validation passed", data=validation, artifacts=[self.guard.relative(sif_path)])
            EvidenceRecorder(project_root).tool_call("elmer_sif_validate", {}, response.to_dict())
            return response
        state["status"] = "SIF_ERROR"
        self._save_state(project, state)
        response = ToolResponse.failure("SIF structural validation failed", data=validation)
        EvidenceRecorder(project_root).tool_call("elmer_sif_validate", {}, response.to_dict())
        return response

    def solver_run(self, project: str, mode: str = "serial", processes: int = 1, timeout: float = 600) -> ToolResponse:
        if mode != "serial":
            return ToolResponse.blocked("v0.1 acceptance runs are serial; MPI requires a separate verified smoke")
        project_root = self._project(project)
        state = self._load_state(project)
        if state.get("status") != "SIF_VALIDATED":
            return ToolResponse.blocked("SIF must pass validation before solver execution")
        environment = probe_elmer(self.config)
        solver = environment.get("elmer_solver")
        if not solver:
            return ToolResponse.blocked("ElmerSolver.exe is unavailable")
        solver_dir = project_root / "solver"
        mesh_workdir = project_root / "mesh"
        log = solver_dir / "solver.log"
        error_log = solver_dir / "solver.err.log"
        jobs = JobStore(project_root / "evidence" / "jobs.json")
        job = jobs.create("elmer_solver", project=project, mode=mode)
        job.status = "RUNNING"
        jobs.save(job)
        state["status"] = "SOLVING"
        self._save_state(project, state)
        bin_dir = str(Path(solver).parent)
        result = self.runner.run(
            solver,
            ["../solver/case.sif"],
            cwd=mesh_workdir,
            stdout_log=log,
            stderr_log=error_log,
            timeout=timeout,
            environment={"ELMER_HOME": str(Path(solver).parent.parent), "PATH": bin_dir + os.pathsep + os.environ.get("PATH", "")},
            evidence=EvidenceRecorder(project_root),
        )
        log_text = "\n".join(
            path.read_text(encoding="utf-8", errors="replace")
            for path in (log, error_log)
            if path.is_file()
        )
        fatal = bool(re.search(r"(?im)(ERROR::|STOP \d+|FATAL|Unknown keyword|Fortran runtime error|Error termination)", log_text))
        completed = bool(re.search(r"(?i)(ALL DONE|SOLVER TOTAL TIME|ElmerSolver: ALL DONE)", log_text))
        result_prefix = str(state.get("equation", {}).get("settings", {}).get("result_prefix", "case"))
        result_candidates = sorted(
            (
                path
                for path in (project_root / "results").glob(f"{result_prefix}*.vtu")
                if "_elmer_raw" not in path.stem
            ),
            key=lambda path: path.stat().st_mtime,
        )
        result_path = result_candidates[-1] if result_candidates else project_root / "results" / f"{result_prefix}.vtu"
        if result.exit_code != 0 or result.timed_out or fatal or not completed or not result_path.is_file() or result_path.stat().st_size == 0:
            state["status"] = "SOLVER_FATAL" if fatal else "RESULT_MISSING"
            self._save_state(project, state)
            job.status = "FAILED"
            job.data.update({"process": result.to_dict(), "fatal": fatal, "result_exists": result_path.exists()})
            jobs.save(job)
            return ToolResponse.failure(
                "Elmer solve did not pass exit/log/artifact gates",
                data={"job_id": job.id, "process": result.to_dict(), "fatal": fatal, "completed_marker": completed},
                evidence=[self.guard.relative(log), self.guard.relative(error_log)],
            )
        raw_result_path = None
        raw_result_paths: list[Path] = []
        if state.get("analysis_type") == "elasticity_2d_static_v1":
            try:
                raw_result_path = self._augment_elasticity_result(result_path, state)
            except Exception as exc:
                state["status"] = "RESULT_INVALID"
                self._save_state(project, state)
                job.status = "FAILED"
                job.data["elasticity_postprocess_error"] = str(exc)
                jobs.save(job)
                return ToolResponse.failure(
                    f"Elasticity result derivation failed: {exc}",
                    artifacts=[self.guard.relative(result_path)],
                )
        if state.get("analysis_type") == "magnetodynamics_2d_transient_eddy_v1":
            try:
                raw_result_paths = self._augment_transient_eddy_sequence(result_candidates, state)
            except Exception as exc:
                state["status"] = "RESULT_INVALID"
                self._save_state(project, state)
                job.status = "FAILED"
                job.data["transient_eddy_postprocess_error"] = str(exc)
                jobs.save(job)
                return ToolResponse.failure(
                    f"Transient eddy-current field derivation failed: {exc}",
                    artifacts=[self.guard.relative(result_path)],
                )
        inspection = self._inspect_result_file(result_path, state)
        if state.get("analysis_type") == "heat_transient_v1":
            transient = self._inspect_transient_heat_sequence(result_candidates, state)
            inspection["physics_acceptance"] = transient
            inspection["time_steps"] = transient.get("time_steps_s", [])
            inspection["valid"] = bool(
                inspection.get("fields")
                and inspection.get("finite")
                and inspection.get("temperature_field")
                and transient.get("pass")
            )
        if state.get("analysis_type") == "magnetodynamics_2d_transient_eddy_v1":
            transient_eddy = self._inspect_transient_eddy_sequence(result_candidates, state)
            inspection["physics_acceptance"] = transient_eddy
            inspection["time_steps"] = [float(row["time_s"]) for row in transient_eddy.get("history", [])]
            inspection["valid"] = bool(
                inspection.get("fields")
                and inspection.get("finite")
                and transient_eddy.get("pass")
            )
        if not inspection["valid"]:
            state["status"] = "RESULT_INVALID"
            self._save_state(project, state)
            job.status = "FAILED"
            job.data["inspection"] = inspection
            jobs.save(job)
            return ToolResponse.failure("VTU result failed finite field validation", data=inspection)
        state["status"] = "RESULT_READY"
        state["result"] = inspection
        self._save_state(project, state)
        job.status = "SUCCEEDED"
        job.data.update({"process": result.to_dict(), "result": self.guard.relative(result_path)})
        jobs.save(job)
        manifest_path = project_root / "results" / "result_manifest.json"
        transient_profiles = {"heat_transient_v1", "magnetodynamics_2d_transient_eddy_v1"}
        manifest_files = result_candidates if state.get("analysis_type") in transient_profiles else [result_path]
        write_json(
            manifest_path,
            {
                "schema_version": "1.0",
                "solver": "Elmer",
                "status": "SOLVED",
                "files": [self.guard.relative(path).split(f"{project}/", 1)[-1] for path in manifest_files],
                "fields": inspection["fields"],
                "time_steps": inspection.get("time_steps", [0.0]),
                "physics_acceptance": inspection.get("physics_acceptance"),
            },
        )
        metrics_suffix = {
            "elasticity_2d_static_v1": "elasticity_metrics",
            "heat_steady_v1": "thermal_metrics",
            "heat_transient_v1": "transient_thermal_metrics",
            "magnetodynamics_2d_harmonic_v1": "induction_metrics",
            "magnetodynamics_2d_transient_eddy_v1": "transient_eddy_metrics",
            "navier_stokes_2d_steady_v1": "flow_metrics",
        }.get(state.get("analysis_type"), "physics_metrics")
        metrics_path = project_root / "post" / f"{result_prefix}_{metrics_suffix}.json"
        if inspection.get("physics_acceptance"):
            write_json(metrics_path, inspection["physics_acceptance"])
        artifacts = [result_path, manifest_path, log, self._state_path(project)]
        if raw_result_path is not None:
            artifacts.append(raw_result_path)
        artifacts.extend(raw_result_paths)
        if metrics_path.is_file():
            artifacts.append(metrics_path)
        EvidenceRecorder(project_root).record_artifacts(artifacts)
        response = ToolResponse.success(
            "Elmer solve passed process, log, VTU, finite-value, and profile physics gates",
            data={"job_id": job.id, "process": result.to_dict(), "inspection": inspection},
            artifacts=[self.guard.relative(path) for path in artifacts],
        )
        EvidenceRecorder(project_root).tool_call("elmer_solver_run", {"mode": mode, "processes": processes}, response.to_dict())
        return response

    def job_status(self, project: str, job_id: str) -> ToolResponse:
        job = JobStore(self._project(project) / "evidence" / "jobs.json").get(job_id)
        if not job:
            return ToolResponse.failure("Unknown job_id")
        return ToolResponse.success("Elmer job status loaded", data={"job_id": job.id, "status": job.status, **job.data})

    def log_inspect(self, project: str, last_n_lines: int = 80) -> ToolResponse:
        log = self._project(project) / "solver" / "solver.log"
        if not log.is_file():
            return ToolResponse.blocked("solver.log does not exist")
        lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
        errors = [line for line in lines if re.search(r"(?i)(ERROR::|FATAL|Unknown keyword|STOP \d+)", line)]
        warnings = [line for line in lines if "warn" in line.lower()]
        return ToolResponse.success(
            "Elmer log inspected",
            data={"errors": errors[-20:], "warnings": warnings[-20:], "tail": lines[-max(1, min(last_n_lines, 500)):], "full_log_path": self.guard.relative(log)},
        )

    @staticmethod
    def _triangle_interpolate(points: np.ndarray, triangles: np.ndarray, values: np.ndarray, xy: tuple[float, float]) -> np.ndarray:
        p0 = points[triangles[:, 0], :2]
        p1 = points[triangles[:, 1], :2]
        p2 = points[triangles[:, 2], :2]
        x, y = xy
        denominator = (p1[:, 1] - p2[:, 1]) * (p0[:, 0] - p2[:, 0]) + (p2[:, 0] - p1[:, 0]) * (p0[:, 1] - p2[:, 1])
        safe = np.abs(denominator) > 1.0e-24
        w0 = np.zeros_like(denominator)
        w1 = np.zeros_like(denominator)
        w0[safe] = ((p1[safe, 1] - p2[safe, 1]) * (x - p2[safe, 0]) + (p2[safe, 0] - p1[safe, 0]) * (y - p2[safe, 1])) / denominator[safe]
        w1[safe] = ((p2[safe, 1] - p0[safe, 1]) * (x - p2[safe, 0]) + (p0[safe, 0] - p2[safe, 0]) * (y - p2[safe, 1])) / denominator[safe]
        w2 = 1.0 - w0 - w1
        candidates = np.flatnonzero(safe & (w0 >= -1.0e-9) & (w1 >= -1.0e-9) & (w2 >= -1.0e-9))
        if not len(candidates):
            raise ValueError(f"Flux sample point is outside the triangular mesh: {xy}")
        index = int(candidates[0])
        node_ids = triangles[index]
        return w0[index] * values[node_ids[0]] + w1[index] * values[node_ids[1]] + w2[index] * values[node_ids[2]]

    @staticmethod
    def _normalized_field(point_data: dict[str, Any], *candidates: str) -> tuple[str | None, np.ndarray | None]:
        normalized = {re.sub(r"[^a-z0-9]", "", name.lower()): name for name in point_data}
        for candidate in candidates:
            actual = normalized.get(re.sub(r"[^a-z0-9]", "", candidate.lower()))
            if actual is not None:
                return actual, np.asarray(point_data[actual], dtype=float)
        return None, None

    def _augment_elasticity_result(self, path: Path, state: dict[str, Any]) -> Path:
        """Add fixed, auditable plane-stress strain/stress arrays derived from Elmer displacement."""
        mesh = meshio.read(path)
        _, displacement = self._normalized_field(mesh.point_data, "displacement")
        if displacement is None or displacement.ndim != 2 or displacement.shape[1] < 2:
            raise ValueError("Elmer displacement vector is missing from the VTU")
        material = state.get("materials", {}).get("beam", {})
        youngs_modulus = float(material.get("youngs_modulus_pa", 0))
        poisson_ratio = float(material.get("poisson_ratio", -1))
        if youngs_modulus <= 0 or not 0 <= poisson_ratio < 0.5:
            raise ValueError("Elastic material is unavailable for strain/stress derivation")

        points = np.asarray(mesh.points, dtype=float)
        nodal_strain = np.zeros((len(points), 3), dtype=float)
        nodal_stress = np.zeros((len(points), 3), dtype=float)
        nodal_count = np.zeros(len(points), dtype=float)
        constitutive = youngs_modulus / (1.0 - poisson_ratio * poisson_ratio)
        shear_modulus = youngs_modulus / (2.0 * (1.0 + poisson_ratio))
        triangle_count = 0
        for block in mesh.cells:
            if not block.type.startswith("triangle"):
                continue
            for triangle in np.asarray(block.data[:, :3], dtype=int):
                coordinates = points[triangle, :2]
                x1, y1 = coordinates[0]
                x2, y2 = coordinates[1]
                x3, y3 = coordinates[2]
                denominator = (x2 - x1) * (y3 - y1) - (x3 - x1) * (y2 - y1)
                if abs(denominator) <= 1.0e-24:
                    raise ValueError("Zero-area triangle encountered in elasticity postprocessing")
                dndx = np.asarray([y2 - y3, y3 - y1, y1 - y2]) / denominator
                dndy = np.asarray([x3 - x2, x1 - x3, x2 - x1]) / denominator
                u = displacement[triangle, 0]
                v = displacement[triangle, 1]
                strain = np.asarray(
                    [
                        float(np.dot(dndx, u)),
                        float(np.dot(dndy, v)),
                        float(np.dot(dndy, u) + np.dot(dndx, v)),
                    ]
                )
                stress = np.asarray(
                    [
                        constitutive * (strain[0] + poisson_ratio * strain[1]),
                        constitutive * (strain[1] + poisson_ratio * strain[0]),
                        shear_modulus * strain[2],
                    ]
                )
                for node_id in triangle:
                    nodal_strain[node_id] += strain
                    nodal_stress[node_id] += stress
                    nodal_count[node_id] += 1.0
                triangle_count += 1
        if triangle_count == 0 or np.any(nodal_count == 0):
            raise ValueError("The VTU does not contain a complete triangular elasticity mesh")
        nodal_strain /= nodal_count[:, None]
        nodal_stress /= nodal_count[:, None]
        von_mises = np.sqrt(
            nodal_stress[:, 0] ** 2
            - nodal_stress[:, 0] * nodal_stress[:, 1]
            + nodal_stress[:, 1] ** 2
            + 3.0 * nodal_stress[:, 2] ** 2
        )
        mean_strain = 0.5 * (nodal_strain[:, 0] + nodal_strain[:, 1])
        radius = np.sqrt(
            (0.5 * (nodal_strain[:, 0] - nodal_strain[:, 1])) ** 2
            + (0.5 * nodal_strain[:, 2]) ** 2
        )
        mesh.point_data["displacement_vector_derived"] = np.column_stack(
            (displacement[:, 0], displacement[:, 1], np.zeros(len(displacement)))
        )
        mesh.point_data["displacement_magnitude"] = np.linalg.norm(displacement[:, :2], axis=1)
        mesh.point_data["strain_plane_derived"] = nodal_strain
        mesh.point_data["strain_xx_derived"] = nodal_strain[:, 0]
        mesh.point_data["strain_yy_derived"] = nodal_strain[:, 1]
        mesh.point_data["engineering_shear_strain_xy_derived"] = nodal_strain[:, 2]
        mesh.point_data["max_principal_strain_derived"] = mean_strain + radius
        mesh.point_data["stress_plane_derived_pa"] = nodal_stress
        mesh.point_data["stress_xx_derived_pa"] = nodal_stress[:, 0]
        mesh.point_data["stress_yy_derived_pa"] = nodal_stress[:, 1]
        mesh.point_data["stress_xy_derived_pa"] = nodal_stress[:, 2]
        mesh.point_data["von_mises_derived_pa"] = von_mises
        backup = path.with_name(f"{path.stem}_elmer_raw.vtu")
        shutil.copy2(path, backup)
        meshio.write(path, mesh, file_format="vtu", binary=True)
        return backup

    def _inspect_transient_heat_sequence(self, paths: list[Path], state: dict[str, Any]) -> dict[str, Any]:
        settings = state.get("equation", {}).get("settings", {})
        expected_steps = int(settings.get("time_step_count", 0))
        time_step = float(settings.get("time_step_s", 0))
        length = float(settings.get("characteristic_length_m", 0))
        initial_temperature = float(settings.get("initial_temperature_k", 0))
        material = state.get("materials", {}).get("solid", {})
        conductivity = float(material.get("heat_conductivity", 0))
        density = float(material.get("density_kg_per_m3", 0))
        heat_capacity = float(material.get("heat_capacity_j_per_kg_k", 0))
        diffusivity = conductivity / (density * heat_capacity) if density > 0 and heat_capacity > 0 else 0.0
        indexed: list[tuple[int, Path]] = []
        for path in paths:
            match = re.search(r"_t(\d+)$", path.stem)
            if match:
                indexed.append((int(match.group(1)), path))
        indexed.sort(key=lambda item: item[0])
        history = []
        all_finite = True
        for step_index, path in indexed:
            mesh = meshio.read(path)
            _, temperature = self._normalized_field(mesh.point_data, "temperature")
            if temperature is None:
                all_finite = False
                continue
            values = temperature.reshape(-1)
            points = np.asarray(mesh.points, dtype=float)
            midpoint = 0.5 * (float(points[:, 0].min()) + float(points[:, 0].max()))
            distance = np.abs(points[:, 0] - midpoint)
            threshold = max(float(distance.min()) + 1.0e-9, length * 0.05)
            mid_values = values[distance <= threshold]
            finite = bool(np.isfinite(values).all() and len(mid_values))
            all_finite = all_finite and finite
            history.append(
                {
                    "step": step_index,
                    "time_s": step_index * time_step,
                    "Tmin_K": float(np.min(values)),
                    "Tmax_K": float(np.max(values)),
                    "Tmid_K": float(np.mean(mid_values)) if len(mid_values) else float("nan"),
                    "file": path.name,
                }
            )
        boundaries = {str(item.get("semantic")): float(item["temperature_k"]) for item in state.get("boundaries", [])}
        hot = boundaries.get("x_min", max(boundaries.values(), default=400.0))
        cold = boundaries.get("x_max", min(boundaries.values(), default=300.0))
        final_time = expected_steps * time_step
        theta = 0.5
        if diffusivity > 0 and length > 0 and final_time > 0:
            series = sum(
                math.sin(index * math.pi * 0.5)
                / index
                * math.exp(-diffusivity * index * index * math.pi * math.pi * final_time / (length * length))
                for index in range(1, 201)
            )
            theta -= 2.0 * series / math.pi
        analytical_midpoint = cold + (hot - cold) * theta
        midpoints = [float(item["Tmid_K"]) for item in history]
        monotonic = bool(midpoints) and all(
            current + 1.0e-5 >= previous for previous, current in zip(midpoints, midpoints[1:])
        )
        final_midpoint = midpoints[-1] if midpoints else float("nan")
        analytical_error = abs(final_midpoint - analytical_midpoint)
        complete = len(indexed) == expected_steps and [item[0] for item in indexed] == list(range(1, expected_steps + 1))
        result = {
            "time_step_count": expected_steps,
            "validated_file_count": len(indexed),
            "time_step_s": time_step,
            "final_time_s": final_time,
            "thermal_diffusivity_m2_per_s": diffusivity,
            "initial_temperature_K": initial_temperature,
            "hot_boundary_K": hot,
            "cold_boundary_K": cold,
            "final_midpoint_temperature_K": final_midpoint,
            "analytical_midpoint_temperature_K": analytical_midpoint,
            "analytical_absolute_error_K": analytical_error,
            "midpoint_monotonic_heating": monotonic,
            "finite": all_finite,
            "time_steps_s": [item["time_s"] for item in history],
            "history": history,
        }
        result["pass"] = bool(
            complete
            and all_finite
            and monotonic
            and midpoints
            and final_midpoint > initial_temperature + 5.0
            and analytical_error <= 3.0
            and all(cold - 1.0 <= item["Tmin_K"] <= item["Tmax_K"] <= hot + 1.0 for item in history)
        )
        result["criteria"] = {
            "sequence": f"exactly {expected_steps} finite VTU time steps",
            "bounds": "all temperatures remain within imposed boundaries +/- 1 K",
            "process": "midpoint temperature is monotonic and rises by more than 5 K",
            "analytical": "final 1D Fourier-series midpoint absolute error <= 3 K",
        }
        return result

    @staticmethod
    def _triangular_excitation_value(time_s: float, peak: float, quarter_s: float) -> float:
        total = 4.0 * quarter_s
        time_s = min(total, max(0.0, time_s))
        if time_s <= quarter_s:
            return peak * time_s / quarter_s
        if time_s <= 2.0 * quarter_s:
            return peak * (2.0 * quarter_s - time_s) / quarter_s
        if time_s <= 3.0 * quarter_s:
            return -peak * (time_s - 2.0 * quarter_s) / quarter_s
        return peak * (time_s - total) / quarter_s

    @staticmethod
    def _triangle_blocks_with_geometry(mesh: meshio.Mesh) -> list[tuple[np.ndarray, np.ndarray]]:
        geometry_ids = mesh.cell_data.get("GeometryIds", [])
        records: list[tuple[np.ndarray, np.ndarray]] = []
        for block_index, block in enumerate(mesh.cells):
            if not block.type.startswith("triangle"):
                continue
            triangles = np.asarray(block.data[:, :3], dtype=int)
            if block_index < len(geometry_ids):
                ids = np.asarray(geometry_ids[block_index], dtype=int).reshape(-1)
            else:
                ids = np.zeros(len(triangles), dtype=int)
            records.append((triangles, ids))
        return records

    def _augment_transient_eddy_sequence(
        self,
        paths: list[Path],
        state: dict[str, Any],
    ) -> list[Path]:
        settings = state.get("equation", {}).get("settings", {})
        dt = float(settings.get("time_step_s", 0))
        quarter = float(settings.get("quarter_period_s", 0))
        if dt <= 0 or quarter <= 0:
            raise ValueError("Transient eddy-current time settings are invalid")
        body_ids = state.get("mesh", {}).get("physical_body_ids", {})
        conductor_id = int(body_ids.get("conductor", 0))
        coil_pos_id = int(body_ids.get("coil_pos", 0))
        coil_neg_id = int(body_ids.get("coil_neg", 0))
        conductivity = float(
            state.get("materials", {}).get("conductor", {}).get("electric_conductivity_s_per_m", 0)
        )
        if not conductor_id or not coil_pos_id or not coil_neg_id or conductivity <= 0:
            raise ValueError("Transient eddy-current body mapping or conductor material is invalid")
        excitations = state.get("excitations", {})
        positive = excitations.get("coil_pos", {})
        negative = excitations.get("coil_neg", {})
        peak = float(positive.get("peak_current_density_a_per_m2", 0))
        if peak <= 0 or float(positive.get("direction", 0)) != 1.0 or float(negative.get("direction", 0)) != -1.0:
            raise ValueError("Transient eddy-current profile requires opposite +/- coil excitations")
        previous_potential: np.ndarray | None = None
        raw_paths: list[Path] = []
        for step_index, path in enumerate(sorted(paths), start=1):
            mesh = meshio.read(path)
            potential_name, potential = self._normalized_field(mesh.point_data, "potential", "az", "a")
            if potential_name is None or potential is None:
                raise ValueError(f"Potential field is missing from {path.name}")
            potential = np.asarray(potential, dtype=float).reshape(-1)
            if previous_potential is None:
                previous_potential = np.zeros_like(potential)
            if potential.shape != previous_potential.shape:
                raise ValueError("Transient eddy-current result meshes are inconsistent")
            points = np.asarray(mesh.points, dtype=float)
            triangles_by_body = self._triangle_blocks_with_geometry(mesh)
            conductor_nodes: set[int] = set()
            coil_pos_nodes: set[int] = set()
            coil_neg_nodes: set[int] = set()
            magnetic_sum = np.zeros((len(points), 3), dtype=float)
            magnetic_weight = np.zeros(len(points), dtype=float)
            for triangles, ids in triangles_by_body:
                for triangle, geometry_id in zip(triangles, ids, strict=True):
                    selected = points[triangle, :2]
                    x0, y0 = selected[0]
                    x1, y1 = selected[1]
                    x2, y2 = selected[2]
                    twice_area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
                    area = 0.5 * abs(twice_area)
                    if area <= 0:
                        continue
                    values = potential[triangle]
                    d_a_dx = (
                        values[0] * (y1 - y2)
                        + values[1] * (y2 - y0)
                        + values[2] * (y0 - y1)
                    ) / twice_area
                    d_a_dy = (
                        values[0] * (x2 - x1)
                        + values[1] * (x0 - x2)
                        + values[2] * (x1 - x0)
                    ) / twice_area
                    magnetic = np.array([d_a_dy, -d_a_dx, 0.0], dtype=float)
                    magnetic_sum[triangle] += area * magnetic
                    magnetic_weight[triangle] += area
                    if int(geometry_id) == conductor_id:
                        conductor_nodes.update(int(value) for value in triangle)
                    elif int(geometry_id) == coil_pos_id:
                        coil_pos_nodes.update(int(value) for value in triangle)
                    elif int(geometry_id) == coil_neg_id:
                        coil_neg_nodes.update(int(value) for value in triangle)
            nonzero = magnetic_weight > 0
            magnetic_field = np.zeros((len(points), 3), dtype=float)
            magnetic_field[nonzero] = magnetic_sum[nonzero] / magnetic_weight[nonzero, None]
            electric_field = np.zeros(len(points), dtype=float)
            eddy_current = np.zeros(len(points), dtype=float)
            conductor_index = np.asarray(sorted(conductor_nodes), dtype=int)
            electric_field[conductor_index] = -(
                potential[conductor_index] - previous_potential[conductor_index]
            ) / dt
            eddy_current[conductor_index] = conductivity * electric_field[conductor_index]
            joule = np.zeros(len(points), dtype=float)
            joule[conductor_index] = eddy_current[conductor_index] ** 2 / conductivity
            source_current = np.zeros(len(points), dtype=float)
            time_s = step_index * dt
            amplitude = self._triangular_excitation_value(time_s, peak, quarter)
            source_current[np.asarray(sorted(coil_pos_nodes), dtype=int)] = amplitude
            source_current[np.asarray(sorted(coil_neg_nodes), dtype=int)] = -amplitude
            eddy_vector = np.zeros((len(points), 3), dtype=float)
            eddy_vector[:, 2] = eddy_current
            mesh.point_data["magnetic_flux_density_derived_t"] = magnetic_field
            mesh.point_data["electric_field_z_derived_v_per_m"] = electric_field
            mesh.point_data["eddy_current_density_z_derived_a_per_m2"] = eddy_current
            mesh.point_data["eddy_current_density_vector_derived_a_per_m2"] = eddy_vector
            mesh.point_data["source_current_density_z_derived_a_per_m2"] = source_current
            mesh.point_data["joule_power_density_derived_w_per_m3"] = joule
            raw_path = path.with_name(f"{path.stem}_elmer_raw.vtu")
            if not raw_path.is_file():
                shutil.copy2(path, raw_path)
            meshio.write(path, mesh, file_format="vtu", binary=True)
            raw_paths.append(raw_path)
            previous_potential = potential.copy()
        return raw_paths

    def _inspect_transient_eddy_sequence(
        self,
        paths: list[Path],
        state: dict[str, Any],
    ) -> dict[str, Any]:
        settings = state.get("equation", {}).get("settings", {})
        expected = int(settings.get("time_step_count", 0))
        dt = float(settings.get("time_step_s", 0))
        quarter = float(settings.get("quarter_period_s", 0))
        depth = float(settings.get("stack_depth_m", 0))
        body_ids = state.get("mesh", {}).get("physical_body_ids", {})
        conductor_id = int(body_ids.get("conductor", 0))
        coil_pos_id = int(body_ids.get("coil_pos", 0))
        coil_neg_id = int(body_ids.get("coil_neg", 0))
        conductivity = float(state.get("materials", {}).get("conductor", {}).get("electric_conductivity_s_per_m", 0))
        peak = float(state.get("excitations", {}).get("coil_pos", {}).get("peak_current_density_a_per_m2", 0))
        history: list[dict[str, Any]] = []
        finite = True
        source_moment_per_density = None
        for step_index, path in enumerate(sorted(paths), start=1):
            mesh = meshio.read(path)
            _, eddy = self._normalized_field(mesh.point_data, "eddy_current_density_z_derived_a_per_m2")
            _, magnetic = self._normalized_field(mesh.point_data, "magnetic_flux_density_derived_t")
            _, joule = self._normalized_field(mesh.point_data, "joule_power_density_derived_w_per_m3")
            if eddy is None or magnetic is None or joule is None:
                return {"pass": False, "finite": False, "error": f"Derived eddy fields missing: {path.name}"}
            eddy = np.asarray(eddy, dtype=float).reshape(-1)
            magnetic = np.asarray(magnetic, dtype=float)
            joule = np.asarray(joule, dtype=float).reshape(-1)
            points = np.asarray(mesh.points, dtype=float)
            induced_moment = 0.0
            source_unit_moment = 0.0
            joule_power = 0.0
            conductor_values: list[float] = []
            conductor_b: list[float] = []
            for triangles, ids in self._triangle_blocks_with_geometry(mesh):
                for triangle, geometry_id in zip(triangles, ids, strict=True):
                    selected = points[triangle, :2]
                    edge_1 = selected[1] - selected[0]
                    edge_2 = selected[2] - selected[0]
                    area = 0.5 * abs(edge_1[0] * edge_2[1] - edge_1[1] * edge_2[0])
                    if area <= 0:
                        continue
                    center_x = float(np.mean(selected[:, 0]))
                    body_id = int(geometry_id)
                    if body_id == conductor_id:
                        local_j = float(np.mean(eddy[triangle]))
                        induced_moment += -0.5 * depth * center_x * local_j * area
                        joule_power += depth * float(np.mean(joule[triangle])) * area
                        conductor_values.extend(float(value) for value in eddy[triangle])
                        if magnetic.ndim == 2:
                            conductor_b.extend(float(np.linalg.norm(value[:2])) for value in magnetic[triangle])
                    elif body_id == coil_pos_id:
                        source_unit_moment += -0.5 * depth * center_x * area
                    elif body_id == coil_neg_id:
                        source_unit_moment += 0.5 * depth * center_x * area
            if source_moment_per_density is None:
                source_moment_per_density = source_unit_moment
            time_s = step_index * dt
            amplitude = self._triangular_excitation_value(time_s, peak, quarter)
            previous_time = max(0.0, time_s - dt)
            previous_amplitude = self._triangular_excitation_value(previous_time, peak, quarter)
            source_moment_rate = source_unit_moment * (amplitude - previous_amplitude) / dt
            values = np.asarray(conductor_values, dtype=float)
            b_values = np.asarray(conductor_b, dtype=float)
            step_finite = bool(
                values.size
                and b_values.size
                and np.isfinite(values).all()
                and np.isfinite(b_values).all()
                and math.isfinite(induced_moment)
                and math.isfinite(joule_power)
            )
            finite = finite and step_finite
            history.append(
                {
                    "step": step_index,
                    "time_s": time_s,
                    "source_current_density_a_per_m2": amplitude,
                    "source_moment_rate_a_m2_per_s": source_moment_rate,
                    "induced_moment_a_m2": induced_moment,
                    "total_moment_rate_product": induced_moment * source_moment_rate,
                    "eddy_current_min_a_per_m2": float(np.min(values)) if values.size else None,
                    "eddy_current_max_a_per_m2": float(np.max(values)) if values.size else None,
                    "eddy_current_rms_a_per_m2": float(np.sqrt(np.mean(values**2))) if values.size else None,
                    "conductor_b_mean_t": float(np.mean(b_values)) if b_values.size else None,
                    "joule_power_w": joule_power,
                    "finite": step_finite,
                    "file": path.name,
                }
            )
        steps_per_quarter = max(1, int(round(quarter / dt)))
        for row in history:
            step = int(row["step"])
            ramp_index = min(3, (step - 1) // steps_per_quarter)
            if ramp_index == 0:
                ramp_start_moment = 0.0
            else:
                ramp_start_step = ramp_index * steps_per_quarter
                ramp_start_moment = float(history[ramp_start_step - 1]["induced_moment_a_m2"])
            incremental_moment = float(row["induced_moment_a_m2"]) - ramp_start_moment
            row["ramp_index"] = ramp_index + 1
            row["ramp_start_induced_moment_a_m2"] = ramp_start_moment
            row["incremental_induced_moment_a_m2"] = incremental_moment
            row["lenz_incremental_product"] = incremental_moment * float(
                row["source_moment_rate_a_m2_per_s"]
            )
        representative_times = [0.5 * quarter, 1.5 * quarter, 2.5 * quarter, 3.5 * quarter]
        representative = [min(history, key=lambda row: abs(float(row["time_s"]) - target)) for target in representative_times]
        lenz_sign_passes = [bool(float(row["lenz_incremental_product"]) < 0) for row in representative]
        all_rms = [float(row["eddy_current_rms_a_per_m2"] or 0) for row in history]
        all_power = [float(row["joule_power_w"] or 0) for row in history]
        energy = float(np.trapezoid(np.asarray(all_power), dx=dt)) if len(all_power) > 1 else 0.0
        induced_signs = {
            int(math.copysign(1, float(row["incremental_induced_moment_a_m2"])))
            for row in representative
            if float(row["incremental_induced_moment_a_m2"]) != 0
        }
        reversal_delays: list[dict[str, Any]] = []
        for ramp_index in range(4):
            ramp_rows = history[
                ramp_index * steps_per_quarter : min((ramp_index + 1) * steps_per_quarter, len(history))
            ]
            first_opposing = next(
                (row for row in ramp_rows if float(row["total_moment_rate_product"]) < 0),
                None,
            )
            reversal_delays.append(
                {
                    "ramp": ramp_index + 1,
                    "total_moment_opposition_delay_s": (
                        float(first_opposing["time_s"]) - ramp_index * quarter
                        if first_opposing is not None
                        else None
                    ),
                    "total_moment_opposed_before_ramp_end": first_opposing is not None,
                }
            )
        result = {
            "time_step_count": expected,
            "validated_file_count": len(paths),
            "time_step_s": dt,
            "final_time_s": expected * dt,
            "quarter_period_s": quarter,
            "conductor_conductivity_s_per_m": conductivity,
            "source_peak_current_density_a_per_m2": peak,
            "source_moment_per_current_density_m4": source_moment_per_density,
            "peak_eddy_current_rms_a_per_m2": max(all_rms, default=0.0),
            "joule_energy_j": energy,
            "representative_lenz_steps": representative,
            "lenz_sign_passes": lenz_sign_passes,
            "incremental_direction_reversal": len(induced_signs) == 2,
            "total_moment_reversal_delays": reversal_delays,
            "finite": finite,
            "history": history,
        }
        result["pass"] = bool(
            len(paths) == expected
            and finite
            and result["peak_eddy_current_rms_a_per_m2"] > 1.0
            and energy > 0
            and all(lenz_sign_passes)
            and result["incremental_direction_reversal"]
        )
        result["criteria"] = {
            "sequence": f"exactly {expected} finite transient VTU steps",
            "eddy_current": "finite conductor RMS eddy current > 1 A/m2",
            "lenz_sign": "ramp-incremental induced moment * source-moment rate < 0 at all four mid-ramp checkpoints",
            "direction": "ramp-incremental induced moment reverses with source-moment rate; total-moment lag is reported separately",
            "joule": "time-integrated non-negative Joule power is finite and non-zero",
        }
        return result

    def _inspect_steady_channel_flow(self, mesh: meshio.Mesh, state: dict[str, Any]) -> dict[str, Any] | None:
        velocity_name, velocity = self._normalized_field(mesh.point_data, "velocity")
        pressure_name, pressure = self._normalized_field(mesh.point_data, "pressure")
        if velocity is None or pressure is None or velocity.ndim != 2 or velocity.shape[1] < 2:
            return None
        points = np.asarray(mesh.points, dtype=float)
        pressure = pressure.reshape(-1)
        triangles = [np.asarray(block.data[:, :3], dtype=int) for block in mesh.cells if block.type.startswith("triangle")]
        if not triangles:
            return None
        triangle_array = np.concatenate(triangles, axis=0)
        settings = state.get("equation", {}).get("settings", {})
        length = float(settings.get("channel_length_m", points[:, 0].max() - points[:, 0].min()))
        height = float(settings.get("channel_height_m", points[:, 1].max() - points[:, 1].min()))
        target_mean = float(settings.get("mean_velocity_m_per_s", 0))
        material = state.get("materials", {}).get("fluid", {})
        density = float(material.get("density_kg_per_m3", 0))
        viscosity = float(material.get("dynamic_viscosity_pa_s", 0))
        x_min = float(points[:, 0].min())
        x_max = float(points[:, 0].max())
        y_min = float(points[:, 1].min())
        y_max = float(points[:, 1].max())
        x_mid = 0.5 * (x_min + x_max)
        sample_y = np.linspace(y_min, y_max, 81)
        sampled_velocity = np.asarray(
            [self._triangle_interpolate(points, triangle_array, velocity, (x_mid, float(y))) for y in sample_y]
        )
        sampled_u = sampled_velocity[:, 0]
        relative_y = (sample_y - y_min) / height
        analytical_u = 6.0 * target_mean * relative_y * (1.0 - relative_y)
        mean_velocity = float(np.trapezoid(sampled_u, sample_y) / height)
        profile_relative_l2 = float(np.linalg.norm(sampled_u - analytical_u) / np.linalg.norm(analytical_u))
        speed = np.linalg.norm(velocity[:, :2], axis=1)
        wall_mask = np.isclose(points[:, 1], y_min, atol=max(height * 1.0e-7, 1.0e-10)) | np.isclose(
            points[:, 1], y_max, atol=max(height * 1.0e-7, 1.0e-10)
        )
        wall_speed_max = float(np.max(speed[wall_mask])) if np.any(wall_mask) else float("inf")
        x_left = x_min + 0.1 * length
        x_right = x_max - 0.1 * length
        pressure_y = np.linspace(y_min + 0.05 * height, y_max - 0.05 * height, 31)
        pressure_left = np.asarray(
            [self._triangle_interpolate(points, triangle_array, pressure, (x_left, float(y))) for y in pressure_y]
        )
        pressure_right = np.asarray(
            [self._triangle_interpolate(points, triangle_array, pressure, (x_right, float(y))) for y in pressure_y]
        )
        pressure_drop = float(np.mean(pressure_left) - np.mean(pressure_right))
        analytical_gradient = 12.0 * viscosity * target_mean / (height * height)
        analytical_drop = analytical_gradient * (x_right - x_left)
        mean_error = abs(mean_velocity - target_mean) / target_mean
        max_speed = float(np.max(speed))
        max_speed_error = abs(max_speed - 1.5 * target_mean) / (1.5 * target_mean)
        pressure_error = abs(pressure_drop - analytical_drop) / analytical_drop if analytical_drop > 0 else float("inf")
        reynolds = density * target_mean * height / viscosity if viscosity > 0 else float("inf")
        result = {
            "velocity_field": velocity_name,
            "pressure_field": pressure_name,
            "target_mean_velocity_m_per_s": target_mean,
            "measured_mean_velocity_m_per_s": mean_velocity,
            "mean_velocity_relative_error": mean_error,
            "max_velocity_m_per_s": max_speed,
            "analytical_max_velocity_m_per_s": 1.5 * target_mean,
            "max_velocity_relative_error": max_speed_error,
            "profile_relative_l2_error": profile_relative_l2,
            "wall_speed_max_m_per_s": wall_speed_max,
            "pressure_drop_10_to_90_percent_pa": pressure_drop,
            "analytical_pressure_drop_10_to_90_percent_pa": analytical_drop,
            "pressure_drop_relative_error": pressure_error,
            "reynolds_number": reynolds,
            "flow_rate_per_unit_depth_m2_per_s": mean_velocity * height,
            "finite": bool(np.isfinite(velocity).all() and np.isfinite(pressure).all()),
        }
        result["pass"] = bool(
            result["finite"]
            and 0 < reynolds <= 200
            and mean_error <= 0.05
            and max_speed_error <= 0.05
            and profile_relative_l2 <= 0.08
            and wall_speed_max <= max(target_mean * 1.0e-6, 1.0e-10)
            and pressure_error <= 0.15
        )
        result["criteria"] = {
            "regime": "0 < Re <= 200",
            "mean_velocity": "relative error <= 5%",
            "maximum_velocity": "relative error from 1.5*Umean <= 5%",
            "profile": "Poiseuille profile relative L2 error <= 8%",
            "walls": "no-slip residual <= 1e-6*Umean",
            "pressure_drop": "relative error <= 15%",
        }
        return result

    def _inspect_result_file(self, path: Path, state: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            mesh = meshio.read(path)
        except Exception as exc:
            return {"valid": False, "error": str(exc), "fields": []}
        state = state or {}
        fields = []
        finite = True
        temperature_name = None
        temperature_values = None
        for name, values in mesh.point_data.items():
            array = np.asarray(values)
            if array.size == 0:
                finite = False
                continue
            field_finite = bool(np.isfinite(array).all())
            finite = finite and field_finite
            fields.append(
                {
                    "name": name,
                    "association": "POINTS",
                    "components": 1 if array.ndim == 1 else int(array.shape[-1]),
                    "unit": "K" if name.lower() == "temperature" else None,
                    "minimum": float(np.nanmin(array)),
                    "maximum": float(np.nanmax(array)),
                    "finite": field_finite,
                }
            )
            if name.lower() == "temperature":
                temperature_name = name
                temperature_values = array.reshape(-1)
        for name, blocks in mesh.cell_data.items():
            arrays = [np.asarray(values) for values in blocks if np.asarray(values).size]
            if not arrays:
                continue
            array = np.concatenate(arrays, axis=0)
            field_finite = bool(np.isfinite(array).all())
            finite = finite and field_finite
            fields.append(
                {
                    "name": name,
                    "association": "CELLS",
                    "components": 1 if array.ndim == 1 else int(array.shape[-1]),
                    "unit": None,
                    "minimum": float(np.nanmin(array)),
                    "maximum": float(np.nanmax(array)),
                    "finite": field_finite,
                }
            )
        analysis_type = state.get("analysis_type", "heat_steady_v1")
        physics = None
        if temperature_values is not None:
            points = np.asarray(mesh.points)
            midpoint = (float(points[:, 0].min()) + float(points[:, 0].max())) / 2.0
            distance = np.abs(points[:, 0] - midpoint)
            threshold = max(float(distance.min()) + 1e-9, (float(points[:, 0].max()) - float(points[:, 0].min())) * 0.05)
            mid_values = temperature_values[distance <= threshold]
            tmin = float(np.min(temperature_values))
            tmax = float(np.max(temperature_values))
            tmid = float(np.mean(mid_values)) if len(mid_values) else float("nan")
            if analysis_type == "heat_transient_v1":
                settings = state.get("equation", {}).get("settings", {})
                initial_temperature = float(settings.get("initial_temperature_k", 300.0))
                boundary_temperatures = [float(item["temperature_k"]) for item in state.get("boundaries", [])]
                lower = min(boundary_temperatures) if boundary_temperatures else initial_temperature
                upper = max(boundary_temperatures) if boundary_temperatures else initial_temperature
                physics = {
                    "Tmin_K": tmin,
                    "Tmax_K": tmax,
                    "Tmid_K": tmid,
                    "initial_temperature_K": initial_temperature,
                    "pass": bool(
                        lower - 1.0 <= tmin <= lower + 1.0
                        and upper - 1.0 <= tmax <= upper + 1.0
                        and initial_temperature < tmid < upper
                    ),
                    "criteria": {
                        "bounds": "temperature remains inside imposed Dirichlet limits +/- 1 K",
                        "midpoint": "final midpoint rises above the initial temperature and remains below the hot boundary",
                    },
                }
            else:
                physics = {
                    "Tmin_K": tmin,
                    "Tmax_K": tmax,
                    "Tmid_K": tmid,
                    "pass": abs(tmin - 300.0) < 1.0 and abs(tmax - 400.0) < 1.0 and abs(tmid - 350.0) < 3.0,
                    "criteria": {"Tmin": "300 +/- 1 K", "Tmax": "400 +/- 1 K", "Tmid": "350 +/- 3 K"},
                }
        fluid = None
        if analysis_type == "navier_stokes_2d_steady_v1":
            fluid = self._inspect_steady_channel_flow(mesh, state)
            physics = fluid
        electromagnetic = None
        if analysis_type == "magnetodynamics_2d_harmonic_v1":
            normalized = {re.sub(r"[^a-z0-9]", "", name.lower()): name for name in mesh.point_data}

            def field_name(*names: str) -> str | None:
                for candidate in names:
                    key = re.sub(r"[^a-z0-9]", "", candidate.lower())
                    if key in normalized:
                        return normalized[key]
                return None

            b_re_name = field_name("B re", "Magnetic Flux Density re")
            b_im_name = field_name("B im", "Magnetic Flux Density im")
            b_real_name = field_name("B", "Magnetic Flux Density")
            a_re_name = field_name("A re", "Potential re")
            a_im_name = field_name("A im", "Potential im")
            selected_b_name = b_re_name or b_real_name
            if selected_b_name:
                b_re = np.asarray(mesh.point_data[selected_b_name], dtype=float)
                if b_re.ndim == 1:
                    b_re = b_re[:, None]
                b_im = np.asarray(mesh.point_data[b_im_name], dtype=float) if b_im_name else np.zeros_like(b_re)
                if b_im.ndim == 1:
                    b_im = b_im[:, None]
                b_amplitude = np.sqrt(np.sum(b_re * b_re + b_im * b_im, axis=1))
                physical_body_ids = state.get("mesh", {}).get("physical_body_ids", {})
                geometry_ids = mesh.cell_data.get("GeometryIds", [])
                body_nodes: dict[str, set[int]] = {str(name): set() for name in physical_body_ids}
                triangles = []
                for block_index, block in enumerate(mesh.cells):
                    if block.type.startswith("triangle"):
                        triangle_block = np.asarray(block.data[:, :3], dtype=int)
                        triangles.append(triangle_block)
                        if block_index < len(geometry_ids):
                            ids = np.asarray(geometry_ids[block_index]).reshape(-1)
                            for semantic, body_id in physical_body_ids.items():
                                matching = triangle_block[ids == int(body_id)]
                                if matching.size:
                                    body_nodes[str(semantic)].update(int(value) for value in np.unique(matching))
                body_field_statistics: dict[str, Any] = {}
                for semantic, node_ids in body_nodes.items():
                    if not node_ids:
                        continue
                    selected = np.asarray(sorted(node_ids), dtype=int)
                    values = b_amplitude[selected]
                    body_field_statistics[semantic] = {
                        "nodes": int(len(selected)),
                        "Bmean_T": float(np.mean(values)),
                        "Bmax_T": float(np.max(values)),
                    }
                far_air_mean = None
                air_nodes = body_nodes.get("air", set())
                if air_nodes:
                    selected = np.asarray(sorted(air_nodes), dtype=int)
                    coordinates = np.asarray(mesh.points)[selected]
                    far_mask = (np.abs(coordinates[:, 0]) >= 0.06) | (np.abs(coordinates[:, 1]) >= 0.055)
                    if np.any(far_mask):
                        far_air_mean = float(np.mean(b_amplitude[selected[far_mask]]))
                core_mean = body_field_statistics.get("core", {}).get("Bmean_T")
                core_to_far_air_ratio = (
                    float(core_mean / far_air_mean)
                    if core_mean is not None and far_air_mean is not None and far_air_mean > 0
                    else None
                )
                settings = state.get("equation", {}).get("settings", {})
                x_min = float(settings.get("flux_line_x_min_m", -0.01))
                x_max = float(settings.get("flux_line_x_max_m", 0.01))
                y_line = float(settings.get("flux_line_y_m", 0.0))
                stack_depth = float(settings.get("stack_depth_m", 0.02))
                frequency = float(settings.get("frequency_hz", 0))
                primary_turns = int(settings.get("primary_turns", 0))
                secondary_turns = int(settings.get("secondary_turns", 0))
                if triangles and b_re.shape[1] >= 2:
                    triangle_array = np.concatenate(triangles, axis=0)
                    sample_x = np.linspace(x_min, x_max, 201)
                    sample_b = []
                    for x_value in sample_x:
                        real_value = self._triangle_interpolate(np.asarray(mesh.points), triangle_array, b_re, (float(x_value), y_line))
                        imag_value = self._triangle_interpolate(np.asarray(mesh.points), triangle_array, b_im, (float(x_value), y_line))
                        sample_b.append(real_value + 1j * imag_value)
                    sample_b_array = np.asarray(sample_b)
                    flux_complex = stack_depth * np.trapezoid(sample_b_array[:, 1], sample_x)
                    omega = 2.0 * math.pi * frequency
                    v1 = abs(omega * primary_turns * flux_complex)
                    v2 = abs(omega * secondary_turns * flux_complex)
                    ratio = v2 / v1 if v1 else float("nan")
                    expected_ratio = secondary_turns / primary_turns if primary_turns else float("nan")
                    ratio_error = abs(ratio - expected_ratio) / expected_ratio if expected_ratio else float("inf")
                    flux_from_a = None
                    if a_re_name:
                        a_re = np.asarray(mesh.point_data[a_re_name], dtype=float).reshape(-1)
                        a_im = np.asarray(mesh.point_data[a_im_name], dtype=float).reshape(-1) if a_im_name else np.zeros_like(a_re)
                        a_left = self._triangle_interpolate(np.asarray(mesh.points), triangle_array, a_re, (x_min, y_line)) + 1j * self._triangle_interpolate(np.asarray(mesh.points), triangle_array, a_im, (x_min, y_line))
                        a_right = self._triangle_interpolate(np.asarray(mesh.points), triangle_array, a_re, (x_max, y_line)) + 1j * self._triangle_interpolate(np.asarray(mesh.points), triangle_array, a_im, (x_max, y_line))
                        flux_from_a = stack_depth * (a_left - a_right)
                    flux_consistency_error = (
                        abs(abs(flux_from_a) - abs(flux_complex)) / abs(flux_complex)
                        if flux_from_a is not None and abs(flux_complex) > 0
                        else float("inf")
                    )
                    excitations = state.get("excitations", {})
                    primary_pos = excitations.get("primary_pos", {})
                    primary_neg = excitations.get("primary_neg", {})
                    positive_current = float(primary_pos.get("current_density_re_a_per_m2", 0))
                    negative_current = float(primary_neg.get("current_density_re_a_per_m2", 0))
                    current_scale = max(abs(positive_current), abs(negative_current), 1.0)
                    opposite_current_pass = bool(
                        positive_current > 0
                        and negative_current < 0
                        and abs(positive_current + negative_current) / current_scale <= 1.0e-9
                    )
                    complex_arrays_present = bool(b_re_name and b_im_name and a_re_name and a_im_name)
                    spatial_verification_available = bool(physical_body_ids)
                    concentration_pass = bool(
                        not spatial_verification_available
                        or (core_to_far_air_ratio is not None and core_to_far_air_ratio > 10.0)
                    )
                    electromagnetic = {
                        "Bmin_T": float(np.min(b_amplitude)),
                        "Bmax_T": float(np.max(b_amplitude)),
                        "B_center_line_mean_T": float(np.mean(np.sqrt(np.sum(np.abs(sample_b_array) ** 2, axis=1)))),
                        "flux_re_Wb": float(np.real(flux_complex)),
                        "flux_im_Wb": float(np.imag(flux_complex)),
                        "flux_magnitude_Wb": float(abs(flux_complex)),
                        "flux_from_A_magnitude_Wb": float(abs(flux_from_a)) if flux_from_a is not None else None,
                        "V1_induced_rms_V": float(v1),
                        "V2_open_rms_V": float(v2),
                        "turns_ratio": float(ratio),
                        "expected_turns_ratio": float(expected_ratio),
                        "turns_ratio_relative_error": float(ratio_error),
                        "flux_A_vs_B_relative_error": float(flux_consistency_error),
                        "complex_A_and_B_arrays_present": complex_arrays_present,
                        "opposite_primary_current_directions": opposite_current_pass,
                        "body_field_statistics": body_field_statistics,
                        "far_air_Bmean_T": far_air_mean,
                        "core_to_far_air_Bmean_ratio": core_to_far_air_ratio,
                        "spatial_verification_available": spatial_verification_available,
                        "core_field_concentration_pass": concentration_pass,
                        "finite": bool(np.isfinite(b_amplitude).all() and np.isfinite([v1, v2, ratio]).all()),
                    }
                    electromagnetic["pass"] = bool(
                        electromagnetic["finite"]
                        and electromagnetic["Bmax_T"] > 1.0e-4
                        and electromagnetic["Bmax_T"] < 2.0
                        and electromagnetic["flux_magnitude_Wb"] > 0
                        and electromagnetic["V2_open_rms_V"] > 0
                        and electromagnetic["turns_ratio_relative_error"] <= 0.02
                        and electromagnetic["flux_A_vs_B_relative_error"] <= 0.05
                        and electromagnetic["complex_A_and_B_arrays_present"]
                        and electromagnetic["opposite_primary_current_directions"]
                        and electromagnetic["core_field_concentration_pass"]
                    )
                    electromagnetic["criteria"] = {
                        "Bmax": "1e-4 T < Bmax < 2 T",
                        "flux": "finite and non-zero",
                        "V2": "finite and non-zero",
                        "turns_ratio": "relative error <= 2%",
                        "flux_consistency": "A-difference and B-line flux relative error <= 5%",
                        "complex_fields": "A re/im and B re/im arrays present",
                        "primary_excitation": "equal-magnitude opposite-sign real current density",
                        "field_concentration": "core mean B / far-air mean B > 10",
                    }
            physics = electromagnetic
        elasticity = None
        if analysis_type == "elasticity_2d_static_v1":
            displacement_name, displacement = self._normalized_field(mesh.point_data, "displacement")
            stress_name, stress_xx = self._normalized_field(mesh.point_data, "stress_xx_derived_pa")
            strain_name, strain_xx = self._normalized_field(mesh.point_data, "strain_xx_derived")
            von_mises_name, von_mises = self._normalized_field(mesh.point_data, "von_mises_derived_pa")
            if (
                displacement is not None
                and displacement.ndim == 2
                and displacement.shape[1] >= 2
                and stress_xx is not None
                and strain_xx is not None
                and von_mises is not None
            ):
                points = np.asarray(mesh.points, dtype=float)
                stress_xx = stress_xx.reshape(-1)
                strain_xx = strain_xx.reshape(-1)
                von_mises = von_mises.reshape(-1)
                settings = state.get("equation", {}).get("settings", {})
                length = float(settings.get("beam_length_m", points[:, 0].max() - points[:, 0].min()))
                height = float(settings.get("beam_height_m", points[:, 1].max() - points[:, 1].min()))
                thickness = float(settings.get("thickness_m", 1.0))
                material = state.get("materials", {}).get("beam", {})
                youngs_modulus = float(material.get("youngs_modulus_pa", 0))
                top_boundary = next(
                    (boundary for boundary in state.get("boundaries", []) if boundary.get("semantic") == "top_load"),
                    {},
                )
                pressure = abs(float(top_boundary.get("traction_y_pa", 0)))
                x_min = float(points[:, 0].min())
                x_max = float(points[:, 0].max())
                y_min = float(points[:, 1].min())
                y_max = float(points[:, 1].max())
                x_mid = 0.5 * (x_min + x_max)
                y_mid = 0.5 * (y_min + y_max)
                x_distance = np.abs(points[:, 0] - x_mid)
                center_mask = x_distance <= float(x_distance.min()) + max(length * 0.015, 1.0e-12)
                outer_mask = center_mask & (np.abs(points[:, 1] - y_mid) >= 0.4 * height)
                if not np.any(outer_mask):
                    outer_mask = center_mask
                fe_deflection = float(max(0.0, -np.min(displacement[center_mask, 1])))
                fe_midspan_stress = float(np.max(np.abs(stress_xx[outer_mask])))
                fe_midspan_strain = float(np.max(np.abs(strain_xx[outer_mask])))
                total_load = pressure * length * thickness
                second_moment = thickness * height**3 / 12.0
                theory_stress = pressure * thickness * length**2 * height / (16.0 * second_moment)
                theory_deflection = (
                    5.0 * pressure * thickness * length**4 / (384.0 * youngs_modulus * second_moment)
                    if youngs_modulus > 0
                    else float("nan")
                )
                theory_strain = theory_stress / youngs_modulus if youngs_modulus > 0 else float("nan")
                deflection_error = (
                    abs(fe_deflection - theory_deflection) / theory_deflection if theory_deflection > 0 else float("inf")
                )
                stress_error = (
                    abs(fe_midspan_stress - theory_stress) / theory_stress if theory_stress > 0 else float("inf")
                )
                strain_error = (
                    abs(fe_midspan_strain - theory_strain) / theory_strain if theory_strain > 0 else float("inf")
                )
                left_node = int(np.argmin((points[:, 0] - x_min) ** 2 + (points[:, 1] - y_min) ** 2))
                right_node = int(np.argmin((points[:, 0] - x_max) ** 2 + (points[:, 1] - y_min) ** 2))
                support_residual = float(
                    max(
                        abs(displacement[left_node, 0]),
                        abs(displacement[left_node, 1]),
                        abs(displacement[right_node, 1]),
                    )
                )
                support_tolerance = max(fe_deflection * 1.0e-6, 1.0e-12)
                elasticity = {
                    "displacement_field": displacement_name,
                    "stress_field": stress_name,
                    "strain_field": strain_name,
                    "von_mises_field": von_mises_name,
                    "max_displacement_m": float(np.max(np.linalg.norm(displacement[:, :2], axis=1))),
                    "midspan_downward_deflection_m": fe_deflection,
                    "max_von_mises_pa": float(np.max(von_mises)),
                    "midspan_outer_fiber_abs_stress_xx_pa": fe_midspan_stress,
                    "midspan_outer_fiber_abs_strain_xx": fe_midspan_strain,
                    "total_applied_load_n": total_load,
                    "theory_support_reaction_each_n": 0.5 * total_load,
                    "theory_max_bending_stress_pa": theory_stress,
                    "theory_midspan_deflection_m": theory_deflection,
                    "theory_max_bending_strain": theory_strain,
                    "deflection_relative_error": deflection_error,
                    "stress_relative_error": stress_error,
                    "strain_relative_error": strain_error,
                    "support_displacement_residual_m": support_residual,
                    "finite": bool(
                        np.isfinite(displacement).all()
                        and np.isfinite(stress_xx).all()
                        and np.isfinite(strain_xx).all()
                        and np.isfinite(von_mises).all()
                    ),
                }
                elasticity["pass"] = bool(
                    elasticity["finite"]
                    and fe_deflection > 0
                    and fe_midspan_stress > 0
                    and fe_midspan_strain > 0
                    and support_residual <= support_tolerance
                    and deflection_error <= 0.20
                    and stress_error <= 0.20
                    and strain_error <= 0.20
                )
                elasticity["criteria"] = {
                    "fields": "finite, non-zero displacement plus derived plane-stress stress/strain",
                    "supports": f"left Ux/Uy and right Uy residual <= {support_tolerance:.6g} m",
                    "deflection": "Euler-Bernoulli relative error <= 20%",
                    "stress": "midspan outer-fiber relative error <= 20%",
                    "strain": "midspan outer-fiber relative error <= 20%",
                }
            physics = elasticity
        if analysis_type == "magnetodynamics_2d_harmonic_v1":
            valid = bool(fields) and finite and bool(electromagnetic and electromagnetic.get("pass"))
        elif analysis_type == "magnetodynamics_2d_transient_eddy_v1":
            valid = bool(fields) and finite
        elif analysis_type == "elasticity_2d_static_v1":
            valid = bool(fields) and finite and bool(elasticity and elasticity.get("pass"))
        elif analysis_type == "navier_stokes_2d_steady_v1":
            valid = bool(fields) and finite and bool(fluid and fluid.get("pass"))
        else:
            valid = bool(fields) and finite and temperature_name is not None and bool(physics and physics["pass"])
        return {
            "valid": valid,
            "points": len(mesh.points),
            "cells": sum(len(block.data) for block in mesh.cells),
            "fields": fields,
            "temperature_field": temperature_name,
            "finite": finite,
            "physics_acceptance": physics,
            "analysis_type": analysis_type,
            "time_steps": [
                float(state.get("equation", {}).get("settings", {}).get("load_factor", 0.0))
                if analysis_type == "elasticity_2d_static_v1"
                else 0.0
            ],
        }

    def result_inspect(self, project: str) -> ToolResponse:
        results_dir = self._project(project) / "results"
        state = self._load_state(project)
        result_prefix = str(state.get("equation", {}).get("settings", {}).get("result_prefix", "case"))
        candidates = sorted(
            (path for path in results_dir.glob(f"{result_prefix}*.vtu") if "_elmer_raw" not in path.stem),
            key=lambda item: item.stat().st_mtime,
        )
        path = candidates[-1] if candidates else results_dir / f"{result_prefix}.vtu"
        if not path.is_file():
            return ToolResponse.blocked(f"results/{result_prefix}.vtu does not exist")
        inspection = self._inspect_result_file(path, state)
        if state.get("analysis_type") == "heat_transient_v1":
            transient = self._inspect_transient_heat_sequence(candidates, state)
            inspection["physics_acceptance"] = transient
            inspection["time_steps"] = transient.get("time_steps_s", [])
            inspection["valid"] = bool(
                inspection.get("fields")
                and inspection.get("finite")
                and inspection.get("temperature_field")
                and transient.get("pass")
            )
        if state.get("analysis_type") == "magnetodynamics_2d_transient_eddy_v1":
            transient_eddy = self._inspect_transient_eddy_sequence(candidates, state)
            inspection["physics_acceptance"] = transient_eddy
            inspection["time_steps"] = [float(row["time_s"]) for row in transient_eddy.get("history", [])]
            inspection["valid"] = bool(
                inspection.get("fields")
                and inspection.get("finite")
                and transient_eddy.get("pass")
            )
        if inspection["valid"]:
            return ToolResponse.success("Elmer VTU result passed validation", data=inspection, artifacts=[self.guard.relative(path)])
        return ToolResponse.failure("Elmer VTU result is invalid", data=inspection, artifacts=[self.guard.relative(path)])
