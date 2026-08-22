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

"""Unit tests for PyAEDT-MCP tools.

These tests mock the AEDT instance and verify tool behavior.
"""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ansys.aedt.mcp import tools  # noqa: F401 - import to register tools
from ansys.aedt.mcp.server import PyAEDTAppContext


@pytest.fixture
def mock_desktop():
    """Create a mock AEDT instance for testing."""
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
    """Create a PyAEDTAppContext with a mock AEDT instance."""
    ctx = PyAEDTAppContext()
    ctx.desktop = mock_desktop
    return ctx


@pytest.fixture
def app_context_no_desktop():
    """Create a PyAEDTAppContext without an AEDT instance (simulating no connection)."""
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
    """Create a mock Context without an AEDT instance for testing error handling."""
    context = MagicMock()
    context.request_context = MagicMock()
    context.request_context.lifespan_context = app_context_no_desktop
    context.enable_components = AsyncMock()
    context.disable_components = AsyncMock()
    return context


@pytest.mark.unit
class TestCheckAEDTStatus:
    """Tests for check_aedt_status tool."""

    def test_no_connection(self, mock_context_no_desktop):
        """Test status check with no connection."""
        from ansys.aedt.mcp.tools import check_aedt_status

        with patch("ansys.aedt.mcp.tools.discover_available_aedt_sessions", return_value=[]):
            result = check_aedt_status(mock_context_no_desktop)

        data = json.loads(result)
        assert data["connected"] is False
        assert "No AEDT connection is available" in data["message"]
        assert "connect_to_aedt" in data["message"]
        assert data["available_sessions"] == []

    def test_no_connection_reports_discovered_sessions(self, mock_context_no_desktop):
        """Test status check returns available system sessions when disconnected."""
        from ansys.aedt.mcp.tools import check_aedt_status

        discovered_sessions = [
            {
                "pid": 111,
                "port": 50061,
                "mode": "grpc",
                "version": "2026.1",
                "non_graphical": True,
                "student_version": False,
                "connectable": True,
            },
            {
                "pid": 222,
                "port": None,
                "mode": "com",
                "version": "2025.2",
                "non_graphical": False,
                "student_version": False,
                "connectable": False,
            },
        ]

        with patch(
            "ansys.aedt.mcp.tools.discover_available_aedt_sessions",
            return_value=discovered_sessions,
        ):
            result = check_aedt_status(mock_context_no_desktop)

        data = json.loads(result)
        assert data["connected"] is False
        assert data["session_count"] == 2
        assert data["connectable_session_count"] == 1
        assert data["connectable_sessions"][0]["port"] == 50061
        assert "launch_aedt(confirm_new_session=True)" in data["message"]

    def test_with_connection(self, mock_context):
        """Test status check with active connection."""
        from ansys.aedt.mcp.tools import check_aedt_status

        with (
            patch("ansys.aedt.mcp.tools.get_aedt_info") as mock_info,
            patch("ansys.aedt.mcp.tools.discover_available_aedt_sessions", return_value=[]),
        ):
            mock_info.return_value = {
                "connection": {
                    "version": "2026.1",
                    "is_grpc": True,
                    "machine": "localhost",
                    "port": 50051,
                },
                "projects": ["Project1", "Project2"],
            }
            result = check_aedt_status(mock_context)
            data = json.loads(result)
            assert data["connected"] is True
            assert data["connection"]["version"] == "2026.1"
            assert data["connection"]["is_grpc"] is True


@pytest.mark.unit
class TestLaunchAEDT:
    """Tests for launch_aedt tool."""

    @pytest.mark.asyncio
    async def test_already_connected(self, mock_context):
        """Test launch when already connected."""
        from ansys.aedt.mcp.tools import launch_aedt

        with patch("ansys.aedt.mcp.tools.session") as mock_session:
            mock_session.locked_connection = False
            result = await launch_aedt(mock_context)
            assert "Already connected" in result

    @pytest.mark.asyncio
    async def test_launch_defaults_to_graphical_mode(self, mock_context_no_desktop):
        """Test launch_aedt defaults to graphical mode."""
        from ansys.aedt.mcp.tools import launch_aedt

        mock_versions = MagicMock()
        mock_versions.current_version = "2026.1"
        mock_versions.latest_version = "2026.1"

        with (
            patch("ansys.aedt.mcp.tools._is_docker", return_value=False),
            patch("ansys.aedt.mcp.tools.aedt_versions", mock_versions),
            patch("ansys.aedt.mcp.tools.discover_available_aedt_sessions", return_value=[]),
            patch("ansys.aedt.core.Desktop") as mock_desktop,
            patch("ansys.aedt.mcp.tools._configure_pyaedt_runtime_settings") as mock_cfg,
        ):
            fake_desktop = MagicMock()
            fake_desktop.aedt_version_id = "2026.1"
            fake_desktop.aedt_install_dir = "C:\\Program Files\\ANSYS Inc\\v261\\AnsysEM"
            fake_desktop.is_grpc_api = True
            mock_desktop.return_value = fake_desktop

            result = await launch_aedt(mock_context_no_desktop)

            call_kwargs = mock_desktop.call_args[1]
            assert call_kwargs["non_graphical"] is False
            assert call_kwargs["version"] == "2026.1"
            mock_cfg.assert_called_once_with()
            assert "Successfully launched AEDT" in result

    @pytest.mark.asyncio
    async def test_launch_asks_to_connect_when_session_exists(self, mock_context_no_desktop):
        """Test launch_aedt refuses to create a new instance when one is attachable."""
        from ansys.aedt.mcp.tools import launch_aedt

        with (
            patch("ansys.aedt.mcp.tools._is_docker", return_value=False),
            patch(
                "ansys.aedt.mcp.tools.discover_available_aedt_sessions",
                return_value=[
                    {
                        "pid": 111,
                        "port": 50062,
                        "mode": "grpc",
                        "version": "2026.1",
                        "non_graphical": True,
                        "student_version": False,
                        "connectable": True,
                    }
                ],
            ),
            patch("ansys.aedt.core.Desktop") as mock_desktop,
        ):
            result = await launch_aedt(mock_context_no_desktop)

        mock_desktop.assert_not_called()
        assert "Ask the user whether to connect" in result
        assert "50062" in result
        assert "launch_aedt(confirm_new_session=True)" in result

    @pytest.mark.asyncio
    async def test_launch_can_be_confirmed_when_sessions_exist(self, mock_context_no_desktop):
        """Test launch_aedt can still create a new instance after explicit confirmation."""
        from ansys.aedt.mcp.tools import launch_aedt

        mock_versions = MagicMock()
        mock_versions.current_version = "2026.1"
        mock_versions.latest_version = "2026.1"

        with (
            patch("ansys.aedt.mcp.tools._is_docker", return_value=False),
            patch("ansys.aedt.mcp.tools.aedt_versions", mock_versions),
            patch(
                "ansys.aedt.mcp.tools.discover_available_aedt_sessions",
                return_value=[
                    {
                        "pid": 111,
                        "port": 50061,
                        "mode": "grpc",
                        "version": "2026.1",
                        "non_graphical": True,
                        "student_version": False,
                        "connectable": True,
                    },
                    {
                        "pid": 222,
                        "port": 50062,
                        "mode": "grpc",
                        "version": "2025.2",
                        "non_graphical": False,
                        "student_version": True,
                        "connectable": True,
                    },
                ],
            ),
            patch("ansys.aedt.core.Desktop") as mock_desktop,
            patch("ansys.aedt.mcp.tools._configure_pyaedt_runtime_settings") as mock_cfg,
        ):
            fake_desktop = MagicMock()
            fake_desktop.aedt_version_id = "2026.1"
            fake_desktop.aedt_install_dir = "C:\\Program Files\\ANSYS Inc\\v261\\AnsysEM"
            fake_desktop.is_grpc_api = True
            mock_desktop.return_value = fake_desktop

            result = await launch_aedt(mock_context_no_desktop, confirm_new_session=True)

        mock_cfg.assert_called_once_with()
        assert mock_desktop.call_args[1]["new_desktop"] is True
        assert "Successfully launched AEDT" in result


