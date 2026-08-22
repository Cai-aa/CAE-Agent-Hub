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

from ansys.mechanical.mcp.server import PyMechanicalAppContext, app


@pytest.mark.unit
def test_app_context_dataclass():
    """Test that PyMechanicalAppContext is properly defined as a dataclass."""
    from dataclasses import is_dataclass

    assert is_dataclass(PyMechanicalAppContext)

    # Test creating PyMechanicalAppContext with Mechanical
    mock_mechanical = MagicMock()
    ctx = PyMechanicalAppContext(mechanical=mock_mechanical)
    assert ctx.mechanical == mock_mechanical

    # Test creating PyMechanicalAppContext without Mechanical
    ctx_none = PyMechanicalAppContext(mechanical=None)
    assert ctx_none.mechanical is None


@pytest.mark.unit
def test_mcp_server_initialization():
    """Test that MCP server is properly initialized."""
    assert app is not None
    assert app.name == "PyMechanical-MCP"


@pytest.mark.unit
def test_mcp_server_has_tools():
    """Test that MCP server has registered tools."""
    # The mcp server should have tools registered
    # This is a basic check to ensure tools are defined
    from ansys.mechanical.mcp.tools import check_mechanical_status, run_python_script

    assert callable(check_mechanical_status)
    assert callable(run_python_script)
