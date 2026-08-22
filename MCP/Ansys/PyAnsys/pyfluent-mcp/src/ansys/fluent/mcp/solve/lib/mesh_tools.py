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

"""Solve-leaf mesh-introspection domain tools (shared implementation).

``mesh_quality`` is a pure-domain tool: it reads only from
``Backend.mesh_quality()``, ``Backend.mesh_check()`` and
``Backend.mesh_counts()``, so it is safe to expose from the standalone
MCP leaf. Richer mesh discovery that depends on named-object or schema
caches is out of scope for the leaf and lives on host-side callers.

**Why cell/face/node counts are always included here:** Fluent does not
expose mesh-element totals on the settings tree, and PyFluent's
``solver.mesh.*`` namespace has no ``cell_count`` attribute. Without
these counts, an agent has no reliable accessor for the canonical "how
many cells does my mesh have?" question and would resort to guessing
non-existent attributes (such as ``solver.field_info.get_cell_count``,
``solver.mesh.cell_count``, and ``solver.mesh_info.cell_count``). The
counts come from ``(inquire-grids)`` via ``Backend.mesh_counts()``.
Surfacing them here makes ``mesh_quality`` the one-stop tool for every
mesh size/quality/topology question.
"""

from __future__ import annotations

from typing import Any

from ansys.fluent.mcp.common.backend import Backend
from ansys.fluent.mcp.common.errors import BackendUnavailableError


async def _safe_mesh_counts(backend: Backend) -> dict[str, int | None]:
    """Fail-soft wrapper around ``Backend.mesh_counts``.

    Returns an all-``None`` payload when the backend has no live solver
    (Fluids One geometry / mesh / post leaves) or the probe failed.
    Never raises — the cell-count addition must never break the
    quality-metrics path.

    Parameters
    ----------
    backend : Backend
        Backend to supply to the function.

    Returns
    -------
    dict[str, int | None]
        Mapping containing the operation result.
    """
    empty: dict[str, int | None] = {
        "cell_count": None,
        "face_count": None,
        "node_count": None,
    }
    fn = getattr(backend, "mesh_counts", None)
    if not callable(fn):
        return empty
    try:
        result = await fn()
    except BackendUnavailableError:
        return empty
    except Exception:  # fail-soft boundary
        return empty
    if not isinstance(result, dict):
        return empty
    return {
        "cell_count": result.get("cell_count"),
        "face_count": result.get("face_count"),
        "node_count": result.get("node_count"),
    }


async def mesh_quality_impl(
    backend: Backend,
    *,
    include_check: bool = False,
) -> dict[str, Any]:
    """Return live mesh sizing and quality metrics from the connected solver.

    Output shape:

    * ``cell_count``/``face_count``/ ``node_count``: Globals from
      ``(inquire-grids)``. ``None`` is returned when the probe failed (no mesh
      loaded or partition pending). Always present at the top level so
      "how many cells does my mesh have?" is answered in a single
      tool call.
    * ``quality``: ``{min_orthogonal_quality, max_ortho_skew,
      max_aspect_ratio}`` from ``mesh.quality``.
    * ``check`` (only when ``include_check=True``): Structured
      ``mesh.check`` payload with domain extents, volume/face-area
      statistics, warnings, errors and a trimmed ``raw`` transcript.

    Parameters
    ----------
    backend : Backend
        Backend to supply to the function.
    include_check : bool
        Include check to supply to the function.

    Returns
    -------
    dict[str, Any]
        Mapping containing the operation result.
    """
    if not backend.is_connected():
        return {
            "connected": False,
            "cell_count": None,
            "face_count": None,
            "node_count": None,
            "quality": None,
            "check": None,
            "note": "mesh_quality requires a live solver session.",
        }

    out: dict[str, Any] = {"connected": True}
    counts = await _safe_mesh_counts(backend)
    out["cell_count"] = counts["cell_count"]
    out["face_count"] = counts["face_count"]
    out["node_count"] = counts["node_count"]

    try:
        out["quality"] = await backend.mesh_quality()
    except BackendUnavailableError as exc:
        return {
            "connected": True,
            "cell_count": out["cell_count"],
            "face_count": out["face_count"],
            "node_count": out["node_count"],
            "quality": None,
            "check": None,
            "error": "backend_unavailable",
            "message": str(exc),
        }

    if include_check:
        try:
            out["check"] = await backend.mesh_check()
        except BackendUnavailableError as exc:
            out["check"] = None
            out["check_error"] = str(exc)

    return out


__all__ = ["mesh_quality_impl"]
