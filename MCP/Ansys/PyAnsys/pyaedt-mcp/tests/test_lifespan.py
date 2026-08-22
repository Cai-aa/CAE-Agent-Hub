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

"""Tests for MCP server lifespan management."""

from unittest.mock import MagicMock

import pytest

from ansys.aedt.mcp.server import PyAEDTAppContext, app


@pytest.mark.unit
def test_app_context_dataclass():
    """Test that PyAEDTAppContext is properly defined as a dataclass."""
    from dataclasses import is_dataclass

    assert is_dataclass(PyAEDTAppContext)

    # Test creating PyAEDTAppContext with Desktop
    mock_desktop = MagicMock()
    ctx = PyAEDTAppContext()
    ctx.desktop = mock_desktop
    assert ctx.desktop == mock_desktop

    # Test creating PyAEDTAppContext without Desktop
    ctx_none = PyAEDTAppContext()
    ctx_none.desktop = None
    assert ctx_none.desktop is None


@pytest.mark.unit
def test_app_context_default_values():
    """Test default values for PyAEDTAppContext."""
    ctx = PyAEDTAppContext()

    assert ctx.desktop is None
    assert ctx.transport_type == "stdio"
    assert ctx.aedt_machine is None
    assert ctx.aedt_port is None
    assert ctx.aedt_version is None
    assert ctx.non_graphical is True
    assert ctx.connect_on_startup is False
    assert ctx.dynamic_tool_discovery is False
    assert ctx.http_host == "127.0.0.1"
    assert ctx.include_context_tools is False
    assert ctx.http_port == 8080
    assert ctx.cors_origins is None


@pytest.mark.unit
def test_app_context_product_instance_property():
    """Test product_instance property getter and setter."""
    mock_desktop = MagicMock()
    ctx = PyAEDTAppContext()

    # Test getter returns None initially
    assert ctx.product_instance is None

    # Test setter via property
    ctx.product_instance = mock_desktop
    assert ctx.product_instance == mock_desktop
    assert ctx.desktop == mock_desktop


@pytest.mark.unit
def test_mcp_server_initialization():
    """Test that MCP server is properly initialized."""
    assert app is not None
    assert app.name == "PyAEDT-MCP"


@pytest.mark.unit
def test_mcp_server_has_tools():
    """Test that MCP server has registered tools."""
    from ansys.aedt.mcp.tools import check_aedt_status, connect_to_aedt, run_python_code

    assert callable(check_aedt_status)
    assert callable(run_python_code)
    assert callable(connect_to_aedt)


@pytest.mark.unit
def test_mcp_server_tool_registration():
    """Test that tools are properly registered with the MCP server."""
    import asyncio

    from ansys.aedt.mcp import app

    async def _list():
        return await app._local_provider._list_tools()

    # Get the list of tools from the server
    tools = asyncio.run(_list())

    # Should have multiple tools registered
    assert len(tools) > 0

    # Check for expected tool names
    tool_names = [tool.name for tool in tools]
    assert "check_aedt_status" in tool_names
    assert "connect_to_aedt" in tool_names
    assert "run_python_code" in tool_names


@pytest.mark.unit
def test_pyaedt_mcp_class():
    """Test PyAEDTMCP class instantiation."""
    from ansys.aedt.mcp.server import PyAEDTMCP

    # Test with default name
    mcp = PyAEDTMCP()
    assert mcp.name == "PyAEDT-MCP"

    # Test with custom name
    mcp_custom = PyAEDTMCP(name="Custom AEDT Server")
    assert mcp_custom.name == "Custom AEDT Server"


@pytest.mark.unit
def test_create_context():
    """Test context creation in PyAEDTMCP."""

    from ansys.aedt.mcp.server import PyAEDTAppContext, PyAEDTMCP

    mcp = PyAEDTMCP()

    # Create context without CLI config
    context = mcp.create_context()

    assert isinstance(context, PyAEDTAppContext)
    assert context.desktop is None
    assert context.python_session is not None


@pytest.mark.unit
def test_context_cli_config_population():
    """Test that context is populated from CLI config."""
    from ansys.aedt.mcp.server import PyAEDTMCP

    mcp = PyAEDTMCP()

    # Set CLI config on mcp instance directly
    setattr(
        mcp,
        "_cli_config",
        {
            "transport_type": "http",
            "aedt_machine": "remote-server",
            "aedt_port": 50052,
            "aedt_version": "2026.1",
            "non_graphical": False,
            "connect_on_startup": True,
            "dynamic_tool_discovery": True,
            "http_host": "0.0.0.0",
            "http_port": 9000,
            "cors_origins": ["http://localhost:3000"],
            "include_context_tools": True,
        },
    )

    context = mcp.create_context()

    assert context.transport_type == "http"
    assert context.aedt_machine == "remote-server"
    assert context.aedt_port == 50052
    assert context.aedt_version == "2026.1"
    assert context.non_graphical is False
    assert context.connect_on_startup is True
    assert context.dynamic_tool_discovery is True
    assert context.http_host == "0.0.0.0"
    assert context.http_port == 9000
    assert context.cors_origins == ["http://localhost:3000"]
    assert context.include_context_tools is True
