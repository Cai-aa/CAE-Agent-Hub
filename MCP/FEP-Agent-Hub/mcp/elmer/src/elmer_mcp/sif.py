from __future__ import annotations

import math
from pathlib import Path
from typing import Any


SUPPORTED_PROFILES = {
    "elasticity_2d_static_v1",
    "heat_steady_v1",
    "heat_transient_v1",
    "magnetodynamics_2d_harmonic_v1",
    "magnetodynamics_2d_transient_eddy_v1",
    "navier_stokes_2d_steady_v1",
}


def generate_heat_sif(case: dict[str, Any], semantic_map: dict[str, Any]) -> str:
    if case.get("analysis_type") != "heat_steady_v1":
        raise ValueError("UNKNOWN_SIF_PROFILE")
    body_ids = sorted(set(semantic_map.get("body_ids", {}).values()))
    if not body_ids:
        raise ValueError("No mapped Elmer body IDs")
    material = case.get("materials", {}).get("solid") or next(iter(case.get("materials", {}).values()), None)
    if not material:
        raise ValueError("Material 'solid' is required")
    conductivity = float(material.get("heat_conductivity", 1.0))
    if conductivity <= 0:
        raise ValueError("Heat conductivity must be positive")

    boundary_blocks = []
    for index, boundary in enumerate(case.get("boundaries", []), start=1):
        semantic = boundary["semantic"]
        target_ids = semantic_map.get("boundary_ids", {}).get(semantic, [])
        if not target_ids:
            raise ValueError(f"Boundary selector did not resolve: {semantic}")
        temperature = float(boundary["temperature_k"])
        targets = " ".join(str(value) for value in target_ids)
        boundary_blocks.append(
            f'''Boundary Condition {index}
  Name = "{semantic}"
  Target Boundaries({len(target_ids)}) = {targets}
  Temperature = {temperature:.12g}
End'''
        )

    body_targets = " ".join(str(value) for value in body_ids)
    return f'''Header
  CHECK KEYWORDS Warn
  Mesh DB "." "elmer_mesh"
End

Simulation
  Max Output Level = 5
  Coordinate System = Cartesian 3D
  Coordinate Mapping(3) = 1 2 3
  Simulation Type = Steady State
  Steady State Max Iterations = 1
  Output Intervals = 1
  Solver Input File = case.sif
  Output File = case.result
  Post File = "../../results/case.vtu"
End

Constants
  Stefan Boltzmann = 5.670374419e-8
End

Body 1
  Name = "solid"
  Target Bodies({len(body_ids)}) = {body_targets}
  Equation = 1
  Material = 1
End

Equation 1
  Name = "Heat Equation"
  Active Solvers(1) = 1
End

Solver 1
  Equation = Heat Equation
  Procedure = "HeatSolve" "HeatSolver"
  Variable = Temperature
  Variable DOFs = 1
  Linear System Solver = Iterative
  Linear System Iterative Method = BiCGStab
  Linear System Max Iterations = 500
  Linear System Convergence Tolerance = 1.0e-10
  Linear System Preconditioning = ILU0
  Steady State Convergence Tolerance = 1.0e-8
End

Material 1
  Name = "{material.get('name', 'GenericSolid')}"
  Heat Conductivity = {conductivity:.12g}
  Density = 1
  Heat Capacity = 1
End

{chr(10).join(boundary_blocks)}
'''


def _target_values(value: Any) -> list[int]:
    values = value if isinstance(value, list) else [value]
    targets = sorted({int(item) for item in values})
    if not targets:
        raise ValueError("A semantic body resolved to no Elmer body IDs")
    return targets


