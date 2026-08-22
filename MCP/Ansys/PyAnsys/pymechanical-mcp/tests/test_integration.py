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

"""Integration tests for PyMechanical MCP Server.

These tests require a running Mechanical instance and are marked as 'integration'.
Run with: pytest -m integration

To skip integration tests, run: pytest -m "not integration"
"""

import os
from unittest.mock import AsyncMock, MagicMock

import pytest

from ansys.mechanical.mcp.server import PyMechanicalAppContext
from ansys.mechanical.mcp.tools import (
    check_mechanical_status,
    run_python_script,
)

ON_CI = os.getenv("ON_CI", "false").lower() == "true"
ON_LOCAL = os.getenv("ON_LOCAL", "false" if ON_CI else "true").lower() == "true"


def _get_real_mechanical_connection():
    """Create a real Mechanical connection for integration tests.

    Returns
    -------
    tuple
        (mechanical, externally_managed) where externally_managed is True when
        connected to a pre-started gRPC server and False when launched locally.
    """
    from ansys.mechanical.core import connect_to_mechanical, launch_mechanical

    start_instance = os.getenv("PYMECHANICAL_START_INSTANCE", "true").lower() == "true"

    if start_instance:
        # Local launch mode (developer machine with Mechanical installed)
        launch_kwargs = {"cleanup_on_exit": False, "loglevel": "ERROR"}
        transport_mode = os.getenv("PYMECHANICAL_TRANSPORT_MODE")
        if transport_mode:
            launch_kwargs["transport_mode"] = transport_mode
        return launch_mechanical(**launch_kwargs), False

    # CI/remote mode: connect to an already running gRPC server
    ip = os.getenv("PYMECHANICAL_IP", "127.0.0.1")
    port = int(os.getenv("PYMECHANICAL_PORT", "10000"))
    transport_mode = os.getenv("PYMECHANICAL_TRANSPORT_MODE")

    kwargs = {"ip": ip, "port": port, "cleanup_on_exit": False}
    if transport_mode:
        kwargs["transport_mode"] = transport_mode

    return connect_to_mechanical(**kwargs), True


@pytest.fixture
def real_context(mock_mechanical):
    """Module-level context fixture using a mock Mechanical for persistent session tests."""
    context = MagicMock()
    context.request_context = MagicMock()
    # Attach a python_session mock with metadata dict to simulate persistent session
    py_session = MagicMock()
    py_session.metadata = {}
    lc = PyMechanicalAppContext(mechanical=mock_mechanical)
    lc.python_session = py_session
    context.request_context.lifespan_context = lc
    return context


@pytest.fixture(scope="class")
def real_mechanical():
    """Connect to a real Mechanical instance for integration tests.

    This requires Mechanical to be running on localhost:10000.
    Skip these tests if Mechanical is not available locally.
    """
    try:
        mechanical, externally_managed = _get_real_mechanical_connection()

        yield mechanical

        # Only terminate when this test launched the process locally.
        if not externally_managed:
            mechanical.exit()

    except Exception as e:
        # Fail hard in CI, skip locally when Mechanical is unavailable.
        if ON_CI:
            raise e
        else:
            pytest.skip(f"Mechanical not available: {e}")


