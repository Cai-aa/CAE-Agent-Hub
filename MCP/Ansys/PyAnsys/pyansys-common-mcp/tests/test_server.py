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

"""Unit tests for server module."""

import argparse
from unittest.mock import MagicMock, patch

import pytest

from ansys.common.mcp.context import PyAnsysBaseAppContext
from ansys.common.mcp.server import PyAnsysBaseMCP


class MockMCP(PyAnsysBaseMCP):
    """Mock implementation of PyAnsysBaseMCP for testing."""

    def __init__(self, *args, **kwargs):
        """Initialize mock MCP server for testing."""
        self.product_startup_called = False
        self.product_cleanup_called = False
        super().__init__(*args, **kwargs)

    def product_startup(self):
        """Mock product startup."""
        self.product_startup_called = True

    def product_cleanup(self):
        """Mock product cleanup."""
        self.product_cleanup_called = True


class TestPyAnsysBaseMCPInitialization:
    """Tests for PyAnsysBaseMCP initialization."""

    def test_mcp_initialization_defaults(self):
        """Test MCP initialization with defaults."""
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):
            mcp = MockMCP()

            assert mcp.python_executable is None
            assert mcp.working_directory is None

    def test_mcp_initialization_with_python_executable(self):
        """Test MCP initialization with custom python executable."""
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):
            executable = "/custom/python"
            mcp = MockMCP(python_executable=executable)

            assert mcp.python_executable == executable

    def test_mcp_initialization_with_working_directory(self):
        """Test MCP initialization with working directory."""
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):
            work_dir = "/tmp/workspace"
            mcp = MockMCP(working_directory=work_dir)

            assert mcp.working_directory == work_dir

    def test_mcp_initialization_stores_parameters(self):
        """Test that MCP initialization stores parameters correctly."""
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):
            executable = "/usr/bin/python3"
            work_dir = "/home/user/project"

            mcp = MockMCP(python_executable=executable, working_directory=work_dir)

            assert mcp.python_executable == executable
            assert mcp.working_directory == work_dir


class TestPyAnsysBaseMCPAbstractMethods:
    """Tests for abstract methods in PyAnsysBaseMCP."""

    def test_product_startup_is_abstract(self):
        """Test that product_startup must be implemented."""
        with pytest.raises(TypeError):

            class IncompleteImpl(PyAnsysBaseMCP):
                def product_cleanup(self):
                    pass

            IncompleteImpl()

    def test_product_cleanup_is_abstract(self):
        """Test that product_cleanup must be implemented."""
        with pytest.raises(TypeError):

            class IncompleteImpl(PyAnsysBaseMCP):
                def product_startup(self):
                    pass

            IncompleteImpl()


class TestPyAnsysBaseMCPCreateContext:
    """Tests for create_context method."""

    def test_create_context_returns_base_context(self):
        """Test that create_context returns PyAnsysBaseAppContext."""
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):
            with patch("ansys.common.mcp.server.PersistentPythonSession"):
                mcp = MockMCP()
                context = mcp.create_context()

                assert isinstance(context, PyAnsysBaseAppContext)

    def test_create_context_creates_python_session(self):
        """Test that create_context creates a PersistentPythonSession."""
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):
            with patch("ansys.common.mcp.server.PersistentPythonSession") as mock_session:
                mcp = MockMCP(python_executable="/custom/python")

                # Verify session is not created before calling create_context
                mock_session.assert_not_called()

                mcp.create_context()

                # Verify PersistentPythonSession was instantiated
                mock_session.assert_called()

    def test_create_context_initializes_empty_history(self):
        """Test that create_context initializes empty command history."""
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):
            with patch("ansys.common.mcp.server.PersistentPythonSession"):
                mcp = MockMCP()
                context = mcp.create_context()

                assert context.command_history == []

    def test_create_context_includes_startup_code(self):
        """Test that startup code is included when creating context."""
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):
            with patch("ansys.common.mcp.server.PersistentPythonSession") as mock_session:
                mcp = MockMCP()
                mcp.create_context()

                # Check that the session was created with startup code
                call_kwargs = mock_session.call_args[1]
                assert "startup_code" in call_kwargs
                startup = call_kwargs["startup_code"]
                assert "matplotlib" in startup
                assert "Agg" in startup
                assert "pyvista" in startup

    def test_create_context_docstring_example(self):
        """Test the example from create_context docstring."""
        # The docstring shows creating a custom context subclass
        # Verify this pattern works

        from dataclasses import dataclass
        from typing import Any, Optional

        @dataclass
        class MockMCPContext(PyAnsysBaseAppContext):
            mock_instance: Optional[Any] = None

        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):

            class MockMCPC(PyAnsysBaseMCP):
                def create_context(self) -> MockMCPContext:
                    return MockMCPContext(
                        python_session=MagicMock(),
                        command_history=[],
                        mock_instance="mock_instance_value",
                    )

                def product_startup(self):
                    pass

                def product_cleanup(self):
                    pass

            mcp = MockMCPC()
            context = mcp.create_context()

            assert isinstance(context, MockMCPContext)
            assert context.mock_instance == "mock_instance_value"
            assert isinstance(context, PyAnsysBaseAppContext)


