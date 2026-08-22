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

"""Lumerical-tuned :class:`PersistentPythonSession`.

The base :class:`ansys.common.mcp.PersistentPythonSession.execute` ends its
collection loop after 0.5 seconds of no data (``helpers.py:353`` --
``consecutive_empty_reads > 5``) and on a caller-supplied ``timeout``. Both
early returns are hostile to Lumerical. A fresh ``FDTD()`` spends seconds in
silent C-level work. The call gives up before the marker arrives, and the
next call's ``_drain_queues`` discards the late output as stale. Timeout
returns also leave the stateful ``python -i`` REPL mid-statement and let a
prior call's stale marker satisfy the next call's wait loop.

This subclass re-implements ``execute`` with **unbounded, marker-only
termination**. It waits indefinitely for a per-call ``___EXEC_<uuid>___``
marker matched by exact-line equality (so neither stale markers nor user
code printing the token can end the wait), with a periodic
``process.poll()`` returning a distinct ``"Subprocess exited..."`` envelope
if the child dies.

Hung snippets are recovered out-of-band via the ``restart_session`` MCP tool
(:meth:`PersistentPythonSession.restart`), issued as a parallel request. The
wait loop polls a *locally captured* subprocess reference rather than
``self.process`` so a parallel ``restart()`` reassigning ``self.process``
cannot deadlock the wedged call on the new handle. The captured reference
flips to an exit code when the original child is killed.
"""

from __future__ import annotations

import logging
import queue
import re
import time
from typing import Any
from uuid import uuid4

from ansys.common.mcp.helpers import PersistentPythonSession

logger = logging.getLogger(__name__)

_POLL_INTERVAL_S = 0.1
_FINAL_DRAIN_S = 0.5
_LIVENESS_CHECK_INTERVAL_S = 1.0

# A real Python traceback always opens with this exact line, and a SyntaxError
# (which never shows a Traceback header) ends with a line like ``SyntaxError:
# ...`` flush-left. Match either to detect a true exception. The base class
# matched any occurrence of the word "error" / "exception" / "traceback" in
# stderr, which is hostile to lumapi: it emits informational stderr lines
# containing "Error" and "Exception" that have nothing to do with the snippet
# we just ran, causing false failures.
#
# The optional ``(?:\w+\.)*`` prefix lets us recognise dotted exception paths
# used by Lumerical (e.g. ``ansys.api.lumerical.lumapi.LumApiError: ...``)
# even when they're printed without a leading traceback header. This keeps
# the detector in parity with ``_EXCEPTION_SUMMARY_RE`` below; previously the
# detector accepted only the bare form and would silently mark a
# traceback-less lumapi error as a successful execution.
_EXCEPTION_RE = re.compile(
    r"^Traceback \(most recent call last\):$"
    r"|^(?:\w+\.)*[A-Z]\w*(?:Error|Exception|Interrupt):",
    re.MULTILINE,
)

# ``python -u -i`` echoes a ``>>> `` (or ``... ``) interactive prompt to stderr
# for every input line. Since we ship many lines per snippet, those prompts
# accumulate in the captured stderr (often dozens in a row, e.g.
# ``">>> >>> >>> Traceback ..."``) and contribute hundreds of bytes of pure
# noise. Stripping them keeps the JSON envelope readable and conserves the
# agent's context-window budget downstream. Match one-or-more leading
# prompt tokens at line start.
_REPL_PROMPT_RE = re.compile(r"^(?:(?:>>>|\.\.\.)(?:\s|$))+")

# Picks the last "<ExceptionName>: <message>" line in a Python traceback. We
# use this as a short summary in the ``error`` field so we don't ship the
# entire traceback twice (once in ``stderr``, once in ``error``). The optional
# ``(?:\w+\.)*`` prefix lets us catch dotted exception paths used by Lumerical
# (e.g. ``ansys.api.lumerical.lumapi.LumApiError: ...``), not just stdlib
# names like ``ValueError: ...``.
_EXCEPTION_SUMMARY_RE = re.compile(
    r"^(?:\w+\.)*[A-Z]\w*(?:Error|Exception|Interrupt):.*$",
    re.MULTILINE,
)


def _stderr_indicates_exception(stderr_text: str) -> bool:
    """Return True iff stderr contains a real Python traceback or exception line."""
    if not stderr_text:
        return False
    return _EXCEPTION_RE.search(stderr_text) is not None


