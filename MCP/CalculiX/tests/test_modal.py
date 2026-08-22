# -*- coding: utf-8 -*-
"""Tests for modal (*FREQUENCY) parsing and mode-shape export.

Parser tests run against canned ``.dat`` text (no solver needed). The
end-to-end test runs a real ccx frequency solve and is skipped automatically
when ccx is not detected.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from tools.result_exporter import _parse_dat_modal_modes, export_result_mesh  # noqa: E402
from tools.solver import _parse_dat_frequencies, detect_ccx, read_results, run_solver  # noqa: E402

EXAMPLE = ROOT / "examples" / "cantilever_modal.inp"

has_ccx = pytest.mark.skipif(
    not detect_ccx(), reason="ccx executable not found (set CCX_EXE or install CalculiX)"
)

# Euler-Bernoulli clamped-free target for the demo bar (steel, mm-t-s-MPa);
# ccx C3D8 shear-locks ~5-10% stiff, so the tolerance is deliberately generous.
F1_HAND_CALC_HZ = 464.0

CANNED = """
     E I G E N V A L U E   O U T P U T

 MODE NO    EIGENVALUE                       FREQUENCY
                                     REAL PART            IMAGINARY PART
                           (RAD/TIME)      (CYCLES/TIME     (RAD/TIME)

      1   0.9932799E+07   0.3151634E+04   0.5015982E+03   0.0000000E+00
      2   0.9932799E+07   0.3151634E+04   0.5015982E+03   0.0000000E+00

     P A R T I C I P A T I O N   F A C T O R S

MODE NO.   X-COMPONENT     Y-COMPONENT     Z-COMPONENT
      1  -0.9382478E-18   0.5929612E-02   0.1307281E-02

                    E I G E N V A L U E    N U M B E R     1

 displacements (vx,vy,vz) for set NALL and time  0.1000000E+01

         1  0.000000E+00  0.000000E+00  0.000000E+00
         2  1.000000E+00  2.000000E+00  3.000000E+00

                    E I G E N V A L U E    N U M B E R     2

 displacements (vx,vy,vz) for set NALL and time  0.1000000E+01

         1  0.000000E+00  0.000000E+00  0.000000E+00
         2 -1.000000E+00 -2.000000E+00 -3.000000E+00
"""


def test_freq_table_parses_and_stops_at_participation():
    """Two eigenvalue rows parse; the participation-factor rows must NOT be swallowed."""
    rows, count = _parse_dat_frequencies(CANNED)
    assert count == 2
    assert [r["mode"] for r in rows] == [1, 2]
    assert rows[0]["freq_hz"] == pytest.approx(501.5982, rel=1e-6)
    assert rows[0]["freq_rad_s"] == pytest.approx(3151.634, rel=1e-6)
    assert rows[0]["eigenvalue"] == pytest.approx(9.932799e6, rel=1e-6)


def test_modal_modes_split_by_marker():
    """Each E I G E N V A L U E N U M B E R block yields its own node->vector map."""
    modes = _parse_dat_modal_modes(CANNED)
    assert sorted(modes) == [1, 2]
    assert modes[1][2] == pytest.approx([1.0, 2.0, 3.0])
    assert modes[2][2] == pytest.approx([-1.0, -2.0, -3.0])  # sign-flipped, not overwritten
    assert modes[1][1] == [0.0, 0.0, 0.0]


def test_export_mode_missing_raises(tmp_path):
    """A mode absent from the .dat raises instead of silently exporting zeros."""
    dat = tmp_path / "canned.dat"
    dat.write_text(CANNED, encoding="utf-8")
    with pytest.raises(ValueError, match="mode 3"):
        export_result_mesh(str(EXAMPLE), dat_path=str(dat), mode=3)
    with pytest.raises(ValueError, match="no \\.dat"):
        export_result_mesh(str(EXAMPLE), dat_path=str(tmp_path / "nothing.dat"), mode=1)


def test_export_modal_schema_canned(tmp_path):
    """Mode export speaks the viewer's modal schema (hole-plate-modal contract)."""
    dat = tmp_path / "canned.dat"
    dat.write_text(CANNED, encoding="utf-8")
    res = export_result_mesh(
        str(EXAMPLE), dat_path=str(dat), mode=1, out_path=str(tmp_path / "m1.json")
    )
    assert res["analysisType"] == "modal"
    assert res["mode"] == 1
    assert res["step"] == "Mode 1"
    assert res["fieldLabel"] == "U, Magnitude"
    assert res["frequencyHz"] == pytest.approx(501.5982, rel=1e-6)
    # displacement normalised: canned node 2 has the only non-zero vector
    mags = {nd["label"]: nd["modalMagnitude"] for nd in res["nodes"]}
    assert mags[2] == pytest.approx(1.0)
    assert mags[1] == pytest.approx(0.0)
    assert res["fieldRanges"]["maxDisplacement"] == pytest.approx(1.0)
    assert res["fieldRanges"]["rawMaxDisplacement"] == pytest.approx(14**0.5)
    # element colour scalar = mean |u| over connectivity; element 1 holds nodes 1,2
    assert res["elements"][0]["mises"] == pytest.approx(1.0 / 8.0)
    assert res["elements"][0]["value"] == pytest.approx(res["elements"][0]["mises"])


@has_ccx
def test_modal_end_to_end(tmp_path):
    """Real ccx frequency solve: 5 modes, f1 near the hand calc, degenerate pair."""
    inp = tmp_path / "cantilever_modal.inp"
    inp.write_text(EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    solve = run_solver(str(inp), timeout=600)
    assert solve["status"] == "ok", solve.get("errors")
    r = read_results(str(tmp_path))
    assert r["status"] == "ok"
    assert r["n_modes"] == 5
    freqs = r["frequencies"]
    assert freqs[0]["freq_hz"] == pytest.approx(F1_HAND_CALC_HZ, rel=0.15)
    # omega = 2 pi f consistency
    assert freqs[0]["freq_rad_s"] == pytest.approx(
        2 * 3.141592653589793 * freqs[0]["freq_hz"], rel=1e-6
    )
    # square 8x8 section -> doubly symmetric -> degenerate bending pair
    assert freqs[1]["freq_hz"] == pytest.approx(freqs[0]["freq_hz"], rel=1e-9)


@has_ccx
def test_export_mode_shape(tmp_path):
    """Mode 1 exports the viewer modal schema against a real ccx solve."""
    inp = tmp_path / "cantilever_modal.inp"
    inp.write_text(EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    run_solver(str(inp), timeout=600)
    out_path = tmp_path / "mode1.json"
    res = export_result_mesh(str(inp), mode=1, out_path=str(out_path))
    assert res["step"] == "Mode 1"
    assert res["analysisType"] == "modal"
    assert res["frequencyHz"] == pytest.approx(501.6, rel=0.05)
    assert len(res["nodes"]) == 625 and len(res["elements"]) == 384
    mags = [nd["modalMagnitude"] for nd in res["nodes"]]
    assert max(mags) == pytest.approx(1.0)  # normalised eigenvector
    assert all(0.0 <= m <= 1.0 for m in mags)
    elem_vals = [e["mises"] for e in res["elements"]]
    assert 0.0 < max(elem_vals) <= 1.0  # colour = mean |u| per element
    assert res["fieldRanges"]["rawMaxDisplacement"] > 0.0  # true mass-normalised max
    tip = max(res["nodes"], key=lambda nd: nd["label"])
    assert tip["modalMagnitude"] > 0.5  # mode 1: the free tip moves most
