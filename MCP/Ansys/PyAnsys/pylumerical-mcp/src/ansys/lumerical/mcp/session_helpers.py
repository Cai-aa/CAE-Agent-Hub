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

"""Pure helpers for building Python snippets and parsing subprocess results.

Every MCP tool in :mod:`ansys.lumerical.mcp.tools` follows the same shape:

1. Build a short Python snippet (:func:`build_*_snippet`) that calls the
   helpers seeded into the persistent subprocess by
   :mod:`ansys.lumerical.mcp.startup_code` and prints a single JSON line on
   success.
2. Run the snippet via ``PersistentPythonSession.execute(snippet)``.
3. Wrap the framework's result dictionary into one of the JSON envelopes
   (:func:`envelope_success`, :func:`envelope_failure`).

Keeping these functions pure makes the tool layer trivial to unit test
without spawning a real subprocess or installing Lumerical.
"""

from __future__ import annotations

import json
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Snippet builders
# ---------------------------------------------------------------------------


def build_open_session_snippet(
    name: str,
    product: str,
    filename: Optional[str],
    hide: bool,
) -> str:
    """Snippet that opens a Lumerical session and prints metadata as JSON."""
    return (
        "_lum_print_json(_lum_open("
        f"{name!r}, {product!r}, filename={filename!r}, hide={bool(hide)!r}"
        "))"
    )


def build_close_session_snippet(name: str) -> str:
    """Snippet that closes a Lumerical session and prints the result as JSON."""
    return f"_lum_print_json(_lum_close({name!r}))"


def build_eval_snippet(session: str, script: str) -> str:
    """Snippet that runs LSF in a session and prints a small status JSON.

    Lumerical's ``.eval()`` returns ``None``. Outputs from the script (such as ``?x;``)
    go to the Lumerical log, not the Python subprocess stdout. If the agent
    needs values back, it should call ``getv``/``getresult`` via
    ``execute_python_code`` after this returns.
    """
    return (
        f"_lum_get({session!r}).eval({script!r}); "
        f"_lum_print_json({{'session': {session!r}, 'evaluated': True}})"
    )


def build_close_all_snippet() -> str:
    """Snippet that closes every still-open Lumerical session (used at shutdown)."""
    return "_lum_close_all()"


# ---------------------------------------------------------------------------
# Result parsing & envelopes
# ---------------------------------------------------------------------------


def extract_json_payload(stdout: str) -> Optional[Any]:
    """Pull the last JSON document printed to stdout, or ``None`` if absent.

    The startup-code helpers use ``_lum_print_json``, which emits exactly one
    JSON document per call (single-line by default). Other libraries may have
    printed unrelated text before that, so this process is used:

    1. Try a whole-string parse first.
    2. Try a per-line parse from the end (cheap, single-line JSON).
    3. Fall back to scanning backwards through ``{`` / ``[`` openers and
       using :class:`json.JSONDecoder.raw_decode` to recover pretty-printed
       JSON that spans multiple lines.
    """
    if not stdout:
        return None
    text = stdout.strip()
    if not text:
        return None

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    for line in reversed(text.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue

    decoder = json.JSONDecoder()
    starts = [i for i, c in enumerate(text) if c in "{["]
    for i in reversed(starts):
        try:
            obj, end = decoder.raw_decode(text[i:])
        except json.JSONDecodeError:
            continue
        # Anything after `end` should be whitespace; otherwise this opener
        # isn't a clean trailing JSON document.
        if text[i + end :].strip():
            continue
        return obj
    return None


def _jsonable(obj: Any) -> Any:
    """Recursively coerce ``obj`` into a JSON-serializable tree.

    Mirrors ``json.dumps(..., default=str)`` but as a walk returning a live
    dict/list/scalar tree, so the envelope helpers can hand FastMCP a
    ``dict`` (-> ``structuredContent``) without a non-JSON-safe leaf failing
    serialization later. Non-string dictionary keys are coerced to ``str`` (lossy
    but never fails).
    """
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(x) for x in obj]
    return str(obj)


def envelope_success(payload: Any, **extras: Any) -> dict[str, Any]:
    """Build a success envelope as a plain JSON-safe dictionary.

    Returning a dictionary (rather than a JSON string) lets FastMCP deliver the
    result as MCP ``structuredContent``, so clients see a single-encoded
    JSON object instead of the doubly-escaped text that resulted from
    JSON-encoding a JSON string at the transport layer.
    """
    body: dict[str, Any] = {"success": True}
    if payload is not None:
        body["data"] = _jsonable(payload)
    body.update(_jsonable(extras))
    return body


def envelope_failure(
    error: str,
    *,
    stdout: str = "",
    stderr: str = "",
    **extras: Any,
) -> dict[str, Any]:
    """Build a failure envelope as a plain JSON-safe dictionary.

    See :func:`envelope_success` for the rationale behind returning a dictionary
    instead of a JSON string.
    """
    body: dict[str, Any] = {"success": False, "error": error}
    if stdout:
        body["stdout"] = stdout
    if stderr:
        body["stderr"] = stderr
    body.update(_jsonable(extras))
    return body


def render_envelope_from_execute(
    execute_result: dict,
    *,
    on_success_payload: Optional[Any] = None,
) -> dict[str, Any]:
    """Convert a ``PersistentPythonSession.execute`` result to our envelope.

    If ``on_success_payload`` is provided, it overrides the parsed-from-stdout
    payload. Otherwise, an attempt is made to parse the last JSON line from stdout.
    """
    if not execute_result.get("success"):
        return envelope_failure(
            error=execute_result.get("error") or "subprocess execution failed",
            stdout=execute_result.get("stdout", ""),
            stderr=execute_result.get("stderr", ""),
        )

    payload = on_success_payload
    if payload is None:
        payload = extract_json_payload(execute_result.get("stdout", ""))
    return envelope_success(payload)


__all__ = [
    "build_open_session_snippet",
    "build_close_session_snippet",
    "build_eval_snippet",
    "build_close_all_snippet",
    "extract_json_payload",
    "envelope_success",
    "envelope_failure",
    "render_envelope_from_execute",
]