def generate_heat_transient_sif(case: dict[str, Any], semantic_map: dict[str, Any]) -> str:
    if case.get("analysis_type") != "heat_transient_v1":
        raise ValueError("UNKNOWN_SIF_PROFILE")
    body_ids = sorted(set(semantic_map.get("body_ids", {}).values()))
    if not body_ids:
        raise ValueError("No mapped Elmer body IDs")
    material = case.get("materials", {}).get("solid") or next(iter(case.get("materials", {}).values()), None)
    if not material:
        raise ValueError("Material 'solid' is required")
    conductivity = float(material.get("heat_conductivity", 0))
    density = float(material.get("density_kg_per_m3", 0))
    heat_capacity = float(material.get("heat_capacity_j_per_kg_k", 0))
    if conductivity <= 0 or density <= 0 or heat_capacity <= 0:
        raise ValueError("Transient heat material properties must be positive")
    settings = case.get("equation", {}).get("settings", {})
    step_count = int(settings.get("time_step_count", 0))
    time_step = float(settings.get("time_step_s", 0))
    initial_temperature = float(settings.get("initial_temperature_k", 0))
    result_prefix = str(settings.get("result_prefix", "transient_heat"))
    if step_count < 2 or time_step <= 0 or initial_temperature <= 0:
        raise ValueError("Invalid transient heat time settings")

    boundary_blocks = []
    for index, boundary in enumerate(case.get("boundaries", []), start=1):
        semantic = str(boundary["semantic"])
        target_ids = semantic_map.get("boundary_ids", {}).get(semantic, [])
        if not target_ids:
            raise ValueError(f"Boundary selector did not resolve: {semantic}")
        targets = " ".join(str(int(value)) for value in sorted(set(target_ids)))
        boundary_blocks.append(
            f'''Boundary Condition {index}
  Name = "{semantic}"
  Target Boundaries({len(target_ids)}) = {targets}
  Temperature = Real {float(boundary["temperature_k"]):.12g}
End'''
        )
    body_target_text = " ".join(str(value) for value in body_ids)
    return f'''Header
  CHECK KEYWORDS Warn
  Mesh DB "." "elmer_mesh"
End

Simulation
  Max Output Level = 5
  Coordinate System = Cartesian 3D
  Coordinate Mapping(3) = 1 2 3
  Simulation Type = Transient
  Timestepping Method = BDF
  BDF Order = 1
  Timestep Intervals = {step_count}
  Timestep Sizes = {time_step:.12g}
  Output Intervals = 1
  Solver Input File = case.sif
  Output File = case.result
End

Body 1
  Name = "solid"
  Target Bodies({len(body_ids)}) = {body_target_text}
  Equation = 1
  Material = 1
  Initial Condition = 1
End

Equation 1
  Name = "Transient Heat Equation"
  Active Solvers(2) = 1 2
End

Solver 1
  Exec Solver = Always
  Equation = Heat Equation
  Procedure = "HeatSolve" "HeatSolver"
  Variable = Temperature
  Variable DOFs = 1
  Linear System Solver = Direct
  Linear System Direct Method = UMFPack
  Linear System Abort Not Converged = Logical True
  Nonlinear System Convergence Tolerance = 1.0e-10
End

Solver 2
  Exec Solver = After Timestep
  Equation = "Result Output"
  Procedure = "ResultOutputSolve" "ResultOutputSolver"
  Output File Name = "../../results/{result_prefix}"
  Vtu Format = Logical True
  Binary Output = Logical False
  Single Precision = Logical False
  Save Geometry Ids = Logical True
  Show Variables = Logical True
End

Material 1
  Name = "{material.get('name', 'Thermal Solid')}"
  Heat Conductivity = {conductivity:.12g}
  Density = {density:.12g}
  Heat Capacity = {heat_capacity:.12g}
End

Initial Condition 1
  Name = "Initial Temperature"
  Temperature = Real {initial_temperature:.12g}
End

{chr(10).join(boundary_blocks)}
'''


