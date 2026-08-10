# -*- coding: utf-8 -*-
"""Tests for the two-stage sizing optimizer.

The optimizer loop is exercised with a MOCKED solver: ``run_solver`` is a no-op
that reports success, and ``read_results`` returns surrogate mass/stress/disp
derived from the current shell thickness in the deck. This lets the full
LHS + coordinate-descent loop run deterministically with no CalculiX install.

A real ccx end-to-end run is covered separately by the ccx-gated solver tests.
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# tools/ first so `import solver` / `import inp_parser` resolve to the SAME module
# objects the optimizer uses (it imports them as top-level names); ROOT so the
# `tools` package imports cleanly.
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

import inp_parser  # noqa: E402
import solver  # noqa: E402
from tools.optimizer import optimize_structure  # noqa: E402

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def _load_gen_bracket():
    spec = importlib.util.spec_from_file_location("gen_bracket", EXAMPLES / "gen_bracket.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _gen_deck(tmp_path: Path) -> Path:
    gen = _load_gen_bracket()
    deck = tmp_path / "bracket.inp"
    gen.main(deck)
    return deck


def _install_surrogate(monkeypatch, gen):
    """Replace solver.run_solver / read_results with thickness-driven surrogates.

    mass(t) = area * t * rho (tonnes); stress(t) = K_s / t^2 (MPa);
    disp(t) = K_d / t^3 (mm). With K_s=2500, K_d=62.5 the feasibility boundary
    (sigma<250, disp<1.5) sits near t~=3.5 mm, so a baseline of 5 mm has room to
    reduce mass while staying feasible.
    """
    area = gen.L * gen.W

    def fake_run(inp_path, timeout=1800):
        return {"status": "ok", "dat_path": str(inp_path), "elapsed": 0.0,
                "errors": [], "stdout_tail": ""}

    def fake_read(result_path):
        dvars = inp_parser.list_design_vars(str(result_path))["variables"]
        t = next((v["current_value"] for v in dvars
                  if v["var_id"] == "shell.PLATE.thickness"), None)
        if not t or t <= 0:
            return {"status": "error", "mass": None,
                    "max_stress_vm": None, "max_disp": None}
        return {"status": "ok",
                "mass": area * t * gen.RHO,
                "max_stress_vm": 2500.0 / (t * t),
                "max_disp": 62.5 / (t ** 3)}

    monkeypatch.setattr(solver, "run_solver", fake_run)
    monkeypatch.setattr(solver, "read_results", fake_read)


def test_bracket_deck_exposes_thickness_var(tmp_path):
    """The generated deck parses and exposes shell.PLATE.thickness, editable in place."""
    deck = _gen_deck(tmp_path)
    dvars = inp_parser.list_design_vars(str(deck))["variables"]
    ids = {v["var_id"]: v for v in dvars}
    assert "shell.PLATE.thickness" in ids
    assert ids["shell.PLATE.thickness"]["current_value"] == pytest.approx(5.0, abs=1e-3)

    out = tmp_path / "bracket_t3.inp"
    inp_parser.modify_card(str(deck), "shell.PLATE.thickness", 3.0, out_path=str(out))
    after = {v["var_id"]: v for v in inp_parser.list_design_vars(str(out))["variables"]}
    assert after["shell.PLATE.thickness"]["current_value"] == pytest.approx(3.0, abs=1e-3)


def test_optimize_reduces_mass(monkeypatch, tmp_path):
    """Optimizer returns a feasible design no heavier than the baseline, with history."""
    gen = _load_gen_bracket()
    deck = _gen_deck(tmp_path)
    _install_surrogate(monkeypatch, gen)

    res = optimize_structure(
        str(deck),
        {"shell.PLATE.thickness": [2.0, 8.0]},
        n_lhs=5,
        max_solves=24,
        max_iters=6,
        seed=42,
    )

    assert res["status"] == "ok"
    base = res["baseline"]["mass_kg"]
    best = res["best"]["mass_kg"]
    assert base is not None and best is not None
    assert best <= base + 1e-9                      # never worse than baseline
    assert res["best"]["feasible"] is True         # best satisfies the constraints
    assert res["best"]["stress_vm"] < 250.0
    assert res["best"]["disp"] < 1.5
    assert len(res["history"]) >= 2                # baseline + >=1 evaluation
    assert Path(res["best"]["inp_path"]).exists()  # optimized deck persisted
    assert res["n_solves"] >= 1


def test_optimize_persists_best_thickness(monkeypatch, tmp_path):
    """The persisted optimized deck carries the best thickness, not the baseline's."""
    gen = _load_gen_bracket()
    deck = _gen_deck(tmp_path)
    _install_surrogate(monkeypatch, gen)

    res = optimize_structure(str(deck), {"shell.PLATE.thickness": [2.0, 8.0]},
                             n_lhs=5, max_solves=24, seed=42)
    best_t = res["best"]["vars"]["shell.PLATE.thickness"]
    persisted = {v["var_id"]: v for v in
                 inp_parser.list_design_vars(res["best"]["inp_path"])["variables"]}
    assert persisted["shell.PLATE.thickness"]["current_value"] == pytest.approx(best_t, abs=1e-3)


def test_optimize_rejects_bad_inputs(tmp_path):
    deck = _gen_deck(tmp_path)
    with pytest.raises(ValueError):
        optimize_structure(str(deck), {})                       # no variables
    with pytest.raises(ValueError):
        optimize_structure(str(deck), {"shell.PLATE.thickness": [5.0, 2.0]})  # lo >= hi
    with pytest.raises(ValueError):
        optimize_structure(str(deck), {"shell.PLATE.thickness": [2.0, 8.0]},
                           objective={"metric": "mass", "direction": "maximize"})
    with pytest.raises(NotImplementedError):
        optimize_structure(str(deck), {"shell.PLATE.thickness": [2.0, 8.0]},
                           strategy="bayesian")
