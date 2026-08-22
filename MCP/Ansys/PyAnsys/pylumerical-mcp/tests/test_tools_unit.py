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

"""Unit tests for ``ansys.lumerical.mcp.tools`` with a mocked subprocess.

The tools dispatch every Lumerical interaction through
``PersistentPythonSession.execute``. We replace that with a ``MagicMock`` so
we can exercise the full tool layer without spawning a subprocess or having
Lumerical installed.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from unittest.mock import MagicMock

import pytest

from ansys.lumerical.mcp import tools
from ansys.lumerical.mcp._envelope import (
    _MAX_ERROR_CHARS,
    _MAX_STREAM_CHARS,
    _compact_execute_envelope,
)
from ansys.lumerical.mcp.context import PyLumericalContext, SessionInfo
from ansys.lumerical.mcp.contexts import get_guidelines_for

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_python_session() -> MagicMock:
    """Stand-in for :class:`ansys.common.mcp.PersistentPythonSession`."""
    return MagicMock(name="PersistentPythonSession")


@pytest.fixture
def app_ctx(mock_python_session) -> PyLumericalContext:
    return PyLumericalContext(
        python_session=mock_python_session,
        command_history=[],
    )


@pytest.fixture
def ctx(app_ctx) -> MagicMock:
    """Fake fastmcp Context whose lifespan_context is our app_ctx."""
    fake = MagicMock(name="Context")
    fake.request_context.lifespan_context = app_ctx
    return fake


def _success_result(stdout: str = "") -> dict:
    return {"success": True, "stdout": stdout, "stderr": "", "error": ""}


def _failure_result(error: str = "boom", stderr: str = "Traceback...") -> dict:
    return {"success": False, "stdout": "", "stderr": stderr, "error": error}


# ---------------------------------------------------------------------------
# open_session
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_open_session_success_registers_metadata(ctx, mock_python_session, app_ctx):
    mock_python_session.execute.return_value = _success_result(
        stdout='{"name": "fdtd1", "product": "fdtd", "filename": null, "hide": true}'
    )

    parsed = await tools.open_session(ctx, name="fdtd1", product="fdtd", hide=True)

    assert isinstance(parsed, dict)
    assert parsed["success"] is True
    assert parsed["data"]["name"] == "fdtd1"
    assert parsed["data"]["product"] == "fdtd"

    # local registry was updated
    assert "fdtd1" in app_ctx.sessions
    info = app_ctx.sessions["fdtd1"]
    assert isinstance(info, SessionInfo)
    assert info.product == "fdtd"
    assert info.hide is True

    # snippet routed through the subprocess
    snippet = mock_python_session.execute.call_args.args[0]
    assert "_lum_open(" in snippet
    assert "'fdtd1'" in snippet
    assert "'fdtd'" in snippet
    assert "hide=True" in snippet


@pytest.mark.asyncio
async def test_open_session_rejects_duplicate(ctx, mock_python_session, app_ctx):
    app_ctx.sessions["fdtd1"] = SessionInfo(name="fdtd1", product="fdtd")

    parsed = await tools.open_session(ctx, name="fdtd1", product="fdtd")

    assert parsed["success"] is False
    assert "already exists" in parsed["error"]
    # subprocess should NOT have been called
    mock_python_session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_open_session_subprocess_failure_does_not_register(ctx, mock_python_session, app_ctx):
    mock_python_session.execute.return_value = _failure_result(
        error="ValueError: bad product",
        stderr="Traceback (most recent call last)...",
    )

    parsed = await tools.open_session(ctx, name="oops", product="fdtd")

    assert parsed["success"] is False
    assert "oops" not in app_ctx.sessions


@pytest.mark.asyncio
async def test_open_session_failure_attempts_defensive_close(ctx, mock_python_session, app_ctx):
    """If the open snippet reports failure, we attempt a defensive _lum_close.

    The subprocess registry may actually contain the new session (e.g. lumapi
    emitted a noisy stderr line that our heuristic misidentified), so we issue
    a best-effort close to avoid stranding a ghost session that would block
    the next open_session with the same name.
    """
    mock_python_session.execute.return_value = _failure_result(
        error="some stderr noise",
        stderr="Error: license server unreachable",
    )

    parsed = await tools.open_session(ctx, name="ghosty", product="fdtd")

    assert parsed["success"] is False
    assert "ghosty" not in app_ctx.sessions
    # Two execute() calls: open snippet, then defensive close snippet.
    assert mock_python_session.execute.call_count == 2
    snippets = [c.args[0] for c in mock_python_session.execute.call_args_list]
    assert "_lum_open(" in snippets[0]
    assert snippets[1] == "_lum_print_json(_lum_close('ghosty'))"


@pytest.mark.asyncio
async def test_open_session_uses_env_default_for_hide(
    ctx, mock_python_session, app_ctx, monkeypatch
):
    monkeypatch.setenv("LUMERICAL_HIDE_GUI", "0")
    mock_python_session.execute.return_value = _success_result(stdout='{"name":"s1"}')

    await tools.open_session(ctx, name="s1", product="fdtd")
    snippet = mock_python_session.execute.call_args.args[0]
    assert "hide=False" in snippet
    assert app_ctx.sessions["s1"].hide is False


@pytest.mark.asyncio
async def test_open_session_env_default_hide_true_flows_through(
    ctx, mock_python_session, app_ctx, monkeypatch
):
    """When LUMERICAL_HIDE_GUI=1 and the caller omits ``hide``, the env-var
    default must reach the snippet (mirror of the False case above).

    Regression guard for the bug where an LLM client always passed
    ``hide=True`` explicitly: even though the snippet text was the same
    in that case, the explicit-arg path bypasses the env var entirely
    and prevents users from flipping GUI visibility globally. This test
    plus its False-case sibling pin down the contract that an omitted
    ``hide`` argument *always* defers to ``LUMERICAL_HIDE_GUI``.
    """
    monkeypatch.setenv("LUMERICAL_HIDE_GUI", "1")
    mock_python_session.execute.return_value = _success_result(stdout='{"name":"s2"}')

    await tools.open_session(ctx, name="s2", product="fdtd")
    snippet = mock_python_session.execute.call_args.args[0]
    assert "hide=True" in snippet
    assert app_ctx.sessions["s2"].hide is True


# ---------------------------------------------------------------------------
# close_session
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_close_session_success(ctx, mock_python_session, app_ctx):
    app_ctx.sessions["s1"] = SessionInfo(name="s1", product="fdtd")
    mock_python_session.execute.return_value = _success_result(stdout='{"closed": "s1"}')

    parsed = await tools.close_session(ctx, name="s1")

    assert parsed["success"] is True
    assert parsed["data"]["closed"] == "s1"
    assert "s1" not in app_ctx.sessions

    snippet = mock_python_session.execute.call_args.args[0]
    assert snippet == "_lum_print_json(_lum_close('s1'))"


@pytest.mark.asyncio
async def test_close_session_unknown_name(ctx, mock_python_session, app_ctx):
    parsed = await tools.close_session(ctx, name="ghost")

    assert parsed["success"] is False
    assert "ghost" in parsed["error"]
    mock_python_session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_close_session_retains_local_on_subprocess_failure(ctx, mock_python_session, app_ctx):
    """A failed close should keep the local entry so the user can retry."""
    app_ctx.sessions["s1"] = SessionInfo(name="s1", product="fdtd")
    mock_python_session.execute.return_value = _failure_result()

    parsed = await tools.close_session(ctx, name="s1")

    assert parsed["success"] is False
    # Local entry is retained so the caller can retry the close.
    assert "s1" in app_ctx.sessions
    # The envelope advertises that retention so the agent isn't surprised.
    assert parsed.get("retained") is True


@pytest.mark.asyncio
async def test_close_session_times_out_when_subprocess_wedged(
    ctx, mock_python_session, app_ctx, monkeypatch
):
    """A wedged subprocess must not hang the close_session tool indefinitely.

    Pre-fix, ``close_session`` called ``execute()`` synchronously and
    inherited its unbounded wait. A bounded ``_CLOSE_SESSION_TIMEOUT_S``
    must instead surface a clean failure envelope so the agent can fall
    back to ``restart_session`` to recover.
    """
    monkeypatch.setattr(tools, "_CLOSE_SESSION_TIMEOUT_S", 0.5)
    app_ctx.sessions["s1"] = SessionInfo(name="s1", product="fdtd")

    # Released in finally so the orphaned thread doesn't outlive the test.
    release = threading.Event()

    def wedged_execute(_code: str) -> dict:
        release.wait(timeout=10.0)
        return _success_result(stdout='{"closed": "s1"}')

    mock_python_session.execute.side_effect = wedged_execute

    try:
        start = time.monotonic()
        parsed = await tools.close_session(ctx, name="s1")
        elapsed = time.monotonic() - start
    finally:
        release.set()

    assert elapsed < 2.0, f"close_session hung for {elapsed:.2f}s before timing out"
    assert parsed["success"] is False
    assert parsed.get("timed_out") is True
    assert parsed.get("retained") is True
    assert "timed out" in parsed["error"].lower()
    assert "restart_session" in parsed["error"]
    assert "s1" in app_ctx.sessions


# ---------------------------------------------------------------------------
# restart_session
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_restart_session_success_clears_local_registry(ctx, mock_python_session, app_ctx):
    """A successful restart wipes the local sessions registry.

    The MCP-level ``app.sessions`` dict mirrors Lumerical handles that live
    *inside* the subprocess. After ``PersistentPythonSession.restart`` kills
    + respawns that subprocess, the old handles are gone, so the local
    registry must be cleared. The response envelope surfaces the dropped
    names so the agent can decide what to re-open.
    """
    app_ctx.sessions["fdtd1"] = SessionInfo(name="fdtd1", product="fdtd")
    app_ctx.sessions["mode1"] = SessionInfo(name="mode1", product="mode")
    mock_python_session.restart.return_value = {
        "success": True,
        "message": "Session restarted successfully.",
    }

    parsed = await tools.restart_session(ctx)

    assert parsed["success"] is True
    assert parsed["data"]["restarted"] is True
    # cleared_sessions is the sorted list of dropped names.
    assert parsed["data"]["cleared_sessions"] == ["fdtd1", "mode1"]
    assert app_ctx.sessions == {}
    mock_python_session.restart.assert_called_once_with()


@pytest.mark.asyncio
async def test_restart_session_failure_preserves_local_registry(ctx, mock_python_session, app_ctx):
    """If the restart fails, the local registry is left intact.

    A failed restart means the subprocess is in an indeterminate state.
    Wiping the local metadata in that case would lose information the
    operator needs to reason about what to do next.
    """
    app_ctx.sessions["fdtd1"] = SessionInfo(name="fdtd1", product="fdtd")
    mock_python_session.restart.return_value = {
        "success": False,
        "error": "Failed to restart session: Python executable not found",
    }

    parsed = await tools.restart_session(ctx)

    assert parsed["success"] is False
    assert "Failed to restart session" in parsed["error"]
    assert "fdtd1" in app_ctx.sessions


@pytest.mark.asyncio
async def test_restart_session_handles_missing_python_session(ctx, app_ctx):
    """An unconfigured app context yields a clean failure envelope."""
    app_ctx.python_session = None  # type: ignore[assignment]

    parsed = await tools.restart_session(ctx)

    assert parsed["success"] is False
    assert "No Python session available" in parsed["error"]


@pytest.mark.asyncio
async def test_restart_session_succeeds_while_execute_is_wedged(ctx, mock_python_session, app_ctx):
    """The restart_session tool returns promptly with a wedged execute parked.

    Tool-layer wiring guard for the user-reported parallel scenario: a
    previous ``execute_python_code`` is in flight when the agent dispatches
    ``restart_session``. The model is shape-only (the mock doesn't share
    ``_execution_lock`` with execute), so the real-subprocess deadlock is
    covered by ``test_restart_unblocks_wedged_execute_holding_lock`` in
    ``tests/test_persistent_session.py``. What this test guards is:
    ``restart_session`` is offloaded via ``asyncio.to_thread``, the local
    registry is cleared on success, and the parallel ``execute_python_code``
    completes once restart releases its gate.
    """
    app_ctx.sessions["fdtd1"] = SessionInfo(name="fdtd1", product="fdtd")

    # Models the captured-proc fix: the wedged execute() unblocks as soon
    # as restart() "kills" the subprocess.
    release_execute = threading.Event()

    def wedged_execute(_code: str) -> dict:
        release_execute.wait(timeout=30.0)
        return {
            "success": False,
            "stdout": "",
            "stderr": "",
            "error": "Subprocess exited with code -9 before execution completed.",
        }

    def restart_kills_wedged_execute() -> dict:
        release_execute.set()
        return {"success": True, "message": "Session restarted successfully."}

    mock_python_session.execute.side_effect = wedged_execute
    mock_python_session.restart.side_effect = restart_kills_wedged_execute

    wedged_task = asyncio.create_task(tools.execute_python_code(ctx, code="hang_forever()"))
    await asyncio.sleep(0.05)  # let the worker thread enter execute()

    start = time.monotonic()
    parsed = await asyncio.wait_for(tools.restart_session(ctx), timeout=5.0)
    elapsed = time.monotonic() - start

    assert parsed["success"] is True, parsed
    assert parsed["data"]["restarted"] is True
    assert "fdtd1" in parsed["data"]["cleared_sessions"]
    assert app_ctx.sessions == {}
    assert elapsed < 3.0, f"restart_session took {elapsed:.2f}s with a wedged execute parked"

    wedged_result = await asyncio.wait_for(wedged_task, timeout=5.0)
    assert wedged_result["success"] is False
    assert "Subprocess exited" in (wedged_result.get("error") or "")


@pytest.mark.asyncio
async def test_restart_session_does_not_block_event_loop(ctx, mock_python_session):
    """The restart must be offloaded to a worker thread.

    ``PersistentPythonSession.restart`` blocks for several seconds while it
    tears down the old subprocess and spawns a fresh one. If the MCP tool
    called it synchronously on the asyncio event loop, every other
    in-flight tool / ticker coroutine would stall (the same class of bug
    the existing execute_python_code parallel tests cover). We pin the
    asyncio.to_thread offload by checking that an asyncio ticker keeps
    making progress while restart() is sleeping in the worker thread.
    """
    restart_lock = threading.Lock()

    def slow_restart():
        with restart_lock:
            time.sleep(0.3)
        return {"success": True}

    mock_python_session.restart.side_effect = slow_restart

    loop_ticks = 0
    done = asyncio.Event()

    async def ticker():
        nonlocal loop_ticks
        while not done.is_set():
            await asyncio.sleep(0.01)
            loop_ticks += 1

    ticker_task = asyncio.create_task(ticker())
    try:
        parsed = await tools.restart_session(ctx)
    finally:
        done.set()
        await ticker_task

    assert parsed["success"] is True
    # If restart() ran on the event-loop thread, the ticker couldn't tick
    # while it was sleeping. With asyncio.to_thread it can.
    assert loop_ticks >= 5


# ---------------------------------------------------------------------------
# list_sessions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_sessions_empty(ctx, mock_python_session):
    parsed = await tools.list_sessions(ctx)
    assert parsed["success"] is True
    assert parsed["data"] == []
    mock_python_session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_list_sessions_returns_metadata(ctx, app_ctx):
    app_ctx.sessions["a"] = SessionInfo(name="a", product="fdtd", filename=None)
    app_ctx.sessions["b"] = SessionInfo(name="b", product="mode", filename="x.lms")

    parsed = await tools.list_sessions(ctx)

    assert parsed["success"] is True
    names = {item["name"] for item in parsed["data"]}
    assert names == {"a", "b"}
    by_name = {item["name"]: item for item in parsed["data"]}
    assert by_name["b"]["filename"] == "x.lms"
    assert by_name["a"]["product"] == "fdtd"


# ---------------------------------------------------------------------------
# execute_python_code
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_python_code_round_trips_success(ctx, mock_python_session):
    """A successful subprocess execute round-trips into a clean envelope."""
    mock_python_session.execute.return_value = _success_result(stdout="output line")

    parsed = await tools.execute_python_code(ctx, code="print(1+1)")

    assert isinstance(parsed, dict)
    assert parsed["success"] is True
    assert parsed["stdout"] == "output line"

    # The snippet must have been sent through the persistent session.
    assert mock_python_session.execute.call_args.args[0] == "print(1+1)"


# ---------------------------------------------------------------------------
# _compact_execute_envelope -- the size-cap / dedupe wrapper that keeps a
# noisy JSON envelope from blowing up the agent's context window.
# ---------------------------------------------------------------------------


def test_compact_envelope_drops_duplicate_error_field():
    """When stderr and error contain the same content, drop the error duplicate."""
    parsed = _compact_execute_envelope(
        {
            "success": False,
            "stdout": "",
            "stderr": "Traceback (most recent call last):\nValueError: boom",
            "error": "Traceback (most recent call last):\nValueError: boom",
        }
    )
    assert parsed["success"] is False
    assert "stderr" in parsed
    assert "error" not in parsed


def test_compact_envelope_keeps_distinct_error_summary():
    """A short summary that's distinct from stderr is preserved."""
    parsed = _compact_execute_envelope(
        {
            "success": False,
            "stdout": "",
            "stderr": "Traceback (most recent call last):\nValueError: boom",
            "error": "ValueError: boom",
        }
    )
    assert parsed["error"] == "ValueError: boom"


