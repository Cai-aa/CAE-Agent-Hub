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

"""Unit tests for MCP CLI parsing and startup connection behavior."""

import asyncio
from unittest.mock import MagicMock, Mock, patch

import pytest


@pytest.mark.unit
def test_main_parses_defaults(monkeypatch):
    """Default args populate mcp._cli_config correctly and doesn't run server."""
    from ansys.mechanical.mcp import app as package_mcp
    from ansys.mechanical.mcp.server import launcher

    # Prevent actual asyncio.run from running
    with patch.object(asyncio, "run") as mock_run:
        with patch.object(package_mcp, "run_stdio_async", new=Mock(return_value=object())):
            launcher([])
            mock_run.assert_called_once()

    # Ensure mcp._cli_config attached and has defaults
    cfg = getattr(package_mcp, "_cli_config", None)
    assert cfg is not None
    assert cfg["transport_type"] == "stdio"
    assert cfg["mechanical_ip"] == "127.0.0.1"
    assert cfg["mechanical_port"] == 10000
    assert cfg["connect_on_startup"] is False
    assert cfg["static_tools"] is False
    assert cfg["http_host"] == "127.0.0.1"
    assert cfg["http_port"] == 8080
    assert cfg["cors_origins"] is None


@pytest.mark.unit
def test_main_accepts_http_transport(monkeypatch):
    """Selecting http transport should work now."""
    from ansys.mechanical.mcp import app as package_mcp
    from ansys.mechanical.mcp.server import launcher

    # Prevent actual asyncio.run from running
    with patch.object(asyncio, "run") as mock_run:
        with patch.object(package_mcp, "run_http_async", new=Mock(return_value=object())):
            launcher(["--transport", "http"])
            mock_run.assert_called_once()

    # Ensure mcp._cli_config attached and has http transport
    cfg = getattr(package_mcp, "_cli_config", None)
    assert cfg is not None
    assert cfg["transport_type"] == "http"


@pytest.mark.unit
def test_main_invalid_port_raises():
    """Providing an invalid port should cause argparse to exit."""
    from ansys.mechanical.mcp.server import launcher

    with pytest.raises(SystemExit):
        launcher(["--port", "70000"])  # out of 1-65535 should exit


@pytest.mark.unit
def test_main_accepts_static_tools_flag():
    """Test that --static-tools is captured in CLI config."""
    from ansys.mechanical.mcp import app as package_mcp
    from ansys.mechanical.mcp.server import launcher

    with (
        patch.object(asyncio, "run"),
        patch.object(package_mcp, "run_stdio_async", new=Mock(return_value=object())),
    ):
        launcher(["--static-tools"])

    cfg = getattr(package_mcp, "_cli_config", None)
    assert cfg is not None
    assert cfg["static_tools"] is True


@pytest.mark.unit
def test_launcher_disables_requires_mechanical_tag_by_default():
    """Default startup should still hide Mechanical-only tools (unchanged behavior)."""
    from ansys.mechanical.mcp.server import app, launcher

    with (
        patch.object(app, "disable") as mock_disable,
        patch.object(asyncio, "run"),
        patch.object(app, "run_stdio_async", new=Mock(return_value=object())),
    ):
        launcher([])

    disable_calls = [c.kwargs.get("tags") for c in mock_disable.call_args_list]
    assert {"requires_mechanical"} in disable_calls


@pytest.mark.unit
def test_launcher_keeps_tools_visible_with_static_tools_flag():
    """Opt-in --static-tools should skip hiding Mechanical-only tools."""
    from ansys.mechanical.mcp.server import app, launcher

    with (
        patch.object(app, "disable") as mock_disable,
        patch.object(asyncio, "run"),
        patch.object(app, "run_stdio_async", new=Mock(return_value=object())),
    ):
        launcher(["--static-tools"])

    disable_calls = [c.kwargs.get("tags") for c in mock_disable.call_args_list]
    assert {"requires_mechanical"} not in disable_calls


@pytest.mark.unit
def test_launcher_keeps_tools_visible_with_connect_on_startup():
    """--connect-on-startup should also skip hiding Mechanical-only tools (existing behavior).

    Note: ``asyncio.run`` is patched out, so the lifespan (and thus the actual
    Mechanical connection attempt in ``product_startup``) never executes here.
    This test only verifies the synchronous ``launcher()``-level disable logic.
    """
    from ansys.mechanical.mcp.server import app, launcher

    with (
        patch.object(app, "disable") as mock_disable,
        patch.object(asyncio, "run"),
        patch.object(app, "run_stdio_async", new=Mock(return_value=object())),
    ):
        launcher(["--connect-on-startup"])

    disable_calls = [c.kwargs.get("tags") for c in mock_disable.call_args_list]
    assert {"requires_mechanical"} not in disable_calls


def test_product_startup_attempts_connect_on_startup():
    """When connect_on_startup is True, MCP should attempt to connect to Mechanical."""
    from ansys.mechanical.mcp.server import PyMechanicalMCP

    # Prepare a fake Mechanical instance to be returned by connect_to_mechanical
    fake_mechanical = MagicMock()
    fake_mechanical.exit = MagicMock()

    # Mock connect_to_mechanical to return our fake instance
    with patch(
        "ansys.mechanical.core.connect_to_mechanical", return_value=fake_mechanical
    ) as mock_connect:
        # Create MCP instance and attach CLI config directly
        mcp = PyMechanicalMCP()
        setattr(
            mcp,
            "_cli_config",
            {
                "transport_type": "stdio",
                "mechanical_ip": "127.0.0.1",
                "mechanical_port": 10000,
                "connect_on_startup": True,
                "http_host": "127.0.0.1",
                "http_port": 8080,
                "cors_origins": None,
                "grpc_transport_mode": None,
                "certs_dir": None,
            },
        )
        mcp.create_context()
        mcp.product_startup()

        # Verify connect_to_mechanical was called with correct parameters.
        # resolve_transport_mode may add transport_mode depending on platform,
        # so we check the essential kwargs rather than an exact match.
        mock_connect.assert_called_once()
        call_kwargs = mock_connect.call_args[1]
        assert call_kwargs["ip"] == "127.0.0.1"
        assert call_kwargs["port"] == 10000
        assert call_kwargs["cleanup_on_exit"] is False

        # Verify Mechanical instance was stored in context
        assert mcp.context.mechanical == fake_mechanical

        # Test cleanup
        mcp.product_cleanup()
        fake_mechanical.exit.assert_called_once()
