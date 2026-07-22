from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hyperworks_mcp.hyperstudy import HyperStudyService, normalize_math_study_spec
from hyperworks_mcp.projects import ProjectService
from hyperworks_mcp.settings import Settings


class HyperStudyTests(unittest.TestCase):
    def test_prepares_typed_doe_and_optimization_script(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings(Path(tmp) / "workspace", None, 4, 32)
            settings.ensure()
            projects = ProjectService(settings)
            project = projects.create("HyperStudy test")
            service = HyperStudyService(projects)
            result = service.prepare_math_study(
                project["project_id"],
                "Bracket tradeoff",
                [
                    {
                        "label": "Width",
                        "varname": "width",
                        "lower": 1.0,
                        "nominal": 2.0,
                        "upper": 4.0,
                    }
                ],
                [
                    {
                        "label": "Area",
                        "varname": "area",
                        "expression": "width*width",
                    }
                ],
                doe={"design": "Hammersley", "runs": 12},
                optimization={
                    "design": "GRSM",
                    "max_evaluations": 20,
                    "goals": [
                        {
                            "varname": "min_area",
                            "response": "area",
                            "type": "Minimize",
                        }
                    ],
                },
            )
            script = Path(result["script_file"])
            self.assertTrue(script.is_file())
            compile(script.read_text(encoding="utf-8"), str(script), "exec")
            self.assertTrue(result["has_doe"])
            self.assertTrue(result["has_optimization"])
            self.assertEqual(service.generated_script(project["project_id"], script.name), script)

    def test_rejects_unsafe_expression_and_unknown_response(self) -> None:
        variables = [
            {"varname": "x", "lower": 0, "nominal": 1, "upper": 2}
        ]
        with self.assertRaisesRegex(ValueError, "unsupported characters"):
            normalize_math_study_spec(
                "unsafe",
                variables,
                [{"varname": "r", "expression": "__import__('os')"}],
            )
        with self.assertRaisesRegex(ValueError, "Unknown optimization response"):
            normalize_math_study_spec(
                "bad goal",
                variables,
                [{"varname": "r", "expression": "x*x"}],
                optimization={
                    "goals": [
                        {
                            "varname": "goal",
                            "response": "missing",
                            "type": "Minimize",
                        }
                    ]
                },
            )


if __name__ == "__main__":
    unittest.main()