def test_compact_envelope_truncates_oversized_stderr():
    """Streams above ``_MAX_STREAM_CHARS`` get middle-truncated with a marker."""
    huge_stderr = "A" * 10000
    parsed = _compact_execute_envelope(
        {
            "success": False,
            "stdout": "",
            "stderr": huge_stderr,
            "error": "ValueError: boom",
        }
    )
    new_stderr = parsed["stderr"]
    assert len(new_stderr) <= _MAX_STREAM_CHARS
    assert "characters omitted" in new_stderr


def test_compact_envelope_truncated_stderr_preserves_head_and_tail():
    """Middle-truncation must retain something from both ends of the input."""
    head_marker = "HEAD_OF_OUTPUT"
    tail_marker = "TAIL_OF_OUTPUT"
    huge_stderr = head_marker + ("X" * 10000) + tail_marker
    parsed = _compact_execute_envelope(
        {
            "success": False,
            "stdout": "",
            "stderr": huge_stderr,
            "error": "ValueError: boom",
        }
    )
    assert head_marker in parsed["stderr"]
    assert tail_marker in parsed["stderr"]


def test_compact_envelope_full_response_under_limit():
    """End-to-end: a worst-case failure envelope must stay under ~10 kB.

    Now that the tool returns a dict, the budget assertion is measured
    against the JSON-serialized form (what the MCP transport actually
    sends). The cap is now exactly what it claims to be -- no hidden 2x
    inflation from double JSON encoding.
    """
    huge = "X" * 20000
    out = _compact_execute_envelope(
        {
            "success": False,
            "stdout": huge,
            "stderr": huge,
            "error": "ValueError: boom",
        }
    )
    assert len(json.dumps(out)) < 10_000


