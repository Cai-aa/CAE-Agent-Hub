# -*- coding: utf-8 -*-
"""Tests for the result_mesh.json exporter.

Mesh-only tests run without a solver. The field test needs ccx and is skipped
automatically when the executable is not detected.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from tools.result_exporter import export_result_mesh  # noqa: E402
from tools.solver import detect_ccx, run_solver  # noqa: E402

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "cantilever.inp"

_NODE_KEYS = {"label", "coordinates", "displacement", "deformed"}
_ELEM_KEYS = {"label", "type", "connectivity", "mises"}

has_ccx = pytest.mark.skipif(
    not detect_ccx(), reason="ccx executable not found (set CCX_EXE or install CalculiX)"
)


def test_mesh_only_export_schema(tmp_path):
    out = tmp_path / "result_mesh.json"
    r = export_result_mesh(str(EXAMPLE), dat_path=None, out_path=str(out))
    assert len(r["nodes"]) == 625
    assert len(r["elements"]) == 384
    assert r["elementType"] == "C3D8"
    assert r["schemaVersion"] == 1
    assert all(set(n) == _NODE_KEYS for n in r["nodes"])
    assert all(set(e) == _ELEM_KEYS for e in r["elements"])
    # connectivity holds 1-based node labels in range
    n_nodes = len(r["nodes"])
    for e in r["elements"]:
        assert all(1 <= c <= n_nodes for c in e["connectivity"])
    # no fields without a .dat
    assert r["fieldRanges"]["misesMax"] == 0.0
    assert r["fieldRanges"]["maxDisplacement"] == 0.0


def test_mesh_only_export_writes_file(tmp_path):
    out = tmp_path / "rm.json"
    export_result_mesh(str(EXAMPLE), dat_path=None, out_path=str(out))
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["elementType"] == "C3D8"
    assert len(data["nodes"]) == 625


@has_ccx
def test_dat_export_with_fields(tmp_path):
    inp = tmp_path / "cantilever.inp"
    inp.write_text(EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    run_solver(str(inp), timeout=600)
    r = export_result_mesh(str(inp), out_path=str(tmp_path / "result_mesh.json"))
    # every element carried a von Mises value out of the .dat
    assert all(e["mises"] > 0.0 for e in r["elements"])
    assert r["fieldRanges"]["misesMax"] == pytest.approx(max(e["mises"] for e in r["elements"]))
    # displacement matches the cantilever hand calc (~0.8 mm)
    assert r["fieldRanges"]["maxDisplacement"] == pytest.approx(0.8, rel=0.5)
    # deformation scale is magnified (auto) and baked into deformed; the loaded
    # tip deflects in -Z, so deformed min-z is more negative than the original min-z
    assert r["deformationScale"] > 1.0
    assert min(n["deformed"][2] for n in r["nodes"]) < min(n["coordinates"][2] for n in r["nodes"])
