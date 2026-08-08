# -*- coding: utf-8 -*-
"""Tests for the ccx solver + .dat reader.

These require a working CalculiX executable. They are skipped automatically when
``ccx`` is not on PATH (and ``CCX_EXE`` unset), so the suite stays green on a
machine without the solver installed.
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from tools.solver import detect_ccx, read_results, run_solver  # noqa: E402

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "cantilever.inp"

has_ccx = pytest.mark.skipif(
    not detect_ccx(), reason="ccx executable not found (set CCX_EXE or install CalculiX)"
)

# Euler-Bernoulier sanity targets for the cantilever (steel C3D8 bar, mm-t-s-MPa,
# P=100N tip). Hand calc is extreme-fibre; ccx reports integration-point values
# (lower), so the tolerances below are deliberately generous.
TIP_DISP_MM = 0.8       # delta = P L^3 / (3 E I), I = W H^3 / 12
ROOT_STRESS_MPA = 140.0  # sigma = P L (H/2) / I


@has_ccx
def test_run_solver_succeeds(tmp_path):
    inp = tmp_path / "cantilever.inp"
    inp.write_text(EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    res = run_solver(str(inp), timeout=600)
    assert res["status"] == "ok", res.get("errors")
    assert res["sta_has_data"] is True
    assert res["dat_path"]


@has_ccx
def test_read_results_physically_sane(tmp_path):
    inp = tmp_path / "cantilever.inp"
    inp.write_text(EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    run_solver(str(inp), timeout=600)
    r = read_results(str(tmp_path))
    assert r["status"] == "ok"
    assert r["max_disp"] is not None and math.isfinite(r["max_disp"])
    assert r["max_disp"] == pytest.approx(TIP_DISP_MM, rel=0.5)   # within 2x of hand calc
    assert r["max_stress_vm"] is not None and math.isfinite(r["max_stress_vm"])
    assert r["max_stress_vm"] == pytest.approx(ROOT_STRESS_MPA, rel=2.0)
    assert r["mass"] is not None and r["mass"] > 0.0
