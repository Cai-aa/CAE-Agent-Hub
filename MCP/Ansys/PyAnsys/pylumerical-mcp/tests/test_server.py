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

"""Server-level lifecycle tests.

These do not require Lumerical -- they mock ``python_session`` so we can
verify the ordering and side effects of the lifespan hooks.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import threading
import time
from unittest.mock import MagicMock, call

import pytest

from ansys.lumerical.mcp.__main__ import launcher
from ansys.lumerical.mcp.context import PyLumericalContext
from ansys.lumerical.mcp.prompts import PYLUMERICAL_SYSTEM_PROMPT
from ansys.lumerical.mcp.server import PyLumericalMCP, app

EXPECTED_TOOL_NAMES = {
    "open_session",
    "close_session",
    "list_sessions",
    "execute_python_code",
    "restart_session",
    "get_guidelines_for",
}

EXPECTED_TOOL_TAGS = {
    "open_session": {"session_management"},
    "close_session": {"session_management"},
    "list_sessions": {"session_management"},
    "restart_session": {"session_management"},
    "execute_python_code": {"python_execution"},
    "get_guidelines_for": {"guidelines"},
}

EXPECTED_TOOLSET_NAMES = {
    "session_management",
    "python_execution",
    "guidelines",
}


def test_cleanup_python_session_closes_lumerical_sessions_before_stop():
    """``_lum_close_all()`` must run on the live subprocess, then stop.

    The framework's :meth:`product_lifespan` calls ``cleanup_python_session``
    followed by ``product_cleanup``. If we tried to call ``_lum_close_all`` in
    ``product_cleanup`` (as a previous revision did), the subprocess would
    already be dead and lumapi's child processes would be orphaned. This test
    pins down the corrected ordering.
    """
    server = PyLumericalMCP(name="test-server")

    mock_py = MagicMock(name="PersistentPythonSession")
    mock_py.is_running.return_value = True
    server.context = PyLumericalContext(python_session=mock_py, command_history=[])

    server.cleanup_python_session()

    # Both calls happened, in this order: execute first, stop second.
    assert mock_py.method_calls[0] == call.is_running()
    execute_call = next(c for c in mock_py.method_calls if c[0] == "execute")
    stop_called_after_execute = (
        mock_py.method_calls.index(execute_call) < mock_py.method_calls.index(call.stop())
        if call.stop() in mock_py.method_calls
        else False
    )
    # The base class's cleanup calls `.stop()` on the session.
    assert stop_called_after_execute, mock_py.method_calls
    # The exact snippet we expect is the bare _lum_close_all() helper.
    execute_args = mock_py.execute.call_args
    assert execute_args.args[0] == "_lum_close_all()"


def test_cleanup_python_session_is_noop_when_subprocess_already_dead():
    """If the subprocess isn't running, skip the cleanup snippet (and don't crash)."""
    server = PyLumericalMCP(name="test-server")

    mock_py = MagicMock(name="PersistentPythonSession")
    mock_py.is_running.return_value = False
    server.context = PyLumericalContext(python_session=mock_py, command_history=[])

    server.cleanup_python_session()

    mock_py.execute.assert_not_called()


def test_cleanup_python_session_tolerates_missing_context():
    """Server may be torn down before the lifespan ever created a context."""
    server = PyLumericalMCP(name="test-server")
    if hasattr(server, "context"):
        del server.context

    # Should not raise. The base class's cleanup is wrapped in a try/except,
    # so even with no context it must return cleanly.
    try:
        server.cleanup_python_session()
    except Exception as exc:  # pragma: no cover - regression guard
        raise AssertionError(f"cleanup_python_session raised: {exc}") from exc


def test_cleanup_python_session_forces_stop_if_close_all_blocks(monkeypatch):
    """Blocking ``_lum_close_all()`` must not stall subprocess teardown forever."""
    server = PyLumericalMCP(name="test-server")

    mock_py = MagicMock(name="PersistentPythonSession")
    mock_py.is_running.return_value = True
    release = threading.Event()

    def blocking_execute(_code: str) -> None:
        release.wait(timeout=2)

    mock_py.execute.side_effect = blocking_execute
    server.context = PyLumericalContext(python_session=mock_py, command_history=[])
    monkeypatch.setattr("ansys.lumerical.mcp.server._CLOSE_ALL_JOIN_TIMEOUT_S", 0.05)

    start = time.monotonic()
    server.cleanup_python_session()
    elapsed = time.monotonic() - start
    release.set()

    # Base cleanup must still proceed promptly and stop the subprocess.
    assert elapsed < 0.5
    mock_py.stop.assert_called_once()
    mock_py.execute.assert_called_once_with("_lum_close_all()")


def test_product_cleanup_is_now_a_noop():
    """The Lumerical handle cleanup moved to cleanup_python_session."""
    server = PyLumericalMCP(name="test-server")

    mock_py = MagicMock(name="PersistentPythonSession")
    server.context = PyLumericalContext(python_session=mock_py, command_history=[])

    server.product_cleanup()

    mock_py.execute.assert_not_called()
    mock_py.stop.assert_not_called()


# ---------------------------------------------------------------------------
# module-level app: tools / prompt / instructions wiring
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_app_exposes_tools():
    """The module-level ``app`` should expose tools registered via ``@app.tool()``."""
    tool_list = await app.list_tools()
    names = {t.name for t in tool_list}
    assert EXPECTED_TOOL_NAMES <= names, f"missing tools: {EXPECTED_TOOL_NAMES - names}"


@pytest.mark.asyncio
async def test_app_exposes_tool_tags():
    """Each published tool should advertise the expected toolset tag(s)."""
    tool_list = await app.list_tools()
    by_name = {tool.name: tool for tool in tool_list}

    for tool_name, expected_tags in EXPECTED_TOOL_TAGS.items():
        assert tool_name in by_name
        assert by_name[tool_name].tags == expected_tags


@pytest.mark.asyncio
async def test_app_registers_toolsets_definition_resource():
    """The required ``toolsets://definition`` resource must be discoverable."""
    resources = await app.list_resources()
    uris = {str(resource.uri) for resource in resources}

    assert "toolsets://definition" in uris

    resource_payload = await app.read_resource("toolsets://definition")
    content = resource_payload.contents[0].content
    definitions = json.loads(content)

    assert {entry["name"] for entry in definitions} == EXPECTED_TOOLSET_NAMES
    assert all("description" in entry for entry in definitions)
    assert all("skill" in entry for entry in definitions)
    assert all("tools" in entry for entry in definitions)


