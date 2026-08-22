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

"""Tests for gRPC transport mode auto-detection and resolution.

Covers:
- resolve_transport_mode() logic on Windows and Linux platforms
- Certificate directory discovery (_find_certs_dir)
- Integration with connect_to_mechanical / launch_mechanical tools
- CLI argument parsing for --transport-mode and --certs-dir
- Environment variable fallbacks (PYMECHANICAL_TRANSPORT_MODE,
  ANSYS_GRPC_CERTIFICATES)
- product_startup() with transport mode
"""

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from ansys.mechanical.mcp.helpers import (
    VALID_TRANSPORT_MODES,
    _find_certs_dir,
    resolve_transport_mode,
)


# ---------------------------------------------------------------------------
# _find_certs_dir
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestFindCertsDir:
    """Tests for the certificate directory discovery function."""

    def test_explicit_dir_with_all_certs(self, tmp_path):
        """Return the directory when all three cert files are present."""
        for name in ("ca.crt", "client.crt", "client.key"):
            (tmp_path / name).write_text("dummy")

        result = _find_certs_dir(str(tmp_path))
        assert result == tmp_path

    def test_explicit_dir_missing_one_cert(self, tmp_path):
        """Return None when a required file is missing."""
        (tmp_path / "ca.crt").write_text("dummy")
        (tmp_path / "client.crt").write_text("dummy")
        # client.key is intentionally missing

        result = _find_certs_dir(str(tmp_path))
        assert result is None

    def test_explicit_dir_does_not_exist(self):
        """Return None when the explicit path does not exist."""
        result = _find_certs_dir("/non/existent/path")
        assert result is None

    def test_env_var_fallback(self, tmp_path, monkeypatch):
        """Fall back to ANSYS_GRPC_CERTIFICATES env var."""
        for name in ("ca.crt", "client.crt", "client.key"):
            (tmp_path / name).write_text("dummy")
        monkeypatch.setenv("ANSYS_GRPC_CERTIFICATES", str(tmp_path))

        result = _find_certs_dir(None)
        assert result == tmp_path

    def test_env_var_with_missing_certs(self, tmp_path, monkeypatch):
        """Env var points to dir with incomplete certs → None."""
        (tmp_path / "ca.crt").write_text("dummy")
        monkeypatch.setenv("ANSYS_GRPC_CERTIFICATES", str(tmp_path))

        result = _find_certs_dir(None)
        assert result is None

    def test_relative_certs_dir(self, tmp_path, monkeypatch):
        """Fall back to 'certs/' relative dir when no explicit or env var."""
        monkeypatch.delenv("ANSYS_GRPC_CERTIFICATES", raising=False)
        certs_dir = tmp_path / "certs"
        certs_dir.mkdir()
        for name in ("ca.crt", "client.crt", "client.key"):
            (certs_dir / name).write_text("dummy")

        # Change cwd so the relative "certs" path resolves correctly
        monkeypatch.chdir(tmp_path)

        result = _find_certs_dir(None)
        assert result == Path("certs")

    def test_no_certs_anywhere(self, tmp_path, monkeypatch):
        """No certs in any location → None."""
        monkeypatch.delenv("ANSYS_GRPC_CERTIFICATES", raising=False)
        monkeypatch.chdir(tmp_path)  # empty directory, no 'certs/' subdir

        result = _find_certs_dir(None)
        assert result is None

    def test_explicit_takes_priority_over_env(self, tmp_path, monkeypatch):
        """Explicit certs_dir is checked before ANSYS_GRPC_CERTIFICATES."""
        explicit_dir = tmp_path / "explicit"
        explicit_dir.mkdir()
        for name in ("ca.crt", "client.crt", "client.key"):
            (explicit_dir / name).write_text("explicit")

        env_dir = tmp_path / "env_certs"
        env_dir.mkdir()
        for name in ("ca.crt", "client.crt", "client.key"):
            (env_dir / name).write_text("env")

        monkeypatch.setenv("ANSYS_GRPC_CERTIFICATES", str(env_dir))

        result = _find_certs_dir(str(explicit_dir))
        assert result == explicit_dir