class TestPyAnsysBaseMCPSessionManagement:
    """Tests for session management methods."""

    def test_start_python_session(self):
        """Test start_python_session method."""
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):
            mock_session = MagicMock()
            mock_session.start.return_value = {"success": True, "stdout": "started"}

            mcp = MockMCP()
            mcp.context = MagicMock()
            mcp.context.python_session = mock_session
            mcp.context.python_executable = None

            with patch("ansys.common.mcp.server.logger") as mock_logger:
                mcp.start_python_session()

                mock_session.start.assert_called_once()
                mock_logger.info.assert_called()

    def test_cleanup_python_session(self):
        """Test cleanup_python_session method."""
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):
            mock_session = MagicMock()
            mock_session.is_running.return_value = True
            mock_session.stop.return_value = {"success": True}

            mcp = MockMCP()
            mcp.context = MagicMock()
            mcp.context.python_session = mock_session

            with patch("ansys.common.mcp.server.logger"):
                mcp.cleanup_python_session()

                mock_session.is_running.assert_called()
                mock_session.stop.assert_called_once()

    def test_cleanup_python_session_not_running(self):
        """Test cleanup_python_session when session is not running."""
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):
            mock_session = MagicMock()
            mock_session.is_running.return_value = False

            mcp = MockMCP()
            mcp.context = MagicMock()
            mcp.context.python_session = mock_session

            with patch("ansys.common.mcp.server.logger"):
                mcp.cleanup_python_session()

                # stop() should not be called if not running
                mock_session.stop.assert_not_called()

    def test_cleanup_python_session_handles_exception(self):
        """Test cleanup_python_session handles exceptions."""
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):
            mock_session = MagicMock()
            mock_session.is_running.return_value = True
            mock_session.stop.side_effect = RuntimeError("Stop failed")

            mcp = MockMCP()
            mcp.context = MagicMock()
            mcp.context.python_session = mock_session

            with patch("ansys.common.mcp.server.logger"):
                # Should not raise an exception
                mcp.cleanup_python_session()


class TestPyAnsysBaseMCPLifespan:
    """Tests for product_lifespan context manager."""

    @pytest.mark.asyncio
    async def test_product_lifespan_basic_flow(self):
        """Test basic flow of product_lifespan."""
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):
            with patch("ansys.common.mcp.server.PersistentPythonSession"):
                with patch("ansys.common.mcp.server.logger"):
                    mcp = MockMCP()

                    mock_server = MagicMock()

                    # Test the lifespan context manager
                    async with mcp.product_lifespan(mock_server) as context:
                        assert mcp.server is mock_server
                        assert mcp.context is not None
                        assert isinstance(context, PyAnsysBaseAppContext)

                    # After exiting, cleanup should be called
                    assert mcp.product_cleanup_called

    @pytest.mark.asyncio
    async def test_product_lifespan_calls_startup(self):
        """Test that product_lifespan calls product_startup."""
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):
            with patch("ansys.common.mcp.server.PersistentPythonSession"):
                with patch("ansys.common.mcp.server.logger"):
                    mcp = MockMCP()

                    mock_server = MagicMock()

                    async with mcp.product_lifespan(mock_server):
                        assert mcp.product_startup_called

    @pytest.mark.asyncio
    async def test_product_lifespan_cleanup_on_exception(self):
        """Test that cleanup is called even if exception occurs."""
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):
            with patch("ansys.common.mcp.server.PersistentPythonSession"):
                with patch("ansys.common.mcp.server.logger"):
                    mcp = MockMCP()

                    mock_server = MagicMock()

                    try:
                        async with mcp.product_lifespan(mock_server):
                            raise ValueError("Test exception")
                    except ValueError:
                        pass

                    # Cleanup should still be called
                    assert mcp.product_cleanup_called


