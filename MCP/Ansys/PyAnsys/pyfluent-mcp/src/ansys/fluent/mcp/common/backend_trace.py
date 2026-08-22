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

"""Diagnostic tracer for backend state-query calls.

Enable with the ``FLUIDS_BACKEND_TRACE`` env var:

* ``1`` / ``true`` / ``on`` — emit one INFO line per call, no stack.
* ``stack`` — INFO line **plus** a 6-frame caller stack (skipping
  this module + backend wrappers).

Disabled by default — zero cost when the env var is unset.

The point of this tracer is to answer the operational question
"who is hitting the live Fluent session when there is no user
query in flight?" without having to attach a debugger. Every
``get_state`` / ``get_active_status`` / ``get_named_object_names``
/ ``solver_status`` / ``run_code`` entry logs a single
``backend_call`` event tagged with method name, arg shape, and
(optionally) the calling frame. Filter the agent log on
``backend_call`` and you can immediately see whether the chatter
is coming from our own code (validator, preface, MCP tool, …) or
from PyFluent's internal heartbeat (which will not appear here
because PyFluent's RPCs do not flow through our wrappers).
"""

from __future__ import annotations

import logging
import os
import traceback

logger = logging.getLogger("ansys.fluent.mcp.backend_trace")

_FRAMES_TO_SKIP: list[str] = [
    "backend_trace.py",
    "pyfluent_backend.py",
    "asyncio",
]


def register_frames_to_skip(*filenames: str) -> None:
    """Register additional filename substrings to skip from stack traces.

    Parameters
    ----------
    filenames : str
        Filename substrings matched against each stack frame.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    for name in filenames:
        if name and name not in _FRAMES_TO_SKIP:
            _FRAMES_TO_SKIP.append(name)


def _mode() -> str | None:
    """Return the configured trace mode.

    Returns
    -------
    str | None
        Optional value produced by the operation.
    """
    raw = (os.environ.get("FLUIDS_BACKEND_TRACE") or "").strip().lower()
    if raw in ("1", "true", "on", "yes"):
        return "line"
    if raw in ("stack", "trace", "frames"):
        return "stack"
    return None


def trace_call(method: str, *, summary: str = "") -> None:
    """Log a single ``backend_call`` entry when tracing is enabled.

    ``method`` is the canonical backend method (``get_state``,
    ``get_active_status``, …). ``summary`` is an optional short
    string describing arg shape (e.g. ``"paths=4"``). Never raises.

    Parameters
    ----------
    method : str
        Backend method name being traced.
    summary : str
        Short description attached to the trace entry.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    mode = _mode()
    if mode is None:
        return
    try:
        if mode == "stack":
            stack = traceback.extract_stack(limit=20)
            interesting: list[str] = []
            for frame in reversed(stack[:-1]):
                fname = frame.filename.rsplit("\\", 1)[-1].rsplit("/", 1)[-1]
                if any(skip in fname for skip in _FRAMES_TO_SKIP):
                    continue
                interesting.append(f"{fname}:{frame.lineno}:{frame.name}")
                if len(interesting) >= 6:
                    break
            caller = " <- ".join(interesting) or "<unknown>"
            logger.info("backend_call method=%s %s caller=%s", method, summary, caller)
        else:
            logger.info("backend_call method=%s %s", method, summary)
    except Exception as exc:  # tracer must never break callers
        logger.warning("backend trace logging failed: %s", exc)


__all__ = ["trace_call"]
