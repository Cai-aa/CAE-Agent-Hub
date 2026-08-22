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

"""Unit tests for Docker-awareness features.

Tests cover:
- _is_docker() detection
- _probe_grpc_endpoint() TCP probe
- check_aedt_installed Docker branch
- launch_aedt Docker guard
- connect_to_aedt Docker env-var override
"""

import os
import socket
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ansys.aedt.mcp.helpers import _is_docker, _probe_grpc_endpoint

# ------------------------------------------------------------------ #
# _is_docker()
# ------------------------------------------------------------------ #


class TestIsDocker:
    """Tests for _is_docker() helper."""

    def test_not_docker_by_default(self):
        """Outside a container, _is_docker() should return False."""
        with patch("ansys.aedt.mcp.helpers.Path") as MockPath:
            MockPath.return_value.exists.return_value = False
            assert _is_docker() is False

    def test_dockerenv_marker(self):
        """Detect Docker via /.dockerenv."""
        with patch("ansys.aedt.mcp.helpers.Path") as MockPath:

            def exists_side_effect(p=None):
                m = MagicMock()
                if str(MockPath.call_args_list[-1][0][0]) == "/.dockerenv":
                    m.exists.return_value = True
                else:
                    m.exists.return_value = False
                return m

            MockPath.side_effect = lambda p: type(
                "P", (), {"exists": lambda self: p == "/.dockerenv"}
            )()
            assert _is_docker() is True

    def test_containerenv_marker(self):
        """Detect Podman/container via /run/.containerenv."""
        with patch("ansys.aedt.mcp.helpers.Path") as MockPath:
            MockPath.side_effect = lambda p: type(
                "P", (), {"exists": lambda self: p == "/run/.containerenv"}
            )()
            assert _is_docker() is True

    def test_no_markers(self):
        """No marker files → not Docker."""
        with patch("ansys.aedt.mcp.helpers.Path") as MockPath:
            MockPath.side_effect = lambda p: type("P", (), {"exists": lambda self: False})()
            assert _is_docker() is False


# ------------------------------------------------------------------ #
# _probe_grpc_endpoint()
# ------------------------------------------------------------------ #


class TestProbeGrpcEndpoint:
    """Tests for _probe_grpc_endpoint() TCP probe."""

    def test_reachable_endpoint(self):
        """Probe a listening TCP socket → True."""
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", 0))
        port = server.getsockname()[1]
        server.listen(1)
        try:
            assert _probe_grpc_endpoint("127.0.0.1", port, timeout=2.0) == {
                "reachable": True,
                "host": "127.0.0.1",
                "port": port,
                "error": None,
            }
        finally:
            server.close()

    def test_unreachable_endpoint(self):
        """Probe a closed port → False."""
        # Bind-then-close to guarantee nobody is listening on that port
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind(("127.0.0.1", 0))
        port = server.getsockname()[1]
        server.close()
        probe = _probe_grpc_endpoint("127.0.0.1", port, timeout=0.5)
        assert probe["reachable"] is False
        assert probe["host"] == "127.0.0.1"
        assert probe["port"] == port
        assert probe["error"] is not None

    def test_unresolvable_host(self):
        """Probe a non-existent host → False."""
        probe = _probe_grpc_endpoint("host.that.does.not.exist.invalid", 50051, timeout=0.5)
        assert probe["reachable"] is False
        assert probe["host"] == "host.that.does.not.exist.invalid"
        assert probe["port"] == 50051
        assert probe["error"] is not None

    def test_custom_timeout(self):
        """Very short timeout on unreachable host → False quickly."""
        probe = _probe_grpc_endpoint("192.0.2.1", 50051, timeout=0.1)
        assert probe["reachable"] is False
        assert probe["host"] == "192.0.2.1"
        assert probe["port"] == 50051
        assert probe["error"] is not None


# ------------------------------------------------------------------ #
# check_aedt_installed – Docker branch
# ------------------------------------------------------------------ #