def _strip_repl_prompts(text: str) -> str:
    """Remove ``>>> ``/``... `` interactive prompts captured from ``python -i``.

    Only strips prompt tokens that appear at the start of a line followed by
    whitespace (or end of line), so legitimate occurrences of ``>>>`` inside
    error messages are preserved. Lines that become empty after stripping are
    dropped to keep stderr compact.
    """
    if not text:
        return text
    cleaned_lines = []
    for line in text.splitlines():
        stripped = _REPL_PROMPT_RE.sub("", line)
        if stripped.strip():
            cleaned_lines.append(stripped)
    return "\n".join(cleaned_lines)


def _summarize_exception(stderr_text: str) -> str:
    """Return the last ``<ExceptionName>: ...`` line from ``stderr_text``.

    Falls back to the last non-empty line if no exception line is found.
    Returns an empty string for empty input.
    """
    if not stderr_text:
        return ""
    # Use ``finditer`` so the last match is a typed ``Match[str]``; ``findall``
    # returns ``list[Any]`` for patterns with non-capturing groups, which makes
    # mypy unhappy about the trailing ``.strip()`` call.
    last_match: re.Match[str] | None = None
    for last_match in _EXCEPTION_SUMMARY_RE.finditer(stderr_text):
        pass
    if last_match is not None:
        return last_match.group(0).strip()
    for line in reversed(stderr_text.splitlines()):
        if line.strip():
            return line.strip()
    return ""


def _build_envelope(
    stdout_lines: list[str],
    stderr_lines: list[str],
    *,
    forced_error: str | None = None,
) -> dict[str, Any]:
    """Build the response envelope from collected stdout/stderr lines.

    Every :meth:`LumericalPersistentPythonSession.execute` return path with
    captured output funnels through here so REPL-prompt stripping and
    exception summarization can't be bypassed.

    Parameters
    ----------
    stdout_lines, stderr_lines : list[str]
        Raw lines pulled from the subprocess output / error queues.
    forced_error : str | None, default: None
        When set, force ``success=False`` with this string in ``error``
        regardless of stderr, while still preserving any partial output.
        Used by the subprocess-died and ``except Exception`` paths.

    Returns
    -------
    dict[str, Any]
        ``{"success", "stdout", "stderr", "error"}`` -- the shape the base
        :class:`PersistentPythonSession.execute` produces.
    """
    stdout_text = "\n".join(stdout_lines)
    stderr_text = _strip_repl_prompts("\n".join(stderr_lines))

    if forced_error is not None:
        return {
            "success": False,
            "stdout": stdout_text,
            "stderr": stderr_text,
            "error": forced_error,
        }

    has_error = _stderr_indicates_exception(stderr_text)
    if has_error:
        logger.warning("Code execution had errors: %.200s", stderr_text)

    # ``error`` is a short ``XxxError: ...`` summary instead of a copy of
    # ``stderr`` -- the full traceback already lives in ``stderr`` and
    # shipping it twice doubles the size of the MCP envelope (and the
    # bytes the agent has to re-read on its next turn).
    return {
        "success": not has_error,
        "stdout": stdout_text,
        "stderr": stderr_text,
        "error": _summarize_exception(stderr_text) if has_error else "",
    }


