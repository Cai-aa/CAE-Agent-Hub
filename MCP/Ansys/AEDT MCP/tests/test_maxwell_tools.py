"""Offline contract/guard tests; these do not validate a live Maxwell solve."""
import inspect
import unittest
from types import SimpleNamespace

import mcp_server
from aedt_target import AedtTarget
from maxwell_capabilities import MAXWELL_COMMANDS
from maxwell_tools import register_maxwell_tools
from pyaedt_backend import BackendCommandError, PyAedtBackend
from pyaedt_capabilities import OfficialCapabilities


class Registry:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def register(fn):
            self.tools[fn.__name__] = fn
            return fn
        return register


class NativeProperties:
    def __init__(self, props):
        self.props = dict(props)

    def GetPropNames(self):
        return list(self.props)

    def GetPropValue(self, key):
        return self.props[key]


class Item:
    def __init__(self, name, kind, props):
        self.name = name
        self.type = kind
        self.props = props
        self.child_object = NativeProperties({"Type": kind, **props})
        self.is_solved = True


class Modeler:
    object_names = ["Terminal", "Rotor", "Band", "Copper"]
    model_units = "mm"
    coordinate_systems = [SimpleNamespace(name="RotorCS")]

    def get_object_faces(self, name):
        return [self.object_names.index(name) + 10]


class Solution:
    expressions = ["Torque1.Torque"]
    units_data = {"Torque1.Torque": "NewtonMeter"}
    primary_sweep = "Time"
    units_sweeps = {"Time": "s"}
    active_variation = {"speed": "1000rpm"}
    variations = [active_variation, {"speed": "2000rpm"}]

    def get_expression_data(self, expression, formula):
        return [0.0, 0.1, 0.2], [1.0, 2.0, 3.0] if formula == "real" else [0.0, 0.0, 0.0]


class App:
    project_name = "Motor"
    design_name = "Maxwell"
    design_type = "Maxwell 3D"
    solution_type = "Transient"

    def __init__(self):
        self.calls = []
        self.boundaries = []
        self.modeler = Modeler()
        self.mesh = SimpleNamespace(meshoperations=[], assign_length_mesh=self.assign_length_mesh)
        self.post = SimpleNamespace(
            field_plots={}, get_solution_data=self.get_solution_data,
            create_fieldplot_surface=self.create_fieldplot_surface,
            create_fieldplot_volume=self.create_fieldplot_volume,
        )
        self.desktop_class = SimpleNamespace(are_there_simulations_running=False)
        self.design_solutions = SimpleNamespace(default_setup=5)
        self.oboundary = SimpleNamespace(GetEddyEffect=lambda name: True)
        self.setups = {"Setup1": Item("Setup1", "Setup", {"TimeStep": "1ms"})}
        self.existing_analysis_sweeps = ["Setup1 : Transient"]
        self.fail = None
        self.solution = Solution()

    def _create(self, method, kind, name, kwargs):
        self.calls.append((method, dict(kwargs)))
        if self.fail == method:
            return False
        item = Item(name, kind, kwargs)
        self.boundaries.append(item)
        return item

    def assign_coil(self, **kwargs):
        return self._create("assign_coil", "CoilTerminal", kwargs["name"], kwargs)

    def assign_winding(self, **kwargs):
        return self._create("assign_winding", "Winding", kwargs["name"], kwargs)

    def add_winding_coils(self, **kwargs):
        self.calls.append(("add_winding_coils", kwargs))
        return self.fail != "add_winding_coils"

    def assign_current(self, **kwargs):
        return self._create("assign_current", "Current", kwargs["name"], kwargs)

    def assign_rotate_motion(self, **kwargs):
        item = self._create("assign_rotate_motion", "Band", "MotionSetup1", kwargs)
        if item:
            item.props["Objects"] = [kwargs["assignment"]]
        return item

    def assign_translate_motion(self, **kwargs):
        item = self._create("assign_translate_motion", "Band", kwargs["motion_name"], kwargs)
        if item:
            item.props["Objects"] = [kwargs["assignment"]]
        return item

    def assign_force(self, **kwargs):
        return self._create("assign_force", "Force", kwargs["force_name"], kwargs)

    def assign_torque(self, **kwargs):
        return self._create("assign_torque", "Torque", kwargs["torque_name"], kwargs)

    def get_all_conductors_names(self):
        return ["Copper"]

    def eddy_effects_on(self, **kwargs):
        self.calls.append(("eddy_effects_on", kwargs))
        return self.fail != "eddy_effects_on"

    def create_setup(self, **kwargs):
        item = self._create("create_setup", "Setup", kwargs["name"], kwargs["props"])
        if item:
            self.setups[item.name] = item
        return item

    def get_setups(self):
        return list(self.setups)

    def get_setup(self, name):
        return self.setups[name]

    def assign_length_mesh(self, **kwargs):
        item = self._create("assign_length_mesh", "LengthBased", kwargs["name"], kwargs)
        if item:
            self.mesh.meshoperations.append(item)
        return item

    def get_solution_data(self, **kwargs):
        self.calls.append(("get_solution_data", kwargs))
        return self.solution

    def create_fieldplot_surface(self, **kwargs):
        return self._create("create_fieldplot_surface", "FieldPlot", kwargs["plot_name"], kwargs)

    def create_fieldplot_volume(self, **kwargs):
        return self._create("create_fieldplot_volume", "FieldPlot", kwargs["plot_name"], kwargs)


