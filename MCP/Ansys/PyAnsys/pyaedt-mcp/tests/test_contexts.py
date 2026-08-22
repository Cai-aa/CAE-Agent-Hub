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

"""Unit tests for PyAEDT-MCP context/guideline tools."""

import pytest


@pytest.mark.asyncio
async def test_context_tools_registered():
    """Test that the consolidated context tool is available when the context tag is enabled."""
    # Import contexts and tools to register them with the app
    from ansys.aedt.mcp import contexts, tools  # noqa: F401
    from ansys.aedt.mcp.server import app

    app.enable(tags={"pyaedt_context"})
    try:
        tool_list = await app.list_tools()
    finally:
        app.disable(tags={"pyaedt_context"})

    tool_names = [t.name for t in tool_list]
    assert "get_guidelines_for" in tool_names


class TestGuidelineTools:
    """Tests for guideline context tools."""

    def test_workflow_overview(self):
        """Test workflow overview guideline."""
        from ansys.aedt.mcp import contexts

        result = contexts.get_guidelines_for_workflow_overview()
        assert "AEDT Simulation Workflow" in result
        assert "PyAEDT Architecture" in result
        assert "HFSS" in result
        assert "Maxwell" in result

    def test_hfss_guidelines(self):
        """Test HFSS guideline."""
        from ansys.aedt.mcp import contexts

        result = contexts.get_guidelines_for_hfss()
        assert "HFSS Simulation Guidelines" in result
        assert "Modal" in result
        assert "wave_port" in result

    def test_maxwell_guidelines(self):
        """Test Maxwell guideline."""
        from ansys.aedt.mcp import contexts

        result = contexts.get_guidelines_for_maxwell()
        assert "Maxwell" in result
        assert "Magnetostatic" in result
        assert "assign_winding" in result

    def test_icepak_guidelines(self):
        """Test Icepak guideline."""
        from ansys.aedt.mcp import contexts

        result = contexts.get_guidelines_for_icepak()
        assert "Icepak Thermal Simulation" in result
        assert "SteadyState" in result
        assert "assign_solid_block" in result

    def test_circuit_guidelines(self):
        """Test Circuit guideline."""
        from ansys.aedt.mcp import contexts

        result = contexts.get_guidelines_for_circuit()
        assert "Circuit Simulation Guidelines" in result
        assert "create_resistor" in result
        assert "Touchstone" in result

    def test_geometry_guidelines(self):
        """Test geometry guideline."""
        from ansys.aedt.mcp import contexts

        result = contexts.get_guidelines_for_geometry()
        assert "Geometry Creation Guidelines" in result
        assert "create_box" in result
        assert "Boolean Operations" in result

    def test_mesh_guidelines(self):
        """Test mesh guideline."""
        from ansys.aedt.mcp import contexts

        result = contexts.get_guidelines_for_mesh()
        assert "Mesh Setup Guidelines" in result
        assert "assign_length_mesh" in result
        assert "adaptive" in result.lower()

    def test_boundaries_guidelines(self):
        """Test boundaries guideline."""
        from ansys.aedt.mcp import contexts

        result = contexts.get_guidelines_for_boundaries()
        assert "Boundary and Excitation Guidelines" in result
        assert "radiation_boundary" in result.lower()
        assert "wave_port" in result

    def test_postprocessing_guidelines(self):
        """Test postprocessing guideline."""
        from ansys.aedt.mcp import contexts

        result = contexts.get_guidelines_for_postprocessing()
        assert "Postprocessing Guidelines" in result
        assert "create_report" in result
        assert "export_touchstone" in result

    def test_parametric_guidelines(self):
        """Test parametric guideline."""
        from ansys.aedt.mcp import contexts

        result = contexts.get_guidelines_for_parametric()
        assert "Parametric" in result
        assert "Optimization" in result
        assert "add_variable" in result