class TestPyAnsysBaseMCPIntegration:
    """Integration tests for PyAnsysBaseMCP."""

    def test_mcp_implementation_complete(self):
        """Test that MockMCP is a complete implementation."""
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):
            mcp = MockMCP(python_executable="/usr/bin/python", working_directory="/tmp/test")

            assert mcp.python_executable == "/usr/bin/python"
            assert mcp.working_directory == "/tmp/test"
            assert callable(mcp.product_startup)
            assert callable(mcp.product_cleanup)
            assert callable(mcp.create_context)


class TestPyAnsysBaseMCPErrors:
    """Tests for error handling in PyAnsysBaseMCP."""

    def test_start_python_session_with_none_context(self):
        """Test start_python_session raises AttributeError with None context."""
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):
            with patch("ansys.common.mcp.server.logger"):
                mcp = MockMCP()
                mcp.context = None

                # Should raise AttributeError when trying to access context.python_executable
                with pytest.raises(AttributeError):
                    mcp.start_python_session()

    def test_cleanup_python_session_with_none_context(self):
        """Test cleanup_python_session raises AttributeError with None context."""
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):
            with patch("ansys.common.mcp.server.logger"):
                mcp = MockMCP()
                mcp.context = None

                # Should raise AttributeError when trying to access context.python_session
                with pytest.raises(AttributeError):
                    mcp.cleanup_python_session()


class TestPyAnsysBaseMCPStartupCode:
    """Tests for startup code generation."""

    def test_startup_code_includes_matplotlib(self):
        """Test startup code configures matplotlib."""
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):
            with patch("ansys.common.mcp.server.PersistentPythonSession") as mock_session:
                mcp = MockMCP()
                mcp.create_context()

                call_kwargs = mock_session.call_args[1]
                startup = call_kwargs["startup_code"]

                assert "matplotlib" in startup
                assert "Agg" in startup

    def test_startup_code_includes_pyvista(self):
        """Test startup code configures pyvista."""
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):
            with patch("ansys.common.mcp.server.PersistentPythonSession") as mock_session:
                mcp = MockMCP()
                mcp.create_context()

                call_kwargs = mock_session.call_args[1]
                startup = call_kwargs["startup_code"]

                assert "pyvista" in startup
                assert "OFF_SCREEN" in startup

    def test_startup_code_includes_plot_functions(self):
        """Test startup code defines plot save functions."""
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):
            with patch("ansys.common.mcp.server.PersistentPythonSession") as mock_session:
                mcp = MockMCP()
                mcp.create_context()

                call_kwargs = mock_session.call_args[1]
                startup = call_kwargs["startup_code"]

                assert "save_plot" in startup
                assert "save_matplotlib_plot" in startup
                assert "base64" in startup


