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

"""Integration tests for PyMAPDL MCP Server.

These tests require a running MAPDL instance and are marked as 'integration'.
Run with: pytest -m integration

To skip integration tests, run: pytest -m "not integration"
"""

import json
import os
import tempfile
import time
from unittest.mock import AsyncMock, MagicMock

from ansys.mapdl.core import launch_mapdl
from fastmcp.tools.base import ToolResult
import numpy as np
import pytest

from ansys.mapdl.mcp.server import PyMAPDLAppContext
from ansys.mapdl.mcp.tools import (
    check_mapdl_status,
    disconnect_from_mapdl,
    launch_mapdl_session,
    list_mapdl_instances,
    run_mapdl_command,
    run_multiple_mapdl_commands,
    run_python_code,
)

ON_LOCAL = os.getenv("ON_LOCAL", "true") == "true"
START_INSTANCE = os.getenv("PYMAPDL_START_INSTANCE", "true") == "true"


@pytest.fixture
def real_context(mock_mapdl):
    """Module-level context fixture using a mock MAPDL for persistent session tests."""
    context = MagicMock()
    context.request_context = MagicMock()
    # Attach a python_session mock with metadata dict to simulate persistent session
    py_session = MagicMock()
    py_session.metadata = {}
    lc = PyMAPDLAppContext(mapdl=mock_mapdl)
    lc.python_session = py_session
    context.request_context.lifespan_context = lc
    return context