# ---------------------------------------------------------------------------
# resolve_transport_mode
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestResolveTransportMode:
    """Tests for the transport mode resolution strategy."""

    # -- Explicit overrides --------------------------------------------------

    def test_explicit_insecure(self):
        """Explicit 'insecure' returns ('insecure', None)."""
        mode, certs = resolve_transport_mode(transport_mode="insecure")
        assert mode == "insecure"
        assert certs is None

    def test_explicit_wnua(self):
        """Explicit 'wnua' returns ('wnua', None)."""
        mode, certs = resolve_transport_mode(transport_mode="wnua")
        assert mode == "wnua"
        assert certs is None

    def test_explicit_mtls_with_certs(self, tmp_path):
        """Explicit 'mtls' with valid certs directory."""
        for name in ("ca.crt", "client.crt", "client.key"):
            (tmp_path / name).write_text("dummy")

        mode, certs = resolve_transport_mode(transport_mode="mtls", certs_dir=str(tmp_path))
        assert mode == "mtls"
        assert certs == str(tmp_path)

    def test_explicit_mtls_without_certs_warns(self, tmp_path):
        """Explicit 'mtls' without certs → still returns 'mtls' (will fail at connect)."""
        mode, certs = resolve_transport_mode(
            transport_mode="mtls", certs_dir=str(tmp_path / "nonexistent")
        )
        assert mode == "mtls"
        # certs_dir is passed through even when not valid, so PyMechanical
        # raises its own descriptive error at connection time
        assert certs == str(tmp_path / "nonexistent")

    def test_invalid_transport_mode_raises(self):
        """Invalid mode string raises ValueError."""
        with pytest.raises(ValueError, match="Invalid transport_mode"):
            resolve_transport_mode(transport_mode="tls_v2")

    def test_case_insensitive(self):
        """Transport mode string is case-insensitive."""
        mode, _ = resolve_transport_mode(transport_mode="INSECURE")
        assert mode == "insecure"

        mode, _ = resolve_transport_mode(transport_mode="MTLS")
        assert mode == "mtls"

    def test_whitespace_stripped(self):
        """Leading/trailing whitespace is stripped."""
        mode, _ = resolve_transport_mode(transport_mode="  insecure  ")
        assert mode == "insecure"

    # -- Auto-detect on Windows ----------------------------------------------

    @patch("ansys.mechanical.mcp.helpers._is_linux", return_value=False)
    def test_auto_on_windows(self, _mock_linux):
        """On Windows, auto-detect returns (None, None) → defer to PyMechanical."""
        mode, certs = resolve_transport_mode(transport_mode=None)
        assert mode is None
        assert certs is None

    @patch("ansys.mechanical.mcp.helpers._is_linux", return_value=False)
    def test_auto_on_windows_with_string(self, _mock_linux):
        """Explicit 'auto' string on Windows also defers."""
        mode, certs = resolve_transport_mode(transport_mode="auto")
        assert mode is None
        assert certs is None

    # -- Auto-detect on Linux (no certs) -------------------------------------

    @patch("ansys.mechanical.mcp.helpers._is_linux", return_value=True)
    def test_auto_on_linux_no_certs(self, _mock_linux, tmp_path, monkeypatch):
        """Linux without certs → ('insecure', None)."""
        monkeypatch.delenv("ANSYS_GRPC_CERTIFICATES", raising=False)
        monkeypatch.chdir(tmp_path)

        mode, certs = resolve_transport_mode(transport_mode=None)
        assert mode == "insecure"
        assert certs is None

    # -- Auto-detect on Linux (with certs) -----------------------------------

    @patch("ansys.mechanical.mcp.helpers._is_linux", return_value=True)
    def test_auto_on_linux_with_certs(self, _mock_linux, tmp_path, monkeypatch):
        """Linux with certs available → ('mtls', <path>)."""
        certs_dir = tmp_path / "certs"
        certs_dir.mkdir()
        for name in ("ca.crt", "client.crt", "client.key"):
            (certs_dir / name).write_text("dummy")

        monkeypatch.delenv("ANSYS_GRPC_CERTIFICATES", raising=False)
        monkeypatch.chdir(tmp_path)

        mode, certs = resolve_transport_mode(transport_mode=None)
        assert mode == "mtls"
        assert certs == str(Path("certs"))

    @patch("ansys.mechanical.mcp.helpers._is_linux", return_value=True)
    def test_auto_on_linux_with_env_certs(self, _mock_linux, tmp_path, monkeypatch):
        """Linux with certs via ANSYS_GRPC_CERTIFICATES env var → mtls."""
        for name in ("ca.crt", "client.crt", "client.key"):
            (tmp_path / name).write_text("dummy")
        monkeypatch.setenv("ANSYS_GRPC_CERTIFICATES", str(tmp_path))
        monkeypatch.chdir(tmp_path / "..")  # ensure relative "certs" doesn't exist

        mode, certs = resolve_transport_mode(transport_mode=None, certs_dir=None)
        assert mode == "mtls"
        assert certs == str(tmp_path)

    # -- None vs "auto" equivalence ------------------------------------------

    @patch("ansys.mechanical.mcp.helpers._is_linux", return_value=True)
    def test_none_and_auto_are_equivalent(self, _mock_linux, tmp_path, monkeypatch):
        """transport_mode=None and transport_mode='auto' produce the same result."""
        monkeypatch.delenv("ANSYS_GRPC_CERTIFICATES", raising=False)
        monkeypatch.chdir(tmp_path)

        mode1, certs1 = resolve_transport_mode(transport_mode=None)
        mode2, certs2 = resolve_transport_mode(transport_mode="auto")
        assert mode1 == mode2
        assert certs1 == certs2


