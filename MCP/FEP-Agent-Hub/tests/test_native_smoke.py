from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.skipif(os.environ.get("OPEN_CAE_NATIVE_TESTS") != "1", reason="set OPEN_CAE_NATIVE_TESTS=1 for CAE executables")
def test_real_heat_smoke() -> None:
    root = Path(__file__).parents[1]
    completed = subprocess.run(
        [sys.executable, str(root / "scripts" / "run_heat_smoke.py")],
        cwd=root,
        shell=False,
        timeout=900,
        check=False,
    )
    assert completed.returncode == 0