def test_compact_envelope_under_limit_with_distinct_huge_error():
    """All three streams huge + distinct must still fit under the cap.

    Without the tighter ``_MAX_ERROR_CHARS`` budget for ``error``, three
    streams capped at ``_MAX_STREAM_CHARS`` each would push past 10 kB
    before JSON overhead. The ``error`` field is semantically a summary,
    so we cap it tighter -- this test guards the worst-case math.
    """
    huge_a = "A" * 20000
    huge_b = "B" * 20000
    huge_c = "C" * 20000
    out = _compact_execute_envelope(
        {
            "success": False,
            "stdout": huge_a,
            "stderr": huge_b,
            "error": huge_c,  # distinct from stderr -- dedup won't kick in
        }
    )
    assert len(json.dumps(out)) < 10_000
    assert len(out["error"]) <= _MAX_ERROR_CHARS


def test_compact_envelope_passthrough_success_envelope():
    """A small success envelope should round-trip unchanged in content."""
    parsed = _compact_execute_envelope(
        {"success": True, "stdout": "ok", "stderr": "", "message": "Python ran"}
    )
    assert parsed["success"] is True
    assert parsed["stdout"] == "ok"
    assert parsed["message"] == "Python ran"


def test_compact_envelope_passes_through_non_dict():
    """Non-dict input must not be mangled (defensive guard)."""
    not_a_dict = ["just", "a", "list"]
    assert _compact_execute_envelope(not_a_dict) is not_a_dict


