from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hyperworks_mcp.environment import environment_report, normalize_installation_root
from hyperworks_mcp.settings import Settings


class EnvironmentTests(unittest.TestCase):
    def test_detects_desktop_without_solver(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Altair" / "2026"
            launcher = root / "hwdesktop" / "hwx" / "bin" / "win64" / "runhwx.exe"
            batch = root / "hwdesktop" / "hm" / "bin" / "win64" / "hmbatch.exe"
            common = root / "common"
            launcher.parent.mkdir(parents=True)
            batch.parent.mkdir(parents=True)
            common.mkdir(parents=True)
            launcher.touch()
            batch.touch()
            workspace = Path(tmp) / "workspace"
            workspace.mkdir()
            settings = Settings(workspace, root, 4, 32)
            report = environment_report(settings)
            self.assertTrue(report["capabilities"]["launch_hypermesh_gui"])
            self.assertTrue(report["capabilities"]["run_hypermesh_batch_tcl"])
            self.assertFalse(report["capabilities"]["run_optistruct"])

    def test_normalizes_user_supplied_bin_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Altair" / "2026"
            target = root / "hwdesktop" / "hwx" / "bin" / "win64"
            target.mkdir(parents=True)
            (root / "common").mkdir()
            self.assertEqual(normalize_installation_root(target), root.resolve())


if __name__ == "__main__":
    unittest.main()
