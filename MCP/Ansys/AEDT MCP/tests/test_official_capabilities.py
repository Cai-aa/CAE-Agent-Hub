import json
import tempfile
import unittest
from pathlib import Path

from aedt_target import AedtTarget
from pyaedt_backend import PyAedtBackend
from pyaedt_capabilities import OFFICIAL_BACKEND_COMMANDS, OfficialCapabilities


class NamedObject:
    def __init__(self, name):
        self.name = name

    def GetName(self):
        return self.name


class FakePost:
    def __init__(self):
        self.calls = []

    def export_model_picture(self, full_name, width, height):
        self.calls.append((full_name, width, height))
        Path(full_name).write_bytes(b"fake-jpeg")


class FakeConfigurations:
    def export_config(self, config_file, overwrite=False):
        Path(config_file).write_text(
            json.dumps({"general": {"model_units": "mm"}}),
            encoding="utf-8",
        )
        return config_file


class FakeApp:
    def __init__(
        self,
        *,
        project_name="ThermalProject",
        design_name="IcepakDesign1",
        design_type="Icepak",
        valid=True,
        **kwargs,
    ):
        self.project_name = kwargs.get("project", project_name)
        self.design_name = kwargs.get("design", design_name)
        self.design_type = design_type
        self.solution_type = kwargs.get("solution_type", "SteadyState")
        self.valid = valid
        self.kwargs = kwargs
        self.analyze_calls = []
        self.export_calls = []
        self.post = FakePost()
        self.configurations = FakeConfigurations()
        self.results_directory = kwargs.get("results_directory", "")
        self.profile_content = kwargs.get(
            "profile_content",
            (
                "Global Nodes: 101, Faces: 202, Cells: 303\n"
                "Total Nodes: 101, Total Faces: 202, Total Cells: 303\n"
                "Status: Normal Completion\n"
            ),
        )

    def validate_simple(self, log_file):
        if not self.valid:
            Path(log_file).write_text("missing opening", encoding="utf-8")
        return self.valid

    def analyze(self, **kwargs):
        self.analyze_calls.append(kwargs)
        return True

    def get_setups(self):
        return ["Setup1"]

    def _export(self, kind, output_file, setup=None):
        self.export_calls.append((kind, output_file, setup))
        Path(output_file).write_text(kind, encoding="utf-8")
        return True

    def export_touchstone(self, output_file, setup=None):
        return self._export("touchstone", output_file, setup)

    def export_profile(self, output_file, setup=None):
        self.export_calls.append(("profile", output_file, setup))
        Path(output_file).write_text(self.profile_content, encoding="utf-8")
        return output_file

    def export_convergence(self, output_file, setup=None):
        return self._export("convergence", output_file, setup)

    def export_mesh_stats(self, output_file, setup=None):
        return self._export("mesh", output_file, setup)


class FakeDesktop:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.aedt_version_id = "2026.1"
        self.aedt_process_id = kwargs.get("aedt_process_id", 4321)
        self.port = kwargs.get("port", 0)
        self.is_grpc_api = kwargs.get("port") is not None
        self.project_list = ["ThermalProject"]
        self.project = NamedObject("ThermalProject")
        self.design = NamedObject("IcepakDesign1")
        self.odesktop = self
        self.loaded = []
        self.saved = []
        self.closed = []
        self.release_calls = []
        self.clear_calls = 0
        self.run_script_calls = []
        self.analyze_all_calls = []

    def active_project(self):
        return self.project

    def active_design(self, project=None):
        return self.design

    def design_list(self, project_name=None):
        return ["IcepakDesign1"]

    def design_type(self, project_name=None, design_name=None):
        return "Icepak"

    def project_path(self):
        return "C:/models/ThermalProject.aedt"

    def load_project(self, path, design_name=None):
        self.loaded.append((path, design_name))
        return True

    def save_project(self, project_name=None, project_path=None):
        self.saved.append((project_name, project_path))
        return True

    def CloseProject(self, project):
        self.closed.append(project)
        self.project_list.remove(project)

    def clear_messages(self):
        self.clear_calls += 1

    def GetMessages(self, project, design, severity):
        return [f"severity-{severity}"]

    def RunScript(self, path):
        self.run_script_calls.append(path)
        return "script-ok"

    def analyze_all(self, project=None, design=None):
        self.analyze_all_calls.append((project, design))
        return True

    def release_desktop(self, close_projects=False, close_on_exit=False):
        self.release_calls.append((close_projects, close_on_exit))
        return True