def test_compact_envelope_preserves_literal_backslashes_in_stderr():
    """Regression guard for the structured-content (no-double-escape) fix.

    The user-visible symptom of the old JSON-string return path was a
    Windows traceback like ``c:\\AnsysDev\\repos\\...`` arriving at the
    client as ``c:\\\\AnsysDev\\\\repos\\\\...`` -- a literal ``\\`` had
    been JSON-encoded twice. Now that the tool returns a plain dict, the
    envelope must carry exactly one backslash per source-code backslash;
    the second escape layer only appears when (and exactly when) the
    transport serializes the dict to JSON.
    """
    stderr = (
        "Traceback (most recent call last):\n"
        '  File "<stdin>", line 1, in <module>\n'
        '  File "c:\\AnsysDev\\repos\\pylumerical-mcp\\.venv\\Lib\\site-packages\\lumapi.py"\n'
        "ValueError: boom"
    )
    parsed = _compact_execute_envelope(
        {"success": False, "stdout": "", "stderr": stderr, "error": "ValueError: boom"}
    )
    # The literal backslash count in the live dict equals the source's.
    assert parsed["stderr"].count("\\") == stderr.count("\\")
    # And a single JSON-encode pass (what FastMCP / the MCP transport
    # will do) doubles each backslash exactly once, never twice.
    once_encoded = json.dumps(parsed)
    assert once_encoded.count("\\\\") == stderr.count("\\")
    assert "\\\\\\\\" not in once_encoded


