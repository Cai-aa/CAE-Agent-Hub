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

"""Tests for error handling in PyMAPDL MCP Server."""

from unittest.mock import MagicMock

from fastmcp.tools.base import ToolResult
import pytest

from ansys.mapdl.mcp.tools import check_mapdl_status, run_mapdl_command


@pytest.mark.unit
class TestErrorHandling:
    """Tests for error handling in various scenarios."""

    def test_mapdl_command_failure(self, mock_context):
        """Test handling of MAPDL command failures."""
        # Make the run method raise an exception
        mock_context.request_context.lifespan_context.mapdl.run.side_effect = RuntimeError(
            "MAPDL command failed"
        )

        with pytest.raises(RuntimeError) as exc_info:
            run_mapdl_command(mock_context, "INVALID_COMMAND")

        assert "MAPDL command failed" in str(exc_info.value)

    def test_none_mapdl_instance(self, mock_context_no_mapdl):
        """Test handling when MAPDL instance is None."""
        # Should return helpful error message instead of raising exception
        result = check_mapdl_status(mock_context_no_mapdl)
        assert isinstance(result, ToolResult)
        assert "No MAPDL connection available" in result.content[0].text

    def test_invalid_context_structure(self):
        """Test handling of invalid context structure."""
        # Create a context with missing mapdl attribute
        invalid_context = MagicMock()
        invalid_context.request_context = MagicMock()
        invalid_context.request_context.lifespan_context = MagicMock()
        invalid_context.request_context.lifespan_context.mapdl = None

        result = check_mapdl_status(invalid_context)
        assert "No MAPDL connection available" in result.content[0].text

    def test_mapdl_timeout(self, mock_context):
        """Test handling of MAPDL timeout scenarios."""
        # Simulate a timeout
        mock_context.request_context.lifespan_context.mapdl.run.side_effect = TimeoutError(
            "MAPDL command timed out"
        )

        with pytest.raises(TimeoutError) as exc_info:
            run_mapdl_command(mock_context, "/SOLVE")

        assert "timed out" in str(exc_info.value)

    def test_empty_command_string(self, mock_context):
        """Test handling of empty command string."""
        # This should not raise an error, but pass empty string to MAPDL
        result = run_mapdl_command(mock_context, "")

        assert "executed successfully" in result.content[0].text
        mock_context.request_context.lifespan_context.mapdl.run.assert_called_once_with("")

    def test_very_long_command(self, mock_context):
        """Test handling of very long commands."""
        # MAPDL has line length limits, but our code should pass it through
        long_command = "COMMENT" + "X" * 1000
        result = run_mapdl_command(mock_context, long_command)

        assert "executed successfully" in result.content[0].text