def generate_navier_stokes_2d_steady_sif(
    case: dict[str, Any], semantic_map: dict[str, Any]
) -> str:
    if case.get("analysis_type") != "navier_stokes_2d_steady_v1":
        raise ValueError("UNKNOWN_SIF_PROFILE")
    if semantic_map.get("dimension") != 2:
        raise ValueError("The steady 2D flow profile requires a two-dimensional Elmer mesh")
    body_map = semantic_map.get("body_ids", {})
    if "fluid" not in body_map:
        raise ValueError("Missing semantic body: fluid")
    boundary_map = semantic_map.get("boundary_ids", {})
    missing_boundaries = [name for name in ("inlet", "outlet", "walls") if not boundary_map.get(name)]
    if missing_boundaries:
        raise ValueError(f"Missing semantic flow boundaries: {missing_boundaries}")
    material = case.get("materials", {}).get("fluid")
    if not material:
        raise ValueError("Material is required for body 'fluid'")
    density = float(material.get("density_kg_per_m3", 0))
    viscosity = float(material.get("dynamic_viscosity_pa_s", 0))
    if density <= 0 or viscosity <= 0:
        raise ValueError("Fluid density and dynamic viscosity must be positive")
    settings = case.get("equation", {}).get("settings", {})
    length = float(settings.get("channel_length_m", 0))
    height = float(settings.get("channel_height_m", 0))
    mean_velocity = float(settings.get("mean_velocity_m_per_s", 0))
    result_prefix = str(settings.get("result_prefix", "channel_flow"))
    if length <= 0 or height <= 0 or mean_velocity <= 0:
        raise ValueError("Invalid channel dimensions or mean velocity")
    boundaries = {str(item.get("semantic")): item for item in case.get("boundaries", [])}
    if not all(name in boundaries for name in ("inlet", "outlet", "walls")):
        raise ValueError("Inlet, outlet, and walls boundary conditions are required")
    inlet_mean = float(boundaries["inlet"].get("mean_velocity_m_per_s", 0))
    wall_x = float(boundaries["walls"].get("velocity_x_m_per_s", 0))
    wall_y = float(boundaries["walls"].get("velocity_y_m_per_s", 0))
    if not math.isclose(inlet_mean, mean_velocity, rel_tol=1.0e-12, abs_tol=1.0e-15):
        raise ValueError("Inlet boundary mean velocity must match the equation setting")
    if not math.isclose(wall_x, 0.0, abs_tol=1.0e-15) or not math.isclose(wall_y, 0.0, abs_tol=1.0e-15):
        raise ValueError("The verified channel profile requires stationary no-slip walls")
    inlet_targets = _target_values(boundary_map["inlet"])
    outlet_targets = _target_values(boundary_map["outlet"])
    wall_targets = _target_values(boundary_map["walls"])
    body_targets = _target_values(body_map["fluid"])
    parabolic = f"6.0*{mean_velocity:.15g}*tx(0)*({height:.15g}-tx(0))/({height:.15g}*{height:.15g})"
    return f'''Header
  CHECK KEYWORDS Warn
  Mesh DB "." "elmer_mesh"
End

Simulation
  Max Output Level = 5
  Coordinate System = Cartesian 2D
  Simulation Type = Steady State
  Steady State Max Iterations = 1
  Output Intervals = 1
  Solver Input File = case.sif
  Output File = case.result
End

Body 1
  Name = "fluid"
  Target Bodies({len(body_targets)}) = {' '.join(str(value) for value in body_targets)}
  Equation = 1
  Material = 1
End

Equation 1
  Name = "Incompressible Navier-Stokes"
  Active Solvers(2) = 1 2
  Navier-Stokes = Logical True
End

Solver 1
  Exec Solver = Always
  Equation = Navier-Stokes
  Procedure = "FlowSolve" "FlowSolver"
  Variable = Flow Solution[Velocity:2 Pressure:1]
  Variable DOFs = 3
  Stabilize = Logical True
  Bubbles = Logical False
  Nonlinear System Max Iterations = 30
  Nonlinear System Convergence Tolerance = 1.0e-9
  Nonlinear System Newton After Iterations = 3
  Nonlinear System Newton After Tolerance = 1.0e-4
  Nonlinear System Relaxation Factor = 0.7
  Linear System Solver = Direct
  Linear System Direct Method = UMFPack
  Linear System Abort Not Converged = Logical True
  Steady State Convergence Tolerance = 1.0e-9
End

Solver 2
  Exec Solver = After Timestep
  Equation = "Result Output"
  Procedure = "ResultOutputSolve" "ResultOutputSolver"
  Output File Name = "../../results/{result_prefix}"
  Vtu Format = Logical True
  Binary Output = Logical False
  Single Precision = Logical False
  Save Geometry Ids = Logical True
  Show Variables = Logical True
End

Material 1
  Name = "{material.get('name', 'Newtonian Fluid')}"
  Density = {density:.12g}
  Viscosity = {viscosity:.12g}
End

Boundary Condition 1
  Name = "inlet"
  Target Boundaries({len(inlet_targets)}) = {' '.join(str(value) for value in inlet_targets)}
  Velocity 1 = Variable Coordinate 2
    Real MATC "{parabolic}"
  Velocity 2 = Real 0
End

Boundary Condition 2
  Name = "outlet"
  Target Boundaries({len(outlet_targets)}) = {' '.join(str(value) for value in outlet_targets)}
  Pressure = Real {float(boundaries['outlet'].get('pressure_pa', 0)):.12g}
End

Boundary Condition 3
  Name = "walls"
  Target Boundaries({len(wall_targets)}) = {' '.join(str(value) for value in wall_targets)}
  Velocity 1 = Real 0
  Velocity 2 = Real 0
End
'''


