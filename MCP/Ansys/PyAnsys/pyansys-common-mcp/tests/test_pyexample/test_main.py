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

"""Tests for the PyExample MCP server entry point (``__main__.py``)."""

from unittest.mock import patch

from pyexample_mcp import app
from pyexample_mcp.__main__ import main
import pytest


class TestMain:
    """Tests for the ``main()`` entry point."""

    def test_main_returns_zero(self):
        """Test that main() returns 0 after a successful run."""
        with patch.object(app, "run_cli") as mock_run_cli:
            result = main([])
            assert result == 0
            mock_run_cli.assert_called_once_with([])

    def test_main_passes_argv_to_run_cli(self):
        """Test that main() forwards its argv argument to run_cli()."""
        argv = ["--transport", "http", "--http-port", "9000"]
        with patch.object(app, "run_cli") as mock_run_cli:
            main(argv)
            mock_run_cli.assert_called_once_with(argv)

    def test_main_passes_none_argv_by_default(self):
        """Test that main() passes None to run_cli() when called without arguments."""
        with patch.object(app, "run_cli") as mock_run_cli:
            main()
            mock_run_cli.assert_called_once_with(None)

    def test_main_sets_up_logging(self):
        """Test that main() calls setup_logging before run_cli()."""
        call_order = []

        with patch(
            "pyexample_mcp.__main__.setup_logging",
            side_effect=lambda **_: call_order.append("logging"),
        ) as mock_logging:
            with patch.object(app, "run_cli", side_effect=lambda _: call_order.append("run_cli")):
                main([])

        mock_logging.assert_called_once_with(level="INFO")
        assert call_order == ["logging", "run_cli"]


class TestMainCliDispatch:
    """Tests verifying that CLI arguments reach run_cli() correctly via main()."""

    def test_stdio_transport(self):
        """Test that stdio transport args are forwarded."""
        with patch.object(app, "run_async", return_value=None) as mock_run:
            with patch("ansys.common.mcp.server.asyncio.run"):
                main(["--transport", "stdio"])
                mock_run.assert_called_once()

    def test_http_transport_default_host_and_port(self):
        """Test that HTTP transport uses default host and port when not specified."""
        with patch.object(app, "run_http_async", return_value=None) as mock_http:
            with patch("ansys.common.mcp.server.asyncio.run"):
                main(["--transport", "http"])
                mock_http.assert_called_once_with(
                    transport="http",
                    host="127.0.0.1",
                    port=8080,
                    middleware=None,
                )

    def test_http_transport_custom_host_and_port(self):
        """Test that custom --http-host and --http-port are forwarded."""
        with patch.object(app, "run_http_async", return_value=None) as mock_http:
            with patch("ansys.common.mcp.server.asyncio.run"):
                main(["--transport", "http", "--http-host", "0.0.0.0", "--http-port", "9000"])
                mock_http.assert_called_once_with(
                    transport="http",
                    host="0.0.0.0",
                    port=9000,
                    middleware=None,
                )

    def test_http_transport_cors_origins(self):
        """Test that --cors-origins creates a CORSMiddleware passed via middleware."""
        from starlette.middleware.cors import CORSMiddleware

        with patch.object(app, "run_http_async", return_value=None) as mock_http:
            with patch("ansys.common.mcp.server.asyncio.run"):
                main(
                    [
                        "--transport",
                        "http",
                        "--cors-origins",
                        "http://localhost:3000,https://myapp.com",
                    ]
                )
                mock_http.assert_called_once()
                mw_list = mock_http.call_args.kwargs["middleware"]
                assert len(mw_list) == 1
                assert mw_list[0].cls is CORSMiddleware
                assert mw_list[0].kwargs["allow_origins"] == [
                    "http://localhost:3000",
                    "https://myapp.com",
                ]

    def test_invalid_port_causes_system_exit(self):
        """Test that an out-of-range port causes SystemExit."""
        with pytest.raises(SystemExit):
            main(["--transport", "http", "--http-port", "99999"])

    def test_unknown_transport_causes_system_exit(self):
        """Test that an unknown transport value causes SystemExit."""
        with pytest.raises(SystemExit):
            main(["--transport", "grpc"])


class TestPyExampleCliHooks:
    """Unit tests for PyExampleMCP._add_cli_arguments and _configure_from_cli."""

    def test_add_cli_arguments_registers_ip(self):
        """Test that --ip is registered and stores value in example_ip."""
        with patch("ansys.common.mcp.server.asyncio.run"):
            main(["--ip", "10.0.0.5"])
        assert app._cli_config["example_ip"] == "10.0.0.5"

    def test_add_cli_arguments_registers_port(self):
        """Test that --port is registered and stored as an integer."""
        with patch("ansys.common.mcp.server.asyncio.run"):
            main(["--port", "50099"])
        assert app._cli_config["example_port"] == 50099

    def test_add_cli_arguments_registers_connect_on_startup_flag(self):
        """Test that --connect-on-startup sets the flag to True."""
        with patch("ansys.common.mcp.server.asyncio.run"):
            main(["--connect-on-startup"])
        assert app._cli_config["connect_on_startup"] is True

    def test_configure_from_cli_defaults(self):
        """Test that _configure_from_cli stores default values when no product args given."""
        with patch("ansys.common.mcp.server.asyncio.run"):
            main([])
        assert app._cli_config == {
            "example_ip": "127.0.0.1",
            "example_port": 50052,
            "connect_on_startup": False,
        }

    def test_configure_from_cli_all_product_args(self):
        """Test that all product-specific args are stored correctly in _cli_config."""
        with patch("ansys.common.mcp.server.asyncio.run"):
            main(["--ip", "192.168.1.1", "--port", "12345", "--connect-on-startup"])
        assert app._cli_config == {
            "example_ip": "192.168.1.1",
            "example_port": 12345,
            "connect_on_startup": True,
        }
