from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hyperworks_mcp.analysis_templates import AnalysisTemplateService
from hyperworks_mcp.reporting import write_job_report


class _Profiles:
    def prepare_optistruct_cantilever(self, project_id, **parameters):
        return {"project_id": project_id, "input_file": "model.fem", **parameters}

    def prepare_radioss_block_impact(self, project_id, **parameters):
        return {"project_id": project_id, "input_file": "model_0000.rad", **parameters}

    def prepare_optistruct_modal(self, project_id, **parameters):
        return {"project_id": project_id, "input_file": "modal.fem", **parameters}

    def prepare_radioss_solid_impact_scenario(self, project_id, **parameters):
        return {"project_id": project_id, "input_file": "scenario_0000.rad", **parameters}


class TemplateAndReportingTests(unittest.TestCase):
    def test_template_registry_validates_and_dispatches(self) -> None:
        service = AnalysisTemplateService(_Profiles())
        self.assertGreaterEqual(service.list("radioss")["count"], 8)
        prepared = service.prepare(
            "project_1",
            "optistruct.linear_static_solid",
            {
                "name": "beam",
                "dimensions": [10, 2, 2],
                "divisions": [5, 1, 1],
                "youngs_modulus": 210000,
                "poissons_ratio": 0.3,
                "density": 7.85e-9,
                "total_force": 1000,
                "force_direction": [0, 0, -1],
            },
        )
        self.assertEqual(prepared["input_file"], "model.fem")
        self.assertEqual(prepared["template_validation_state"], "real_solver_verified")
        with self.assertRaisesRegex(ValueError, "Unknown template parameters"):
            service.prepare(
                "project_1", "optistruct.linear_static_solid",
                {
                    "name": "beam", "dimensions": [10, 2, 2],
                    "divisions": [5, 1, 1], "youngs_modulus": 210000,
                    "poissons_ratio": 0.3, "density": 7.85e-9,
                    "total_force": 1000, "force_direction": [0, 0, -1],
                    "unexpected": True,
                },
            )

        modal = service.prepare(
            "project_1", "optistruct.normal_modes_solid",
            {"name": "modes", "dimensions": [10, 2, 2], "divisions": [5, 1, 1], "youngs_modulus": 210000, "poissons_ratio": 0.3, "density": 7.85e-9},
        )
        self.assertEqual(modal["number_of_modes"], 10)
        self.assertEqual(modal["template_validation_state"], "real_solver_verified")
        drop = service.prepare("project_1", "radioss.drop_weight_solid_surrogate", {"name": "drop"})
        self.assertEqual(drop["scenario"], "drop_weight_surrogate")
        self.assertEqual(
            drop["template_validation_state"],
            "real_solver_verified_solid_surrogate",
        )
        with self.assertRaisesRegex(RuntimeError, "not runnable"):
            service.prepare("project_1", "radioss.tube_crush", {})

    def test_job_report_writes_html_and_machine_readable_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "output"
            output.mkdir()
            image = output / "contour.png"
            image.write_bytes(b"fake image")
            result = write_job_report(
                output,
                "report",
                {"job_id": "job_1", "project_id": "project_1", "kind": "radioss", "state": "COMPLETED", "return_code": 0},
                {"categories": {"result": [{"path": "result.h3d"}], "animation": []}},
                {"passed": True, "gates": {"starter_normal_termination": True, "engine_normal_termination": True}, "engine": {"maximum_absolute_energy_error_percent": 2.0}},
                [image],
            )
            self.assertTrue(Path(result["html_file"]).is_file())
            self.assertTrue(Path(result["json_file"]).is_file())
            self.assertEqual(result["evidence_count"], 1)


if __name__ == "__main__":
    unittest.main()