def generate_elasticity_2d_static_sif(
    case: dict[str, Any], semantic_map: dict[str, Any]
) -> str:
    if case.get("analysis_type") != "elasticity_2d_static_v1":
        raise ValueError("UNKNOWN_SIF_PROFILE")
    if semantic_map.get("dimension") != 2:
        raise ValueError("The static 2D elasticity profile requires a two-dimensional Elmer mesh")
    body_map = semantic_map.get("body_ids", {})
    if "beam" not in body_map:
        raise ValueError("Missing semantic body: beam")
    material = case.get("materials", {}).get("beam")
    if not material:
        raise ValueError("Material is required for body 'beam'")
    youngs_modulus = float(material.get("youngs_modulus_pa", 0))
    poisson_ratio = float(material.get("poisson_ratio", -1))
    density = float(material.get("density_kg_per_m3", 0))
    if youngs_modulus <= 0 or density <= 0 or not 0 <= poisson_ratio < 0.5:
        raise ValueError("Invalid isotropic elastic material")
    settings = case.get("equation", {}).get("settings", {})
    result_prefix = str(settings.get("result_prefix", "case"))
    body_targets = _target_values(body_map["beam"])
    body_target_text = " ".join(str(value) for value in body_targets)

    boundary_blocks = []
    for index, boundary in enumerate(case.get("boundaries", []), start=1):
        semantic = str(boundary["semantic"])
        target_ids = semantic_map.get("boundary_ids", {}).get(semantic, [])
        if not target_ids:
            raise ValueError(f"Boundary selector did not resolve: {semantic}")
        values = []
        for key, sif_name in (
            ("displacement_x_m", "Displacement 1"),
            ("displacement_y_m", "Displacement 2"),
            ("traction_x_pa", "Force 1"),
            ("traction_y_pa", "Force 2"),
        ):
            if key in boundary:
                values.append(f"  {sif_name} = Real {float(boundary[key]):.12g}")
        if not values:
            raise ValueError(f"Elastic boundary has no supported condition: {semantic}")
        targets = " ".join(str(int(value)) for value in sorted(set(target_ids)))
        boundary_blocks.append(
            f'''Boundary Condition {index}
  Name = "{semantic}"
  Target Boundaries({len(target_ids)}) = {targets}
{chr(10).join(values)}
End'''
        )

    return f'''Header
  CHECK KEYWORDS Warn
  Mesh DB "." "elmer_mesh"
End

Simulation
  Max Output Level = 5
  Coordinate System = Cartesian 2D
  Simulation Type = Steady State
  Steady State Max Iterations = 1
  Output Intervals = 1
  Solver Input File = case.sif
  Output File = case.result
End

Body 1
  Name = "beam"
  Target Bodies({len(body_targets)}) = {body_target_text}
  Equation = 1
  Material = 1
End

Equation 1
  Name = "Plane Stress Elasticity"
  Active Solvers(2) = 1 2
  Plane Stress = Logical True
  Calculate Stresses = Logical True
End

Solver 1
  Exec Solver = Always
  Equation = "Stress Analysis"
  Procedure = "StressSolve" "StressSolver"
  Variable = Displacement
  Variable DOFs = 2
  Calculate Stresses = Logical True
  Calculate Loads = Logical True
  Displace Mesh = Logical False
  Linear System Solver = Direct
  Linear System Direct Method = UMFPack
  Linear System Abort Not Converged = Logical True
  Steady State Convergence Tolerance = 1.0e-10
End

Solver 2
  Exec Solver = After Timestep
  Equation = "Result Output"
  Procedure = "ResultOutputSolve" "ResultOutputSolver"
  Output File Name = "../../results/{result_prefix}"
  Vtu Format = Logical True
  Binary Output = Logical False
  Single Precision = Logical False
  Save Geometry Ids = Logical True
  Show Variables = Logical True
End

Material 1
  Name = "{material.get('name', 'Steel')}"
  Youngs Modulus = {youngs_modulus:.12g}
  Poisson Ratio = {poisson_ratio:.12g}
  Density = {density:.12g}
End

{chr(10).join(boundary_blocks)}
'''


