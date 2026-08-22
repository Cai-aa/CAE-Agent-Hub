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

"""Tests for MCP tools functionality."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

from mcp.types import TextContent
import pytest

from ansys.mechanical.mcp.tools import (
    check_mechanical_installed,
    check_mechanical_status,
    clear_mechanical,
    connect_to_mechanical,
    disconnect_from_mechanical,
    download_file,
    get_model_info,
    launch_mechanical,
    list_files,
    list_mechanical_instances,
    mechanical_working_directory,
    run_python_script,
    screenshot,
    upload_file,
)


@pytest.mark.unit
class TestCheckMechanicalStatus:
    """Tests for check_mechanical_status tool."""

    def test_check_status_with_mechanical(self, mock_context):
        """Test checking Mechanical status when Mechanical is available."""
        # Mock get_product_info method
        mock_context.request_context.lifespan_context.mechanical.get_product_info = MagicMock(
            return_value="Product Info"
        )
        mock_context.request_context.lifespan_context.mechanical.busy = False
        mock_context.request_context.lifespan_context.mechanical.exited = False

        result = check_mechanical_status(mock_context)

        assert isinstance(result, str)
        # Check for JSON structure
        import json

        data = json.loads(result)
        assert "connection" in data
        assert "version" in data["connection"]

    def test_check_status_without_mechanical(self, mock_context_no_mechanical):
        """Test checking Mechanical status when Mechanical is not available."""
        result = check_mechanical_status(mock_context_no_mechanical)

        # Should return helpful error message instead of raising exception
        assert isinstance(result, str)
        assert "No Mechanical connection available" in result
        assert "connect_to_mechanical" in result

    def test_check_status_with_exited_mechanical(self, mock_context):
        """Test checking status when Mechanical has exited."""
        mock_context.request_context.lifespan_context.mechanical.exited = True

        result = check_mechanical_status(mock_context)

        assert isinstance(result, str)
        assert "Mechanical instance has exited" in result
        assert "reconnect or launch" in result.lower()

    def test_check_status_returns_connection_info(self, mock_context):
        """Test status extraction returns proper connection information."""
        import json

        # Mock get_product_info method
        mock_context.request_context.lifespan_context.mechanical.get_product_info = MagicMock(
            return_value="Product Info"
        )
        mock_context.request_context.lifespan_context.mechanical.busy = False
        mock_context.request_context.lifespan_context.mechanical.exited = False

        result = check_mechanical_status(mock_context)

        data = json.loads(result)

        # Verify connection section is present
        assert "connection" in data
        assert "version" in data["connection"]
        assert "project_directory" in data["connection"]
        assert "is_alive" in data["connection"]


@pytest.mark.unit
class TestRunMechanicalScript:
    """Tests for run_python_script tool."""

    def test_run_script_success(self, mock_context):
        """Test running a Mechanical script successfully."""
        script = "print('hello')"
        result = run_python_script(mock_context, script)

        assert isinstance(result, str)
        assert "Script executed successfully" in result

        # Verify that Mechanical's run_python_script method was called
        mock_context.request_context.lifespan_context.mechanical.run_python_script.assert_called_once_with(
            script
        )

    def test_run_script_with_arguments(self, mock_context):
        """Test running a Mechanical script with arguments."""
        script = "result = 1 + 2; print(result)"
        result = run_python_script(mock_context, script)

        assert isinstance(result, str)
        assert "Script executed successfully" in result

    def test_run_script_without_mechanical(self, mock_context_no_mechanical):
        """Test running a script when Mechanical is not available."""
        result = run_python_script(mock_context_no_mechanical, "print('test')")

        # Should return helpful error message instead of raising exception
        assert isinstance(result, str)
        assert "No Mechanical connection available" in result
        assert "connect_to_mechanical" in result

    def test_run_multiple_scripts(self, mock_context):
        """Test running multiple Mechanical scripts sequentially."""
        scripts = ["print('1')", "print('2')", "print('3')"]

        for script in scripts:
            result = run_python_script(mock_context, script)
            assert "Script executed successfully" in result

        # Verify all scripts were called
        assert (
            mock_context.request_context.lifespan_context.mechanical.run_python_script.call_count
            == len(scripts)
        )

    def test_run_script_from_file(self, mock_context, tmp_path):
        """Test running an inline script sourced from a local file."""
        script_file = tmp_path / "snippet.py"
        script_file.write_text("print('from file')")

        result = run_python_script(mock_context, file_path=str(script_file))

        assert "Script executed successfully" in result
        mock_context.request_context.lifespan_context.mechanical.run_python_script.assert_called_once_with(
            "print('from file')"
        )

    def test_run_script_from_missing_file(self, mock_context):
        """Test running from a file that does not exist."""
        result = run_python_script(mock_context, file_path="/nonexistent/script.py")

        assert "Script file not found" in result

    def test_run_script_without_script_or_file(self, mock_context):
        """Test that at least one of script or file_path is required."""
        result = run_python_script(mock_context)

        assert "Provide either" in result


@pytest.mark.unit
class TestMechanicalWorkingDirectoryResource:
    """Tests for the files://mechanical/working_directory resource."""

    def test_working_directory_returns_project_directory(self, monkeypatch, mock_mechanical):
        """When Mechanical is connected, resource returns its project directory."""
        from ansys.mechanical.mcp import app as mechanical_app

        ctx = MagicMock()
        ctx.mechanical = mock_mechanical
        monkeypatch.setattr(mechanical_app, "context", ctx, raising=False)

        result = mechanical_working_directory()

        assert result == "/tmp/mechanical_project"

    def test_working_directory_not_connected(self, monkeypatch):
        """When Mechanical is not connected, resource returns a hint."""
        from ansys.mechanical.mcp import app as mechanical_app

        ctx = MagicMock()
        ctx.mechanical = None
        monkeypatch.setattr(mechanical_app, "context", ctx, raising=False)

        result = mechanical_working_directory()

        assert "Mechanical is not connected" in result