@pytest.mark.unit
class TestConnectToAEDT:
    """Tests for connect_to_aedt tool."""

    @pytest.mark.asyncio
    async def test_already_connected(self, mock_context):
        """Test connect when already connected."""
        from ansys.aedt.mcp.tools import connect_to_aedt

        with patch("ansys.aedt.mcp.tools.session") as mock_session:
            mock_session.locked_connection = False
            result = await connect_to_aedt(mock_context, port=50051)
            assert "Already connected" in result

    @pytest.mark.asyncio
    async def test_connect_configures_grpc_runtime_settings(self, mock_context_no_desktop):
        """Test connect_to_aedt configures gRPC and runtime safety settings."""
        from ansys.aedt.mcp.tools import connect_to_aedt

        with (
            patch("ansys.aedt.mcp.tools._is_docker", return_value=False),
            patch("ansys.aedt.mcp.tools.discover_available_aedt_sessions", return_value=[]),
            patch("ansys.aedt.core.Desktop") as mock_desktop,
            patch("ansys.aedt.mcp.tools._configure_pyaedt_runtime_settings") as mock_cfg,
        ):
            fake_desktop = MagicMock()
            fake_desktop.aedt_version_id = "2026.1"
            fake_desktop.is_grpc_api = True
            mock_desktop.return_value = fake_desktop

            result = await connect_to_aedt(mock_context_no_desktop, port=50051)

            mock_cfg.assert_called_once_with(enable_grpc=True)
            assert "Successfully connected to AEDT" in result

    @pytest.mark.asyncio
    async def test_connect_auto_selects_single_discovered_session(self, mock_context_no_desktop):
        """Test connect_to_aedt auto-selects the only discovered local gRPC session."""
        from ansys.aedt.mcp.tools import connect_to_aedt

        fake_desktop = MagicMock()
        fake_desktop.aedt_version_id = "2026.1"
        fake_desktop.is_grpc_api = True

        with (
            patch("ansys.aedt.mcp.tools._is_docker", return_value=False),
            patch(
                "ansys.aedt.mcp.tools.discover_available_aedt_sessions",
                return_value=[
                    {
                        "pid": 111,
                        "port": 50062,
                        "mode": "grpc",
                        "version": "2026.1",
                        "non_graphical": True,
                        "student_version": False,
                        "connectable": True,
                    }
                ],
            ),
            patch("ansys.aedt.core.Desktop", return_value=fake_desktop) as mock_desktop,
            patch("ansys.aedt.mcp.tools._configure_pyaedt_runtime_settings"),
        ):
            result = await connect_to_aedt(mock_context_no_desktop)

        assert "Successfully connected to AEDT" in result
        assert mock_desktop.call_args[1]["port"] == 50062

    @pytest.mark.asyncio
    async def test_connect_returns_selection_prompt_for_multiple_sessions(
        self, mock_context_no_desktop
    ):
        """Test connect_to_aedt asks for a session choice when several are available."""
        from ansys.aedt.mcp.tools import connect_to_aedt

        with (
            patch("ansys.aedt.mcp.tools._is_docker", return_value=False),
            patch(
                "ansys.aedt.mcp.tools.discover_available_aedt_sessions",
                return_value=[
                    {
                        "pid": 111,
                        "port": 50061,
                        "mode": "grpc",
                        "version": "2026.1",
                        "non_graphical": True,
                        "student_version": False,
                        "connectable": True,
                    },
                    {
                        "pid": 222,
                        "port": 50062,
                        "mode": "grpc",
                        "version": "2025.2",
                        "non_graphical": False,
                        "student_version": True,
                        "connectable": True,
                    },
                ],
            ),
        ):
            result = await connect_to_aedt(mock_context_no_desktop)

        assert "Multiple running AEDT gRPC sessions are available" in result
        assert "50061" in result
        assert "50062" in result
        assert "launch_aedt(confirm_new_session=True)" in result

    @pytest.mark.asyncio
    async def test_connect_explicit_port_bypasses_multiple_session_prompt(
        self, mock_context_no_desktop
    ):
        """Test connect_to_aedt honors an explicit port even when several sessions exist."""
        from ansys.aedt.mcp.tools import connect_to_aedt

        fake_desktop = MagicMock()
        fake_desktop.aedt_version_id = "2026.1"
        fake_desktop.is_grpc_api = True

        with (
            patch("ansys.aedt.mcp.tools._is_docker", return_value=False),
            patch(
                "ansys.aedt.mcp.tools.discover_available_aedt_sessions",
                return_value=[
                    {
                        "pid": 111,
                        "port": 50051,
                        "mode": "grpc",
                        "version": "2027.1",
                        "non_graphical": False,
                        "student_version": False,
                        "connectable": True,
                    },
                    {
                        "pid": 222,
                        "port": 50052,
                        "mode": "grpc",
                        "version": "2026.1",
                        "non_graphical": False,
                        "student_version": False,
                        "connectable": True,
                    },
                ],
            ),
            patch("ansys.aedt.core.Desktop", return_value=fake_desktop) as mock_desktop,
            patch("ansys.aedt.mcp.tools._configure_pyaedt_runtime_settings") as mock_cfg,
        ):
            result = await connect_to_aedt(mock_context_no_desktop, port=50051)

        mock_cfg.assert_called_once_with(enable_grpc=True)
        assert mock_desktop.call_args[1]["port"] == 50051
        assert "Successfully connected to AEDT" in result


@pytest.mark.unit
class TestDisconnectFromAEDT:
    """Tests for disconnect_from_aedt tool."""

    @pytest.mark.asyncio
    async def test_no_connection(self, mock_context_no_desktop):
        """Test disconnect with no connection."""
        from ansys.aedt.mcp.tools import disconnect_from_aedt

        with patch("ansys.aedt.mcp.tools.session") as mock_session:
            mock_session.locked_connection = False
            result = await disconnect_from_aedt(mock_context_no_desktop)
            assert "No AEDT connection" in result

    @pytest.mark.asyncio
    async def test_disconnect_requires_explicit_close_choice(self, mock_context):
        """Test disconnect asks whether AEDT should remain open when unspecified."""
        from ansys.aedt.mcp.tools import disconnect_from_aedt

        with patch("ansys.aedt.mcp.tools.session") as mock_session:
            mock_session.locked_connection = False
            result = await disconnect_from_aedt(mock_context)
            assert "Specify whether to close the AEDT desktop" in result
            mock_context.request_context.lifespan_context.desktop.release_desktop.assert_not_called()

    @pytest.mark.asyncio
    async def test_disconnect_success_keep_desktop_open(self, mock_context):
        """Test successful disconnect without closing the AEDT desktop."""
        from ansys.aedt.mcp.tools import disconnect_from_aedt

        desktop = mock_context.request_context.lifespan_context.desktop

        with patch("ansys.aedt.mcp.tools.session") as mock_session:
            mock_session.locked_connection = False
            result = await disconnect_from_aedt(mock_context, close_desktop=False)

        assert "keeping the desktop session open" in result
        desktop.release_desktop.assert_called_once_with(close_projects=False, close_on_exit=False)
        assert mock_context.request_context.lifespan_context.desktop is None
        assert mock_context.request_context.lifespan_context.aedt_port is None

    @pytest.mark.asyncio
    async def test_disconnect_success_close_desktop(self, mock_context):
        """Test successful disconnect while closing the AEDT desktop."""
        from ansys.aedt.mcp.tools import disconnect_from_aedt

        desktop = mock_context.request_context.lifespan_context.desktop

        with patch("ansys.aedt.mcp.tools.session") as mock_session:
            mock_session.locked_connection = False
            result = await disconnect_from_aedt(
                mock_context, close_projects=True, close_desktop=True
            )

        assert "closed the desktop session" in result
        desktop.release_desktop.assert_called_once_with(close_projects=True, close_on_exit=True)


@pytest.mark.unit
class TestListProjects:
    """Tests for list_projects tool."""

    def test_no_connection(self, mock_context_no_desktop):
        """Test list projects with no connection."""
        from ansys.aedt.mcp.tools import list_projects

        result = list_projects(mock_context_no_desktop)
        assert "No AEDT connection" in result

    def test_list_projects_success(self, mock_context):
        """Test successful project listing."""
        from ansys.aedt.mcp.tools import list_projects

        result = list_projects(mock_context)
        data = json.loads(result)
        assert data["count"] == 2
        assert "Project1" in data["open_projects"]


