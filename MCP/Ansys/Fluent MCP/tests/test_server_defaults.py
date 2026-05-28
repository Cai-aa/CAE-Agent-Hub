from __future__ import annotations

import os
import unittest
from unittest import mock

import server


class ServerDefaultsTests(unittest.TestCase):
    def test_pyfluent_defaults_use_environment_values(self) -> None:
        env = {
            "PYFLUENT_DIMENSION": "2",
            "PYFLUENT_PRECISION": "single",
            "PYFLUENT_PROCESSOR_COUNT": "6",
            "PYFLUENT_LAUNCH_MODE": "meshing",
            "PYFLUENT_UI_MODE": "gui",
            "PYFLUENT_START_TIMEOUT": "240",
        }

        with mock.patch.dict(os.environ, env, clear=False):
            defaults = server.pyfluent_defaults()

        self.assertEqual(defaults["dimension"], 2)
        self.assertEqual(defaults["precision"], "single")
        self.assertEqual(defaults["processor_count"], 6)
        self.assertEqual(defaults["mode"], "meshing")
        self.assertEqual(defaults["ui_mode"], "gui")
        self.assertEqual(defaults["start_timeout"], 240)


if __name__ == "__main__":
    unittest.main()