class LumericalPersistentPythonSession(PersistentPythonSession):
    """A :class:`PersistentPythonSession` that tolerates long, silent operations.

    :meth:`execute` blocks indefinitely on a per-call completion marker; hung
    calls are recovered out-of-band by the ``restart_session`` MCP tool, which
    invokes :meth:`PersistentPythonSession.restart`.
    """

    def execute(self, code: str) -> dict[str, Any]:  # type: ignore[override]
        """Execute Python code in the persistent session.

        Parameters
        ----------
        code : str
            Python source to feed to the persistent ``python -u -i`` process.

        Returns
        -------
        dict[str, Any]
            Same shape as :meth:`PersistentPythonSession.execute` --
            ``{"success", "stdout", "stderr", "error"}``.
        """
        if not self._is_running or self.process is None:
            return {
                "success": False,
                "stdout": "",
                "stderr": "",
                "error": "Session is not running. Call 'start()' first.",
            }

        with self._execution_lock:
            stdout_lines: list[str] = []
            stderr_lines: list[str] = []
            try:
                # Pin the subprocess reference: ``self.process`` is reassigned
                # by ``restart()`` from another thread, and polling the live
                # attribute would deadlock this loop on the new alive handle
                # (see module docstring).
                proc = self.process
                if proc is None or proc.stdin is None:
                    return {
                        "success": False,
                        "stdout": "",
                        "stderr": "",
                        "error": "Process or stdin is not available.",
                    }

                self._drain_queues(timeout=0.1)

                # Per-call nonce marker eliminates two failure modes by
                # construction: (a) substring collision with user code that
                # happens to print the sentinel text, and (b) stale-marker
                # races where a prior (e.g. restarted) call's late marker
                # poisons the next call's wait loop.
                marker = f"___EXEC_{uuid4().hex}___"
                code_with_marker = f"{code}\nprint('{marker}')\n"
                logger.debug("Executing code: %.100s...", code)

                proc.stdin.write(code_with_marker)
                proc.stdin.flush()

                marker_found = False
                last_liveness_check = time.monotonic()

                while True:
                    # Periodic subprocess-liveness check. Without a timeout,
                    # a dead subprocess (segfault, OOM, ``exit()`` in user
                    # code) would otherwise leave the wait loop spinning
                    # forever waiting for a marker that will never arrive.
                    now = time.monotonic()
                    if now - last_liveness_check >= _LIVENESS_CHECK_INTERVAL_S:
                        last_liveness_check = now
                        if not marker_found:
                            rc = proc.poll()
                            if rc is not None:
                                error_msg = (
                                    f"Subprocess exited with code {rc} before execution completed."
                                )
                                logger.error(error_msg)
                                return _build_envelope(
                                    stdout_lines,
                                    stderr_lines,
                                    forced_error=error_msg,
                                )

                    output_line: str | None = None
                    try:
                        output_line = self._output_queue.get(timeout=_POLL_INTERVAL_S)
                    except queue.Empty:
                        pass

                    if output_line:
                        # Marker detection accepts either:
                        # - a standalone marker line, or
                        # - ``<user_output><marker>`` on one line when user
                        #   code writes stdout without a trailing newline.
                        #
                        # The subprocess is line-buffered (``bufsize=1`` in
                        # the base ``Popen``) and ``_read_stream`` uses
                        # ``readline``, so each ``output_line`` is one line.
                        # Strip only line endings (not all whitespace), then
                        # remove a trailing marker token if present.
                        output_no_newline = output_line.rstrip("\r\n")
                        if output_no_newline.endswith(marker):
                            prefix = output_no_newline[: -len(marker)]
                            if prefix:
                                stdout_lines.append(prefix)
                            marker_found = True
                        else:
                            stdout_lines.append(output_line.rstrip())

                    error_line: str | None = None
                    try:
                        error_line = self._error_queue.get(timeout=_POLL_INTERVAL_S)
                    except queue.Empty:
                        pass

                    if error_line:
                        stderr_lines.append(error_line.rstrip())

                    if marker_found and not (output_line or error_line):
                        break

                # Final drain window for both streams. After the marker
                # arrives, late stdout / stderr can still trickle in from
                # the subprocess's line-buffered runtime (notably on
                # Windows, where the producer side may briefly stall
                # between writes). Drain for a bounded window so the next
                # caller's first call doesn't inherit stale output.
                #
                # Poll both queues every iteration via ``get_nowait`` so a
                # heavy stdout stream cannot starve stderr collection (or
                # vice versa). Only sleep when both queues are empty, so
                # the loop is responsive when data is actually flowing.
                # Importantly we do NOT exit the drain early on the first
                # empty cycle: late output frequently arrives after a brief
                # gap, especially on Windows.
                final_drain_start = time.monotonic()
                while time.monotonic() - final_drain_start < _FINAL_DRAIN_S:
                    drained = False
                    try:
                        stdout_lines.append(self._output_queue.get_nowait().rstrip())
                        drained = True
                    except queue.Empty:
                        pass
                    try:
                        stderr_lines.append(self._error_queue.get_nowait().rstrip())
                        drained = True
                    except queue.Empty:
                        pass
                    if not drained:
                        time.sleep(0.05)

                return _build_envelope(stdout_lines, stderr_lines)

            except Exception as exc:  # pragma: no cover - defensive
                error_msg = f"Error during code execution: {exc}"
                logger.error(error_msg)
                # Preserve any partial output that was captured before the
                # failure: a defensive ``return {... stdout="" ...}`` would
                # otherwise discard exactly the diagnostics the caller needs
                # to figure out what went wrong.
                return _build_envelope(
                    stdout_lines,
                    stderr_lines,
                    forced_error=error_msg,
                )
