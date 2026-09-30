"""Structured Maxwell operations on an existing, explicitly selected design."""
from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from typing import Any

from pyaedt_capabilities import CapabilityError, json_safe


MAXWELL_COMMANDS = {
    "maxwell_assign_coil", "maxwell_assign_winding", "maxwell_add_winding_coils",
    "maxwell_assign_current", "maxwell_assign_rotate_motion",
    "maxwell_assign_translate_motion", "maxwell_assign_force", "maxwell_assign_torque",
    "maxwell_set_eddy_effects", "maxwell_create_setup", "maxwell_assign_length_mesh",
    "maxwell_get_design_info", "maxwell_get_analysis_status",
    "maxwell_get_solution_data", "maxwell_create_field_plot",
}


def text_arg(arguments: Mapping[str, Any], name: str) -> str:
    value = arguments.get(name)
    if not isinstance(value, str) or not value.strip():
        raise CapabilityError(f"{name} must be a non-empty string")
    return value.strip()


def choice(arguments: Mapping[str, Any], name: str, options: set[str]) -> str:
    value = text_arg(arguments, name)
    if value not in options:
        raise CapabilityError(f"{name} must be one of {', '.join(sorted(options))}")
    return value


def positive_int(arguments: Mapping[str, Any], name: str) -> int:
    value = arguments.get(name)
    if type(value) is not int or value <= 0:
        raise CapabilityError(f"{name} must be a positive integer")
    return value


def scalar(value: Any, name: str) -> int | float | str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if type(value) in {int, float} and math.isfinite(value):
        return value
    raise CapabilityError(f"{name} must be a finite number or non-empty AEDT expression")