# ---------------------------------------------------------------------------
# connect_to_mechanical tool - transport_mode pass-through
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestConnectToMechanicalTransportMode:
    """Tests that the connect_to_mechanical tool resolves and passes
    transport_mode correctly to pymechanical.connect_to_mechanical."""

    @patch("ansys.mechanical.mcp.helpers._is_linux", return_value=True)
    @pytest.mark.asyncio
    async def test_connect_auto_linux_no_certs(
        self, _mock_linux, mock_context_no_mechanical, tmp_path, monkeypatch
    ):
        """On Linux without certs, auto-detect passes transport_mode='insecure'."""
        monkeypatch.delenv("ANSYS_GRPC_CERTIFICATES", raising=False)
        monkeypatch.chdir(tmp_path)

        mock_mechanical = MagicMock()
        mock_mechanical.version = "2025 R2"

        with patch(
            "ansys.mechanical.mcp.tools.pymechanical.connect_to_mechanical",
            return_value=mock_mechanical,
        ) as mock_connect:
            from ansys.mechanical.mcp.tools import connect_to_mechanical

            result = await connect_to_mechanical(
                mock_context_no_mechanical,
                ip="host.docker.internal",
                port=10000,
            )

            assert "Successfully connected" in result

            # Verify transport_mode was passed through
            call_kwargs = mock_connect.call_args[1]
            assert call_kwargs["transport_mode"] == "insecure"
            assert "certs_dir" not in call_kwargs

    @patch("ansys.mechanical.mcp.helpers._is_linux", return_value=True)
    @pytest.mark.asyncio
    async def test_connect_auto_linux_with_certs(
        self, _mock_linux, mock_context_no_mechanical, tmp_path, monkeypatch
    ):
        """On Linux with certs, auto-detect passes transport_mode='mtls'."""
        certs_dir = tmp_path / "certs"
        certs_dir.mkdir()
        for name in ("ca.crt", "client.crt", "client.key"):
            (certs_dir / name).write_text("dummy")

        monkeypatch.delenv("ANSYS_GRPC_CERTIFICATES", raising=False)
        monkeypatch.chdir(tmp_path)

        mock_mechanical = MagicMock()
        mock_mechanical.version = "2025 R2"

        with patch(
            "ansys.mechanical.mcp.tools.pymechanical.connect_to_mechanical",
            return_value=mock_mechanical,
        ) as mock_connect:
            from ansys.mechanical.mcp.tools import connect_to_mechanical

            result = await connect_to_mechanical(
                mock_context_no_mechanical,
                ip="host.docker.internal",
                port=10000,
            )

            assert "Successfully connected" in result
            call_kwargs = mock_connect.call_args[1]
            assert call_kwargs["transport_mode"] == "mtls"
            assert call_kwargs["certs_dir"] == str(Path("certs"))

    @patch("ansys.mechanical.mcp.helpers._is_linux", return_value=False)
    @pytest.mark.asyncio
    async def test_connect_auto_windows(
        self, _mock_linux, mock_context_no_mechanical, tmp_path, monkeypatch
    ):
        """On Windows, auto-detect does not pass transport_mode (defer to pymechanical)."""
        monkeypatch.chdir(tmp_path)

        mock_mechanical = MagicMock()
        mock_mechanical.version = "2025 R2"

        with patch(
            "ansys.mechanical.mcp.tools.pymechanical.connect_to_mechanical",
            return_value=mock_mechanical,
        ) as mock_connect:
            from ansys.mechanical.mcp.tools import connect_to_mechanical

            result = await connect_to_mechanical(mock_context_no_mechanical)

            assert "Successfully connected" in result
            call_kwargs = mock_connect.call_args[1]
            # transport_mode should NOT be in kwargs (let pymechanical default)
            assert "transport_mode" not in call_kwargs

    @pytest.mark.asyncio
    async def test_connect_explicit_transport_mode(self, mock_context_no_mechanical):
        """Explicit transport_mode param on the tool is honoured."""
        mock_mechanical = MagicMock()
        mock_mechanical.version = "2025 R2"

        with patch(
            "ansys.mechanical.mcp.tools.pymechanical.connect_to_mechanical",
            return_value=mock_mechanical,
        ) as mock_connect:
            from ansys.mechanical.mcp.tools import connect_to_mechanical

            result = await connect_to_mechanical(
                mock_context_no_mechanical,
                ip="10.0.0.1",
                port=10000,
                transport_mode="insecure",
            )

            assert "Successfully connected" in result
            call_kwargs = mock_connect.call_args[1]
            assert call_kwargs["transport_mode"] == "insecure"

    @pytest.mark.asyncio
    async def test_connect_context_transport_mode_fallback(self, mock_context_no_mechanical):
        """When tool param is None, falls back to context's grpc_transport_mode."""
        mock_context_no_mechanical.request_context.lifespan_context.grpc_transport_mode = "insecure"

        mock_mechanical = MagicMock()
        mock_mechanical.version = "2025 R2"

        with patch(
            "ansys.mechanical.mcp.tools.pymechanical.connect_to_mechanical",
            return_value=mock_mechanical,
        ) as mock_connect:
            from ansys.mechanical.mcp.tools import connect_to_mechanical

            result = await connect_to_mechanical(mock_context_no_mechanical)

            assert "Successfully connected" in result
            call_kwargs = mock_connect.call_args[1]
            assert call_kwargs["transport_mode"] == "insecure"

    @pytest.mark.asyncio
    async def test_connect_tool_param_overrides_context(self, mock_context_no_mechanical):
        """Tool's transport_mode param takes precedence over context config."""
        mock_context_no_mechanical.request_context.lifespan_context.grpc_transport_mode = "mtls"

        mock_mechanical = MagicMock()
        mock_mechanical.version = "2025 R2"

        with patch(
            "ansys.mechanical.mcp.tools.pymechanical.connect_to_mechanical",
            return_value=mock_mechanical,
        ) as mock_connect:
            from ansys.mechanical.mcp.tools import connect_to_mechanical

            result = await connect_to_mechanical(
                mock_context_no_mechanical,
                transport_mode="insecure",
            )

            assert "Successfully connected" in result
            call_kwargs = mock_connect.call_args[1]
            assert call_kwargs["transport_mode"] == "insecure"

    @pytest.mark.asyncio
    async def test_connect_result_includes_transport_mode(self, mock_context_no_mechanical):
        """Result message includes the resolved transport mode."""
        mock_mechanical = MagicMock()
        mock_mechanical.version = "2025 R2"

        with patch(
            "ansys.mechanical.mcp.tools.pymechanical.connect_to_mechanical",
            return_value=mock_mechanical,
        ):
            from ansys.mechanical.mcp.tools import connect_to_mechanical

            result = await connect_to_mechanical(
                mock_context_no_mechanical,
                transport_mode="insecure",
            )

            assert "Transport mode: insecure" in result


