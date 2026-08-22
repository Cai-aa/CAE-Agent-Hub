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

"""Tests for main entry point functionality."""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.unit
def test_main_function_exists():
    """Test that main function is defined."""
    from ansys.mapdl.mcp.server import launcher

    assert callable(launcher)


@pytest.mark.unit
def test_main_entry_point():
    """Test that main entry point can be called."""
    import asyncio

    from ansys.mapdl.mcp.server import app, launcher

    with patch.object(asyncio, "run") as mock_run:
        with patch.object(app, "run_stdio_async", new_callable=AsyncMock):
            # Mock asyncio.run to avoid actually starting the server
            launcher([])

            # Verify that asyncio.run was called with app.run_stdio_async()
            mock_run.assert_called_once()


@pytest.mark.unit
def test_main_with_http_transport():
    """Test that main entry point can be called with HTTP transport."""
    import asyncio

    from ansys.mapdl.mcp.server import app, launcher

    with patch.object(asyncio, "run") as mock_run:
        with patch.object(app, "run_http_async", new_callable=AsyncMock):
            # Mock asyncio.run to avoid actually starting the server
            launcher(["--transport", "http"])

            # Verify that asyncio.run was called
            mock_run.assert_called_once()


@pytest.mark.unit
def test_main_http_with_custom_host_port():
    """Test HTTP transport with custom host and port."""
    import asyncio

    from ansys.mapdl.mcp.server import app, launcher

    with patch.object(asyncio, "run") as mock_run:
        with patch.object(app, "run_http_async", new_callable=AsyncMock):
            launcher(["--transport", "http", "--http-host", "0.0.0.0", "--http-port", "9000"])

            # Verify that asyncio.run was called
            mock_run.assert_called_once()

            # Verify the CLI config was set correctly
            assert hasattr(app, "_cli_config")
            assert app._cli_config["http_host"] == "0.0.0.0"
            assert app._cli_config["http_port"] == 9000


@pytest.mark.unit
def test_main_with_cors_origins():
    """Test HTTP transport with CORS origins."""
    import asyncio

    from ansys.mapdl.mcp.server import app, launcher

    with patch.object(asyncio, "run"):
        with patch.object(app, "run_http_async", new_callable=AsyncMock):
            launcher(
                [
                    "--transport",
                    "http",
                    "--cors-origins",
                    "http://localhost:3000,https://example.com",
                ]
            )

            # Verify CORS origins were parsed correctly
            assert hasattr(app, "_cli_config")
            assert app._cli_config["cors_origins"] == [
                "http://localhost:3000",
                "https://example.com",
            ]


@pytest.mark.unit
def test_mapdl_args_work_with_http():
    """Test that MAPDL connection arguments work with HTTP transport."""
    import asyncio

    from ansys.mapdl.mcp.server import app, launcher

    with patch.object(asyncio, "run"):
        with patch.object(app, "run_http_async", new_callable=AsyncMock):
            launcher(
                [
                    "--transport",
                    "http",
                    "--ip",
                    "192.168.1.100",
                    "--port",
                    "50053",
                    "--connect-on-startup",
                ]
            )

            # Verify MAPDL args were set correctly
            assert hasattr(app, "_cli_config")
            assert app._cli_config["mapdl_ip"] == "192.168.1.100"
            assert app._cli_config["mapdl_port"] == 50053
            assert app._cli_config["connect_on_startup"] is True


@pytest.mark.unit
def test_module_main_guard():
    """Test that the module can be imported without running main."""
    # This test verifies that importing the module doesn't automatically
    # start the server (due to if __name__ == "__main__" guard)
    import ansys.mapdl.mcp

    # If we got here without hanging, the guard works correctly
    assert hasattr(ansys.mapdl.mcp, "launcher")
