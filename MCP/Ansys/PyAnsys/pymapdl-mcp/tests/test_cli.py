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

"""Unit tests for MCP CLI parsing and startup connection behavior."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from ansys.mapdl.mcp import app, launcher
from ansys.mapdl.mcp.server import PyMAPDLMCP


@pytest.mark.unit
def test_main_parses_defaults(monkeypatch):
    """Default args populate mcp._cli_config correctly and doesn't run server."""
    # Prevent actual asyncio.run from running
    with patch.object(asyncio, "run") as mock_run:
        launcher([])
        mock_run.assert_called_once()

    # Ensure mcp._cli_config attached and has defaults
    cfg = getattr(app, "_cli_config", None)
    assert cfg is not None
    assert cfg["transport_type"] == "stdio"
    assert cfg["mapdl_ip"] == "127.0.0.1"
    assert cfg["mapdl_port"] == 50052
    assert cfg["connect_on_startup"] is False
    assert cfg["http_host"] == "127.0.0.1"
    assert cfg["http_port"] == 8080
    assert cfg["cors_origins"] is None


@pytest.mark.unit
def test_main_accepts_http_transport(monkeypatch):
    """Selecting http transport should work now."""
    # Prevent actual asyncio.run from running
    with patch.object(asyncio, "run") as mock_run:
        launcher(["--transport", "http"])
        mock_run.assert_called_once()

    # Ensure mcp._cli_config attached and has http transport
    cfg = getattr(app, "_cli_config", None)
    assert cfg is not None
    assert cfg["transport_type"] == "http"


@pytest.mark.unit
def test_main_invalid_port_raises():
    """Providing an invalid port should cause argparse to exit."""
    from ansys.mapdl.mcp.server import launcher

    with pytest.raises(SystemExit):
        launcher(["--port", "70000"])  # out of 1-65535 should exit


def test_product_startup_attempts_connect_on_startup():
    """When connect_on_startup is True, MCP should attempt to connect to MAPDL."""
    # Prepare a fake Mapdl instance to be returned by Mapdl constructor
    fake_mapdl = MagicMock()
    fake_mapdl.exit = MagicMock()

    # Mock Mapdl to return our fake instance
    with patch("ansys.mapdl.core.Mapdl", return_value=fake_mapdl) as mock_mapdl:
        # Create MCP instance and attach CLI config directly
        mcp = PyMAPDLMCP()
        setattr(
            mcp,
            "_cli_config",
            {
                "transport_type": "stdio",
                "mapdl_ip": "127.0.0.1",
                "mapdl_port": 50052,
                "connect_on_startup": True,
                "http_host": "127.0.0.1",
                "http_port": 8080,
                "cors_origins": None,
            },
        )
        mcp.create_context()
        mcp.product_startup()

        assert mcp.context.connect_on_startup is True

        # Verify Mapdl was instantiated with correct parameters
        mock_mapdl.assert_called_once_with(
            start_instance=False,
            ip="127.0.0.1",
            port=50052,
            cleanup_on_exit=False,
        )

        # Verify MAPDL instance was stored in context
        assert mcp.context.mapdl == fake_mapdl

        # Test cleanup
        mcp.product_cleanup()
        fake_mapdl.exit.assert_called_once()


@pytest.mark.unit
def test_launcher_disables_requires_mapdl_when_no_connect_on_startup():
    """Without --connect-on-startup, the launcher must disable requires_mapdl tools."""
    with (
        patch.object(asyncio, "run"),
        patch.object(app, "disable") as mock_disable,
    ):
        launcher([])

    # requires_mapdl should be in the disabled tags
    disabled_tags = {
        tag for c in mock_disable.call_args_list for tag in (c.kwargs.get("tags") or set())
    }
    assert "requires_mapdl" in disabled_tags


@pytest.mark.unit
def test_launcher_does_not_disable_requires_mapdl_when_connect_on_startup():
    """With --connect-on-startup, the launcher must NOT disable requires_mapdl tools."""
    with (
        patch.object(asyncio, "run"),
        patch.object(app, "disable") as mock_disable,
    ):
        launcher(["--connect-on-startup"])

    disabled_tags = {
        tag for c in mock_disable.call_args_list for tag in (c.kwargs.get("tags") or set())
    }
    assert "requires_mapdl" not in disabled_tags
