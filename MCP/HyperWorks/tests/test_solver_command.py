from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

from hyperworks_mcp.server import _solver_command


class SolverCommandTests(unittest.TestCase):
    def test_radioss_batch_command_quotes_paths_with_spaces(self) -> None:
        executable = Path(r"C:\Program Files\Altair\2026\hwsolvers\scripts\radioss.bat")
        run_input = Path(r"C:\CAE Projects\S Beam\input\case_0000.rad")

        command = _solver_command(executable, run_input, 4, "radioss")

        expected = subprocess.list2cmdline(
            [str(executable), str(run_input), "-ncpu", "4"]
        )
        self.assertEqual(command, ["cmd.exe", "/d", "/s", "/c", expected])
        self.assertIn(f'"{executable}"', command[-1])
        self.assertIn(f'"{run_input}"', command[-1])

    def test_optistruct_nobg_stays_inside_batch_command(self) -> None:
        executable = Path(r"D:\Altair Suite\hwsolvers\scripts\optistruct.cmd")
        run_input = Path(r"D:\CAE Jobs\model.fem")

        command = _solver_command(executable, run_input, 8, "optistruct")

        expected = subprocess.list2cmdline(
            [str(executable), str(run_input), "-ncpu", "8", "-nobg"]
        )
        self.assertEqual(command, ["cmd.exe", "/d", "/s", "/c", expected])
        self.assertTrue(command[-1].endswith("-nobg"))


if __name__ == "__main__":
    unittest.main()
