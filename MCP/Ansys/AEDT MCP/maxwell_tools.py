"""Typed MCP entry points for Maxwell; all requests use the existing broker."""
from __future__ import annotations

from typing import Any, Literal

Scalar = int | float | str


def register_maxwell_tools(mcp, worker_call) -> None:

    @mcp.tool()
    async def maxwell_assign_coil(
        project_name: str,
        design_name: str,
        assignment: list[str | int],
        name: str,
        conductors_number: int = 1,
        polarity: Literal['Positive', 'Negative'] = 'Positive',
        pid: int | None = None,
        port: int | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Assign an existing coil terminal. Maxwell 2D requires object names; 3D accepts terminal sheet names or face IDs. conductors_number is a positive conductor/turn count. Polarity controls terminal direction. This does not create coil geometry."""
        return await worker_call(
            "maxwell_assign_coil", pid=pid, port=port, timeout=timeout,
            arguments={
                "project_name": project_name,
                "design_name": design_name,
                "assignment": assignment,
                "name": name,
                "conductors_number": conductors_number,
                "polarity": polarity,
            },
        )

    @mcp.tool()
    async def maxwell_assign_winding(
        project_name: str,
        design_name: str,
        name: str,
        winding_type: Literal['Current', 'Voltage', 'External'] = 'Current',
        is_solid: bool = False,
        current: Scalar = '0A',
        resistance: Scalar = '0ohm',
        inductance: Scalar = '0H',
        voltage: Scalar = '0V',
        parallel_branches: int = 1,
        phase: Scalar = '0deg',
        pid: int | None = None,
        port: int | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Create a named winding group without implicitly creating terminals. Link previously assigned coils with maxwell_add_winding_coils. is_solid=false means stranded. Numeric values use A, ohm, H, V and degrees; strings may contain units or AEDT expressions. External windings require a separately configured external circuit."""
        return await worker_call(
            "maxwell_assign_winding", pid=pid, port=port, timeout=timeout,
            arguments={
                "project_name": project_name,
                "design_name": design_name,
                "name": name,
                "winding_type": winding_type,
                "is_solid": is_solid,
                "current": current,
                "resistance": resistance,
                "inductance": inductance,
                "voltage": voltage,
                "parallel_branches": parallel_branches,
                "phase": phase,
            },
        )

    @mcp.tool()
    async def maxwell_add_winding_coils(
        project_name: str,
        design_name: str,
        winding_name: str,
        coils: list[str],
        pid: int | None = None,
        port: int | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Link existing named coil terminals to an existing winding. Reject missing or incorrectly typed boundaries. API acceptance is reported separately from native association verification; inspect the actual winding terminal relationship in AEDT."""
        return await worker_call(
            "maxwell_add_winding_coils", pid=pid, port=port, timeout=timeout,
            arguments={
                "project_name": project_name,
                "design_name": design_name,
                "winding_name": winding_name,
                "coils": coils,
            },
        )

    @mcp.tool()
    async def maxwell_assign_current(
        project_name: str,
        design_name: str,
        assignment: list[str | int],
        name: str,
        amplitude: Scalar = '1A',
        phase: str = '0deg',
        solid: bool = True,
        swap_direction: bool = False,
        pid: int | None = None,
        port: int | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Assign a direct magnetic current excitation on existing objects/3D faces. Numeric amplitude uses amperes; strings may contain units or expressions. For windings with turns use the coil/winding tools instead."""
        return await worker_call(
            "maxwell_assign_current", pid=pid, port=port, timeout=timeout,
            arguments={
                "project_name": project_name,
                "design_name": design_name,
                "assignment": assignment,
                "name": name,
                "amplitude": amplitude,
                "phase": phase,
                "solid": solid,
                "swap_direction": swap_direction,
            },
        )

    @mcp.tool()
    async def maxwell_assign_rotate_motion(
        project_name: str,
        design_name: str,
        band_object: str,
        angular_velocity: Scalar,
        coordinate_system: str = 'Global',
        axis: Literal['X', 'Y', 'Z'] = 'Z',
        positive_movement: bool = True,
        start_position: Scalar = '0deg',
        has_rotation_limits: bool = False,
        negative_limit: Scalar = '0deg',
        positive_limit: Scalar = '360deg',
        non_cylindrical: bool = False,
        mechanical_transient: bool = False,
        inertia: float = 1.0,
        damping: float = 0.0,
        load_torque: Scalar = '0NewtonMeter',
        pid: int | None = None,
        port: int | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Assign rotation to an EXISTING enclosing band in a magnetic Transient design. Create and review band geometry first: it must contain all moving objects. Numeric angular velocity uses rpm, angles use degrees, inertia uses kg*m^2. A returned motion object does not verify containment or mesh topology."""
        return await worker_call(
            "maxwell_assign_rotate_motion", pid=pid, port=port, timeout=timeout,
            arguments={
                "project_name": project_name,
                "design_name": design_name,
                "band_object": band_object,
                "angular_velocity": angular_velocity,
                "coordinate_system": coordinate_system,
                "axis": axis,
                "positive_movement": positive_movement,
                "start_position": start_position,
                "has_rotation_limits": has_rotation_limits,
                "negative_limit": negative_limit,
                "positive_limit": positive_limit,
                "non_cylindrical": non_cylindrical,
                "mechanical_transient": mechanical_transient,
                "inertia": inertia,
                "damping": damping,
                "load_torque": load_torque,
            },
        )

    @mcp.tool()
    async def maxwell_assign_translate_motion(
        project_name: str,
        design_name: str,
        band_object: str,
        motion_name: str,
        velocity: Scalar,
        coordinate_system: str = 'Global',
        axis: Literal['X', 'Y', 'Z'] = 'X',
        positive_movement: bool = True,
        start_position: Scalar = '0mm',
        periodic_translate: bool = False,
        negative_limit: Scalar = '0mm',
        positive_limit: Scalar = '0mm',
        mechanical_transient: bool = False,
        mass: Scalar = '1kg',
        damping: float = 0.0,
        load_force: Scalar = '0newton',
        pid: int | None = None,
        port: int | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Assign translation to an EXISTING enclosing band in a magnetic Transient design. Review travel limits and band containment before solving. Numeric positions use model units, velocity uses m/s, mass uses kg, load_force uses newtons. No geometry enclosure validation is implied."""
        return await worker_call(
            "maxwell_assign_translate_motion", pid=pid, port=port, timeout=timeout,
            arguments={
                "project_name": project_name,
                "design_name": design_name,
                "band_object": band_object,
                "motion_name": motion_name,
                "velocity": velocity,
                "coordinate_system": coordinate_system,
                "axis": axis,
                "positive_movement": positive_movement,
                "start_position": start_position,
                "periodic_translate": periodic_translate,
                "negative_limit": negative_limit,
                "positive_limit": positive_limit,
                "mechanical_transient": mechanical_transient,
                "mass": mass,
                "damping": damping,
                "load_force": load_force,
            },
        )

    @mcp.tool()
    async def maxwell_assign_force(
        project_name: str,
        design_name: str,
        assignment: list[str],
        name: str,
        coordinate_system: str = 'Global',
        is_virtual: bool = True,
        pid: int | None = None,
        port: int | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Create an electromagnetic force calculation parameter on existing objects. is_virtual selects virtual/Lorentz force where the selected solver supports it; effective settings are returned from PyAEDT/native properties."""
        return await worker_call(
            "maxwell_assign_force", pid=pid, port=port, timeout=timeout,
            arguments={
                "project_name": project_name,
                "design_name": design_name,
                "assignment": assignment,
                "name": name,
                "coordinate_system": coordinate_system,
                "is_virtual": is_virtual,
            },
        )

    @mcp.tool()
    async def maxwell_assign_torque(
        project_name: str,
        design_name: str,
        assignment: list[str],
        name: str,
        coordinate_system: str = 'Global',
        axis: Literal['X', 'Y', 'Z'] = 'Z',
        is_positive: bool = True,
        is_virtual: bool = True,
        pid: int | None = None,
        port: int | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Create an electromagnetic torque calculation parameter on existing objects. Coordinate system, axis and sign must match the engineering question. Transient solvers may force virtual torque; inspect returned effective properties."""
        return await worker_call(
            "maxwell_assign_torque", pid=pid, port=port, timeout=timeout,
            arguments={
                "project_name": project_name,
                "design_name": design_name,
                "assignment": assignment,
                "name": name,
                "coordinate_system": coordinate_system,
                "axis": axis,
                "is_positive": is_positive,
                "is_virtual": is_virtual,
            },
        )

    @mcp.tool()
    async def maxwell_set_eddy_effects(
        project_name: str,
        design_name: str,
        assignment: list[str],
        enable_eddy_effects: bool = True,
        enable_displacement_current: bool = False,
        pid: int | None = None,
        port: int | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Set eddy effects on existing conductors in AC Magnetic/EddyCurrent or magnetic Transient. Return native GetEddyEffect readback per object. Displacement-current support is solver-dependent and is not independently confirmed by this tool."""
        return await worker_call(
            "maxwell_set_eddy_effects", pid=pid, port=port, timeout=timeout,
            arguments={
                "project_name": project_name,
                "design_name": design_name,
                "assignment": assignment,
                "enable_eddy_effects": enable_eddy_effects,
                "enable_displacement_current": enable_displacement_current,
            },
        )

    @mcp.tool()
    async def maxwell_create_setup(
        project_name: str,
        design_name: str,
        name: str,
        properties: dict[str, Any],
        pid: int | None = None,
        port: int | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Create a named Maxwell setup using the current solution's native template. Reject unknown top-level properties and duplicate setup names. Examples: transient StopTime/TimeStep; static MaximumPasses/PercentError; AC Frequency. Use native property names and explicit units. Does not start a solve."""
        return await worker_call(
            "maxwell_create_setup", pid=pid, port=port, timeout=timeout,
            arguments={
                "project_name": project_name,
                "design_name": design_name,
                "name": name,
                "properties": properties,
            },
        )

    @mcp.tool()
    async def maxwell_assign_length_mesh(
        project_name: str,
        design_name: str,
        assignment: list[str | int],
        name: str,
        maximum_length: Scalar,
        inside_selection: bool = True,
        maximum_elements: int | None = None,
        pid: int | None = None,
        port: int | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Assign named local length mesh refinement on existing objects/3D faces. Numeric maximum_length uses model units; explicit units are preferred. Face selections require inside_selection=false. This creates a mesh operation, not a generated or validated mesh."""
        return await worker_call(
            "maxwell_assign_length_mesh", pid=pid, port=port, timeout=timeout,
            arguments={
                "project_name": project_name,
                "design_name": design_name,
                "assignment": assignment,
                "name": name,
                "maximum_length": maximum_length,
                "inside_selection": inside_selection,
                "maximum_elements": maximum_elements,
            },
        )

    @mcp.tool()
    async def maxwell_get_design_info(
        project_name: str,
        design_name: str,
        pid: int | None = None,
        port: int | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Read Maxwell objects, units, coil/winding/motion/force/torque boundaries, setups and mesh operations. Separate cached api_properties from native_properties and readback_confirmed."""
        return await worker_call(
            "maxwell_get_design_info", pid=pid, port=port, timeout=timeout,
            arguments={
                "project_name": project_name,
                "design_name": design_name,
            },
        )

    @mcp.tool()
    async def maxwell_get_analysis_status(
        project_name: str,
        design_name: str,
        setup_name: str,
        pid: int | None = None,
        port: int | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Read desktop-wide simulation activity and result availability for one existing Maxwell setup. Idle desktop or existing result data cannot confirm completion/convergence of the latest solve. solver_completion_confirmed remains false."""
        return await worker_call(
            "maxwell_get_analysis_status", pid=pid, port=port, timeout=timeout,
            arguments={
                "project_name": project_name,
                "design_name": design_name,
                "setup_name": setup_name,
            },
        )

    @mcp.tool()
    async def maxwell_get_solution_data(
        project_name: str,
        design_name: str,
        expressions: list[str],
        setup_sweep_name: str,
        domain: Literal['Time', 'Sweep'] | None = None,
        variations: dict[str, list[str]] | None = None,
        primary_sweep_variable: str | None = None,
        report_category: str | None = None,
        max_points: int = 2000,
        pid: int | None = None,
        port: int | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Read solved Maxwell numerical curves (e.g. torque, force, losses or winding quantities) by exact AEDT expression names. Return real/imaginary arrays, sweep units and actual active variation. At most 100 expressions/10000 points per expression; truncation is explicit. Data can be from an earlier solve; no completion claim is made."""
        return await worker_call(
            "maxwell_get_solution_data", pid=pid, port=port, timeout=timeout,
            arguments={
                "project_name": project_name,
                "design_name": design_name,
                "expressions": expressions,
                "setup_sweep_name": setup_sweep_name,
                "domain": domain,
                "variations": variations,
                "primary_sweep_variable": primary_sweep_variable,
                "report_category": report_category,
                "max_points": max_points,
            },
        )

    @mcp.tool()
    async def maxwell_create_field_plot(
        project_name: str,
        design_name: str,
        assignment: list[str | int],
        quantity: str,
        setup_sweep_name: str,
        name: str,
        plot_type: Literal['surface', 'volume'] = 'surface',
        intrinsics: dict[str, str] | None = None,
        pid: int | None = None,
        port: int | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Create a Maxwell surface/3D volume field plot for an explicit setup/sweep and quantity (e.g. Mag_B). Specify Time/Freq/Phase intrinsics as applicable. 2D accepts object names and surface plots. The plot alone does not verify solver completion or engineering validity."""
        return await worker_call(
            "maxwell_create_field_plot", pid=pid, port=port, timeout=timeout,
            arguments={
                "project_name": project_name,
                "design_name": design_name,
                "assignment": assignment,
                "quantity": quantity,
                "setup_sweep_name": setup_sweep_name,
                "name": name,
                "plot_type": plot_type,
                "intrinsics": intrinsics,
            },
        )
