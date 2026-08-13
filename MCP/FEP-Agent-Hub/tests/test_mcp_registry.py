from __future__ import annotations

from elmer_mcp.server import mcp as elmer
from freecad_mcp.server import mcp as freecad
from paraview_mcp.server import mcp as paraview


def test_expected_tool_counts_and_names() -> None:
    assert len(freecad._tool_manager._tools) == 15
    assert len(elmer._tool_manager._tools) == 17
    assert len(paraview._tool_manager._tools) == 17
    assert "freecad_export_step" in freecad._tool_manager._tools
    assert "elmer_solver_run" in elmer._tool_manager._tools
    assert "elmer_excitation_set" in elmer._tool_manager._tools
    assert "paraview_export_image" in paraview._tool_manager._tools


def test_no_arbitrary_execution_tools() -> None:
    names = set(freecad._tool_manager._tools) | set(elmer._tool_manager._tools) | set(paraview._tool_manager._tools)
    forbidden = {"run_shell", "exec_python", "eval", "powershell", "run_arbitrary_executable"}
    assert names.isdisjoint(forbidden)
