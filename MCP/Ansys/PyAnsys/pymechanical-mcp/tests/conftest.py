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

"""Pytest configuration and fixtures for PyMechanical MCP Server tests."""

import sys
from unittest.mock import AsyncMock, MagicMock

from mcp.server.session import ServerSession
import pytest

from ansys.mechanical.mcp.server import PyMechanicalAppContext


@pytest.fixture
def mock_mechanical():
    """Create a mock Mechanical instance for testing."""
    mechanical = MagicMock()
    mechanical.name = "Mechanical"
    mechanical.version = "2024 R2"
    mechanical._ip = "127.0.0.1"
    mechanical._port = 10000
    mechanical.ip = "127.0.0.1"
    mechanical.port = 10000
    mechanical.run_python_script = MagicMock(return_value="Script executed")
    mechanical.exit = MagicMock()

    # Mock common Mechanical attributes
    mechanical.project_directory = "/tmp/mechanical_project"
    mechanical.directory = "/tmp/mechanical_project"
    mechanical.is_alive = True
    mechanical.is_local = True
    mechanical._exited = False
    mechanical._exiting = False
    mechanical.status = "Running"
    mechanical.platform = "linux"
    mechanical.jobname = "file"
    mechanical.check_status = "running"

    # Mock information class
    mechanical.information = MagicMock()
    mechanical.information.title = "Test Project"
    mechanical.information.jobname = "file"
    mechanical.information.routine = ""
    mechanical.information.units = "SI"
    mechanical.information.revision = "2024 R2"
    mechanical.information.product = "Mechanical"

    return mechanical


@pytest.fixture
def app_context(mock_mechanical):
    """Create a PyMechanicalAppContext with a mock Mechanical instance."""
    return PyMechanicalAppContext(mechanical=mock_mechanical)


@pytest.fixture
def app_context_no_mechanical():
    """Create a PyMechanicalAppContext without Mechanical (simulating connection failure)."""
    return PyMechanicalAppContext(mechanical=None)


@pytest.fixture
def mock_server_session():
    """Create a mock ServerSession for testing."""
    session = MagicMock(spec=ServerSession)
    return session


@pytest.fixture
def mock_context(mock_server_session, app_context):
    """Create a mock Context with PyMechanicalAppContext for testing tools."""
    context = MagicMock()
    context.request_context = MagicMock()
    context.request_context.lifespan_context = app_context
    context.enable_components = AsyncMock()
    context.disable_components = AsyncMock()
    return context


@pytest.fixture
def mock_context_no_mechanical(mock_server_session, app_context_no_mechanical):
    """Create a mock Context without Mechanical for testing error handling."""
    context = MagicMock()
    context.request_context = MagicMock()
    context.request_context.lifespan_context = app_context_no_mechanical
    context.enable_components = AsyncMock()
    context.disable_components = AsyncMock()
    return context


@pytest.fixture
def app_server():
    """Create a FastMCP server instance for testing."""
    from ansys.mechanical.mcp.server import app

    return app


@pytest.fixture(autouse=True)
def reset_stderr():
    """Ensure stderr is reset between tests."""
    original_stderr = sys.stderr
    yield
    sys.stderr = original_stderr
