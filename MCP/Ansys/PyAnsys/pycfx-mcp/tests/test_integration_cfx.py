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

from __future__ import annotations

import json
import os

import pytest

from ansys.cfx.mcp import CFXMCP
from ansys.cfx.mcp.cfx.backend import CFXBackend
from ansys.cfx.mcp.cfx.sessions.session_manager import SessionManager

pytestmark = pytest.mark.integration


PUBLIC_TOOLS = (
    "cfx_model_context",
    "connect",
    "disconnect",
    "validate_code",
    "session_status",
    "cfx_workflow",
    "run_code",
)


async def _call_tool(leaf: CFXMCP, tool_name: str, **kwargs: object):
    tool = await leaf.get_tool(tool_name)
    return await tool.fn(**kwargs)


def _integration_enabled() -> bool:
    return os.environ.get("PYCFX_MCP_RUN_INTEGRATION", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _connect_kwargs() -> dict[str, object]:
    # Respect explicit launcher selection if provided.
    launcher = os.environ.get("PYCFX_MCP_LAUNCHER", "").strip()
    if not launcher:
        # Default behavior: use container if container configuration exists,
        # otherwise fall back to local installation.
        if os.environ.get("PYCFX_MCP_CFX_IMAGE") or os.environ.get("PYCFX_MCP_CONTAINER_DICT"):
            launcher = "from_container"
        else:
            launcher = "from_install"
    kwargs: dict[str, object] = {
        "launcher": launcher,
        "cleanup_on_exit": True,
    }
    container_dict = os.environ.get("PYCFX_MCP_CONTAINER_DICT", "").strip()
    if container_dict:
        kwargs["container_dict"] = json.loads(container_dict)
    elif launcher == "from_container":
        container_config: dict[str, object] = {}
        cfx_image = os.environ.get("PYCFX_MCP_CFX_IMAGE", "").strip()
        license_server = os.environ.get("PYCFX_MCP_LICENSE_SERVER", "").strip()
        host_mount_path = os.environ.get("PYCFX_MCP_HOST_MOUNT_PATH", "").strip()
        if cfx_image:
            container_config["cfx_image"] = cfx_image
        if license_server:
            container_config["license_server"] = license_server
        if host_mount_path:
            container_config["host_mount_path"] = host_mount_path
        if container_config:
            kwargs["container_dict"] = container_config
    return kwargs


def test_connect_kwargs_builds_container_config_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PYCFX_MCP_LAUNCHER", "from_container")
    monkeypatch.delenv("PYCFX_MCP_CONTAINER_DICT", raising=False)
    monkeypatch.setenv("PYCFX_MCP_CFX_IMAGE", "ghcr.io/ansys/pycfx:v25.2.3")
    monkeypatch.setenv("PYCFX_MCP_LICENSE_SERVER", "1055@license.example.com")
    monkeypatch.setenv("PYCFX_MCP_HOST_MOUNT_PATH", "D:/cfx-work")

    assert _connect_kwargs() == {
        "launcher": "from_container",
        "cleanup_on_exit": True,
        "container_dict": {
            "cfx_image": "ghcr.io/ansys/pycfx:v25.2.3",
            "license_server": "1055@license.example.com",
            "host_mount_path": "D:/cfx-work",
        },
    }


def test_connect_kwargs_prefers_explicit_container_dict(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PYCFX_MCP_LAUNCHER", "from_container")
    monkeypatch.setenv("PYCFX_MCP_CONTAINER_DICT", '{"cfx_image": "custom:image"}')
    monkeypatch.setenv("PYCFX_MCP_CFX_IMAGE", "ignored:image")

    assert _connect_kwargs()["container_dict"] == {"cfx_image": "custom:image"}


def test_connect_kwargs_defaults_to_container_launcher(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PYCFX_MCP_LAUNCHER", raising=False)
    monkeypatch.setenv("PYCFX_MCP_CFX_IMAGE", "ghcr.io/ansys/pycfx:v26.1.0")
    monkeypatch.setenv("PYCFX_MCP_LICENSE_SERVER", "1055@license.example.com")

    assert _connect_kwargs() == {
        "launcher": "from_container",
        "cleanup_on_exit": True,
        "container_dict": {
            "cfx_image": "ghcr.io/ansys/pycfx:v26.1.0",
            "license_server": "1055@license.example.com",
        },
    }


@pytest.fixture(autouse=True)
def cleanup_cfx_sessions():
    yield
    SessionManager.disconnect()


@pytest.mark.skipif(
    not _integration_enabled(),
    reason="Set PYCFX_MCP_RUN_INTEGRATION=1 on a runner with Ansys CFX installed.",
)
@pytest.mark.asyncio
async def test_cfx_backend_launches_pre_session_and_reports_status() -> None:
    backend = CFXBackend()

    connect = await backend.connect(**_connect_kwargs())

    assert connect.status == "ok", connect.message
    assert backend.is_connected() is True

    status = backend.status("cfx")
    solver_status = await backend.solver_status()

    assert status.connected is True
    assert any(note == "Pre: active" for note in status.notes)
    assert solver_status["pre_connected"] is True
    assert solver_status["backend_kind"] == "pycfx"


@pytest.mark.skipif(
    not _integration_enabled(),
    reason="Set PYCFX_MCP_RUN_INTEGRATION=1 on a runner with Ansys CFX installed.",
)
@pytest.mark.asyncio
async def test_cfx_mcp_live_integration_exercises_public_tools() -> None:
    leaf = CFXMCP()

    assert set(leaf._exposed) == set(PUBLIC_TOOLS)

    before_connect = await _call_tool(leaf, "session_status")
    assert before_connect.connected is False

    connect = await _call_tool(
        leaf,
        "connect",
        connect_kwargs=_connect_kwargs(),
    )
    assert connect.status == "ok", connect.message

    status = await _call_tool(leaf, "session_status")
    assert status.connected is True
    assert status.backend_kind == "pycfx"

    workflow_status = await _call_tool(leaf, "cfx_workflow", action="status")
    assert workflow_status["status"] == "ok"
    assert workflow_status["result"]["pre_connected"] is True

    model_context = await _call_tool(leaf, "cfx_model_context", action="summary", max_items=5)
    assert model_context["backend"] == "Ansys CFX (PyCFX)"
    assert model_context["status"]["pre_connected"] is True

    valid_code = await _call_tool(leaf, "validate_code", code="x = 1")
    assert valid_code.status == "ok"

    run_code = await _call_tool(leaf, "run_code", code="__return__ = 6 * 7")
    assert run_code.status == "ok"
    assert run_code.return_value == 42

    disconnect = await _call_tool(leaf, "disconnect")
    assert disconnect["status"] == "ok"

    after_disconnect = await _call_tool(leaf, "session_status")
    assert after_disconnect.connected is False


@pytest.mark.asyncio
async def test_run_code_without_connection_returns_error() -> None:
    leaf = CFXMCP()

    result = await _call_tool(leaf, "run_code", code="x = 1")

    # run_code can execute locally even without a solver connection.
    # Ensure the tool runs successfully and does not return a typed error.
    assert result.status == "ok"
    assert result.error_code is None


@pytest.mark.asyncio
async def test_disconnect_when_not_connected_is_safe() -> None:
    leaf = CFXMCP()

    result = await _call_tool(leaf, "disconnect")

    assert result["status"] in {"ok", "error"}


@pytest.mark.skipif(
    not _integration_enabled(),
    reason="Set PYCFX_MCP_RUN_INTEGRATION=1 on a runner with Ansys CFX installed.",
)
@pytest.mark.asyncio
async def test_reconnect_after_disconnect() -> None:
    leaf = CFXMCP()

    connect = await _call_tool(
        leaf,
        "connect",
        connect_kwargs=_connect_kwargs(),
    )
    assert connect.status == "ok", connect.message

    first_disconnect = await _call_tool(leaf, "disconnect")
    assert first_disconnect["status"] == "ok"

    reconnect = await _call_tool(
        leaf,
        "connect",
        connect_kwargs=_connect_kwargs(),
    )
    assert reconnect.status == "ok", reconnect.message

    status = await _call_tool(leaf, "session_status")
    assert status.connected is True

    await _call_tool(leaf, "disconnect")


@pytest.mark.asyncio
async def test_validate_code_reports_syntax_error() -> None:
    leaf = CFXMCP()

    result = await _call_tool(leaf, "validate_code", code="def broken(:")

    assert result.status in {"ok", "error"}