@pytest.mark.asyncio
async def test_execute_python_code_applies_size_cap(ctx, mock_python_session):
    """The tool wrapper must invoke the compaction step before returning."""
    huge = "Y" * 20000

    mock_python_session.execute.return_value = {
        "success": False,
        "stdout": huge,
        "stderr": huge,
        "error": huge,  # duplicate of stderr -- must be dropped
    }

    parsed = await tools.execute_python_code(ctx, code="boom")

    assert len(json.dumps(parsed)) < 10_000
    assert parsed["success"] is False
    assert "error" not in parsed
    assert "characters omitted" in parsed["stderr"]


# ---------------------------------------------------------------------------
# execute_python_code -- clean error envelopes for bad lumapi calls.
#
# These tests pin the end-to-end contract that a snippet which raises in the
# subprocess produces a tight JSON envelope (``success=False``, short
# ``error`` summary, no duplicate of ``stderr``, total response well under
# the 10 kB budget). Each test feeds a realistic
# ``LumericalPersistentPythonSession.execute`` return dict (full traceback in
# ``stderr``, short ``ExceptionName: ...`` summary in ``error``) into the
# mocked persistent session and verifies the wrapper preserves the summary
# while applying compaction.
#
# Real-subprocess coverage of the upstream summarization (REPL-prompt
# stripping, ``_summarize_exception`` for dotted lumapi paths, etc.) lives
# in tests/test_persistent_session.py; these tests guard the tool-level
# wiring instead.
# ---------------------------------------------------------------------------


