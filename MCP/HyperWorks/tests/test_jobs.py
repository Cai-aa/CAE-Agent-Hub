from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path

from hyperworks_mcp.jobs import JobService
from hyperworks_mcp.settings import Settings


class JobTests(unittest.TestCase):
    def test_tracks_successful_process_and_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            settings = Settings(workspace, None, 4, 32)
            settings.ensure()
            service = JobService(settings)
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            job = service.start(
                "TEST",
                "project_test",
                [sys.executable, "-c", "print('job-ok')"],
                run_dir,
            )
            deadline = time.time() + 10
            status = service.status(job["job_id"])
            while status["state"] == "RUNNING" and time.time() < deadline:
                time.sleep(0.05)
                status = service.status(job["job_id"])
            self.assertEqual(status["state"], "COMPLETED")
            self.assertIn("job-ok", "\n".join(service.log(job["job_id"])["lines"]))


if __name__ == "__main__":
    unittest.main()
