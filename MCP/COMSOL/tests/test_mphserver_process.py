from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.mphserver_process import build_mphserver_command, mphserver_status


class MphServerProcessTests(unittest.TestCase):
    def test_build_mphserver_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "comsol.exe"
            exe.write_text("", encoding="utf-8")

            command = build_mphserver_command(str(exe), port=2037, extra_args=["-login", "never"])

            self.assertEqual(command, [str(exe.resolve()), "mphserver", "-port", "2037", "-login", "never"])

    def test_status_reports_closed_port(self):
        status = mphserver_status(host="127.0.0.1", port=9)

        self.assertFalse(status["listening"])
        self.assertEqual(status["port"], 9)

    def test_native_windows_server_has_no_extra_mphserver_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe=Path(tmp)/'comsolmphserver.exe'; exe.touch()
            command=build_mphserver_command(str(exe),2038,['-multi','on'])
            self.assertEqual(command,[str(exe.resolve()),'-port','2038','-multi','on'])


if __name__ == "__main__":
    unittest.main()
