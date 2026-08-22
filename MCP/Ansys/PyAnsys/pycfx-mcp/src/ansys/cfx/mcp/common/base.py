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

"""Base MCP server for the CFX MCP leaf.

A leaf:

- Picks one or more `Backend` instances at construction time.
- Inherits from `PyAnsysBaseMCP` so it can be registered alongside other
  PyAnsys MCP servers at the organization level.
- Auto-registers the requested tool surface from `ALL_TOOLS`, including
    `session_status`, `connect`, `disconnect`, model-context helpers,
    `run_code`, `validate_code`, and optional lifecycle/reporting tools.

Concrete leaves only have to declare which tools to *expose* as a subset of
the preceding list, keeping the MCP surface lean per leaf.
"""

from __future__ import annotations

import logging
import tempfile
from typing import Any, Awaitable, Callable, Iterable, Optional

from ansys.common.mcp.server import PyAnsysBaseMCP

from ansys.cfx.mcp.common.backend import Backend
from ansys.cfx.mcp.common.errors import (
    BackendUnavailable,
    InvalidArguments,
    NotConnected,
    typed_guard,
)
from ansys.cfx.mcp.common.models import ConnectResult, SessionStatus

logger = logging.getLogger("ansys.cfx.mcp.base")


# Default tool catalog. Leaves cherry-pick the ones they want to expose.
ALL_TOOLS = (
    "session_status",
    "connect",
    "disconnect",
    "error_remediation",
    "list_named_objects",
    "find_named_object",
    "select_named_objects",
    "find_api",
    "get_state",
    "get_targeted_context",
    "get_help",
    "solver_status",
    "run_code",
    "validate_code",
    "screenshot",
    "manage_component",
    "summarize_setup",
    "simulation_report",
)