@pytest.mark.unit
class TestListDesigns:
    """Tests for list_designs tool."""

    def test_no_connection(self, mock_context_no_desktop):
        """Test list designs with no connection."""
        from ansys.aedt.mcp.tools import list_designs

        result = list_designs(mock_context_no_desktop)
        assert "No AEDT connection" in result

    def test_list_designs_success(self, mock_context):
        """Test successful design listing."""
        from ansys.aedt.mcp.tools import list_designs

        result = list_designs(mock_context, project_name="Project1")
        data = json.loads(result)
        assert data["count"] == 2
        assert "Design1" in data["designs"]


@pytest.mark.unit
class TestRunPythonCode:
    """Tests for run_python_code tool."""

    def test_no_connection(self, mock_context_no_desktop):
        """Test run code with no connection."""
        from ansys.aedt.mcp.tools import run_python_code

        result = run_python_code(mock_context_no_desktop, code="print('hello')")
        assert "No AEDT connection" in result

    def test_run_code_success(self, mock_context):
        """Test successful code execution."""
        from ansys.aedt.mcp.tools import run_python_code

        # Mock the python_session.run method
        mock_context.request_context.lifespan_context.python_session = MagicMock()
        mock_context.request_context.lifespan_context.python_session.run.return_value = (
            "test output"
        )

        result = run_python_code(mock_context, code="result = 'test output'")
        assert "test output" in result

    def test_run_code_disables_release_on_exception(self, mock_context):
        """Test run_python_code applies safe runtime settings before exec."""
        from ansys.aedt.mcp.tools import run_python_code

        with patch("ansys.aedt.mcp.tools._configure_pyaedt_runtime_settings") as mock_cfg:
            result = run_python_code(mock_context, code="result = 'ok'")

        mock_cfg.assert_called_once_with()
        assert "ok" in result


@pytest.mark.unit
class TestGetPyAEDTLogs:
    """Tests for get_pyaedt_logs tool."""

    def test_invalid_tail_lines(self, mock_context_no_desktop):
        """Test validation for tail_lines."""
        from ansys.aedt.mcp.tools import get_pyaedt_logs

        result = get_pyaedt_logs(mock_context_no_desktop, tail_lines=0)
        assert "tail_lines must be greater than 0" in result

    def test_log_file_not_resolved(self, mock_context_no_desktop):
        """Test response when no PyAEDT log file can be found."""
        from ansys.aedt.mcp.tools import get_pyaedt_logs

        with patch("ansys.aedt.mcp.tools._resolve_pyaedt_log_file", return_value=None):
            result = get_pyaedt_logs(mock_context_no_desktop)
        assert "could not be resolved" in result

    def test_get_logs_tail_and_filter(self, mock_context_no_desktop, tmp_path):
        """Test successful log retrieval with tail and text filter."""
        from ansys.aedt.mcp.tools import get_pyaedt_logs

        log_file = tmp_path / "pyaedt_test.log"
        log_file.write_text(
            "INFO startup\nERROR solver failed\nINFO retry\nERROR solver recovered\n",
            encoding="utf-8",
        )

        with patch(
            "ansys.aedt.mcp.tools._resolve_pyaedt_log_file",
            return_value=str(log_file),
        ):
            result = get_pyaedt_logs(mock_context_no_desktop, tail_lines=1, contains="error")

        data = json.loads(result)
        assert data["log_file"] == str(log_file.resolve())
        assert data["matched_lines"] == 2
        assert data["returned_lines"] == 1
        assert "ERROR solver recovered" in data["logs"]


@pytest.mark.unit
class TestOpenProject:
    """Tests for open_project tool."""

    def test_no_connection(self, mock_context_no_desktop):
        """Test open project with no connection."""
        from ansys.aedt.mcp.tools import open_project

        result = open_project(mock_context_no_desktop, project_path="test.aedt")
        assert "No AEDT connection" in result

    def test_file_not_found(self, mock_context):
        """Test open project with non-existent file."""
        from ansys.aedt.mcp.tools import open_project

        with patch("ansys.aedt.mcp.tools.Path.exists", return_value=False):
            result = open_project(mock_context, project_path="nonexistent.aedt")
            assert "not found" in result

    def test_open_project_success(self, mock_context):
        """Test successful project open."""
        from ansys.aedt.mcp.tools import open_project

        with patch("ansys.aedt.mcp.tools.Path.exists", return_value=True):
            result = open_project(mock_context, project_path="test.aedt")
            assert "Successfully opened" in result


@pytest.mark.unit
class TestSaveProject:
    """Tests for save_project tool."""

    def test_no_connection(self, mock_context_no_desktop):
        """Test save project with no connection."""
        from ansys.aedt.mcp.tools import save_project

        result = save_project(mock_context_no_desktop)
        assert "No AEDT connection" in result

    def test_save_project_success(self, mock_context):
        """Test successful project save."""
        from ansys.aedt.mcp.tools import save_project

        # Mock that there are projects open
        mock_context.request_context.lifespan_context.desktop.project_list = ["TestProject"]
        result = save_project(mock_context)
        assert "saved successfully" in result or "No project" in result

    def test_save_project_save_as(self, mock_context):
        """Test save-as branch for explicit output path."""
        from ansys.aedt.mcp.tools import save_project

        result = save_project(mock_context, save_as="C:/tmp/new_project.aedt")

        mock_context.request_context.lifespan_context.desktop.save_project.assert_called_with(
            project_path="C:/tmp/new_project.aedt"
        )
        assert "Project saved to" in result

    def test_save_project_exception(self, mock_context):
        """Test save project exception handling."""
        from ansys.aedt.mcp.tools import save_project

        mock_context.request_context.lifespan_context.desktop.save_project.side_effect = (
            RuntimeError("save failed")
        )

        result = save_project(mock_context)

        assert "Error saving project" in result
        assert "save failed" in result


@pytest.mark.unit
class TestClearAEDT:
    """Tests for clear_aedt tool."""

    def test_no_connection(self, mock_context_no_desktop):
        """Test clear AEDT with no connection."""
        from ansys.aedt.mcp.tools import clear_aedt

        result = clear_aedt(mock_context_no_desktop)
        assert "No AEDT connection" in result

    def test_clear_success(self, mock_context):
        """Test successful clear operation."""
        from ansys.aedt.mcp.tools import clear_aedt

        result = clear_aedt(mock_context)
        assert "cleared" in result or "AEDT" in result

    def test_clear_error(self, mock_context):
        """Test clear operation exception handling."""
        from ansys.aedt.mcp.tools import clear_aedt

        mock_context.request_context.lifespan_context.desktop.clear_messages.side_effect = (
            RuntimeError("clear failed")
        )

        result = clear_aedt(mock_context)

        assert "Error clearing AEDT" in result
        assert "clear failed" in result


@pytest.mark.unit
class TestCreateDesign:
    """Tests for create_design tool."""

    def test_no_connection(self, mock_context_no_desktop):
        """Test create design with no connection."""
        from ansys.aedt.mcp.tools import create_design

        result = create_design(mock_context_no_desktop, "Hfss", "TestDesign")
        assert "No AEDT connection" in result

    def test_create_design_success(self, mock_context):
        """Test successful design creation."""
        from ansys.aedt.mcp.tools import create_design

        with patch("ansys.aedt.core.Hfss") as mock_hfss:
            mock_instance = MagicMock()
            mock_instance.design_name = "TestDesign"
            mock_instance.project_name = "TestProject"
            mock_instance.solution_type = "DrivenModal"
            mock_hfss.return_value = mock_instance

            result = create_design(mock_context, "Hfss", "TestDesign")

            assert "Successfully created" in result or "Hfss" in result

    def test_create_design_invalid_app_type(self, mock_context):
        """Test create design with invalid app type."""
        from ansys.aedt.mcp.tools import create_design

        result = create_design(mock_context, "InvalidApp", "TestDesign")  # type: ignore
        assert "Unsupported" in result or "Error" in result

    def test_create_design_with_optional_kwargs(self, mock_context):
        """Test create_design forwards optional project and solution arguments."""
        from ansys.aedt.mcp.tools import create_design

        with patch("ansys.aedt.core.Hfss") as mock_hfss:
            mock_instance = MagicMock()
            mock_instance.design_name = "OptDesign"
            mock_instance.project_name = "OptProject"
            mock_instance.solution_type = "DrivenModal"
            mock_hfss.return_value = mock_instance

            result = create_design(
                mock_context,
                "Hfss",
                design_name="OptDesign",
                project_name="OptProject",
                solution_type="DrivenModal",
            )

        mock_hfss.assert_called_once_with(
            design="OptDesign",
            project="OptProject",
            solution_type="DrivenModal",
        )
        assert "Successfully created Hfss design" in result

    def test_create_design_exception(self, mock_context):
        """Test create_design exception handling."""
        from ansys.aedt.mcp.tools import create_design

        with patch("ansys.aedt.core.Hfss", side_effect=RuntimeError("create failed")):
            result = create_design(mock_context, "Hfss", "BrokenDesign")

        assert "Error creating design" in result
        assert "create failed" in result


