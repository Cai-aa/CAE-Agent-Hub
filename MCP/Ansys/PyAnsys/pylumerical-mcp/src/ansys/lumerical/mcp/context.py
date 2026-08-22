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

"""Application context for the PyLumerical MCP server.

Extends :class:`ansys.common.mcp.PyAnsysBaseAppContext` with a per-name
``sessions`` registry that mirrors the Lumerical handles living inside the
framework's persistent Python subprocess. The dictionary here is metadata only. The
live ``FDTD``/``MODE``/``DEVICE``/``INTERCONNECT`` instances live in the
subprocess and are reached via the seeded ``_lum_get(name)`` helper.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Optional, cast

from ansys.common.mcp import PyAnsysBaseAppContext
from fastmcp import Context


@dataclass
class SessionInfo:
    """Metadata for one Lumerical CAD session."""

    name: str
    product: str
    filename: Optional[str] = None
    hide: bool = False
    opened_at: float = field(default_factory=time.time)


@dataclass
class PyLumericalContext(PyAnsysBaseAppContext):
    """Multi-session context for the PyLumerical MCP server."""

    sessions: dict[str, SessionInfo] = field(default_factory=dict)


def _lifespan_context(ctx: Context) -> PyLumericalContext:
    """Pull the typed application context off a FastMCP request context.

    Every MCP tool that needs the Lumerical session registry / persistent
    Python subprocess goes through this accessor. Centralising the
    ``cast`` here keeps the tool layer free of FastMCP plumbing details.
    """
    return cast(PyLumericalContext, ctx.request_context.lifespan_context)


__all__ = ["PyLumericalContext", "SessionInfo", "_lifespan_context"]