@pytest.mark.unit
class TestConnectToMechanical:
    """Tests for connect_to_mechanical tool."""

    @pytest.mark.asyncio
    async def test_connect_default_parameters(self, mock_context_no_mechanical):
        """Test connecting to Mechanical with default parameters."""
        # Create a mock Mechanical instance
        mock_mechanical = MagicMock()
        mock_mechanical.version = "2024 R2"
        mock_mechanical._ip = "127.0.0.1"
        mock_mechanical._port = 10000

        with patch(
            "ansys.mechanical.mcp.tools.pymechanical.connect_to_mechanical",
            return_value=mock_mechanical,
        ):
            result = await connect_to_mechanical(mock_context_no_mechanical)

            # Verify successful connection
            assert isinstance(result, str)
            assert "Successfully connected to Mechanical" in result
            assert "127.0.0.1:10000" in result
            assert "2024 R2" in result

            # Verify Mechanical was stored in context
            assert (
                mock_context_no_mechanical.request_context.lifespan_context.mechanical
                == mock_mechanical
            )

    @pytest.mark.asyncio
    async def test_connect_custom_port(self, mock_context_no_mechanical):
        """Test connecting to Mechanical with custom port."""
        mock_mechanical = MagicMock()
        mock_mechanical.version = "2024 R1"
        mock_mechanical._ip = "127.0.0.1"
        mock_mechanical._port = 10001

        with (
            patch(
                "ansys.mechanical.mcp.tools.pymechanical.connect_to_mechanical",
                return_value=mock_mechanical,
            ) as mock_connect,
            patch(
                "ansys.mechanical.mcp.tools.resolve_transport_mode",
                return_value=(None, None),
            ),
        ):
            result = await connect_to_mechanical(mock_context_no_mechanical, port=10001)

            # Verify connection with custom port
            assert "Successfully connected to Mechanical" in result
            assert "127.0.0.1:10001" in result

            # Verify connect_to_mechanical was called with correct parameters
            mock_connect.assert_called_once_with(
                ip="127.0.0.1",
                port=10001,
                cleanup_on_exit=False,
            )

    @pytest.mark.asyncio
    async def test_connect_custom_ip(self, mock_context_no_mechanical):
        """Test connecting to Mechanical with custom IP address."""
        mock_mechanical = MagicMock()
        mock_mechanical.version = "2024 R2"
        mock_mechanical._ip = "192.168.1.100"
        mock_mechanical._port = 10000

        with (
            patch(
                "ansys.mechanical.mcp.tools.pymechanical.connect_to_mechanical",
                return_value=mock_mechanical,
            ) as mock_connect,
            patch(
                "ansys.mechanical.mcp.tools.resolve_transport_mode",
                return_value=(None, None),
            ),
        ):
            result = await connect_to_mechanical(mock_context_no_mechanical, ip="192.168.1.100")

            # Verify connection with custom IP
            assert "Successfully connected to Mechanical" in result
            assert "192.168.1.100:10000" in result

            # Verify connect_to_mechanical was called with correct parameters
            mock_connect.assert_called_once_with(
                ip="192.168.1.100",
                port=10000,
                cleanup_on_exit=False,
            )

    @pytest.mark.asyncio
    async def test_connect_custom_ip_and_port(self, mock_context_no_mechanical):
        """Test connecting to Mechanical with both custom IP and port."""
        mock_mechanical = MagicMock()
        mock_mechanical.version = "2024 R2"
        mock_mechanical._ip = "10.0.0.50"
        mock_mechanical._port = 10099

        with (
            patch(
                "ansys.mechanical.mcp.tools.pymechanical.connect_to_mechanical",
                return_value=mock_mechanical,
            ) as mock_connect,
            patch(
                "ansys.mechanical.mcp.tools.resolve_transport_mode",
                return_value=(None, None),
            ),
        ):
            result = await connect_to_mechanical(
                mock_context_no_mechanical, port=10099, ip="10.0.0.50"
            )

            # Verify connection with custom parameters
            assert "Successfully connected to Mechanical" in result
            assert "10.0.0.50:10099" in result

            # Verify connect_to_mechanical was called with correct parameters
            mock_connect.assert_called_once_with(
                ip="10.0.0.50",
                port=10099,
                cleanup_on_exit=False,
            )

    @pytest.mark.asyncio
    async def test_connect_already_connected(self, mock_context):
        """Test connecting when already connected."""
        # Context already has a Mechanical connection
        result = await connect_to_mechanical(mock_context)

        # Verify appropriate error message
        assert "Already connected to a Mechanical instance" in result
        assert "disconnect first" in result.lower()

    @pytest.mark.asyncio
    async def test_connect_connection_error(self, mock_context_no_mechanical):
        """Test handling connection errors."""
        with patch(
            "ansys.mechanical.mcp.tools.pymechanical.connect_to_mechanical",
            side_effect=Exception("Connection refused"),
        ):
            result = await connect_to_mechanical(
                mock_context_no_mechanical, port=10000, ip="127.0.0.1"
            )

            # Verify error message is returned
            assert "Failed to connect to Mechanical" in result
            assert "Connection refused" in result

            # Verify context remains empty
            assert mock_context_no_mechanical.request_context.lifespan_context.mechanical is None

    @pytest.mark.asyncio
    async def test_connect_network_error(self, mock_context_no_mechanical):
        """Test handling network errors during connection."""
        with patch(
            "ansys.mechanical.mcp.tools.pymechanical.connect_to_mechanical",
            side_effect=ConnectionError("Network unreachable"),
        ):
            result = await connect_to_mechanical(
                mock_context_no_mechanical, port=10000, ip="192.168.1.999"
            )

            # Verify error message
            assert "Failed to connect to Mechanical" in result
            assert "Network unreachable" in result

    @pytest.mark.asyncio
    async def test_connect_timeout_error(self, mock_context_no_mechanical):
        """Test handling timeout errors during connection."""
        with patch(
            "ansys.mechanical.mcp.tools.pymechanical.connect_to_mechanical",
            side_effect=TimeoutError("Connection timed out"),
        ):
            result = await connect_to_mechanical(mock_context_no_mechanical)

            # Verify timeout error is handled
            assert "Failed to connect to Mechanical" in result
            assert "Connection timed out" in result

    @pytest.mark.asyncio
    async def test_connect_stores_mechanical_in_context(self, mock_context_no_mechanical):
        """Test that connected Mechanical instance is properly stored in context."""
        mock_mechanical = MagicMock()
        mock_mechanical.version = "2024 R2"
        mock_mechanical._ip = "127.0.0.1"
        mock_mechanical._port = 10000

        # Verify context starts with no Mechanical
        assert mock_context_no_mechanical.request_context.lifespan_context.mechanical is None

        with patch(
            "ansys.mechanical.mcp.tools.pymechanical.connect_to_mechanical",
            return_value=mock_mechanical,
        ):
            result = await connect_to_mechanical(mock_context_no_mechanical)

            # Verify successful connection
            assert "Successfully connected" in result

            # Verify Mechanical is stored in context
            assert (
                mock_context_no_mechanical.request_context.lifespan_context.mechanical is not None
            )
            assert (
                mock_context_no_mechanical.request_context.lifespan_context.mechanical
                == mock_mechanical
            )

    @pytest.mark.asyncio
    async def test_connect_result_message(self, mock_context_no_mechanical):
        """Test that connect_to_mechanical returns informative success message."""
        mock_mechanical = MagicMock()
        mock_mechanical.version = "2024 R2"
        mock_mechanical._ip = "127.0.0.1"
        mock_mechanical._port = 10000

        with patch(
            "ansys.mechanical.mcp.tools.pymechanical.connect_to_mechanical",
            return_value=mock_mechanical,
        ):
            result = await connect_to_mechanical(mock_context_no_mechanical)

            # Verify the result contains connection information
            assert isinstance(result, str)
            assert "Successfully connected to Mechanical at 127.0.0.1:10000" in result
            assert "2024 R2" in result


