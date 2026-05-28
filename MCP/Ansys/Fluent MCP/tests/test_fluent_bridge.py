from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import fluent_bridge


class FluentBridgeTests(unittest.TestCase):
    def test_find_fluent_exe_prefers_explicit_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "fluent.exe"
            exe.write_text("", encoding="utf-8")
            with mock.patch.dict(os.environ, {"FLUENT_EXE": str(exe)}, clear=True):
                self.assertEqual(fluent_bridge.find_fluent_exe(), exe)

    def test_find_fluent_exe_uses_ansys_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exe = root / "fluent" / "ntbin" / "win64" / "fluent.exe"
            exe.parent.mkdir(parents=True)
            exe.write_text("", encoding="utf-8")
            with mock.patch.dict(os.environ, {"ANSYS_ROOT": str(root)}, clear=True):
                self.assertEqual(fluent_bridge.find_fluent_exe(), exe)

    def test_build_fluent_batch_command_normalizes_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            journal = root / "case.jou"
            journal.write_text("/exit yes", encoding="utf-8")
            exe = root / "fluent.exe"
            exe.write_text("", encoding="utf-8")

            command = fluent_bridge.build_fluent_batch_command(
                fluent_exe=exe,
                journal_path=journal,
                dimension="3",
                precision="double",
                processor_count=4,
                extra_args=["-meshing"],
            )

            self.assertEqual(
                command,
                [str(exe), "3ddp", "-g", "-t4", "-i", str(journal), "-meshing"],
            )

    def test_launch_fluent_journal_writes_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exe = root / "fluent.exe"
            exe.write_text("", encoding="utf-8")
            journal = root / "case.jou"
            journal.write_text("/exit yes", encoding="utf-8")
            jobs_dir = root / "jobs"
            popen_calls: list[dict[str, object]] = []

            class FakeProcess:
                pid = 1234

            def fake_popen(command: list[str], **kwargs: object) -> FakeProcess:
                popen_calls.append({"command": command, **kwargs})
                return FakeProcess()

            with mock.patch.object(fluent_bridge.subprocess, "Popen", fake_popen):
                result = fluent_bridge.launch_fluent_journal(
                    journal_path=str(journal),
                    fluent_exe=str(exe),
                    jobs_dir=jobs_dir,
                    processor_count=2,
                )

            self.assertEqual(result["status"], "running")
            self.assertTrue(str(result["job_id"]).startswith("fluent_"))
            self.assertEqual(popen_calls[0]["command"][:5], [str(exe), "3ddp", "-g", "-t2", "-i"])
            meta = Path(str(result["metadata_path"]))
            self.assertTrue(meta.exists())
            self.assertEqual(json.loads(meta.read_text(encoding="utf-8"))["pid"], 1234)

    def test_get_fluent_job_status_marks_finished_process(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            jobs_dir = Path(tmp) / "jobs"
            job_id = "fluent_deadbeef"
            job_dir = jobs_dir / job_id
            job_dir.mkdir(parents=True)
            (job_dir / "job.json").write_text(
                json.dumps({"job_id": job_id, "status": "running", "pid": 456}),
                encoding="utf-8",
            )

            with mock.patch.object(fluent_bridge, "_process_running", lambda pid: False):
                status = fluent_bridge.get_fluent_job_status(job_id, jobs_dir=jobs_dir)

            self.assertEqual(status["status"], "completed_or_exited")
            self.assertIn("finished_at", status)


if __name__ == "__main__":
    unittest.main()