def string_list(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or not value or len(value) > 1000:
        raise CapabilityError(f"{name} must be a non-empty list of at most 1000 names")
    names = [text_arg({name: item}, name) for item in value]
    if len(set(names)) != len(names):
        raise CapabilityError(f"{name} contains duplicates")
    return names


def snapshot(item: Any) -> dict[str, Any]:
    """Keep native readback separate from PyAEDT's cached request properties."""
    result = {
        "name": str(item.name),
        "type": str(getattr(item, "type", type(item).__name__)),
        "api_properties": json_safe(getattr(item, "props", {})),
        "native_properties": {},
        "readback_confirmed": False,
    }
    try:
        child = getattr(item, "child_object", None)
        if child is None:
            # Boundary constructors initialize their tree node before create().
            # Re-resolve the native node after creation instead of using that cache.
            child = getattr(item, "_child_object", None)
        if child is None:
            result["readback_error"] = "Native property object is unavailable"
            return result
        keys = list(child.GetPropNames())
        values = {str(key): child.GetPropValue(key) for key in keys}
        result["native_properties"] = json_safe(values)
        result["readback_confirmed"] = bool(keys) and all(v is not None for v in values.values())
    except Exception as exc:  # Native property support varies by solver/version.
        result["readback_error"] = str(exc)
    return result


class MaxwellCapabilities:
    def __init__(self, *, app_resolver: Callable[..., Any]) -> None:
        self._app_resolver = app_resolver

    def execute(self, command, *, desktop, target, arguments) -> dict[str, Any]:
        if command not in MAXWELL_COMMANDS:
            raise CapabilityError(f"unsupported Maxwell command: {command}")
        project = text_arg(arguments, "project_name")
        design = text_arg(arguments, "design_name")
        if project not in list(desktop.project_list):
            raise CapabilityError(f"project is not open in selected AEDT session: {project}")
        if design not in list(desktop.design_list(project)):
            raise CapabilityError(f"design does not exist in project {project}: {design}")
        if desktop.design_type(project, design) not in {"Maxwell 2D", "Maxwell 3D"}:
            raise CapabilityError("Maxwell tools require a Maxwell 2D or Maxwell 3D design")
        app = self._app_resolver(desktop, project, design)
        if (app.project_name, app.design_name) != (project, design):
            raise CapabilityError("Resolved PyAEDT application does not match requested project/design")
        if app.design_type not in {"Maxwell 2D", "Maxwell 3D"}:
            raise CapabilityError("Resolved PyAEDT application is not Maxwell")
        self._validate_values(arguments)
        result = getattr(self, f"_{command}")(app, arguments)
        return json_safe({
            "target": {"kind": target.kind, "value": target.value},
            "project_name": project, "design_name": design,
            "design_type": app.design_type, "solution_type": app.solution_type,
            **result,
        })

    @staticmethod
    def _validate_values(arguments):
        bools = {
            "is_solid", "solid", "swap_direction", "positive_movement",
            "has_rotation_limits", "non_cylindrical", "mechanical_transient",
            "periodic_translate", "is_virtual", "is_positive", "enable_eddy_effects",
            "enable_displacement_current", "inside_selection",
        }
        scalars = {
            "current", "resistance", "inductance", "voltage", "phase", "amplitude",
            "start_position", "negative_limit", "positive_limit", "angular_velocity",
            "load_torque", "velocity", "mass", "load_force", "maximum_length",
        }
        for key, value in arguments.items():
            if key in bools and type(value) is not bool:
                raise CapabilityError(f"{key} must be a boolean")
            if key in scalars:
                scalar(value, key)
            if key in {"inertia", "damping"}:
                if type(value) not in {int, float} or not math.isfinite(value) or value < 0:
                    raise CapabilityError(f"{key} must be a finite non-negative number")

    @staticmethod
    def _magnetic(app):
        solution = app.solution_type.replace(" ", "").lower()
        if not (solution == "magnetostatic" or solution.startswith(("eddycurrent", "acmagnetic", "transient"))):
            raise CapabilityError(f"Magnetic excitation is unavailable for solution type {app.solution_type}")

    @staticmethod
    def _transient(app):
        # PyAEDT 1.5.0's motion methods require the normalized Transient type.
        if app.solution_type != "Transient":
            raise CapabilityError("Motion bands require a magnetic Transient design")

    @staticmethod
    def _selection(app, arguments, *, faces=True) -> list[str | int]:
        values = arguments.get("assignment")
        if not isinstance(values, list) or not values or len(values) > 1000:
            raise CapabilityError("assignment must be a non-empty list of at most 1000 object names or face IDs")
        names = all(isinstance(v, str) and v.strip() for v in values)
        ids = all(type(v) is int and v > 0 for v in values)
        if not names and not ids:
            raise CapabilityError("assignment must contain only object names or only positive face IDs")
        values = [v.strip() if isinstance(v, str) else v for v in values]
        if len(set(values)) != len(values):
            raise CapabilityError("assignment contains duplicates")
        if names:
            missing = set(values) - set(app.modeler.object_names)
            if missing:
                raise CapabilityError(f"Unknown model objects: {', '.join(sorted(missing))}")
        else:
            if not faces or app.design_type == "Maxwell 2D":
                raise CapabilityError("This operation requires object names; face IDs are unavailable")
            available = {face for name in app.modeler.object_names for face in app.modeler.get_object_faces(name)}
            if set(values) - available:
                raise CapabilityError("assignment contains face IDs absent from selected design")
        return values

    @staticmethod
    def _unique(app, name, items=None):
        if name in {item.name for item in (app.boundaries if items is None else items)}:
            raise CapabilityError(f"Name already exists in selected design: {name}")

    @staticmethod
    def _coordinate_system(app, arguments):
        cs = text_arg(arguments, "coordinate_system")
        available = {"Global", *(item.name for item in app.modeler.coordinate_systems)}
        if cs not in available:
            raise CapabilityError(f"Unknown coordinate system: {cs}")
        if "axis" in arguments:
            choice(arguments, "axis", {"X", "Y", "Z"})
        return cs

    @staticmethod
    def _created(item, method):
        if item is None or item is False or not getattr(item, "name", None):
            raise CapabilityError(f"PyAEDT {method} did not return a created object; inspect AEDT logs")
        return {"api_accepted": True, "object": snapshot(item)}

    def _maxwell_assign_coil(self, app, a):
        self._magnetic(app)
        name = text_arg(a, "name")
        self._unique(app, name)
        kwargs = {
            "assignment": self._selection(app, a), "name": name,
            "conductors_number": positive_int(a, "conductors_number"),
            "polarity": choice(a, "polarity", {"Positive", "Negative"}),
        }
        return self._created(app.assign_coil(**kwargs), "assign_coil")

    def _maxwell_assign_winding(self, app, a):
        self._magnetic(app)
        name = text_arg(a, "name")
        self._unique(app, name)
        kwargs = {key: a[key] for key in ("is_solid", "current", "resistance", "inductance", "voltage", "phase")}
        kwargs.update(name=name, assignment=None,
                      winding_type=choice(a, "winding_type", {"Current", "Voltage", "External"}),
                      parallel_branches=positive_int(a, "parallel_branches"))
        return self._created(app.assign_winding(**kwargs), "assign_winding")

    def _maxwell_add_winding_coils(self, app, a):
        self._magnetic(app)
        winding = text_arg(a, "winding_name")
        coils = string_list(a.get("coils"), "coils")
        boundaries = {item.name: item for item in app.boundaries}
        if winding not in boundaries or boundaries[winding].type not in {"Winding", "Winding Group"}:
            raise CapabilityError("winding_name must identify an existing winding")
        if any(name not in boundaries or boundaries[name].type not in {"Coil", "CoilTerminal", "Coil Terminal"} for name in coils):
            raise CapabilityError("coils must identify existing coil terminals")
        if app.add_winding_coils(assignment=winding, coils=coils) is not True:
            raise CapabilityError("PyAEDT add_winding_coils failed; inspect AEDT logs")
        result = {
            "api_accepted": True, "winding_name": winding, "requested_coils": coils,
            "winding": snapshot(boundaries[winding]), "association_confirmed": False,
            "verification_note": "Review winding terminal membership if native child-name readback cannot confirm the requested coils.",
        }
        try:
            item = boundaries[winding]
            child = getattr(item, "_child_object", None)
            if child is None:
                child = getattr(item, "child_object", None)
            children = list(child.GetChildNames())
            result["native_winding_children"] = children
            result["association_confirmed"] = set(coils).issubset(children)
        except Exception as exc:
            result["association_readback_error"] = str(exc)
        return result

    def _maxwell_assign_current(self, app, a):
        self._magnetic(app)
        name = text_arg(a, "name")
        self._unique(app, name)
        kwargs = {key: a[key] for key in ("amplitude", "phase", "solid", "swap_direction")}
        kwargs.update(assignment=self._selection(app, a), name=name)
        return self._created(app.assign_current(**kwargs), "assign_current")

    def _motion(self, app, a, rotate):
        self._transient(app)
        band = text_arg(a, "band_object")
        self._selection(app, {"assignment": [band]}, faces=False)
        cs = self._coordinate_system(app, a)
        keys = ["axis", "positive_movement", "start_position", "negative_limit", "positive_limit", "mechanical_transient", "damping"]
        keys += (["has_rotation_limits", "non_cylindrical", "angular_velocity", "inertia", "load_torque"]
                 if rotate else ["periodic_translate", "velocity", "mass", "load_force"])
        kwargs = {key: a[key] for key in keys}
        kwargs.update(assignment=band, coordinate_system=cs)
        if not rotate:
            name = text_arg(a, "motion_name")
            self._unique(app, name)
            kwargs["motion_name"] = name
        existing = [b for b in app.boundaries if b.type in {"Band", "MotionSetup"}]
        for boundary in existing:
            assigned = boundary.props.get("Objects", [])
            if band in ([assigned] if isinstance(assigned, str) else assigned):
                raise CapabilityError(f"Band object already has a motion assignment: {band}")
        method = "assign_rotate_motion" if rotate else "assign_translate_motion"
        result = self._created(getattr(app, method)(**kwargs), method)
        result.update(band_object=band, geometry_enclosure_verified=False,
                      verification_note="The existing band must enclose all moving objects; geometry/topology and clearances require review.")
        return result

    def _maxwell_assign_rotate_motion(self, app, a):
        return self._motion(app, a, True)

    def _maxwell_assign_translate_motion(self, app, a):
        return self._motion(app, a, False)

    def _maxwell_assign_force(self, app, a):
        name = text_arg(a, "name")
        self._unique(app, name)
        cs = self._coordinate_system(app, a)
        return self._created(app.assign_force(
            assignment=self._selection(app, a, faces=False), coordinate_system=cs,
            is_virtual=a["is_virtual"], force_name=name), "assign_force")

    def _maxwell_assign_torque(self, app, a):
        name = text_arg(a, "name")
        self._unique(app, name)
        cs = self._coordinate_system(app, a)
        return self._created(app.assign_torque(
            assignment=self._selection(app, a, faces=False), coordinate_system=cs,
            is_positive=a["is_positive"], is_virtual=a["is_virtual"], axis=a["axis"],
            torque_name=name), "assign_torque")

    def _maxwell_set_eddy_effects(self, app, a):
        solution = app.solution_type.replace(" ", "").lower()
        if not solution.startswith(("eddycurrent", "acmagnetic", "transient")):
            raise CapabilityError("Eddy effects require AC Magnetic/EddyCurrent or magnetic Transient")
        selection = self._selection(app, a, faces=False)
        if set(selection) - set(app.get_all_conductors_names()):
            raise CapabilityError("Eddy effects require conductor objects")
        accepted = app.eddy_effects_on(
            assignment=selection, enable_eddy_effects=a["enable_eddy_effects"],
            enable_displacement_current=a["enable_displacement_current"])
        if accepted is not True:
            raise CapabilityError("PyAEDT eddy_effects_on failed; inspect AEDT logs")
        values, errors = {}, {}
        for name in selection:
            try:
                value = app.oboundary.GetEddyEffect(name)
                if type(value) not in {bool, int} or value not in (0, 1):
                    raise ValueError("Native eddy effect value is unavailable")
                values[name] = bool(value)
            except Exception as exc:
                errors[name] = str(exc)
        return {"api_accepted": True, "eddy_effects": values, "readback_errors": errors,
                "readback_confirmed": not errors and all(v == a["enable_eddy_effects"] for v in values.values()),
                "displacement_current_confirmed": False}

    def _maxwell_create_setup(self, app, a):
        name = text_arg(a, "name")
        if name in list(app.get_setups()):
            raise CapabilityError(f"Setup already exists: {name}")
        props = a.get("properties")
        if not isinstance(props, dict) or not props:
            raise CapabilityError("properties must be a non-empty mapping of native setup properties")
        from ansys.aedt.core.modules.setup_templates import SetupKeys

        template = SetupKeys.get_setup_templates()[app.design_solutions.default_setup]
        unknown = set(props) - set(template)
        if unknown:
            raise CapabilityError(f"Unsupported setup properties for this solution: {', '.join(sorted(unknown))}")
        if any(key in props for key in {"Name", "name"}):
            raise CapabilityError("Set the setup name using name, not properties")
        result = self._created(app.create_setup(name=name, props=props), "create_setup")
        result["requested_properties"] = props
        result["setup_list_confirmed"] = name in list(app.get_setups())
        return result

    def _maxwell_assign_length_mesh(self, app, a):
        name = text_arg(a, "name")
        self._unique(app, name, app.mesh.meshoperations)
        selection = self._selection(app, a)
        if isinstance(selection[0], int) and a["inside_selection"]:
            raise CapabilityError("Face mesh selections require inside_selection=false")
        length = scalar(a["maximum_length"], "maximum_length")
        if type(length) in {int, float} and length <= 0:
            raise CapabilityError("maximum_length must be positive")
        elements = a.get("maximum_elements")
        if elements is not None:
            positive_int(a, "maximum_elements")
        return self._created(app.mesh.assign_length_mesh(
            assignment=selection, inside_selection=a["inside_selection"], maximum_length=length,
            maximum_elements=elements, name=name), "assign_length_mesh")

    def _maxwell_get_design_info(self, app, a):
        return {
            "model_units": app.modeler.model_units, "objects": list(app.modeler.object_names),
            "boundaries": [snapshot(item) for item in app.boundaries],
            "setups": [snapshot(app.get_setup(name)) for name in app.get_setups()],
            "mesh_operations": [snapshot(item) for item in app.mesh.meshoperations],
        }

    def _maxwell_get_analysis_status(self, app, a):
        setup_name = text_arg(a, "setup_name")
        if setup_name not in list(app.get_setups()):
            raise CapabilityError(f"Setup does not exist: {setup_name}")
        running = app.desktop_class.are_there_simulations_running
        if callable(running):
            running = running()
        if type(running) not in {bool, int, float} or not math.isfinite(running) or running < 0:
            raise CapabilityError("Native simulation running state is unavailable")
        data_available, error = None, None
        try:
            available = app.get_setup(setup_name).is_solved
            if type(available) is bool:
                data_available = available
            else:
                error = "Native setup solution availability is unavailable"
        except Exception as exc:
            error = str(exc)
        return {
            "setup_name": setup_name, "desktop_simulations_running": bool(running),
            "running_scope": "selected AEDT desktop, not just this design/setup",
            "solution_data_available": data_available, "solution_probe_error": error,
            "solver_completion_confirmed": False,
            "verification_note": "Existing results can be stale. Idle desktop and result availability do not establish completion of the latest solve or convergence.",
        }

    def _maxwell_get_solution_data(self, app, a):
        expressions = string_list(a.get("expressions"), "expressions")
        sweep = text_arg(a, "setup_sweep_name")
        if sweep not in list(app.existing_analysis_sweeps):
            raise CapabilityError(f"Unknown setup/sweep: {sweep}")
        limit = positive_int(a, "max_points")
        if limit > 10000 or len(expressions) > 100:
            raise CapabilityError("At most 100 expressions and 10000 points per expression are allowed")
        kwargs = {key: a[key] for key in ("domain", "variations", "primary_sweep_variable", "report_category") if a.get(key) is not None}
        if "domain" in kwargs:
            choice(a, "domain", {"Time", "Sweep"})
        variations = kwargs.get("variations")
        if variations is not None and (not isinstance(variations, dict) or any(
                not isinstance(key, str) or not isinstance(values, list) or not values or
                any(not isinstance(v, str) or not v.strip() for v in values)
                for key, values in variations.items())):
            raise CapabilityError("variations must map names to non-empty lists of AEDT value strings")
        data = app.post.get_solution_data(expressions=expressions, setup_sweep_name=sweep, **kwargs)
        if data is None or data is False:
            raise CapabilityError("No solution data returned; inspect solved setup, expressions and variations")
        curves = {}
        for expression in expressions:
            if expression not in data.expressions:
                raise CapabilityError(f"Requested expression absent from returned solution: {expression}")
            x, real = data.get_expression_data(expression=expression, formula="real")
            xi, imag = data.get_expression_data(expression=expression, formula="imag")
            x, xi, real, imag = [v.tolist() if hasattr(v, "tolist") else list(v) for v in (x, xi, real, imag)]
            if not x or x != xi or len(x) != len(real) or len(x) != len(imag):
                raise CapabilityError(f"Empty or inconsistent solution arrays for {expression}")
            if any(type(value) not in {int, float} or not math.isfinite(value)
                   for values in (x, real, imag) for value in values):
                raise CapabilityError(f"Non-finite or non-numeric solution arrays for {expression}")
            curves[expression] = {
                "x": x[:limit], "real": real[:limit], "imag": imag[:limit],
                "unit": data.units_data.get(expression), "total_points": len(x), "truncated": len(x) > limit,
            }
        return {
            "setup_sweep_name": sweep, "primary_sweep": data.primary_sweep,
            "sweep_unit": data.units_sweeps.get(data.primary_sweep),
            "active_variation": data.active_variation,
            "available_variations": data.variations,
            "curves": curves, "solver_completion_confirmed": False,
        }

    def _maxwell_create_field_plot(self, app, a):
        sweep = text_arg(a, "setup_sweep_name")
        if sweep not in list(app.existing_analysis_sweeps):
            raise CapabilityError(f"Unknown setup/sweep: {sweep}")
        name = text_arg(a, "name")
        if name in app.post.field_plots:
            raise CapabilityError(f"Field plot already exists: {name}")
        kind = choice(a, "plot_type", {"surface", "volume"})
        if kind == "volume" and app.design_type == "Maxwell 2D":
            raise CapabilityError("Volume plots require Maxwell 3D; use surface for Maxwell 2D")
        selection = self._selection(app, a, faces=kind == "surface")
        intrinsics = a.get("intrinsics")
        if intrinsics is not None and (not isinstance(intrinsics, dict) or any(
                key not in {"Time", "Freq", "Phase"} or not isinstance(value, str) or not value.strip()
                for key, value in intrinsics.items())):
            raise CapabilityError("intrinsics must map Time, Freq or Phase to AEDT value strings")
        method = f"create_fieldplot_{kind}"
        result = self._created(getattr(app.post, method)(
            assignment=selection, quantity=text_arg(a, "quantity"), setup=sweep,
            intrinsics=intrinsics, plot_name=name), method)
        result.update(setup_sweep_name=sweep, intrinsics=intrinsics, solver_completion_confirmed=False)
        return result
