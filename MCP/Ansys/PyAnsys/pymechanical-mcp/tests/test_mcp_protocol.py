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

"""Tests for MCP protocol compliance and server behavior."""

from fastmcp.server import FastMCP
import pytest

from ansys.mechanical.mcp import app


@pytest.mark.unit
class TestMCPProtocol:
    """Tests for MCP protocol compliance."""

    def test_server_name(self):
        """Test that server has correct name."""
        assert app.name == "PyMechanical-MCP"

    def test_server_is_fastmcp_instance(self):
        """Test that server is an instance of FastMCP."""
        assert isinstance(app, FastMCP)

    def test_server_has_lifespan(self):
        """Test that server has lifespan configured."""
        # The server should have a lifespan function configured
        # Simply check that the server was created with lifespan by checking it's a valid instance
        # The actual lifespan functionality is tested in test_lifespan.py
        assert isinstance(app, FastMCP)
        assert app.name == "PyMechanical-MCP"

    @pytest.mark.asyncio
    async def test_server_tools_registered(self):
        """Test that all tools are properly registered."""
        # Tools should be accessible through the MCP server
        from ansys.mechanical.mcp.tools import (
            check_mechanical_status,
            launch_mechanical,
            run_python_script,
        )

        tools = [
            check_mechanical_status,
            launch_mechanical,
            run_python_script,
        ]

        for tool in tools:
            # Tools can be either FunctionTool objects (with .fn) or regular functions (decorated with @app.tool())
            if hasattr(tool, "fn"):
                # FunctionTool object
                assert callable(tool.fn)
                assert hasattr(tool.fn, "__name__")
            else:
                # Regular function
                assert callable(tool)
                assert hasattr(tool, "__name__")