class TestPyAnsysBaseMCPNeedPython:
    """Tests for need_python property and Python session management."""

    def test_need_python_default_is_true(self):
        """Test that need_python defaults to True."""
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):
            mcp = MockMCP()
            assert mcp._need_python is True

    def test_need_python_can_be_set_to_false(self):
        """Test that need_python can be set to False."""
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):
            mcp = MockMCP(need_python=False)
            assert mcp._need_python is False

    def test_need_python_internal_state(self):
        """Test that _need_python internal state is set correctly."""
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):
            # Test default (True)
            mcp_default = MockMCP()
            assert mcp_default._need_python is True

            # Test explicit True
            mcp_true = MockMCP(need_python=True)
            assert mcp_true._need_python is True

            # Test explicit False
            mcp_false = MockMCP(need_python=False)
            assert mcp_false._need_python is False

    @pytest.mark.asyncio
    async def test_lifespan_starts_python_session_when_need_python_true(self):
        """Test that product_lifespan starts Python session when need_python is True."""
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):
            with patch("ansys.common.mcp.server.PersistentPythonSession"):
                with patch("ansys.common.mcp.server.logger"):
                    mcp = MockMCP(need_python=True)

                    mock_server = MagicMock()

                    with patch.object(mcp, "start_python_session") as mock_start:
                        async with mcp.product_lifespan(mock_server):
                            pass

                        # Verify start_python_session was called
                        mock_start.assert_called_once()

    @pytest.mark.asyncio
    async def test_lifespan_skips_python_session_when_need_python_false(self):
        """Test that product_lifespan skips Python session when need_python is False."""
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):
            with patch("ansys.common.mcp.server.PersistentPythonSession"):
                with patch("ansys.common.mcp.server.logger"):
                    mcp = MockMCP(need_python=False)

                    mock_server = MagicMock()

                    with patch.object(mcp, "start_python_session") as mock_start:
                        async with mcp.product_lifespan(mock_server):
                            pass

                        # Verify start_python_session was NOT called
                        mock_start.assert_not_called()

    @pytest.mark.asyncio
    async def test_lifespan_cleans_up_python_session_when_need_python_true(self):
        """Test that product_lifespan cleans up Python session when need_python is True."""
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):
            with patch("ansys.common.mcp.server.PersistentPythonSession"):
                with patch("ansys.common.mcp.server.logger"):
                    mcp = MockMCP(need_python=True)

                    mock_server = MagicMock()

                    with patch.object(mcp, "cleanup_python_session") as mock_cleanup:
                        async with mcp.product_lifespan(mock_server):
                            pass

                        # Verify cleanup_python_session was called
                        mock_cleanup.assert_called_once()

    @pytest.mark.asyncio
    async def test_lifespan_skips_cleanup_python_session_when_need_python_false(self):
        """Test that product_lifespan skips cleanup when need_python is False."""
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):
            with patch("ansys.common.mcp.server.PersistentPythonSession"):
                with patch("ansys.common.mcp.server.logger"):
                    mcp = MockMCP(need_python=False)

                    mock_server = MagicMock()

                    with patch.object(mcp, "cleanup_python_session") as mock_cleanup:
                        async with mcp.product_lifespan(mock_server):
                            pass

                        # Verify cleanup_python_session was NOT called
                        mock_cleanup.assert_not_called()

    @pytest.mark.asyncio
    async def test_lifespan_always_calls_product_startup_regardless_of_need_python(self):
        """Test that product_startup is always called regardless of need_python."""
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):
            with patch("ansys.common.mcp.server.PersistentPythonSession"):
                with patch("ansys.common.mcp.server.logger"):
                    mock_server = MagicMock()

                    # Test with need_python = True
                    mcp_true = MockMCP(need_python=True)
                    async with mcp_true.product_lifespan(mock_server):
                        pass
                    assert mcp_true.product_startup_called

                    # Test with need_python = False
                    mcp_false = MockMCP(need_python=False)
                    async with mcp_false.product_lifespan(mock_server):
                        pass
                    assert mcp_false.product_startup_called


class TestValidatePort:
    """Tests for the _validate_port helper."""

    def test_valid_port(self):
        """Test that a valid port returns an integer."""
        from ansys.common.mcp.server import _validate_port

        assert _validate_port("8080") == 8080
        assert _validate_port("1") == 1
        assert _validate_port("65535") == 65535

    def test_port_zero_raises(self):
        """Test that port 0 raises ArgumentTypeError."""
        import argparse

        from ansys.common.mcp.server import _validate_port

        with pytest.raises(argparse.ArgumentTypeError):
            _validate_port("0")

    def test_port_too_large_raises(self):
        """Test that a port above 65535 raises ArgumentTypeError."""
        import argparse

        from ansys.common.mcp.server import _validate_port

        with pytest.raises(argparse.ArgumentTypeError):
            _validate_port("65536")

    def test_non_integer_raises(self):
        """Test that a non-integer value raises ArgumentTypeError."""
        import argparse

        from ansys.common.mcp.server import _validate_port

        with pytest.raises(argparse.ArgumentTypeError):
            _validate_port("not-a-port")


