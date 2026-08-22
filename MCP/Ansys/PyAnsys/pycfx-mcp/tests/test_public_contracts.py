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

from typing import Any

import pytest

from ansys.cfx.mcp import CFXMCP
from ansys.cfx.mcp.common.backend import Backend
from ansys.cfx.mcp.common.models import ConnectResult, RunCodeResult

PUBLIC_TOOLS = (
    "session_status",
    "connect",
    "disconnect",
    "cfx_workflow",
    "cfx_model_context",
    "run_code",
    "validate_code",
)


class ContractBackend(Backend):
    kind = "pycfx"
    label = "Contract backend"

    def __init__(self) -> None:
        super().__init__()
        self.connected = False

    async def connect(self, **kwargs: Any) -> ConnectResult:
        self.connected = True
        return ConnectResult(status="ok", backend_kind=self.kind, endpoint="contract")

    def is_connected(self) -> bool:
        return self.connected

    async def disconnect(self) -> None:
        self.connected = False

    async def run_code(self, code: str, **kwargs: Any) -> RunCodeResult:
        return RunCodeResult(status="ok", stdout="stable\n", return_value={"ran": code})

    async def cfx_workflow(self, *, action: str, params: dict[str, Any] | None = None):
        return {"status": "ok", "action": action, "params": params or {}}

    async def cfx_model_context(
        self,
        *,
        action: str = "summary",
        params: dict[str, Any] | None = None,
        max_items: int = 20,
    ):
        return {"status": "ok", "action": action, "params": params or {}, "max_items": max_items}


async def _call_tool(leaf: CFXMCP, tool_name: str, **kwargs: Any):
    tool = await leaf.get_tool(tool_name)
    return await tool.fn(**kwargs)


def test_public_mcp_surface_stays_compact_and_stable() -> None:
    leaf = CFXMCP()

    assert set(leaf._exposed) == set(PUBLIC_TOOLS)
    assert {toolset["name"]: tuple(toolset["tools"]) for toolset in leaf.build_toolsets()} == {
        "connection": ("session_status", "connect", "disconnect"),
        "code-validation": ("validate_code",),
        "cfx-workflow": ("cfx_workflow",),
        "cfx-model-context": ("cfx_model_context",),
        "code-execution": ("run_code", "validate_code"),
    }


@pytest.mark.asyncio
async def test_public_mcp_tools_keep_response_contracts() -> None:
    backend = ContractBackend()
    leaf = CFXMCP()
    leaf._backends = {"pycfx": backend}
    leaf._active_kind = "pycfx"

    before_connect = await _call_tool(leaf, "session_status")
    assert before_connect.model_dump(include={"leaf", "connected", "backend_kind", "notes"}) == {
        "leaf": "cfx",
        "connected": False,
        "backend_kind": "pycfx",
        "notes": [],
    }

    connect = await _call_tool(leaf, "connect")
    assert connect.model_dump(include={"status", "backend_kind", "endpoint"}) == {
        "status": "ok",
        "backend_kind": "pycfx",
        "endpoint": "contract",
    }

    assert (await _call_tool(leaf, "cfx_workflow", action="status"))["status"] == "ok"
    assert (await _call_tool(leaf, "cfx_model_context", action="summary"))["max_items"] == 20

    assert (await _call_tool(leaf, "validate_code", code="x = 1")).status == "ok"
    assert (await _call_tool(leaf, "run_code", code="x = 1")).stdout == "stable\n"

    disconnect = await _call_tool(leaf, "disconnect")
    assert disconnect == {"status": "ok"}
    assert backend.is_connected() is False


@pytest.mark.asyncio
async def test_public_mcp_tools_return_typed_errors_for_bad_inputs() -> None:
    leaf = CFXMCP()

    missing_backend = await _call_tool(leaf, "connect", backend_kind="missing")
    assert missing_backend.model_dump(include={"status", "error_code"}) == {
        "status": "error",
        "error_code": "invalid_arguments",
    }

    empty_code = await _call_tool(leaf, "run_code", code=" ")
    assert empty_code.model_dump(include={"status", "error_code"}) == {
        "status": "error",
        "error_code": "invalid_arguments",
    }

    bad_code = await _call_tool(leaf, "validate_code", code="for")
    assert bad_code.status == "error"
    assert bad_code.error_code == "syntax_error"