@pytest.mark.unit
class TestScreenshot:
    """Tests for screenshot tool."""

    def test_screenshot_no_connection(self, mock_context_no_desktop):
        """Test screenshot with no connection."""
        from ansys.aedt.mcp.tools import screenshot

        result = screenshot(mock_context_no_desktop)

        assert len(result) >= 1
        assert "No AEDT connection" in result[0].text

    def test_screenshot_success(self, mock_context, tmp_path):
        """Test successful screenshot capture."""
        from ansys.aedt.mcp.tools import screenshot

        test_image = tmp_path / "screenshot.jpg"

        mock_project = MagicMock()
        mock_project.GetName.return_value = "Project1"
        mock_context.request_context.lifespan_context.desktop.active_project.return_value = (
            mock_project
        )
        mock_design_obj = MagicMock()
        mock_design_obj.GetName.return_value = "Design1"
        mock_context.request_context.lifespan_context.desktop.active_design.return_value = (
            mock_design_obj
        )
        mock_context.request_context.lifespan_context.desktop.design_type.return_value = "HFSS"

        mock_app = MagicMock()
        mock_app.design_name = "Design1"
        mock_app.project_name = "Project1"

        def _export_image(full_name, width, height):
            Path(full_name).write_bytes(b"\xff\xd8\xff" + b"\x00" * 100)

        mock_app.post.export_model_picture.side_effect = _export_image

        with (
            patch("ansys.aedt.core.get_pyaedt_app", return_value=mock_app),
            patch(
                "ansys.aedt.mcp.tools._open_file_in_default_viewer", return_value=None
            ) as mock_open_viewer,
        ):
            result = screenshot(mock_context, path=str(test_image))

        assert len(result) == 2
        assert "Screenshot saved to" in result[0].text
        assert "Design: Design1" in result[0].text
        assert "Project: Project1" in result[0].text
        assert "Opened screenshot in the default image viewer." in result[0].text
        assert test_image.exists()
        assert result[1].mimeType == "image/jpeg"
        mock_app.post.export_model_picture.assert_called_once_with(
            full_name=str(test_image.resolve()),
            width=1920,
            height=1080,
        )
        mock_open_viewer.assert_called_once_with(test_image.resolve())

    def test_screenshot_uses_4k_resolution(self, mock_context, tmp_path):
        """Test screenshot exports at 4k resolution when requested."""
        from ansys.aedt.mcp.tools import screenshot

        test_image = tmp_path / "screenshot.jpg"
        mock_app = MagicMock()
        mock_app.design_name = "Design1"
        mock_app.project_name = "Project1"
        mock_app.post.export_model_picture.side_effect = lambda full_name, width, height: Path(
            full_name
        ).write_bytes(b"\xff\xd8\xff" + b"\x00" * 100)

        with patch("ansys.aedt.core.get_pyaedt_app", return_value=mock_app):
            result = screenshot(
                mock_context,
                path=str(test_image),
                resolution="4k",
                open_viewer=False,
            )

        assert len(result) == 2
        assert test_image.exists()
        assert result[1].mimeType == "image/jpeg"
        mock_app.post.export_model_picture.assert_called_once_with(
            full_name=str(test_image.resolve()),
            width=3840,
            height=2160,
        )

    def test_screenshot_viewer_failure_does_not_fail_capture(self, mock_context, tmp_path):
        """Test screenshot still succeeds when viewer launch fails."""
        from ansys.aedt.mcp.tools import screenshot

        test_image = tmp_path / "screenshot.jpg"

        mock_context.request_context.lifespan_context.desktop.active_project.return_value = None
        mock_context.request_context.lifespan_context.desktop.active_design.return_value = None
        mock_context.request_context.lifespan_context.desktop.design_type.return_value = "HFSS"

        mock_app = MagicMock()
        mock_app.design_name = "Design1"
        mock_app.project_name = "Project1"
        mock_app.post.export_model_picture.side_effect = lambda full_name, width, height: Path(
            full_name
        ).write_bytes(b"\xff\xd8\xff" + b"\x00" * 100)

        with (
            patch("ansys.aedt.core.get_pyaedt_app", return_value=mock_app),
            patch(
                "ansys.aedt.mcp.tools._open_file_in_default_viewer",
                return_value="Viewer launch failed: test error",
            ),
        ):
            result = screenshot(mock_context, path=str(test_image))

        assert len(result) == 2
        assert "Screenshot saved to" in result[0].text
        assert "Viewer launch failed: test error" in result[0].text

    def test_screenshot_export_failure(self, mock_context):
        """Test screenshot export error with project save guidance."""
        from ansys.aedt.mcp.tools import screenshot

        mock_context.request_context.lifespan_context.desktop.active_project.return_value = None
        mock_context.request_context.lifespan_context.desktop.active_design.return_value = None
        mock_context.request_context.lifespan_context.desktop.design_type.return_value = "HFSS"

        mock_app = MagicMock()
        mock_app.post.export_model_picture.side_effect = RuntimeError("model picture export failed")

        with patch("ansys.aedt.core.get_pyaedt_app", return_value=mock_app):
            result = screenshot(mock_context)

        assert len(result) == 1
        assert "Failed to export screenshot" in result[0].text
        assert "Try saving the project first" in result[0].text