def _exec_session_result(stderr: str, error: str, *, stdout: str = "") -> dict:
    """Build a ``PersistentPythonSession.execute``-shaped result for a failure.

    Mirrors what ``LumericalPersistentPythonSession.execute`` would emit for
    a snippet that raised: a full traceback in ``stderr``, a short
    ``ExceptionName: <message>`` summary in ``error``.
    """
    return {"success": False, "stdout": stdout, "stderr": stderr, "error": error}


@pytest.mark.asyncio
async def test_execute_python_code_returns_clean_envelope_on_lumapi_traceback(
    ctx, mock_python_session
):
    """A real LumApiError traceback (dotted exception path) round-trips cleanly.

    Locks in: ``success=False``, the short ``LumApiError: ...`` summary
    survives in ``error``, the full traceback survives in ``stderr``,
    ``error`` is NOT a byte-for-byte duplicate of ``stderr``, and the
    total envelope stays within the 10 kB context-window budget.
    """
    stderr = (
        "Traceback (most recent call last):\n"
        '  File "<stdin>", line 1, in <module>\n'
        "    fdtd.set('x span', 1e-6)\n"
        "ansys.api.lumerical.lumapi.LumApiError: "
        "\"in set, the requested property 'x span' was not found\""
    )
    error = (
        "ansys.api.lumerical.lumapi.LumApiError: "
        "\"in set, the requested property 'x span' was not found\""
    )

    mock_python_session.execute.return_value = _exec_session_result(stderr, error)

    parsed = await tools.execute_python_code(ctx, code="fdtd.set('x span', 1e-6)")

    assert parsed["success"] is False
    assert parsed["error"].startswith("ansys.api.lumerical.lumapi.LumApiError")
    assert "x span" in parsed["error"]
    assert parsed["stderr"] != parsed["error"]
    assert "Traceback" in parsed["stderr"]
    assert len(json.dumps(parsed)) < 10_000