@pytest.mark.integration
@pytest.mark.slow
class TestMechanicalIntegration:
    """Integration tests that require a real Mechanical connection.

    This class combines all basic Mechanical integration tests to share a single
    Mechanical instance, reducing test execution time.
    """

    @pytest.fixture()
    def mechanical(self, real_mechanical):
        real_mechanical.clear()
        return real_mechanical

    @pytest.fixture
    def real_context(self, real_mechanical):
        """Create a real context with actual Mechanical connection."""
        from unittest.mock import MagicMock

        from ansys.mechanical.mcp.server import PyMechanicalAppContext

        context = MagicMock()
        context.request_context = MagicMock()
        context.request_context.lifespan_context = PyMechanicalAppContext(
            mechanical=real_mechanical
        )

        return context

    def test_real_check_mechanical_status(self, real_context):
        """Test checking Mechanical status with a real connection."""
        import json

        result = check_mechanical_status(real_context)

        assert isinstance(result, str)
        # Check for JSON structure
        data = json.loads(result)
        assert "connection" in data
        assert "version" in data["connection"]

    def test_real_run_script(self, real_context):
        """Test running a Mechanical script with a real connection."""
        # Use a safe script that doesn't affect the model
        script = "print('Hello from Mechanical')"
        result = run_python_script(real_context, script)

        assert isinstance(result, str)
        assert "Script executed successfully" in result


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.skipif(not ON_LOCAL, reason="Only run on local environments")
class TestLaunchMechanicalIntegration:
    """Integration tests for launch_mechanical tool.

    Consolidated to minimize expensive launch_mechanical calls.
    Other test cases are covered by unit tests in test_tools.py.
    """

    @pytest.fixture
    def clean_context(self):
        """Create a clean context with no Mechanical connection."""
        from ansys.mechanical.mcp.server import PyMechanicalAppContext

        context = MagicMock()
        context.enable_components = AsyncMock(return_value=None)
        context.disable_components = AsyncMock(return_value=None)
        context.request_context = MagicMock()
        context.request_context.lifespan_context = PyMechanicalAppContext(mechanical=None)

        return context

    @pytest.mark.asyncio
    async def test_launch_mechanical_basic_workflow(self, clean_context):
        """Test launching Mechanical with default parameters and executing scripts.

        This test combines multiple scenarios:
        - Launch with default parameters
        - Verify connection info
        - Execute scripts
        - Check status
        """
        from ansys.mechanical.mcp.tools import (
            check_mechanical_status,
            disconnect_from_mechanical,
            launch_mechanical,
            run_python_script,
        )

        try:
            # Launch Mechanical
            result = await launch_mechanical(clean_context)

            # Verify successful launch
            assert isinstance(result, str)
            assert "Successfully launched Mechanical" in result
            assert "Version:" in result

            # Verify Mechanical was stored in context
            assert clean_context.request_context.lifespan_context.mechanical is not None

            mechanical = clean_context.request_context.lifespan_context.mechanical
            assert mechanical.is_alive is True
            assert mechanical.version is not None

            # Execute a simple script
            script_result = run_python_script(clean_context, "print('test')")
            assert "Script executed successfully" in script_result

            # Check status
            status_result = check_mechanical_status(clean_context)
            import json

            status_data = json.loads(status_result)
            assert "connection" in status_data
            assert "version" in status_data["connection"]

            # Test launching when already connected
            result2 = await launch_mechanical(clean_context)
            assert "Already connected to a Mechanical instance" in result2
            assert "disconnect first" in result2.lower()

        finally:
            # Clean up
            await disconnect_from_mechanical(clean_context)

    @pytest.mark.asyncio
    async def test_launch_mechanical_custom_parameters(self, clean_context):
        """Test launching Mechanical with custom parameters.

        This test combines:
        - Custom port
        - Custom version
        """

        from ansys.mechanical.mcp.tools import (
            disconnect_from_mechanical,
            launch_mechanical,
        )

        try:
            result = await launch_mechanical(clean_context, port=10050)

            # Verify successful launch
            assert isinstance(result, str)
            assert "Successfully launched Mechanical" in result

            # Verify Mechanical instance was created
            mechanical = clean_context.request_context.lifespan_context.mechanical
            assert mechanical is not None
            assert mechanical.is_alive is True

        finally:
            # Disconnect Mechanical
            await disconnect_from_mechanical(clean_context)


@pytest.mark.integration
@pytest.mark.slow
class TestPythonPersistentSessionIntegration:
    """Integration tests for connecting to Mechanical in persistent Python session."""

    @pytest.fixture
    def persistent_real_context(self, real_mechanical):
        """Context wired with REAL Mechanical and a mocked persistent session."""
        ctx = MagicMock()
        ctx.request_context = MagicMock()
        lc = PyMechanicalAppContext(mechanical=real_mechanical)
        py_session = MagicMock()
        py_session.metadata = {}
        lc.python_session = py_session
        ctx.request_context.lifespan_context = lc
        return ctx

    def test_run_python_code_executes_simple(self, persistent_real_context, capsys):
        """Light-weight execution test using mocked python_session near integration suite."""
        import json
        from unittest.mock import MagicMock

        from ansys.mechanical.mcp.tools import run_python_code

        # Attach a mocked persistent python session to the real_context lifespan
        session = MagicMock()
        session.metadata = {
            "mechanical": persistent_real_context.request_context.lifespan_context.mechanical
        }
        # Simulate a normal dict-shaped execution result
        session.execute.return_value = {
            "success": True,
            "stdout": "hello\n",
            "stderr": "",
        }
        persistent_real_context.request_context.lifespan_context.python_session = session

        with capsys.disabled():
            result = run_python_code(persistent_real_context, code="print('hello')")
        data = json.loads(result)
        assert data["success"] is True
        assert data["stdout"].strip() == "hello"