class OfficialCapabilityTests(unittest.TestCase):
    def setUp(self):
        self.desktop = FakeDesktop()
        self.active_app = FakeApp()
        self.created_apps = []
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.log_file = self.root / "pyaedt.log"
        self.log_file.write_text("start\nwarning: hot\nfinished\n", encoding="utf-8")

        def app_factory(**kwargs):
            app = FakeApp(**kwargs)
            self.created_apps.append(app)
            return app

        capabilities = OfficialCapabilities(
            app_resolver=lambda **kwargs: self.active_app,
            app_class_resolver=lambda app_type: (
                app_factory if app_type == "Icepak" else None
            ),
            log_file_resolver=lambda: str(self.log_file),
        )
        self.backend = PyAedtBackend(
            desktop_factory=lambda **kwargs: self.desktop,
            official_capabilities=capabilities,
        )
        self.target = AedtTarget("port", 50051)

    def tearDown(self):
        self.temp.cleanup()

    def test_all_official_backend_commands_have_handlers(self):
        capabilities = self.backend._official
        missing = [
            command
            for command in OFFICIAL_BACKEND_COMMANDS
            if not hasattr(capabilities, f"_{command}")
        ]
        self.assertEqual(missing, [])

    def test_create_icepak_design_stays_on_explicit_grpc_target(self):
        result = self.backend.execute(
            self.target,
            "create_design",
            {
                "app_type": "Icepak",
                "project_name": "Cooling",
                "design_name": "BoardThermal",
                "solution_type": "SteadyState",
            },
        )

        app = self.created_apps[0]
        self.assertEqual(result["app_type"], "Icepak")
        self.assertEqual(app.kwargs["machine"], "localhost")
        self.assertEqual(app.kwargs["port"], 50051)
        self.assertFalse(app.kwargs["new_desktop"])
        self.assertEqual(app.design_name, "BoardThermal")

    def test_inline_code_reuses_persistent_broker_namespace(self):
        first = self.backend.execute(
            self.target,
            "run_python_code",
            {"code": "counter = 40\nprint('hello')\nresult = counter + 1"},
        )
        second = self.backend.execute(
            self.target,
            "run_python_code",
            {"code": "result = counter + 2"},
        )

        self.assertEqual(first["result"], 41)
        self.assertEqual(first["stdout"], "hello\n")
        self.assertEqual(second["result"], 42)

    def test_validate_then_analyze_is_async_and_does_not_claim_completion(self):
        validation = self.backend.execute(
            self.target,
            "validate_design",
            {"project_name": "ThermalProject", "design_name": "IcepakDesign1"},
        )
        analysis = self.backend.execute(
            self.target,
            "analyze_design",
            {
                "project_name": "ThermalProject",
                "design_name": "IcepakDesign1",
                "setup_name": "Setup1",
                "num_cores": 4,
            },
        )

        self.assertTrue(validation["valid"])
        self.assertTrue(analysis["started"])
        self.assertFalse(analysis["solver_completion_confirmed"])
        self.assertFalse(self.active_app.analyze_calls[0]["blocking"])
        self.assertTrue(analysis["icepak_safe_mode_applied"])
        self.assertEqual(analysis["requested_resources"]["num_cores"], 4)
        self.assertEqual(analysis["effective_resources"]["num_cores"], 1)
        self.assertEqual(self.active_app.analyze_calls[0]["cores"], 1)
        self.assertFalse(self.active_app.analyze_calls[0]["use_auto_settings"])

    def test_icepak_safe_mode_can_be_disabled(self):
        analysis = self.backend.execute(
            self.target,
            "analyze_design",
            {
                "project_name": "ThermalProject",
                "design_name": "IcepakDesign1",
                "setup_name": "Setup1",
                "num_cores": 4,
                "icepak_safe_mode": False,
            },
        )

        self.assertFalse(analysis["icepak_safe_mode_applied"])
        self.assertEqual(self.active_app.analyze_calls[0]["cores"], 4)
        self.assertTrue(self.active_app.analyze_calls[0]["use_auto_settings"])

    def test_failed_validation_prevents_analysis(self):
        self.active_app.valid = False
        result = self.backend.execute(
            self.target,
            "analyze_design",
            {"project_name": "ThermalProject", "design_name": "IcepakDesign1"},
        )

        self.assertFalse(result["started"])
        self.assertFalse(result["validation_passed"])
        self.assertIn("missing opening", result["validation_details"])
        self.assertEqual(self.active_app.analyze_calls, [])

    def test_exports_config_results_and_screenshot(self):
        config_path = self.root / "design-config.json"
        result_path = self.root / "mesh.txt"
        image_path = self.root / "view.jpg"

        config = self.backend.execute(
            self.target,
            "export_config",
            {"output": str(config_path), "overwrite": True},
        )
        result = self.backend.execute(
            self.target,
            "export_results",
            {"output_path": str(result_path), "export_type": "mesh"},
        )
        image = self.backend.execute(
            self.target,
            "screenshot",
            {"path": str(image_path), "open_viewer": False, "resolution": "4k"},
        )

        self.assertEqual(config["config"]["general"]["model_units"], "mm")
        self.assertTrue(result["file_exists"])
        self.assertEqual(image["data_base64"], "ZmFrZS1qcGVn")
        self.assertEqual(self.active_app.post.calls[0][1:], (3840, 2160))

    def test_icepak_convergence_exports_monitor_history(self):
        results = self.root / "ThermalProject.aedtresults"
        design_results = results / "IcepakDesign1.results"
        design_results.mkdir(parents=True)
        (design_results / "DV1_Meshes0.sd").mkdir()
        monitor = design_results / "DV1_S1_MON0_V1.sd"
        monitor.write_text(
            "\n".join(
                [
                    "1.0 Continuity(1.0e-2)XVelocity(2.0e-2)Energy(3.0e-3)",
                    "2.0 Continuity(5.0e-3)XVelocity(1.0e-2)Energy(9.0e-4)",
                ]
            ),
            encoding="utf-8",
        )
        self.active_app.results_directory = str(results)
        output = self.root / "icepak-convergence.csv"

        result = self.backend.execute(
            self.target,
            "export_results",
            {
                "output_path": str(output),
                "export_type": "convergence",
                "setup_name": "Setup1",
            },
        )

        self.assertTrue(result["file_exists"])
        self.assertEqual(result["export_method"], "icepak_monitor_history")
        self.assertEqual(result["details"]["row_count"], 2)
        self.assertIn("Continuity", output.read_text(encoding="utf-8"))

    def test_icepak_mesh_stats_export_from_solution_profile(self):
        output = self.root / "icepak-mesh.csv"

        result = self.backend.execute(
            self.target,
            "export_results",
            {
                "output_path": str(output),
                "export_type": "mesh",
                "setup_name": "Setup1",
            },
        )

        self.assertTrue(result["file_exists"])
        self.assertEqual(result["export_method"], "icepak_solution_profile")
        self.assertEqual(
            result["details"]["statistics"],
            {"nodes": 101, "faces": 202, "cells": 303},
        )
        self.assertIn("NormalCompletion", output.read_text(encoding="utf-8"))

    def test_logs_scripts_listing_and_disconnect(self):
        script = self.root / "inside_aedt.py"
        script.write_text("print('inside')", encoding="utf-8")

        logs = self.backend.execute(
            self.target,
            "get_pyaedt_logs",
            {"tail_lines": 10, "contains": "warning", "max_chars": 1000},
        )
        script_result = self.backend.execute(
            self.target, "run_python_script", {"script_path": str(script)}
        )
        designs = self.backend.execute(
            self.target, "list_designs", {"project_name": "ThermalProject"}
        )
        disconnected = self.backend.execute(
            self.target,
            "disconnect_from_aedt",
            {"close_projects": False, "close_desktop": False},
        )

        self.assertIn("warning: hot", logs["logs"])
        self.assertEqual(script_result["result"], "script-ok")
        self.assertEqual(designs["designs"], ["IcepakDesign1"])
        self.assertTrue(disconnected["disconnected"])
        self.assertEqual(self.desktop.release_calls, [(False, False)])


if __name__ == "__main__":
    unittest.main()