@pytest.mark.unit
class TestAnalyzeDesign:
    """Tests for analyze_design tool."""

    def test_analyze_design_uses_app_level_api(self, mock_context):
        """Test design-level analysis forwards PyAEDT solve options."""
        from ansys.aedt.mcp.tools import analyze_design

        mock_app = MagicMock()
        mock_app.project_name = "Project1"
        mock_app.design_name = "Design1"
        mock_app.analyze.return_value = True

        with patch("ansys.aedt.core.get_pyaedt_app", return_value=mock_app) as mock_get_app:
            result = analyze_design(
                mock_context,
                setup_name="Setup1",
                project_name="Project1",
                design_name="Design1",
                num_cores=8,
                num_tasks=2,
                num_gpus=1,
                acf_file="C:/temp/config.acf",
                use_auto_settings=False,
                solve_in_batch=True,
                machine="remote-host",
                run_in_thread=True,
                revert_to_initial_mesh=True,
            )

        mock_get_app.assert_called_once_with(
            project_name="Project1",
            design_name="Design1",
            desktop=mock_context.request_context.lifespan_context.desktop,
        )
        mock_app.analyze.assert_called_once_with(
            setup="Setup1",
            cores=8,
            tasks=2,
            gpus=1,
            acf_file="C:/temp/config.acf",
            use_auto_settings=False,
            solve_in_batch=True,
            machine="remote-host",
            run_in_thread=True,
            revert_to_initial_mesh=True,
            blocking=False,
        )
        assert "Analysis started successfully and is running asynchronously" in result
        assert "Check the simulation status in AEDT" in result
        assert "Project: Project1" in result
        assert "Design: Design1" in result
        assert "Setup: Setup1" in result
        assert "Mode: batch" in result

    def test_analyze_design_can_run_desktop_analyze_all(self, mock_context):
        """Test explicit desktop-wide analysis path."""
        from ansys.aedt.mcp.tools import analyze_design

        mock_context.request_context.lifespan_context.desktop.analyze_all.return_value = True

        result = analyze_design(
            mock_context,
            project_name="Project1",
            design_name="Design1",
            analyze_all_designs=True,
        )

        mock_context.request_context.lifespan_context.desktop.analyze_all.assert_called_once_with(
            project="Project1",
            design="Design1",
        )
        assert "Analysis completed successfully" in result
        assert "Mode: desktop analyze_all" in result

    def test_analyze_design_rejects_setup_with_desktop_analyze_all(self, mock_context):
        """Test invalid analyze_all usage with a specific setup."""
        from ansys.aedt.mcp.tools import analyze_design

        result = analyze_design(
            mock_context,
            setup_name="Setup1",
            analyze_all_designs=True,
        )

        mock_context.request_context.lifespan_context.desktop.analyze_all.assert_not_called()
        assert "`setup_name` cannot be used" in result

    def test_analyze_design_analyze_all_failure(self, mock_context):
        """Test desktop analyze_all failure response."""
        from ansys.aedt.mcp.tools import analyze_design

        mock_context.request_context.lifespan_context.desktop.analyze_all.return_value = False

        result = analyze_design(mock_context, analyze_all_designs=True)

        assert "Analysis failed during AEDT-wide 'analyze_all' invocation." in result

    def test_analyze_design_app_failure(self, mock_context):
        """Test design-level analyze false result message."""
        from ansys.aedt.mcp.tools import analyze_design

        mock_app = MagicMock()
        mock_app.project_name = "Project1"
        mock_app.design_name = "Design1"
        mock_app.analyze.return_value = False

        with patch("ansys.aedt.core.get_pyaedt_app", return_value=mock_app):
            result = analyze_design(mock_context, setup_name="Setup1")

        assert "Analysis failed." in result
        assert "Setup: Setup1" in result

    def test_analyze_design_exception(self, mock_context):
        """Test analyze_design exception handling."""
        from ansys.aedt.mcp.tools import analyze_design

        with patch("ansys.aedt.core.get_pyaedt_app", side_effect=RuntimeError("analyze boom")):
            result = analyze_design(mock_context)

        assert "Error during analysis" in result
        assert "analyze boom" in result


@pytest.mark.unit
class TestExportConfig:
    """Tests for export_config tool."""

    def test_export_config_no_connection(self, mock_context_no_desktop):
        """Test config export with no connection."""
        from ansys.aedt.mcp.tools import export_config

        result = export_config(mock_context_no_desktop)

        assert "No AEDT connection" in result

    def test_export_config_inline_success(self, mock_context, tmp_path):
        """Test inline config export using a temporary file."""
        from ansys.aedt.mcp.tools import export_config

        mock_project = MagicMock()
        mock_project.GetName.return_value = "Project1"
        mock_context.request_context.lifespan_context.desktop.active_project.return_value = (
            mock_project
        )
        mock_design_obj = MagicMock()
        mock_design_obj.GetName.return_value = "Design1"
        mock_context.request_context.lifespan_context.desktop.active_design.return_value = (
            mock_design_obj
        )
        mock_context.request_context.lifespan_context.desktop.design_type.return_value = "HFSS"

        config_path = tmp_path / "temp_config.json"
        config_data = {"variables": {"w": "10mm"}}

        mock_app = MagicMock()
        mock_app.design_name = "Design1"
        mock_app.project_name = "Project1"

        def _export_config(**kwargs):
            Path(kwargs["config_file"]).write_text(json.dumps(config_data), encoding="utf-8")
            return kwargs["config_file"]

        mock_app.configurations.export_config.side_effect = _export_config

        with (
            patch("ansys.aedt.core.get_pyaedt_app", return_value=mock_app),
            patch("tempfile.mkstemp", return_value=(0, str(config_path))),
            patch("os.close"),
            patch("ansys.aedt.mcp.tools.Path.unlink"),
        ):
            result = export_config(mock_context)

        data = json.loads(result)
        assert data["design"] == "Design1"
        assert data["project"] == "Project1"
        assert data["config"] == config_data
        assert "config_file" not in data

    def test_export_config_to_output_success(self, mock_context, tmp_path):
        """Test config export to a user-specified output path."""
        from ansys.aedt.mcp.tools import export_config

        mock_context.request_context.lifespan_context.desktop.active_project.return_value = None
        mock_context.request_context.lifespan_context.desktop.active_design.return_value = None
        mock_context.request_context.lifespan_context.desktop.design_type.return_value = "HFSS"

        output_path = tmp_path / "design_config"
        expected_file = tmp_path / "design_config.json"
        config_data = {"setups": ["Setup1"]}

        mock_app = MagicMock()
        mock_app.design_name = "Design1"
        mock_app.project_name = "Project1"

        def _export_config(**kwargs):
            Path(kwargs["config_file"]).write_text(json.dumps(config_data), encoding="utf-8")
            return kwargs["config_file"]

        mock_app.configurations.export_config.side_effect = _export_config

        with patch("ansys.aedt.core.get_pyaedt_app", return_value=mock_app):
            result = export_config(mock_context, output=str(output_path), overwrite=True)

        data = json.loads(result)
        assert data["config"] == config_data
        assert data["config_file"] == str(expected_file)

    def test_export_config_failure(self, mock_context):
        """Test config export failure path."""
        from ansys.aedt.mcp.tools import export_config

        mock_context.request_context.lifespan_context.desktop.active_project.return_value = None
        mock_context.request_context.lifespan_context.desktop.active_design.return_value = None
        mock_context.request_context.lifespan_context.desktop.design_type.return_value = "HFSS"

        mock_app = MagicMock()
        mock_app.configurations.export_config.return_value = None

        with patch("ansys.aedt.core.get_pyaedt_app", return_value=mock_app):
            result = export_config(mock_context)

        assert "Failed to export configuration" in result


@pytest.mark.asyncio
async def test_tools_registered():
    """Test that all tools are registered with the MCP server."""
    from ansys.aedt.mcp.server import app

    # Use the local provider's unfiltered list to avoid visibility-state interference
    tool_list = await app._local_provider._list_tools()

    # Expected tool names
    expected_tools = [
        "check_aedt_status",
        "get_pyaedt_logs",
        "check_aedt_installed",
        "launch_aedt",
        "connect_to_aedt",
        "disconnect_from_aedt",
        "run_python_script",
        "run_python_code",
        "list_designs",
        "open_project",
        "save_project",
        "create_design",
        "analyze_design",
        "export_results",
        "export_config",
        "screenshot",
        "clear_aedt",
        "get_model_info",
    ]

    # Check each expected tool is registered
    tool_names = [t.name for t in tool_list]
    for expected_name in expected_tools:
        assert expected_name in tool_names, f"Tool {expected_name} not found"


