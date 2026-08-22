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

"""Unit tests for :class:`LumericalPersistentPythonSession`.

The behaviour we care about most: a code path that is **silent for longer than
0.5 s** must still return its eventual stdout. The base
:class:`ansys.common.mcp.PersistentPythonSession.execute` would lose this
output (its hard-coded 5*0.1 s "no data" break fires before the marker
arrives). Lumerical's ``FDTD()`` startup is the real-world example; here we
simulate it with a plain ``time.sleep`` so the test stays self-contained and
fast (~2 s).

We also pin the unbounded-execution contract: ``execute`` has no timeout-
driven early return (see the module docstring of ``persistent_session.py``
for why), so hung snippets are recovered out-of-band via
:meth:`PersistentPythonSession.restart`. The subprocess-kill / restart tests
below pin both halves of that recovery flow.
"""

from __future__ import annotations

import sys
import threading
import time

import pytest

from ansys.lumerical.mcp.persistent_session import (
    LumericalPersistentPythonSession,
    _build_envelope,
    _stderr_indicates_exception,
    _strip_repl_prompts,
    _summarize_exception,
)


@pytest.fixture
def session(monkeypatch):
    """A started persistent Python session, torn down after the test."""
    # These unit tests instantiate sessions directly (outside launcher), so
    # clear editor-injected startup hooks that print banner text in REPL mode.
    monkeypatch.delenv("PYTHONSTARTUP", raising=False)
    s = LumericalPersistentPythonSession(python_executable=sys.executable)
    started = s.start()
    assert started["success"], started
    yield s
    s.stop()


def test_execute_simple_print_round_trips(session: LumericalPersistentPythonSession):
    result = session.execute("print('hello')")
    assert result["success"], result
    assert result["stdout"].strip() == "hello"


def test_execute_recovers_output_after_silent_pause(
    session: LumericalPersistentPythonSession,
):
    """Code that is silent for >0.5 s must still deliver its trailing output.

    This is the exact pattern that ``FDTD()`` triggers: several seconds of
    C-level work followed by a Python-side ``print``. The base class's 0.5 s
    no-data safety break would discard the print; our subclass must not.
    """
    result = session.execute("import time; time.sleep(1.5); print('LATE')")
    assert result["success"], result
    assert "LATE" in result["stdout"]


def test_execute_preserves_state_between_calls(
    session: LumericalPersistentPythonSession,
):
    session.execute("x = 41")
    result = session.execute("print(x + 1)")
    assert result["stdout"].strip() == "42"


def test_execute_does_not_terminate_on_legacy_marker_text(
    session: LumericalPersistentPythonSession,
):
    """A snippet that prints the legacy marker text must round-trip cleanly.

    Pre-uuid-marker, the module-level ``_MARKER`` constant was matched by
    substring, so this snippet's own ``print('___EXECUTION_COMPLETE___')``
    would terminate the wait loop **before** the framework-appended marker
    arrived; the captured stdout would have been the wrong value and the
    next ``execute()`` would have started inheriting the framework marker
    as stale data. The per-call uuid marker (``___EXEC_<uuid>___``)
    eliminates this collision class by construction.
    """
    result = session.execute("print('___EXECUTION_COMPLETE___')")
    assert result["success"], result
    assert "___EXECUTION_COMPLETE___" in result["stdout"]


def test_execute_detects_marker_after_non_newline_stdout(
    session: LumericalPersistentPythonSession,
):
    """Marker detection must survive snippets that skip trailing newlines.

    ``python -i`` can flush ``<user_output><marker>`` as a single line when
    the snippet writes to stdout without a trailing newline (for example
    ``print(..., end='')``). The marker detector must
    still terminate and preserve the user-output prefix.
    """
    result = session.execute("print('prefix', end='', flush=True)")
    assert result["success"], result
    assert result["stdout"] == "prefix"


