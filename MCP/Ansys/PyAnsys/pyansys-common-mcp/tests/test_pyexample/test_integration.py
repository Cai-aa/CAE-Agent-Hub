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

"""Integration tests for PyExample MCP server.

These tests validate the complete MCP server implementation and serve as
end-to-end tests for the pyansys-common-mcp library.
"""

from unittest.mock import MagicMock, patch

from pyexample_mcp import PyExampleContext, PyExampleMCP, app
from pyexample_mcp.mock_pyexample import PyExample
import pytest


class TestPyExampleMCPInitialization:
    """Tests for PyExampleMCP initialization."""

    def test_initialization_defaults(self):
        """Test MCP initialization with default parameters."""
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):
            mcp = PyExampleMCP()

            assert mcp.launch_mode == "local"
            assert mcp.timeout == 60

    def test_initialization_custom_parameters(self):
        """Test MCP initialization with custom parameters."""
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):
            mcp = PyExampleMCP(launch_mode="remote", timeout=120)

            assert mcp.launch_mode == "remote"
            assert mcp.timeout == 120

    def test_initialization_with_python_executable(self):
        """Test MCP initialization with custom Python executable."""
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):
            mcp = PyExampleMCP(python_executable="/custom/python")

            assert mcp.python_executable == "/custom/python"


class TestPyExampleMCPContext:
    """Tests for PyExampleContext creation."""

    def test_create_context(self):
        """Test create_context returns PyExampleContext."""
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):
            with patch("ansys.common.mcp.server.PersistentPythonSession"):
                mcp = PyExampleMCP()
                context = mcp.create_context()

                assert isinstance(context, PyExampleContext)
                assert context.example_instance is None
                assert context.simulation_results == {}

    def test_create_context_includes_startup_code(self):
        """Test that context creation includes PyExample-specific startup code."""
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):
            with patch("pyexample_mcp.server.PersistentPythonSession") as mock_session:
                mcp = PyExampleMCP()
                mcp.create_context()

                call_kwargs = mock_session.call_args[1]
                startup = call_kwargs["startup_code"]

                assert "import numpy" in startup
                assert "import pandas" in startup
                assert "PyExample MCP session initialized" in startup


class TestPyExampleMCPProductLifecycle:
    """Tests for product_startup and product_cleanup."""

    def test_product_startup(self):
        """Test product_startup launches PyExample instance."""
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):
            with patch("ansys.common.mcp.server.PersistentPythonSession"):
                mcp = PyExampleMCP(launch_mode="local", timeout=30)
                mcp.context = PyExampleContext(
                    python_session=MagicMock(),
                    command_history=[],
                )

                mcp.product_startup()

                assert mcp.context.example_instance is not None
                assert isinstance(mcp.context.example_instance, PyExample)
                assert mcp.context.example_instance.mode == "local"
                assert mcp.context.example_instance.timeout == 30

    def test_product_cleanup(self):
        """Test product_cleanup closes PyExample instance."""
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):
            with patch("ansys.common.mcp.server.PersistentPythonSession"):
                mcp = PyExampleMCP()
                mcp.context = PyExampleContext(
                    python_session=MagicMock(),
                    command_history=[],
                )

                # Start and then cleanup
                mcp.product_startup()
                assert mcp.context.example_instance.is_connected is True

                mcp.product_cleanup()
                assert mcp.context.example_instance.is_connected is False

    def test_product_cleanup_handles_none_instance(self):
        """Test product_cleanup handles None instance gracefully."""
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):
            with patch("ansys.common.mcp.server.PersistentPythonSession"):
                mcp = PyExampleMCP()
                mcp.context = PyExampleContext(
                    python_session=MagicMock(),
                    command_history=[],
                )

                # Should not raise an error
                mcp.product_cleanup()


class TestPyExampleMCPLifespan:
    """Tests for the complete lifespan context manager."""

    @pytest.mark.asyncio
    async def test_lifespan_complete_flow(self):
        """Test complete lifespan from startup to cleanup."""
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):
            with patch("ansys.common.mcp.server.PersistentPythonSession"):
                with patch("ansys.common.mcp.server.logger"):
                    mcp = PyExampleMCP(launch_mode="grpc", timeout=90)

                    mock_server = MagicMock()

                    async with mcp.product_lifespan(mock_server) as context:
                        # Verify context is created
                        assert isinstance(context, PyExampleContext)

                        # Verify PyExample instance is launched
                        assert context.example_instance is not None
                        assert context.example_instance.mode == "grpc"
                        assert context.example_instance.timeout == 90
                        assert context.example_instance.is_connected is True

                    # After exiting, instance should be closed
                    assert context.example_instance.is_connected is False

    @pytest.mark.asyncio
    async def test_lifespan_cleanup_on_exception(self):
        """Test that cleanup happens even if exception occurs."""
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):
            with patch("ansys.common.mcp.server.PersistentPythonSession"):
                with patch("ansys.common.mcp.server.logger"):
                    mcp = PyExampleMCP()
                    mock_server = MagicMock()

                    try:
                        async with mcp.product_lifespan(mock_server) as context:
                            # Store reference to check cleanup
                            instance = context.example_instance
                            assert instance.is_connected is True
                            raise ValueError("Test exception")
                    except ValueError:
                        pass

                    # Instance should still be cleaned up
                    assert instance.is_connected is False