class FluidsLeafMCP(PyAnsysBaseMCP):
    """Base server class for a single shared MCP leaf."""

    def run(
        self, transport: str = "stdio", host: str | None = None, port: int | None = None
    ) -> None:
        """Run the MCP server event loop for the configured transport.

        Parameters
        ----------
        transport : str, optional
            MCP transport implementation to use. Default is ``'stdio'``.
        host : str | None, optional
            Host interface for the MCP transport. Default is ``None``.
        port : int | None, optional
            Port of the running CFX service to attach to. Default is ``None``.

        Returns
        -------
        None
            No value is returned; side effects are applied to the relevant cache, session, or
            server.
        """
        parent_run = getattr(super(), "run", None)
        if not callable(parent_run):
            raise RuntimeError(
                "PyAnsys MCP runtime is unavailable: missing base `run()` implementation. "
                "Install `ansys-common-mcp` (or equivalent runtime dependency) to launch this "
                "server."
            )
        if transport == "stdio":
            parent_run(transport="stdio")
            return
        parent_run(transport="http", host=host or "127.0.0.1", port=port or 8000)

    leaf_name: str = "fluids"
    default_backend_kind: Optional[str] = None
    cache_ttl_seconds: float = 30.0
    connect_on_startup: bool = False

    #: Short label used to name component lifecycle tools.
    #: Each leaf sets this to match its managed component:
    #: for example ``"cfx"`` for the CFX leaf.
    component_label: str = ""

    #: Description surfaced to clients for the ``error_remediation`` tool.
    #: Leaves should override with a domain-specific description so the
    #: tool is reliably picked up by tool-discovery / function-calling.
    error_remediation_description: str = (
        "Generate a Markdown remediation / how-to answer for a "
        "natural-language request (error message, workflow question, "
        "etc.). The backend calls the upstream chat endpoint and returns "
        "the rendered Markdown text. Optional `context` is forwarded "
        "verbatim to the backend."
    )

    def __init__(
        self,
        *,
        backends: dict[str, Backend],
        expose_tools: Iterable[str] = ALL_TOOLS,
        hide_connection_tools: bool = False,
        name: Optional[str] = None,
        **fastmcp_kwargs: Any,
    ) -> None:
        """Initialize this object with the dependencies required for later operations.

        Parameters
        ----------
        backends : dict[str, Backend]
            Backend implementations that this leaf server can select from.
        expose_tools : Iterable[str], optional
            Tool names to expose for this leaf server. Default is ``ALL_TOOLS``.
        hide_connection_tools : bool, optional
            Whether connection-management tools should be omitted from registration. Default is
            ``False``.
        name : Optional[str], optional
            Name of the object, resource, or field to process. Default is ``None``.
        fastmcp_kwargs : Any
            Additional keyword arguments forwarded to FastMCP.

        Returns
        -------
        None
            No value is returned; side effects are applied to the relevant cache, session, or
            server.
        """
        if not backends:
            raise ValueError(f"{self.leaf_name}: at least one backend is required")
        super().__init__(
            name=name or f"ansys-cfx-mcp-{self.leaf_name}",
            need_python=False,
            **fastmcp_kwargs,
        )

        self._backends = backends
        self._active_kind: Optional[str] = None
        requested_tools = set(expose_tools)
        if hide_connection_tools:
            requested_tools.discard("connect")
            requested_tools.discard("disconnect")
        self._exposed = requested_tools

        if self.default_backend_kind and self.default_backend_kind in backends:
            self._active_kind = self.default_backend_kind

        # Opt-in observers invoked after every ``run_code`` tool call.
        # The agent layer registers a learning observer that classifies
        # failures and records constraints into
        # :class:`LearnedConstraints`, so even ad-hoc client-driven
        # ``run_code`` calls (i.e. those that bypass the planner) feed
        # the same learning store the retry loop reads from.
        self._run_code_observers: list[Callable[..., Awaitable[None] | None]] = []

        self._register_tools()
        self._register_resources()

    # ------------------------------------------------------------------
    # PyAnsysBaseMCP abstract methods
    # ------------------------------------------------------------------

    def product_startup(self) -> None:  # noqa: D401
        """Run product-specific startup hooks before serving MCP requests.

        Returns
        -------
        None
            No value is returned; side effects are applied to the relevant cache, session, or
            server.
        """
        logger.info("%s leaf starting (backends=%s)", self.leaf_name, list(self._backends))

    def product_cleanup(self) -> None:  # noqa: D401
        """Run product-specific cleanup hooks before shutdown.

        Returns
        -------
        None
            No value is returned; side effects are applied to the relevant cache, session, or
            server.
        """
        for backend in self._backends.values():
            try:
                # Backends own their own event loop integration; best-effort sync close.
                close = getattr(backend, "close_sync", None)
                if callable(close):
                    close()
            except Exception:
                logger.exception("Error during cleanup of %s", backend.label)

    # ------------------------------------------------------------------
    # Backend selection
    # ------------------------------------------------------------------

    @property
    def backend(self) -> Backend:
        """Return the currently active backend instance.

        Returns
        -------
        Backend
            Value computed by the helper for the requested CFX workflow.
        """
        if self._active_kind is None:
            # If only one backend is configured, treat it as active.
            if len(self._backends) == 1:
                self._active_kind = next(iter(self._backends))
            else:
                raise NotConnected(
                    f"No active backend selected for {self.leaf_name}. Call `connect`."
                )
        return self._backends[self._active_kind]

    # ------------------------------------------------------------------
    # Tool registration
    # ------------------------------------------------------------------

    def _register_tools(self) -> None:
        """Register MCP tools exposed by this leaf server.

        Returns
        -------
        None
            No value is returned; side effects are applied to the relevant cache, session, or
            server.
        """
        if "session_status" in self._exposed:
            self._tool_session_status()
        if "connect" in self._exposed:
            self._tool_connect()
        if "disconnect" in self._exposed:
            self._tool_disconnect()
        if "error_remediation" in self._exposed:
            self._tool_error_remediation()
        if "list_named_objects" in self._exposed:
            self._tool_list_named_objects()
        if "find_named_object" in self._exposed:
            self._tool_find_named_object()
        if "select_named_objects" in self._exposed:
            self._tool_select_named_objects()
        if "find_api" in self._exposed:
            self._tool_find_api()
        if "get_state" in self._exposed:
            self._tool_get_state()
        if "get_targeted_context" in self._exposed:
            self._tool_get_targeted_context()
        if "get_help" in self._exposed:
            self._tool_get_help()
        if "solver_status" in self._exposed:
            self._tool_solver_status()
        if "run_code" in self._exposed:
            self._tool_run_code()
        if "validate_code" in self._exposed:
            self._tool_validate_code()
        if "screenshot" in self._exposed:
            self._tool_screenshot()
        if "manage_component" in self._exposed:
            self._tool_manage_component()
        if "summarize_setup" in self._exposed:
            self._tool_summarize_setup()
        if "simulation_report" in self._exposed:
            self._tool_simulation_report()

    # ------------------------------------------------------------------
    # Resource registration
    # ------------------------------------------------------------------

    def _register_resources(self) -> None:
        """Register MCP resources exposed by this leaf server.

        Returns
        -------
        None
            No value is returned; side effects are applied to the relevant cache, session, or
            server.
        """
        toolsets_fn = self.build_toolsets

        @self.resource(
            "toolsets://definition",
            name="toolsets_definition",
            description="Toolset definitions for PyAnsysMCPService discovery.",
            mime_type="application/json",
        )
        def get_toolsets() -> list[dict[str, Any]]:
            """Return toolset metadata describing the exposed MCP tools.

            Returns
            -------
            list[dict[str, Any]]
                List of structured records matching the request.
            """
            return toolsets_fn()

    # ------------------------------------------------------------------
    # Toolset definitions
    # ------------------------------------------------------------------

    #: Master catalog mapping every tool to its logical toolset.
    #: Tools not listed here fall into the "general" toolset.
    _TOOLSET_CATALOGUE: dict[str, dict[str, Any]] = {
        "connection": {
            "description": ("Tools for connecting to and managing CFX sessions."),
            "skill": (
                "Call session_status to check connectivity before other "
                "operations. Use connect to start or attach to CFX-Pre, "
                "CFX Solver, or CFD-Post resources. Call disconnect for "
                "graceful cleanup."
            ),
            "tools": ["session_status", "connect", "disconnect"],
        },
        "code-validation": {
            "description": ("Tools for validating PyCFX snippets before execution."),
            "skill": "Use validate_code for dry-run checks before execution.",
            "tools": ["validate_code"],
        },
        "cfx-workflow": {
            "description": ("Tools for routed CFX lifecycle actions."),
            "skill": (
                "Use cfx_workflow for common CFX lifecycle actions before "
                "falling back to custom code. Supported actions include "
                "status, start_pre, import_mesh, write_def, start_solver, "
                "wait_solver, get_results_file, and open_post."
            ),
            "tools": ["cfx_workflow"],
        },
        "cfx-model-context": {
            "description": ("Tools for bounded CFX model and API context."),
            "skill": (
                "Use cfx_model_context for compact summaries, named-object "
                "lookup, state snippets, API help, allowed values, and "
                "targeted context. Keep max_items small for broad discovery "
                "and request more detail only for selected paths."
            ),
            "tools": ["cfx_model_context"],
        },
        "api-discovery": {
            "description": ("Tools for exploring and searching the settings API tree."),
            "skill": (
                "Use find_api for keyword-based semantic search. Use "
                "get_help for docstrings and child listings. Use "
                "get_targeted_context for batched disambiguation "
                "(active-status + state + allowed-values + child-names "
                "in one round-trip)."
            ),
            "tools": [
                "find_api",
                "get_help",
                "get_targeted_context",
            ],
        },
        "named-objects": {
            "description": (
                "Tools for discovering and selecting named objects in the settings tree."
            ),
            "skill": (
                "Use list_named_objects to enumerate a collection. "
                "Use find_named_object to resolve a symbolic name "
                "across all collections. Use select_named_objects "
                "for glob-based filtering."
            ),
            "tools": [
                "list_named_objects",
                "find_named_object",
                "select_named_objects",
            ],
        },
        "state-inspection": {
            "description": ("Tools for reading live solver state and status."),
            "skill": (
                "Use get_state to read current values of settings "
                "paths (confirm active first via get_targeted_context). "
                "Use solver_status for iteration count, residuals, and "
                "convergence info."
            ),
            "tools": ["get_state", "solver_status"],
        },
        "code-execution": {
            "description": (
                "Tools for validating and running Python against the active CFX backend."
            ),
            "skill": (
                "Use validate_code before running generated or user-provided "
                "Python. Use run_code only when a routed cfx_workflow action "
                "or cfx_model_context query is not enough."
            ),
            "tools": ["run_code", "validate_code"],
        },
        "visualization": {
            "description": ("Tools for capturing visual output from the solver."),
            "skill": (
                "Use screenshot to capture the current model view as a PNG image for the user."
            ),
            "tools": ["screenshot"],
        },
        "error-handling": {
            "description": ("Tools for diagnosing and remediating errors."),
            "skill": (
                "Use error_remediation when the user reports an error "
                "message or asks a workflow question. Returns a Markdown "
                "remediation answer from the upstream chat endpoint."
            ),
            "tools": ["error_remediation"],
        },
        "component-lifecycle": {
            "description": (
                "Tools for activating, deactivating, updating, and "
                "refreshing solver/component instances in Fluids One."
            ),
            "skill": (
                "Use manage_component with action='activate' to start "
                "a solver component. Use action='deactivate' to cleanly "
                "stop it. Use action='update' to apply pending config "
                "changes. Use action='refresh' to force a state reload."
            ),
            "tools": ["manage_component"],
        },
        "reports": {
            "description": (
                "Tools for generating simulation reports and retrieving setup "
                "summaries from the solver."
            ),
            "skill": (
                "Use summarize_setup to get the full solver setup "
                "overview (models, materials, BCs, solver settings, "
                "schemes, limits) in one call. Use simulation_report "
                "to generate or export a rich simulation report "
                "(HTML, PDF, or PPTX). Prefer summarize_setup as the "
                "first tool when the user asks 'show me my setup' or "
                "'what is configured?'."
            ),
            "tools": ["summarize_setup", "simulation_report"],
        },
    }

    def build_toolsets(self) -> list[dict[str, Any]]:
        """Build toolset metadata for the tools exposed by this leaf server.

        Returns
        -------
        list[dict[str, Any]]
            List of structured records matching the request.
        """
        result: list[dict[str, Any]] = []
        for name, defn in self._TOOLSET_CATALOGUE.items():
            # Only include tools that are actually exposed by this leaf.
            active_tools = [t for t in defn["tools"] if t in self._exposed]
            if not active_tools:
                continue
            result.append(
                {
                    "name": name,
                    "description": defn["description"],
                    "skill": defn["skill"],
                    "tools": active_tools,
                }
            )
        return result

    # ---- session.status -----------------------------------------------

    def _tool_session_status(self) -> None:
        """Register the ``session_status`` MCP tool for this leaf server.

        Returns
        -------
        None
            No value is returned; the tool is added to the FastMCP server.
        """
        leaf = self.leaf_name

        @self.tool(
            name="session_status",
            description=(
                f"Report whether the {leaf} leaf has an active backend. "
                "Safe to call before `connect`. Returns the connected endpoint, "
                "backend kind, and the list of tools available in the current state."
            ),
        )
        @typed_guard
        async def session_status() -> SessionStatus:
            """Report the active backend connection state for this leaf server.

            Returns
            -------
            SessionStatus
                Connection status, backend kind, endpoint, notes, and currently
                available tool names.
            """
            if self._active_kind is None:
                return SessionStatus(leaf=leaf, connected=False, notes=["No backend connected."])
            return self._backends[self._active_kind].status(leaf)

    # ---- connect / disconnect ----------------------------------------

    def _tool_connect(self) -> None:
        """Register the ``connect`` MCP tool for backend selection.

        Returns
        -------
        None
            No value is returned; side effects are applied to the relevant cache, session, or
            server.
        """
        leaf = self.leaf_name
        kinds = list(self._backends)

        @self.tool(
            name="connect",
            description=(
                f"Connect the {leaf} leaf to a backend. "
                f"Available backend kinds: {kinds}. "
                "Pass `backend_kind` to choose, or omit it to auto-select. "
                "Backend-specific options (url/token/ip/port/...) go in "
                "`connect_kwargs` as a dict and are forwarded to the backend."
            ),
        )
        @typed_guard
        async def connect(
            backend_kind: Optional[str] = None,
            connect_kwargs: Optional[dict[str, Any]] = None,
        ) -> ConnectResult:
            """Connect this backend to a CFX runtime or service.

            Parameters
            ----------
            backend_kind : Optional[str], optional
                Backend kind to connect, or ``None`` to use the default backend.
                Default is ``None``.
            connect_kwargs : Optional[dict[str, Any]], optional
                Backend-specific connection options forwarded to the selected backend.
                Default is ``None``.

            Returns
            -------
            ConnectResult
                Connection result describing the selected backend session.
            """
            kind = backend_kind or self.default_backend_kind
            if kind is None:
                if len(self._backends) == 1:
                    kind = next(iter(self._backends))
                else:
                    raise InvalidArguments(f"backend_kind is required; choose one of {kinds}")
            if kind not in self._backends:
                raise InvalidArguments(f"Unknown backend_kind '{kind}'; available: {kinds}")
            backend = self._backends[kind]
            result = await backend.connect(**(connect_kwargs or {}))
            if result.status == "ok":
                self._active_kind = kind
            return result

    def _tool_disconnect(self) -> None:
        """Register the ``disconnect`` MCP tool for backend shutdown.

        Returns
        -------
        None
            No value is returned; side effects are applied to the relevant cache, session, or
            server.
        """

        @self.tool(
            name="disconnect",
            description=f"Disconnect the {self.leaf_name} leaf's active backend.",
        )
        @typed_guard
        async def disconnect() -> dict[str, Any]:
            """Disconnect this backend from its active CFX runtime or service.

            Returns
            -------
            dict[str, Any]
                Structured response payload for the requested operation.
            """
            if self._active_kind is None:
                return {"status": "ok", "message": "No active backend."}
            backend = self._backends[self._active_kind]
            await backend.disconnect()
            self._active_kind = None
            return {"status": "ok"}

    def _tool_error_remediation(self) -> None:
        """Register the ``error_remediation`` MCP tool for recovery guidance.

        Returns
        -------
        None
            No value is returned; the tool is added to the FastMCP server.
        """

        @self.tool(
            name="error_remediation",
            description=self.error_remediation_description,
        )
        @typed_guard
        async def error_remediation(
            remediation_request: str,
            context: Optional[dict[str, Any]] = None,
        ):
            """Ask the active backend for guidance after a failed CFX operation.

            Parameters
            ----------
            remediation_request : str
                Error message, failing code, or user request that needs recovery guidance.
            context : Optional[dict[str, Any]], optional
                Additional details such as validation output, backend status, or recent tool
                results. Default is ``None``.

            Returns
            -------
            Any
                Remediation response from the backend, typically containing suggested fixes
                and diagnostic detail.
            """
            if not remediation_request or not remediation_request.strip():
                raise InvalidArguments("remediation_request must be a non-empty string")
            return await self.backend.error_remediation(
                remediation_request,
                context=context,
            )

    # ---- live model context -------------------------------------------

    def _tool_list_named_objects(self) -> None:
        """Register the ``list_named_objects`` MCP tool for model inventory.

        Returns
        -------
        None
            No value is returned; side effects are applied to the relevant cache, session, or
            server.
        """

        @self.tool(
            name="list_named_objects",
            description=(
                "Return a mapping of named-object collection paths to the names "
                "of the objects currently defined. Cached briefly to keep "
                "follow-up tool calls fast. Supports pagination: pass "
                "`limit` (>=1) and optional `offset` to slice the names "
                "of each collection; the response then includes a "
                "`_pagination` envelope with the original totals so the "
                "caller can request more if needed."
            ),
        )
        @typed_guard
        async def list_named_objects(
            limit: Optional[int] = None,
            offset: int = 0,
        ) -> dict[str, Any]:
            """List named objects available in the active context.

            Parameters
            ----------
            limit : Optional[int], optional
                Maximum number of records to return. Default is ``None``.
            offset : int, optional
                Number of matching records to skip before returning results. Default is ``0``.

            Returns
            -------
            dict[str, Any]
                Structured response payload for the requested operation.
            """
            mapping = await self.backend.list_named_objects()
            if limit is None and not offset:
                return mapping
            if limit is not None and limit < 1:
                raise InvalidArguments("limit must be >= 1")
            if offset < 0:
                raise InvalidArguments("offset must be >= 0")
            sliced: dict[str, Any] = {}
            totals: dict[str, int] = {}
            for coll, names in (mapping or {}).items():
                lst = list(names or [])
                totals[coll] = len(lst)
                end = offset + limit if limit is not None else None
                sliced[coll] = lst[offset:end]
            sliced["_pagination"] = {
                "offset": offset,
                "limit": limit,
                "totals": totals,
                "truncated": any(
                    (limit is not None and totals[c] > offset + limit) or offset > 0 for c in totals
                ),
            }
            return sliced

    def _tool_find_named_object(self) -> None:
        """Register the ``find_named_object`` MCP tool for object lookup.

        Returns
        -------
        None
            No value is returned; side effects are applied to the relevant cache, session, or
            server.
        """

        @self.tool(
            name="find_named_object",
            description=(
                "Resolve a symbolic name (e.g. 'Default Domain') across every "
                "named-object collection. Returns a list of "
                "{collection_path, name, exact} matches sorted with exact "
                "matches first. Use this BEFORE generating code so you know "
                "which collection (flow, domain, boundary, user, ...) "
                "the user actually meant; if multiple matches exist, ask a "
                "clarification."
            ),
        )
        @typed_guard
        async def find_named_object(name: str) -> list[dict[str, Any]]:
            """Find named object matching the request.

            Parameters
            ----------
            name : str
                Name of the object, resource, or field to process.

            Returns
            -------
            list[dict[str, Any]]
                List of structured records matching the request.
            """
            return await self.backend.find_named_object(name)

    def _tool_select_named_objects(self) -> None:
        """Register the ``select_named_objects`` MCP tool for filtered object lists.

        Returns
        -------
        None
            No value is returned; side effects are applied to the relevant cache, session, or
            server.
        """

        @self.tool(
            name="select_named_objects",
            description=(
                "Expand a glob pattern over a single named-object "
                "collection and return the matching names. Use this "
                "instead of hand-curating a long list when the user "
                "asks for 'all walls', 'all inlets', 'every fluid "
                "zone', etc. — it makes the selection reproducible "
                "and survives mesh re-numbering. "
                "Arguments: `collection` is the dotted path of the "
                "named-object family (e.g. "
                "'flow.domain.boundary'); `pattern` is a "
                "Unix-shell-style glob (default `*`); "
                "`include_shadows` is accepted for compatibility and is "
                "only meaningful for backends that expose shadow names; "
                "`exclude` is an optional list of glob patterns to subtract "
                "from the result."
            ),
        )
        @typed_guard
        async def select_named_objects(
            collection: str,
            pattern: str = "*",
            include_shadows: bool = True,
            exclude: Optional[list[str]] = None,
        ) -> dict[str, Any]:
            """Select named CFX objects using collection and wildcard filters.

            Parameters
            ----------
            collection : str
                Named-object collection to inspect.
            pattern : str, optional
                Name or wildcard pattern used to select objects. Default is ``'*'``.
            include_shadows : bool, optional
                Whether shadowed names should be included in object-selection results. Default is
                ``True``.
            exclude : Optional[list[str]], optional
                Names or patterns to omit from object-selection results. Default is ``None``.

            Returns
            -------
            dict[str, Any]
                Structured response payload for the requested operation.
            """
            named = await self.backend.list_named_objects()
            return select_named_objects_from_mapping(
                named,
                collection=collection,
                pattern=pattern,
                include_shadows=include_shadows,
                exclude=exclude,
            )

    def _tool_find_api(self) -> None:
        """Register the ``find_api`` MCP tool for schema and API search.

        Returns
        -------
        None
            No value is returned; side effects are applied to the relevant cache, session, or
            server.
        """

        @self.tool(
            name="find_api",
            description=(
                "Retrieve candidate CFX API paths for a query. Returns "
                "ranked hits as {path, kind, score, ...}. Use this to "
                "locate the PyCFX path that implements a lifecycle action, "
                "model setting, named object, or query. Optional filters: "
                "`kinds` (Parameter, Command, Object, Group, Constructor) "
                "and `under` (path prefix to scope the search)."
            ),
        )
        @typed_guard
        async def find_api(
            query: str,
            top_k: int = 10,
            kinds: Optional[list[str]] = None,
            under: Optional[str] = None,
            compact: bool = False,
        ) -> list[dict[str, Any]]:
            """Find api matching the request.

            Parameters
            ----------
            query : str
                Search query used to rank CFX API or object matches.
            top_k : int, optional
                Maximum number of matches to return. Default is ``10``.
            kinds : Optional[list[str]], optional
                Optional result categories used to narrow the search. Default is ``None``.
            under : Optional[str], optional
                Optional CFX path prefix used to scope the search. Default is ``None``.
            compact : bool, optional
                Whether to return a compact representation of backend state. Default is ``False``.

            Returns
            -------
            list[dict[str, Any]]
                List of structured records matching the request.
            """
            hits = await self.backend.find_api(
                query,
                top_k=top_k,
                kinds=kinds,
                under=under,
            )
            if not compact:
                return hits
            # Slim envelope: only the fields the agent uses to pick
            # the next call. Drops schema/allowed_values/docstring
            # (~80% of the bytes per hit) so cheap discovery turns
            # don't bloat the prompt cache.
            slim: list[dict[str, Any]] = []
            for h in hits:
                desc = h.get("docstring") or h.get("description") or ""
                if isinstance(desc, str):
                    one_line = desc.strip().split("\n", 1)[0][:160]
                else:
                    one_line = ""
                slim.append(
                    {
                        "path": h.get("path"),
                        "kind": h.get("kind"),
                        "score": h.get("score"),
                        "summary": one_line,
                    }
                )
            return slim

    def _tool_get_state(self) -> None:
        """Register the ``get_state`` MCP tool for backend state queries.

        Returns
        -------
        None
            No value is returned; side effects are applied to the relevant cache, session, or
            server.
        """

        @self.tool(
            name="get_state",
            description=(
                "Return the current state of the requested settings paths. "
                "If `paths` is omitted, returns the global Fluids state summary. "
                "FAST PATH: pass `key` together with a single collection path "
                "in `paths` (e.g. paths=['setup.boundary_conditions.wall'], "
                "key='outer-wall') to fetch JUST that one named-object slice "
                "without dumping every sibling — saves substantial prompt "
                "tokens on big cases."
            ),
        )
        @typed_guard
        async def get_state(
            paths: Optional[list[str]] = None,
            key: Optional[str] = None,
        ) -> dict[str, Any]:
            """Return state for the active CFX context.

            Parameters
            ----------
            paths : Optional[list[str]], optional
                Backend paths to inspect. Default is ``None``.
            key : Optional[str], optional
                Cache key identifying the value to read, write, or invalidate. Default is ``None``.

            Returns
            -------
            dict[str, Any]
                Structured response payload for the requested operation.
            """
            if key is not None:
                if not paths or len(paths) != 1:
                    raise InvalidArguments("`key` requires exactly one collection path in `paths`")
                base = paths[0].rstrip(".")
                if base.endswith("]"):
                    raise InvalidArguments("`paths[0]` already indexes a named object; drop `key`")
                if '"' in key or "'" in key or "]" in key or "[" in key:
                    raise InvalidArguments("`key` contains invalid characters")
                paths = [f"{base}[{key}]"]
            return await self.backend.get_state(paths=paths)

    def _tool_get_targeted_context(self) -> None:
        """Register the ``get_targeted_context`` MCP tool for compact context slices.

        Returns
        -------
        None
            No value is returned; side effects are applied to the relevant cache, session, or
            server.
        """

        @self.tool(
            name="get_targeted_context",
            description=(
                "Fetch active-status, state, named-objects, child-names, and "
                "allowed values for a focused set of paths in a single call. "
                "Use this for fast disambiguation before generating code."
            ),
        )
        @typed_guard
        async def get_targeted_context(
            paths_to_check: list[str],
            named_object_types: Optional[list[str]] = None,
            instance_state_fetch: Optional[list[str]] = None,
        ) -> dict[str, Any]:
            """Return a compact context slice for the requested CFX paths or objects.

            Parameters
            ----------
            paths_to_check : list[str]
                CFX paths to check against live state or schema metadata.
            named_object_types : Optional[list[str]], optional
                Named-object categories to include in context output. Default is ``None``.
            instance_state_fetch : Optional[list[str]], optional
                Optional callback used to fetch live instance state. Default is ``None``.

            Returns
            -------
            dict[str, Any]
                Structured response payload for the requested operation.
            """
            return await self.backend.get_targeted_context(
                paths_to_check=paths_to_check,
                named_object_types=named_object_types or [],
                instance_state_fetch=instance_state_fetch or [],
            )

    def _tool_get_help(self) -> None:
        """Register the ``get_help`` MCP tool for backend help lookups.

        Returns
        -------
        None
            No value is returned; side effects are applied to the relevant cache, session, or
            server.
        """

        @self.tool(
            name="get_help",
            description=(
                "Return docstring + child names + allowed values for a "
                "specific CFX API path. Use this to confirm "
                "semantics of an ambiguous parameter (e.g. "
                "model option or boundary-condition branch) before emitting code."
            ),
        )
        @typed_guard
        async def get_help(path: str) -> dict[str, Any]:
            """Return help for the active CFX context.

            Parameters
            ----------
            path : str
                CFX API, object, schema, or file path to process.

            Returns
            -------
            dict[str, Any]
                Structured response payload for the requested operation.
            """
            return await self.backend.get_help(path)

    def _tool_solver_status(self) -> None:
        """Register the ``solver_status`` MCP tool for solver progress checks.

        Returns
        -------
        None
            No value is returned; side effects are applied to the relevant cache, session, or
            server.
        """

        @self.tool(
            name="solver_status",
            description=(
                "Return CFX Solver readiness and run status, including "
                "whether a solver session is connected or running and which "
                ".def/.res artifacts are known."
            ),
        )
        @typed_guard
        async def solver_status() -> dict[str, Any]:
            """Return CFX-Solver run status from the active backend.

            Returns
            -------
            dict[str, Any]
                Structured response payload for the requested operation.
            """
            return await self.backend.solver_status()

    # ---- code execution ------------------------------------------------

    def _tool_run_code(self) -> None:
        """Register the ``run_code`` MCP tool for Python execution.

        Returns
        -------
        None
            No value is returned; side effects are applied to the relevant cache, session, or
            server.
        """

        @self.tool(
            name="run_code",
            description=(
                "Execute Python code against the active PyCFX session namespace. "
                "The code runs with `pre`, `solver`, `post`, `session`, "
                "`cfxpre`, `cfxsolver`, and `cfxpost` helpers refreshed from "
                "the current CFX sessions. Returns stdout, stderr, and any "
                "`__return__` value. Prefer `cfx_workflow` or "
                "`cfx_model_context` for routed actions and read-only queries."
            ),
        )
        @typed_guard
        async def run_code(code: str):
            """Execute Python code in the active CFX session namespace.

            Parameters
            ----------
            code : str
                Python source code submitted for validation, grounding, or execution.

            Returns
            -------
            Any
                Backend execution result containing stdout, stderr, return value, and any
                validation or runtime diagnostics.
            """
            if not code or not code.strip():
                raise InvalidArguments("code must be a non-empty string")
            result: Any = None
            error: BaseException | None = None
            try:
                result = await self.backend.run_code(code)
                return result
            except BaseException as exc:
                error = exc
                raise
            finally:
                # Belt-and-braces: even backends that don't override
                # `invalidate_live_caches` get them dropped here so the
                # next live tool sees post-mutation state.
                self.backend.invalidate_live_caches()
                # Notify observers (learning, telemetry, audit) about
                # the call. Observer failures must never break the
                # tool result the caller already received.
                await self._notify_run_code_observers(
                    code=code,
                    result=result,
                    error=error,
                )

    def register_run_code_observer(
        self,
        observer: Callable[..., Awaitable[None] | None],
    ) -> None:
        """Register a callback that observes successful run-code executions.

        Parameters
        ----------
        observer : Callable[..., Awaitable[None] | None]
            Callback to notify after run-code execution.

        Returns
        -------
        None
            No value is returned; the callback is stored for later notifications.
        """
        if not callable(observer):
            raise TypeError("observer must be callable")
        self._run_code_observers.append(observer)

    async def _notify_run_code_observers(
        self,
        *,
        code: str,
        result: Any,
        error: BaseException | None,
    ) -> None:
        """Notify registered callbacks after run-code execution completes.

        Parameters
        ----------
        code : str
            Python source code submitted for validation, grounding, or execution.
        result : Any
            Run-code result passed to observers or recorded in history.
        error : BaseException | None
            Exception raised by the backend, when execution failed.

        Returns
        -------
        None
            No value is returned; observers are invoked for their side effects.
        """
        if not self._run_code_observers:
            return
        import inspect

        for observer in list(self._run_code_observers):
            try:
                ret = observer(code=code, result=result, error=error)
                if inspect.isawaitable(ret):
                    await ret
            except Exception:
                logger.debug("run_code observer failed", exc_info=True)

    def _tool_validate_code(self) -> None:
        """Register the ``validate_code`` MCP tool for dry-run validation.

        Returns
        -------
        None
            No value is returned; the tool is added to the FastMCP server.
        """

        @self.tool(
            name="validate_code",
            description=(
                "Dry-run / validate CFX Python without applying side effects. "
                "Returns parse / type / semantic feedback."
            ),
        )
        @typed_guard
        async def validate_code(code: str):
            """Validate CFX Python without applying model changes.

            Parameters
            ----------
            code : str
                Python source code submitted for validation, grounding, or execution.

            Returns
            -------
            Any
                Backend validation result describing syntax, safety, and semantic feedback.
            """
            if not code or not code.strip():
                raise InvalidArguments("code must be a non-empty string")
            return await self.backend.validate_code(code)

    # ---- component lifecycle -----------------------------------------

    def _tool_manage_component(self) -> None:
        """Register the ``manage_component`` MCP tool for component lifecycle actions.

        Returns
        -------
        None
            No value is returned; side effects are applied to the relevant cache, session, or
            server.
        """
        label = self.component_label or self.leaf_name

        @self.tool(
            name=f"manage_{label}",
            description=(
                f"Manage the {label} component lifecycle in Fluids One. "
                "Actions:\n"
                f"  • activate — start or resume the {label} component.\n"
                f"  • deactivate — cleanly stop {label} and free resources.\n"
                f"  • update — apply pending configuration changes.\n"
                f"  • refresh — force reload state from the server.\n"
                "Returns a status dict."
            ),
        )
        @typed_guard
        async def manage_component(action: str) -> dict[str, Any]:
            """Apply a generic component-management action through the active backend.

            Parameters
            ----------
            action : str
                Component-management action to apply.

            Returns
            -------
            dict[str, Any]
                Structured response payload for the requested operation.
            """
            action = (action or "").strip().lower()
            if action == "activate":
                return await self.backend.activate_component()
            elif action == "deactivate":
                return await self.backend.deactivate_component()
            elif action == "update":
                return await self.backend.update_component()
            elif action == "refresh":
                return await self.backend.refresh_component()
            else:
                raise InvalidArguments(
                    f"invalid action {action!r}; use 'activate', 'deactivate', 'update', or 'refresh'"  # noqa: E501
                )

    # ---- visuals ------------------------------------------------------

    def _tool_screenshot(self) -> None:
        """Register the ``screenshot`` MCP tool for backend image capture.

        Returns
        -------
        None
            No value is returned; side effects are applied to the relevant cache, session, or
            server.
        """

        @self.tool(
            name="screenshot",
            description=(
                "Capture a PNG screenshot of the current model view. "
                "Returns `{format: 'png', data: <base64>}`."
            ),
        )
        @typed_guard
        async def screenshot(view: Optional[str] = None) -> dict[str, Any]:
            """Capture a screenshot from the active backend, when supported.

            Parameters
            ----------
            view : Optional[str], optional
                Optional view name for screenshot capture. Default is ``None``.

            Returns
            -------
            dict[str, Any]
                Structured response payload for the requested operation.
            """
            return await self.backend.screenshot(view=view)

    # ---- reports ------------------------------------------------------

    def _tool_summarize_setup(self) -> None:
        """Register the ``summarize_setup`` MCP tool for setup summaries.

        Returns
        -------
        None
            No value is returned; side effects are applied to the relevant cache, session, or
            server.
        """

        @self.tool(
            name="summarize_setup",
            description=(
                "Return the full solver setup summary — models, "
                "materials, boundary conditions, solver settings, "
                "discretization schemes, and limits — in a single "
                "call. Equivalent to the solver setup summary report. "
                "Use this FIRST when the user asks 'show me my "
                "setup' or 'what is configured?'. Read-only."
            ),
        )
        @typed_guard
        async def summarize_setup() -> dict[str, Any]:
            """Summarize the current CFX setup for humans and model prompts.

            Returns
            -------
            dict[str, Any]
                Structured response payload for the requested operation.
            """
            tmp_handle = tempfile.NamedTemporaryFile(suffix=".txt", delete=False)
            tmp_handle.close()
            tmp = tmp_handle.name.replace("\\", "/")
            snippet = (
                f"session.settings.results.report.summary(write_to_file=True, file_name={tmp!r})"
            )
            result = await self.backend.run_code(snippet)
            status = getattr(result, "status", "")
            if status != "ok":
                err = (
                    getattr(result, "stderr", None)
                    or getattr(result, "message", None)
                    or "summary command failed"
                )
                return {"error": err}
            import pathlib as _pl

            fp = _pl.Path(tmp)
            content = ""
            try:
                if fp.exists():
                    content = fp.read_text(
                        encoding="utf-8",
                        errors="replace",
                    )
                    fp.unlink(missing_ok=True)
            except OSError:
                pass
            return {"summary": content or "(no output)"}

    def _tool_simulation_report(self) -> None:
        """Register the ``simulation_report`` MCP tool for report generation.

        Returns
        -------
        None
            No value is returned; side effects are applied to the relevant cache, session, or
            server.
        """

        @self.tool(
            name="simulation_report",
            description=(
                "Generate or export a rich simulation report from "
                "the connected solver session. Actions:\n"
                "  • generate — create a named simulation report.\n"
                "  • export_html — export an existing report as HTML.\n"
                "  • export_pdf — export as PDF.\n"
                "  • export_pptx — export as PowerPoint.\n"
                "  • list — list previously generated reports.\n"
                "Returns the output path or report list."
            ),
        )
        @typed_guard
        async def simulation_report(
            action: str = "list",
            report_name: str = "default-report",
            output_path: Optional[str] = None,
        ) -> dict[str, Any]:
            """Generate a simulation report from the active backend state.

            Parameters
            ----------
            action : str, optional
                Component-management action to apply. Default is ``'list'``.
            report_name : str, optional
                Name assigned to the generated simulation report. Default is ``'default-report'``.
            output_path : Optional[str], optional
                Optional file path for writing report artifacts. Default is ``None``.

            Returns
            -------
            dict[str, Any]
                Structured response payload for the requested operation.
            """
            action = (action or "list").strip().lower()
            valid = {
                "generate",
                "export_html",
                "export_pdf",
                "export_pptx",
                "list",
            }
            if action not in valid:
                return {
                    "error": f"invalid action {action!r}",
                    "valid_actions": sorted(valid),
                }

            if action == "list":
                snippet = (
                    "session.settings.results.report.simulation_reports.list_simulation_reports()"
                )
                result = await self.backend.run_code(snippet)
                if getattr(result, "status", "") != "ok":
                    return {
                        "error": (
                            getattr(result, "stderr", None) or "list_simulation_reports failed"
                        ),
                    }
                return {
                    "reports": getattr(result, "return_value", None),
                    "stdout": getattr(result, "stdout", "") or None,
                }

            if action == "generate":
                snippet = (
                    "session.settings.results.report"
                    ".simulation_reports"
                    f".generate_simulation_report("
                    f"report_name={report_name!r})"
                )
            elif action == "export_html":
                out = output_path or tempfile.mkdtemp(
                    prefix="cfx_report_",
                ).replace("\\", "/")
                snippet = (
                    "session.settings.results.report"
                    ".simulation_reports"
                    ".export_simulation_report_as_html("
                    f"report_name={report_name!r}, "
                    f"output_dir={out!r})"
                )
            elif action == "export_pdf":
                if output_path:
                    out = output_path
                else:
                    tmp_handle = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
                    tmp_handle.close()
                    out = tmp_handle.name.replace("\\", "/")
                snippet = (
                    "session.settings.results.report"
                    ".simulation_reports"
                    ".export_simulation_report_as_pdf("
                    f"report_name={report_name!r}, "
                    f"file_name={out!r})"
                )
            else:  # export_pptx
                if output_path:
                    out = output_path
                else:
                    tmp_handle = tempfile.NamedTemporaryFile(suffix=".pptx", delete=False)
                    tmp_handle.close()
                    out = tmp_handle.name.replace("\\", "/")
                snippet = (
                    "session.settings.results.report"
                    ".simulation_reports"
                    ".export_simulation_report_as_pptx("
                    f"report_name={report_name!r}, "
                    f"file_name={out!r})"
                )

            result = await self.backend.run_code(snippet)
            if getattr(result, "status", "") != "ok":
                return {
                    "error": (getattr(result, "stderr", None) or f"{action} failed"),
                }
            return {
                "action": action,
                "report_name": report_name,
                "output_path": (out if action != "generate" else None),
                "stdout": getattr(result, "stdout", "") or None,
                "note": (f"Simulation report {action} completed."),
            }