def test_execute_error_field_is_short_summary_not_duplicate_of_stderr(
    session: LumericalPersistentPythonSession,
):
    """The ``error`` field must be a brief summary, not a copy of ``stderr``.

    Shipping the full traceback verbatim in both ``stderr`` and
    ``error`` doubles the payload, wastes the agent's context-window
    budget on duplicate text.
    """
    result = session.execute("raise ValueError('boom')")
    assert not result["success"]
    assert result["stderr"]  # full traceback present here
    assert result["error"]  # short summary present here
    assert result["error"] != result["stderr"]
    # The summary is the final ``XxxError: ...`` line of the traceback.
    assert result["error"].startswith("ValueError")
    assert "boom" in result["error"]
    # And it's short -- well under the full traceback length.
    assert len(result["error"]) < 200


def test_execute_strips_repl_prompts_from_stderr(
    session: LumericalPersistentPythonSession,
):
    """``python -u -i`` echoes ``>>> ``/``... `` prompts to stderr; we drop them.

    Otherwise dozens of leading prompts accumulate on the line preceding each
    Traceback header (e.g. ``">>> >>> >>> Traceback..."``) and bloat the
    response with no information value.
    """
    result = session.execute("raise ValueError('boom')")
    # No standalone prompt line should remain.
    for line in result["stderr"].splitlines():
        assert not line.startswith(">>> "), line
        assert not line.startswith("... "), line
        assert line.strip() != ">>>", line
        assert line.strip() != "...", line


def test_execute_surfaces_subprocess_death_instead_of_hanging(
    session: LumericalPersistentPythonSession,
):
    """A subprocess that dies mid-execute must produce a distinct envelope.

    Pre-liveness-check, ``execute`` had no timeout *and* no health check, so
    a segfault / OOM / accidental ``os._exit()`` in user code would leave
    the polling loop spinning forever waiting for a marker that would
    never arrive. The periodic ``self.process.poll()`` inside the wait
    loop must detect the death within ~1 s and return a
    ``"Subprocess exited with code N..."`` envelope.
    """
    proc = session.process
    assert proc is not None

    blocked: dict[str, object] = {}

    def hang() -> None:
        # ``time.sleep(60)`` is way longer than the test's allowed wall time,
        # so we depend entirely on the liveness check to surface the death.
        blocked["result"] = session.execute("import time; time.sleep(60)")

    t = threading.Thread(target=hang, daemon=True)
    t.start()

    # Let the worker write its code and enter the polling loop, then kill
    # the subprocess from the main thread.
    time.sleep(0.3)
    proc.kill()

    # Liveness check runs every ~1 s; allow generous slack on slow CI.
    t.join(timeout=8)
    assert not t.is_alive(), "execute() did not return after subprocess kill"

    result = blocked["result"]
    assert isinstance(result, dict)
    assert result["success"] is False
    assert "Subprocess exited" in (result.get("error") or "")


def test_restart_recovers_session_after_subprocess_kill(
    session: LumericalPersistentPythonSession,
):
    """End-to-end recovery flow: kill -> restart -> next execute succeeds.

    This pins the agent-visible recovery path. Since ``execute`` has no
    timeout, a hung snippet can only be cleared by killing the subprocess
    (which the ``restart_session`` MCP tool does via
    :meth:`PersistentPythonSession.restart`). After restart the session
    must accept new snippets again.
    """
    proc = session.process
    assert proc is not None

    blocked: dict[str, object] = {}

    def hang() -> None:
        blocked["result"] = session.execute("import time; time.sleep(60)")

    t = threading.Thread(target=hang, daemon=True)
    t.start()
    time.sleep(0.3)
    proc.kill()

    t.join(timeout=8)
    assert not t.is_alive()
    blocked_result = blocked["result"]
    assert isinstance(blocked_result, dict)
    assert blocked_result["success"] is False

    # Now exercise the recovery flow.
    restart = session.restart()
    assert restart["success"], restart

    fresh = session.execute("print(7 * 6)")
    assert fresh["success"], fresh
    assert fresh["stdout"].strip() == "42"