def generate_magnetodynamics_2d_harmonic_sif(
    case: dict[str, Any], semantic_map: dict[str, Any]
) -> str:
    if case.get("analysis_type") != "magnetodynamics_2d_harmonic_v1":
        raise ValueError("UNKNOWN_SIF_PROFILE")
    if semantic_map.get("dimension") != 2:
        raise ValueError("The harmonic 2D profile requires a two-dimensional Elmer mesh")
    body_map = semantic_map.get("body_ids", {})
    required_bodies = ["air", "core", "primary_pos", "primary_neg", "secondary_pos", "secondary_neg"]
    missing_bodies = [name for name in required_bodies if name not in body_map]
    if missing_bodies:
        raise ValueError(f"Missing semantic bodies: {missing_bodies}")
    boundary_ids = semantic_map.get("boundary_ids", {}).get("outer_boundary", [])
    if not boundary_ids:
        raise ValueError("Boundary selector did not resolve: outer_boundary")

    settings = case.get("equation", {}).get("settings", {})
    frequency = float(settings.get("frequency_hz", 0))
    if frequency <= 0:
        raise ValueError("frequency_hz must be positive")
    omega = 2.0 * 3.141592653589793 * frequency
    result_prefix = str(settings.get("result_prefix", "case"))
    materials = case.get("materials", {})
    excitations = case.get("excitations", {})

    material_blocks = []
    body_blocks = []
    excitation_blocks = []
    excitation_index: dict[str, int] = {}
    for semantic in required_bodies:
        material = materials.get(semantic)
        if not material:
            raise ValueError(f"Material is required for body '{semantic}'")
        permeability = float(material.get("relative_permeability", 0))
        conductivity = float(material.get("electric_conductivity_s_per_m", -1))
        if permeability <= 0 or conductivity < 0:
            raise ValueError(f"Invalid electromagnetic material for body '{semantic}'")
        material_id = len(material_blocks) + 1
        material_blocks.append(
            f'''Material {material_id}
  Name = "{material.get('name', semantic)}"
  Relative Permeability = {permeability:.12g}
  Electric Conductivity = {conductivity:.12g}
End'''
        )
        excitation = excitations.get(semantic)
        if excitation:
            force_id = len(excitation_blocks) + 1
            excitation_index[semantic] = force_id
            current_re = float(excitation.get("current_density_re_a_per_m2", 0))
            current_im = float(excitation.get("current_density_im_a_per_m2", 0))
            excitation_blocks.append(
                f'''Body Force {force_id}
  Name = "{semantic}_current"
  Current Density = Real {current_re:.12g}
  Current Density Im = Real {current_im:.12g}
  Calculate Potential = Logical True
End'''
            )
        targets = _target_values(body_map[semantic])
        target_text = " ".join(str(value) for value in targets)
        force_line = f"\n  Body Force = {excitation_index[semantic]}" if semantic in excitation_index else ""
        body_blocks.append(
            f'''Body {len(body_blocks) + 1}
  Name = "{semantic}"
  Target Bodies({len(targets)}) = {target_text}
  Equation = 1
  Material = {material_id}{force_line}
End'''
        )

    outer_targets = " ".join(str(int(value)) for value in sorted(set(boundary_ids)))
    return f'''Header
  CHECK KEYWORDS Warn
  Mesh DB "." "elmer_mesh"
End

Simulation
  Max Output Level = 5
  Coordinate System = Cartesian 2D
  Simulation Type = Steady State
  Steady State Max Iterations = 1
  Output Intervals = 1
  Angular Frequency = {omega:.15g}
  Solver Input File = case.sif
  Output File = case.result
End

Constants
  Permeability of Vacuum = 1.25663706212e-6
  Permittivity of Vacuum = 8.8541878128e-12
End

{chr(10).join(body_blocks)}

Equation 1
  Name = "Harmonic Magnetodynamics 2D"
  Active Solvers(3) = 1 2 3
End

Solver 1
  Exec Solver = Always
  Equation = "Mag"
  Variable = A[A re:1 A im:1]
  Procedure = "MagnetoDynamics2D" "MagnetoDynamics2DHarmonic"
  Linear System Complex = Logical True
  Linear System Solver = Direct
  Linear System Direct Method = UMFPack
  Linear System Abort Not Converged = Logical True
  Steady State Convergence Tolerance = 1.0e-8
End

Solver 2
  Exec Solver = Always
  Equation = "ComputeB"
  Variable = -nooutput temp
  Exported Variable 1 = B[B re:2 B im:2]
  Target Variable = "A"
  Target Variable Complex = Logical True
  Procedure = "MagnetoDynamics2D" "BSolver"
  Discontinuous Galerkin = Logical True
  Average Within Materials = Logical True
  Calculate Joule Heating = Logical False
  Linear System Solver = Iterative
  Linear System Iterative Method = BiCGStab
  Linear System Max Iterations = 500
  Linear System Convergence Tolerance = 1.0e-8
  Linear System Preconditioning = ILU0
End

Solver 3
  Exec Solver = After Timestep
  Equation = "Result Output"
  Procedure = "ResultOutputSolve" "ResultOutputSolver"
  Output File Name = "../../results/{result_prefix}"
  Vtu Format = Logical True
  Binary Output = Logical False
  Single Precision = Logical False
  Save Geometry Ids = Logical True
  Discontinuous Galerkin = Logical True
  Show Variables = Logical True
End

{chr(10).join(material_blocks)}

{chr(10).join(excitation_blocks)}

Boundary Condition 1
  Name = "outer_boundary"
  Target Boundaries({len(boundary_ids)}) = {outer_targets}
  A re = Real 0
  A im = Real 0
End
'''