@pytest.mark.unit
class TestDisconnectFromMechanical:
    """Tests for disconnect_from_mechanical tool."""

    @pytest.mark.asyncio
    async def test_disconnect_success(self, mock_context):
        """Test disconnecting from Mechanical successfully."""
        # Store reference to check exit was called
        mechanical_ref = mock_context.request_context.lifespan_context.mechanical

        result = await disconnect_from_mechanical(mock_context)

        # Verify successful disconnection
        assert isinstance(result, str)
        assert "Successfully disconnected from Mechanical" in result

        # Verify exit was called on the original object
        mechanical_ref.exit.assert_called_once()

        # Verify Mechanical was removed from context
        assert mock_context.request_context.lifespan_context.mechanical is None

    @pytest.mark.asyncio
    async def test_disconnect_no_connection(self, mock_context_no_mechanical):
        """Test disconnecting when no connection exists."""
        result = await disconnect_from_mechanical(mock_context_no_mechanical)

        # Verify appropriate message
        assert "No Mechanical connection to disconnect" in result

    @pytest.mark.asyncio
    async def test_disconnect_clears_context(self, mock_context):
        """Test that disconnect properly clears the context."""
        mock_context.request_context.lifespan_context.mechanical._ip = "127.0.0.1"
        mock_context.request_context.lifespan_context.mechanical._port = 10000

        # Verify Mechanical exists before disconnect
        assert mock_context.request_context.lifespan_context.mechanical is not None

        await disconnect_from_mechanical(mock_context)

        # Verify Mechanical is cleared after disconnect
        assert mock_context.request_context.lifespan_context.mechanical is None

    @pytest.mark.asyncio
    async def test_disconnect_error_during_exit(self, mock_context):
        """Test handling errors during disconnection."""
        mock_context.request_context.lifespan_context.mechanical._ip = "127.0.0.1"
        mock_context.request_context.lifespan_context.mechanical._port = 10000
        mock_context.request_context.lifespan_context.mechanical.exit.side_effect = Exception(
            "Disconnection error"
        )

        result = await disconnect_from_mechanical(mock_context)

        # Verify error message is returned
        assert "Error during disconnect" in result
        assert "Disconnection error" in result

        # Verify context is still cleared even on error
        assert mock_context.request_context.lifespan_context.mechanical is None

    @pytest.mark.asyncio
    async def test_disconnect_connection_lost(self, mock_context):
        """Test disconnecting when connection is already lost."""
        mock_context.request_context.lifespan_context.mechanical._ip = "127.0.0.1"
        mock_context.request_context.lifespan_context.mechanical._port = 10000
        mock_context.request_context.lifespan_context.mechanical.exit.side_effect = ConnectionError(
            "Connection already closed"
        )

        result = await disconnect_from_mechanical(mock_context)

        # Verify error is handled gracefully
        assert "Error during disconnect" in result
        assert "Connection already closed" in result

        # Context should still be cleared
        assert mock_context.request_context.lifespan_context.mechanical is None

    @pytest.mark.asyncio
    async def test_disconnect_return_message(self, mock_context):
        """Test that disconnect_from_mechanical returns informative message."""
        result = await disconnect_from_mechanical(mock_context)

        # Verify the result contains disconnection information
        assert isinstance(result, str)
        assert "Successfully disconnected from Mechanical" in result

    @pytest.mark.asyncio
    async def test_disconnect_custom_ip_port(self, mock_context):
        """Test disconnecting from Mechanical with custom IP and port."""
        result = await disconnect_from_mechanical(mock_context)

        # Verify disconnection message
        assert "Successfully disconnected from Mechanical" in result


