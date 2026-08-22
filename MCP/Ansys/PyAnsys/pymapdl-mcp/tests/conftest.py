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

"""Pytest configuration and fixtures for PyMAPDL MCP Server tests."""

import sys
from unittest.mock import AsyncMock, MagicMock

from mcp.server.session import ServerSession
import pytest

from ansys.mapdl.mcp.server import PyMAPDLAppContext


@pytest.fixture
def mock_mapdl():
    """Create a mock MAPDL instance for testing."""
    mapdl = MagicMock()
    mapdl.version = "2024 R2"
    mapdl.com = MagicMock(return_value="Comment written")
    mapdl.run = MagicMock(return_value="Command executed")
    mapdl.exit = MagicMock()

    # Mock common MAPDL attributes
    mapdl.jobname = "file"
    mapdl.name = "MAPDL instance 0"
    mapdl.check_status = "RUNNING"
    mapdl.directory = "/tmp"
    mapdl.parameters = {}
    mapdl.is_alive = True
    mapdl.is_local = True
    mapdl.port = 50052
    mapdl.ip = "127.0.0.1"
    mapdl._exited = False
    mapdl._exiting = False
    mapdl.platform = "linux"

    # Mock Information class
    mapdl.info = MagicMock()
    mapdl.info.title = "Test Analysis"
    mapdl.info.jobname = "file"
    mapdl.info.routine = "PREP7"
    mapdl.info.units = "SI"
    mapdl.info.revision = "2024 R2"
    mapdl.info.product = "ANSYS Mechanical Enterprise"

    # Mock Geometry class
    mapdl.geometry = MagicMock()
    mapdl.geometry.n_keypoint = 0
    mapdl.geometry.n_line = 0
    mapdl.geometry.n_area = 0
    mapdl.geometry.n_volu = 0

    # Mock Post_processing class
    mapdl.post_processing = MagicMock()
    mapdl.post_processing.nsets = 0

    # Mock Mesh class
    mapdl.mesh = MagicMock()
    mapdl.mesh.n_node = 0
    mapdl.mesh.n_elem = 0

    # Mock ComponentManager
    mock_components = MagicMock()
    mock_components.__len__ = MagicMock(return_value=2)
    mock_components.names = ("COMP_NODES", "COMP_ELEMS")
    mock_components.types = ("NODES", "ELEMS")
    mock_components.items = MagicMock(
        return_value={"COMP_NODES": "NODES", "COMP_ELEMS": "ELEMS"}.items()
    )
    mapdl.components = mock_components

    # Mock get_value for material, section and parts queries
    def _get_value_side_effect(entity, entnum, item1, *args, **kwargs):
        entity_upper = str(entity).upper()
        item1_upper = str(item1).upper()
        if entity_upper == "MAT":
            if item1_upper in ("NUM", "COUNT"):
                return 2
        if entity_upper == "SECP":
            if item1_upper in ("NUM", "COUNT"):
                return 2
        if entity_upper == "PART":
            if item1_upper == "NUMP":
                return 0
        return 0

    mapdl.get_value = MagicMock(side_effect=_get_value_side_effect)

    return mapdl


@pytest.fixture
def app_context(mock_mapdl):
    """Create an PyMAPDLAppContext with a mock MAPDL instance."""
    return PyMAPDLAppContext(mapdl=mock_mapdl)


@pytest.fixture
def app_context_no_mapdl():
    """Create an PyMAPDLAppContext without MAPDL (simulating connection failure)."""
    return PyMAPDLAppContext(mapdl=None)


@pytest.fixture
def mock_server_session():
    """Create a mock ServerSession for testing."""
    session = MagicMock(spec=ServerSession)
    return session


@pytest.fixture
def mock_context(mock_server_session, app_context):
    """Create a mock Context with PyMAPDLAppContext for testing tools."""
    context = MagicMock()
    context.request_context = MagicMock()
    context.request_context.lifespan_context = app_context
    context.enable_components = AsyncMock()
    context.disable_components = AsyncMock()
    return context


@pytest.fixture
def mock_context_no_mapdl(mock_server_session, app_context_no_mapdl):
    """Create a mock Context without MAPDL for testing error handling."""
    context = MagicMock()
    context.request_context = MagicMock()
    context.request_context.lifespan_context = app_context_no_mapdl
    context.enable_components = AsyncMock()
    context.disable_components = AsyncMock()
    return context


@pytest.fixture
def app_server():
    """Create a FastMCP server instance for testing."""
    from ansys.mapdl.mcp.server import app

    return app


@pytest.fixture(autouse=True)
def reset_stderr():
    """Ensure stderr is reset between tests."""
    original_stderr = sys.stderr
    yield
    sys.stderr = original_stderr