@pytest.mark.unit
class TestCheckAEDTInstalled:
    """Tests for check_aedt_installed tool."""

    def test_docker_endpoint_reachable(self, mock_context):
        """Test Docker path when gRPC endpoint is reachable."""
        from ansys.aedt.mcp.tools import check_aedt_installed

        with (
            patch("ansys.aedt.mcp.tools._is_docker", return_value=True),
            patch(
                "ansys.aedt.mcp.tools._probe_grpc_endpoint",
                return_value={
                    "reachable": True,
                    "host": "myhost",
                    "port": 50052,
                    "error": None,
                },
            ),
            patch.dict("os.environ", {"AEDT_MACHINE": "myhost", "AEDT_PORT": "50052"}),
        ):
            result = check_aedt_installed(mock_context)

        assert "Running inside Docker" in result
        assert "myhost:50052" in result
        assert "reachable" in result

    def test_docker_endpoint_not_reachable(self, mock_context):
        """Test Docker path when gRPC endpoint is NOT reachable."""
        from ansys.aedt.mcp.tools import check_aedt_installed

        with (
            patch("ansys.aedt.mcp.tools._is_docker", return_value=True),
            patch(
                "ansys.aedt.mcp.tools._probe_grpc_endpoint",
                return_value={
                    "reachable": False,
                    "host": "myhost",
                    "port": 50052,
                    "error": "connection refused",
                },
            ),
            patch.dict("os.environ", {"AEDT_MACHINE": "myhost", "AEDT_PORT": "50052"}),
        ):
            result = check_aedt_installed(mock_context)

        assert "NOT reachable" in result
        assert "ansysedt.exe" in result

    def test_native_installed_versions(self, mock_context):
        """Test native path with installed AEDT versions found."""
        from ansys.aedt.mcp.tools import check_aedt_installed

        mock_versions = MagicMock()
        mock_versions.installed_versions = {
            "2026.1": "C:/ANSYS/v261/AnsysEM",
            "2025.2": "C:/ANSYS/v252/AnsysEM",
        }
        mock_versions.current_version = "2026.1"
        mock_versions.latest_version = "2026.1"

        with (
            patch("ansys.aedt.mcp.tools._is_docker", return_value=False),
            patch("ansys.aedt.mcp.tools.aedt_versions", mock_versions),
        ):
            result = check_aedt_installed(mock_context)

        assert "AEDT is installed" in result
        assert "2026.1" in result
        assert "2025.2" in result

    def test_native_not_installed(self, mock_context):
        """Test native path when AEDT is not found."""
        from ansys.aedt.mcp.tools import check_aedt_installed

        mock_versions = MagicMock()
        mock_versions.installed_versions = {}
        mock_versions.current_version = ""
        mock_versions.latest_version = ""

        with (
            patch("ansys.aedt.mcp.tools._is_docker", return_value=False),
            patch("ansys.aedt.mcp.tools.aedt_versions", mock_versions),
        ):
            result = check_aedt_installed(mock_context)

        assert "no aedt versions found installed" in result.lower()

    def test_native_exception(self, mock_context):
        """Test native path when an exception occurs."""
        from ansys.aedt.mcp.tools import check_aedt_installed

        mock_versions = MagicMock()
        type(mock_versions).installed_versions = property(
            lambda _self: (_ for _ in ()).throw(ImportError("no module"))
        )

        with (
            patch("ansys.aedt.mcp.tools._is_docker", return_value=False),
            patch("ansys.aedt.mcp.tools.aedt_versions", mock_versions),
        ):
            result = check_aedt_installed(mock_context)

        assert "Error" in result


@pytest.mark.unit
class TestRunPythonScript:
    """Tests for run_python_script tool."""

    def test_no_connection(self, mock_context_no_desktop):
        """Test run script with no connection."""
        from ansys.aedt.mcp.tools import run_python_script

        result = run_python_script(mock_context_no_desktop, script_path="test.py")
        assert "No AEDT connection" in result

    def test_script_not_found(self, mock_context):
        """Test run script with non-existent file."""
        from ansys.aedt.mcp.tools import run_python_script

        with patch("ansys.aedt.mcp.tools.Path.exists", return_value=False):
            result = run_python_script(mock_context, script_path="/missing/script.py")

        assert "Script file not found" in result

    def test_script_success(self, mock_context):
        """Test successful script execution."""
        from ansys.aedt.mcp.tools import run_python_script

        mock_context.request_context.lifespan_context.desktop.odesktop.RunScript.return_value = "OK"

        with patch("ansys.aedt.mcp.tools.Path.exists", return_value=True):
            result = run_python_script(mock_context, script_path="test.py")

        assert "Script executed successfully" in result
        assert "OK" in result

    def test_script_exception(self, mock_context):
        """Test script execution failure."""
        from ansys.aedt.mcp.tools import run_python_script

        mock_context.request_context.lifespan_context.desktop.odesktop.RunScript.side_effect = (
            RuntimeError("Script crashed")
        )

        with patch("ansys.aedt.mcp.tools.Path.exists", return_value=True):
            result = run_python_script(mock_context, script_path="test.py")

        assert "Error executing script" in result
        assert "Script crashed" in result


@pytest.mark.unit
class TestExportResults:
    """Tests for export_results tool."""

    def test_no_connection(self, mock_context_no_desktop):
        """Test export results with no connection."""
        from ansys.aedt.mcp.tools import export_results

        result = export_results(mock_context_no_desktop, output_path="/tmp/out.snp")
        assert "No AEDT connection" in result

    def test_export_returns_placeholder(self, mock_context):
        """Test export results returns placeholder message when no app instance."""
        from ansys.aedt.mcp.tools import export_results

        result = export_results(mock_context, output_path="/tmp/out.snp")
        assert "Export functionality requires an active application" in result

    def test_export_custom_type(self, mock_context):
        """Test export with a specific export type."""
        from ansys.aedt.mcp.tools import export_results

        result = export_results(mock_context, output_path="/tmp/out.csv", export_type="convergence")
        assert isinstance(result, str)


@pytest.mark.unit
class TestExportResultsExtended:
    """Additional branch tests for export_results tool."""

    @pytest.mark.parametrize(
        ("export_type", "method_name", "success_text"),
        [
            ("touchstone", "export_touchstone", "Touchstone exported"),
            ("profile", "export_profile", "Profile exported"),
            ("convergence", "export_convergence", "Convergence data exported"),
            ("mesh", "export_mesh_stats", "Mesh stats exported"),
        ],
    )
    def test_export_result_type_success(
        self,
        mock_context,
        export_type,
        method_name,
        success_text,
    ):
        """Test successful export branches for all supported export types."""
        from ansys.aedt.mcp.tools import export_results

        mock_app = MagicMock()
        getattr(mock_app, method_name).return_value = "OK"

        with patch("ansys.aedt.core.get_pyaedt_app", return_value=mock_app):
            result = export_results(
                mock_context,
                output_path="/tmp/out.file",
                export_type=export_type,
                setup_name="Setup1",
            )

        getattr(mock_app, method_name).assert_called_once_with(
            output_file="/tmp/out.file", setup="Setup1"
        )

        assert success_text in result

    @pytest.mark.parametrize(
        ("export_type", "missing_method"),
        [
            ("touchstone", "export_touchstone"),
            ("profile", "export_profile"),
            ("convergence", "export_convergence"),
            ("mesh", "export_mesh_stats"),
        ],
    )
    def test_export_result_type_unavailable(self, mock_context, export_type, missing_method):
        """Test unsupported export methods on resolved app objects."""
        from ansys.aedt.mcp.tools import export_results

        app_without_method = SimpleNamespace()
        # Ensure only the targeted method is absent.
        for method in [
            "export_touchstone",
            "export_profile",
            "export_convergence",
            "export_mesh_stats",
        ]:
            if method != missing_method:
                setattr(app_without_method, method, MagicMock(return_value="OK"))

        with patch("ansys.aedt.core.get_pyaedt_app", return_value=app_without_method):
            result = export_results(
                mock_context, output_path="/tmp/out.file", export_type=export_type
            )

        assert "not available" in result

    def test_export_unknown_type(self, mock_context):
        """Test unknown export type validation message."""
        from ansys.aedt.mcp.tools import export_results

        with patch("ansys.aedt.core.get_pyaedt_app", return_value=MagicMock()):
            result = export_results(
                mock_context, output_path="/tmp/out.file", export_type="unknown"
            )

        assert "Unknown export type" in result
        assert "Supported: touchstone, profile, convergence, mesh" in result

    def test_export_get_pyaedt_app_exception(self, mock_context):
        """Test app resolution failure path in export_results."""
        from ansys.aedt.mcp.tools import export_results

        with patch("ansys.aedt.core.get_pyaedt_app", side_effect=RuntimeError("no design")):
            result = export_results(mock_context, output_path="/tmp/out.file")

        assert "requires an active application" in result

    def test_export_method_raises_exception(self, mock_context):
        """Test outer exception handling when export method raises."""
        from ansys.aedt.mcp.tools import export_results

        mock_app = MagicMock()
        mock_app.export_touchstone.side_effect = RuntimeError("export boom")

        with patch("ansys.aedt.core.get_pyaedt_app", return_value=mock_app):
            result = export_results(
                mock_context, output_path="/tmp/out.file", export_type="touchstone"
            )

        assert "Error exporting results" in result
        assert "export boom" in result