def _triangular_wave_table(peak: float, quarter_period_s: float, sign: float) -> str:
    """Return a fixed four-ramp Elmer interpolation table; no expression input is accepted."""
    points = (
        (0.0, 0.0),
        (quarter_period_s, sign * peak),
        (2.0 * quarter_period_s, 0.0),
        (3.0 * quarter_period_s, -sign * peak),
        (4.0 * quarter_period_s, 0.0),
    )
    rows = "\n".join(f"    {time_s:.12g} {value:.12g}" for time_s, value in points)
    return f"Variable Time\n  Real\n{rows}\n  End"


def generate_magnetodynamics_2d_transient_eddy_sif(
    case: dict[str, Any], semantic_map: dict[str, Any]
) -> str:
    if case.get("analysis_type") != "magnetodynamics_2d_transient_eddy_v1":
        raise ValueError("UNKNOWN_SIF_PROFILE")
    if semantic_map.get("dimension") != 2:
        raise ValueError("The transient eddy-current profile requires a two-dimensional Elmer mesh")
    body_map = semantic_map.get("body_ids", {})
    required_bodies = ["air", "conductor", "coil_pos", "coil_neg"]
    missing = [name for name in required_bodies if name not in body_map]
    if missing:
        raise ValueError(f"Missing semantic bodies: {missing}")
    boundary_ids = semantic_map.get("boundary_ids", {}).get("outer_boundary", [])
    if not boundary_ids:
        raise ValueError("Boundary selector did not resolve: outer_boundary")
    settings = case.get("equation", {}).get("settings", {})
    steps = int(settings.get("time_step_count", 0))
    dt = float(settings.get("time_step_s", 0))
    quarter = float(settings.get("quarter_period_s", 0))
    result_prefix = str(settings.get("result_prefix", "lenz_eddy"))
    if steps < 4 or dt <= 0 or quarter <= 0 or not math.isclose(steps * dt, 4.0 * quarter, rel_tol=0, abs_tol=1e-12):
        raise ValueError("Transient eddy-current time settings must span exactly four quarter ramps")
    materials = case.get("materials", {})
    excitations = case.get("excitations", {})
    material_blocks = []
    body_blocks = []
    force_blocks = []
    force_ids: dict[str, int] = {}
    for semantic in required_bodies:
        material = materials.get(semantic)
        if not material:
            raise ValueError(f"Material is required for body '{semantic}'")
        permeability = float(material.get("relative_permeability", 0))
        conductivity = float(material.get("electric_conductivity_s_per_m", -1))
        if permeability <= 0 or conductivity < 0:
            raise ValueError(f"Invalid electromagnetic material for body '{semantic}'")
        material_id = len(material_blocks) + 1
        material_blocks.append(
            f'''Material {material_id}
  Name = "{material.get('name', semantic)}"
  Relative Permeability = {permeability:.12g}
  Electric Conductivity = {conductivity:.12g}
End'''
        )
        excitation = excitations.get(semantic)
        if excitation:
            peak = float(excitation.get("peak_current_density_a_per_m2", 0))
            direction = float(excitation.get("direction", 0))
            if peak <= 0 or direction not in (-1.0, 1.0):
                raise ValueError(f"Invalid transient excitation for body '{semantic}'")
            force_id = len(force_blocks) + 1
            force_ids[semantic] = force_id
            force_blocks.append(
                f'''Body Force {force_id}
  Name = "{semantic}_triangular_current"
  Current Density = {_triangular_wave_table(peak, quarter, direction)}
End'''
            )
        targets = _target_values(body_map[semantic])
        force_line = f"\n  Body Force = {force_ids[semantic]}" if semantic in force_ids else ""
        body_blocks.append(
            f'''Body {len(body_blocks) + 1}
  Name = "{semantic}"
  Target Bodies({len(targets)}) = {' '.join(str(value) for value in targets)}
  Equation = 1
  Material = {material_id}
  Initial Condition = 1{force_line}
End'''
        )
    outer_targets = " ".join(str(int(value)) for value in sorted(set(boundary_ids)))
    return f'''Header
  CHECK KEYWORDS Warn
  Mesh DB "." "elmer_mesh"
End

Simulation
  Max Output Level = 5
  Coordinate System = Cartesian 2D
  Simulation Type = Transient
  Timestepping Method = BDF
  BDF Order = 1
  Timestep Intervals = {steps}
  Timestep Sizes = {dt:.12g}
  Output Intervals = 1
  Solver Input File = case.sif
  Output File = case.result
End

Constants
  Permeability of Vacuum = 1.25663706212e-6
  Permittivity of Vacuum = 8.8541878128e-12
End

{chr(10).join(body_blocks)}

Equation 1
  Name = "Transient Eddy Current 2D"
  Active Solvers(3) = 1 2 3
End

Solver 1
  Exec Solver = Always
  Equation = "Mag"
  Variable = Potential
  Procedure = "MagnetoDynamics2D" "MagnetoDynamics2D"
  Linear System Solver = Direct
  Linear System Direct Method = UMFPack
  Linear System Abort Not Converged = Logical True
  Nonlinear System Max Iterations = 1
  Steady State Convergence Tolerance = 1.0e-9
End

Solver 2
  Exec Solver = After Timestep
  Equation = "ComputeB"
  Variable = -nooutput bsolver_temp
  Exported Variable 1 = B[B:2]
  Target Variable = "Potential"
  Target Variable Complex = Logical False
  Procedure = "MagnetoDynamics2D" "BSolver"
  Discontinuous Galerkin = Logical True
  Average Within Materials = Logical True
  Linear System Solver = Iterative
  Linear System Iterative Method = BiCGStab
  Linear System Max Iterations = 500
  Linear System Convergence Tolerance = 1.0e-8
  Linear System Preconditioning = ILU0
End

Solver 3
  Exec Solver = After Timestep
  Equation = "Result Output"
  Procedure = "ResultOutputSolve" "ResultOutputSolver"
  Output File Name = "../../results/{result_prefix}"
  Vtu Format = Logical True
  Binary Output = Logical False
  Single Precision = Logical False
  Save Geometry Ids = Logical True
  Discontinuous Galerkin = Logical True
  Show Variables = Logical True
End

{chr(10).join(material_blocks)}

{chr(10).join(force_blocks)}

Initial Condition 1
  Potential = Real 0
End

Boundary Condition 1
  Name = "outer_boundary"
  Target Boundaries({len(boundary_ids)}) = {outer_targets}
  Potential = Real 0
End
'''


