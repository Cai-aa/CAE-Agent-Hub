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

"""Tests for error handling in PyAEDT-MCP."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_desktop():
    """Create a mock AEDT Desktop instance."""
    desktop = MagicMock()
    desktop.aedt_version_id = "2026.1"
    desktop.aedt_version_string = "AEDT 2026 R1"
    desktop.aedt_install_dir = "C:\\Program Files\\ANSYS Inc\\v261\\AnsysEM"
    desktop.is_grpc_api = True
    desktop.machine = "localhost"
    desktop.port = 50051
    desktop.non_graphical = True
    desktop.aedt_process_id = 12345
    desktop.project_list = ["Project1", "Project2"]
    desktop.installed_versions = {"261": "C:\\Program Files\\ANSYS Inc\\v261"}
    return desktop


@pytest.fixture
def app_context(mock_desktop):
    """Create a PyAEDTAppContext with a mock Desktop instance."""
    from ansys.aedt.mcp.server import PyAEDTAppContext

    ctx = PyAEDTAppContext()
    ctx.desktop = mock_desktop
    return ctx


@pytest.fixture
def app_context_no_desktop():
    """Create a PyAEDTAppContext without Desktop."""
    from ansys.aedt.mcp.server import PyAEDTAppContext

    ctx = PyAEDTAppContext()
    ctx.desktop = None
    return ctx


@pytest.fixture
def mock_context(app_context):
    """Create a mock Context with PyAEDTAppContext."""
    context = MagicMock()
    context.request_context = MagicMock()
    context.request_context.lifespan_context = app_context
    context.enable_components = AsyncMock()
    context.disable_components = AsyncMock()
    return context


@pytest.fixture
def mock_context_no_desktop(app_context_no_desktop):
    """Create a mock Context without Desktop."""
    context = MagicMock()
    context.request_context = MagicMock()
    context.request_context.lifespan_context = app_context_no_desktop
    context.enable_components = AsyncMock()
    context.disable_components = AsyncMock()
    return context


@pytest.mark.unit
class TestErrorHandling:
    """Tests for error handling in various scenarios."""

    def test_run_python_script_failure(self, mock_context):
        """Test handling of script execution failures."""
        from ansys.aedt.mcp.tools import run_python_script

        # Mock the script execution to fail
        with patch("builtins.open", side_effect=FileNotFoundError("Script not found")):
            result = run_python_script(mock_context, "/nonexistent/script.py")
            assert "Error" in result or "not found" in result.lower()

    def test_none_desktop_instance(self, mock_context_no_desktop):
        """Test handling when Desktop instance is None."""
        from ansys.aedt.mcp.tools import check_aedt_status

        result = check_aedt_status(mock_context_no_desktop)
        assert isinstance(result, str)
        assert "No AEDT connection is available" in result

    def test_invalid_context_structure(self):
        """Test handling of invalid context structure."""
        from ansys.aedt.mcp.tools import check_aedt_status

        # Create a context with missing desktop attribute
        invalid_context = MagicMock()
        invalid_context.request_context = MagicMock()
        invalid_context.request_context.lifespan_context = MagicMock()
        invalid_context.request_context.lifespan_context.desktop = None

        result = check_aedt_status(invalid_context)
        assert "No AEDT connection is available" in result

    @pytest.mark.asyncio
    async def test_desktop_connection_error(self, mock_context_no_desktop):
        """Test handling of Desktop connection errors."""
        from ansys.aedt.mcp.tools import connect_to_aedt

        # Mock Desktop to raise connection error
        with patch("ansys.aedt.core.Desktop", side_effect=RuntimeError("Connection refused")):
            result = await connect_to_aedt(
                mock_context_no_desktop, machine="invalid-server", port=50051
            )
            assert "Error" in result or "Failed" in result or "Connection refused" in result

    def test_invalid_project_path(self, mock_context):
        """Test handling of invalid project paths."""
        from ansys.aedt.mcp.tools import open_project

        mock_context.request_context.lifespan_context.desktop.open_project.side_effect = (
            FileNotFoundError("Project file not found")
        )

        result = open_project(mock_context, "/nonexistent/project.aedt")
        assert "Error" in result or "not found" in result.lower() or "Failed" in result

    def test_analyze_without_design(self, mock_context_no_desktop):
        """Test analyze when no design is active."""
        from ansys.aedt.mcp.tools import analyze_design

        result = analyze_design(mock_context_no_desktop)
        assert "No AEDT connection" in result or "Error" in result

    def test_empty_python_code(self, mock_context):
        """Test handling of empty Python code."""
        from ansys.aedt.mcp.tools import run_python_code

        result = run_python_code(mock_context, "")
        # Empty code should still execute without error (may return empty result)
        assert isinstance(result, str)

    def test_malformed_python_code(self, mock_context):
        """Test handling of malformed Python code."""
        from ansys.aedt.mcp.tools import run_python_code

        # Simulate syntax error in code execution
        mock_context.request_context.lifespan_context.python_session = MagicMock()
        mock_context.request_context.lifespan_context.python_session.execute.side_effect = (
            SyntaxError("invalid syntax")
        )

        result = run_python_code(mock_context, "def foo( :")
        # Should handle the error gracefully
        assert isinstance(result, str)

    def test_export_results_no_solution(self, mock_context_no_desktop):
        """Test export when no solution is available."""
        from ansys.aedt.mcp.tools import export_results

        result = export_results(mock_context_no_desktop, output_path="/tmp/results.snp")
        assert "No AEDT connection" in result or "Error" in result
