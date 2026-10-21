"""Windows regressions for an MCP host whose stdin remains open."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


@unittest.skipUnless(os.name == "nt", "Windows batch process test")
class BatchProcessTests(unittest.TestCase):
    def run_worker(self, child_source, timeout_sec=2):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            child = root / "child.py"
            child.write_text(child_source, encoding="utf-8")
            launcher = root / "launcher.bat"
            launcher.write_text(f'@echo off\n"{sys.executable}" "{child}"\n', encoding="utf-8")
            worker = root / "worker.py"
            worker.write_text(
                "from adams_mcp.config import Settings\n"
                "from adams_mcp.service import AdamsService\n"
                "from pathlib import Path\nimport json\n"
                f"root=Path({str(root)!r})\n"
                "service=AdamsService(Settings(root, root/'launcher.bat', 'test', root))\n"
                f"result=service._run_batch_text('! test', {{'kind':'regression'}}, {timeout_sec})\n"
                "print(json.dumps(result))\n", encoding="utf-8")
            process = subprocess.Popen([sys.executable, str(worker)], stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                # Keep the MCP-like input pipe OPEN while the batch runs.
                process.wait(timeout=30)
                output, errors = process.communicate(timeout=2)
                self.assertEqual(process.returncode, 0, errors.decode(errors="replace"))
                return json.loads(output)
            finally:
                if process.poll() is None:
                    subprocess.run([str(Path(os.environ['SystemRoot']) / 'System32' / 'taskkill.exe'), '/PID', str(process.pid), '/T', '/F'], capture_output=True)
                    process.communicate(timeout=5)

    def test_batch_does_not_read_mcp_stdin(self):
        result = self.run_worker("import sys\nsys.stdin.read()\nprint('completed')\n", timeout_sec=10)
        self.assertTrue(result['ok'], result)

    def test_batch_timeout_returns_with_descendant(self):
        result = self.run_worker("import time\ntime.sleep(60)\n")
        self.assertFalse(result['ok'])
        self.assertEqual(result['status'], 'TIMEOUT')