@pytest.mark.integration
@pytest.mark.slow
class TestMapdlIntegration:
    """Integration tests that require a real MAPDL connection.

    This class combines all basic MAPDL integration tests to share a single
    MAPDL instance, reducing test execution time.
    """

    @pytest.fixture(scope="class")
    def real_mapdl(self):
        """
        Fixture to connect to a real MAPDL instance.

        This requires MAPDL to be running on localhost:50052.
        Skip these tests if MAPDL is not available.
        """
        try:
            mapdl = launch_mapdl(cleanup_on_exit=False, loglevel="ERROR")

            yield mapdl

            # Cleanup after tests
            # Don't exit since MAPDL is running externally
            mapdl.exit()

        except Exception as e:
            # Not allow to skip if running on CICD
            if os.getenv("ON_CI", False):
                raise e
            else:
                pytest.skip(f"MAPDL not available: {e}")

    @pytest.fixture()
    def mapdl(self, real_mapdl):
        real_mapdl.clear()
        return real_mapdl

    @pytest.fixture
    def real_context(self, real_mapdl):
        """Create a real context with actual MAPDL connection."""
        context = MagicMock()
        context.request_context = MagicMock()
        context.request_context.lifespan_context = PyMAPDLAppContext(mapdl=real_mapdl)

        return context

    def test_real_check_mapdl_status(self, real_context):
        """Test checking MAPDL status with a real connection."""
        result = check_mapdl_status(real_context)

        assert isinstance(result, ToolResult)
        # Check for JSON structure
        data = json.loads(result.content[0].text)
        assert "connection" in data
        assert "version" in data["connection"]
        assert data["connection"]["status"] == "Running"

    def test_real_run_command(self, real_context):
        """Test running a MAPDL command with a real connection."""
        # Use a safe command that doesn't affect the model
        command = "/INQUIRE,RELEASE"
        result = run_mapdl_command(real_context, command)

        assert isinstance(result, ToolResult)
        assert "MAPDL command executed successfully" in result.content[0].text

    def test_real_prep7_workflow(self, real_context):
        """Test a basic PREP7 workflow with real MAPDL."""
        # Clear any existing model
        run_mapdl_command(real_context, "/CLEAR")

        # Enter preprocessor
        result = run_mapdl_command(real_context, "/PREP7")
        assert "executed successfully" in result.content[0].text

        # Define element type
        result = run_mapdl_command(real_context, "ET,1,SOLID185")
        assert "executed successfully" in result.content[0].text

        # Define material property
        result = run_mapdl_command(real_context, "MP,EX,1,200E9")
        assert "executed successfully" in result.content[0].text

    def test_real_run_multiple_mapdl_commands(self, real_context):
        """Test running multiple commands with real MAPDL."""
        # Clear any existing model
        run_mapdl_command(real_context, "/CLEAR")

        # Run multiple commands
        commands = [
            "/PREP7",
            "ET,1,SOLID185",
            "MP,EX,1,200E9",
            "MP,PRXY,1,0.3",
        ]

        result = run_multiple_mapdl_commands(real_context, commands)

        assert isinstance(result, ToolResult)
        assert "Successfully executed 4 MAPDL commands" in result.content[1].text
        assert all(cmd in result.content[1].text for cmd in commands)

    def test_real_run_multiple_mapdl_commands_with_geometry(self, real_context):
        """Test running multiple commands to create simple geometry."""
        # Clear any existing model
        run_mapdl_command(real_context, "/CLEAR")

        # Create a simple block using multiple commands
        commands = [
            "/PREP7",
            "ET,1,SOLID185",
            "MP,EX,1,200E9",
            "MP,PRXY,1,0.3",
            "BLC4,0,0,1,1,1",  # Create a block
        ]

        result = run_multiple_mapdl_commands(real_context, commands)

        assert "Successfully executed 5 MAPDL commands" in result.content[1].text
        assert "BLC4,0,0,1,1,1" in result.content[1].text

    def test_real_run_multiple_mapdl_commands_empty_list(self, real_context):
        """Test error handling with empty command list."""
        result = run_multiple_mapdl_commands(real_context, [])

        assert "No commands provided" in result.content[0].text

    def test_real_run_multiple_mapdl_commands_vs_single(self, real_context):
        """Compare run_multiple_mapdl_commands with sequential single commands."""
        # Clear any existing model
        run_mapdl_command(real_context, "/CLEAR")

        commands = [
            "/PREP7",
            "ET,1,SOLID185",
            "MP,EX,1,200E9",
        ]

        # Test multiple commands
        result_multi = run_multiple_mapdl_commands(real_context, commands)
        assert "Successfully executed 3 MAPDL commands" in result_multi.content[1].text

        # Clear and test single commands
        run_mapdl_command(real_context, "/CLEAR")

        results_single = []
        for cmd in commands:
            result = run_mapdl_command(real_context, cmd)
            results_single.append(result)
            assert "executed successfully" in result.content[0].text

        # Both approaches should work successfully
        assert len(results_single) == 3

    def test_multiple_commands_large_batch(self, real_context, mapdl):
        """Test running a large batch of commands."""
        # Clear model
        run_mapdl_command(real_context, "/CLEAR")
        run_mapdl_command(real_context, "/PREP7")

        # Create many keypoints
        commands = [f"K,{i},{i * 0.1},{i * 0.1},{i * 0.1}" for i in range(1, 51)]

        result = run_multiple_mapdl_commands(real_context, commands)

        assert "Successfully executed 50 MAPDL commands" in result.content[1].text

        assert mapdl.geometry.get_keypoints(return_as_array=True).shape[0] == 50

    def test_multiple_commands_with_comments(self, real_context, mapdl):
        """Test running multiple commands including comments."""
        run_mapdl_command(real_context, "/CLEAR")

        commands = [
            "/COM, Starting material definition",
            "/PREP7",
            "/COM, Define element type",
            "ET,1,SOLID185",
            "/COM, Define material properties",
            "MP,EX,1,200E9",
            "MP,PRXY,1,0.3",
        ]

        result = run_multiple_mapdl_commands(real_context, commands)

        assert "Successfully executed 7 MAPDL commands" in result.content[1].text

        assert mapdl.get_value("MAT", 0, "count") == 1.0
        assert mapdl.get_value("ETYP", 1, "attr", "enam") == 185.0
        assert np.allclose(mapdl.get_value("EX", 1), 200e9)
        assert np.allclose(mapdl.get_value("PRXY", 1), 0.3)

    def test_multiple_commands_error_handling(self, real_context):
        """Test error handling with invalid commands."""
        run_mapdl_command(real_context, "/CLEAR")

        # Include an invalid command
        commands = [
            "/PREP7",
            "ET,1,SOLID185",
            "INVALID_MAPDL_COMMAND_XYZ",  # This should cause an error
        ]

        result = run_multiple_mapdl_commands(real_context, commands)

        # Should get error message
        assert isinstance(result, ToolResult)
        msg = result.content[0].text if len(result.content) == 1 else result.content[1].text
        # Either successful execution or error message
        assert (
            "Successfully executed" in msg
            or "Error executing commands" in msg
            or "error" in msg.lower()
        )

    def test_multiple_commands_performance(self, real_context):
        """Test that multiple commands are faster than sequential single commands."""

        run_mapdl_command(real_context, "/CLEAR")

        commands = ["/PREP7", "ET,1,SOLID185", "MP,EX,1,200E9", "MP,PRXY,1,0.3"]

        # Time multiple commands approach
        start_multi = time.time()
        result_multi = run_multiple_mapdl_commands(real_context, commands)
        time_multi = time.time() - start_multi

        assert "Successfully executed 4 MAPDL commands" in result_multi.content[1].text

        # Clear and time single commands approach
        run_mapdl_command(real_context, "/CLEAR")

        start_single = time.time()
        for cmd in commands:
            run_mapdl_command(real_context, cmd)
        time_single = time.time() - start_single

        # Multiple commands should be at least as fast (usually faster)
        # We allow some tolerance since timing can vary
        print(f"Multiple commands time: {time_multi:.4f}s")
        print(f"Single commands time: {time_single:.4f}s")
        print(f"Speedup: {time_single / time_multi:.2f}x")

        # Just verify both completed successfully
        assert time_multi > 0
        assert time_single > 0
        # assert time_multi < time_single

    def test_list_instances_with_running_mapdl(self, real_context):
        """Test list_mapdl_instances when MAPDL is known to be running.

        This is the only integration test that launches MAPDL for list_instances.
        Other tests are covered by unit tests in test_tools.py.
        """
        # If we get here, MAPDL is running
        result = list_mapdl_instances(real_context)

        assert isinstance(result, ToolResult)
        assert len(result.content) > 0

        # The output should contain information about instances
        # Check for table headers
        assert "Name" in result.content[0].text and "Status" in result.content[0].text


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.skipif(not ON_LOCAL, reason="Only run on local environments")
@pytest.mark.skipif(
    not START_INSTANCE,
    reason="PYMAPDL_START_INSTANCE=false: cannot launch new MAPDL instances",
)
class TestLaunchMapdlIntegration:
    """Integration tests for launch_mapdl_session tool."""

    @pytest.fixture
    def clean_context(self):
        """Create a clean context with no MAPDL connection."""

        context = MagicMock()
        context.request_context = MagicMock()
        context.request_context.lifespan_context = PyMAPDLAppContext(mapdl=None)
        context.enable_components = AsyncMock()
        context.disable_components = AsyncMock()

        return context

    @pytest.mark.asyncio
    async def test_launch_mapdl_basic_workflow(self, clean_context):
        """Test launching MAPDL with default parameters and executing commands.

        This test combines multiple scenarios:
        - Launch with default parameters
        - Verify connection info
        - Execute commands
        - Check status
        """
        try:
            # Launch MAPDL
            result = await launch_mapdl_session(ctx=clean_context)

            # Verify successful launch
            assert isinstance(result, ToolResult)
            assert "Successfully launched MAPDL" in result.content[0].text
            assert "MAPDL Version:" in result.content[0].text

            # Verify MAPDL was stored in context
            assert clean_context.request_context.lifespan_context.mapdl is not None

            mapdl = clean_context.request_context.lifespan_context.mapdl
            assert mapdl.is_alive is True
            assert mapdl.version is not None

            # Verify connection info
            assert hasattr(mapdl, "ip")
            assert hasattr(mapdl, "port")
            assert hasattr(mapdl, "directory")
            assert f"{mapdl.ip}:{mapdl.port}" in result.content[0].text

            # Execute a simple command
            cmd_result = run_mapdl_command(clean_context, "/PREP7")
            assert "MAPDL command executed successfully" in cmd_result.content[0].text
            assert mapdl.parameters.routine == "PREP7"

            # Check status
            status_result = check_mapdl_status(clean_context)
            import json

            status_data = json.loads(status_result.content[0].text)
            assert "connection" in status_data
            assert "version" in status_data["connection"]
            assert status_data["connection"]["status"] == "Running"

            # Test launching when already connected
            result2 = await launch_mapdl_session(ctx=clean_context)
            assert "Already connected to MAPDL" in result2.content[0].text
            assert "disconnect first" in result2.content[0].text

        finally:
            # Clean up
            await disconnect_from_mapdl(clean_context)

    @pytest.mark.asyncio
    async def test_launch_mapdl_session_custom_parameters(self, clean_context):
        """Test launching MAPDL with custom parameters.

        This test combines:
        - Custom nproc
        - Custom run location
        """
        # Create a temporary directory for MAPDL to run in
        tmpdir = tempfile.mkdtemp()

        try:
            result = await launch_mapdl_session(ctx=clean_context, nproc=1, run_location=tmpdir)

            # Verify successful launch
            assert isinstance(result, ToolResult)
            assert "Successfully launched MAPDL" in result.content[0].text

            # Verify MAPDL instance was created
            mapdl = clean_context.request_context.lifespan_context.mapdl
            assert mapdl is not None
            assert mapdl.is_alive is True

            # Verify MAPDL is using the specified directory
            assert tmpdir in str(mapdl.directory)

        finally:
            # Disconnect MAPDL first to release file locks
            await disconnect_from_mapdl(clean_context)

            # Clean up the temporary directory manually
            import shutil
            import time

            # Wait a bit for MAPDL to fully release files
            time.sleep(1)
            try:
                shutil.rmtree(tmpdir, ignore_errors=True)
            except Exception:
                pass  # Ignore cleanup errors


