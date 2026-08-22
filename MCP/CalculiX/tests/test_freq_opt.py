# -*- coding: utf-8 -*-
"""Tests for frequency-constrained sizing optimization (avoid resonance).

Mock tests fake the solver with the analytic plate response (f1 = 9.29 * t Hz,
mass = 0.1413 * t kg) so the optimizer's search behaviour is deterministic.
The end-to-end test runs real ccx and is skipped automatically when ccx is
not detected.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))

import solver  # noqa: E402  (top-level: the optimizer does `import solver`, monkeypatch must hit the same module)

import pytest  # noqa: E402

from tools.optimizer import _metrics_from_results, optimize_structure  # noqa: E402
from tools.solver import detect_ccx  # noqa: E402

EXAMPLE = ROOT / "examples" / "plate_modal.inp"

has_ccx = pytest.mark.skipif(
    not detect_ccx(), reason="ccx executable not found (set CCX_EXE or install CalculiX)"
)

# Euler-Bernoulli cantilever plate: f1 = (beta1^2/2pi)(t/L^2)sqrt(E/12rho)
# ~= 9.29*t Hz for L=300 steel; mass = rho*L*W*t = 0.1413*t kg.
HZ_PER_MM = 9.29
KG_PER_MM = 0.1413


def _thickness_from_inp(path):
    text = Path(path).read_text(encoding="utf-8")
    m = re.search(r"\*SHELL SECTION[^\n]*\n\s*([0-9.eE+-]+)", text)
    assert m, f"no shell section thickness found in {path}"
    return float(m.group(1))


def _fake_results(t_mm):
    f1 = HZ_PER_MM * t_mm
    return {
        "status": "ok",
        "mass": KG_PER_MM * t_mm / 1000.0,  # tonnes, as read_results reports
        "max_stress_vm": None,
        "max_disp": None,
        "frequencies": [
            {"mode": 1, "eigenvalue": (2 * 3.141592653589793 * f1) ** 2, "freq_rad_s": 2 * 3.141592653589793 * f1, "freq_hz": f1},
            {"mode": 2, "eigenvalue": 0.0, "freq_rad_s": 0.0, "freq_hz": HZ_PER_MM * t_mm * 6.26},
        ],
    }


def test_metrics_extract_frequency_modes():
    """Each eigenmode becomes a freq_<N>_hz metric in Hz."""
    res = _fake_results(4.0)
    m = _metrics_from_results(res)
    assert m["mass"] == pytest.approx(KG_PER_MM * 4.0)
    assert m["freq_1_hz"] == pytest.approx(HZ_PER_MM * 4.0)
    assert m["freq_2_hz"] == pytest.approx(HZ_PER_MM * 4.0 * 6.26)
    assert _metrics_from_results({"mass": None}).get("freq_1_hz") is None


def test_unknown_constraint_metric_rejected(tmp_path):
    """A typo'd metric raises with the valid names instead of optimizing garbage."""
    with pytest.raises(ValueError, match="freq_1_hz"):
        optimize_structure(
            str(EXAMPLE),
            {"shell.PLATE.thickness": [2.0, 8.0]},
            constraints=[{"metric": "first_frequency", "op": ">", "value": 30.0}],
            n_lhs=1,
            max_solves=2,
            work_dir=str(tmp_path),
        )


def test_freq_constrained_optimization_mock(tmp_path, monkeypatch):
    """Avoid-resonance run lands on the f1 floor (analytic t* ~ 3.23 mm)."""
    def fake_run(inp, timeout=1800, **kw):
        return {"status": "ok", "dat_path": inp, "elapsed": 0.0, "errors": []}

    def fake_read(result_path, **kw):
        t = _thickness_from_inp(result_path if str(result_path).endswith(".inp") else str(result_path).replace(".dat", ".inp"))
        return _fake_results(t)

    monkeypatch.setattr(solver, "run_solver", fake_run)
    monkeypatch.setattr(solver, "read_results", fake_read)

    result = optimize_structure(
        str(EXAMPLE),
        {"shell.PLATE.thickness": [2.0, 8.0]},
        constraints=[{"metric": "freq_1_hz", "op": ">", "value": 30.0}],
        n_lhs=4,
        max_iters=8,
        max_solves=40,
        seed=3,
        work_dir=str(tmp_path),
    )
    assert result["status"] == "ok"
    assert result["best"]["feasible"]
    best_t = result["best"]["vars"]["shell.PLATE.thickness"]
    best_f1 = result["best"]["freq_1_hz"]
    assert best_f1 == pytest.approx(30.0, rel=0.10)  # thins down to the floor
    assert 3.2 < best_t < 3.6  # analytic optimum 30/9.29 = 3.23
    assert result["best"]["mass_reduction_pct"] < 0  # lighter than the t=4 baseline
    # the optimized deck was persisted with the best thickness
    assert _thickness_from_inp(result["best"]["inp_path"]) == pytest.approx(best_t)


def test_static_constraints_on_modal_deck_warn(tmp_path, monkeypatch):
    """Default stress/disp constraints on a modal deck: warned, never feasible."""
    def fake_run(inp, timeout=1800, **kw):
        return {"status": "ok", "dat_path": inp, "elapsed": 0.0, "errors": []}

    def fake_read(result_path, **kw):
        t = _thickness_from_inp(result_path if str(result_path).endswith(".inp") else str(result_path).replace(".dat", ".inp"))
        return _fake_results(t)

    monkeypatch.setattr(solver, "run_solver", fake_run)
    monkeypatch.setattr(solver, "read_results", fake_read)

    result = optimize_structure(
        str(EXAMPLE),
        {"shell.PLATE.thickness": [2.0, 8.0]},
        constraints=None,  # defaults: max_stress_vm + max_disp - absent on a modal deck
        n_lhs=2,
        max_solves=4,
        work_dir=str(tmp_path),
    )
    assert result["all_feasible_found"] is False
    assert any("freq_" in w for w in result["warnings"])


@has_ccx
def test_freq_constrained_end_to_end(tmp_path):
    """Real ccx: min mass s.t. f1 >= 30 Hz on the shell plate lands near t* ~ 3.2 mm."""
    result = optimize_structure(
        str(EXAMPLE),
        {"shell.PLATE.thickness": [2.0, 8.0]},
        constraints=[{"metric": "freq_1_hz", "op": ">", "value": 30.0}],
        n_lhs=5,
        max_iters=6,
        max_solves=18,
        seed=7,
        timeout=600,
        work_dir=str(tmp_path / "run"),
    )
    assert result["status"] == "ok"
    assert result["best"]["feasible"]
    best_t = result["best"]["vars"]["shell.PLATE.thickness"]
    best_f1 = result["best"]["freq_1_hz"]
    # ccx f1 at t=4 is 37.6 Hz (EB hand calc 37.1); the floor is hit near t ~ 3.2
    assert best_f1 >= 30.0
    assert best_f1 < 34.0
    assert 3.0 < best_t < 3.6
    assert result["best"]["mass_reduction_pct"] < 0
    assert result["baseline"]["freq_1_hz"] == pytest.approx(37.63, abs=0.5)