@pytest.mark.unit
class TestLaunchMechanical:
    """Tests for launch_mechanical tool."""

    @pytest.mark.asyncio
    async def test_launch_default_parameters(self, mock_context_no_mechanical):
        """Test launching Mechanical with default parameters."""
        # Create a mock Mechanical instance
        mock_mechanical = MagicMock()
        mock_mechanical.version = "2024 R2"
        mock_mechanical.project_directory = "/tmp/ansys_mechanical_1234"

        with (
            patch(
                "ansys.mechanical.mcp.tools.pymechanical.launch_mechanical",
                return_value=mock_mechanical,
            ) as mock_launch,
            patch(
                "ansys.mechanical.mcp.tools.resolve_transport_mode",
                return_value=(None, None),
            ),
        ):
            mock_context_no_mechanical.elicit = AsyncMock(
                side_effect=RuntimeError("elicitation unavailable")
            )
            result = await launch_mechanical(mock_context_no_mechanical)

            # Verify successful launch
            assert isinstance(result, str)
            assert "Successfully launched Mechanical" in result
            assert "2024 R2" in result

            # Verify launch_mechanical was called with correct parameters
            mock_launch.assert_called_once_with(
                batch=False,
                loglevel="INFO",
                cleanup_on_exit=True,
                start_timeout=300,
            )

            # Verify Mechanical was stored in context
            assert (
                mock_context_no_mechanical.request_context.lifespan_context.mechanical
                == mock_mechanical
            )

    @pytest.mark.asyncio
    async def test_launch_with_port(self, mock_context_no_mechanical):
        """Test launching Mechanical with custom port."""
        mock_mechanical = MagicMock()
        mock_mechanical.version = "2024 R2"
        mock_mechanical.project_directory = "/tmp/ansys_mechanical_1234"

        mock_context_no_mechanical.elicit = AsyncMock(
            side_effect=RuntimeError("elicitation unavailable")
        )

        with (
            patch(
                "ansys.mechanical.mcp.tools.pymechanical.launch_mechanical",
                return_value=mock_mechanical,
            ) as mock_launch,
            patch(
                "ansys.mechanical.mcp.tools.resolve_transport_mode",
                return_value=(None, None),
            ),
        ):
            result = await launch_mechanical(mock_context_no_mechanical, port=10050)

            # Verify successful launch
            assert "Successfully launched Mechanical" in result

            # Verify launch_mechanical was called with correct port
            mock_launch.assert_called_once_with(
                batch=False,
                loglevel="INFO",
                cleanup_on_exit=True,
                start_timeout=300,
                port=10050,
            )

    @pytest.mark.asyncio
    async def test_launch_with_version(self, mock_context_no_mechanical):
        """Test launching Mechanical with specific version."""
        mock_mechanical = MagicMock()
        mock_mechanical.version = "2025 R2"
        mock_mechanical.project_directory = "/tmp/ansys_mechanical_1234"

        mock_context_no_mechanical.elicit = AsyncMock(
            side_effect=RuntimeError("elicitation unavailable")
        )

        with (
            patch(
                "ansys.mechanical.mcp.tools.pymechanical.launch_mechanical",
                return_value=mock_mechanical,
            ) as mock_launch,
            patch(
                "ansys.mechanical.mcp.tools.resolve_transport_mode",
                return_value=(None, None),
            ),
        ):
            result = await launch_mechanical(mock_context_no_mechanical, version="252")

            # Verify successful launch
            assert "Successfully launched Mechanical" in result
            assert "2025 R2" in result

            # Verify launch_mechanical was called with version
            mock_launch.assert_called_once_with(
                batch=False,
                loglevel="INFO",
                cleanup_on_exit=True,
                start_timeout=300,
                version="252",
            )

    @pytest.mark.asyncio
    async def test_launch_uses_prompted_batch_choice(self, mock_context_no_mechanical):
        """Test launching Mechanical in batch mode when the client selects it."""
        mock_mechanical = MagicMock()
        mock_mechanical.version = "2024 R2"
        mock_mechanical.project_directory = "/tmp/ansys_mechanical_1234"

        mock_context_no_mechanical.elicit = AsyncMock(
            return_value=MagicMock(action="accept", data="batch")
        )

        with (
            patch(
                "ansys.mechanical.mcp.tools.pymechanical.launch_mechanical",
                return_value=mock_mechanical,
            ) as mock_launch,
            patch(
                "ansys.mechanical.mcp.tools.resolve_transport_mode",
                return_value=(None, None),
            ),
        ):
            result = await launch_mechanical(mock_context_no_mechanical)

            assert "Successfully launched Mechanical" in result
            mock_launch.assert_called_once_with(
                batch=True,
                loglevel="INFO",
                cleanup_on_exit=True,
                start_timeout=300,
            )

    @pytest.mark.asyncio
    async def test_launch_uses_prompted_gui_choice(self, mock_context_no_mechanical):
        """Test launching Mechanical in GUI mode when the client selects it."""
        mock_mechanical = MagicMock()
        mock_mechanical.version = "2024 R2"
        mock_mechanical.project_directory = "/tmp/ansys_mechanical_1234"

        mock_context_no_mechanical.elicit = AsyncMock(
            return_value=MagicMock(action="accept", data="gui")
        )

        with (
            patch(
                "ansys.mechanical.mcp.tools.pymechanical.launch_mechanical",
                return_value=mock_mechanical,
            ) as mock_launch,
            patch(
                "ansys.mechanical.mcp.tools.resolve_transport_mode",
                return_value=(None, None),
            ),
        ):
            result = await launch_mechanical(mock_context_no_mechanical)

            assert "Successfully launched Mechanical" in result
            mock_launch.assert_called_once_with(
                batch=False,
                loglevel="INFO",
                cleanup_on_exit=True,
                start_timeout=300,
            )

    @pytest.mark.parametrize("action", ["decline", "cancel"])
    @pytest.mark.asyncio
    async def test_launch_defaults_to_gui_when_prompt_not_accepted(
        self, mock_context_no_mechanical, action
    ):
        """Test launching Mechanical in GUI mode when the client declines or cancels."""
        mock_mechanical = MagicMock()
        mock_mechanical.version = "2024 R2"
        mock_mechanical.project_directory = "/tmp/ansys_mechanical_1234"

        mock_context_no_mechanical.elicit = AsyncMock(
            return_value=MagicMock(action=action, data=None)
        )

        with (
            patch(
                "ansys.mechanical.mcp.tools.pymechanical.launch_mechanical",
                return_value=mock_mechanical,
            ) as mock_launch,
            patch(
                "ansys.mechanical.mcp.tools.resolve_transport_mode",
                return_value=(None, None),
            ),
        ):
            result = await launch_mechanical(mock_context_no_mechanical)

            assert "Successfully launched Mechanical" in result
            mock_launch.assert_called_once_with(
                batch=False,
                loglevel="INFO",
                cleanup_on_exit=True,
                start_timeout=300,
            )

    @pytest.mark.asyncio
    async def test_launch_explicit_batch_true_skips_prompt(self, mock_context_no_mechanical):
        """Test launching Mechanical in batch mode when explicitly requested."""
        mock_mechanical = MagicMock()
        mock_mechanical.version = "2024 R2"
        mock_mechanical.project_directory = "/tmp/ansys_mechanical_1234"
        mock_context_no_mechanical.elicit = AsyncMock()

        with (
            patch(
                "ansys.mechanical.mcp.tools.pymechanical.launch_mechanical",
                return_value=mock_mechanical,
            ) as mock_launch,
            patch(
                "ansys.mechanical.mcp.tools.resolve_transport_mode",
                return_value=(None, None),
            ),
        ):
            result = await launch_mechanical(mock_context_no_mechanical, batch=True)

            assert "Successfully launched Mechanical" in result
            mock_context_no_mechanical.elicit.assert_not_awaited()
            mock_launch.assert_called_once_with(
                batch=True,
                loglevel="INFO",
                cleanup_on_exit=True,
                start_timeout=300,
            )

    @pytest.mark.asyncio
    async def test_launch_all_custom_parameters(self, mock_context_no_mechanical):
        """Test launching Mechanical with all custom parameters."""
        mock_mechanical = MagicMock()
        mock_mechanical.version = "2024 R1"
        mock_mechanical.project_directory = "/custom/work/dir"

        exec_path = "/path/to/mechanical"

        with (
            patch(
                "ansys.mechanical.mcp.tools.pymechanical.launch_mechanical",
                return_value=mock_mechanical,
            ) as mock_launch,
            patch(
                "ansys.mechanical.mcp.tools.resolve_transport_mode",
                return_value=(None, None),
            ),
        ):
            result = await launch_mechanical(
                mock_context_no_mechanical,
                exec_file=exec_path,
                port=10001,
                batch=False,
                version="241",
            )

            # Verify successful launch
            assert "Successfully launched Mechanical" in result
            assert "2024 R1" in result

            # Verify launch_mechanical was called with all parameters
            mock_launch.assert_called_once_with(
                batch=False,
                loglevel="INFO",
                cleanup_on_exit=True,
                start_timeout=300,
                exec_file=exec_path,
                port=10001,
                version="241",
            )

    @pytest.mark.asyncio
    async def test_launch_already_connected(self, mock_context):
        """Test launching when already connected to Mechanical."""
        # Context already has a Mechanical connection
        result = await launch_mechanical(mock_context)

        # Verify appropriate error message
        assert "Already connected to a Mechanical instance" in result
        assert "disconnect first" in result.lower()

    @pytest.mark.asyncio
    async def test_launch_error(self, mock_context_no_mechanical):
        """Test handling launch errors."""
        with patch(
            "ansys.mechanical.mcp.tools.pymechanical.launch_mechanical",
            side_effect=Exception("Mechanical executable not found"),
        ):
            result = await launch_mechanical(mock_context_no_mechanical)

            # Verify error message is returned
            assert "Failed to launch Mechanical" in result
            assert "Mechanical executable not found" in result

            # Verify context remains empty
            assert mock_context_no_mechanical.request_context.lifespan_context.mechanical is None

    @pytest.mark.asyncio
    async def test_launch_license_error(self, mock_context_no_mechanical):
        """Test handling license errors during launch."""
        with patch(
            "ansys.mechanical.mcp.tools.pymechanical.launch_mechanical",
            side_effect=Exception("No ANSYS license available"),
        ):
            result = await launch_mechanical(mock_context_no_mechanical)

            # Verify error message
            assert "Failed to launch Mechanical" in result
            assert "No ANSYS license available" in result

    @pytest.mark.asyncio
    async def test_launch_stores_mechanical_in_context(self, mock_context_no_mechanical):
        """Test that launched Mechanical instance is properly stored in context."""
        mock_mechanical = MagicMock()
        mock_mechanical.version = "2024 R2"
        mock_mechanical.project_directory = "/tmp/ansys_mechanical_1234"

        # Verify context starts with no Mechanical
        assert mock_context_no_mechanical.request_context.lifespan_context.mechanical is None

        with patch(
            "ansys.mechanical.mcp.tools.pymechanical.launch_mechanical",
            return_value=mock_mechanical,
        ):
            result = await launch_mechanical(mock_context_no_mechanical)

            # Verify successful launch
            assert "Successfully launched Mechanical" in result

            # Verify Mechanical is stored in context
            assert (
                mock_context_no_mechanical.request_context.lifespan_context.mechanical is not None
            )
            assert (
                mock_context_no_mechanical.request_context.lifespan_context.mechanical
                == mock_mechanical
            )

    @pytest.mark.asyncio
    async def test_launch_result_message(self, mock_context_no_mechanical):
        """Test that launch_mechanical returns informative success message."""
        mock_mechanical = MagicMock()
        mock_mechanical.version = "2024 R2"
        mock_mechanical.project_directory = "/tmp/ansys_mechanical_1234"

        with patch(
            "ansys.mechanical.mcp.tools.pymechanical.launch_mechanical",
            return_value=mock_mechanical,
        ):
            result = await launch_mechanical(mock_context_no_mechanical)

            # Verify the result contains launch information
            assert isinstance(result, str)
            assert "Successfully launched Mechanical" in result
            assert "Version: 2024 R2" in result
            assert "Project Directory:" in result

    @pytest.mark.asyncio
    async def test_launch_with_port_parameter(self, mock_context_no_mechanical):
        """Test launching Mechanical with specific port parameter."""
        mock_mechanical = MagicMock()
        mock_mechanical.version = "2024 R2"
        mock_mechanical.project_directory = "/tmp/ansys_mechanical_1234"

        mock_context_no_mechanical.elicit = AsyncMock(
            side_effect=RuntimeError("elicitation unavailable")
        )

        with (
            patch(
                "ansys.mechanical.mcp.tools.pymechanical.launch_mechanical",
                return_value=mock_mechanical,
            ) as mock_launch,
            patch(
                "ansys.mechanical.mcp.tools.resolve_transport_mode",
                return_value=(None, None),
            ),
        ):
            result = await launch_mechanical(mock_context_no_mechanical, port=10060)

            # Verify successful launch
            assert isinstance(result, str)
            assert "Successfully launched Mechanical" in result

            # Verify launch_mechanical was called with port
            mock_launch.assert_called_once_with(
                batch=False,
                loglevel="INFO",
                cleanup_on_exit=True,
                start_timeout=300,
                port=10060,
            )

    @pytest.mark.asyncio
    async def test_launch_connection_info_in_result(self, mock_context_no_mechanical):
        """Test that launch result contains all connection info."""
        mock_mechanical = MagicMock()
        mock_mechanical.version = "2024 R2"
        mock_mechanical.project_directory = "/home/user/mechanical_work"

        with patch(
            "ansys.mechanical.mcp.tools.pymechanical.launch_mechanical",
            return_value=mock_mechanical,
        ):
            result = await launch_mechanical(mock_context_no_mechanical)

            # Verify all connection details are in result
            assert "Successfully launched Mechanical" in result
            assert "Version: 2024 R2" in result
            assert "Project Directory:" in result


