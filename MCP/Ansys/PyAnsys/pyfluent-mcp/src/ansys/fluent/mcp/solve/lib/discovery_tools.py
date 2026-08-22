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

"""Solve-leaf live-introspection domain tools (shared implementation).

These tools talk directly to the connected Fluent backend and do not
depend on any host-side cache, so they are safe to expose from the
standalone MCP leaf.

Currently, ``list_fields_impl`` enumerates the data fields the loaded
solver case can plot and report on (e.g. for ``contour`` setup).
"""

from __future__ import annotations

from typing import Any

from ansys.fluent.mcp.common.backend import Backend


async def list_fields_impl(
    backend: Backend,
    *,
    scope: str = "any",
) -> dict[str, Any]:
    """Enumerate scalar/vector fields available in the loaded case.

    ``scope`` is forwarded verbatim to ``Backend.list_fields`` and is
    typically one of ``"any" | "cell" | "node" | "face"``.

    Parameters
    ----------
    backend : Backend
        Backend to supply to the function.
    scope : str
        Scope for limiting the field or API lookup.

    Returns
    -------
    dict[str, Any]
        Mapping containing the operation result.
    """
    if not backend.is_connected():
        return {
            "connected": False,
            "fields": [],
            "note": "live session required to list solver fields",
        }
    scope = (scope or "any").strip() or "any"
    try:
        info = await backend.list_fields(scope=scope)
    except Exception as exc:  # surface as typed payload
        return {"error": f"failed to list fields: {exc}"}
    if not info:
        return {
            "connected": True,
            "fields": [],
            "scope": scope,
            "note": (
                "no field info available (data may not be loaded). "
                "This is NOT a blocker — proceed with the canonical "
                "field name from the user's phrasing (e.g. "
                "'pressure', 'temperature', 'velocity-magnitude'). "
                "The plan executor resolves field names at "
                "apply-time. If the session truly has no data, "
                "queue `solution.initialization.hybrid_initialize` "
                "as a PREREQUISITE step in the SAME plan as the "
                "contour/vector create — do not stop after "
                "initialize."
            ),
        }
    return {"connected": True, **info}


__all__ = ["list_fields_impl"]