class TestRunCli:
    """Tests for PyAnsysBaseMCP.run_cli()."""

    def test_run_cli_stdio_default(self):
        """Test that run_cli dispatches to run_async for stdio (default)."""
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):
            mcp = MockMCP()
            with patch.object(mcp, "run_async", return_value=None) as mock_run:
                with patch("ansys.common.mcp.server.asyncio.run") as mock_asyncio:
                    mcp.run_cli([])

                    mock_asyncio.assert_called_once()
                    mock_run.assert_called_once()

    def test_run_cli_explicit_stdio(self):
        """Test that --transport stdio dispatches to run_async."""
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):
            mcp = MockMCP()
            with patch.object(mcp, "run_async", return_value=None) as mock_run:
                with patch("ansys.common.mcp.server.asyncio.run"):
                    mcp.run_cli(["--transport", "stdio"])

                    mock_run.assert_called_once()

    def test_run_cli_http_dispatches_run_http_async(self):
        """Test that --transport http dispatches to run_http_async without middleware."""
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):
            mcp = MockMCP()
            with patch.object(mcp, "run_http_async", return_value=None) as mock_http:
                with patch("ansys.common.mcp.server.asyncio.run"):
                    mcp.run_cli(["--transport", "http"])

                    mock_http.assert_called_once_with(
                        transport="http",
                        host="127.0.0.1",
                        port=8080,
                        middleware=None,
                    )

    def test_run_cli_http_custom_host_and_port(self):
        """Test that custom --http-host and --http-port are forwarded."""
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):
            mcp = MockMCP()
            with patch.object(mcp, "run_http_async", return_value=None) as mock_http:
                with patch("ansys.common.mcp.server.asyncio.run"):
                    mcp.run_cli(
                        ["--transport", "http", "--http-host", "0.0.0.0", "--http-port", "9000"]
                    )

                    mock_http.assert_called_once_with(
                        transport="http",
                        host="0.0.0.0",
                        port=9000,
                        middleware=None,
                    )

    def test_run_cli_http_cors_origins_creates_middleware(self):
        """Test that --cors-origins builds a CORSMiddleware and passes it via middleware."""
        from starlette.middleware.cors import CORSMiddleware

        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):
            mcp = MockMCP()
            with patch.object(mcp, "run_http_async", return_value=None) as mock_http:
                with patch("ansys.common.mcp.server.asyncio.run"):
                    mcp.run_cli(
                        [
                            "--transport",
                            "http",
                            "--cors-origins",
                            "http://localhost:3000,https://myapp.com",
                        ]
                    )

                    mock_http.assert_called_once()
                    call_kwargs = mock_http.call_args.kwargs
                    assert call_kwargs["transport"] == "http"
                    assert call_kwargs["host"] == "127.0.0.1"
                    assert call_kwargs["port"] == 8080
                    mw_list = call_kwargs["middleware"]
                    assert len(mw_list) == 1
                    assert mw_list[0].cls is CORSMiddleware
                    assert mw_list[0].kwargs["allow_origins"] == [
                        "http://localhost:3000",
                        "https://myapp.com",
                    ]

    def test_run_cli_invalid_port_exits(self):
        """Test that an out-of-range port causes SystemExit."""
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):
            mcp = MockMCP()
            with pytest.raises(SystemExit):
                mcp.run_cli(["--transport", "http", "--http-port", "99999"])

    def test_run_cli_invalid_transport_exits(self):
        """Test that an unknown transport value causes SystemExit."""
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):
            mcp = MockMCP()
            with pytest.raises(SystemExit):
                mcp.run_cli(["--transport", "grpc"])

    def test_add_cli_arguments_is_called(self):
        """Test that _add_cli_arguments is invoked with the parser."""
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):
            mcp = MockMCP()
            with patch.object(mcp, "_add_cli_arguments") as mock_add:
                with patch.object(mcp, "run_async", return_value=None):
                    with patch("ansys.common.mcp.server.asyncio.run"):
                        mcp.run_cli([])
                mock_add.assert_called_once()
                assert isinstance(mock_add.call_args[0][0], argparse.ArgumentParser)

    def test_configure_from_cli_is_called_with_namespace(self):
        """Test that _configure_from_cli is invoked with the parsed namespace."""
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):
            mcp = MockMCP()
            with patch.object(mcp, "_configure_from_cli") as mock_cfg:
                with patch.object(mcp, "run_async", return_value=None):
                    with patch("ansys.common.mcp.server.asyncio.run"):
                        mcp.run_cli(["--transport", "stdio"])
                mock_cfg.assert_called_once()
                ns = mock_cfg.call_args[0][0]
                assert isinstance(ns, argparse.Namespace)
                assert ns.transport == "stdio"

    def test_product_specific_argument_injected_via_hook(self):
        """Test end-to-end: a subclass adds --my-flag and reads it in _configure_from_cli."""
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):

            class ExtendedMCP(MockMCP):
                captured_args = None

                def _add_cli_arguments(self, parser):
                    parser.add_argument("--my-flag", dest="my_flag", default="default_value")

                def _configure_from_cli(self, args):
                    ExtendedMCP.captured_args = args

            mcp = ExtendedMCP()
            with patch.object(mcp, "run_async", return_value=None):
                with patch("ansys.common.mcp.server.asyncio.run"):
                    mcp.run_cli(["--my-flag", "custom_value"])

            assert ExtendedMCP.captured_args is not None
            assert ExtendedMCP.captured_args.my_flag == "custom_value"

    def test_default_add_cli_arguments_is_noop(self):
        """Test that the default _add_cli_arguments does nothing."""
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):
            mcp = MockMCP()
            parser = argparse.ArgumentParser()
            before = set(vars(parser.parse_args([])).keys())
            mcp._add_cli_arguments(parser)
            after = set(vars(parser.parse_args([])).keys())
            assert before == after

    def test_default_configure_from_cli_is_noop(self):
        """Test that the default _configure_from_cli does nothing."""
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):
            mcp = MockMCP()
            ns = argparse.Namespace(transport="stdio")
            # Should not raise and should not modify the server
            mcp._configure_from_cli(ns)

    def test_cli_config_initialized_as_empty_dict(self):
        """Test that _cli_config is always initialized as an empty dict."""
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):
            mcp = MockMCP()
            assert mcp._cli_config == {}

    @pytest.mark.asyncio
    async def test_lifespan_always_calls_product_cleanup_regardless_of_need_python(self):
        """Test that product_cleanup is always called regardless of need_python."""
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):
            with patch("ansys.common.mcp.server.PersistentPythonSession"):
                with patch("ansys.common.mcp.server.logger"):
                    mock_server = MagicMock()

                    # Test with need_python = True
                    mcp_true = MockMCP(need_python=True)
                    async with mcp_true.product_lifespan(mock_server):
                        pass
                    assert mcp_true.product_cleanup_called

                    # Test with need_python = False
                    mcp_false = MockMCP(need_python=False)
                    async with mcp_false.product_lifespan(mock_server):
                        pass
                    assert mcp_false.product_cleanup_called

    def test_need_python_can_be_set_in_subclass_init(self):
        """Test that need_python can be configured via constructor parameter in subclass."""
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):

            class CustomMCP(PyAnsysBaseMCP):
                """Custom MCP that disables Python session."""

                def __init__(self, *args, **kwargs):
                    super().__init__(*args, need_python=False, **kwargs)

                def product_startup(self):
                    pass

                def product_cleanup(self):
                    pass

            mcp = CustomMCP()
            assert mcp._need_python is False

    def test_need_python_with_python_executable_parameter(self):
        """Test need_python with python_executable parameter."""
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):
            executable = "/custom/python"
            mcp = MockMCP(python_executable=executable, need_python=False)

            assert mcp._need_python is False
            assert mcp.python_executable == executable

    def test_need_python_as_constructor_parameter_true(self):
        """Test that need_python can be passed as constructor parameter (True)."""
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):
            mcp = MockMCP(need_python=True)
            assert mcp._need_python is True

    def test_need_python_as_constructor_parameter_false(self):
        """Test that need_python can be passed as constructor parameter (False)."""
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):
            mcp = MockMCP(need_python=False)
            assert mcp._need_python is False

    def test_need_python_constructor_parameter_with_other_args(self):
        """Test need_python constructor parameter with other parameters."""
        with patch("ansys.common.mcp.server.FastMCP.__init__", return_value=None):
            executable = "/custom/python"
            work_dir = "/tmp/test"
            mcp = MockMCP(
                python_executable=executable,
                working_directory=work_dir,
                need_python=False,
            )

            assert mcp.python_executable == executable
            assert mcp.working_directory == work_dir
            assert mcp._need_python is False
