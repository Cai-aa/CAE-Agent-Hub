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

"""The MCP tools exposed by the PyLumerical MCP server.

Each tool builds a small Python snippet (see
:mod:`ansys.lumerical.mcp.session_helpers`), runs it in the persistent
Python subprocess, and returns a JSON-safe dictionary. FastMCP forwards the
dictionary as MCP ``structuredContent`` so that clients see a single-encoded JSON
object (no double escaping). Heavy work (Lumerical orchestration, result
serialization, plotting) goes through :func:`execute_python_code` against
the helpers seeded by :mod:`ansys.lumerical.mcp.startup_code`.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Annotated, Any, Literal, Optional

from ansys.common.mcp.helpers import _sanitize_output
from fastmcp import Context
from pydantic import Field

from ansys.lumerical.mcp._envelope import _compact_execute_envelope
from ansys.lumerical.mcp.config import load_config
from ansys.lumerical.mcp.context import SessionInfo, _lifespan_context
from ansys.lumerical.mcp.server import app
from ansys.lumerical.mcp.session_helpers import (
    build_close_session_snippet,
    build_open_session_snippet,
    envelope_failure,
    envelope_success,
    extract_json_payload,
)

logger = logging.getLogger(__name__)


# Hard ceiling on close_session execute time. A healthy close finishes in
# well under a second; the timeout exists to surface a clean failure when
# the subprocess is wedged so the agent can dispatch ``restart_session``.
_CLOSE_SESSION_TIMEOUT_S = 30.0


_TOOL_SET_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "session_management",
        "description": "Tools for opening, listing, closing, and recovering Lumerical sessions",
        "skill": (
            "Use these tools to manage the lifecycle of named Lumerical sessions. "
            "Start with open_session before any product interaction, use list_sessions "
            "to inspect active sessions, close_session when done, and restart_session "
            "only to recover from wedged subprocess or license-server states."
        ),
        "tools": ["open_session", "close_session", "list_sessions", "restart_session"],
    },
    {
        "name": "python_execution",
        "description": "Tool for running custom Python against the persistent subprocess",
        "skill": (
            "Use execute_python_code for advanced workflows after a session is open. "
            "Prefer _lum_print_json(...) for structured output, avoid inventing lumapi APIs, "
            "and use get_guidelines_for before writing new Lumerical scripting code "
            "you are unsure about."
        ),
        "tools": ["execute_python_code"],
    },
    {
        "name": "guidelines",
        "description": "Tool for retrieving Lumerical workflow guidance",
        "skill": (
            "Call get_guidelines_for before generating Lumerical Python code. "
            "Start with workflow, then fetch only the task-specific topics "
            "(for example fdtd_workflow, geometry, materials, sweeps, fdtd_results)."
        ),
        "tools": ["get_guidelines_for"],
    },
]


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@app.resource("toolsets://definition")
def list_tool_sets() -> list[dict[str, Any]]:
    """Toolset definitions consumed by MCP clients and Ansys product UIs."""
    return _TOOL_SET_DEFINITIONS


@app.tool(tags={"session_management"})
async def open_session(
    ctx: Context,
    name: Annotated[
        str,
        Field(description="Unique session name. Used in subsequent tool calls."),
    ],
    product: Annotated[
        Literal["fdtd", "mode", "device", "interconnect"],
        Field(description="Lumerical product to launch."),
    ],
    filename: Annotated[
        Optional[str],
        Field(
            description=(
                "Optional path to an existing .fsp/.lms/.icp/.ldev project to load on open."
            ),
        ),
    ] = None,
    hide: Annotated[
        Optional[bool],
        Field(
            description=(
                "OMIT this argument unless the user explicitly asks to override the default."
            ),
        ),
    ] = None,
) -> dict[str, Any]:
    """Open a Lumerical CAD session and register it under ``name``.

    Multiple sessions of any product type may be open concurrently. Each is
    addressable by the ``name`` you choose here. Returns a JSON-safe dictionary
    envelope (delivered to the client as MCP ``structuredContent``) with
    success/failure plus session metadata. Common failures include duplicate
    name, invalid product, and license-server errors.

    The call blocks until the subprocess finishes the open. If a Lumerical
    product wedges (such as a license-server hang), dispatch a parallel
    ``restart_session`` tool call to recover.
    """
    lifespan_context = _lifespan_context(ctx)
    cfg = load_config()
    effective_hide = cfg.hide_gui if hide is None else bool(hide)

    if name in lifespan_context.sessions:
        return envelope_failure(
            error=f"Session {name!r} already exists. Close it first or pick a different name.",
        )

    snippet = build_open_session_snippet(name, product, filename, effective_hide)
    # Run the blocking subprocess call on a worker thread so we don't freeze
    # the FastMCP server's asyncio event loop while waiting for the snippet
    # to complete (see ``LumericalPersistentPythonSession.execute``'s
    # synchronous polling loop). The existing ``threading.Lock`` inside
    # ``execute`` still serializes access to the single subprocess; this
    # change only moves the *waiting* off the event loop.
    raw = await asyncio.to_thread(lifespan_context.python_session.execute, snippet)

    if raw.get("success"):
        payload = extract_json_payload(raw.get("stdout", "")) or {}
        lifespan_context.sessions[name] = SessionInfo(
            name=name,
            product=product.lower(),
            filename=filename,
            hide=effective_hide,
        )
        merged = {
            "name": name,
            "product": product.lower(),
            "filename": filename,
            "hide": effective_hide,
        }
        if isinstance(payload, dict):
            merged.update({k: v for k, v in payload.items() if k not in merged})
        return envelope_success(merged)

    # Defensive cleanup: the open may have *partially* succeeded (the live
    # subprocess registry contains the new session) even though our success
    # heuristic flagged the call as failed - e.g. lumapi emitted an
    # informational stderr line that looked like an error. Try to close any
    # such ghost session so the user can retry open_session without hitting
    # "Session already exists" in the subprocess. Best effort: a failure
    # here (including "no such session") is logged at debug level but
    # otherwise ignored so the original open_session failure isn't masked.
    try:
        await asyncio.to_thread(
            lifespan_context.python_session.execute, build_close_session_snippet(name)
        )
    except Exception as exc:  # pragma: no cover - best effort
        logger.debug("Defensive close after open_session failure ignored: %s", exc)

    return envelope_failure(
        error=raw.get("error") or "open_session failed",
        stdout=raw.get("stdout", ""),
        stderr=raw.get("stderr", ""),
    )


@app.tool(tags={"session_management"})
async def close_session(
    ctx: Context,
    name: Annotated[str, Field(description="Session name to close.")],
) -> dict[str, Any]:
    """Close a Lumerical session and remove it from the registry.

    Bounded by :data:`_CLOSE_SESSION_TIMEOUT_S`. On timeout, returns a
    failure envelope with ``timed_out=True`` and ``retained=True`` so the
    agent can dispatch ``restart_session`` to recover. The orphaned worker
    thread is left to drain on its own (asyncio cannot cancel it).
    """
    lifespan_context = _lifespan_context(ctx)

    if name not in lifespan_context.sessions:
        return envelope_failure(
            error=f"No session named {name!r}.",
        )

    snippet = build_close_session_snippet(name)
    # Offload to a worker thread (see open_session) bounded by wait_for so a
    # wedged subprocess can't hang the agent. The orphaned thread is harmless;
    # ``restart_session`` is the universal escape hatch.
    try:
        raw = await asyncio.wait_for(
            asyncio.to_thread(lifespan_context.python_session.execute, snippet),
            timeout=_CLOSE_SESSION_TIMEOUT_S,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "close_session(%s) timed out after %.1fs; subprocess appears wedged.",
            name,
            _CLOSE_SESSION_TIMEOUT_S,
        )
        return envelope_failure(
            error=(
                f"close_session timed out after {_CLOSE_SESSION_TIMEOUT_S:.0f}s. "
                "The subprocess appears wedged; dispatch restart_session to recover."
            ),
            retained=True,
            timed_out=True,
        )

    if raw.get("success"):
        # Drop the local entry only when the subprocess confirmed the close.
        lifespan_context.sessions.pop(name, None)
        payload = extract_json_payload(raw.get("stdout", "")) or {"closed": name}
        return envelope_success(payload)

    # Close failed: keep the local entry so the user (or a retry) can attempt
    # the close again. If the underlying subprocess session is genuinely gone,
    # the next close_session call will surface "No session ..." cleanly.
    return envelope_failure(
        error=raw.get("error") or "close_session failed",
        stdout=raw.get("stdout", ""),
        stderr=raw.get("stderr", ""),
        retained=True,
    )


@app.tool(tags={"session_management"})
async def list_sessions(ctx: Context) -> dict[str, Any]:
    """List currently open Lumerical sessions (metadata only).

    The returned list reflects the MCP server's view of registered sessions.
    To verify the live subprocess registry, use ``execute_python_code`` with
    ``_lum_print_json(_lum_list())``.
    """
    lifespan_context = _lifespan_context(ctx)
    items = [
        {
            "name": s.name,
            "product": s.product,
            "filename": s.filename,
            "hide": s.hide,
            "opened_at": s.opened_at,
        }
        for s in lifespan_context.sessions.values()
    ]
    return envelope_success(items)


@app.tool(tags={"python_execution"})
async def execute_python_code(
    ctx: Context,
    code: Annotated[
        str,
        Field(
            description=(
                "Python source to execute in the persistent subprocess that "
                "hosts all Lumerical sessions."
            ),
        ),
    ],
) -> dict[str, Any]:
    """Execute Python in the persistent subprocess that hosts all Lumerical sessions.

    Pre-loaded into the subprocess globals:

    - Imports: ``FDTD``, ``MODE``, ``DEVICE``, ``INTERCONNECT`` from ``ansys.lumerical.core``
    - Registry: ``_lumerical_sessions: dict[str, Lumerical]`` (live handles)
    - Helpers:

      * ``_lum_open(name, product, filename=None, hide=False)`` -- prefer
        the ``open_session`` MCP tool over calling this helper directly
      * ``_lum_close(name)``
      * ``_lum_get(name)`` -- returns the live handle for ``name``
      * ``_lum_list()``
      * ``_lum_print_json(obj, *, max_array_size=200_000, indent=None)``

    DATA-RETURN CONTRACT: only ``print()``-ed text leaves the subprocess. For
    structured data (numpy arrays, dictionaries, Lumerical results), use
    ``_lum_print_json(...)``. It handles numpy/complex/dict/list with a
    size guard that truncates arrays larger than ``max_array_size`` to
    ``{shape, dtype, preview}`` so the LLM context window doesn't get blown
    up by multi-MB field data.

    Example -- run an FDTD simulation and pull a transmission spectrum::

        fdtd = _lum_get("fdtd_main")
        fdtd.addrect(name="r1", x=0, x_span=1e-6, y=0, y_span=1e-6, z=0, z_span=1e-6)
        fdtd.save("foo.fsp")
        fdtd.run()
        _lum_print_json(fdtd.getresult("T_monitor", "T"))

    The call blocks until the snippet finishes. The lock that serializes
    subprocess access is held for the duration, so if a snippet hangs
    (infinite loop, unterminated multi-line input, license-server stall),
    the agent must dispatch a parallel ``restart_session`` tool call to
    recover.
    """
    # Note: we deliberately do NOT delegate to
    # ``ansys.common.mcp.execute_python_code`` here. That upstream helper is
    # declared ``async`` but calls ``session.execute(...)`` synchronously,
    # which blocks the FastMCP server's asyncio event loop for the full
    # duration of every snippet (sometimes minutes for an ``fdtd.run()``).
    # That stalls every other in-flight ``tools/call`` request -- including
    # purely static tools like ``get_guidelines_for`` -- and triggers a
    # client-side ``Cannot read properties of undefined (reading 'invoke')``
    # error in Cursor's MCP client when calls are issued in parallel. We
    # instead run the blocking ``execute(...)`` on a worker thread via
    # ``asyncio.to_thread`` so the event loop stays responsive; the existing
    # ``threading.Lock`` inside ``LumericalPersistentPythonSession.execute``
    # still serializes access to the single subprocess.
    lifespan_context = _lifespan_context(ctx)
    session = lifespan_context.python_session

    if session is None:
        return {
            "success": False,
            "error": (
                "No Python session available. The persistent Python session was not initialized."
            ),
        }

    sanitized_code = _sanitize_output(code)
    logger.info("Executing Python code in persistent session:\n%s", sanitized_code)

    try:
        result = await asyncio.to_thread(session.execute, sanitized_code)
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Error executing Python code: %s", exc)
        return {"success": False, "error": f"Error executing Python code: {exc}"}

    # ``LumericalPersistentPythonSession.execute`` always returns a dict, but
    # guard against future refactors / mocks that might return something else.
    if not isinstance(result, dict):
        return _compact_execute_envelope(
            {
                "success": True,
                "stdout": _sanitize_output(str(result)) if result else "",
                "stderr": "",
                "message": "Python code executed successfully.",
            }
        )

    stdout = _sanitize_output(result.get("stdout", ""))
    stderr = _sanitize_output(result.get("stderr", ""))

    if result.get("success"):
        envelope: dict[str, Any] = {
            "success": True,
            "stdout": stdout,
            "stderr": stderr,
            "message": "Python code executed successfully.",
        }
    else:
        error_msg = _sanitize_output(result.get("error", "Unknown error occurred."))
        envelope = {
            "success": False,
            "stdout": stdout,
            "stderr": stderr,
            "error": error_msg,
        }

    return _compact_execute_envelope(envelope)


@app.tool(tags={"session_management"})
async def restart_session(ctx: Context) -> dict[str, Any]:
    """Restart the persistent Python subprocess that hosts all Lumerical sessions.

    Use this when a previous tool call appears stuck. Typical triggers are
    an unterminated multi-line snippet sent to ``execute_python_code``, an
    infinite loop in user code, or a license-server/Lumerical handshake
    that has wedged. Since :meth:`LumericalPersistentPythonSession.execute`
    blocks indefinitely (see :mod:`ansys.lumerical.mcp.persistent_session`),
    this tool is the agent-visible recovery path.

    Because blocking ``execute`` calls run on worker threads, this coroutine
    can run while a previous ``execute_python_code`` is still blocked. The
    restart kills the wedged subprocess, so that blocked call also returns
    shortly after (with an error envelope, since its subprocess died).

    Side effects
    ------------
    - The persistent subprocess is terminated (gracefully if possible,
      forcefully otherwise) and a fresh one is spawned. The
      ``LUMERICAL_STARTUP_CODE`` startup snippet is re-executed in the new
      subprocess.
    - All live Lumerical handles previously hosted by the subprocess are
      destroyed. There is no automatic re-open: the agent must call
      :func:`open_session` for any session it still needs.
    - The MCP-level ``lifespan_context.sessions`` metadata registry is cleared,
      since every entry refers to a Lumerical handle that lived in the now-dead
      subprocess. The cleared names are returned in the response envelope
      so the agent can re-open them if desired.

    Returns
    -------
    dict[str, Any]
        JSON-safe envelope dictionary. On success the ``data`` payload contains
        ``{"restarted": True, "cleared_sessions": [<names>]}``. On failure
        the envelope is the standard ``{"success": False, "error": "..."}``.
        FastMCP forwards this dictionary as MCP ``structuredContent`` so MCP
        clients see it as a parsed JSON object (no double escaping).
    """
    lifespan_context = _lifespan_context(ctx)
    py = lifespan_context.python_session

    if py is None:
        return envelope_failure(
            error=(
                "No Python session available to restart. The persistent "
                "Python session was not initialized."
            ),
        )

    # ``PersistentPythonSession.restart`` is synchronous (stop + start, both
    # of which block while the subprocess is torn down / spawned). Offload it
    # to a worker thread so the asyncio event loop stays responsive to any
    # other in-flight tool calls.
    restart_result = await asyncio.to_thread(py.restart)

    if not restart_result.get("success"):
        return envelope_failure(
            error=restart_result.get("error") or "restart_session failed",
        )

    # Local registry entries reference Lumerical handles that lived in the
    # subprocess we just killed. Drop them; surface the dropped names so the
    # agent can re-open whichever sessions it still needs.
    cleared = sorted(lifespan_context.sessions.keys())
    lifespan_context.sessions.clear()
    return envelope_success({"restarted": True, "cleared_sessions": cleared})


__all__ = [
    "list_tool_sets",
    "open_session",
    "close_session",
    "list_sessions",
    "execute_python_code",
    "restart_session",
]