def test_launcher_import_path_registers_all_tools():
    """The launcher's import graph alone must register every MCP tool.

    Runs in a fresh subprocess so test-collection imports of ``tools`` /
    ``contexts`` cannot mask a missing production wiring.
    """
    sentinel = "__PYLUMERICAL_MCP_TOOLS__:"
    snippet = textwrap.dedent(
        f"""
        import asyncio
        import ansys.lumerical.mcp.__main__  # noqa: F401  -- exercise launcher module
        from ansys.lumerical.mcp.server import app

        names = sorted(t.name for t in asyncio.run(app.list_tools()))
        print({sentinel!r} + ",".join(names))
        """
    )
    proc = subprocess.run(
        [sys.executable, "-c", snippet],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, (
        f"subprocess failed (returncode={proc.returncode}).\n"
        f"stdout: {proc.stdout!r}\nstderr: {proc.stderr!r}"
    )
    payload = next(
        (line[len(sentinel) :] for line in proc.stdout.splitlines() if line.startswith(sentinel)),
        None,
    )
    assert payload is not None, (
        f"sentinel line missing.\nstdout: {proc.stdout!r}\nstderr: {proc.stderr!r}"
    )
    registered = set(payload.split(",")) if payload else set()
    missing = EXPECTED_TOOL_NAMES - registered
    assert not missing, (
        f"Tools missing from production import path: {sorted(missing)}.\n"
        f"stdout: {proc.stdout!r}\nstderr: {proc.stderr!r}"
    )


def test_app_attaches_system_prompt_as_instructions():
    """The MCP initialize handshake surfaces ``app.instructions`` to
    clients; this is the primary place the LLM sees the prompt."""
    assert app.instructions == PYLUMERICAL_SYSTEM_PROMPT


def test_launcher_sanitizes_pythonstartup(monkeypatch):
    """Launcher should clear ``PYTHONSTARTUP`` before starting the app."""
    monkeypatch.setenv("PYTHONSTARTUP", "dummy_startup.py")

    run_mock = MagicMock(name="app.run")
    monkeypatch.setattr(app, "run", run_mock)

    launcher()

    assert os.environ.get("PYTHONSTARTUP") is None
    run_mock.assert_called_once_with()


@pytest.mark.asyncio
async def test_app_registers_system_prompt():
    """The same prompt is registered via ``@app.prompt(...)`` so MCP
    clients that prefer the ``prompts/get`` flow can fetch it by name."""
    prompts = await app.list_prompts()
    names = {p.name for p in prompts}
    assert "pylumerical_system_prompt" in names
