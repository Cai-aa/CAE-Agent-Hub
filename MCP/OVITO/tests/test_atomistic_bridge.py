from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import atomistic_bridge


class AtomisticBridgeTests(unittest.TestCase):
    def test_find_lammps_prefers_explicit_environment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            executable = Path(tmp) / "lmp.exe"
            executable.write_text("", encoding="utf-8")
            with mock.patch.dict(os.environ, {"LAMMPS_EXE": str(executable)}, clear=True):
                self.assertEqual(atomistic_bridge.find_lammps(), executable.resolve())

    def test_detect_ovito_gui_is_partial_without_batch_python(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            gui = Path(tmp) / "ovito.exe"
            gui.write_text("", encoding="utf-8")
            with mock.patch.dict(os.environ, {"OVITO_EXE": str(gui)}, clear=True):
                result = atomistic_bridge.detect_ovito()
            self.assertEqual(result["status"], "partial")
            self.assertFalse(result["batch_python_available"])

    def test_run_writes_job_metadata_and_logs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            jobs = root / "jobs"
            with mock.patch.object(atomistic_bridge, "JOBS_DIR", jobs):
                result = atomistic_bridge._run(
                    "test", ["cmd", "/c", "echo", "ok"], root, root / "run", 30
                )
                self.assertEqual(result["status"], "completed")
                stored = json.loads((jobs / result["job_id"] / "job.json").read_text(encoding="utf-8"))
                self.assertEqual(stored["returncode"], 0)
                self.assertIn("ok", Path(stored["stdout"]).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
