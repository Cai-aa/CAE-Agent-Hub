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

"""CFX leaf powered by PyCFX sessions."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Iterable, Optional, cast

from ansys.cfx.mcp.cfx.backend import CFXBackend
from ansys.cfx.mcp.common.backend import Backend
from ansys.cfx.mcp.common.base import FluidsLeafMCP
from ansys.cfx.mcp.common.errors import typed_guard


class CFXMCP(FluidsLeafMCP):
    """CFX MCP leaf server implementation."""

    leaf_name = "cfx"
    default_backend_kind = "pycfx"
    component_label = "cfx"

    def __init__(
        self, *, expose_tools: Optional[Iterable[str]] = None, **fastmcp_kwargs: Any
    ) -> None:
        """Initialize this object with the dependencies required for later operations.

        Parameters
        ----------
        expose_tools : Optional[Iterable[str]], default: None
            Optional tool-name allow-list. When ``None``, the standard CFX tools are exposed.
        fastmcp_kwargs : Any
            Additional keyword arguments forwarded to FastMCP.

        Returns
        -------
        None
            No value is returned. Side effects are applied to the relevant cache, session, or
            server.
        """
        backends: dict[str, Backend] = {"pycfx": CFXBackend()}
        super().__init__(
            backends=backends,
            expose_tools=expose_tools
            or (
                "session_status",
                "connect",
                "disconnect",
                "cfx_workflow",
                "cfx_model_context",
                "run_code",
                "validate_code",
            ),
            **fastmcp_kwargs,
        )

    def _register_tools(self) -> None:
        """Register MCP tools exposed by the leaf server.

        Returns
        -------
        None
            No value is returned. Side effects are applied to the relevant cache, session, or
            server.
        """
        super()._register_tools()
        if "cfx_workflow" in self._exposed:
            self._tool_cfx_workflow()
        if "cfx_model_context" in self._exposed:
            self._tool_cfx_model_context()

    def _tool_cfx_workflow(self) -> None:
        """Register the ``cfx_workflow`` MCP tool for lifecycle actions.

        Returns
        -------
        None
            No value is returned. The tool is added to the FastMCP server.
        """

        @self.tool(
            name="cfx_workflow",
            description=(
                "Run one focused CFX lifecycle or artifact action. Actions: "
                "start_pre, import_mesh, write_def, start_solver, wait_solver, "
                "get_results_file, open_post, status. Use the external agent "
                "layer for custom PyCFX code generation."
            ),
        )
        @typed_guard
        async def cfx_workflow(
            action: str,
            params: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            """Run a focused CFX lifecycle or artifact action.

            Parameters
            ----------
            action : str
                Component-management action to apply.
            params : dict[str, Any] | None, default: None
                Action-specific parameters such as file paths, launch options, or timeout
                settings.

            Returns
            -------
            dict[str, Any]
                Status payload returned by the CFX workflow backend.
            """
            workflow = cast(
                Callable[..., Awaitable[dict[str, Any]]] | None,
                getattr(self.backend, "cfx_workflow", None),
            )
            if not callable(workflow):
                return {"status": "error", "message": "CFX workflow is unavailable."}
            return await workflow(action=action, params=params or {})

    def _tool_cfx_model_context(self) -> None:
        """Register the ``cfx_model_context`` MCP tool for compact model queries.

        Returns
        -------
        None
            No value is returned. The tool is added to the FastMCP server.
        """

        @self.tool(
            name="cfx_model_context",
            description=(
                "Return a targeted, compact CFX model context slice. Actions: "
                "summary, list_named_objects, find_named_object, "
                "select_named_objects, state, api_help, find_api, allowed_values, "
                "targeted_context. Use max_items to keep responses small."
            ),
        )
        @typed_guard
        async def cfx_model_context(
            action: str = "summary",
            params: dict[str, Any] | None = None,
            max_items: int = 20,
        ) -> dict[str, Any]:
            """Return a targeted slice of active CFX model context.

            Parameters
            ----------
            action : str, default: 'summary'
                Component-management action to apply.
            params : dict[str, Any] | None, default: None
                Query-specific options such as paths, object names, or search text.
            max_items : int, default: 20
                Maximum number of context items to include in the response.

            Returns
            -------
            dict[str, Any]
                Structured response payload for the requested operation.
            """
            context = cast(
                Callable[..., Awaitable[dict[str, Any]]] | None,
                getattr(self.backend, "cfx_model_context", None),
            )
            if not callable(context):
                return {"status": "error", "message": "CFX model context is unavailable."}
            return await context(
                action=action,
                params=params or {},
                max_items=max_items,
            )


__all__ = ["CFXMCP"]
