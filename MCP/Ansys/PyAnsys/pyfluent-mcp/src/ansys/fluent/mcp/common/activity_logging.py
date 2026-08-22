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

"""Helpers for compact, redaction-safe logging of tool calls and live session interactions.

Used by:

* :func:`ansys.fluent.mcp.solve.backends.pyfluent.PyFluentBackend.run_code`
  to log the snippet that was sent to the live solver and the response
  it produced.
* An optional higher-level agent layer (when installed) to log every
  tool invocation (name, sanitized arguments, latency, brief result). This
  package exposes the helpers. It does not import that layer.

All records flow through Python's ``logging`` module on dedicated child
loggers under the ``ansys.fluent.mcp`` namespace so they are captured by
the session log file installed by
:mod:`ansys.fluent.mcp.common.session_logging` without callers needing
to know that file exists.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable, Mapping

# Loggers callers should use. Each child of ``ansys.fluent.mcp``
# propagates up to the package logger and the session FileHandler picks
# it up.
TOOL_LOGGER = logging.getLogger("ansys.fluent.mcp.agent.tool_calls")
SESSION_LOGGER = logging.getLogger("ansys.fluent.mcp.session.run_code")

# Soft caps so a single huge arg payload or stdout dump doesn't fill
# the log file. Caller can pass an explicit ``limit`` to override.
_DEFAULT_VALUE_LIMIT = 800
_DEFAULT_TEXT_LIMIT = 2000

# Fields whose values look secret-bearing; redacted in tool args before
# logging. We only check the KEY name (case-insensitive substring),
# never the value, because Python regexing values across every nested
# dict is both slow and unreliable.
_REDACT_KEY_PARTS: tuple[str, ...] = (
    "api_key",
    "apikey",
    "token",
    "secret",
    "password",
    "auth",
)

# Argument keys to print verbatim regardless of length, because they
# are useful for debugging even when long. Anything else is truncated
# at ``_DEFAULT_VALUE_LIMIT`` chars.
_KEEP_FULL_KEYS: frozenset[str] = frozenset(
    {
        "name",
        "path",
        "tool",
        "kind",
    }
)


def _looks_secret(key: str) -> bool:
    """Return whether a name appears to contain a secret.

    Parameters
    ----------
    key : str
        Key used to look up or store the associated value.

    Returns
    -------
    bool
        Boolean result of the operation.
    """
    k = key.lower()
    return any(part in k for part in _REDACT_KEY_PARTS)


def _truncate(text: str, limit: int) -> str:
    """Shorten a value for logging or display.

    Parameters
    ----------
    text : str
        Text value to parse, normalize, or write.
    limit : int
        Maximum number of items to include in the response.

    Returns
    -------
    str
        String value produced by the helper.
    """
    if len(text) <= limit:
        return text
    return text[:limit] + f"... <+{len(text) - limit} chars>"


def sanitize_args(args: Any, *, limit: int = _DEFAULT_VALUE_LIMIT) -> Any:
    """Return a logging-safe copy of ``args``.

    * Redacts secret-looking keys.
    * Truncates string values longer than ``limit``.
    * Recursively descends into dictionaries, lists, and tuples.

    Other scalar types (int, float, bool, None) are returned as-is.

    Parameters
    ----------
    args : Any
        Positional arguments forwarded to the wrapped call.
    limit : int
        Maximum number of items or characters to include.

    Returns
    -------
    Any
        Result produced by the function.
    """
    if isinstance(args, Mapping):
        out: dict[str, Any] = {}
        for k, v in args.items():
            key = str(k)
            if _looks_secret(key) and v is not None:
                out[key] = f"<redacted len={len(v)}>" if isinstance(v, str) else "<redacted>"
                continue
            if key in _KEEP_FULL_KEYS:
                out[key] = v if not isinstance(v, str) else v
            else:
                out[key] = sanitize_args(v, limit=limit)
        return out
    if isinstance(args, (list, tuple)):
        cls = list  # JSON-friendly
        return cls(sanitize_args(item, limit=limit) for item in args)
    if isinstance(args, str):
        return _truncate(args, limit)
    return args


def summarise_result(result: Any, *, limit: int = _DEFAULT_VALUE_LIMIT) -> Any:
    """Compact rendering of a tool's return payload.

    Tool handlers return a wide variety of dictionaries (some with large
    nested ``state``, ``snapshot``, or ``preview`` blobs). This handler keeps the
    top-level keys but truncates values aggressively so the log line
    stays under a few KB. For non-dictionary returns, the handler truncates.

    Parameters
    ----------
    result : Any
        Result object to summarize for logging.
    limit : int
        Maximum number of items or characters to include.

    Returns
    -------
    Any
        Result produced by the function.
    """
    if isinstance(result, Mapping):
        return {str(k): _summarise_value(v, limit=limit) for k, v in result.items()}
    return _summarise_value(result, limit=limit)


def _summarise_value(value: Any, *, limit: int) -> Any:
    """Summarize a value for activity logging.

    Parameters
    ----------
    value : Any
        Value to inspect, convert, or store.
    limit : int
        Maximum number of items to include in the response.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    if isinstance(value, Mapping):
        # Compress dict to its keys when there are many entries.
        if len(value) > 12:
            return {
                "_kind": "dict",
                "_keys": sorted(str(k) for k in value)[:20],
                "_size": len(value),
            }
        return {str(k): _summarise_value(v, limit=limit) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        if len(value) > 12:
            head = [_summarise_value(v, limit=limit) for v in list(value)[:6]]
            return {
                "_kind": type(value).__name__,
                "_head": head,
                "_size": len(value),
            }
        return [_summarise_value(v, limit=limit) for v in value]
    if isinstance(value, str):
        return _truncate(value, limit)
    return value


def format_iterable_inline(items: Iterable[Any], *, limit: int = 200) -> str:
    """Render an iterable as a compact comma-separated string.

    Parameters
    ----------
    items : Iterable[Any]
        Items to format or summarize.
    limit : int
        Maximum number of items or characters to include.

    Returns
    -------
    str
        String result produced by the function.
    """
    parts: list[str] = []
    used = 0
    for item in items:
        chunk = str(item)
        if used + len(chunk) + 2 > limit:
            parts.append("…")
            break
        parts.append(chunk)
        used += len(chunk) + 2
    return ", ".join(parts)


def truncate_text(text: str, *, limit: int = _DEFAULT_TEXT_LIMIT) -> str:
    """Use the public truncation helper for one-line stdout/stderr summaries.

    Parameters
    ----------
    text : str
        Text value to parse, normalize, or write.
    limit : int
        Maximum number of items or characters to include.

    Returns
    -------
    str
        String result produced by the function.
    """
    if not text:
        return ""
    return _truncate(text, limit)


__all__ = [
    "SESSION_LOGGER",
    "TOOL_LOGGER",
    "format_iterable_inline",
    "sanitize_args",
    "summarise_result",
    "truncate_text",
]
