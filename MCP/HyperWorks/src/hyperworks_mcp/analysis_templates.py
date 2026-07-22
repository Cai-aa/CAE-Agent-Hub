from __future__ import annotations

from copy import deepcopy
from typing import Any

from .analysis_profiles import AnalysisProfileService


TEMPLATES: dict[str, dict[str, Any]] = {
    "optistruct.linear_static_solid": {
        "template_id": "optistruct.linear_static_solid",
        "solver": "optistruct",
        "analysis": "linear_static",
        "description": "Structured CHEXA cantilever with material, PSOLID, SPC, force, optional CGAP, and H3D output.",
        "prepare_method": "prepare_optistruct_cantilever",
        "required_parameters": [
            "name", "dimensions", "divisions", "youngs_modulus",
            "poissons_ratio", "density", "total_force", "force_direction",
        ],
        "optional_parameters": ["gap_contacts", "output_name"],
        "validation_state": "real_solver_verified",
    },
    "radioss.explicit_block_impact": {
        "template_id": "radioss.explicit_block_impact",
        "solver": "radioss",
        "analysis": "explicit_impact",
        "description": "LAW2 solid block impact with initial velocity, BCS, TYPE7 contact, animation, time history, and H3D.",
        "prepare_method": "prepare_radioss_block_impact",
        "required_parameters": [
            "name", "impactor_dimensions", "impactor_divisions",
            "target_dimensions", "target_divisions", "initial_gap",
            "initial_velocity", "end_time", "output_interval",
        ],
        "optional_parameters": [
            "youngs_modulus", "poissons_ratio", "density", "yield_stress",
            "hardening_modulus", "hardening_exponent", "friction", "output_name",
        ],
        "validation_state": "real_solver_verified",
    },
    "optistruct.normal_modes_solid": {
        "template_id": "optistruct.normal_modes_solid",
        "solver": "optistruct",
        "analysis": "normal_modes",
        "description": "Fixed-end structured CHEXA solid with Lanczos EIGRL mode extraction and H3D eigenvectors.",
        "prepare_method": "prepare_optistruct_modal",
        "required_parameters": ["name", "dimensions", "divisions", "youngs_modulus", "poissons_ratio", "density"],
        "optional_parameters": ["number_of_modes", "output_name"],
        "default_parameters": {"number_of_modes": 10, "output_name": "modal.fem"},
        "validation_state": "real_solver_verified",
    },
    "optistruct.linear_buckling_solid": {
        "template_id": "optistruct.linear_buckling_solid",
        "solver": "optistruct",
        "analysis": "linear_buckling",
        "description": "Reference static preload followed by EIGRL linear buckling using STATSUB(BUCKLING).",
        "prepare_method": "prepare_optistruct_buckling",
        "required_parameters": ["name", "dimensions", "divisions", "youngs_modulus", "poissons_ratio", "density", "reference_force", "force_direction"],
        "optional_parameters": ["number_of_modes", "output_name"],
        "default_parameters": {"number_of_modes": 5, "output_name": "buckling.fem"},
        "validation_state": "real_solver_verified",
    },
    "optistruct.multi_case_static_solid": {
        "template_id": "optistruct.multi_case_static_solid",
        "solver": "optistruct",
        "analysis": "multi_case_linear_static",
        "description": "One structured CHEXA model with 2-50 independent FORCE subcases sharing material and SPC definitions.",
        "prepare_method": "prepare_optistruct_multicase_static",
        "required_parameters": ["name", "dimensions", "divisions", "youngs_modulus", "poissons_ratio", "density", "load_cases"],
        "optional_parameters": ["output_name"],
        "default_parameters": {"output_name": "multicase_static.fem"},
        "validation_state": "real_solver_verified",
    },
    "optistruct.gap_contact_static_solid": {
        "template_id": "optistruct.gap_contact_static_solid",
        "solver": "optistruct",
        "analysis": "linear_gap_contact_static",
        "description": "Structured CHEXA static fixture with explicit PGAP/CGAP definitions and grounded contact nodes.",
        "prepare_method": "prepare_optistruct_contact_static",
        "required_parameters": ["name", "dimensions", "divisions", "youngs_modulus", "poissons_ratio", "density", "total_force", "force_direction", "gap_contacts"],
        "optional_parameters": ["output_name"],
        "default_parameters": {"output_name": "contact_static.fem"},
        "validation_state": "real_solver_verified",
    },
    "optistruct.uniform_thermal_stress_solid": {
        "template_id": "optistruct.uniform_thermal_stress_solid",
        "solver": "optistruct",
        "analysis": "linear_thermal_stress",
        "description": "Constrained CHEXA solid with MAT1 thermal expansion and a uniform TEMP(LOAD) field.",
        "prepare_method": "prepare_optistruct_thermal_stress",
        "required_parameters": ["name", "dimensions", "divisions", "youngs_modulus", "poissons_ratio", "density", "thermal_expansion", "reference_temperature", "applied_temperature"],
        "optional_parameters": ["output_name"],
        "default_parameters": {"output_name": "thermal_stress.fem"},
        "validation_state": "real_solver_verified",
    },
    "radioss.drop_weight_solid_surrogate": {
        "template_id": "radioss.drop_weight_solid_surrogate",
        "solver": "radioss",
        "analysis": "drop_weight_surrogate",
        "description": "Initial-velocity solid striker against a deformable solid coupon; gravity and support fixtures are not implied.",
        "prepare_method": "prepare_radioss_solid_impact_scenario",
        "required_parameters": ["name"],
        "optional_parameters": ["impactor_dimensions", "impactor_divisions", "target_dimensions", "target_divisions", "initial_gap", "initial_velocity", "end_time", "output_interval", "youngs_modulus", "poissons_ratio", "density", "yield_stress", "hardening_modulus", "hardening_exponent", "friction", "output_name"],
        "fixed_parameters": {"scenario": "drop_weight_surrogate"},
        "default_parameters": {"impactor_dimensions": [5.0, 8.0, 8.0], "impactor_divisions": [2, 2, 2], "target_dimensions": [2.0, 20.0, 20.0], "target_divisions": [1, 4, 4], "initial_gap": 1.0, "initial_velocity": 5.0, "end_time": 1.0, "output_interval": 0.1, "youngs_modulus": 210.0, "poissons_ratio": 0.3, "density": 7.85e-6, "yield_stress": 0.25, "hardening_modulus": 0.5, "hardening_exponent": 0.5, "friction": 0.1, "output_name": "drop_weight_0000.rad"},
        "validation_state": "real_solver_verified_solid_surrogate",
    },
    "radioss.plate_impact_solid": {
        "template_id": "radioss.plate_impact_solid",
        "solver": "radioss",
        "analysis": "plate_impact",
        "description": "Structured solid projectile and plate fixture with LAW2 plasticity, TYPE7 contact, H3D, animation, and histories.",
        "prepare_method": "prepare_radioss_solid_impact_scenario",
        "required_parameters": ["name"],
        "optional_parameters": ["impactor_dimensions", "impactor_divisions", "target_dimensions", "target_divisions", "initial_gap", "initial_velocity", "end_time", "output_interval", "youngs_modulus", "poissons_ratio", "density", "yield_stress", "hardening_modulus", "hardening_exponent", "friction", "output_name"],
        "fixed_parameters": {"scenario": "plate_impact"},
        "default_parameters": {"impactor_dimensions": [4.0, 4.0, 4.0], "impactor_divisions": [2, 2, 2], "target_dimensions": [2.0, 16.0, 16.0], "target_divisions": [1, 4, 4], "initial_gap": 1.0, "initial_velocity": 10.0, "end_time": 0.8, "output_interval": 0.08, "youngs_modulus": 210.0, "poissons_ratio": 0.3, "density": 7.85e-6, "yield_stress": 0.25, "hardening_modulus": 0.5, "hardening_exponent": 0.5, "friction": 0.1, "output_name": "plate_impact_0000.rad"},
        "validation_state": "real_solver_verified",
    },
    "radioss.solid_axial_collision": {
        "template_id": "radioss.solid_axial_collision",
        "solver": "radioss",
        "analysis": "solid_axial_collision",
        "description": "Two structured solid members in axial impact; this is not a thin-wall crash box model.",
        "prepare_method": "prepare_radioss_solid_impact_scenario",
        "required_parameters": ["name"],
        "optional_parameters": ["impactor_dimensions", "impactor_divisions", "target_dimensions", "target_divisions", "initial_gap", "initial_velocity", "end_time", "output_interval", "youngs_modulus", "poissons_ratio", "density", "yield_stress", "hardening_modulus", "hardening_exponent", "friction", "output_name"],
        "fixed_parameters": {"scenario": "solid_axial_collision"},
        "default_parameters": {"impactor_dimensions": [20.0, 6.0, 6.0], "impactor_divisions": [8, 2, 2], "target_dimensions": [20.0, 6.0, 6.0], "target_divisions": [8, 2, 2], "initial_gap": 1.0, "initial_velocity": 5.0, "end_time": 2.0, "output_interval": 0.2, "youngs_modulus": 210.0, "poissons_ratio": 0.3, "density": 7.85e-6, "yield_stress": 0.25, "hardening_modulus": 0.5, "hardening_exponent": 0.5, "friction": 0.1, "output_name": "solid_axial_collision_0000.rad"},
        "validation_state": "real_solver_verified_solid_surrogate",
    },
    "radioss.three_point_bending": {
        "template_id": "radioss.three_point_bending", "solver": "radioss", "analysis": "three_point_bending",
        "description": "Requires specimen, two supports, striker, contact surfaces, and support constraints.",
        "prepare_method": None, "required_parameters": [], "optional_parameters": [],
        "validation_state": "requires_geometry_fixture", "unavailable_reason": "The current generator has only two structured solid parts; a four-body support/striker fixture is required.",
    },
    "radioss.tube_crush": {
        "template_id": "radioss.tube_crush", "solver": "radioss", "analysis": "tube_crush",
        "description": "Requires hollow tube or shell geometry, platens, self-contact, and appropriate hourglass controls.",
        "prepare_method": None, "required_parameters": [], "optional_parameters": [],
        "validation_state": "requires_geometry_fixture", "unavailable_reason": "No hollow-tube or shell crash-box generator is exposed yet.",
    },
    "radioss.thin_wall_axial_collision": {
        "template_id": "radioss.thin_wall_axial_collision", "solver": "radioss", "analysis": "thin_wall_axial_collision",
        "description": "Requires a shell crash box, triggers, self-contact, and section/thickness mapping.",
        "prepare_method": None, "required_parameters": [], "optional_parameters": [],
        "validation_state": "requires_geometry_fixture", "unavailable_reason": "The solid axial collision template must not be represented as a thin-wall shell model.",
    },
    "radioss.vehicle_crash_subsystem": {
        "template_id": "radioss.vehicle_crash_subsystem", "solver": "radioss", "analysis": "vehicle_crash_subsystem",
        "description": "Requires imported subsystem CAD/mesh, connections, many contacts, material mapping, and model-specific controls.",
        "prepare_method": None, "required_parameters": [], "optional_parameters": [],
        "validation_state": "requires_imported_model_fixture", "unavailable_reason": "A vehicle subsystem cannot be safely synthesized from the current two-block benchmark.",
    },
    "hyperstudy.template_doe_optimization": {
        "template_id": "hyperstudy.template_doe_optimization", "solver": "hyperstudy", "analysis": "doe_optimization",
        "description": "Solver-linked parameter study contract; current internal-math DOE/GRSM exists, but template-to-solver file coupling is not yet exposed.",
        "prepare_method": None, "required_parameters": [], "optional_parameters": [],
        "validation_state": "requires_solver_coupling_fixture", "unavailable_reason": "HyperStudy can run typed internal-math studies, but external OptiStruct/Radioss parameter substitution and response extraction still need a controlled model adapter.",
    },
}


