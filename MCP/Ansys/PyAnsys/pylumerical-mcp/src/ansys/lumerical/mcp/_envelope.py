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

"""Size-cap and dedupe helpers for the ``execute_python_code`` envelope.

Tool responses are forwarded verbatim into the next LLM turn, so noisy
output (large tracebacks, a stray ``print(huge_array)``) can crowd out
the agent's context budget. Middle-truncating ``stdout`` / ``stderr``
caps the worst-case envelope at roughly
``2 * _MAX_STREAM_CHARS + _MAX_ERROR_CHARS + JSON overhead`` (~7.5 kB)
while preserving the head and tail of any traceback.

The ``error`` field is normally a short summary set at the source by
:meth:`LumericalPersistentPythonSession.execute`; the dedup branch in
:func:`_compact_execute_envelope` is a defensive fallback for sessions
that revert to copying ``stderr`` into ``error``.
"""

from __future__ import annotations

from typing import Any

# Per-stream caps for the ``execute_python_code`` JSON envelope.
_MAX_STREAM_CHARS = 3500
_MAX_ERROR_CHARS = 500  # ``error`` is a summary line; doesn't need full stream budget
_TRUNCATION_TAIL_FRACTION = 0.6  # keep more of the tail (root cause is usually last)


def _truncate_middle(text: str, max_chars: int = _MAX_STREAM_CHARS) -> str:
    """Truncate ``text`` to ``max_chars``, keeping head + tail with a marker.

    Both ends are usually needed (first failure at the top, root cause at
    the bottom), so a middle slice is dropped. The tail keeps a larger
    share (``_TRUNCATION_TAIL_FRACTION``) since the actionable exception
    line sits at the end of a traceback.
    """
    if len(text) <= max_chars:
        return text
    marker_template = "\n[... {n} characters omitted to fit response budget ...]\n"
    # Reserve a conservative slot for the marker; the actual marker length is
    # computed after the slice so the placeholder shows the real ``n``.
    reserve = len(marker_template.format(n=len(text)))
    budget = max(0, max_chars - reserve)
    tail_len = int(budget * _TRUNCATION_TAIL_FRACTION)
    head_len = budget - tail_len
    head = text[:head_len]
    tail = text[-tail_len:] if tail_len > 0 else ""
    omitted = len(text) - head_len - tail_len
    return head + marker_template.format(n=omitted) + tail


def _compact_execute_envelope(envelope: dict[str, Any]) -> dict[str, Any]:
    """Shrink an ``execute_python_code`` envelope dict in place and return it.

    The envelope has the shape
    ``{"success": ..., "stdout": ..., "stderr": ..., "error"|"message": ...}``.
    Oversized payloads waste context and have been reported to trip some
    MCP clients (see the Cursor forum thread in tests/test_contexts.py). We:

    1. Middle-truncate ``stdout`` / ``stderr`` to ``_MAX_STREAM_CHARS`` each
       and ``error`` to ``_MAX_ERROR_CHARS``.
    2. Drop ``error`` if it duplicates ``stderr`` byte-for-byte.

    Non-dict / unexpected shapes pass through unchanged. The same dict is
    returned (mutated in place) so callers can chain.
    """
    if not isinstance(envelope, dict):
        return envelope

    # Snapshot the pre-truncation values so the duplicate check below compares
    # the originals (not the already-truncated ``envelope["stderr"]``).
    stdout = envelope.get("stdout")
    stderr = envelope.get("stderr")
    error = envelope.get("error")

    if isinstance(stdout, str):
        envelope["stdout"] = _truncate_middle(stdout)
    if isinstance(stderr, str):
        envelope["stderr"] = _truncate_middle(stderr)
    if isinstance(error, str):
        if isinstance(stderr, str) and error == stderr:
            envelope.pop("error", None)
        else:
            envelope["error"] = _truncate_middle(error, max_chars=_MAX_ERROR_CHARS)

    return envelope


__all__ = [
    "_MAX_STREAM_CHARS",
    "_MAX_ERROR_CHARS",
    "_TRUNCATION_TAIL_FRACTION",
    "_truncate_middle",
    "_compact_execute_envelope",
]
