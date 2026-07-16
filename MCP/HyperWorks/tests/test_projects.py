from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hyperworks_mcp.projects import ProjectService
from hyperworks_mcp.settings import Settings


class ProjectTests(unittest.TestCase):
    def test_create_import_and_write_script(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            settings = Settings(workspace, None, 4, 32)
            settings.ensure()
            service = ProjectService(settings)
            project = service.create("demo")
            source = Path(tmp) / "model.fem"
            source.write_text("BEGIN BULK\nENDDATA\n", encoding="utf-8")
            imported = service.import_file(project["project_id"], str(source), None)
            written = service.write_tcl(project["project_id"], "prep", 'puts "ok"\n')
            self.assertTrue(Path(imported["imported_file"]).is_file())
            self.assertTrue(Path(written["script_file"]).is_file())
            summary = service.manifest(project["project_id"])
            self.assertEqual(summary["files"], ["input/model.fem"])
            self.assertEqual(summary["scripts"], ["scripts/prep.tcl"])

    def test_project_id_cannot_escape_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings(Path(tmp) / "workspace", None, 4, 32)
            settings.ensure()
            service = ProjectService(settings)
            with self.assertRaises(ValueError):
                service.root("../outside")


if __name__ == "__main__":
    unittest.main()
