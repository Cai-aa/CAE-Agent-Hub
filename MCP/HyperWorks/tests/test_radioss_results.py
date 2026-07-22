from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hyperworks_mcp.radioss_results import (
    audit_radioss_output_files,
    parse_radioss_engine_output,
)


ENGINE_OUTPUT = """
   CYCLE    TIME      TIME-STEP  ELEMENT          ERROR  I-ENERGY    K-ENERGY T  K-ENERGY R  EXT-WORK     MAS.ERR     TOTAL MASS  MASS ADDED
       0   0.000      0.2853E-03 SOLID         12   0.0%   0.000      0.1766E-01   0.000       0.000       0.000      0.2983E-02   0.000
    3500   0.9979     0.2853E-03 SOLID         10 -11.3%   0.1330E-02 0.1433E-01   0.000       0.000       0.000      0.2983E-02   0.000
NORMAL TERMINATION
"""


class RadiossResultTests(unittest.TestCase):
    def test_parses_engine_quality_signals(self) -> None:
        result = parse_radioss_engine_output(ENGINE_OUTPUT)
        self.assertTrue(result["normal_termination"])
        self.assertEqual(result["progress_row_count"], 2)
        self.assertEqual(result["maximum_absolute_energy_error_percent"], 11.3)
        self.assertAlmostEqual(result["minimum_time_step"], 2.853e-4)

    def test_audit_applies_explicit_quality_gates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            starter = root / "impact_0000.out"
            engine = root / "impact_0001.out"
            starter.write_text(
                "NORMAL TERMINATION\n0 ERROR(S)\n0 WARNING(S)\n", encoding="utf-8"
            )
            engine.write_text(ENGINE_OUTPUT, encoding="utf-8")
            passed = audit_radioss_output_files(starter, engine)
            failed = audit_radioss_output_files(
                starter, engine, maximum_absolute_energy_error_percent=10.0
            )
        self.assertTrue(passed["passed"])
        self.assertFalse(failed["passed"])
        self.assertFalse(failed["gates"]["energy_error_within_limit"])


if __name__ == "__main__":
    unittest.main()
