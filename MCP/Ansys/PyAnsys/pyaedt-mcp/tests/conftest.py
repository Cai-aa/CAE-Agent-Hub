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

"""Test configuration for PyAEDT-MCP tests."""

from pathlib import Path
import shutil
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

# Add src to path for imports
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))


@pytest.fixture(scope="module")
def file_tmp_root(tmp_path_factory, request):
    """Create a module-scoped temporary root for generated test artifacts."""
    module_path = Path(request.fspath)
    name = module_path.stem
    root = tmp_path_factory.mktemp(f"{name}-")
    yield root
    try:
        shutil.rmtree(root, ignore_errors=True)
    except Exception:
        pass


@pytest.fixture
def test_tmp_dir(file_tmp_root, request):
    """Create a per-test temporary directory for generated artifacts."""
    temp_dir = file_tmp_root / request.node.name.split("[", 1)[0]
    if temp_dir.exists():
        shutil.rmtree(temp_dir, ignore_errors=True)
    temp_dir.mkdir(parents=True, exist_ok=True)
    return temp_dir


@pytest.fixture
def mock_desktop():
    """Create a mock AEDT Desktop instance for testing."""
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
    desktop.release_desktop = MagicMock()
    desktop.save_project = MagicMock()
    desktop.close_project = MagicMock()
    desktop.open_project = MagicMock()
    desktop.design_list = MagicMock(return_value=["Design1", "Design2"])
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
    """Create a PyAEDTAppContext without Desktop (simulating no connection)."""
    from ansys.aedt.mcp.server import PyAEDTAppContext

    ctx = PyAEDTAppContext()
    ctx.desktop = None
    return ctx


@pytest.fixture
def mock_context(app_context):
    """Create a mock Context with PyAEDTAppContext for testing tools."""
    context = MagicMock()
    context.request_context = MagicMock()
    context.request_context.lifespan_context = app_context
    context.enable_components = AsyncMock()
    context.disable_components = AsyncMock()
    return context


@pytest.fixture
def mock_context_no_desktop(app_context_no_desktop):
    """Create a mock Context without Desktop for testing error handling."""
    context = MagicMock()
    context.request_context = MagicMock()
    context.request_context.lifespan_context = app_context_no_desktop
    context.enable_components = AsyncMock()
    context.disable_components = AsyncMock()
    return context