def test_restart_unblocks_wedged_execute_holding_lock(monkeypatch):
    """``restart()`` must succeed while another execute() is still wedged.

    Pre-fix, ``execute()`` polled ``self.process`` in its wait loop. When
    ``restart()`` reassigned ``self.process`` to a fresh subprocess, the
    wedged call's liveness check kept seeing ``rc is None`` for the new
    alive handle, so the loop never exited, ``_execution_lock`` was never
    released, and the startup-code execute that ``start()`` issues right
    after respawn deadlocked. Every subsequent session-management tool
    call hung on the same lock. Pinning the captured process reference
    fixes this; we assert restart completes, the wedged call exits with
    a clean "Subprocess exited" envelope, and the post-restart session
    accepts new work.

    Crucially this test builds the session with a non-empty
    ``startup_code`` -- exactly as production does
    (``server.py`` passes ``LUMERICAL_STARTUP_CODE``). That is what makes
    the deadlock real: ``restart()`` -> ``start()`` -> ``execute(startup_code)``
    must acquire ``_execution_lock``, so a wedged execute that never
    releases the lock hangs ``restart()`` itself (the user-reported
    "restart_session waits forever"). The shared ``session`` fixture has
    no startup_code, so with it ``start()`` never contends for the lock and
    the restart-success assertion below would pass vacuously even with the
    bug present -- only the wedged-thread leak would be caught. ``import
    math`` is a cheap, dependency-free stand-in that still forces the
    startup execute (and therefore the lock contention) to happen.
    """
    monkeypatch.delenv("PYTHONSTARTUP", raising=False)
    session = LumericalPersistentPythonSession(
        python_executable=sys.executable,
        startup_code="import math",
    )
    started = session.start()
    assert started["success"], started

    try:
        blocked: dict[str, object] = {}

        def hang() -> None:
            blocked["result"] = session.execute("import time; time.sleep(120)")

        t = threading.Thread(target=hang, daemon=True)
        t.start()
        # Let the worker acquire ``_execution_lock`` before we trigger restart,
        # otherwise the test wouldn't actually exercise the deadlock scenario.
        time.sleep(0.5)

        restart_done: dict[str, object] = {}

        def do_restart() -> None:
            restart_done["result"] = session.restart()

        rt = threading.Thread(target=do_restart, daemon=True)
        rt.start()
        # ~5 s for stop()'s graceful-exit wait + ~1 s for the wedged liveness
        # check to fire + startup time. 30 s is generous slack for slow CI.
        rt.join(timeout=30)
        assert not rt.is_alive(), (
            "restart() deadlocked while a wedged execute held the lock "
            "(start()'s startup-code execute could not acquire _execution_lock)"
        )

        restart_result = restart_done["result"]
        assert isinstance(restart_result, dict)
        assert restart_result.get("success") is True, restart_result

        t.join(timeout=10)
        assert not t.is_alive(), (
            "Wedged execute() did not exit after restart killed the subprocess; "
            "did the liveness-check loop drift back to polling self.process?"
        )
        blocked_result = blocked["result"]
        assert isinstance(blocked_result, dict)
        assert blocked_result["success"] is False
        assert "Subprocess exited" in (blocked_result.get("error") or "")

        fresh = session.execute("print(7 * 6)")
        assert fresh["success"], fresh
        assert fresh["stdout"].strip() == "42"
    finally:
        session.stop()


# ---------------------------------------------------------------------------
# _strip_repl_prompts
# ---------------------------------------------------------------------------


def test_strip_repl_prompts_removes_leading_chevrons():
    text = ">>> >>> >>> Traceback (most recent call last):"
    assert _strip_repl_prompts(text) == "Traceback (most recent call last):"


def test_strip_repl_prompts_removes_ellipsis_continuations():
    text = "... ... if True:"
    assert _strip_repl_prompts(text) == "if True:"


def test_strip_repl_prompts_drops_bare_prompt_lines():
    text = ">>> \n>>>\nTraceback (most recent call last):"
    assert _strip_repl_prompts(text) == "Traceback (most recent call last):"


def test_strip_repl_prompts_preserves_non_prompt_content():
    text = (
        '  File "<stdin>", line 1, in <module>\nValueError: bad input -- see >>> docs for details'
    )
    # ``>>> docs`` appears mid-line, NOT a REPL prompt; must be preserved.
    out = _strip_repl_prompts(text)
    assert ">>> docs" in out
    assert "ValueError: bad input -- see >>> docs for details" in out


