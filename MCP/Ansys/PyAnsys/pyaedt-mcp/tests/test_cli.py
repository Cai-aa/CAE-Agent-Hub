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
import importlib
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.unit
def test_main_parses_defaults(monkeypatch):
    """Default args populate mcp._cli_config correctly and doesn't run server."""
    from ansys.aedt.mcp import app as package_mcp
    from ansys.aedt.mcp.server import launcher

    # Prevent actual asyncio.run from running
    with patch.object(asyncio, "run") as mock_run:
        launcher([])
        mock_run.assert_called_once()

    # Ensure mcp._cli_config attached and has defaults
    cfg = getattr(package_mcp, "_cli_config", None)
    assert cfg is not None
    assert cfg["transport_type"] == "stdio"
    assert cfg["aedt_machine"] == "localhost"
    assert cfg["aedt_port"] == 50051
    assert cfg["connect_on_startup"] is False
    assert cfg["include_context_tools"] is False
    assert cfg["dynamic_tool_discovery"] is False
    assert cfg["http_host"] == "127.0.0.1"
    assert cfg["http_port"] == 8080
    assert cfg["cors_origins"] is None


@pytest.mark.unit
def test_main_accepts_http_transport(monkeypatch):
    """Selecting http transport should work."""
    from ansys.aedt.mcp import app as package_mcp
    from ansys.aedt.mcp.server import launcher

    # Prevent actual asyncio.run from running
    with patch.object(asyncio, "run") as mock_run:
        launcher(["--transport", "http"])
        mock_run.assert_called_once()

    # Ensure mcp._cli_config attached and has http transport
    cfg = getattr(package_mcp, "_cli_config", None)
    assert cfg is not None
    assert cfg["transport_type"] == "http"


@pytest.mark.unit
def test_main_invalid_port_raises():
    """Providing an invalid port should cause argparse to exit."""
    from ansys.aedt.mcp.server import launcher

    with pytest.raises(SystemExit):
        launcher(["--port", "70000"])  # out of 1-65535 should exit


@pytest.mark.unit
def test_main_accepts_custom_machine():
    """Test that custom machine name is accepted."""
    from ansys.aedt.mcp import app as package_mcp
    from ansys.aedt.mcp.server import launcher

    with patch.object(asyncio, "run"):
        launcher(["--machine", "remote-server.example.com"])

    cfg = getattr(package_mcp, "_cli_config", None)
    assert cfg is not None
    assert cfg["aedt_machine"] == "remote-server.example.com"


@pytest.mark.unit
def test_main_accepts_aedt_version():
    """Test that AEDT version is accepted."""
    from ansys.aedt.mcp import app as package_mcp
    from ansys.aedt.mcp.server import launcher

    with patch.object(asyncio, "run"):
        launcher(["--version", "2026.1"])

    cfg = getattr(package_mcp, "_cli_config", None)
    assert cfg is not None
    assert cfg["aedt_version"] == "2026.1"


@pytest.mark.unit
def test_main_accepts_include_context_flag():
    """Test that include-context is captured in CLI config."""
    from ansys.aedt.mcp import app as package_mcp
    from ansys.aedt.mcp.server import launcher

    with patch.object(asyncio, "run"):
        launcher(["--include-context"])

    cfg = getattr(package_mcp, "_cli_config", None)
    assert cfg is not None
    assert cfg["include_context_tools"] is True


@pytest.mark.unit
def test_main_accepts_dynamic_tool_discovery_flag():
    """Test that dynamic tool discovery is captured in CLI config."""
    from ansys.aedt.mcp import app as package_mcp
    from ansys.aedt.mcp.server import launcher

    with patch.object(asyncio, "run"):
        launcher(["--dynamic-tool-discovery"])

    cfg = getattr(package_mcp, "_cli_config", None)
    assert cfg is not None
    assert cfg["dynamic_tool_discovery"] is True


@pytest.mark.unit
def test_launcher_disables_only_context_tag_by_default(monkeypatch):
    """Default startup should keep the full AEDT tool surface visible."""
    from ansys.aedt.mcp.server import app, launcher

    imported_modules = []
    real_import_module = importlib.import_module

    def tracking_import(name, package=None):
        imported_modules.append(name)
        return real_import_module(name, package)

    monkeypatch.setattr(importlib, "import_module", tracking_import)

    with (
        patch.object(app, "disable") as mock_disable,
        patch.object(app, "enable") as mock_enable,
    ):
        with patch.object(asyncio, "run"):
            launcher([])

    assert "ansys.aedt.mcp.prompts" in imported_modules
    assert "ansys.aedt.mcp.tools" in imported_modules
    assert "ansys.aedt.mcp.contexts" in imported_modules
    disable_calls = [c.kwargs.get("tags") for c in mock_disable.call_args_list]
    assert {"pyaedt_context"} in disable_calls
    assert {"requires_aedt"} not in disable_calls
    mock_enable.assert_not_called()