def validate_sif(path: str | Path, *, required_boundaries: int = 2, profile: str | None = None) -> dict[str, Any]:
    text = Path(path).read_text(encoding="utf-8")
    selected_profile = profile or (
        "magnetodynamics_2d_harmonic_v1"
        if "MagnetoDynamics2DHarmonic" in text
        else "heat_steady_v1"
    )
    if selected_profile == "magnetodynamics_2d_harmonic_v1":
        required = [
            "Header", "Simulation", "Angular Frequency", "Equation 1", "Solver 1",
            "MagnetoDynamics2DHarmonic", "BSolver", "ResultOutputSolver",
            "A[A re:1 A im:1]", "Current Density", "Relative Permeability",
            "Electric Conductivity", "outer_boundary", "A re = Real 0", "A im = Real 0",
        ]
        missing = [token for token in required if token not in text]
        return {
            "valid": not missing,
            "missing": missing,
            "boundary_count": text.count("Boundary Condition "),
            "body_count": text.count("Body "),
            "profile": selected_profile,
        }
    if selected_profile == "magnetodynamics_2d_transient_eddy_v1":
        required = [
            "Simulation Type = Transient", "Timestepping Method = BDF",
            "MagnetoDynamics2D\" \"MagnetoDynamics2D", "BSolver",
            "ResultOutputSolver", "Variable = Potential", "Current Density = Variable Time",
            "Electric Conductivity", "Initial Condition 1", "outer_boundary",
            "Potential = Real 0",
        ]
        missing = [token for token in required if token not in text]
        return {
            "valid": not missing,
            "missing": missing,
            "boundary_count": text.count("Boundary Condition "),
            "body_count": text.count("Body "),
            "profile": selected_profile,
        }
    if selected_profile == "elasticity_2d_static_v1":
        required = [
            "Header", "Simulation", "Cartesian 2D", "Body 1", "Equation 1",
            "Plane Stress = Logical True", "StressSolver", "ResultOutputSolver",
            "Variable = Displacement", "Youngs Modulus", "Poisson Ratio",
            "left_pin", "right_roller", "top_load", "Force 2",
        ]
        missing = [token for token in required if token not in text]
        boundary_count = text.count("Boundary Condition ")
        if boundary_count < 3:
            missing.append("at least 3 Boundary Condition blocks")
        return {
            "valid": not missing,
            "missing": missing,
            "boundary_count": boundary_count,
            "profile": selected_profile,
        }
    if selected_profile == "heat_transient_v1":
        required = [
            "Header", "Simulation", "Simulation Type = Transient", "Timestepping Method = BDF",
            "Timestep Intervals", "Timestep Sizes", "HeatSolver", "ResultOutputSolver",
            "Initial Condition 1", "Heat Conductivity", "Density", "Heat Capacity",
        ]
        missing = [token for token in required if token not in text]
        boundary_count = text.count("Boundary Condition ")
        if boundary_count < required_boundaries:
            missing.append(f"at least {required_boundaries} Boundary Condition blocks")
        return {
            "valid": not missing,
            "missing": missing,
            "boundary_count": boundary_count,
            "profile": selected_profile,
        }
    if selected_profile == "navier_stokes_2d_steady_v1":
        required = [
            "Header", "Simulation", "Cartesian 2D", "Navier-Stokes", "FlowSolver",
            "Flow Solution[Velocity:2 Pressure:1]", "ResultOutputSolver", "Density", "Viscosity",
            "inlet", "outlet", "walls", "Real MATC", "Pressure = Real",
        ]
        missing = [token for token in required if token not in text]
        boundary_count = text.count("Boundary Condition ")
        if boundary_count < 3:
            missing.append("at least 3 Boundary Condition blocks")
        return {
            "valid": not missing,
            "missing": missing,
            "boundary_count": boundary_count,
            "profile": selected_profile,
        }
    required = ["Header", "Simulation", "Body 1", "Equation 1", "Solver 1", "Material 1", "HeatSolver"]
    missing = [token for token in required if token not in text]
    boundary_count = text.count("Boundary Condition ")
    if boundary_count < required_boundaries:
        missing.append(f"at least {required_boundaries} Boundary Condition blocks")
    return {
        "valid": not missing,
        "missing": missing,
        "boundary_count": boundary_count,
        "profile": selected_profile,
    }