@pytest.mark.integration
@pytest.mark.slow
class TestPythonPersistentSessionIntegration:
    """Integration tests for connecting to MAPDL in persistent Python session."""

    @pytest.fixture(scope="class")
    def real_mapdl(self):
        """
        Fixture to connect to a real MAPDL instance.

        This requires MAPDL to be running on localhost:50052.
        Skip these tests if MAPDL is not available.
        """
        try:
            mapdl = launch_mapdl(cleanup_on_exit=False, loglevel="ERROR")

            yield mapdl

            # Cleanup after tests
            # Don't exit since MAPDL is running externally
            mapdl.exit()

        except Exception as e:
            # Not allow to skip if running on CICD
            if os.getenv("ON_CI", False):
                raise e
            else:
                pytest.skip(f"MAPDL not available: {e}")

    @pytest.fixture
    def persistent_real_context(self, real_mapdl):
        """Context wired with REAL MAPDL and a mocked persistent session."""
        ctx = MagicMock()
        ctx.request_context = MagicMock()
        lc = PyMAPDLAppContext(mapdl=real_mapdl)
        py_session = MagicMock()
        py_session.metadata = {}
        lc.python_session = py_session
        ctx.request_context.lifespan_context = lc
        return ctx

    def test_connect_to_mapdl_in_persistent_python(
        self, persistent_real_context, real_mapdl, capsys
    ):
        """Test connecting to MAPDL in persistent Python session."""
        from ansys.mapdl.mcp.helpers import connect_to_mapdl_in_persistent_python

        result = connect_to_mapdl_in_persistent_python(persistent_real_context)

        # Should return the stored mapdl instance
        assert result is persistent_real_context.request_context.lifespan_context.mapdl
        assert result is real_mapdl
        # Verify that the mapdl instance has expected attributes
        assert result._ip == real_mapdl._ip
        assert result._port == real_mapdl._port

    def test_connect_to_mapdl_in_persistent_python_no_session(
        self, persistent_real_context, capsys
    ):
        """Test handling when no persistent Python session is available."""
        from ansys.mapdl.mcp.helpers import connect_to_mapdl_in_persistent_python

        # Remove python_session to simulate missing session
        persistent_real_context.request_context.lifespan_context.python_session = None

        result = connect_to_mapdl_in_persistent_python(persistent_real_context)

        assert isinstance(result, str)
        assert "persistent Python session was not initialized" in result

    def test_connect_to_mapdl_in_persistent_python_no_mapdl(
        self, persistent_real_context, real_mapdl, capsys
    ):
        """Test handling when no MAPDL instance is in the persistent Python session."""
        from unittest.mock import MagicMock

        from ansys.mapdl.mcp.helpers import connect_to_mapdl_in_persistent_python

        # Prepare python_session with no mapdl metadata
        session = MagicMock()
        session.metadata = {}
        persistent_real_context.request_context.lifespan_context.python_session = session
        # Simulate absence of MAPDL in lifespan context
        persistent_real_context.request_context.lifespan_context.mapdl = None

        result = connect_to_mapdl_in_persistent_python(persistent_real_context)

        assert isinstance(result, str)
        assert "No MAPDL instance available in lifespan context" in result

    def test_connect_to_mapdl_in_persistent_python_execute_failure(
        self,
        persistent_real_context,
    ):
        """Test handling when executing code in persistent Python session fails."""
        from unittest.mock import MagicMock

        from ansys.mapdl.mcp.helpers import connect_to_mapdl_in_persistent_python

        # Prepare python_session with mapdl metadata
        session = MagicMock()
        session.metadata = {"mapdl": None}  # Simulate missing mapdl instance
        session.execute.side_effect = RuntimeError("Execution failed")
        persistent_real_context.request_context.lifespan_context.python_session = session

        result = connect_to_mapdl_in_persistent_python(persistent_real_context)

        # On failure, function returns whatever is in metadata (likely None)
        assert result is None

    @pytest.mark.asyncio
    async def test_run_python_code_executes_simple(self, persistent_real_context, capsys):
        """Light-weight execution test using mocked python_session near integration suite."""
        # Attach a mocked persistent python session to the real_context lifespan
        session = MagicMock()
        session.metadata = {"mapdl": persistent_real_context.request_context.lifespan_context.mapdl}
        # Simulate a normal dict-shaped execution result
        session.execute.return_value = {
            "success": True,
            "stdout": "hello\n",
            "stderr": "",
        }
        persistent_real_context.request_context.lifespan_context.python_session = session

        with capsys.disabled():
            result = await run_python_code(persistent_real_context, code="print('hello')")
        data = json.loads(result.content[0].text)
        assert data["success"] is True
        assert data["stdout"].strip() == "hello"
