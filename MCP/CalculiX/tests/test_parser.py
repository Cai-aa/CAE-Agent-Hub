# -*- coding: utf-8 -*-
"""Tests for the .inp parser over the public cantilever benchmark (C3D8 solids)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from tools.inp_parser import list_design_vars, modify_card, parse_model  # noqa: E402

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "cantilever.inp"


def test_parse_model_basic_counts():
    m = parse_model(str(EXAMPLE))
    assert m["nodes"] == 625
    assert m["elements_by_type"] == {"C3D8": 384}
    assert m["shell_sections"] == []  # solid model: no shell sections


def test_parse_model_material_and_load():
    m = parse_model(str(EXAMPLE))
    assert "STEEL" in m["materials"]
    assert m["materials"]["STEEL"]["elastic"]["E"] == pytest.approx(210000.0)
    assert m["materials"]["STEEL"]["elastic"]["nu"] == pytest.approx(0.3)
    assert m["materials"]["STEEL"]["density"]["rho"] == pytest.approx(7.85e-9)
    assert len(m["loads"]) == 1
    assert m["loads"][0]["type"] == "CLOAD"
    assert m["loads"][0]["dof"] == pytest.approx(3.0)
    assert m["loads"][0]["magnitude"] == pytest.approx(-4.0)


def test_list_design_vars_covers_categories():
    dv = list_design_vars(str(EXAMPLE))
    # solid model: E, nu, density, load (no shell thickness / beam section)
    assert dv["count"] == 4
    var_ids = {v["var_id"] for v in dv["variables"]}
    assert "material.STEEL.E" in var_ids
    assert "material.STEEL.nu" in var_ids
    assert "material.STEEL.density" in var_ids
    assert "cload.0.magnitude" in var_ids


def test_modify_card_elastic_E_roundtrip(tmp_path):
    dst = tmp_path / "cantilever_modified.inp"
    dst.write_text(EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    res = modify_card(str(dst), "material.STEEL.E", 200000.0)
    assert res["changed"] is True
    assert res["old_value"] == pytest.approx(210000.0)
    assert res["new_value"] == pytest.approx(200000.0)
    m = parse_model(str(dst))
    assert m["materials"]["STEEL"]["elastic"]["E"] == pytest.approx(200000.0)
