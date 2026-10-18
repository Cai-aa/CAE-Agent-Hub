from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from adams_mcp.config import Settings
from adams_mcp.service import AdamsService


class ServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        workspace = Path(self.temp.name)
        self.service = AdamsService(Settings(workspace / "installation", workspace / "missing_launcher.bat", "2024.1", workspace))
        (workspace / "projects").mkdir()
        (workspace / "runs").mkdir()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_project_and_builder(self) -> None:
        created = self.service.project_create("demo", "MCP_DEMO")
        self.assertTrue(created["ok"])
        body = self.service.rigid_body_create("demo", "link", [0, 0, 0], [10, 2, 1], 1.0, [1, 1, 1])
        self.assertTrue(body["ok"])
        joint = self.service.connection_create_revolute("demo", "pivot", "link", "ground", [0, 0, 0])
        self.assertTrue(joint["ok"])
        motion = self.service.motion_create_rotational("demo", "drive", "pivot", "90d*time")
        self.assertTrue(motion["ok"])
        cmd = (self.service.projects / "demo" / "model.cmd").read_text(encoding="utf-8")
        self.assertIn("constraint create joint revolute", cmd)
        self.assertIn("motion_generator", cmd)

    def test_workspace_guard(self) -> None:
        result = self.service.batch_run_cmd(str(Path(self.temp.name).parent / "outside.cmd"))
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "ADM-MCP-004")

    def test_raw_command_guard(self) -> None:
        result = self.service.live_command("quit conf=no")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "ADM-MCP-004")

    def test_noncanonical_workspace_accepts_its_own_files(self) -> None:
        workspace = Path(self.temp.name) / "projects" / ".."
        service = AdamsService(Settings(workspace, workspace / "missing.bat", "test", workspace))
        path = Path(self.temp.name) / "runs" / "canonical.txt"
        path.write_text("1\n2\n", encoding="utf-8")
        result = service.result_summary(str(path))
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["data"]["points"], 2)

    def test_invalid_names_rejected(self) -> None:
        result = self.service.project_create("../escape", "bad")
        self.assertFalse(result["ok"])

    def test_numeric_result_summary(self) -> None:
        path = self.service.settings.workspace / "runs" / "values.txt"
        path.write_text("heading\n1.0\n-2.0E+00\n3\n", encoding="utf-8")
        result = self.service.result_summary(str(path))
        self.assertTrue(result["ok"])
        self.assertEqual(result["data"]["points"], 3)
        self.assertEqual(result["data"]["min"], -2.0)


if __name__ == "__main__":
    unittest.main()