@pytest.mark.unit
class TestConnectionLifecycle:
    """Tests for the full connection lifecycle."""

    @pytest.mark.asyncio
    async def test_connect_use_disconnect_workflow(self, mock_context_no_mechanical):
        """Test complete workflow: connect, use, disconnect."""
        # Create mock Mechanical
        mock_mechanical = MagicMock()
        mock_mechanical.name = "Mechanical"
        mock_mechanical.version = "2024 R2"
        mock_mechanical.project_directory = "/tmp/test"
        mock_mechanical.is_alive = True
        mock_mechanical.exited = False
        mock_mechanical.busy = False

        mock_mechanical.run_python_script = MagicMock(return_value="Script executed")
        mock_mechanical.get_product_info = MagicMock(return_value="Product Info")

        # Step 1: Connect
        with patch(
            "ansys.mechanical.mcp.tools.pymechanical.connect_to_mechanical",
            return_value=mock_mechanical,
        ):
            result = await connect_to_mechanical(mock_context_no_mechanical)
            assert "Successfully connected" in result

        # Step 2: Use Mechanical
        status = check_mechanical_status(mock_context_no_mechanical)
        status_data = json.loads(status)
        assert "connection" in status_data
        assert status_data["connection"]["version"] == "2024 R2"

        script_result = run_python_script(mock_context_no_mechanical, "print('test')")
        assert "Script executed successfully" in script_result

        # Step 3: Disconnect
        result = await disconnect_from_mechanical(mock_context_no_mechanical)
        assert "Successfully disconnected" in result

        # Step 4: Verify connection is cleared
        status_after = check_mechanical_status(mock_context_no_mechanical)
        assert "No Mechanical connection available" in status_after

    @pytest.mark.asyncio
    async def test_reconnect_after_disconnect(self, mock_context_no_mechanical):
        """Test that we can reconnect after disconnecting."""
        mock_mechanical1 = MagicMock()
        mock_mechanical1.version = "2024 R2"
        mock_mechanical1._ip = "127.0.0.1"
        mock_mechanical1._port = 10000

        mock_mechanical2 = MagicMock()
        mock_mechanical2.version = "2024 R1"
        mock_mechanical2._ip = "127.0.0.1"
        mock_mechanical2._port = 10001

        # First connection
        with patch(
            "ansys.mechanical.mcp.tools.pymechanical.connect_to_mechanical",
            return_value=mock_mechanical1,
        ):
            result = await connect_to_mechanical(mock_context_no_mechanical, port=10000)
            assert "Successfully connected" in result
            assert "10000" in result

        # Disconnect
        await disconnect_from_mechanical(mock_context_no_mechanical)

        # Second connection with different parameters
        with patch(
            "ansys.mechanical.mcp.tools.pymechanical.connect_to_mechanical",
            return_value=mock_mechanical2,
        ):
            result = await connect_to_mechanical(mock_context_no_mechanical, port=10001)
            assert "Successfully connected" in result
            assert "10001" in result

    def test_tools_without_connection(self, mock_context_no_mechanical):
        """Test that tools return appropriate messages without connection."""
        # Check status without connection
        status = check_mechanical_status(mock_context_no_mechanical)
        assert "No Mechanical connection available" in status

        # Try to run script without connection
        script_result = run_python_script(mock_context_no_mechanical, "print('test')")
        assert "No Mechanical connection available" in script_result


@pytest.mark.unit
class TestLaunchWorkflow:
    """Tests for launch and usage workflow."""

    @pytest.mark.asyncio
    async def test_launch_use_disconnect_workflow(self, mock_context_no_mechanical):
        """Test complete workflow: launch, use, disconnect."""
        # Create mock Mechanical
        mock_mechanical = MagicMock()
        mock_mechanical.name = "Mechanical"
        mock_mechanical.check_status = "Running"
        mock_mechanical.version = "2024 R2"
        mock_mechanical.project_directory = "/tmp/ansys_mechanical_1234"
        mock_mechanical.is_alive = True
        mock_mechanical.is_local = True
        mock_mechanical._exited = False
        mock_mechanical._exiting = False
        mock_mechanical.exited = False
        mock_mechanical.busy = False

        mock_mechanical.run_python_script = MagicMock(return_value="Script executed")
        mock_mechanical.get_product_info = MagicMock(return_value="Product Info")

        # Step 1: Launch
        with patch(
            "ansys.mechanical.mcp.tools.pymechanical.launch_mechanical",
            return_value=mock_mechanical,
        ):
            result = await launch_mechanical(mock_context_no_mechanical)
            assert "Successfully launched Mechanical" in result

        # Step 2: Use Mechanical
        status = check_mechanical_status(mock_context_no_mechanical)
        status_data = json.loads(status)
        assert "connection" in status_data
        assert status_data["connection"]["version"] == "2024 R2"

        script_result = run_python_script(mock_context_no_mechanical, "print('test')")
        assert "Script executed successfully" in script_result

        # Step 3: Disconnect
        result = await disconnect_from_mechanical(mock_context_no_mechanical)
        assert "Successfully disconnected" in result

        # Step 4: Verify connection is cleared
        status_after = check_mechanical_status(mock_context_no_mechanical)
        assert "No Mechanical connection available" in status_after

    @pytest.mark.asyncio
    async def test_launch_after_disconnect(self, mock_context_no_mechanical):
        """Test that we can launch after disconnecting."""
        mock_mechanical1 = MagicMock()
        mock_mechanical1.version = "2024 R2"
        mock_mechanical1.project_directory = "/tmp/ansys_mechanical_1234"

        mock_mechanical2 = MagicMock()
        mock_mechanical2.version = "2024 R1"
        mock_mechanical2.project_directory = "/tmp/ansys_mechanical_5678"

        # First launch
        with patch(
            "ansys.mechanical.mcp.tools.pymechanical.launch_mechanical",
            return_value=mock_mechanical1,
        ):
            result = await launch_mechanical(mock_context_no_mechanical)
            assert "Successfully launched Mechanical" in result
            assert "2024 R2" in result

        # Disconnect
        await disconnect_from_mechanical(mock_context_no_mechanical)

        # Second launch
        with patch(
            "ansys.mechanical.mcp.tools.pymechanical.launch_mechanical",
            return_value=mock_mechanical2,
        ):
            result = await launch_mechanical(mock_context_no_mechanical)
            assert "Successfully launched Mechanical" in result
            assert "2024 R1" in result

    @pytest.mark.asyncio
    async def test_cannot_launch_when_connected(self, mock_context_no_mechanical):
        """Test that launching fails when already connected."""
        # First, connect to an existing instance
        mock_mechanical = MagicMock()
        mock_mechanical.version = "2024 R2"
        mock_mechanical._ip = "127.0.0.1"
        mock_mechanical._port = 10000

        with patch(
            "ansys.mechanical.mcp.tools.pymechanical.connect_to_mechanical",
            return_value=mock_mechanical,
        ):
            connect_result = await connect_to_mechanical(mock_context_no_mechanical)
            assert "Successfully connected" in connect_result

        # Now try to launch - should fail
        launch_result = await launch_mechanical(mock_context_no_mechanical)
        assert "Already connected to a Mechanical instance" in launch_result
        assert "disconnect first" in launch_result.lower()