@pytest.mark.unit
class TestToolErrorBranches:
    """Additional branch/error tests for top-level tools."""

    def test_check_aedt_status_exception(self, mock_context):
        """Test status check when backend info retrieval fails."""
        from ansys.aedt.mcp.tools import check_aedt_status

        with patch("ansys.aedt.mcp.tools.get_aedt_info", side_effect=RuntimeError("status boom")):
            result = check_aedt_status(mock_context)

        assert "Error checking AEDT status" in result
        assert "status boom" in result

    def test_get_pyaedt_logs_max_chars_validation(self, mock_context_no_desktop):
        """Test validation for max_chars parameter."""
        from ansys.aedt.mcp.tools import get_pyaedt_logs

        result = get_pyaedt_logs(mock_context_no_desktop, max_chars=0)
        assert "max_chars must be greater than 0" in result

    def test_get_pyaedt_logs_truncation(self, mock_context_no_desktop, tmp_path):
        """Test large log payload truncation path."""
        from ansys.aedt.mcp.tools import get_pyaedt_logs

        log_file = tmp_path / "pyaedt_long.log"
        log_file.write_text("line1\nline2\nline3\nline4\n", encoding="utf-8")

        with patch("ansys.aedt.mcp.tools._resolve_pyaedt_log_file", return_value=str(log_file)):
            result = get_pyaedt_logs(
                mock_context_no_desktop,
                tail_lines=100,
                max_chars=8,
            )

        data = json.loads(result)
        assert data["truncated"] is True

    @pytest.mark.asyncio
    async def test_launch_application_without_desktop_handle(self, mock_context_no_desktop):
        """Test application launch failure when desktop handle cannot be resolved."""
        from ansys.aedt.mcp.tools import launch_aedt

        mock_versions = MagicMock()
        mock_versions.current_version = "2026.1"
        mock_versions.latest_version = "2026.1"

        app_instance = MagicMock()
        app_instance.desktop_class = None

        with (
            patch("ansys.aedt.mcp.tools._is_docker", return_value=False),
            patch("ansys.aedt.mcp.tools.aedt_versions", mock_versions),
            patch("ansys.aedt.core.Hfss", return_value=app_instance),
            patch("ansys.aedt.mcp.tools._configure_pyaedt_runtime_settings"),
        ):
            result = await launch_aedt(mock_context_no_desktop, application="Hfss")

        assert "Failed to launch AEDT" in result
        assert "Unable to resolve AEDT handle" in result

    @pytest.mark.asyncio
    async def test_connect_tip_with_project_name(self, mock_context_no_desktop):
        """Test connect tip text when project_name is provided without design_name."""
        from ansys.aedt.mcp.tools import connect_to_aedt

        fake_desktop = MagicMock()
        fake_desktop.aedt_version_id = "2026.1"
        fake_desktop.is_grpc_api = True

        with (
            patch("ansys.aedt.mcp.tools._is_docker", return_value=False),
            patch("ansys.aedt.core.Desktop", return_value=fake_desktop),
            patch("ansys.aedt.mcp.tools._configure_pyaedt_runtime_settings"),
        ):
            result = await connect_to_aedt(mock_context_no_desktop, project_name="P1")

        assert "Tip: provide design_name" in result
        assert "and project_name" not in result

    @pytest.mark.asyncio
    async def test_disconnect_exception_still_clears_desktop(self, mock_context):
        """Test disconnect exception branch clears context desktop."""
        from ansys.aedt.mcp.tools import disconnect_from_aedt

        mock_context.request_context.lifespan_context.desktop.release_desktop.side_effect = (
            RuntimeError("disconnect boom")
        )

        result = await disconnect_from_aedt(mock_context, close_desktop=False)

        assert "Error during AEDT disconnect" in result
        assert mock_context.request_context.lifespan_context.desktop is None
        assert mock_context.request_context.lifespan_context.aedt_port is None


@pytest.mark.unit
class TestGetModelInfo:
    """Tests for get_model_info tool."""

    def test_no_connection(self, mock_context_no_desktop):
        """Test get model info with no connection."""
        from ansys.aedt.mcp.tools import get_model_info

        result = get_model_info(mock_context_no_desktop)
        assert "No AEDT connection" in result

    def test_get_model_info_success(self, mock_context):
        """Test successful model info retrieval."""
        from ansys.aedt.mcp.tools import get_model_info

        mock_context.request_context.lifespan_context.desktop.design_type.return_value = "HFSS"
        mock_context.request_context.lifespan_context.desktop.project_path.return_value = (
            "C:\\Projects\\test.aedt"
        )

        result = get_model_info(mock_context, design_name="TestDesign")
        data = json.loads(result)
        assert data["design_name"] == "TestDesign"
        assert data["design_type"] == "HFSS"
        assert data["project_path"] == "C:\\Projects\\test.aedt"

    def test_get_model_info_active_design(self, mock_context):
        """Test model info with no explicit design name uses active design."""
        from ansys.aedt.mcp.tools import get_model_info

        mock_context.request_context.lifespan_context.desktop.design_type.return_value = "Maxwell3d"
        mock_context.request_context.lifespan_context.desktop.project_path.return_value = (
            "C:\\Projects\\maxwell.aedt"
        )

        result = get_model_info(mock_context)
        data = json.loads(result)
        assert data["design_name"] == "Active Design"
        assert data["design_type"] == "Maxwell3d"

    def test_get_model_info_exception(self, mock_context):
        """Test model info when an exception occurs."""
        from ansys.aedt.mcp.tools import get_model_info

        mock_context.request_context.lifespan_context.desktop.design_type.side_effect = (
            RuntimeError("No active design")
        )

        result = get_model_info(mock_context)
        assert "Error getting model info" in result


@pytest.mark.unit
class TestLaunchAEDTExtended:
    """Extended tests for launch_aedt tool."""

    @pytest.mark.asyncio
    async def test_launch_in_docker_returns_error(self, mock_context_no_desktop):
        """Test that launching AEDT inside Docker is blocked."""
        from ansys.aedt.mcp.tools import launch_aedt

        with patch("ansys.aedt.mcp.tools._is_docker", return_value=True):
            result = await launch_aedt(mock_context_no_desktop)

        assert "Docker" in result
        assert "not supported" in result

    @pytest.mark.asyncio
    async def test_launch_with_application(self, mock_context_no_desktop):
        """Test launching AEDT with a specific application type."""
        from ansys.aedt.mcp.tools import launch_aedt

        mock_versions = MagicMock()
        mock_versions.current_version = "2026.1"
        mock_versions.latest_version = "2026.1"

        mock_app_instance = MagicMock()
        mock_app_instance.desktop_class = MagicMock()
        mock_app_instance.desktop_class.aedt_version_id = "2026.1"
        mock_app_instance.desktop_class.aedt_install_dir = "C:\\ANSYS"
        mock_app_instance.desktop_class.is_grpc_api = True

        with (
            patch("ansys.aedt.mcp.tools._is_docker", return_value=False),
            patch("ansys.aedt.mcp.tools.aedt_versions", mock_versions),
            patch("ansys.aedt.core.Hfss", return_value=mock_app_instance),
            patch("ansys.aedt.mcp.tools._configure_pyaedt_runtime_settings"),
        ):
            result = await launch_aedt(mock_context_no_desktop, application="Hfss")

        assert "Successfully launched Hfss" in result

    @pytest.mark.asyncio
    async def test_launch_unsupported_application(self, mock_context_no_desktop):
        """Test launching AEDT with an unsupported application type."""
        from ansys.aedt.mcp.tools import launch_aedt

        with (
            patch("ansys.aedt.mcp.tools._is_docker", return_value=False),
            patch("ansys.aedt.mcp.tools._configure_pyaedt_runtime_settings"),
        ):
            result = await launch_aedt(mock_context_no_desktop, application="InvalidApp")  # type: ignore

        assert "Unsupported application type" in result