# ---------------------------------------------------------------------------
# launch_mechanical tool - transport_mode pass-through
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestLaunchMechanicalTransportMode:
    """Tests that launch_mechanical resolves and passes transport_mode."""

    @patch("ansys.mechanical.mcp.helpers._is_linux", return_value=True)
    @pytest.mark.asyncio
    async def test_launch_auto_linux_no_certs(
        self, _mock_linux, mock_context_no_mechanical, tmp_path, monkeypatch
    ):
        """On Linux, auto passes transport_mode='insecure' to launch."""
        monkeypatch.delenv("ANSYS_GRPC_CERTIFICATES", raising=False)
        monkeypatch.chdir(tmp_path)

        mock_mechanical = MagicMock()
        mock_mechanical.version = "2025 R2"
        mock_mechanical.project_directory = "/tmp/project"

        with patch(
            "ansys.mechanical.mcp.tools.pymechanical.launch_mechanical",
            return_value=mock_mechanical,
        ) as mock_launch:
            from ansys.mechanical.mcp.tools import launch_mechanical

            result = await launch_mechanical(mock_context_no_mechanical)

            assert "Successfully launched" in result
            call_kwargs = mock_launch.call_args[1]
            assert call_kwargs["transport_mode"] == "insecure"

    @pytest.mark.asyncio
    async def test_launch_explicit_transport_mode(self, mock_context_no_mechanical):
        """Explicit transport_mode is passed through to pymechanical."""
        mock_mechanical = MagicMock()
        mock_mechanical.version = "2025 R2"
        mock_mechanical.project_directory = "/tmp/project"

        with patch(
            "ansys.mechanical.mcp.tools.pymechanical.launch_mechanical",
            return_value=mock_mechanical,
        ) as mock_launch:
            from ansys.mechanical.mcp.tools import launch_mechanical

            result = await launch_mechanical(
                mock_context_no_mechanical,
                transport_mode="insecure",
            )

            assert "Successfully launched" in result
            call_kwargs = mock_launch.call_args[1]
            assert call_kwargs["transport_mode"] == "insecure"

    @patch("ansys.mechanical.mcp.helpers._is_linux", return_value=False)
    @pytest.mark.asyncio
    async def test_launch_auto_windows(
        self, _mock_linux, mock_context_no_mechanical, tmp_path, monkeypatch
    ):
        """On Windows auto, transport_mode is not passed (defer to pymechanical)."""
        monkeypatch.chdir(tmp_path)

        mock_mechanical = MagicMock()
        mock_mechanical.version = "2025 R2"
        mock_mechanical.project_directory = "/tmp/project"

        with patch(
            "ansys.mechanical.mcp.tools.pymechanical.launch_mechanical",
            return_value=mock_mechanical,
        ) as mock_launch:
            from ansys.mechanical.mcp.tools import launch_mechanical

            result = await launch_mechanical(mock_context_no_mechanical)

            assert "Successfully launched" in result
            call_kwargs = mock_launch.call_args[1]
            assert "transport_mode" not in call_kwargs