def test_strip_repl_prompts_handles_empty():
    assert _strip_repl_prompts("") == ""


# ---------------------------------------------------------------------------
# _summarize_exception
# ---------------------------------------------------------------------------


def test_summarize_exception_returns_last_exception_line():
    stderr = (
        "Traceback (most recent call last):\n"
        '  File "<stdin>", line 1, in <module>\n'
        "ValueError: first\n"
        "Traceback (most recent call last):\n"
        '  File "<stdin>", line 1, in <module>\n'
        "AttributeError: second"
    )
    assert _summarize_exception(stderr) == "AttributeError: second"


def test_summarize_exception_handles_dotted_exception_path():
    """lumapi raises ``ansys.api.lumerical.lumapi.LumApiError: ...`` -- the
    dotted prefix must not prevent the regex from picking the line up."""
    stderr = (
        "Traceback (most recent call last):\n"
        '  File "<stdin>", line 1, in <module>\n'
        '    mode.set("x span", 1e-6)\n'
        "ansys.api.lumerical.lumapi.LumApiError: "
        "\"in set, the requested property 'x span' was not found\"\n"
        "Some unrelated trailing log line that must NOT be picked"
    )
    summary = _summarize_exception(stderr)
    assert summary.startswith("ansys.api.lumerical.lumapi.LumApiError:")
    assert "x span" in summary


def test_summarize_exception_falls_back_to_last_non_empty_line():
    stderr = "some warning\nfinal noise line\n"
    assert _summarize_exception(stderr) == "final noise line"


def test_summarize_exception_handles_empty_input():
    assert _summarize_exception("") == ""


# ---------------------------------------------------------------------------
# _build_envelope - the single chokepoint for response construction.
#
# Every captured-output return path in execute() must funnel through this
# helper so the REPL-prompt stripping and exception-summary logic can't be
# silently skipped by a future code path. These tests pin that contract
# directly, independent of subprocess timing.
# ---------------------------------------------------------------------------


def test_build_envelope_strips_repl_prompts_on_forced_error():
    """Forced-error envelopes must run the same cleanup as success envelopes."""
    env = _build_envelope(
        stdout_lines=[],
        stderr_lines=[">>> >>> ", "... ... ", ">>> some content"],
        forced_error="Subprocess exited with code 1 before execution completed.",
    )
    assert env["success"] is False
    assert env["error"] == "Subprocess exited with code 1 before execution completed."
    assert env["stderr"] == "some content"
    assert env["stdout"] == ""


def test_build_envelope_success_path_strips_and_marks_success():
    """Clean stderr -> success=True, no error summary."""
    env = _build_envelope(
        stdout_lines=["hello"],
        stderr_lines=[">>> ", "... "],
    )
    assert env["success"] is True
    assert env["stdout"] == "hello"
    assert env["stderr"] == ""
    assert env["error"] == ""


def test_build_envelope_detects_real_traceback_and_summarizes():
    """A real Python traceback in stderr -> success=False with short summary."""
    env = _build_envelope(
        stdout_lines=[],
        stderr_lines=[
            ">>> Traceback (most recent call last):",
            '  File "<stdin>", line 1, in <module>',
            "ValueError: boom",
        ],
    )
    assert env["success"] is False
    # Full traceback in stderr (with prompt stripped from the first line).
    assert "Traceback (most recent call last):" in env["stderr"]
    assert "ValueError: boom" in env["stderr"]
    # Short summary in error -- not a copy of stderr.
    assert env["error"] == "ValueError: boom"
    assert env["error"] != env["stderr"]