@pytest.mark.unit
class TestConnectToAEDTExtended:
    """Extended tests for connect_to_aedt tool."""

    @pytest.mark.asyncio
    async def test_connect_docker_overrides_defaults(self, mock_context_no_desktop):
        """Test that Docker overrides default machine/port from env vars."""
        from ansys.aedt.mcp.tools import connect_to_aedt

        fake_desktop = MagicMock()
        fake_desktop.aedt_version_id = "2026.1"
        fake_desktop.is_grpc_api = True

        with (
            patch("ansys.aedt.mcp.tools._is_docker", return_value=True),
            patch.dict("os.environ", {"AEDT_MACHINE": "docker-host", "AEDT_PORT": "50099"}),
            patch("ansys.aedt.core.Desktop", return_value=fake_desktop) as mock_desktop,
            patch("ansys.aedt.mcp.tools._configure_pyaedt_runtime_settings"),
        ):
            result = await connect_to_aedt(mock_context_no_desktop)

        call_kwargs = mock_desktop.call_args[1]
        assert call_kwargs["machine"] == "docker-host"
        assert call_kwargs["port"] == 50099
        assert "Successfully connected" in result

    @pytest.mark.asyncio
    async def test_connect_with_design_name(self, mock_context_no_desktop):
        """Test connecting directly to a design."""
        from ansys.aedt.mcp.tools import connect_to_aedt

        fake_desktop = MagicMock()
        fake_desktop.aedt_version_id = "2026.1"
        fake_desktop.is_grpc_api = True

        fake_app = MagicMock()
        fake_app.project_name = "Project1"
        fake_app.design_name = "Design1"
        fake_app.design_type = "HFSS"

        with (
            patch("ansys.aedt.mcp.tools._is_docker", return_value=False),
            patch("ansys.aedt.mcp.tools.discover_available_aedt_sessions", return_value=[]),
            patch("ansys.aedt.core.Desktop", return_value=fake_desktop),
            patch("ansys.aedt.core.get_pyaedt_app", return_value=fake_app),
            patch("ansys.aedt.mcp.tools._configure_pyaedt_runtime_settings"),
        ):
            result = await connect_to_aedt(
                mock_context_no_desktop,
                design_name="Design1",
                project_name="Project1",
            )

        assert "Successfully connected" in result
        assert "Design: Design1" in result
        assert "Project: Project1" in result

    @pytest.mark.asyncio
    async def test_connect_reports_empty_session_guidance(self, mock_context_no_desktop):
        """Test connecting to a session with no open projects suggests create_design."""
        from ansys.aedt.mcp.tools import connect_to_aedt

        fake_desktop = MagicMock()
        fake_desktop.aedt_version_id = "2026.1"
        fake_desktop.is_grpc_api = True
        fake_desktop.project_list = []

        with (
            patch("ansys.aedt.mcp.tools._is_docker", return_value=False),
            patch("ansys.aedt.mcp.tools.discover_available_aedt_sessions", return_value=[]),
            patch("ansys.aedt.core.Desktop", return_value=fake_desktop),
            patch("ansys.aedt.mcp.tools._configure_pyaedt_runtime_settings"),
        ):
            result = await connect_to_aedt(mock_context_no_desktop, port=50051)

        assert "No open projects are available in this AEDT session" in result
        assert "call create_design" in result
        assert "Hfss" in result


@pytest.mark.unit
class TestRequiresAEDTVisibility:
    """Tests for AEDT-connection-aware tool visibility."""

    @pytest.mark.asyncio
    async def test_connect_enables_requires_aedt_tools(self, mock_context_no_desktop):
        """Successful connect_to_aedt should call ctx.enable_components for the tag."""
        from ansys.aedt.mcp.tools import connect_to_aedt

        with (
            patch("ansys.aedt.mcp.tools._configure_pyaedt_runtime_settings"),
            patch("ansys.aedt.core.Desktop") as mock_desktop_cls,
        ):
            fake_desktop = MagicMock()
            fake_desktop.aedt_version_id = "2026.1"
            fake_desktop.is_grpc_api = True
            mock_desktop_cls.return_value = fake_desktop

            await connect_to_aedt(mock_context_no_desktop)
            mock_context_no_desktop.enable_components.assert_called_once_with(
                tags={"requires_aedt"}
            )

    @pytest.mark.asyncio
    async def test_launch_enables_requires_aedt_tools(self, mock_context_no_desktop):
        """Successful launch_aedt should call ctx.enable_components for the tag."""
        from ansys.aedt.mcp.tools import launch_aedt

        mock_versions = MagicMock()
        mock_versions.current_version = "2026.1"
        mock_versions.latest_version = "2026.1"

        with (
            patch("ansys.aedt.mcp.tools._is_docker", return_value=False),
            patch("ansys.aedt.mcp.tools.aedt_versions", mock_versions),
            patch("ansys.aedt.core.Desktop") as mock_desktop_cls,
            patch("ansys.aedt.mcp.tools._configure_pyaedt_runtime_settings"),
        ):
            fake_desktop = MagicMock()
            fake_desktop.aedt_version_id = "2026.1"
            fake_desktop.aedt_install_dir = "C:/test"
            fake_desktop.is_grpc_api = True
            mock_desktop_cls.return_value = fake_desktop

            await launch_aedt(mock_context_no_desktop)
            mock_context_no_desktop.enable_components.assert_called_once_with(
                tags={"requires_aedt"}
            )

    @pytest.mark.asyncio
    async def test_disconnect_disables_requires_aedt_tools(self, mock_context):
        """Successful disconnect_from_aedt should call ctx.disable_components."""
        from ansys.aedt.mcp.tools import disconnect_from_aedt

        await disconnect_from_aedt(mock_context, close_desktop=False)
        mock_context.disable_components.assert_called_once_with(tags={"requires_aedt"})

    def test_requires_aedt_tag_present_on_correct_tools(self):
        """Tools that need AEDT should have the requires_aedt tag."""
        import asyncio

        from ansys.aedt.mcp.server import app

        async def _check():
            return {t.name: t for t in await app._local_provider._list_tools()}

        tool_registry = asyncio.run(_check())
        expected_tagged = {
            "disconnect_from_aedt",
            "run_python_script",
            "run_python_code",
            "list_designs",
            "open_project",
            "save_project",
            "create_design",
            "analyze_design",
            "export_results",
            "screenshot",
            "export_config",
            "clear_aedt",
            "get_model_info",
        }
        for tool_name in expected_tagged:
            assert tool_name in tool_registry, f"Tool '{tool_name}' not found"
            assert "requires_aedt" in (tool_registry[tool_name].tags or set()), (
                f"Tool '{tool_name}' missing 'requires_aedt' tag"
            )

    def test_no_tool_surface_drift(self):
        """Every tool must be in the always-available allowlist or carry
        the ``requires_aedt`` gating tag.

        This test prevents accidental "tool surface drift" — i.e. someone
        adding a new tool that needs an AEDT connection but forgetting to
        tag it ``requires_aedt``. Without the tag, the tool would be
        exposed to clients before any AEDT session exists and would crash
        at call time.

        If you add a brand-new tool that legitimately must be reachable
        BEFORE any AEDT connection is established (e.g. a pure
        installation / diagnostic helper), add its name to
        ``ALWAYS_AVAILABLE_TOOLS`` below. Otherwise, tag the tool
        ``requires_aedt`` (see ``REQUIRES_AEDT_TAG`` in tools.py).
        """
        import asyncio

        from ansys.aedt.mcp.server import app

        # Tools that are intentionally reachable before any AEDT session.
        # Keep this list minimal — anything that touches a connected
        # Desktop/Project/Design must NOT be here.
        ALWAYS_AVAILABLE_TOOLS = {
            "check_aedt_installed",
            "check_aedt_status",
            "launch_aedt",
            "connect_to_aedt",
            "get_pyaedt_logs",
            "get_guidelines_for",
        }

        async def _list():
            return await app._local_provider._list_tools()

        registered = asyncio.run(_list())
        offenders = []
        for t in registered:
            tags = t.tags or set()
            if t.name in ALWAYS_AVAILABLE_TOOLS:
                continue
            if "requires_aedt" not in tags:
                offenders.append(t.name)

        assert not offenders, (
            "The following tools are missing the 'requires_aedt' tag and "
            "are not in the ALWAYS_AVAILABLE_TOOLS allowlist:\n  - "
            + "\n  - ".join(sorted(offenders))
            + "\n\nEither tag the tool with REQUIRES_AEDT_TAG (the common "
            "case) or — if the tool genuinely does not need an AEDT "
            "session — add it to ALWAYS_AVAILABLE_TOOLS in this test."
        )