__all__ = [
    "FluidsLeafMCP",
    "ALL_TOOLS",
    "BackendUnavailable",
    "NotConnected",
    "select_named_objects_from_mapping",
]


def select_named_objects_from_mapping(
    named: dict[str, list[str]],
    *,
    collection: str,
    pattern: str = "*",
    include_shadows: bool = True,
    exclude: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Filter named CFX objects from a mapping using include and exclude rules.

    Parameters
    ----------
    named : dict[str, list[str]]
        Mapping of named objects grouped by collection.
    collection : str
        Named-object collection to inspect.
    pattern : str, optional
        Name or wildcard pattern used to select objects. Default is ``'*'``.
    include_shadows : bool, optional
        Whether shadowed names should be included in object-selection results. Default is
        ``True``.
    exclude : Optional[list[str]], optional
        Names or patterns to omit from object-selection results. Default is ``None``.

    Returns
    -------
    dict[str, Any]
        Structured response payload for the requested operation.
    """
    import fnmatch

    candidates = (
        named.get(collection)
        or named.get(collection.replace(".", "/").replace("_", "-"))
        or named.get(collection.replace("/", ".").replace("-", "_"))
    )
    if candidates is None:
        return {
            "collection": collection,
            "pattern": pattern,
            "names": [],
            "available_collections": sorted(named.keys()),
            "note": ("collection not found; pass one of `available_collections`."),
        }
    matched = [n for n in candidates if fnmatch.fnmatchcase(n, pattern)]
    if not include_shadows:
        matched = [n for n in matched if not n.endswith("-shadow")]
    for ex_pattern in exclude or []:
        matched = [n for n in matched if not fnmatch.fnmatchcase(n, ex_pattern)]
    return {
        "collection": collection,
        "pattern": pattern,
        "include_shadows": include_shadows,
        "exclude": list(exclude or []),
        "names": matched,
        "count": len(matched),
    }