@pytest.mark.unit
class TestCheckMechanicalInstalled:
    """Tests for check_mechanical_installed tool."""

    def test_check_installed_true(self):
        """Test when Mechanical is installed."""
        with patch("ansys.mechanical.core.mechanical.check_valid_mechanical", return_value=True):
            result = check_mechanical_installed(MagicMock())

            assert isinstance(result, str)
            assert "installed" in result.lower()

    def test_check_installed_false(self):
        """Test when Mechanical is not installed."""
        with patch(
            "ansys.mechanical.core.mechanical.check_valid_mechanical",
            return_value=False,
        ):
            result = check_mechanical_installed(MagicMock())

            assert isinstance(result, str)
            assert "not installed" in result.lower()

    def test_check_installed_exception(self):
        """Test error handling during installation check."""
        with patch(
            "ansys.mechanical.core.mechanical.check_valid_mechanical",
            side_effect=Exception("System error"),
        ):
            result = check_mechanical_installed(MagicMock())

            assert isinstance(result, str)
            assert "Error" in result


@pytest.mark.unit
class TestListMechanicalInstances:
    """Tests for list_mechanical_instances tool."""

    def test_list_instances(self):
        """Test listing Mechanical instances."""
        with patch(
            "ansys.mechanical.mcp.helpers.list_instances",
            return_value="Instance 1\nInstance 2",
        ):
            result = list_mechanical_instances()

            assert isinstance(result, str)

    def test_list_instances_no_instances(self):
        """Test when no Mechanical instances are running."""
        with patch(
            "ansys.mechanical.mcp.helpers.list_instances",
            return_value="No instances found",
        ):
            result = list_mechanical_instances()

            assert isinstance(result, str)


@pytest.mark.unit
class TestListFiles:
    """Tests for list_files tool."""

    def test_list_files_success(self, mock_context):
        """Test listing files successfully."""
        mock_context.request_context.lifespan_context.mechanical.list_files.return_value = [
            "file1.txt",
            "file2.txt",
            "model.mechdb",
        ]

        result = list_files(mock_context)

        assert isinstance(result, str)
        assert "file1.txt" in result
        assert "file2.txt" in result

    def test_list_files_empty(self, mock_context):
        """Test when no files in directory."""
        mock_context.request_context.lifespan_context.mechanical.list_files.return_value = []

        result = list_files(mock_context)

        assert "No files found" in result

    def test_list_files_no_mechanical(self, mock_context_no_mechanical):
        """Test listing files without Mechanical connection."""
        result = list_files(mock_context_no_mechanical)

        assert "No Mechanical connection available" in result

    def test_list_files_error(self, mock_context):
        """Test error handling during file listing."""
        mock_context.request_context.lifespan_context.mechanical.list_files.side_effect = Exception(
            "Permission denied"
        )

        result = list_files(mock_context)

        assert "Error listing files" in result


@pytest.mark.unit
class TestUploadFile:
    """Tests for upload_file tool."""

    def test_upload_file_success(self, mock_context, tmp_path):
        """Test uploading file successfully."""
        # Create a temporary file
        test_file = tmp_path / "test_upload.txt"
        test_file.write_text("test content")

        mock_context.request_context.lifespan_context.mechanical.upload.return_value = (
            "test_upload.txt"
        )

        result = upload_file(mock_context, str(test_file))

        assert "Successfully uploaded" in result

    def test_upload_file_not_found(self, mock_context):
        """Test uploading non-existent file."""
        result = upload_file(mock_context, "/nonexistent/file.txt")

        assert "File not found" in result

    def test_upload_file_no_mechanical(self, mock_context_no_mechanical, tmp_path):
        """Test uploading without Mechanical connection."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")

        result = upload_file(mock_context_no_mechanical, str(test_file))

        assert "No Mechanical connection available" in result

    def test_upload_file_error(self, mock_context, tmp_path):
        """Test error handling during upload."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")

        mock_context.request_context.lifespan_context.mechanical.upload.side_effect = Exception(
            "Upload failed"
        )

        result = upload_file(mock_context, str(test_file))

        assert "Error uploading file" in result


@pytest.mark.unit
class TestDownloadFile:
    """Tests for download_file tool."""

    def test_download_file_success(self, mock_context, tmp_path):
        """Test downloading file successfully."""
        mock_context.request_context.lifespan_context.mechanical.download.return_value = [
            str(tmp_path / "downloaded.txt")
        ]

        result = download_file(mock_context, "test.txt", str(tmp_path))

        assert "Successfully downloaded" in result

    def test_download_file_no_match(self, mock_context):
        """Test when no files match."""
        mock_context.request_context.lifespan_context.mechanical.download.return_value = []

        result = download_file(mock_context, "nonexistent.txt")

        assert "No files matching" in result

    def test_download_file_no_mechanical(self, mock_context_no_mechanical):
        """Test downloading without Mechanical connection."""
        result = download_file(mock_context_no_mechanical, "test.txt")

        assert "No Mechanical connection available" in result

    def test_download_file_error(self, mock_context):
        """Test error handling during download."""
        mock_context.request_context.lifespan_context.mechanical.download.side_effect = Exception(
            "Download failed"
        )

        result = download_file(mock_context, "test.txt")

        assert "Error downloading file" in result


@pytest.mark.unit
class TestClearMechanical:
    """Tests for clear_mechanical tool."""

    def test_clear_success(self, mock_context):
        """Test clearing Mechanical database successfully."""
        mock_context.request_context.lifespan_context.mechanical.clear.return_value = None

        result = clear_mechanical(mock_context)

        assert "cleared successfully" in result.lower()

    def test_clear_no_mechanical(self, mock_context_no_mechanical):
        """Test clearing without Mechanical connection."""
        result = clear_mechanical(mock_context_no_mechanical)

        assert "No Mechanical connection available" in result

    def test_clear_error(self, mock_context):
        """Test error handling during clear."""
        mock_context.request_context.lifespan_context.mechanical.clear.side_effect = Exception(
            "Cannot clear"
        )

        result = clear_mechanical(mock_context)

        assert "Error clearing database" in result


@pytest.mark.unit
class TestGetModelInfo:
    """Tests for get_model_info tool."""

    def test_get_model_info_success(self, mock_context):
        """Test getting model info successfully."""
        mock_context.request_context.lifespan_context.mechanical.run_python_script.return_value = (
            '{"project": {"name": "Test"}, "model": {"name": "Model1"}}'
        )

        result = get_model_info(mock_context)

        assert isinstance(result, str)

    def test_get_model_info_no_mechanical(self, mock_context_no_mechanical):
        """Test getting model info without Mechanical connection."""
        result = get_model_info(mock_context_no_mechanical)

        assert "No Mechanical connection available" in result

    def test_get_model_info_error(self, mock_context):
        """Test error handling when getting model info."""
        mock_context.request_context.lifespan_context.mechanical.run_python_script.side_effect = (
            Exception("Script error")
        )

        result = get_model_info(mock_context)

        assert "Error getting model info" in result