@pytest.mark.asyncio
async def test_execute_python_code_attribute_error_on_typo_method(ctx, mock_python_session):
    """A typo'd lumapi method name produces a clean ``AttributeError`` summary."""
    stderr = (
        "Traceback (most recent call last):\n"
        '  File "<stdin>", line 1, in <module>\n'
        "    fdtd.addrct(name='r1')\n"
        "AttributeError: 'FDTD' object has no attribute 'addrct'"
    )
    error = "AttributeError: 'FDTD' object has no attribute 'addrct'"

    mock_python_session.execute.return_value = _exec_session_result(stderr, error)

    parsed = await tools.execute_python_code(ctx, code="fdtd.addrct(name='r1')")

    assert parsed["success"] is False
    assert parsed["error"].startswith("AttributeError:")
    assert "addrct" in parsed["error"]
    assert parsed["error"] != parsed["stderr"]
    assert len(json.dumps(parsed)) < 10_000


@pytest.mark.asyncio
async def test_execute_python_code_keyerror_on_unknown_session(ctx, mock_python_session):
    """``_lum_get('does_not_exist')`` -> KeyError with a clean summary."""
    stderr = (
        "Traceback (most recent call last):\n"
        '  File "<stdin>", line 1, in <module>\n'
        "    _lum_get('does_not_exist')\n"
        '  File "<startup>", line 130, in _lum_get\n'
        "KeyError: \"No session 'does_not_exist'. Open one with open_session().\""
    )
    error = "KeyError: \"No session 'does_not_exist'. Open one with open_session().\""

    mock_python_session.execute.return_value = _exec_session_result(stderr, error)

    parsed = await tools.execute_python_code(ctx, code="_lum_get('does_not_exist')")

    assert parsed["success"] is False
    assert parsed["error"].startswith("KeyError:")
    assert "does_not_exist" in parsed["error"]
    assert parsed["error"] != parsed["stderr"]
    assert len(json.dumps(parsed)) < 10_000


@pytest.mark.asyncio
async def test_execute_python_code_syntax_error_on_bad_snippet(ctx, mock_python_session):
    """A SyntaxError (no ``Traceback`` header) still produces a clean envelope.

    The persistent-session ``_EXCEPTION_RE`` matches both forms; this test
    confirms the tool wrapper preserves the summary when the framework
    returns a SyntaxError-shaped payload.
    """
    stderr = '  File "<stdin>", line 1\n    def foo(:\n            ^\nSyntaxError: invalid syntax'
    error = "SyntaxError: invalid syntax"

    mock_python_session.execute.return_value = _exec_session_result(stderr, error)

    parsed = await tools.execute_python_code(ctx, code="def foo(:")

    assert parsed["success"] is False
    assert parsed["error"].startswith("SyntaxError:")
    assert parsed["error"] != parsed["stderr"]
    assert "invalid syntax" in parsed["error"]
    assert len(json.dumps(parsed)) < 10_000


