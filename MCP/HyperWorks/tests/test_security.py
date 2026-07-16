from __future__ import annotations

import unittest

from hyperworks_mcp.security import validate_tcl


class TclSecurityTests(unittest.TestCase):
    def test_hypermesh_commands_are_allowed(self) -> None:
        result = validate_tcl('puts "ok"\n*createmark nodes 1 all\n')
        self.assertTrue(result["valid"])

    def test_process_escape_is_blocked(self) -> None:
        with self.assertRaisesRegex(ValueError, "exec"):
            validate_tcl('set x [exec powershell.exe -Command whoami]\n')

    def test_quit_is_owned_by_runner(self) -> None:
        with self.assertRaisesRegex(ValueError, "quit"):
            validate_tcl("*quit 1\n")

    def test_absolute_output_path_is_blocked(self) -> None:
        with self.assertRaisesRegex(ValueError, "absolute Windows path"):
            validate_tcl('*writefile "C:/outside/model.hm" 1\n')


if __name__ == "__main__":
    unittest.main()
