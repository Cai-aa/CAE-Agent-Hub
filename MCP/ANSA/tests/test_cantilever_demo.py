from __future__ import annotations

from ansa_mcp.cantilever_demo import _write_model


def test_fixed_cantilever_deck_has_consistent_mesh_and_load(tmp_path):
    target = tmp_path / "cantilever.inp"
    _write_model(target)
    text = target.read_text(encoding="ascii")
    lines = text.splitlines()
    start_nodes = lines.index("*Node") + 1
    start_elements = lines.index("*Element, type=C3D8I, elset=EALL")
    end_elements = lines.index("*Nset, nset=FIX")
    assert start_elements - start_nodes == 615
    assert end_elements - start_elements - 1 == 320
    assert "*Cload\nTIP, 3, -6.666666666667" in text
    assert "*Boundary\nFIX, 1, 3, 0.0" in text
    assert "40, 200.00000000, 0.00000000, 0.00000000" not in text
    assert "41, 200.00000000, 0.00000000, 0.00000000" in text