# ---------------------------------------------------------------------------
# CLI argument parsing
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestCLITransportModeArgs:
    """Tests for --transport-mode and --certs-dir CLI arguments."""

    def test_default_transport_mode_is_none(self):
        """Default CLI parsing has grpc_transport_mode=None."""
        from ansys.mechanical.mcp import app as package_mcp
        from ansys.mechanical.mcp.server import launcher

        with patch.object(asyncio, "run"):
            with patch.object(package_mcp, "run_stdio_async", new=Mock(return_value=object())):
                launcher([])

        cfg = getattr(package_mcp, "_cli_config", None)
        assert cfg is not None
        assert cfg["grpc_transport_mode"] is None
        assert cfg["certs_dir"] is None

    def test_explicit_transport_mode_cli(self):
        """--transport-mode insecure is parsed correctly."""
        from ansys.mechanical.mcp import app as package_mcp
        from ansys.mechanical.mcp.server import launcher

        with patch.object(asyncio, "run"):
            with patch.object(package_mcp, "run_stdio_async", new=Mock(return_value=object())):
                launcher(["--transport-mode", "insecure"])

        cfg = getattr(package_mcp, "_cli_config", None)
        assert cfg["grpc_transport_mode"] == "insecure"

    def test_transport_mode_mtls_with_certs_dir(self):
        """--transport-mode mtls --certs-dir /path is parsed correctly."""
        from ansys.mechanical.mcp import app as package_mcp
        from ansys.mechanical.mcp.server import launcher

        with patch.object(asyncio, "run"):
            with patch.object(package_mcp, "run_stdio_async", new=Mock(return_value=object())):
                launcher(["--transport-mode", "mtls", "--certs-dir", "/path/to/certs"])

        cfg = getattr(package_mcp, "_cli_config", None)
        assert cfg["grpc_transport_mode"] == "mtls"
        assert cfg["certs_dir"] == "/path/to/certs"

    def test_invalid_transport_mode_exits(self):
        """Invalid --transport-mode value should cause argparse to exit."""
        from ansys.mechanical.mcp.server import launcher

        with pytest.raises(SystemExit):
            launcher(["--transport-mode", "nonexistent"])

    def test_env_var_fallback(self, monkeypatch):
        """PYMECHANICAL_TRANSPORT_MODE env var is used when CLI flag is absent."""
        monkeypatch.setenv("PYMECHANICAL_TRANSPORT_MODE", "insecure")

        from ansys.mechanical.mcp import app as package_mcp
        from ansys.mechanical.mcp.server import launcher

        with patch.object(asyncio, "run"):
            with patch.object(package_mcp, "run_stdio_async", new=Mock(return_value=object())):
                launcher([])

        cfg = getattr(package_mcp, "_cli_config", None)
        assert cfg["grpc_transport_mode"] == "insecure"

    def test_cli_flag_overrides_env_var(self, monkeypatch):
        """CLI --transport-mode takes precedence over env var."""
        monkeypatch.setenv("PYMECHANICAL_TRANSPORT_MODE", "insecure")

        from ansys.mechanical.mcp import app as package_mcp
        from ansys.mechanical.mcp.server import launcher

        with patch.object(asyncio, "run"):
            with patch.object(package_mcp, "run_stdio_async", new=Mock(return_value=object())):
                launcher(["--transport-mode", "mtls"])

        cfg = getattr(package_mcp, "_cli_config", None)
        assert cfg["grpc_transport_mode"] == "mtls"

    def test_certs_dir_env_var_fallback(self, monkeypatch):
        """ANSYS_GRPC_CERTIFICATES env var is used for certs_dir."""
        monkeypatch.setenv("ANSYS_GRPC_CERTIFICATES", "/custom/certs")

        from ansys.mechanical.mcp import app as package_mcp
        from ansys.mechanical.mcp.server import launcher

        with patch.object(asyncio, "run"):
            with patch.object(package_mcp, "run_stdio_async", new=Mock(return_value=object())):
                launcher([])

        cfg = getattr(package_mcp, "_cli_config", None)
        assert cfg["certs_dir"] == "/custom/certs"


