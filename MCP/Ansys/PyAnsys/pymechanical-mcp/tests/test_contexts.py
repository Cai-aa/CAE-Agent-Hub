# Copyright (C) 2026 Synopsys, Inc. and ANSYS, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for MCP context tools (formerly resources)."""

import pytest


@pytest.mark.asyncio
async def test_context_tools_registered():
    """Test that the consolidated context tool is registered with the MCP server."""
    # Import contexts and tools to register them with the app
    from ansys.mechanical.mcp import contexts, tools  # noqa: F401
    from ansys.mechanical.mcp.server import app

    tool_list = await app._local_provider._list_tools()
    tool_names = [t.name for t in tool_list]
    assert "get_guidelines_for" in tool_names


def test_workflow_overview_content():
    """Test that workflow overview tool returns expected content."""
    from ansys.mechanical.mcp import contexts

    content = contexts.get_guidelines_for_workflow_overview()

    # Check for key sections in the overview
    assert "Mechanical Simulation Workflow Overview" in content
    assert "Preprocessing" in content
    assert "Postprocessing" in content


def test_geometry_import_content():
    """Test geometry import tool content."""
    from ansys.mechanical.mcp import contexts

    content = contexts.get_guidelines_for_geometry_import()

    assert "Geometry Import" in content
    assert "STEP" in content or ".stp" in content
    assert "AddGeometryImport" in content


def test_materials_content():
    """Test materials tool content."""
    from ansys.mechanical.mcp import contexts

    content = contexts.get_guidelines_for_materials()

    assert "Material Definition" in content
    assert "Structural Steel" in content
    assert "body.Material" in content


def test_meshing_content():
    """Test meshing tool content."""
    from ansys.mechanical.mcp import contexts

    content = contexts.get_guidelines_for_meshing()

    assert "Mesh" in content
    assert "GenerateMesh" in content


def test_boundary_conditions_content():
    """Test boundary conditions tool content."""
    from ansys.mechanical.mcp import contexts

    content = contexts.get_guidelines_for_boundary_conditions()

    assert "Boundary" in content or "Load" in content


def test_analysis_setup_content():
    """Test analysis setup tool content."""
    from ansys.mechanical.mcp import contexts

    content = contexts.get_guidelines_for_analysis_setup()

    assert "Analysis" in content
    assert "Static Structural" in content or "Modal" in content or "Thermal" in content


def test_solution_content():
    """Test solution tool content."""
    from ansys.mechanical.mcp import contexts

    content = contexts.get_guidelines_for_solution()

    assert "Solution" in content or "Solve" in content


def test_postprocessing_content():
    """Test postprocessing tool content."""
    from ansys.mechanical.mcp import contexts

    content = contexts.get_guidelines_for_postprocessing()

    assert "Postprocessing" in content or "Result" in content


def test_named_selections_content():
    """Test named selections tool content."""
    from ansys.mechanical.mcp import contexts

    content = contexts.get_guidelines_for_named_selections()

    assert "Named Selection" in content or "NamedSelection" in content


def test_general_rules_content():
    """Test general rules tool content."""
    from ansys.mechanical.mcp import contexts

    content = contexts.get_guidelines_for_general_rules()

    assert "General" in content or "Rules" in content or "Best Practices" in content


def test_all_context_tools_return_strings():
    """Test that all context tool functions return strings."""
    from ansys.mechanical.mcp import contexts

    context_tool_functions = [
        contexts.get_guidelines_for_workflow_overview,
        contexts.get_guidelines_for_geometry_import,
        contexts.get_guidelines_for_materials,
        contexts.get_guidelines_for_meshing,
        contexts.get_guidelines_for_analysis_setup,
        contexts.get_guidelines_for_boundary_conditions,
        contexts.get_guidelines_for_solution,
        contexts.get_guidelines_for_postprocessing,
        contexts.get_guidelines_for_named_selections,
        contexts.get_guidelines_for_general_rules,
    ]

    for func in context_tool_functions:
        result = func()
        assert isinstance(result, str), f"{func.__name__} should return a string"
        assert len(result) > 0, f"{func.__name__} should return non-empty string"