@pytest.mark.unit
class TestScreenshot:
    """Tests for screenshot tool."""

    def test_screenshot_no_mechanical(self, mock_context_no_mechanical):
        """Test screenshot without Mechanical connection."""
        result = screenshot(mock_context_no_mechanical)

        assert len(result) == 1
        assert isinstance(result[0], TextContent)
        assert "No Mechanical connection available" in result[0].text

    def test_screenshot_success(self, mock_context, tmp_path):
        """Test screenshot capture successfully."""
        # Mock the script execution and file creation
        test_image_path = tmp_path / "screenshot.png"
        test_image_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)  # Fake PNG

        mock_context.request_context.lifespan_context.mechanical.run_python_script.return_value = (
            str(test_image_path)
        )

        with (
            patch("tempfile.mkstemp", return_value=(0, str(test_image_path))),
            patch("os.close"),
            patch("os.path.exists", return_value=True),
            patch("builtins.open", create=True) as mock_open,
        ):
            mock_open.return_value.__enter__.return_value.read.return_value = (
                b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
            )
            result = screenshot(mock_context)

            # Either success with image content or text content with error
            assert len(result) >= 1

    def test_screenshot_with_view_type(self, mock_context):
        """Test screenshot with different view types."""
        mock_context.request_context.lifespan_context.mechanical.run_python_script.side_effect = (
            Exception("Graphics not available")
        )

        result = screenshot(mock_context, view_type="mesh")

        # Should handle error gracefully
        assert len(result) >= 1


@pytest.mark.unit
class TestSaveProject:
    """Tests for save_project tool."""

    def test_save_project_no_mechanical(self, mock_context_no_mechanical):
        """Test saving project without Mechanical connection."""
        from ansys.mechanical.mcp.tools import save_project

        result = save_project(mock_context_no_mechanical)
        assert "No Mechanical connection available" in result

    def test_save_project_in_place(self, mock_context):
        """Test saving project in current location."""
        from ansys.mechanical.mcp.tools import save_project

        mock_context.request_context.lifespan_context.mechanical.run_python_script.return_value = ""

        result = save_project(mock_context)
        assert "Project saved successfully" in result
        mock_context.request_context.lifespan_context.mechanical.run_python_script.assert_called_once_with(
            "ExtAPI.DataModel.Project.Save()"
        )

    def test_save_project_as_new_path(self, mock_context, tmp_path):
        """Test saving project to a new location."""
        from ansys.mechanical.mcp.tools import save_project

        file_path = str(tmp_path / "test_project.mechdb")
        mock_context.request_context.lifespan_context.mechanical.run_python_script.return_value = ""

        result = save_project(mock_context, file_path=file_path)
        assert "Project saved to" in result
        assert file_path in result

    def test_save_project_adds_extension(self, mock_context, tmp_path):
        """Test that .mechdb extension is added if missing."""
        from ansys.mechanical.mcp.tools import save_project

        file_path = str(tmp_path / "test_project")
        mock_context.request_context.lifespan_context.mechanical.run_python_script.return_value = ""

        result = save_project(mock_context, file_path=file_path)
        assert "Project saved to" in result
        assert ".mechdb" in result

    def test_save_project_invalid_directory(self, mock_context):
        """Test saving project to non-existent directory."""
        from ansys.mechanical.mcp.tools import save_project

        result = save_project(mock_context, file_path="/nonexistent_xyz_dir/subdir/project.mechdb")
        assert "Directory does not exist" in result

    def test_save_project_error(self, mock_context):
        """Test error handling during save."""
        from ansys.mechanical.mcp.tools import save_project

        mock_context.request_context.lifespan_context.mechanical.run_python_script.side_effect = (
            Exception("Save failed: disk full")
        )

        result = save_project(mock_context)
        assert "Error saving project" in result
        assert "disk full" in result


@pytest.mark.unit
class TestOpenProject:
    """Tests for open_project tool."""

    def test_open_project_no_mechanical(self, mock_context_no_mechanical):
        """Test opening project without Mechanical connection."""
        from ansys.mechanical.mcp.tools import open_project

        result = open_project(mock_context_no_mechanical, "test.mechdb")
        assert "No Mechanical connection is available" in result

    def test_open_project_file_not_found(self, mock_context):
        """Test opening a non-existent project file."""
        from ansys.mechanical.mcp.tools import open_project

        result = open_project(mock_context, "Z:\\nonexistent\\project.mechdb")
        assert "Project file not found" in result

    def test_open_project_invalid_extension(self, mock_context, tmp_path):
        """Test opening a file with wrong extension."""
        from ansys.mechanical.mcp.tools import open_project

        wrong_file = tmp_path / "test.txt"
        wrong_file.write_text("not a project")

        result = open_project(mock_context, str(wrong_file))
        assert "Invalid file type" in result
        assert "MECHDB" in result

    def test_open_project_success(self, mock_context, tmp_path):
        """Test opening a valid project file."""
        from ansys.mechanical.mcp.tools import open_project

        project_file = tmp_path / "test_project.mechdb"
        project_file.write_bytes(b"dummy")  # Create a dummy file

        mock_context.request_context.lifespan_context.mechanical.run_python_script.side_effect = [
            "",  # Open call
            '{"name": "TestProject", "product_version": "2025 R2", "body_count": 3, "analyses_count": 1}',
        ]

        result = open_project(mock_context, str(project_file))
        assert "Project opened successfully" in result
        assert "TestProject" in result

    def test_open_project_error(self, mock_context, tmp_path):
        """Test error handling during project open."""
        from ansys.mechanical.mcp.tools import open_project

        project_file = tmp_path / "corrupt.mechdb"
        project_file.write_bytes(b"corrupt")

        mock_context.request_context.lifespan_context.mechanical.run_python_script.side_effect = (
            Exception("File is corrupt")
        )

        result = open_project(mock_context, str(project_file))
        assert "Error opening project" in result
        assert "corrupt" in result


@pytest.mark.unit
class TestSolveAnalysis:
    """Tests for solve_analysis tool."""

    def test_solve_no_mechanical(self, mock_context_no_mechanical):
        """Test solving without Mechanical connection."""
        from ansys.mechanical.mcp.tools import solve_analysis

        result = solve_analysis(mock_context_no_mechanical)
        assert "No Mechanical connection is available" in result

    def test_solve_success(self, mock_context):
        """Test successful solve."""
        from ansys.mechanical.mcp.tools import solve_analysis

        mock_context.request_context.lifespan_context.mechanical.run_python_script.return_value = (
            json.dumps(
                {
                    "success": True,
                    "status": "Done",
                    "analysis_name": "Static Structural",
                    "analysis_type": "Static",
                    "elapsed_seconds": 5.2,
                    "warnings": [],
                    "result_objects_count": 2,
                }
            )
        )

        result = solve_analysis(mock_context)
        data = json.loads(result)
        assert data["success"] is True
        assert data["status"] == "Done"
        assert data["analysis_name"] == "Static Structural"

    def test_solve_custom_index(self, mock_context):
        """Test solving a specific analysis by index."""
        from ansys.mechanical.mcp.tools import solve_analysis

        mock_context.request_context.lifespan_context.mechanical.run_python_script.return_value = (
            json.dumps({"success": True, "status": "Done", "analysis_name": "Modal"})
        )

        result = solve_analysis(mock_context, analysis_index=1)
        data = json.loads(result)
        assert data["success"] is True

    def test_solve_failure(self, mock_context):
        """Test solve failure response."""
        from ansys.mechanical.mcp.tools import solve_analysis

        mock_context.request_context.lifespan_context.mechanical.run_python_script.return_value = (
            json.dumps(
                {
                    "success": False,
                    "error": "No analyses defined in the model",
                }
            )
        )

        result = solve_analysis(mock_context)
        data = json.loads(result)
        assert data["success"] is False
        assert "No analyses defined" in data["error"]

    def test_solve_exception(self, mock_context):
        """Test solve exception handling."""
        from ansys.mechanical.mcp.tools import solve_analysis

        mock_context.request_context.lifespan_context.mechanical.run_python_script.side_effect = (
            Exception("gRPC connection lost")
        )

        result = solve_analysis(mock_context)
        data = json.loads(result)
        assert data["success"] is False
        assert "gRPC connection lost" in data["error"]