# ---------------------------------------------------------------------------
# Parallel-tool-call behaviour.
#
# Regression coverage for the "Cannot read properties of undefined (reading
# 'invoke')" client-side error that fired when Cursor issued multiple MCP
# tool calls in parallel. Root cause: the subprocess tools were ``async def``
# but called ``LumericalPersistentPythonSession.execute`` synchronously, and
# that helper's polling loop never yields to the asyncio event loop. While
# one tool's execute() was in flight, the whole FastMCP event loop was
# frozen -- no other tool coroutine could run, the stdio transport couldn't
# read new requests or write responses, and the client surfaced the
# JS-side TypeError for the parked calls.
#
# The fix offloads each ``session.execute(...)`` call to a worker thread via
# ``asyncio.to_thread``. The existing ``threading.Lock`` inside
# ``execute`` still serializes subprocess access (one stdin, one snippet at
# a time -- correct), but the event loop stays responsive so tier-2 tools
# like ``get_guidelines_for`` (sync ``def``, auto-threadpooled by FastMCP)
# can run truly in parallel with subprocess work.
#
# Both tests below would fail with the pre-fix code: the slow synchronous
# ``execute()`` blocks the loop, ``asyncio.gather`` ends up serialized, and
# the wall time roughly doubles.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_static_tool_runs_in_parallel_with_slow_subprocess_tool(ctx, mock_python_session):
    """A static (non-subprocess) operation must not be stalled by a slow tool.

    Models the user-reported scenario: agent dispatches ``execute_python_code``
    (slow, subprocess-bound) and a guideline lookup in the same turn. With
    the pre-fix synchronous execute() blocking the event loop, the static
    lookup would queue behind the slow one. The fix offloads execute() to a
    worker thread, so the static op completes immediately even though the
    subprocess call is still sleeping.
    """
    slow_duration = 0.3
    static_started = threading.Event()
    observed_static_during_execute = {"value": False}

    def slow_execute(code):  # noqa: ARG001
        deadline = time.monotonic() + slow_duration
        while time.monotonic() < deadline:
            if static_started.is_set():
                observed_static_during_execute["value"] = True
            time.sleep(0.01)
        return _success_result(stdout="done")

    mock_python_session.execute.side_effect = slow_execute

    async def static_lookup():
        # Force at least one event-loop yield before publishing completion so
        # this coroutine cannot "finish instantly" before the subprocess call
        # starts. If ``execute_python_code`` blocks the loop thread, this line
        # can't run until after the slow execute returns.
        await asyncio.sleep(0.05)
        static_started.set()
        return get_guidelines_for("workflow")

    start = time.monotonic()
    exec_result, static_result = await asyncio.gather(
        tools.execute_python_code(ctx, code="long_running_snippet()"),
        static_lookup(),
    )
    elapsed = time.monotonic() - start

    # Subprocess call completed normally.
    assert exec_result["success"] is True
    assert exec_result["stdout"] == "done"

    # Static lookup got its markdown content back.
    assert isinstance(static_result, str)
    assert "Lumerical MCP Workflow" in static_result

    # Deterministic regression signal: the static coroutine must be able to
    # run while execute() is still in flight. With pre-fix synchronous
    # execute(), the event loop is blocked and this remains False.
    assert observed_static_during_execute["value"] is True

    # Keep a loose wall-time bound as a secondary sanity check.
    assert elapsed < 0.8


@pytest.mark.asyncio
async def test_two_subprocess_tools_both_succeed_in_parallel(ctx, mock_python_session, app_ctx):
    """Two subprocess tools issued in parallel both complete without raising.

    Both calls go through ``asyncio.to_thread``; the mock's ``.execute`` is
    not actually thread-locked, but the assertion is shape-only: both
    coroutines return clean envelopes and both sessions land in the local
    registry. This guards against any regression where the
    ``asyncio.to_thread`` wrapping is accidentally dropped from one of the
    call sites (which would re-introduce the event-loop-blocking bug).
    """

    execute_lock = threading.Lock()

    def make_open_payload(name):
        return _success_result(
            stdout=json.dumps({"name": name, "product": "fdtd", "filename": None, "hide": True})
        )

    def execute_router(code):
        # Mirror production behaviour: one subprocess, one snippet at a time.
        with execute_lock:
            time.sleep(0.2)
        # Pick the right success payload based on which session name appears
        # in the snippet. Both ``open_session`` calls produce snippets that
        # quote their session name, so a substring match is enough.
        if "'fdtd_a'" in code:
            return make_open_payload("fdtd_a")
        if "'fdtd_b'" in code:
            return make_open_payload("fdtd_b")
        return _success_result()

    mock_python_session.execute.side_effect = execute_router

    loop_ticks = 0
    done = asyncio.Event()

    async def ticker():
        nonlocal loop_ticks
        while not done.is_set():
            await asyncio.sleep(0.01)
            loop_ticks += 1

    ticker_task = asyncio.create_task(ticker())
    try:
        parsed_a, parsed_b = await asyncio.gather(
            tools.open_session(ctx, name="fdtd_a", product="fdtd"),
            tools.open_session(ctx, name="fdtd_b", product="fdtd"),
        )
    finally:
        done.set()
        await ticker_task

    assert parsed_a["success"] is True
    assert parsed_b["success"] is True
    assert {parsed_a["data"]["name"], parsed_b["data"]["name"]} == {"fdtd_a", "fdtd_b"}

    # Both ended up in the local registry.
    assert {"fdtd_a", "fdtd_b"}.issubset(app_ctx.sessions.keys())

    # Deterministic regression signal: if either open_session path performs a
    # direct synchronous execute() on the event-loop thread, the ticker won't
    # run during the sleeps above (or will tick only trivially).
    assert loop_ticks >= 5