@pytest.mark.unit
def test_launcher_enables_context_tag_when_requested(monkeypatch):
    """The include-context flag should enable the pyaedt_context tool tag."""
    from ansys.aedt.mcp.server import app, launcher

    imported_modules = []
    real_import_module = importlib.import_module

    def tracking_import(name, package=None):
        imported_modules.append(name)
        return real_import_module(name, package)

    monkeypatch.setattr(importlib, "import_module", tracking_import)

    with (
        patch.object(app, "disable") as mock_disable,
        patch.object(app, "enable") as mock_enable,
    ):
        with patch.object(asyncio, "run"):
            launcher(["--include-context"])

    assert "ansys.aedt.mcp.contexts" in imported_modules
    mock_enable.assert_called_once_with(tags={"pyaedt_context"})
    # disable may still be called for requires_aedt tag (tools requiring AEDT connection)
    for call in mock_disable.call_args_list:
        assert call.kwargs.get("tags") != {"pyaedt_context"}


@pytest.mark.unit
def test_launcher_disables_requires_aedt_tag_when_dynamic_discovery_requested(
    monkeypatch,
):
    """Opt-in dynamic discovery should hide AEDT-only tools until connected."""
    from ansys.aedt.mcp.server import app, launcher

    imported_modules = []
    real_import_module = importlib.import_module

    def tracking_import(name, package=None):
        imported_modules.append(name)
        return real_import_module(name, package)

    monkeypatch.setattr(importlib, "import_module", tracking_import)

    with (
        patch.object(app, "disable") as mock_disable,
        patch.object(app, "enable") as mock_enable,
    ):
        with patch.object(asyncio, "run"):
            launcher(["--dynamic-tool-discovery"])

    assert "ansys.aedt.mcp.tools" in imported_modules
    disable_calls = [c.kwargs.get("tags") for c in mock_disable.call_args_list]
    assert {"pyaedt_context"} in disable_calls
    assert {"requires_aedt"} in disable_calls
    mock_enable.assert_not_called()


@pytest.mark.unit
def test_product_startup_connects_when_connect_flag_is_true():
    """MCP startup should initialize AEDT Desktop when connect_on_startup is True."""
    from ansys.aedt.mcp.server import PyAEDTMCP

    with (
        patch("ansys.aedt.core.Desktop") as mock_desktop,
    ):
        fake_desktop = MagicMock()
        mock_desktop.return_value = fake_desktop

        mcp = PyAEDTMCP()
        setattr(
            mcp,
            "_cli_config",
            {
                "transport_type": "stdio",
                "aedt_machine": "localhost",
                "aedt_port": 50051,
                "aedt_version": None,
                "non_graphical": True,
                "connect_on_startup": True,
                "include_context_tools": False,
                "dynamic_tool_discovery": False,
                "http_host": "127.0.0.1",
                "http_port": 8080,
                "cors_origins": None,
            },
        )
        mcp.create_context()
        mcp.product_startup()

        mock_desktop.assert_called_once_with(
            version=None,
            non_graphical=True,
            new_desktop=False,
            machine="localhost",
            port=50051,
        )
        assert mcp.context.desktop is fake_desktop


@pytest.mark.unit
def test_product_startup_does_not_connect_by_default():
    """When connect_on_startup is False, MCP should not initialize AEDT Desktop."""
    from ansys.aedt.mcp.server import PyAEDTMCP

    with patch("ansys.aedt.core.Desktop") as mock_desktop:
        mcp = PyAEDTMCP()
        setattr(
            mcp,
            "_cli_config",
            {
                "transport_type": "stdio",
                "aedt_machine": "localhost",
                "aedt_port": 50051,
                "aedt_version": None,
                "non_graphical": True,
                "connect_on_startup": False,
                "include_context_tools": False,
                "dynamic_tool_discovery": False,
                "http_host": "127.0.0.1",
                "http_port": 8080,
                "cors_origins": None,
            },
        )
        mcp.create_context()
        mcp.product_startup()

        mock_desktop.assert_not_called()
        assert mcp.context.desktop is None


@pytest.mark.unit
def test_non_graphical_modes():
    """Test graphical/non-graphical mode flags."""
    from ansys.aedt.mcp import app as package_mcp
    from ansys.aedt.mcp.server import launcher

    # Test default (non-graphical)
    with patch.object(asyncio, "run"):
        launcher([])
    cfg = getattr(package_mcp, "_cli_config", None)
    assert cfg["non_graphical"] is True

    # Test explicit graphical mode
    with patch.object(asyncio, "run"):
        launcher(["--graphical"])
    cfg = getattr(package_mcp, "_cli_config", None)
    assert cfg["non_graphical"] is False


@pytest.mark.unit
def test_legacy_enable_agent_codegen_context_flag_is_rejected():
    """Legacy flag should fail."""
    from ansys.aedt.mcp.server import launcher

    with pytest.raises(SystemExit):
        launcher(["--enable-agent-codegen-context"])