class TestCheckAEDTInstalledDocker:
    """Tests for check_aedt_installed tool inside Docker."""

    def test_docker_endpoint_reachable(self, mock_context_no_desktop):
        """Docker + reachable endpoint → success message."""
        from ansys.aedt.mcp.tools import check_aedt_installed

        with (
            patch("ansys.aedt.mcp.tools._is_docker", return_value=True),
            patch(
                "ansys.aedt.mcp.tools._probe_grpc_endpoint",
                return_value={
                    "reachable": True,
                    "host": "aedt-host",
                    "port": 50051,
                    "error": None,
                },
            ),
            patch.dict(os.environ, {"AEDT_MACHINE": "aedt-host", "AEDT_PORT": "50051"}),
        ):
            result = check_aedt_installed(mock_context_no_desktop)
            assert "reachable" in result.lower()
            assert "aedt-host" in result
            assert "50051" in result

    def test_docker_endpoint_unreachable(self, mock_context_no_desktop):
        """Docker + unreachable endpoint → failure message."""
        from ansys.aedt.mcp.tools import check_aedt_installed

        with (
            patch("ansys.aedt.mcp.tools._is_docker", return_value=True),
            patch(
                "ansys.aedt.mcp.tools._probe_grpc_endpoint",
                return_value={
                    "reachable": False,
                    "host": "badhost",
                    "port": 9999,
                    "error": "connection refused",
                },
            ),
            patch.dict(os.environ, {"AEDT_MACHINE": "badhost", "AEDT_PORT": "9999"}),
        ):
            result = check_aedt_installed(mock_context_no_desktop)
            assert "not reachable" in result.lower()
            assert "badhost" in result

    def test_docker_defaults(self, mock_context_no_desktop):
        """Docker without env vars falls back to host.docker.internal:50051."""
        from ansys.aedt.mcp.tools import check_aedt_installed

        with (
            patch("ansys.aedt.mcp.tools._is_docker", return_value=True),
            patch(
                "ansys.aedt.mcp.tools._probe_grpc_endpoint",
                return_value={
                    "reachable": True,
                    "host": "host.docker.internal",
                    "port": 50051,
                    "error": None,
                },
            ),
            patch.dict(os.environ, {}, clear=True),
        ):
            # Need to remove AEDT_MACHINE/AEDT_PORT if set
            os.environ.pop("AEDT_MACHINE", None)
            os.environ.pop("AEDT_PORT", None)
            result = check_aedt_installed(mock_context_no_desktop)
            assert "host.docker.internal" in result


# ------------------------------------------------------------------ #
# launch_aedt – Docker guard
# ------------------------------------------------------------------ #


class TestLaunchAEDTDocker:
    """Tests for launch_aedt tool inside Docker."""

    @pytest.mark.asyncio
    async def test_docker_guard(self, mock_context_no_desktop):
        """launch_aedt should refuse to run inside Docker."""
        from ansys.aedt.mcp.tools import launch_aedt

        with patch("ansys.aedt.mcp.tools._is_docker", return_value=True):
            result = await launch_aedt(mock_context_no_desktop)
            assert "not supported" in result.lower()
            assert "connect_to_aedt" in result

    @pytest.mark.asyncio
    async def test_native_proceeds(self, mock_context_no_desktop):
        """launch_aedt on native should NOT hit Docker guard."""
        from ansys.aedt.mcp.tools import launch_aedt

        with (
            patch("ansys.aedt.mcp.tools._is_docker", return_value=False),
            patch("ansys.aedt.mcp.tools.discover_available_aedt_sessions", return_value=[]),
            patch("ansys.aedt.core.Desktop") as MockDesktop,
        ):
            mock_desk = MagicMock()
            mock_desk.aedt_version_id = "261"
            mock_desk.aedt_install_dir = "/opt/ansys"
            mock_desk.is_grpc_api = True
            MockDesktop.return_value = mock_desk

            result = await launch_aedt(mock_context_no_desktop, version="261")
            assert "successfully launched" in result.lower() or "261" in result