class Desktop:
    project_list = ["Motor"]
    aedt_process_id = 100
    port = 50051

    def __init__(self, app):
        self.app = app

    def design_list(self, project):
        return ["Maxwell"]

    def design_type(self, project, design):
        return self.app.design_type


class MaxwellTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.app = App()
        self.desktop = Desktop(self.app)
        self.resolutions = []

        def resolve(**kwargs):
            self.resolutions.append(kwargs)
            return self.app

        self.backend = PyAedtBackend(
            desktop_factory=lambda **kwargs: self.desktop,
            official_capabilities=OfficialCapabilities(app_resolver=resolve),
        )
        self.registry = Registry()

        async def worker(command, *, pid, port, timeout, arguments):
            return self.backend.execute(AedtTarget.from_values(pid=pid, port=port), command, arguments)

        register_maxwell_tools(self.registry, worker)

    async def call(self, tool, **arguments):
        return await self.registry.tools[tool](project_name="Motor", design_name="Maxwell", port=50051, **arguments)

    async def test_registration_and_explicit_design_schema(self):
        tools = {tool.name: tool for tool in await mcp_server.mcp.list_tools()}
        self.assertEqual(len(tools), 45)
        self.assertEqual(set(self.registry.tools), MAXWELL_COMMANDS)
        for name in MAXWELL_COMMANDS:
            self.assertIn(name, tools)
            schema = tools[name].inputSchema
            self.assertTrue({"project_name", "design_name"}.issubset(schema["required"]))
            self.assertTrue({"pid", "port"}.issubset(schema["properties"]))

    async def test_coil_winding_link_preserves_turns_and_polarity(self):
        coil = await self.call("maxwell_assign_coil", assignment=[10], name="CoilA", conductors_number=25, polarity="Negative")
        winding = await self.call("maxwell_assign_winding", name="PhaseA", current="2A*sin(2*pi*50*time)")
        linked = await self.call("maxwell_add_winding_coils", winding_name="PhaseA", coils=["CoilA"])
        self.assertTrue(coil["object"]["readback_confirmed"])
        self.assertEqual(coil["object"]["api_properties"]["conductors_number"], 25)
        self.assertEqual(coil["object"]["native_properties"]["polarity"], "Negative")
        self.assertIsNone(winding["object"]["api_properties"]["assignment"])
        self.assertFalse(winding["object"]["api_properties"]["is_solid"])
        self.assertTrue(linked["api_accepted"])
        self.assertFalse(linked["association_confirmed"])
        self.assertEqual(self.app.calls[-1][1], {"assignment": "PhaseA", "coils": ["CoilA"]})

    async def test_winding_membership_requires_native_child_names(self):
        await self.call("maxwell_assign_coil", assignment=[10], name="C")
        await self.call("maxwell_assign_winding", name="W")
        winding = self.app.boundaries[-1]
        winding.child_object.GetChildNames = lambda: ["C"]
        result = await self.call("maxwell_add_winding_coils", winding_name="W", coils=["C"])
        self.assertTrue(result["association_confirmed"])
        winding.child_object.GetChildNames = lambda: []
        result = await self.call("maxwell_add_winding_coils", winding_name="W", coils=["C"])
        self.assertFalse(result["association_confirmed"])

    async def test_motion_tools_use_existing_band_and_report_geometry_limit(self):
        rotated = await self.call("maxwell_assign_rotate_motion", band_object="Band", angular_velocity="1000rpm", coordinate_system="RotorCS")
        self.assertFalse(rotated["geometry_enclosure_verified"])
        self.assertFalse(self.app.calls[-1][1]["has_rotation_limits"])
        self.assertEqual(self.app.calls[-1][1]["angular_velocity"], "1000rpm")
        with self.assertRaisesRegex(BackendCommandError, "already has a motion"):
            await self.call("maxwell_assign_rotate_motion", band_object="Band", angular_velocity="1000rpm")
        self.app.boundaries.clear()
        translated = await self.call("maxwell_assign_translate_motion", band_object="Band", motion_name="Travel", velocity="1m_per_sec", axis="X")
        self.assertEqual(translated["object"]["name"], "Travel")
        self.assertFalse(self.app.calls[-1][1]["periodic_translate"])

    async def test_current_force_torque_and_conductor_eddy_tools(self):
        for name, kwargs in [
            ("maxwell_assign_current", {"assignment": [10], "name": "Current1", "amplitude": "3A"}),
            ("maxwell_assign_force", {"assignment": ["Rotor"], "name": "Force1"}),
            ("maxwell_assign_torque", {"assignment": ["Rotor"], "name": "Torque1", "axis": "Z"}),
        ]:
            result = await self.call(name, **kwargs)
            self.assertTrue(result["api_accepted"])
        eddy = await self.call("maxwell_set_eddy_effects", assignment=["Copper"])
        self.assertTrue(eddy["readback_confirmed"])
        self.assertFalse(eddy["displacement_current_confirmed"])
        self.app.oboundary.GetEddyEffect = lambda name: False
        eddy = await self.call("maxwell_set_eddy_effects", assignment=["Copper"])
        self.assertFalse(eddy["readback_confirmed"])

    async def test_setup_mesh_and_design_readback(self):
        setup = await self.call("maxwell_create_setup", name="Setup2", properties={"StopTime": "20ms", "TimeStep": "0.1ms"})
        self.assertTrue(setup["setup_list_confirmed"])
        mesh = await self.call("maxwell_assign_length_mesh", assignment=[10], name="GapMesh", maximum_length="0.2mm", inside_selection=False)
        self.assertEqual(mesh["object"]["api_properties"]["maximum_length"], "0.2mm")
        info = await self.call("maxwell_get_design_info")
        self.assertEqual(info["model_units"], "mm")
        self.assertEqual(len(info["setups"]), 2)
        self.assertEqual(len(info["mesh_operations"]), 1)

    async def test_idle_and_old_solution_never_claim_solve_completion(self):
        status = await self.call("maxwell_get_analysis_status", setup_name="Setup1")
        self.assertFalse(status["desktop_simulations_running"])
        self.assertTrue(status["solution_data_available"])
        self.assertFalse(status["solver_completion_confirmed"])
        self.app.desktop_class.are_there_simulations_running = 1
        self.assertTrue((await self.call("maxwell_get_analysis_status", setup_name="Setup1"))["desktop_simulations_running"])
        self.app.desktop_class.are_there_simulations_running = None
        with self.assertRaisesRegex(BackendCommandError, "running state is unavailable"):
            await self.call("maxwell_get_analysis_status", setup_name="Setup1")

    async def test_numerical_data_includes_actual_variation_units_and_truncation(self):
        result = await self.call("maxwell_get_solution_data", expressions=["Torque1.Torque"], setup_sweep_name="Setup1 : Transient", domain="Time", max_points=2)
        curve = result["curves"]["Torque1.Torque"]
        self.assertEqual(curve["x"], [0.0, 0.1])
        self.assertEqual(curve["real"], [1.0, 2.0])
        self.assertEqual(curve["unit"], "NewtonMeter")
        self.assertTrue(curve["truncated"])
        self.assertEqual(result["active_variation"], {"speed": "1000rpm"})
        self.assertFalse(result["solver_completion_confirmed"])

    async def test_field_plots_forward_quantity_setup_and_intrinsics(self):
        for kind, assignment in [("surface", [10]), ("volume", ["Rotor"])]:
            result = await self.call("maxwell_create_field_plot", assignment=assignment, quantity="Mag_B", setup_sweep_name="Setup1 : Transient", name=f"B_{kind}", plot_type=kind, intrinsics={"Time": "10ms"})
            self.assertTrue(result["api_accepted"])
            self.assertEqual(self.app.calls[-1][0], f"create_fieldplot_{kind}")
            self.assertEqual(self.app.calls[-1][1]["intrinsics"], {"Time": "10ms"})

    async def test_missing_project_design_and_wrong_solver_reject_before_resolver(self):
        fn = self.registry.tools["maxwell_assign_coil"]
        for project, design in [("Missing", "Maxwell"), ("Motor", "Missing")]:
            with self.assertRaises(BackendCommandError):
                await fn(project_name=project, design_name=design, port=50051, assignment=[10], name="C")
        self.app.design_type = "HFSS"
        with self.assertRaisesRegex(BackendCommandError, "Maxwell tools require"):
            await self.call("maxwell_assign_coil", assignment=[10], name="C")
        self.assertEqual(self.resolutions, [])
        self.assertEqual(self.app.calls, [])

    async def test_missing_or_ambiguous_session_target_rejects(self):
        fn = self.registry.tools["maxwell_get_design_info"]
        for kwargs in [{}, {"pid": 100, "port": 50051}]:
            with self.assertRaises(ValueError):
                await fn(project_name="Motor", design_name="Maxwell", **kwargs)
        self.assertEqual(self.resolutions, [])

    async def test_invalid_assignments_counts_polarity_and_duplicate_name_reject(self):
        for kwargs in [
            {"assignment": []}, {"assignment": [True]}, {"assignment": [999]},
            {"assignment": ["Missing"]}, {"assignment": [10, "Terminal"]},
            {"assignment": [10, 10]}, {"assignment": [10], "conductors_number": 0},
            {"assignment": [10], "conductors_number": True}, {"assignment": [10], "polarity": "Bad"},
        ]:
            with self.subTest(kwargs=kwargs), self.assertRaises(BackendCommandError):
                await self.call("maxwell_assign_coil", name="C", **kwargs)
        self.assertEqual(self.app.calls, [])
        await self.call("maxwell_assign_coil", assignment=[10], name="C")
        with self.assertRaisesRegex(BackendCommandError, "Name already exists"):
            await self.call("maxwell_assign_coil", assignment=[10], name="C")

    async def test_2d_rejects_faces_and_volumes_but_accepts_object_coil(self):
        self.app.design_type = "Maxwell 2D"
        with self.assertRaisesRegex(BackendCommandError, "face IDs"):
            await self.call("maxwell_assign_coil", assignment=[10], name="C")
        result = await self.call("maxwell_assign_coil", assignment=["Terminal"], name="C")
        self.assertEqual(result["design_type"], "Maxwell 2D")
        with self.assertRaisesRegex(BackendCommandError, "Volume plots"):
            await self.call("maxwell_create_field_plot", assignment=["Rotor"], quantity="Mag_B", setup_sweep_name="Setup1 : Transient", name="B", plot_type="volume")

    async def test_invalid_physics_and_property_options_do_not_mutate(self):
        self.app.solution_type = "Magnetostatic"
        with self.assertRaisesRegex(BackendCommandError, "Transient"):
            await self.call("maxwell_assign_rotate_motion", band_object="Band", angular_velocity="1000rpm")
        with self.assertRaisesRegex(BackendCommandError, "Eddy effects require"):
            await self.call("maxwell_set_eddy_effects", assignment=["Copper"])
        self.app.solution_type = "Electrostatic"
        with self.assertRaisesRegex(BackendCommandError, "Magnetic excitation"):
            await self.call("maxwell_assign_winding", name="W")
        self.app.solution_type = "Transient"
        with self.assertRaisesRegex(BackendCommandError, "Unsupported setup properties"):
            await self.call("maxwell_create_setup", name="Bad", properties={"TimeStpe": "1ms"})
        with self.assertRaisesRegex(BackendCommandError, "Unknown coordinate"):
            await self.call("maxwell_assign_torque", assignment=["Rotor"], name="T", coordinate_system="Unknown")
        with self.assertRaisesRegex(BackendCommandError, "inside_selection"):
            await self.call("maxwell_assign_length_mesh", assignment=[10], name="M", maximum_length="1mm")
        with self.assertRaisesRegex(BackendCommandError, "conductor objects"):
            await self.call("maxwell_set_eddy_effects", assignment=["Band"])
        self.assertEqual(self.app.calls, [])

    async def test_link_rejects_missing_coils_and_wrong_boundary_types(self):
        await self.call("maxwell_assign_winding", name="W")
        for winding, coils in [("Missing", ["Missing"]), ("W", ["Missing"]), ("W", ["W"])]:
            with self.assertRaises(BackendCommandError):
                await self.call("maxwell_add_winding_coils", winding_name=winding, coils=coils)
        self.assertEqual([name for name, _ in self.app.calls], ["assign_winding"])

    async def test_api_failure_and_missing_native_readback_are_not_success_evidence(self):
        self.app.fail = "assign_coil"
        with self.assertRaisesRegex(BackendCommandError, "did not return a created object"):
            await self.call("maxwell_assign_coil", assignment=[10], name="C")
        self.app.fail = None
        await self.call("maxwell_assign_coil", assignment=[10], name="C")
        self.app.boundaries[0].child_object = None
        info = await self.call("maxwell_get_design_info")
        self.assertFalse(info["boundaries"][0]["readback_confirmed"])
        self.assertIn("readback_error", info["boundaries"][0])

    async def test_empty_missing_or_inconsistent_solution_is_rejected(self):
        kwargs = {"expressions": ["Torque1.Torque"], "setup_sweep_name": "Setup1 : Transient"}
        self.app.solution = False
        with self.assertRaisesRegex(BackendCommandError, "No solution data"):
            await self.call("maxwell_get_solution_data", **kwargs)
        self.app.solution = Solution()
        with self.assertRaisesRegex(BackendCommandError, "Unknown setup/sweep"):
            await self.call("maxwell_get_solution_data", expressions=["Torque1.Torque"], setup_sweep_name="Missing")
        with self.assertRaisesRegex(BackendCommandError, "expression absent"):
            await self.call("maxwell_get_solution_data", expressions=["Missing"], setup_sweep_name="Setup1 : Transient")
        self.app.solution.get_expression_data = lambda **kwargs: ([], [])
        with self.assertRaisesRegex(BackendCommandError, "Empty or inconsistent"):
            await self.call("maxwell_get_solution_data", **kwargs)

    async def test_nonfinite_solution_and_input_values_are_rejected(self):
        for value in [float("nan"), float("inf"), True, ""]:
            with self.subTest(value=value), self.assertRaises(BackendCommandError):
                await self.call("maxwell_assign_current", assignment=[10], name="I", amplitude=value)
        self.assertEqual(self.app.calls, [])
        self.app.solution.get_expression_data = lambda **kwargs: ([0.0], [float("nan")])
        with self.assertRaisesRegex(BackendCommandError, "Non-finite"):
            await self.call("maxwell_get_solution_data", expressions=["Torque1.Torque"], setup_sweep_name="Setup1 : Transient")

    async def test_fresh_native_boundary_node_is_resolved_after_creation(self):
        await self.call("maxwell_assign_coil", assignment=[10], name="C")
        item = self.app.boundaries[0]
        item._child_object = item.child_object
        item.child_object = None
        info = await self.call("maxwell_get_design_info")
        self.assertTrue(info["boundaries"][0]["readback_confirmed"])

    async def test_dispatched_kwargs_match_installed_pyaedt_150_signatures(self):
        from ansys.aedt.core import Maxwell3d
        from ansys.aedt.core.modules.mesh import Mesh
        from ansys.aedt.core.visualization.post.post_common_3d import PostProcessor3D

        cases = [
            ("maxwell_assign_coil", {"assignment": [10], "name": "C"}, Maxwell3d.assign_coil),
            ("maxwell_assign_winding", {"name": "W"}, Maxwell3d.assign_winding),
            ("maxwell_add_winding_coils", {"winding_name": "W", "coils": ["C"]}, Maxwell3d.add_winding_coils),
            ("maxwell_assign_current", {"assignment": [10], "name": "I"}, Maxwell3d.assign_current),
            ("maxwell_assign_rotate_motion", {"band_object": "Band", "angular_velocity": "1000rpm"}, Maxwell3d.assign_rotate_motion),
            ("maxwell_assign_translate_motion", {"band_object": "Rotor", "motion_name": "Travel", "velocity": "1m_per_sec"}, Maxwell3d.assign_translate_motion),
            ("maxwell_assign_force", {"assignment": ["Rotor"], "name": "F"}, Maxwell3d.assign_force),
            ("maxwell_assign_torque", {"assignment": ["Rotor"], "name": "T"}, Maxwell3d.assign_torque),
            ("maxwell_set_eddy_effects", {"assignment": ["Copper"]}, Maxwell3d.eddy_effects_on),
            ("maxwell_create_setup", {"name": "S", "properties": {"TimeStep": "1ms"}}, Maxwell3d.create_setup),
            ("maxwell_assign_length_mesh", {"assignment": ["Rotor"], "name": "M", "maximum_length": "1mm"}, Mesh.assign_length_mesh),
            ("maxwell_get_solution_data", {"expressions": ["Torque1.Torque"], "setup_sweep_name": "Setup1 : Transient"}, PostProcessor3D.get_solution_data),
            ("maxwell_create_field_plot", {"assignment": [10], "quantity": "Mag_B", "setup_sweep_name": "Setup1 : Transient", "name": "B"}, PostProcessor3D.create_fieldplot_surface),
        ]
        for tool, args, method in cases:
            with self.subTest(tool=tool):
                await self.call(tool, **args)
                inspect.signature(method).bind(object(), **self.app.calls[-1][1])


if __name__ == "__main__":
    unittest.main()