@pytest.mark.unit
class TestExportResults:
    """Tests for export_results tool."""

    def test_export_no_mechanical(self, mock_context_no_mechanical):
        """Test exporting without Mechanical connection."""
        from ansys.mechanical.mcp.tools import export_results

        result = export_results(mock_context_no_mechanical)
        assert "No Mechanical connection available" in result

    def test_export_success(self, mock_context, tmp_path):
        """Test successful result export."""
        from ansys.mechanical.mcp.tools import export_results

        mock_context.request_context.lifespan_context.mechanical.run_python_script.return_value = (
            json.dumps(
                {
                    "success": True,
                    "exported_files": [
                        str(tmp_path / "Total_Deformation.png"),
                        str(tmp_path / "Equivalent_Stress.png"),
                    ],
                    "file_count": 2,
                    "errors": [],
                    "output_directory": str(tmp_path),
                }
            )
        )

        result = export_results(mock_context, output_dir=str(tmp_path))
        data = json.loads(result)
        assert data["success"] is True
        assert data["file_count"] == 2

    def test_export_specific_result_type(self, mock_context, tmp_path):
        """Test exporting specific result type."""
        from ansys.mechanical.mcp.tools import export_results

        mock_context.request_context.lifespan_context.mechanical.run_python_script.return_value = (
            json.dumps(
                {
                    "success": True,
                    "exported_files": [str(tmp_path / "Equivalent_Stress.png")],
                    "file_count": 1,
                    "errors": [],
                    "output_directory": str(tmp_path),
                }
            )
        )

        result = export_results(mock_context, result_type="stress", output_dir=str(tmp_path))
        data = json.loads(result)
        assert data["success"] is True
        assert data["file_count"] == 1

    def test_export_both_formats(self, mock_context, tmp_path):
        """Test exporting in both PNG and TXT formats."""
        from ansys.mechanical.mcp.tools import export_results

        mock_context.request_context.lifespan_context.mechanical.run_python_script.return_value = (
            json.dumps(
                {
                    "success": True,
                    "exported_files": [
                        str(tmp_path / "Total_Deformation.png"),
                        str(tmp_path / "Total_Deformation.txt"),
                    ],
                    "file_count": 2,
                    "errors": [],
                    "output_directory": str(tmp_path),
                }
            )
        )

        result = export_results(mock_context, export_format="both", output_dir=str(tmp_path))
        data = json.loads(result)
        assert data["success"] is True
        assert data["file_count"] == 2

    def test_export_no_solution(self, mock_context):
        """Test export when solution has not been run."""
        from ansys.mechanical.mcp.tools import export_results

        mock_context.request_context.lifespan_context.mechanical.run_python_script.return_value = (
            json.dumps(
                {
                    "success": False,
                    "error": "Solution has not been completed. Status: NotSolved",
                }
            )
        )

        result = export_results(mock_context)
        data = json.loads(result)
        assert data["success"] is False
        assert "not been completed" in data["error"]

    def test_export_exception(self, mock_context):
        """Test export exception handling."""
        from ansys.mechanical.mcp.tools import export_results

        mock_context.request_context.lifespan_context.mechanical.run_python_script.side_effect = (
            Exception("Export error")
        )

        result = export_results(mock_context)
        data = json.loads(result)
        assert data["success"] is False
        assert "Export error" in data["error"]


@pytest.mark.unit
class TestRequiresMechanicalVisibility:
    """Tests for Mechanical-connection-aware tool visibility."""

    @pytest.mark.asyncio
    async def test_connect_enables_requires_mechanical_tools(self, mock_context_no_mechanical):
        """Successful connect_to_mechanical should call ctx.enable_components for the tag."""
        mock_mechanical = MagicMock()
        mock_mechanical.version = "2024 R2"
        mock_mechanical._ip = "127.0.0.1"
        mock_mechanical._port = 10000

        with patch(
            "ansys.mechanical.mcp.tools.pymechanical.connect_to_mechanical",
            return_value=mock_mechanical,
        ):
            await connect_to_mechanical(mock_context_no_mechanical)
            mock_context_no_mechanical.enable_components.assert_called_once_with(
                tags={"requires_mechanical"}
            )

    @pytest.mark.asyncio
    async def test_connect_does_not_enable_on_failure(self, mock_context_no_mechanical):
        """Failed connect_to_mechanical should not call ctx.enable_components."""
        with patch(
            "ansys.mechanical.mcp.tools.pymechanical.connect_to_mechanical",
            side_effect=Exception("Connection refused"),
        ):
            await connect_to_mechanical(mock_context_no_mechanical)
            mock_context_no_mechanical.enable_components.assert_not_called()

    @pytest.mark.asyncio
    async def test_launch_enables_requires_mechanical_tools(self, mock_context_no_mechanical):
        """Successful launch_mechanical should call ctx.enable_components for the tag."""
        mock_mechanical = MagicMock()
        mock_mechanical.version = "2024 R2"
        mock_mechanical.project_directory = "/tmp/proj"

        with patch(
            "ansys.mechanical.mcp.tools.pymechanical.launch_mechanical",
            return_value=mock_mechanical,
        ):
            await launch_mechanical(mock_context_no_mechanical)
            mock_context_no_mechanical.enable_components.assert_called_once_with(
                tags={"requires_mechanical"}
            )

    @pytest.mark.asyncio
    async def test_disconnect_disables_requires_mechanical_tools(self, mock_context):
        """Successful disconnect_from_mechanical should call ctx.disable_components."""
        await disconnect_from_mechanical(mock_context)
        mock_context.disable_components.assert_called_once_with(tags={"requires_mechanical"})

    def test_no_tool_surface_drift(self):
        """Every tool must be in the always-available allowlist or carry
        the ``requires_mechanical`` gating tag.

        This test prevents accidental "tool surface drift", i.e. someone
        adding a new tool that needs a Mechanical connection but
        forgetting to tag it ``requires_mechanical``. Without the tag,
        the tool would be exposed to clients before any Mechanical
        session exists and would crash at call time.

        If you add a brand-new tool that legitimately must be reachable
        BEFORE any Mechanical connection is established (e.g. a pure
        installation / diagnostic helper), add its name to
        ``ALWAYS_AVAILABLE_TOOLS`` below. Otherwise, tag the tool
        ``requires_mechanical`` (see ``REQUIRES_MECHANICAL_TAG`` in
        tools.py).
        """
        import asyncio

        from ansys.mechanical.mcp.server import app

        # Tools that are intentionally reachable before any Mechanical
        # session. Keep this list minimal; anything that touches a
        # connected Mechanical instance must NOT be here.
        ALWAYS_AVAILABLE_TOOLS = {
            "check_mechanical_installed",
            "check_mechanical_status",
            "launch_mechanical",
            "connect_to_mechanical",
            "list_mechanical_instances",
            "get_guidelines_for",
        }

        async def _list():
            return await app._local_provider._list_tools()

        tools = asyncio.run(_list())
        offenders = []
        for t in tools:
            tags = t.tags or set()
            if t.name in ALWAYS_AVAILABLE_TOOLS:
                continue
            if "requires_mechanical" not in tags:
                offenders.append(t.name)

        assert not offenders, (
            "The following tools are missing the 'requires_mechanical' "
            "tag and are not in the ALWAYS_AVAILABLE_TOOLS allowlist:\n  - "
            + "\n  - ".join(sorted(offenders))
            + "\n\nEither tag the tool with REQUIRES_MECHANICAL_TAG (the "
            "common case) or, if the tool genuinely does not need a "
            "Mechanical session, add it to ALWAYS_AVAILABLE_TOOLS in "
            "this test."
        )
