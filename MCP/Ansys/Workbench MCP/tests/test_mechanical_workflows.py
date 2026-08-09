from __future__ import annotations

import ast
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def _load_module():
    path = ROOT / "tools" / "mechanical_workflows.py"
    spec = importlib.util.spec_from_file_location("mechanical_workflows_under_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class MechanicalWorkflowTests(unittest.TestCase):
    def test_valid_rotor_spec_is_normalized(self):
        module = _load_module()
        result = module.validate_rotor_job_spec(
            {
                "analysis_name": "Rotating_Static",
                "rotational_speed_rpm": 6000,
                "rotation_axis": "x",
                "fixed_support_named_selection": "Disk_Bore",
                "contact_mode": "named_pairs",
                "contact_pairs": [{"source": "Blade_01", "target": "Slot_01"}],
                "expected_contact_count": 20,
                "material_name": "Structural Steel",
            }
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["normalized"]["rotation_axis"], "X")
        self.assertEqual(result["normalized"]["rotational_speed_rpm"], 6000.0)
        self.assertEqual(result["normalized"]["expected_contact_count"], 20)
        self.assertEqual(
            result["normalized"]["modal_analysis_names"],
            ["Modal_Zero_RPM", "Modal_Prestressed"],
        )

    def test_invalid_rotor_specs_fail_before_mechanical(self):
        cases = [
            ({"rotational_speed_rpm": 0}, "rotational_speed_rpm"),
            ({"rotation_axis": "A"}, "rotation_axis"),
            ({"fixed_support_named_selection": ""}, "fixed_support_named_selection"),
            ({"contact_mode": "named_pairs", "contact_pairs": []}, "contact_pairs"),
        ]
        module = _load_module()
        for update, expected in cases:
            with self.subTest(update=update):
                payload = {
                    "rotational_speed_rpm": 6000,
                    "rotation_axis": "X",
                    "fixed_support_named_selection": "Disk_Bore",
                    "contact_mode": "existing",
                }
                payload.update(update)
                result = module.validate_rotor_job_spec(payload)
                self.assertFalse(result["ok"])
                self.assertIn(expected, " ".join(result["errors"]))

    def test_mesh_spec_accepts_global_and_local_sizes(self):
        module = _load_module()
        result = module.validate_mesh_spec(
            {
                "global_size_mm": 5,
                "local_sizings": [
                    {"named_selection": "Blade_Roots", "size_mm": 1.5},
                    {"named_selection": "Disk_Bore", "size_mm": 2.0},
                ],
            }
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["normalized"]["global_size_mm"], 5.0)
        self.assertEqual(len(result["normalized"]["local_sizings"]), 2)

    def test_workbench_journal_contains_prestress_transfer(self):
        module = _load_module()
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "rotor.wbpj"
            result = module.build_prestressed_modal_journal(str(project), overwrite_policy="error")
            self.assertTrue(result["ok"])
            journal = Path(result["journal_path"]).read_text(encoding="utf-8")
            self.assertIn('TemplateName="Static Structural"', journal)
            self.assertIn('TemplateName="Modal"', journal)
            self.assertIn("static_solution.TransferData(TargetComponent=prestress_setup)", journal)
            self.assertIn("Modal Zero RPM", journal)

    def test_workbench_project_defaults_to_fail_if_exists(self):
        module = _load_module()
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "existing.wbpj"
            project.write_text("existing", encoding="utf-8")
            result = module.build_prestressed_modal_journal(str(project), overwrite_policy="error")
            self.assertFalse(result["ok"])
            self.assertIn("existing.wbpj", result["error"])

    def test_mechanical_script_embeds_only_validated_request(self):
        module = _load_module()
        code = module._mechanical_script("create_analysis_chain", {"mode_count": 6})
        self.assertIn("REQUEST =", code)
        self.assertIn("'operation': 'create_analysis_chain'", code)
        self.assertIn("ANSYS_WORKBENCH_WORKFLOW_JSON:", code)
        compile(code, "generated_mechanical_workflow.py", "exec")

    def test_workflow_marker_is_extracted_from_nested_queue_response(self):
        module = _load_module()
        payload = {
            "response": {
                "response": {
                    "stdout": 'prefix\nANSYS_WORKBENCH_WORKFLOW_JSON:{"ok":true,"data":{"count":3}}\n'
                }
            }
        }
        parsed = module._find_workflow_marker(payload)
        self.assertEqual(parsed, {"ok": True, "data": {"count": 3}})

    def test_socket_transport_is_blocked_for_model_mutation(self):
        module = _load_module()
        result = module._dispatch("configure_rotor", {}, "socket", 1.0)
        self.assertFalse(result["ok"])
        self.assertIn("transport=queue", result["error"])

    def test_readiness_requires_project_model_and_analyses(self):
        module = _load_module()
        socket_result = {"ok": True, "connected": True}
        probe_result = {
            "workflow_result": {
                "data": {
                    "project_available": True,
                    "model_available": False,
                    "analysis_collection_readable": False,
                }
            }
        }
        with mock.patch.object(module, "socket_timer_state", return_value=socket_result), mock.patch.object(
            module, "_dispatch", return_value=probe_result
        ):
            result = module.mechanical_readiness(timeout=1.0)
        self.assertFalse(result["ok"])
        self.assertFalse(result["ready_for_model_mutation"])

    def test_server_exposes_all_new_workflow_tools(self):
        server_path = ROOT / "server.py"
        tree = ast.parse(server_path.read_text(encoding="utf-8"))
        names = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
        expected = {
            "mechanical_readiness_tool",
            "mechanical_probe_session_tool",
            "workbench_create_prestressed_modal_chain_tool",
            "mechanical_geometry_inventory_tool",
            "mechanical_import_geometry_tool",
            "mechanical_create_named_selection_tool",
            "mechanical_create_analysis_chain_tool",
            "mechanical_validate_rotor_job_tool",
            "mechanical_configure_rotor_model_tool",
            "mechanical_validate_mesh_job_tool",
            "mechanical_mesh_and_validate_tool",
            "mechanical_solve_analysis_tool",
            "mechanical_workflow_status_tool",
            "mechanical_extract_structural_results_tool",
            "mechanical_extract_modal_results_tool",
            "mechanical_export_evidence_tool",
        }
        self.assertTrue(expected <= names)

    def test_mechanical_side_script_remains_python_syntax_compatible(self):
        path = ROOT / "workbench_plugin" / "mechanical_analysis_workflows.py"
        compile(path.read_text(encoding="utf-8"), str(path), "exec")


if __name__ == "__main__":
    unittest.main()