class TestPyExampleMCPAppInstance:
    """Tests for the global app instance."""

    def test_app_instance_exists(self):
        """Test that app instance is created."""
        assert app is not None
        assert isinstance(app, PyExampleMCP)

    def test_app_instance_name(self):
        """Test app instance has correct name."""
        # Access the name directly from the app
        assert app.name == "pyexample-mcp"


class TestPyExampleMCPEndToEnd:
    """End-to-end integration tests.

    These tests validate the complete workflow including:
    - Server initialization
    - PyExample instance management
    - Tool registration and execution
    - Context state management
    - Cleanup and shutdown
    """

    @pytest.mark.asyncio
    async def test_end_to_end_model_creation_workflow(self):
        """Test complete workflow: init -> create model -> cleanup."""
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):
            with patch("ansys.common.mcp.server.PersistentPythonSession"):
                with patch("ansys.common.mcp.server.logger"):
                    mcp = PyExampleMCP()
                    mock_server = MagicMock()

                    async with mcp.product_lifespan(mock_server) as context:
                        # Create a model using the PyExample instance
                        model = context.example_instance.create_model(
                            "test_model",
                            model_type="structural",
                            length=10,
                        )

                        assert model.name == "test_model"
                        assert model.model_type == "structural"
                        assert context.example_instance.active_model == "test_model"

    @pytest.mark.asyncio
    async def test_end_to_end_solve_workflow(self):
        """Test complete workflow: init -> create -> solve -> cleanup."""
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):
            with patch("ansys.common.mcp.server.PersistentPythonSession"):
                with patch("ansys.common.mcp.server.logger"):
                    mcp = PyExampleMCP()
                    mock_server = MagicMock()

                    async with mcp.product_lifespan(mock_server) as context:
                        # Create and solve a model
                        context.example_instance.create_model("beam")
                        result = context.example_instance.solve("beam")

                        assert result.model_name == "beam"
                        assert result.status == "converged"
                        assert result.convergence_iterations > 0
                        assert result.max_stress > 0

    @pytest.mark.asyncio
    async def test_end_to_end_command_execution(self):
        """Test complete workflow using run_command interface."""
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):
            with patch("ansys.common.mcp.server.PersistentPythonSession"):
                with patch("ansys.common.mcp.server.logger"):
                    mcp = PyExampleMCP()
                    mock_server = MagicMock()

                    async with mcp.product_lifespan(mock_server) as context:
                        # Execute commands
                        result1 = context.example_instance.run_command(
                            "CREATE MODEL plate TYPE thermal"
                        )
                        assert "created successfully" in result1

                        result2 = context.example_instance.run_command("SOLVE MODEL plate")
                        assert "solved successfully" in result2

                        result3 = context.example_instance.run_command("LIST MODELS")
                        assert "plate" in result3

    @pytest.mark.asyncio
    async def test_end_to_end_multiple_models(self):
        """Test workflow with multiple models."""
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):
            with patch("ansys.common.mcp.server.PersistentPythonSession"):
                with patch("ansys.common.mcp.server.logger"):
                    mcp = PyExampleMCP()
                    mock_server = MagicMock()

                    async with mcp.product_lifespan(mock_server) as context:
                        # Create multiple models
                        models = []
                        for i in range(3):
                            model = context.example_instance.create_model(
                                f"model_{i}",
                                model_type="default",
                            )
                            models.append(model)

                        # Verify all models exist
                        all_models = context.example_instance.list_models()
                        assert len(all_models) == 3

                        # Solve each model
                        for i in range(3):
                            result = context.example_instance.solve(f"model_{i}")
                            assert result.status == "converged"


class TestPyExampleMCPErrorHandling:
    """Tests for error handling in PyExampleMCP."""

    def test_product_startup_with_invalid_mode(self):
        """Test that product_startup handles initialization gracefully."""
        # The mock doesn't validate mode, but we test the flow
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):
            with patch("ansys.common.mcp.server.PersistentPythonSession"):
                mcp = PyExampleMCP(launch_mode="invalid_mode")
                mcp.context = PyExampleContext(
                    python_session=MagicMock(),
                    command_history=[],
                )

                # Should not raise - mock accepts any mode
                mcp.product_startup()
                assert mcp.context.example_instance is not None