class AnalysisTemplateService:
    def __init__(self, profiles: AnalysisProfileService):
        self.profiles = profiles

    def list(self, solver: str | None = None) -> dict[str, Any]:
        normalized = solver.strip().lower() if solver else None
        items = [
            deepcopy(spec)
            for spec in TEMPLATES.values()
            if normalized is None or spec["solver"] == normalized
        ]
        return {"templates": items, "count": len(items), "solver_filter": normalized}

    def get(self, template_id: str) -> dict[str, Any]:
        spec = TEMPLATES.get(str(template_id))
        if spec is None:
            raise ValueError(
                "Unknown template_id. Available templates: " + ", ".join(sorted(TEMPLATES))
            )
        return deepcopy(spec)

    def prepare(
        self,
        project_id: str,
        template_id: str,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        spec = self.get(template_id)
        if not spec.get("prepare_method"):
            raise RuntimeError(
                f"Template {template_id} is not runnable: "
                + str(spec.get("unavailable_reason", "required fixture is unavailable"))
            )
        if not isinstance(parameters, dict):
            raise ValueError("parameters must be an object")
        required = set(spec["required_parameters"])
        optional = set(spec["optional_parameters"])
        missing = sorted(required - set(parameters))
        unknown = sorted(set(parameters) - required - optional)
        if missing:
            raise ValueError("Missing required template parameters: " + ", ".join(missing))
        if unknown:
            raise ValueError("Unknown template parameters: " + ", ".join(unknown))
        resolved = deepcopy(spec.get("default_parameters", {}))
        resolved.update(parameters)
        resolved.update(deepcopy(spec.get("fixed_parameters", {})))
        method = getattr(self.profiles, spec["prepare_method"])
        result = method(project_id=project_id, **resolved)
        return {
            "template_id": template_id,
            "template_validation_state": spec["validation_state"],
            **result,
        }