def test_build_envelope_forced_error_overrides_stderr_exception_detection():
    """When a ``forced_error`` is reported, success is False regardless of stderr.

    Even if some traceback-shaped text snuck into the captured stderr (e.g.
    a partial dump from before the snippet died), the user-facing reason
    is still the forced error (timeout in legacy callers; subprocess
    death today). We pin this so a future refactor doesn't accidentally
    start reporting ``error`` from the exception summary while also
    claiming forced-error semantics.
    """
    env = _build_envelope(
        stdout_lines=[],
        stderr_lines=["ValueError: stale"],
        forced_error="Subprocess exited with code 1 before execution completed.",
    )
    assert env["success"] is False
    assert env["error"] == "Subprocess exited with code 1 before execution completed."


def test_build_envelope_handles_empty_streams():
    env = _build_envelope(stdout_lines=[], stderr_lines=[])
    assert env == {"success": True, "stdout": "", "stderr": "", "error": ""}


def test_build_envelope_forced_error_preserves_partial_output():
    """Captured stdout / stderr must survive the forced-error route.

    The defensive ``except Exception`` branch inside ``execute`` and the
    subprocess-death path both funnel through ``_build_envelope`` with a
    ``forced_error`` set. Pre-refactor that branch hand-rolled an envelope
    with empty stdout/stderr, throwing away exactly the diagnostics the
    caller needs to understand the failure. Pin that partial output is
    preserved here so future contributors don't re-introduce the loss.
    """
    env = _build_envelope(
        stdout_lines=["partial line 1", "partial line 2"],
        stderr_lines=["partial stderr"],
        forced_error="Error during code execution: BrokenPipeError",
    )
    assert env["success"] is False
    assert env["stdout"] == "partial line 1\npartial line 2"
    assert env["stderr"] == "partial stderr"
    assert env["error"] == "Error during code execution: BrokenPipeError"


# ---------------------------------------------------------------------------
# _stderr_indicates_exception - the success heuristic.
#
# The base ansys-common-mcp implementation flagged failure for ANY occurrence
# of "error" / "exception" / "traceback" in stderr. lumapi emits informational
# stderr lines containing those substrings (license messages, "Error: X" status
# pings, etc.), so the base heuristic produces noisy false failures. Our
# replacement looks for a real Python traceback header or a flush-left
# ``SyntaxError: ...``-style line.
# ---------------------------------------------------------------------------


def test_stderr_heuristic_flags_real_traceback():
    stderr = (
        "Traceback (most recent call last):\n"
        '  File "<stdin>", line 1, in <module>\n'
        "ValueError: boom"
    )
    assert _stderr_indicates_exception(stderr) is True


def test_stderr_heuristic_flags_syntax_error():
    stderr = '  File "<stdin>", line 1\n    def foo(:\n            ^\nSyntaxError: invalid syntax'
    assert _stderr_indicates_exception(stderr) is True


def test_stderr_heuristic_flags_keyboard_interrupt():
    stderr = (
        "Traceback (most recent call last):\n"
        '  File "<stdin>", line 1, in <module>\n'
        "KeyboardInterrupt:"
    )
    assert _stderr_indicates_exception(stderr) is True


def test_stderr_heuristic_flags_dotted_lumapi_error_without_traceback():
    """A lumapi error printed without a ``Traceback`` header must still flag.

    lumapi occasionally surfaces exception text directly (via its own
    logging) instead of letting Python's default traceback printer handle
    it -- in that case the captured stderr starts with the dotted exception
    line itself rather than a ``Traceback (most recent call last):`` header.
    The detector must recognise the dotted form (parity with the
    ``_summarize_exception`` regex), otherwise these errors are silently
    classified as ``success=True``.
    """
    stderr = (
        "ansys.api.lumerical.lumapi.LumApiError: "
        "\"in set, the requested property 'x span' was not found\""
    )
    assert _stderr_indicates_exception(stderr) is True


def test_stderr_heuristic_ignores_informational_lines():
    """lumapi-style informational stderr that mentions error words is NOT a failure."""
    stderr = (
        "Info: connecting to license server\n"
        "Error: license server slow to respond (retrying)\n"
        "Exception handler installed.\n"
        "Some traceback-related diagnostic blurb.\n"
    )
    assert _stderr_indicates_exception(stderr) is False


def test_stderr_heuristic_handles_empty_string():
    assert _stderr_indicates_exception("") is False
