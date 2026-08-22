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

"""Tests for MCP server lifespan management."""

from unittest.mock import MagicMock

import pytest

from ansys.mapdl.mcp.server import PyMAPDLAppContext, app


@pytest.mark.unit
def test_app_context_dataclass():
    """Test that PyMAPDLAppContext is properly defined as a dataclass."""
    from dataclasses import is_dataclass

    assert is_dataclass(PyMAPDLAppContext)

    # Test creating PyMAPDLAppContext with MAPDL
    mock_mapdl = MagicMock()
    ctx = PyMAPDLAppContext(mapdl=mock_mapdl)
    assert ctx.mapdl == mock_mapdl

    # Test creating PyMAPDLAppContext without MAPDL
    ctx_none = PyMAPDLAppContext(mapdl=None)
    assert ctx_none.mapdl is None


@pytest.mark.unit
def test_mcp_server_initialization():
    """Test that MCP server is properly initialized."""
    assert app is not None
    assert app.name == "PyMAPDL MCP Server"


@pytest.mark.unit
def test_mcp_server_has_tools():
    """Test that MCP server has registered tools."""
    # The mcp server should have tools registered
    # This is a basic check to ensure tools are defined
    from ansys.mapdl.mcp.tools import (
        check_mapdl_status,
        run_mapdl_command,
    )

    assert callable(check_mapdl_status)
    assert callable(run_mapdl_command)