# ---------------------------------------------------------------------------
# product_startup - transport_mode
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestProductStartupTransportMode:
    """Tests that product_startup passes resolved transport_mode."""

    def test_startup_connect_passes_transport_mode(self):
        """product_startup uses resolve_transport_mode and passes to connect."""
        from ansys.mechanical.mcp.server import PyMechanicalAppContext, PyMechanicalMCP

        fake_mechanical = MagicMock()
        fake_mechanical.exit = MagicMock()

        with patch(
            "ansys.mechanical.core.connect_to_mechanical",
            return_value=fake_mechanical,
        ) as mock_connect:
            with patch(
                "ansys.mechanical.mcp.helpers.resolve_transport_mode",
                return_value=("insecure", None),
            ):
                mcp = PyMechanicalMCP()
                mcp.context = PyMechanicalAppContext(
                    mechanical_ip="host.docker.internal",
                    mechanical_port=10000,
                    connect_on_startup=True,
                    grpc_transport_mode=None,
                    certs_dir=None,
                )
                mcp.product_startup()

                call_kwargs = mock_connect.call_args[1]
                assert call_kwargs["transport_mode"] == "insecure"
                assert call_kwargs["ip"] == "host.docker.internal"
                assert call_kwargs["port"] == 10000

                mcp.product_cleanup()

    def test_startup_connect_with_explicit_mode(self):
        """product_startup honours explicit grpc_transport_mode from CLI."""
        from ansys.mechanical.mcp.server import PyMechanicalAppContext, PyMechanicalMCP

        fake_mechanical = MagicMock()
        fake_mechanical.exit = MagicMock()

        with patch(
            "ansys.mechanical.core.connect_to_mechanical",
            return_value=fake_mechanical,
        ) as mock_connect:
            with patch(
                "ansys.mechanical.mcp.helpers.resolve_transport_mode",
                return_value=("insecure", None),
            ):
                mcp = PyMechanicalMCP()
                mcp.context = PyMechanicalAppContext(
                    mechanical_ip="10.0.0.1",
                    mechanical_port=10001,
                    connect_on_startup=True,
                    grpc_transport_mode="insecure",
                    certs_dir=None,
                )
                mcp.product_startup()

                call_kwargs = mock_connect.call_args[1]
                assert call_kwargs["transport_mode"] == "insecure"
                assert call_kwargs["ip"] == "10.0.0.1"
                assert call_kwargs["port"] == 10001

                mcp.product_cleanup()

    def test_startup_connect_windows_auto(self):
        """When resolution defers, transport_mode is not passed to pymechanical."""
        from ansys.mechanical.mcp.server import PyMechanicalAppContext, PyMechanicalMCP

        fake_mechanical = MagicMock()
        fake_mechanical.exit = MagicMock()

        with patch(
            "ansys.mechanical.core.connect_to_mechanical",
            return_value=fake_mechanical,
        ) as mock_connect:
            with patch(
                "ansys.mechanical.mcp.helpers.resolve_transport_mode",
                return_value=(None, None),
            ):
                mcp = PyMechanicalMCP()
                mcp.context = PyMechanicalAppContext(
                    mechanical_ip="127.0.0.1",
                    mechanical_port=10000,
                    connect_on_startup=True,
                    grpc_transport_mode=None,
                    certs_dir=None,
                )
                mcp.product_startup()

                call_kwargs = mock_connect.call_args[1]
                assert "transport_mode" not in call_kwargs
                assert call_kwargs["ip"] == "127.0.0.1"

                mcp.product_cleanup()


# ---------------------------------------------------------------------------
# VALID_TRANSPORT_MODES constant
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestConstants:
    """Validate exported constants."""

    def test_valid_modes(self):
        """VALID_TRANSPORT_MODES contains the expected values."""
        assert VALID_TRANSPORT_MODES == {"auto", "insecure", "mtls", "wnua"}
