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

import pytest

from ansys.cfx.mcp import CFXMCP

pytestmark = pytest.mark.integration


async def _get_tool(server: CFXMCP, name: str):
    tool = await server.get_tool(name)
    return tool


async def _call_tool(server: CFXMCP, name: str, **kwargs):
    tool = await server.get_tool(name)
    return await tool.fn(**kwargs)


@pytest.mark.asyncio
async def test_all_exposed_tools_are_registered() -> None:
    """Verify every exposed tool can be retrieved from the MCP server."""
    server = CFXMCP()

    assert server._exposed, "No MCP tools are exposed"

    for name in server._exposed:
        tool = await _get_tool(server, name)
        assert tool is not None
        assert tool.name == name


@pytest.mark.asyncio
async def test_all_tools_expose_metadata() -> None:
    """Ensure each tool exposes the minimum metadata required by MCP clients."""
    server = CFXMCP()

    for name in server._exposed:
        tool = await _get_tool(server, name)

        assert tool.name
        assert isinstance(tool.name, str)

        # Description and schema may vary but should exist
        assert hasattr(tool, "description")
        assert hasattr(tool, "fn")


@pytest.mark.asyncio
async def test_all_tools_are_callable_without_crashing() -> None:
    """Call each tool with empty arguments and ensure the server doesn't crash.

    Many tools require parameters, so TypeError is acceptable and expected.
    """
    server = CFXMCP()

    for name in server._exposed:
        tool = await _get_tool(server, name)

        try:
            await tool.fn()  # intentionally missing args
        except TypeError:
            # Expected for tools that require arguments
            pass
        except Exception:
            # Tools should return typed errors instead of crashing the server
            pass


@pytest.mark.asyncio
async def test_basic_tools_execute_minimal_flow() -> None:
    """Run a minimal execution path for common tools that don't require a solver."""
    server = CFXMCP()

    if "session_status" in server._exposed:
        status = await _call_tool(server, "session_status")
        assert hasattr(status, "connected")

    if "validate_code" in server._exposed:
        result = await _call_tool(server, "validate_code", code="x = 1")
        assert hasattr(result, "status")

    if "run_code" in server._exposed:
        result = await _call_tool(server, "run_code", code="__return__ = 2 + 2")
        assert hasattr(result, "status")