# ------------------------------------------------------------------ #
# connect_to_aedt – Docker env-var override
# ------------------------------------------------------------------ #


class TestConnectToAEDTDocker:
    """Tests for connect_to_aedt tool inside Docker."""

    @pytest.mark.asyncio
    async def test_docker_overrides_defaults(self, mock_context_no_desktop):
        """Inside Docker, defaults should be overridden by env vars."""
        from ansys.aedt.mcp.tools import connect_to_aedt

        with (
            patch("ansys.aedt.mcp.tools._is_docker", return_value=True),
            patch.dict(os.environ, {"AEDT_MACHINE": "remote-host", "AEDT_PORT": "55555"}),
            patch("ansys.aedt.core.Desktop") as MockDesktop,
            patch("ansys.aedt.core.generic.settings.settings"),
        ):
            mock_desk = MagicMock()
            mock_desk.aedt_version_id = "261"
            mock_desk.is_grpc_api = True
            MockDesktop.return_value = mock_desk

            await connect_to_aedt(mock_context_no_desktop)

            # Desktop should have been called with overridden host/port
            call_kwargs = MockDesktop.call_args[1]
            assert call_kwargs["machine"] == "remote-host"
            assert call_kwargs["port"] == 55555

    @pytest.mark.asyncio
    async def test_docker_no_override_when_explicit(self, mock_context_no_desktop):
        """Explicit non-default port/machine should NOT be overridden."""
        from ansys.aedt.mcp.tools import connect_to_aedt

        with (
            patch("ansys.aedt.mcp.tools._is_docker", return_value=True),
            patch.dict(os.environ, {"AEDT_MACHINE": "env-host", "AEDT_PORT": "55555"}),
            patch("ansys.aedt.core.Desktop") as MockDesktop,
            patch("ansys.aedt.core.generic.settings.settings"),
        ):
            mock_desk = MagicMock()
            mock_desk.aedt_version_id = "261"
            mock_desk.is_grpc_api = True
            MockDesktop.return_value = mock_desk

            # Pass explicit non-default values
            await connect_to_aedt(mock_context_no_desktop, port=9999, machine="my-server")

            call_kwargs = MockDesktop.call_args[1]
            # Explicit values should be preserved, NOT overridden
            assert call_kwargs["machine"] == "my-server"
            assert call_kwargs["port"] == 9999

    @pytest.mark.asyncio
    async def test_native_no_override(self, mock_context_no_desktop):
        """Outside Docker, defaults remain localhost:50051."""
        from ansys.aedt.mcp.tools import connect_to_aedt

        with (
            patch("ansys.aedt.mcp.tools._is_docker", return_value=False),
            patch("ansys.aedt.mcp.tools.discover_available_aedt_sessions", return_value=[]),
            patch("ansys.aedt.core.Desktop") as MockDesktop,
            patch("ansys.aedt.core.generic.settings.settings"),
        ):
            mock_desk = MagicMock()
            mock_desk.aedt_version_id = "261"
            mock_desk.is_grpc_api = True
            MockDesktop.return_value = mock_desk

            await connect_to_aedt(mock_context_no_desktop)

            call_kwargs = MockDesktop.call_args[1]
            assert call_kwargs["machine"] == "localhost"
            assert call_kwargs["port"] == 50051


# ------------------------------------------------------------------ #
# Fixtures (from conftest, duplicated here for self-containment)
# ------------------------------------------------------------------ #


@pytest.fixture
def mock_context_no_desktop():
    """Create a mock Context without Desktop for testing tools."""
    from ansys.aedt.mcp.server import PyAEDTAppContext

    app_ctx = PyAEDTAppContext()
    app_ctx.desktop = None

    context = MagicMock()
    context.request_context = MagicMock()
    context.request_context.lifespan_context = app_ctx
    context.enable_components = AsyncMock()
    context.disable_components = AsyncMock()
    return context
