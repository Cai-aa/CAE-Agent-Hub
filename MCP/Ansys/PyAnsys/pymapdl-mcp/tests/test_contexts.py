# Copyright (C) 2025 - 2026 ANSYS, Inc. and/or its affiliates.
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
    """Test that the unified get_guidelines_for tool is registered with the MCP server."""
    # Import contexts and tools to register them with the app
    from ansys.mapdl.mcp import contexts, tools  # noqa: F401
    from ansys.mapdl.mcp.server import app

    # Get list of registered tools
    tool_list = await app.list_tools()

    tool_names = [t.name for t in tool_list]

    assert "get_guidelines_for" in tool_names, "Tool get_guidelines_for not found"

    # Old individual tools must NOT be registered anymore
    old_tools = [
        "get_guidelines_for_workflow_overview",
        "get_guidelines_for_preprocessing_geometry",
        "get_guidelines_for_preprocessing_elements",
        "get_guidelines_for_preprocessing_materials",
        "get_guidelines_for_preprocessing_mesh",
        "get_guidelines_for_preprocessing_boundary_conditions",
        "get_guidelines_for_solution_phase",
        "get_guidelines_for_postprocessing_phase",
        "get_guidelines_for_general_rules",
    ]
    for old_name in old_tools:
        assert old_name not in tool_names, f"Old tool {old_name} should not be registered"


def test_workflow_overview_content():
    """Test that 'workflow' content returns expected sections."""
    from ansys.mapdl.mcp import contexts

    content = contexts.get_guidelines_for(content="workflow")

    assert "MAPDL Simulation Workflow Overview" in content
    assert "Preprocessing" in content
    assert "Solution" in content
    assert "Postprocessing" in content
    assert "General Rules" in content


def test_preprocessing_geometry_content():
    """Test 'geometry' content."""
    from ansys.mapdl.mcp import contexts

    content = contexts.get_guidelines_for(content="geometry")

    assert "Geometry Guidelines" in content
    assert "2D vs 3D" in content
    assert "finite elements" in content


def test_preprocessing_elements_content():
    """Test 'elements' content."""
    from ansys.mapdl.mcp import contexts

    content = contexts.get_guidelines_for(content="elements")

    assert "Element Type Selection" in content
    assert "SOLID186" in content
    assert "SHELL181" in content
    assert "BEAM189" in content


def test_preprocessing_materials_content():
    """Test 'materials' content."""
    from ansys.mapdl.mcp import contexts

    content = contexts.get_guidelines_for(content="materials")

    assert "Material Property Definition" in content
    assert "Steel" in content or "steel" in content
    assert "Aluminum" in content or "aluminum" in content


def test_preprocessing_mesh_content():
    """Test 'mesh' content."""
    from ansys.mapdl.mcp import contexts

    content = contexts.get_guidelines_for(content="mesh")

    assert "Mesh Generation Guidelines" in content
    assert "mesh quality" in content.lower()
    assert "vmesh" in content or "VMESH" in content


def test_preprocessing_boundary_conditions_content():
    """Test 'boundary_conditions' content."""
    from ansys.mapdl.mcp import contexts

    content = contexts.get_guidelines_for(content="boundary_conditions")

    assert "Boundary Conditions and Loads" in content
    assert "Fixed Supports" in content or "fixed supports" in content
    assert "beam elements" in content.lower()


def test_solution_phase_content():
    """Test 'solution' content."""
    from ansys.mapdl.mcp import contexts

    content = contexts.get_guidelines_for(content="solution")

    assert "Solution" in content
    assert "STATIC" in content
    assert "MODAL" in content
    assert "TRANSIENT" in content
    assert "mapdl.solution()" in content


def test_postprocessing_phase_content():
    """Test 'postprocessing' content."""
    from ansys.mapdl.mcp import contexts

    content = contexts.get_guidelines_for(content="postprocessing")

    assert "Postprocessing" in content
    assert "post1" in content
    assert "post26" in content
    assert "plot_nodal_solution" in content


def test_general_rules_content():
    """Test 'general' content."""
    from ansys.mapdl.mcp import contexts

    content = contexts.get_guidelines_for(content="general")

    assert "General Rules" in content
    assert "Accuracy" in content or "accuracy" in content
    assert "convergence" in content.lower()
    assert "verification" in content.lower()


def test_all_contents_return_non_empty_strings():
    """Test that get_guidelines_for returns a non-empty string for every valid content value."""
    from ansys.mapdl.mcp import contexts

    all_contents = [
        "workflow",
        "geometry",
        "elements",
        "materials",
        "mesh",
        "boundary_conditions",
        "solution",
        "postprocessing",
        "general",
    ]

    for content in all_contents:
        result = contexts.get_guidelines_for(content=content)
        assert isinstance(result, str), f"get_guidelines_for('{content}') should return a string"
        assert len(result) > 0, f"get_guidelines_for('{content}') should return non-empty string"
