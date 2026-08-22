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

"""CFX backend that bridges PyCFX sessions into the MCP backend interface."""

from __future__ import annotations

import ast
from io import StringIO
import logging
import os
import re
import sys
from typing import Any, cast

from ansys.cfx.mcp.cfx.dependencies import (
    check_cfx_prerequisites,
)
from ansys.cfx.mcp.cfx.sessions.session_manager import SessionManager
from ansys.cfx.mcp.common.backend import Backend
from ansys.cfx.mcp.common.models import ConnectResult, RunCodeResult, SessionStatus
from ansys.cfx.mcp.common.validation import (
    _ALLOWED_BUILTINS,
    _ALLOWED_IMPORTS,
    validate_python_source,
)

_LOG = logging.getLogger(__name__)


def _strict_validation_enabled() -> bool:
    """Check if opt-in strict schema validation is enabled.

    Set ``CFX_MCP_STRICT_VALIDATION=1`` (or ``FLUIDS_MCP_STRICT_VALIDATION=1``)
    to promote near-match CFX schema-path warnings to hard
    ``unknown_cfx_path`` errors. The default is off, which means near-matches stay
    warnings so callers can correct them.
    """
    for var in ("CFX_MCP_STRICT_VALIDATION", "FLUIDS_MCP_STRICT_VALIDATION"):
        val = os.environ.get(var)
        if val is not None and val.strip().lower() in {"1", "true", "yes", "on"}:
            return True
    return False


def _collect_domains_and_boundaries(
    flow_state: Any,
) -> tuple[list[str], list[str]]:
    """Collect domain and boundary names from the serialized CFX flow state.

    Parameters
    ----------
    flow_state : Any
        Serialized CFX flow-state mapping to inspect or augment.

    Returns
    -------
    tuple[list[str], list[str]]
        Value computed by the helper for the requested CFX workflow.
    """
    domains: list[str] = []
    boundaries: list[str] = []
    if not isinstance(flow_state, dict):
        return domains, boundaries
    for analysis in flow_state.values():
        if not isinstance(analysis, dict):
            continue
        domain_map = analysis.get("domain")
        if not isinstance(domain_map, dict):
            continue
        for domain_name, domain_data in domain_map.items():
            if domain_name not in domains:
                domains.append(domain_name)
            if not isinstance(domain_data, dict):
                continue
            boundary_map = domain_data.get("boundary")
            if not isinstance(boundary_map, dict):
                continue
            for boundary_name in boundary_map:
                if boundary_name not in boundaries:
                    boundaries.append(boundary_name)
    return domains, boundaries


def _walk_live_domains_and_boundaries(
    flow_coll: Any,
) -> tuple[list[str], list[str]]:
    """Walk live PyCFX flow objects to discover domains and boundaries.

    Parameters
    ----------
    flow_coll : Any
        Live PyCFX flow collection used to discover domains and boundaries.

    Returns
    -------
    tuple[list[str], list[str]]
        Value computed by the helper for the requested CFX workflow.
    """
    domains: list[str] = []
    boundaries: list[str] = []
    if flow_coll is None:
        return domains, boundaries

    def _names(obj: Any) -> list[str]:
        """Return object names exposed by a PyCFX collection-like object.

        Parameters
        ----------
        obj : Any
            Object being inspected or adapted.

        Returns
        -------
        list[str]
            Value computed by the helper for the requested CFX workflow.
        """
        getter = getattr(obj, "get_object_names", None)
        if callable(getter):
            try:
                return list(getter())
            except Exception:
                _LOG.debug(
                    "Unable to read PyCFX object names with get_object_names().", exc_info=True
                )
        keys = getattr(obj, "keys", None)
        if callable(keys):
            try:
                return list(keys())
            except Exception:
                _LOG.debug("Unable to read PyCFX object names with keys().", exc_info=True)
        return []

    for analysis_name in _names(flow_coll):
        try:
            analysis = flow_coll[analysis_name]
        except Exception:
            _LOG.debug("Unable to read PyCFX flow analysis %r.", analysis_name, exc_info=True)
            analysis = None
        if analysis is None:
            continue
        domain_coll = getattr(analysis, "domain", None)
        if domain_coll is None:
            continue
        for domain_name in _names(domain_coll):
            if domain_name not in domains:
                domains.append(domain_name)
            try:
                domain_obj = domain_coll[domain_name]
            except Exception:
                _LOG.debug("Unable to read PyCFX domain %r.", domain_name, exc_info=True)
                domain_obj = None
            if domain_obj is None:
                continue
            boundary_coll = getattr(domain_obj, "boundary", None)
            if boundary_coll is None:
                continue
            for boundary_name in _names(boundary_coll):
                if boundary_name not in boundaries:
                    boundaries.append(boundary_name)
    return domains, boundaries


def _augment_flow_state_with_live_tree(flow_state: Any, flow_coll: Any) -> Any:
    """Merge live domain and boundary information into serialized flow state.

    Parameters
    ----------
    flow_state : Any
        Serialized CFX flow-state mapping to inspect or augment.
    flow_coll : Any
        Live PyCFX flow collection used to discover domains and boundaries.

    Returns
    -------
    Any
        Value computed by the helper for the requested CFX workflow.
    """
    if not isinstance(flow_state, dict):
        return flow_state
    for analysis_name, analysis_data in flow_state.items():
        if not isinstance(analysis_data, dict):
            continue
        existing_domains = analysis_data.get("domain")
        if isinstance(existing_domains, dict) and existing_domains:
            continue  # state already carries the domain tree
        try:
            analysis = flow_coll[analysis_name]
        except Exception:
            _LOG.debug("Unable to augment PyCFX flow analysis %r.", analysis_name, exc_info=True)
            analysis = None
        if analysis is None:
            continue
        domain_coll = getattr(analysis, "domain", None)
        if domain_coll is None:
            continue
        domain_map: dict[str, Any] = {}
        names = getattr(domain_coll, "get_object_names", None)
        try:
            domain_names = list(names()) if callable(names) else []
        except Exception:
            domain_names = []
        for domain_name in domain_names:
            boundary_map: dict[str, Any] = {}
            try:
                domain_obj = domain_coll[domain_name]
            except Exception:
                domain_obj = None
            boundary_coll = getattr(domain_obj, "boundary", None)
            bnames = getattr(boundary_coll, "get_object_names", None)
            try:
                boundary_names = list(bnames()) if callable(bnames) else []
            except Exception:
                boundary_names = []
            for boundary_name in boundary_names:
                boundary_map[boundary_name] = {}
            domain_map[domain_name] = {"boundary": boundary_map}
        if domain_map:
            analysis_data["domain"] = domain_map
    return flow_state


def _make_safe_import() -> Any:
    """Create an import function that only permits modules on the safe allow-list.

    Returns
    -------
    Any
        Value computed by the helper for the requested CFX workflow.
    """
    real_import = __import__

    def _safe_import(
        name: str,
        globals: dict[str, Any] | None = None,  # noqa: A002
        locals: dict[str, Any] | None = None,  # noqa: A002
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> Any:
        """Import an allowed module inside the restricted execution namespace.

        Parameters
        ----------
        name : str
            Name of the object, resource, or field to process.
        globals : dict[str, Any] | None, default: None
            Global namespace provided to a restricted import call.
        locals : dict[str, Any] | None, default: None
            Local namespace provided to a restricted import call.
        fromlist : tuple[str, ...], default: ``()``
            Names requested by a restricted from-import call.
        level : int, default: 0
            Relative import level requested by the import call.

        Returns
        -------
        Any
            Value computed by the helper for the requested CFX workflow.
        """
        if level != 0:
            raise ImportError(f"relative imports are not permitted: {name!r}")
        root_mod = name.split(".", 1)[0]
        if name not in _ALLOWED_IMPORTS and root_mod not in _ALLOWED_IMPORTS:
            raise ImportError(f"import of {name!r} is not permitted in run_code")
        return real_import(name, globals, locals, fromlist, level)

    return _safe_import


def _build_safe_builtins() -> dict[str, Any]:
    """Build the restricted set of builtins exposed to generated code.

    Returns
    -------
    dict[str, Any]
        Structured response payload for the requested operation.
    """
    import builtins as builtins_module

    safe: dict[str, Any] = {}
    for name in _ALLOWED_BUILTINS:
        if hasattr(builtins_module, name):
            safe[name] = getattr(builtins_module, name)
    safe["__import__"] = _make_safe_import()
    return safe


_CFX_API_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "path": "PreProcessing.from_install",
        "kind": "Constructor",
        "stage": "pre",
        "description": "Launch a local CFX-Pre session from the installed Ansys version.",
        "tokens": ("launch", "start", "pre", "cfx-pre", "preprocessing", "session"),
    },
    {
        "path": "connect_to_cfx",
        "kind": "Function",
        "stage": "pre/post",
        "description": (
            "Attach to an existing PyCFX-MCP instance by IP address, port, "
            "and password, or server-information file."
        ),
        "tokens": ("connect", "attach", "server", "sinfo", "ip", "port", "password"),
    },
    {
        "path": "pre.setup.flow",
        "kind": "NamedObject",
        "stage": "pre",
        "description": "CFX-Pre flow-analysis collection, usually indexed by 'Flow Analysis 1'.",
        "tokens": ("flow", "analysis", "setup", "domain", "pre"),
    },
    {
        "path": "flow.domain",
        "kind": "NamedObject",
        "stage": "pre",
        "description": "Domain collection under a flow analysis, usually indexed by domain name.",
        "tokens": ("domain", "fluid", "solid", "flow", "default"),
    },
    {
        "path": "domain.boundary",
        "kind": "NamedObject",
        "stage": "pre",
        "description": (
            "Boundary collection for inlet, outlet, wall, opening, symmetry, and interface setup."
        ),
        "tokens": ("boundary", "condition", "inlet", "outlet", "wall", "opening", "interface"),
    },
    {
        "path": "boundary.boundary_conditions.mass_and_momentum",
        "kind": "Object",
        "stage": "pre",
        "description": (
            "Mass and momentum boundary-condition branch for speed, pressure, and flow regime."
        ),
        "tokens": ("mass", "momentum", "velocity", "speed", "pressure", "flow", "regime"),
    },
    {
        "path": "boundary.boundary_conditions.heat_transfer",
        "kind": "Object",
        "stage": "pre",
        "description": (
            "Thermal boundary-condition branch for adiabatic, fixed "
            "temperature, and heat flux walls."
        ),
        "tokens": ("heat", "thermal", "temperature", "wall", "adiabatic", "flux", "energy"),
    },
    {
        "path": "domain.fluid_models.heat_transfer_model.option",
        "kind": "Parameter",
        "stage": "pre",
        "description": (
            "Select Thermal Energy, Total Energy, or related heat-transfer model on a CFX domain."
        ),
        "tokens": ("heat", "transfer", "thermal", "total", "energy", "temperature", "model"),
    },
    {
        "path": "domain.fluid_definition.<fluid-definition-key>.material",
        "kind": "Pattern",
        "stage": "pre",
        "description": (
            "Set a material on an existing fluid_definition entry "
            "discovered in the active CFX domain."
        ),
        "tokens": ("default", "domain", "fluid", "material", "water", "flow", "analysis"),
    },
    {
        "path": (
            "pre.setup.flow.Flow Analysis 1.domain.Default "
            "Domain.domain_models.reference_pressure.reference_pressure"
        ),
        "kind": "Parameter",
        "stage": "pre",
        "description": "Set reference pressure on Flow Analysis 1 / Default Domain.",
        "tokens": ("default", "domain", "reference", "pressure", "atm", "flow", "analysis"),
    },
    {
        "path": (
            "pre.setup.flow.Flow Analysis 1.domain.Default "
            "Domain.fluid_models.heat_transfer_model.option"
        ),
        "kind": "Parameter",
        "stage": "pre",
        "description": "Set the heat-transfer model on Flow Analysis 1 / Default Domain.",
        "tokens": ("default", "domain", "heat", "transfer", "thermal", "energy"),
    },
    {
        "path": (
            "pre.setup.flow.Flow Analysis 1.domain.Default "
            "Domain.fluid_models.turbulence_model.option"
        ),
        "kind": "Parameter",
        "stage": "pre",
        "description": "Set the turbulence model on Flow Analysis 1 / Default Domain.",
        "tokens": ("default", "domain", "turbulence", "model", "k epsilon", "k", "epsilon"),
    },
    {
        "path": "pre.file.import_mesh",
        "kind": "Command",
        "stage": "pre",
        "description": "Import a mesh file into CFX-Pre before creating domains and boundaries.",
        "tokens": ("import", "mesh", "load", "file", "pre"),
    },
    {
        "path": "pre.file.write_solver_input_file",
        "kind": "Command",
        "stage": "pre",
        "description": "Write a CFX Solver input .def file from the current CFX-Pre setup.",
        "tokens": ("write", "solver", "input", "def", "file", "export"),
    },
    {
        "path": "Solver.from_install",
        "kind": "Constructor",
        "stage": "solver",
        "description": "Launch CFX Solver from an input .def file.",
        "tokens": ("launch", "start", "solver", "solve", "run", "def"),
    },
    {
        "path": "solver.solution.start_run",
        "kind": "Command",
        "stage": "solver",
        "description": "Start the CFX Solver run.",
        "tokens": ("start", "run", "solve", "solver", "calculation"),
    },
    {
        "path": "solver.solution.wait_for_run",
        "kind": "Command",
        "stage": "solver",
        "description": "Block until the CFX Solver run completes.",
        "tokens": ("wait", "complete", "finish", "solver", "run"),
    },
    {
        "path": "solver.solution.get_results_file_name",
        "kind": "Command",
        "stage": "solver",
        "description": "Return the .res results file produced by a solver run.",
        "tokens": ("results", "res", "file", "solver", "output"),
    },
    {
        "path": "PostProcessing.from_install",
        "kind": "Constructor",
        "stage": "post",
        "description": "Launch CFD-Post against a .res results file.",
        "tokens": ("post", "cfd-post", "results", "res", "launch", "open"),
    },
    {
        "path": "post.results.contour",
        "kind": "NamedObject",
        "stage": "post",
        "description": (
            "CFD-Post contour collection for temperature, pressure, "
            "velocity, and other result plots."
        ),
        "tokens": ("contour", "plot", "temperature", "pressure", "velocity", "post"),
    },
)


_CFX_STATIC_ALLOWED_VALUES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        ".fluid_models.turbulence_model.option",
        ("k epsilon", "k omega", "SST", "laminar"),
    ),
    (
        ".fluid_models.heat_transfer_model.option",
        ("None", "Isothermal", "Thermal Energy", "Total Energy"),
    ),
    (
        ".boundary_conditions.flow_regime.option",
        ("Subsonic", "Supersonic"),
    ),
    (
        ".boundary_conditions.mass_and_momentum.option",
        (
            "Normal Speed",
            "Total Pressure",
            "Average Static Pressure",
            "Mass Flow Rate",
        ),
    ),
    (
        ".boundary_conditions.heat_transfer.option",
        ("Adiabatic", "Static Temperature", "Fixed Temperature", "Heat Flux"),
    ),
    (
        ".fluid_definition.*.option",
        ("Material Library", "User Material"),
    ),
)


_INDEXER_RE = re.compile(
    r"^(?P<name>[A-Za-z_][A-Za-z0-9_]*)\[(?P<quote>['\"])(?P<key>.+?)(?P=quote)\]$"
)


class CFXBackend(Backend):
    """Backend that manages CFX Pre, CFX-Solver, and CFD-Post sessions via PyCFX."""

    kind: str = "pycfx"
    label: str = "Ansys CFX (PyCFX)"

    def __init__(self) -> None:
        """Initialize this object with the dependencies required for later operations.

        Returns
        -------
        None
            No value is returned. Side effects are applied to the relevant cache, session, or
            server.
        """
        super().__init__()
        self._connected = False
        self._exec_ns: dict[str, Any] = self._build_initial_namespace()
        self._cache: dict[str, Any] = {}

    # ---- lifecycle -------------------------------------------------------

    async def connect(self, **kwargs: Any) -> ConnectResult:
        """Connect this backend to a CFX runtime or service.

        Parameters
        ----------
        kwargs : Any
            Keyword arguments forwarded to the wrapped callable.

        Returns
        -------
        ConnectResult
            Connection result describing the selected backend session.
        """
        mode = str(kwargs.get("mode") or "auto").strip().lower()
        if mode not in ("auto", "launch", "attach"):
            return ConnectResult(
                status="error",
                message=f"Invalid mode {mode!r}; expected 'auto', 'launch', or 'attach'.",
                error_code="connect_failed",
            )

        ip = kwargs.get("ip")
        port = kwargs.get("port")
        password = kwargs.get("password")
        server_info_file = kwargs.get("server_info_file") or kwargs.get("pre_sinfo")
        launcher = kwargs.get("launcher", "from_install")
        ui_mode = kwargs.get("ui_mode")
        product_version = kwargs.get("product_version")
        case_file_name = kwargs.get("case_file_name") or kwargs.get("project_file")
        start_timeout = int(kwargs.get("start_timeout", 60))
        additional_arguments = str(kwargs.get("additional_arguments", ""))
        container_dict = kwargs.get("container_dict")
        cleanup_on_exit = bool(kwargs.get("cleanup_on_exit", True))

        solver_input = kwargs.get("solver_input_file")

        post_sinfo = kwargs.get("post_sinfo") or kwargs.get("post_server_info_file")
        results_file = kwargs.get("results_file")

        has_attach_params = bool(ip or port or server_info_file or post_sinfo)
        if mode == "attach" and not has_attach_params:
            return ConnectResult(
                status="error",
                message=(
                    "mode='attach' requires attach parameters "
                    "(ip+port, server_info_file/pre_sinfo, or post_sinfo)."
                ),
                error_code="connect_failed",
            )
        if mode == "launch" and has_attach_params:
            return ConnectResult(
                status="error",
                message=(
                    "mode='launch' cannot be combined with attach parameters "
                    "(ip, port, server_info_file/pre_sinfo, post_sinfo); "
                    "omit them to launch a local session."
                ),
                error_code="connect_failed",
            )

        try:
            needs_pre = bool(
                ip
                or port
                or server_info_file
                or case_file_name
                or not (solver_input or post_sinfo or results_file)
            )
            # --- Pre ---
            if ip or port or server_info_file:
                SessionManager.attach_pre(
                    ip=ip,
                    port=port,
                    password=password,
                    server_info_file=server_info_file,
                )
            elif needs_pre:
                SessionManager.launch_pre(
                    launcher=launcher,
                    ui_mode=ui_mode,
                    product_version=product_version,
                    case_file_name=case_file_name,
                    start_timeout=start_timeout,
                    additional_arguments=additional_arguments,
                    container_dict=container_dict,
                    cleanup_on_exit=cleanup_on_exit,
                )

            # --- Solver (launch only) ---
            if solver_input:
                SessionManager.launch_solver(
                    solver_input,
                    product_version=product_version,
                    cleanup_on_exit=cleanup_on_exit,
                )

            # --- Post ---
            if post_sinfo:
                SessionManager.attach_post(server_info_file=post_sinfo)
            elif results_file:
                SessionManager.launch_post(
                    results_file,
                    ui_mode=ui_mode,
                    product_version=product_version,
                    cleanup_on_exit=cleanup_on_exit,
                )

            self._connected = True
            return ConnectResult(
                status="ok",
                backend_kind=self.kind,
                endpoint=f"{ip}:{port}" if ip else "local",
                message="CFX session(s) connected.",
            )
        except Exception as exc:
            return ConnectResult(
                status="error",
                message=str(exc),
                error_code="connect_failed",
            )

    async def disconnect(self) -> None:
        """Disconnect this backend from its active CFX runtime or service.

        Returns
        -------
        None
            No value is returned. Side effects are applied to the relevant cache, session, or
            server.
        """
        SessionManager.close_all()
        self._connected = False

    def is_connected(self) -> bool:
        """Check if the backend is currently connected.

        Returns
        -------
        bool
            Whether the backend currently has an active CFX connection.
        """
        return self._connected

    def status(self, leaf: str) -> SessionStatus:
        """Return a structured status summary for the active CFX backend or session manager.

        Parameters
        ----------
        leaf : str
            Leaf server or backend name associated with the status payload.

        Returns
        -------
        dict[str, Any]
            Structured status payload for the active backend or session manager.
        """
        mgr = SessionManager.status()
        notes = []
        if mgr.get("pre"):
            notes.append("Pre: active")
        if mgr.get("solver"):
            notes.append("Solver: active")
        if mgr.get("post"):
            notes.append("Post: active")
        if mgr.get("solver_input_file"):
            notes.append(f"DEF: {mgr['solver_input_file']}")
        if mgr.get("results_file"):
            notes.append(f"RES: {mgr['results_file']}")
        return SessionStatus(
            leaf=leaf,
            connected=self._connected,
            backend=self.label,
            backend_kind=self.kind,
            notes=notes,
        )

    async def find_api(
        self,
        query: str,
        *,
        top_k: int = 10,
        kinds: list[str] | None = None,
        under: str | None = None,
    ) -> list[dict[str, Any]]:
        """Find the API matching the request.

        Parameters
        ----------
        query : str
            Search query for ranking CFX API or object matches.
        top_k : int, default: 10
            Maximum number of matches to return.
        kinds : list[str] | None, default: None
            Optional result categories used to narrow the search.
        under : str | None, default: None
            Optional CFX path prefix used to scope the search.

        Returns
        -------
        list[dict[str, Any]]
            List of structured records matching the request.
        """
        query = (query or "").strip()
        if not query:
            return []
        top_k = max(1, min(int(top_k or 10), 20))
        kind_filter = {item.lower() for item in kinds or []}
        under_filter = under.strip().lower() if under else None
        tokens = self._api_search_tokens(query)
        scored: list[tuple[float, str, dict[str, Any]]] = []
        for index, entry in enumerate(_CFX_API_CATALOG):
            path = str(entry["path"])
            kind = str(entry["kind"])
            if kind_filter and kind.lower() not in kind_filter:
                continue
            if under_filter and not path.lower().startswith(under_filter):
                continue
            score = self._score_api_entry(tokens, entry)
            if score <= 0:
                continue
            result = {
                "path": path,
                "kind": kind,
                "stage": entry.get("stage"),
                "score": round(score, 4),
                "description": entry.get("description", ""),
                "source": "cfx_builtin_catalog",
            }
            scored.append((score, path, result | {"_index": index}))
        scored.sort(key=lambda item: (-item[0], item[1]))
        out: list[dict[str, Any]] = []
        for _, _, result in scored[:top_k]:
            result.pop("_index", None)
            out.append(result)
        return out

    async def get_allowed_values(self, paths: list[str]) -> dict[str, list[Any]]:
        """Get allowed values for a CFX path from a live state or schema metadata.

        Parameters
        ----------
        paths : list[str]
            Backend paths to inspect.

        Returns
        -------
        dict[str, Any]
            Structured allowed-values payload for the requested path.
        """
        result: dict[str, list[Any]] = {}
        for path in paths:
            values: list[Any] | None = None
            if self.is_connected():
                values = self._get_live_allowed_values(path)
            if not values:
                values = self._get_static_allowed_values(path)
            if values is not None:
                result[path] = values
        return result

    async def get_active_status(self, paths: list[str]) -> dict[str, bool]:
        """Return the active/inactive status for a CFX path or component.

        A path is considered *active* when both of these conditions are met:

        * The live PyCFX object resolves successfully.
        * The resolved node either has a state value (``get_state``
          returns truthy/non-empty/numeric) or is a child-bearing
          group whose ``keys()`` produce at least one entry.

        Inactive paths cover three cases:

        * The path cannot be resolved. (The schema matches but the CCL tree
          has no live node, such as ``domain.boundary[inlet].turbulence.epsilon``
          when ``turbulence.option != 'k-Epsilon'``).
        * The parent option is set such that this child is pruned.
          (It resolves but ``get_state()`` returns ``None``/empty.)
        * The path does not exist in the live tree at all.

        Parameters
        ----------
        paths : list[str]
            Backend paths to inspect.

        Returns
        -------
        dict[str, bool]
            ``{path: is_active}`` for every requested path. Paths that
            could not be resolved at all are reported ``False`` (not
            absent from the dictionary) so callers get a stable shape.
        """
        status: dict[str, bool] = {}
        for path in paths:
            try:
                node = self._resolve_live_path(path)
            except Exception:
                status[path] = False
                continue
            status[path] = self._node_is_active(node)
        return status

    @staticmethod
    def _node_is_active(node: Any) -> bool:
        """Return ``True`` when a live CFX node carries usable state.

        The check is intentionally permissive: a Group/NamedObject
        with no children but a resolvable handle is still considered
        active. (The user may be about to populate it.) Only nodes
        whose ``get_state`` returns ``None`` AND whose ``keys()``
        returns nothing are reported inactive. This combination is
        the signature of a pruned-by-option subtree.
        """
        if node is None:
            return False
        try:
            get_state = getattr(node, "get_state", None)
            if callable(get_state):
                state = get_state()
                if state not in (None, ""):
                    return True
        except Exception:  # nosec B110
            # Probe failures are non-fatal — fall through to the
            # children-based check below.
            pass
        try:
            keys = getattr(node, "keys", None)
            if callable(keys):
                if list(keys()):
                    return True
                # An empty named-object collection is still "active" —
                # the user can populate it. We return True for
                # consistency with `get_state` raising no exception.
                return True
        except Exception:
            return False
        # Plain attribute / value: existence implies activity.
        return True

    async def probe_path(self, paths: list[str]) -> dict[str, dict[str, Any]]:
        """Batch the pre-flight probe for one or more CFX paths.

        This callable combines the schema cache (``exists`` + ``kind``)
        with the live resolver (``is_active``) so the agent gets a single
        round-trip answer to these questions:

        - "Does this CFX path exist?"
        - "Is it active in the current case?"
        - "Can the user ``.create()`` under it?"
        - "What kind of node is it?"

        Parameters
        ----------
        paths : list[str]
            Backend paths to inspect.

        Returns
        -------
        dict[str, dict[str, Any]]
            ``{path: {exists, is_active, is_user_creatable, kind}}``.
            All four fields are always populated. ``kind`` is
            ``"unknown"`` when neither the schema nor live state can
            classify the path.
        """
        # Resolve the schema cache lazily — we tolerate the schema
        # being unavailable (offline build, missing config files,
        # ...) and fall back to live resolution alone.
        try:
            from ansys.cfx.mcp.cfx.schema_cache import get_schema_cache

            cache = get_schema_cache()
        except Exception:  # noqa: BLE001
            cache = None

        active_map: dict[str, bool] = {}
        if self.is_connected():
            try:
                active_map = await self.get_active_status(list(paths))
            except Exception:  # noqa: BLE001
                active_map = {}

        results: dict[str, dict[str, Any]] = {}
        for path in paths:
            schema_node = cache.get(path) if cache is not None else None
            exists_in_schema = schema_node is not None
            is_active = bool(active_map.get(path, False))
            # If the live tree confirmed the path, treat it as
            # existing even when the schema cache does not know
            # about it (schema is best-effort).
            exists = exists_in_schema or is_active
            kind = schema_node.kind if schema_node is not None else "unknown"
            # ``NamedObject`` and ``Group`` containers are the only
            # node kinds that accept ``.create()``.
            # Parameter/Query/Command leaves are not user-creatable.
            is_user_creatable = kind in {"NamedObject", "Group"}
            results[path] = {
                "exists": exists,
                "is_active": is_active,
                "is_user_creatable": is_user_creatable,
                "kind": kind,
            }
        return results

    async def get_help(self, path: str) -> dict[str, Any]:
        """Get help for the active CFX context.

        Parameters
        ----------
        path : str
            CFX API, object, schema, or file path to process.

        Returns
        -------
        dict[str, Any]
            Structured response payload for the requested operation.
        """
        query = (path or "").strip()
        if not query:
            return {"path": path, "error": "path must be a non-empty string"}

        catalog_entry = self._find_catalog_entry(query)
        live_info: dict[str, Any] = {}
        if self.is_connected():
            try:
                node = self._resolve_live_path(query)
                live_info = self._describe_live_node(node)
            except Exception as exc:
                live_info = {"resolves": False, "error": str(exc)}

        allowed = (await self.get_allowed_values([query])).get(query)
        if not allowed:
            allowed = (await self.get_allowed_values([f"{query}.option"])).get(f"{query}.option")
        result: dict[str, Any] = {
            "path": query,
            "source": "cfx_builtin_catalog",
            "resolves": bool(live_info.get("resolves", False)),
        }
        if catalog_entry is not None:
            result.update(
                {
                    "kind": catalog_entry.get("kind"),
                    "stage": catalog_entry.get("stage"),
                    "description": catalog_entry.get("description", ""),
                    "tokens": list(catalog_entry.get("tokens", ())),
                }
            )
        else:
            result.update(
                {
                    "kind": live_info.get("kind", "unknown"),
                    "description": "No exact CFX catalog entry was found for this path.",
                }
            )
            suggestions = await self.find_api(query, top_k=5)
            if suggestions:
                result["suggestions"] = suggestions
        if allowed:
            result["allowed_values"] = allowed
        result.update(live_info)
        return result

    async def get_targeted_context(
        self,
        *,
        paths_to_check: list[str],
        named_object_types: list[str] | None = None,
        instance_state_fetch: list[str] | None = None,
    ) -> dict[str, Any]:
        """Get a compact context slice for the requested CFX paths or objects.

        Parameters
        ----------
        paths_to_check : list[str]
            CFX paths to check against live state or schema metadata.
        named_object_types : list[str] | None, default: None
            Named-object categories to include in context output.
        instance_state_fetch : list[str] | None, default: None
            Optional callback used to fetch live instance state.

        Returns
        -------
        dict[str, Any]
            Structured response payload for the requested operation.
        """
        paths = list(paths_to_check or [])
        state_paths = list(instance_state_fetch or [])
        named_types = list(named_object_types or [])

        context: dict[str, Any] = {
            "active_status": await self.get_active_status(paths),
            "allowed_values": await self.get_allowed_values(paths),
            "state": {},
            "named_objects": {},
            "help": {},
        }
        if state_paths:
            try:
                context["state"] = await self.get_state(state_paths)
            except Exception as exc:
                fallback = await self._state_fallback_from_named_objects(state_paths)
                context["state"] = fallback or {"_error": str(exc)}
        try:
            named = await self.list_named_objects()
        except Exception as exc:
            context["named_objects"] = {"_error": str(exc)}
        else:
            if named_types:
                context["named_objects"] = {name: named.get(name, []) for name in named_types}
            else:
                context["named_objects"] = named
        for path in paths:
            context["help"][path] = await self.get_help(path)
        return context

    async def solver_status(self) -> dict[str, Any]:
        """Get the CFX-Solver run status from the active backend.

        Returns
        -------
        dict[str, Any]
            Structured response payload for the requested operation.
        """
        status = SessionManager.status()
        solver = SessionManager.get_solver()
        running: bool | None = None
        if solver is not None:
            try:
                running = bool(solver.is_running())
            except Exception:
                running = None
        return {
            "backend_kind": self.kind,
            "connected": self.is_connected(),
            "pre_connected": bool(status.get("pre")),
            "solver_connected": bool(status.get("solver")),
            "post_connected": bool(status.get("post")),
            "solver_running": running,
            "solver_input_file": status.get("solver_input_file"),
            "results_file": status.get("results_file"),
        }

    async def summarize_setup(self) -> dict[str, Any]:
        """Summarize the current CFX setup for humans and model prompts.

        Returns
        -------
        dict[str, Any]
            Structured response payload for the requested operation.
        """
        status = await self.solver_status()
        summary: dict[str, Any] = {
            "backend": self.label,
            "status": status,
            "named_objects": {},
            "state": {},
        }
        try:
            summary["named_objects"] = await self.list_named_objects()
        except Exception as exc:
            summary["named_objects"] = {"_error": str(exc)}
        if status.get("pre_connected"):
            try:
                summary["state"] = await self.get_state(["flow", "mesh", "user"])
            except Exception as exc:
                fallback = await self._state_fallback_from_named_objects(["flow", "mesh", "user"])
                summary["state"] = fallback or {"_error": str(exc)}
        else:
            summary["state"] = {"_note": "No active CFX-Pre session."}
        return summary

    async def cfx_workflow(
        self,
        *,
        action: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run a CFX lifecycle action through the backend workflow router.

        Parameters
        ----------
        action : str
            Component-management action to apply.
        params : dict[str, Any] | None, default: None
            Action-specific parameter mapping.

        Returns
        -------
        dict[str, Any]
            Structured response payload for the requested operation.
        """
        action_name = (action or "").strip().lower()
        payload = dict(params or {})
        if action_name in {"status", "session_status"}:
            return {"status": "ok", "action": action_name, "result": await self.solver_status()}
        if action_name == "start_pre":
            connect = await self.connect(**payload)
            return {"status": connect.status, "action": action_name, "result": connect.model_dump()}
        if action_name == "import_mesh":
            mesh_file = self._required_param(payload, "path", aliases=("mesh_file", "file"))
            pre = self._require_pre()
            pre.import_mesh(str(mesh_file))
            return {"status": "ok", "action": action_name, "mesh_file": str(mesh_file)}
        if action_name == "write_def":
            def_file = self._required_param(
                payload, "path", aliases=("def_file", "solver_input_file")
            )
            pre = self._require_pre()
            pre.write_solver_input(str(def_file))
            return {"status": "ok", "action": action_name, "solver_input_file": str(def_file)}
        if action_name == "start_solver":
            def_file = self._required_param(
                payload, "def_file", aliases=("path", "solver_input_file")
            )
            connect_params = dict(payload)
            for key in ("def_file", "path", "solver_input_file"):
                connect_params.pop(key, None)
            connect = await self.connect(solver_input_file=str(def_file), **connect_params)
            return {"status": connect.status, "action": action_name, "result": connect.model_dump()}
        if action_name == "wait_solver":
            solver = self._require_solver()
            interval = int(payload.get("interval", payload.get("poll_interval", 10)))
            timeout = int(payload.get("timeout", 86400))
            solver.wait_for_run(interval=interval, timeout=timeout)
            results_file = solver.get_results_file_name()
            if results_file:
                SessionManager.set_results_file(results_file)
            return {
                "status": "ok",
                "action": action_name,
                "results_file": results_file,
            }
        if action_name == "get_results_file":
            solver = SessionManager.get_solver()
            results_file = None
            if solver is not None:
                try:
                    results_file = solver.get_results_file_name()
                except Exception:
                    results_file = None
            results_file = results_file or SessionManager.get_results_file()
            return {"status": "ok", "action": action_name, "results_file": results_file}
        if action_name == "open_post":
            results_file = self._required_param(
                payload, "results_file", aliases=("path", "res_file")
            )
            connect_params = dict(payload)
            for key in ("results_file", "path", "res_file"):
                connect_params.pop(key, None)
            connect = await self.connect(results_file=str(results_file), **connect_params)
            return {"status": connect.status, "action": action_name, "result": connect.model_dump()}
        return {
            "status": "error",
            "action": action_name,
            "message": "Unknown CFX workflow action.",
            "allowed_actions": [
                "start_pre",
                "import_mesh",
                "write_def",
                "start_solver",
                "wait_solver",
                "get_results_file",
                "open_post",
                "status",
            ],
        }

    async def cfx_model_context(
        self,
        *,
        action: str = "summary",
        params: dict[str, Any] | None = None,
        max_items: int = 20,
    ) -> dict[str, Any]:
        """Return a compact CFX model-context response from the backend.

        Parameters
        ----------
        action : str, default: ``"summary"``
            Component-management action to apply.
        params : dict[str, Any] | None, default: None
            Action-specific parameter mapping.
        max_items : int, default: 20
            Maximum number of context items to include in the response.

        Returns
        -------
        dict[str, Any]
            Structured response payload for the requested operation.
        """
        action_name = (action or "summary").strip().lower()
        payload = dict(params or {})
        limit = max(1, min(int(max_items or 20), 100))
        if action_name == "summary":
            return cast(
                dict[str, Any],
                self._limit_context(await self.summarize_setup(), limit),
            )
        if action_name == "list_named_objects":
            return {
                "status": "ok",
                "action": action_name,
                "objects": self._limit_context(await self.list_named_objects(), limit),
            }
        if action_name == "find_named_object":
            name = self._required_param(payload, "name", aliases=("query",))
            return {
                "status": "ok",
                "action": action_name,
                "matches": await self.find_named_object(str(name)),
            }
        if action_name == "select_named_objects":
            names = payload.get("names", [])
            if isinstance(names, str):
                names = [names]
            return {
                "status": "ok",
                "action": action_name,
                "selected": await self.select_named_objects(names=list(names)),
            }
        if action_name == "state":
            paths = self._list_param(payload, "paths", default=["flow", "mesh", "user"])
            return {
                "status": "ok",
                "action": action_name,
                "state": self._limit_context(await self.get_state(paths), limit),
            }
        if action_name == "api_help":
            path = self._required_param(payload, "path", aliases=("query",))
            return {"status": "ok", "action": action_name, "help": await self.get_help(str(path))}
        if action_name == "find_api":
            query = self._required_param(payload, "query", aliases=("path",))
            kinds = payload.get("kinds") if isinstance(payload.get("kinds"), list) else None
            under = payload.get("under") if isinstance(payload.get("under"), str) else None
            return {
                "status": "ok",
                "action": action_name,
                "matches": await self.find_api(str(query), top_k=limit, kinds=kinds, under=under),
            }
        if action_name == "allowed_values":
            paths = self._list_param(payload, "paths", default=[])
            if not paths and payload.get("path"):
                paths = [str(payload["path"])]
            return {
                "status": "ok",
                "action": action_name,
                "allowed_values": await self.get_allowed_values(paths),
            }
        if action_name == "targeted_context":
            paths = self._list_param(payload, "paths_to_check", default=[])
            named_types = self._list_param(payload, "named_object_types", default=[])
            state_paths = self._list_param(payload, "instance_state_fetch", default=[])
            return {
                "status": "ok",
                "action": action_name,
                "context": self._limit_context(
                    await self.get_targeted_context(
                        paths_to_check=paths,
                        named_object_types=named_types,
                        instance_state_fetch=state_paths,
                    ),
                    limit,
                ),
            }
        return {
            "status": "error",
            "action": action_name,
            "message": "Unknown CFX model context action.",
            "allowed_actions": [
                "summary",
                "list_named_objects",
                "find_named_object",
                "select_named_objects",
                "state",
                "api_help",
                "find_api",
                "allowed_values",
                "targeted_context",
            ],
        }

    @staticmethod
    def _required_param(
        params: dict[str, Any],
        name: str,
        *,
        aliases: tuple[str, ...] = (),
    ) -> Any:
        """Read a required action parameter and raise a clear error when it is missing.

        Parameters
        ----------
        params : dict[str, Any]
            Action-specific parameter mapping.
        name : str
            Name of the object, resource, or field to process.
        aliases : tuple[str, ...], default: ``()``
            Alternative parameter names that may also satisfy the requirement.

        Returns
        -------
        Any
            Value computed by the helper for the requested CFX workflow.
        """
        for key in (name, *aliases):
            value = params.get(key)
            if value not in (None, ""):
                return value
        raise ValueError(f"Missing required parameter: {name}")

    @staticmethod
    def _list_param(
        params: dict[str, Any],
        name: str,
        *,
        default: list[str],
    ) -> list[str]:
        """Normalize an action parameter into a list of string values.

        Parameters
        ----------
        params : dict[str, Any]
            Action-specific parameter mapping.
        name : str
            Name of the object, resource, or field to process.
        default : list[str]
            Fallback value used when no explicit setting is present.

        Returns
        -------
        list[str]
            Value computed by the helper for the requested CFX workflow.
        """
        value = params.get(name, default)
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            return [str(item) for item in value]
        return list(default)

    @staticmethod
    def _limit_context(value: Any, limit: int) -> Any:
        """Limit context payload sizes so MCP responses remain compact.

        Parameters
        ----------
        value : Any
            Value to store in the target cache or data structure.
        limit : int
            Maximum number of records to return.

        Returns
        -------
        Any
            Value computed by the helper for the requested CFX workflow.
        """
        if isinstance(value, dict):
            limited: dict[str, Any] = {}
            for index, (key, item) in enumerate(value.items()):
                if index >= limit:
                    limited["_truncated"] = True
                    break
                limited[str(key)] = CFXBackend._limit_context(item, limit)
            return limited
        if isinstance(value, list):
            out = [CFXBackend._limit_context(item, limit) for item in value[:limit]]
            if len(value) > limit:
                out.append({"_truncated": True, "remaining": len(value) - limit})
            return out
        return value

    @staticmethod
    def _require_pre() -> Any:
        """Return the active CFX-Pre session or raise a not-connected error.

        Returns
        -------
        Any
            Value computed by the helper for the requested CFX workflow.
        """
        pre = SessionManager.get_pre()
        if pre is None:
            raise RuntimeError("No active CFX-Pre session.")
        return pre

    @staticmethod
    def _require_solver() -> Any:
        """Return the active CFX-Solver session or raise a not-connected error.

        Returns
        -------
        Any
            Value computed by the helper for the requested CFX workflow.
        """
        solver = SessionManager.get_solver()
        if solver is None:
            raise RuntimeError("No active CFX Solver session.")
        return solver

    def _get_live_allowed_values(self, path: str) -> list[Any] | None:
        """Get the allowed values reported by the live PyCFX object tree.

        Parameters
        ----------
        path : str
            CFX API, object, schema, or file path to process.

        Returns
        -------
        list[Any] | None
            Value computed by the helper for the requested CFX workflow.
        """
        try:
            node = self._resolve_live_path(path)
        except Exception:
            return None
        return self._coerce_allowed_values(node)

    async def _state_fallback_from_named_objects(self, paths: list[str]) -> dict[str, Any]:
        """Build a compact state fallback from currently known named CFX objects.

        Parameters
        ----------
        paths : list[str]
            Backend paths to inspect.

        Returns
        -------
        dict[str, Any]
            Structured response payload for the requested operation.
        """
        try:
            named = await self.list_named_objects()
        except Exception:
            return {}
        fallback: dict[str, Any] = {}
        for path in paths:
            if path in ("flow", "mesh", "user"):
                fallback[path] = named.get(path, [])
        return fallback

    @staticmethod
    def _find_catalog_entry(path: str) -> dict[str, Any] | None:
        """Find the best static API catalog entry for a requested CFX path.

        Parameters
        ----------
        path : str
            CFX API, object, schema, or file path to process.

        Returns
        -------
        dict[str, Any] | None
            Value computed by the helper for the requested CFX workflow.
        """
        normalized = path.strip().lower()
        for entry in _CFX_API_CATALOG:
            if str(entry.get("path", "")).lower() == normalized:
                return dict(entry)
        return None

    @staticmethod
    def _describe_live_node(node: Any) -> dict[str, Any]:
        """Describe a live PyCFX node using available metadata and attributes.

        Parameters
        ----------
        node : Any
            AST or PyCFX object node being inspected.

        Returns
        -------
        dict[str, Any]
            Structured response payload for the requested operation.
        """
        info: dict[str, Any] = {
            "resolves": True,
            "kind": type(node).__name__,
        }
        if isinstance(node, dict):
            info["child_names"] = sorted(str(key) for key in node.keys())
            return info
        keys = getattr(node, "keys", None)
        if callable(keys):
            try:
                info["child_names"] = sorted(str(key) for key in keys())
            except Exception as exc:
                _LOG.debug("Could not describe live CFX node children: %s", exc)
        get_state = getattr(node, "get_state", None)
        if callable(get_state):
            info["has_state"] = True
        return info

    def _resolve_live_path(self, path: str) -> Any:
        """Resolve a dotted CFX path to a live PyCFX object when possible.

        Parameters
        ----------
        path : str
            CFX API, object, schema, or file path to process.

        Returns
        -------
        Any
            Value computed by the helper for the requested CFX workflow.
        """
        segments = [segment for segment in path.split(".") if segment]
        if not segments:
            raise KeyError("empty CFX path")

        root_name = segments[0]
        if root_name in ("pre", "cfxpre"):
            session = SessionManager.get_pre()
        elif root_name in ("post", "cfxpost"):
            session = SessionManager.get_post()
        elif root_name in ("solver", "cfxsolver"):
            session = SessionManager.get_solver()
        else:
            session = SessionManager.get_pre()
            segments = ["setup", *segments]
        if session is None:
            raise KeyError(f"No active CFX session for {root_name!r}")

        current = session.raw
        start_index = (
            1
            if root_name
            in (
                "pre",
                "cfxpre",
                "post",
                "cfxpost",
                "solver",
                "cfxsolver",
            )
            else 0
        )
        for segment in segments[start_index:]:
            current = self._resolve_live_segment(current, segment)
        return current

    @staticmethod
    def _resolve_live_segment(current: Any, segment: str) -> Any:
        """Resolve one segment of a CFX path against the current live object.

        Parameters
        ----------
        current : Any
            Current live object while resolving a CFX path.
        segment : str
            Single path segment to resolve against the current object.

        Returns
        -------
        Any
            Value computed by the helper for the requested CFX workflow.
        """
        match = _INDEXER_RE.match(segment)
        if match is not None:
            collection = CFXBackend._resolve_live_segment(current, match.group("name"))
            return collection[match.group("key")]
        if isinstance(current, dict):
            return current[segment]
        try:
            return getattr(current, segment)
        except AttributeError:
            return current[segment]

    @staticmethod
    def _coerce_allowed_values(node: Any) -> list[Any] | None:
        """Normalize allowed-value metadata from a live PyCFX node.

        Parameters
        ----------
        node : Any
            AST or PyCFX object node being inspected.

        Returns
        -------
        list[Any] | None
            Value computed by the helper for the requested CFX workflow.
        """
        for attr_name in ("allowed_values", "get_allowed_values"):
            try:
                member = getattr(node, attr_name)
            except AttributeError:
                continue
            raw = member() if callable(member) else member
            values = CFXBackend._coerce_allowed_values_payload(raw)
            if values:
                return values
        if isinstance(node, dict):
            for key in ("allowed-values", "allowed_values", "values"):
                values = CFXBackend._coerce_allowed_values_payload(node.get(key))
                if values:
                    return values
        return None

    @staticmethod
    def _coerce_allowed_values_payload(raw: Any) -> list[Any] | None:
        """Normalize an arbitrary allowed-values payload into a list of strings.

        Parameters
        ----------
        raw : Any
            Raw payload returned by PyCFX or a provider API.

        Returns
        -------
        list[Any] | None
            Value computed by the helper for the requested CFX workflow.
        """
        if raw is None:
            return None
        if isinstance(raw, str):
            return [raw]
        if not isinstance(raw, (list, tuple, set)):
            return None
        values: list[Any] = []
        for item in raw:
            if isinstance(item, dict):
                for key in ("name", "value", "id", "key"):
                    value = item.get(key)
                    if value:
                        values.append(value)
                        break
            else:
                values.append(item)
        return values or None

    @staticmethod
    def _get_static_allowed_values(path: str) -> list[Any] | None:
        """Get the allowed values recorded in the static CFX schema cache.

        Parameters
        ----------
        path : str
            CFX API, object, schema, or file path to process.

        Returns
        -------
        list[Any] | None
            Value computed by the helper for the requested CFX workflow.
        """
        normalized = path.replace("['", ".").replace("']", "")
        normalized = normalized.replace('["', ".").replace('"]', "")
        for suffix, values in _CFX_STATIC_ALLOWED_VALUES:
            if "*" in suffix:
                pattern = re.escape(suffix).replace(r"\*", r"[^.]+") + r"$"
                if re.search(pattern, normalized):
                    return list(values)
            elif normalized.endswith(suffix):
                return list(values)
        return None

    @staticmethod
    def _api_search_tokens(query: str) -> set[str]:
        """Tokenize a CFX API search query for catalog scoring.

        Parameters
        ----------
        query : str
            Search query for ranking CFX API or object matches.

        Returns
        -------
        set[str]
            Value computed by the helper for the requested CFX workflow.
        """
        import re

        return {token for token in re.split(r"[^a-z0-9]+", query.lower()) if len(token) >= 2}

    @staticmethod
    def _score_api_entry(tokens: set[str], entry: dict[str, Any]) -> float:
        """Score a CFX API catalog entry against search tokens.

        Parameters
        ----------
        tokens : set[str]
            Search tokens produced from the query text.
        entry : dict[str, Any]
            Schema or API catalog entry to inspect.

        Returns
        -------
        float
            Floating-point score, timestamp, or metric for the requested operation.
        """
        path = str(entry["path"]).lower()
        haystack = set(entry.get("tokens", ()))
        haystack.update(CFXBackend._api_search_tokens(path))
        haystack.update(CFXBackend._api_search_tokens(str(entry.get("description", ""))))
        score = 0.0
        for token in tokens:
            if token in haystack:
                score += 4.0
            elif any(token in item or item in token for item in haystack):
                score += 1.0
        score -= 0.05 * path.count(".")
        return score

    # ---- prerequisites ---------------------------------------------------

    async def check_prerequisites(
        self,
        *,
        intent: str | None = None,
        recipe_name: str | None = None,
        params: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Check whether a CFX request has the sessions and files it needs.

        Parameters
        ----------
        intent : str | None, default: None
            User request text for inferring the required CFX action.
        recipe_name : str | None, default: None
            Name of the matched CFX recipe, when one is available.
        params : dict[str, Any] | None, default: None
            Action-specific parameter mapping.
        context : dict[str, Any] | None, default: None
            Additional context supplied by the caller.

        Returns
        -------
        dict[str, Any]
            Structured response payload for the requested operation.
        """
        return check_cfx_prerequisites(
            intent=intent,
            recipe_name=recipe_name,
            params=params,
            context=context,
            status=SessionManager.status(),
        )

    def _sanitize_cfx_python_code(
        self,
        code: str,
        *,
        context: dict[str, Any] | None = None,
    ) -> str:
        """Clean generated CFX Python code before validation and execution.

        Parameters
        ----------
        code : str
            Python source code submitted for validation, grounding, or execution.
        context : dict[str, Any] | None, default: None
            Additional context supplied by the caller.

        Returns
        -------
        str
            String value produced for the requested CFX or provider operation.
        """
        if not code or ".fluid_definition" not in code:
            return code
        fluid_definition_name = self._resolve_fluid_definition_key(context)
        if not fluid_definition_name:
            fluid_definition_name = self._infer_fluid_definition_key(code)
        if not fluid_definition_name:
            return code

        option_line_pattern = re.compile(
            r"^\s*.*\.fluid_definition\.(?P<key>[A-Za-z_][A-Za-z0-9_ ]*)"
            r"\.option\s*=\s*[\"']Material Library[\"']\s*$\n?",
            re.MULTILINE,
        )
        code = option_line_pattern.sub("", code)

        pattern = re.compile(
            r"\.fluid_definition\.(?P<key>[A-Za-z_][A-Za-z0-9_ ]*)"
            r"\.(?P<leaf>material|option)"
        )

        def repl(match: re.Match[str]) -> str:
            """Rewrite helper references in generated code for the active execution namespace.

            Parameters
            ----------
            match : re.Match[str]
                Regular-expression match describing the text to replace.

            Returns
            -------
            str
                String value produced for the requested CFX or provider operation.
            """
            candidate = match.group("key").strip()
            leaf = match.group("leaf")
            if candidate == fluid_definition_name:
                return f'.fluid_definition["{fluid_definition_name}"].{leaf}'
            if candidate.lower() in {"water", "air", "oil", "steam"}:
                return f'.fluid_definition["{fluid_definition_name}"].{leaf}'
            return match.group(0)

        return pattern.sub(repl, code)

    def _infer_fluid_definition_key(self, code: str) -> str | None:
        """Infer the intended fluid-definition key from generated CFX setup code.

        Parameters
        ----------
        code : str
            Python source code submitted for validation, grounding, or execution.

        Returns
        -------
        str | None
            Value computed by the helper for the requested CFX workflow.
        """
        if ".fluid_definition.Water." not in code:
            return None
        has_default_flow = (
            'flow["Flow Analysis 1"]' in code
            or "flow['Flow Analysis 1']" in code
            or "flow.Flow Analysis 1" in code
        )
        has_default_domain = (
            'domain["Default Domain"]' in code
            or "domain['Default Domain']" in code
            or "domain.Default Domain" in code
        )
        if has_default_flow and has_default_domain:
            return "Water"
        return None

    def _ensure_fluid_definition_option_line(
        self,
        code: str,
        *,
        fluid_definition_name: str,
    ) -> str:
        """Ensure the generated CFX code assigns a fluid-definition option when needed.

        Parameters
        ----------
        code : str
            Python source code submitted for validation, grounding, or execution.
        fluid_definition_name : str
            Fluid definition name detected or required by generated CFX code.

        Returns
        -------
        str
            String value produced for the requested CFX or provider operation.
        """
        material_pattern = re.compile(
            r"^(?P<prefix>\s*(?P<target>.+?\.fluid_definition\[\""
            + re.escape(fluid_definition_name)
            + r"""\"\])\.material\s*=\s*["'](?P<material>[^"']+)["'].*)$""",
            re.MULTILINE,
        )
        option_line_by_target: set[str] = set()
        option_pattern = re.compile(
            r"(?P<target>.+?\.fluid_definition\[\""
            + re.escape(fluid_definition_name)
            + r"""\"\])\.option\s*=\s*["']Material Library["']"""
        )
        for match in option_pattern.finditer(code):
            option_line_by_target.add(match.group("target").strip())

        lines: list[str] = []
        last_position = 0
        for match in material_pattern.finditer(code):
            lines.append(code[last_position : match.start()])
            target = match.group("target")
            normalized_target = target.strip()
            indent_match = re.match(r"\s*", match.group("prefix"))
            indent = indent_match.group(0) if indent_match else ""
            if normalized_target not in option_line_by_target:
                lines.append(f'{indent}{target}.option = "Material Library"\n')
                option_line_by_target.add(normalized_target)
            lines.append(match.group(0))
            last_position = match.end()
        lines.append(code[last_position:])
        return "".join(lines)

    def _resolve_fluid_definition_key(
        self,
        context: dict[str, Any] | None = None,
    ) -> str | None:
        """Resolve the fluid-definition key that the generated CFX code should use.

        Parameters
        ----------
        context : dict[str, Any] | None, default: None
            Additional context supplied by the caller.

        Returns
        -------
        str | None
            Value computed by the helper for the requested CFX workflow.
        """
        context = context or {}
        key = context.get("fluid_name") or context.get("fluid_definition")
        if isinstance(key, str) and key.strip():
            return key.strip()

        flow_name = context.get("flow_name")
        domain_name = context.get("domain_name")
        try:
            pre = SessionManager.get_pre()
            flow_state = pre.raw.setup.flow.get_state() if pre else None
        except Exception:
            return None
        if not isinstance(flow_state, dict):
            return None
        flows = [flow_name] if isinstance(flow_name, str) else list(flow_state)
        discovered: list[str] = []
        for flow in flows:
            flow_data = flow_state.get(flow)
            domains = flow_data.get("domain") if isinstance(flow_data, dict) else None
            if not isinstance(domains, dict):
                continue
            domain_names = [domain_name] if isinstance(domain_name, str) else list(domains)
            for domain in domain_names:
                domain_data = domains.get(domain)
                fluid_definitions = (
                    domain_data.get("fluid_definition") if isinstance(domain_data, dict) else None
                )
                if isinstance(fluid_definitions, dict):
                    discovered.extend(str(name) for name in fluid_definitions)
        unique = sorted(set(discovered))
        return unique[0] if len(unique) == 1 else None

    # ---- run_code --------------------------------------------------------

    def _build_initial_namespace(self) -> dict[str, Any]:
        """Build the initial restricted namespace for executing generated CFX Python code.

        Returns
        -------
        dict[str, Any]
            Structured response payload for the requested operation.
        """

        def get_cfx_pre():
            """Get the active raw CFX-Pre object for generated code execution.

            Returns
            -------
            Any
                Requested CFX data or metadata for the active session.
            """
            pre = SessionManager.get_pre()
            return pre.raw if pre else None

        def get_cfx_solver():
            """Get the active raw CFX-Solver object for generated code execution.

            Returns
            -------
            Any
                Requested CFX data or metadata for the active session.
            """
            solver = SessionManager.get_solver()
            return solver.raw if solver else None

        def get_cfx_post():
            """Get the active raw CFD-Post object for generated code execution.

            Returns
            -------
            Any
                Requested CFX data or metadata for the active session.
            """
            post = SessionManager.get_post()
            return post.raw if post else None

        ns: dict[str, Any] = {
            "session_manager": SessionManager,
            "launch_pre": SessionManager.launch_pre,
            "attach_pre": SessionManager.attach_pre,
            "launch_solver": SessionManager.launch_solver,
            "launch_post": SessionManager.launch_post,
            "attach_post": SessionManager.attach_post,
            # Helper accessors for current sessions
            "get_cfx_pre": get_cfx_pre,
            "get_cfx_solver": get_cfx_solver,
            "get_cfx_post": get_cfx_post,
        }
        return ns

    def _ensure_namespace_helpers(self, namespace: dict[str, Any]) -> None:
        """Add helper accessors for active CFX sessions to an execution namespace.

        Parameters
        ----------
        namespace : dict[str, Any]
            Execution namespace containing safe builtins and active CFX objects.

        Returns
        -------
        None
            No value is returned. Side effects are applied to the relevant cache, session, or
            server.
        """
        for name, value in self._build_initial_namespace().items():
            namespace.setdefault(name, value)

    def _sync_session_refs(self, namespace: dict[str, Any] | None = None) -> None:
        """Synchronize namespace references with the currently active CFX sessions.

        Parameters
        ----------
        namespace : dict[str, Any] | None, default: None
            Execution namespace containing safe builtins and active CFX objects.

        Returns
        -------
        None
            No value is returned. Side effects are applied to the relevant cache, session, or
            server.
        """
        ns = namespace if namespace is not None else self._exec_ns
        pre = SessionManager.get_pre()
        raw_pre = pre.raw if pre else None
        ns["pre"] = raw_pre
        ns["cfxpre"] = raw_pre
        ns["pypre"] = raw_pre

        solver = SessionManager.get_solver()
        raw_solver = solver.raw if solver else None
        ns["solver"] = raw_solver
        ns["cfxsolver"] = raw_solver

        post = SessionManager.get_post()
        raw_post = post.raw if post else None
        ns["post"] = raw_post
        ns["cfxpost"] = raw_post
        ns["session"] = raw_pre or raw_solver or raw_post

    async def validate_code(self, code: str) -> RunCodeResult:
        """Validate generated CFX code without executing it.

        This callable wraps the :func:`validate_python_source` function with ``strict=True`` so
        the AST import allow-list and top-level name allow-list are
        enforced. Otherwise, the validator only catches the
        ``_FORBIDDEN_CALLS`` set, missing imports of
        ``os``, ``subprocess``, or hand-rolled helpers.

        On top of the sandbox check, the validator extracts every
        ``solver.<path>``/``pre.<path>``/``post.<path>``/``session.<path>``
        attribute chain and compares it against
        the indexed :class:`CFXSchemaCache`. Paths that the schema
        cache does not know about, and whose leaf has no
        near-match, are promoted from silent warnings to
        ``unknown_cfx_path`` errors because such tokens almost
        always signal an unsupported API call.
        """
        if not code or not code.strip():
            return RunCodeResult(
                status="error",
                error_code="invalid_arguments",
                message="code must be a non-empty string",
            )

        # Strict AST pass — catches imports / Name lookups / forbidden
        # calls. The agent's own ``run_code`` already runs this exact
        # check before executing, so a clean ``validate_code`` is a
        # strong predictor that ``run_code`` will succeed.
        sandbox_extra = tuple(self._exec_ns.keys()) if self._exec_ns else ()
        sandbox = validate_python_source(
            code,
            strict=True,
            extra_allowed_names=sandbox_extra,
        )
        if sandbox.status == "error":
            return sandbox

        # Best-effort semantic check against the bundled CFX schema.
        schema_error = self._check_cfx_schema_paths(code)
        if schema_error is not None:
            return schema_error
        warnings = self._cfx_schema_warnings(code)
        return RunCodeResult(
            status="ok",
            message="parse_ok",
            warnings=warnings,
        )

    def _cfx_schema_findings(self, code: str) -> tuple[list[str], list[str]]:
        """Return schema warnings and hallucinated paths.

        CFX attribute chains in ``code`` are checked against the schema
        cache. Best-effort: Missing cache/parse errors yield empties.
        """
        warnings: list[str] = []
        hallucinated: list[str] = []
        try:
            from ansys.cfx.mcp.cfx.schema_cache import get_schema_cache

            cache = get_schema_cache()
        except Exception:  # noqa: BLE001
            cache = None
        if cache is None:
            return warnings, hallucinated
        try:
            tree = ast.parse(code)
            paths = self._extract_cfx_paths(tree)
        except Exception:  # noqa: BLE001
            paths = []
        for path in sorted(set(paths)):
            schema_path = self._normalise_cfx_path_for_schema(path)
            if cache.exists(schema_path):
                continue
            near = cache.suggest(schema_path, limit=3)
            if near:
                hint = ", ".join(near[:2])
                warnings.append(f"unknown CFX path '{path}'; did you mean: {hint}")
            else:
                hallucinated.append(path)
        return warnings, hallucinated

    def _cfx_schema_warnings(self, code: str) -> list[str]:
        warnings, _ = self._cfx_schema_findings(code)
        return warnings

    def _check_cfx_schema_paths(self, code: str) -> "RunCodeResult | None":
        """Return an ``unknown_cfx_path`` error for unresolved paths.

        Returns CFX paths the schema cache cannot resolve and has no near-match
        for, else returns ``None``. When strict validation is enabled
        (``CFX_MCP_STRICT_VALIDATION``), near-matches also become errors.
        This is shared by ``validate_code`` and ``run_code`` so mutating
        execution gets the same hallucination guard as the dry run.
        """
        warnings, hallucinated = self._cfx_schema_findings(code)
        if _strict_validation_enabled() and warnings:
            # Promote near-match warnings to blocking in strict mode.
            hallucinated = list(hallucinated) + [w.split("'")[1] for w in warnings if "'" in w]
            warnings = []
        if hallucinated:
            return RunCodeResult(
                status="error",
                error_code="unknown_cfx_path",
                message=(
                    "Rejected the snippet: the following CFX path(s) were "
                    "not found in the bundled CFX schema cache and have no "
                    f"near-match: {hallucinated}. These are almost "
                    "certainly hallucinated. Use ``find_api`` / "
                    "``probe_path`` to discover the real path first."
                ),
                warnings=warnings,
            )
        return None

    @staticmethod
    def _extract_cfx_paths(tree: ast.AST) -> list[str]:
        """Extract ``<session>.<path>...`` attribute chains from an AST.

        Walks attribute/subscript nodes in postorder and stitches
        the longest dotted chain rooted in one of the CFX session
        names. Subscript indexes are coerced into the canonical
        ``["<name>"]`` form so the result aligns with how
        ``CFXSchemaCache`` indexes NamedObject collections.

        Returns the list of distinct chains (no de-dup; caller
        does ``sorted(set(...))``).
        """
        roots = {"solver", "pre", "post", "session", "cfxpre", "cfxpost", "cfxsolver"}
        chains: list[str] = []

        def render(node: ast.AST) -> str | None:
            if isinstance(node, ast.Name):
                return node.id if node.id in roots else None
            if isinstance(node, ast.Attribute):
                parent = render(node.value)
                if parent is None:
                    return None
                return f"{parent}.{node.attr}"
            if isinstance(node, ast.Subscript):
                parent = render(node.value)
                if parent is None:
                    return None
                key = "<name>"
                # ast.Index in py<3.9 and Constant in py>=3.9
                idx = getattr(node, "slice", None)
                if isinstance(idx, ast.Constant) and isinstance(idx.value, str):
                    key = idx.value
                return f'{parent}["{key}"]'
            return None

        for node in ast.walk(tree):
            if isinstance(node, (ast.Attribute, ast.Subscript)):
                chain = render(node)
                if chain and "." in chain:
                    # Skip the chain itself if its parent attribute
                    # is also accessed — we only want the leaf
                    # access.  This is a heuristic, not exact.
                    chains.append(chain)
        return chains

    @staticmethod
    def _normalise_cfx_path_for_schema(path: str) -> str:
        """Strip the session-root prefix and normalize subscripts.

        Examples
        --------
        ``solver.setup.flow["main"].domain["fluid"].fluid_models`` →
            ``setup.flow["<name>"].domain["<name>"].fluid_models``
        ``pre.setup.flow.domain`` → ``setup.flow.domain``
        """
        roots = ("solver.", "pre.", "post.", "session.", "cfxpre.", "cfxpost.", "cfxsolver.")
        for prefix in roots:
            if path.startswith(prefix):
                path = path[len(prefix) :]
                break
        # Replace any bracket key with the canonical placeholder so
        # the schema cache (which indexes ``["<name>"]`` placeholders)
        # can find a match.
        out = []
        depth = 0
        for ch in path:
            if ch == "[":
                if depth == 0:
                    out.append('["<name>"]')
                depth += 1
            elif ch == "]":
                depth -= 1
            elif depth == 0:
                out.append(ch)
        return "".join(out)

    async def run_code(self, code: str, **kwargs: Any) -> RunCodeResult:
        """Run Python code against the active CFX backend namespace.

        Parameters
        ----------
        code : str
            Python source code submitted for validation, grounding, or execution.
        kwargs : Any
            Keyword arguments forwarded to the wrapped callable.

        Returns
        -------
        RunCodeResult
            Execution or validation result returned to the MCP caller.
        """
        if not code or not code.strip():
            return RunCodeResult(
                status="error",
                error_code="invalid_arguments",
                message="code must be a non-empty string",
            )

        namespace = kwargs.get("namespace")
        exec_ns = namespace if isinstance(namespace, dict) else self._exec_ns
        self._ensure_namespace_helpers(exec_ns)
        self._sync_session_refs(exec_ns)
        code = self._sanitize_cfx_python_code(code)

        check = validate_python_source(
            code,
            strict=True,
            extra_allowed_names=tuple(exec_ns.keys()),
        )
        if check.status == "error":
            return check

        # Schema-path hallucination guard (Phase 1a). ``run_code``
        # MUTATES the live CFX case, so it must apply the same
        # ``unknown_cfx_path`` rejection that ``validate_code`` does —
        # otherwise a hallucinated path silently executes against the
        # live solver. Mirrors ``validate_code``'s schema pass.
        schema_error = self._check_cfx_schema_paths(code)
        if schema_error is not None:
            return schema_error

        exec_ns["__builtins__"] = _build_safe_builtins()

        old_stdout = sys.stdout
        captured = sys.stdout = StringIO()
        try:
            tree = ast.parse(code, filename="<cfx-run-code>", mode="exec")
            last_expr_node: ast.Expression | None = None
            body = list(tree.body)
            if body and isinstance(body[-1], ast.Expr):
                last_stmt = body.pop()
                if not isinstance(last_stmt, ast.Expr):
                    raise TypeError("Expected final AST statement to be an expression.")
                last_expr_node = ast.Expression(body=last_stmt.value)
                ast.copy_location(last_expr_node, last_stmt)
                ast.fix_missing_locations(last_expr_node)

            if body:
                exec_tree = ast.Module(body=body, type_ignores=[])
                ast.fix_missing_locations(exec_tree)
                exec(  # nosec B102
                    compile(exec_tree, "<cfx-run-code>", "exec"),
                    exec_ns,
                    exec_ns,
                )
            auto_value: Any = None
            if last_expr_node is not None:
                auto_value = eval(  # nosec B307
                    compile(last_expr_node, "<cfx-run-code>", "eval"),
                    exec_ns,
                    exec_ns,
                )
                if auto_value is not None:
                    print(repr(auto_value))
            stdout = captured.getvalue()
            self._sync_session_refs(exec_ns)
            ret = exec_ns.pop("__return__", None)
            return RunCodeResult(
                status="ok",
                stdout=stdout,
                return_value=ret if ret is not None else auto_value,
            )
        except Exception as exc:
            return RunCodeResult(status="error", stderr=str(exc), error_code="exec_error")
        finally:
            sys.stdout = old_stdout

    def invalidate_live_caches(self) -> None:
        """Clear live CFX session caches after model or session state changes.

        Returns
        -------
        None
            No value is returned. Side effects are applied to the relevant cache, session, or
            server.
        """
        self._cache.clear()

    # ---- named objects ---------------------------------------------------

    async def list_named_objects(self) -> dict[str, Any]:
        """List named objects available in the active context.

        Returns
        -------
        dict[str, Any]
            Structured response payload for the requested operation.
        """
        pre = SessionManager.get_pre()
        if not pre:
            from ansys.cfx.mcp.common.errors import BackendUnavailable

            raise BackendUnavailable("No active CFX-Pre session.")
        try:
            objects: dict[str, Any] = {
                "flow": list(pre.raw.setup.flow.keys()),
                "mesh": list(pre.raw.setup.mesh.keys()),
                "user": list(pre.raw.setup.user.keys()),
            }
        except Exception:
            return {}

        # Surface nested domains/boundaries. Use get_state() rather than
        # live container .keys() at each nested level so a partially
        # populated tree degrades gracefully instead of raising.
        try:
            flow_state = pre.raw.setup.flow.get_state()
        except Exception:
            flow_state = None
        domains, boundaries = _collect_domains_and_boundaries(flow_state)
        # ``get_state()`` does not always include nested named-object
        # collections after a case is read in from a ``.cfx``/``.def``/
        # ``.res`` file. When it reports no domains, walk the live tree
        # directly so a fully-defined case (e.g. StaticMixer.cfx with its
        # "Default Domain") is not incorrectly reported as having no domains.
        if not domains:
            try:
                live_domains, live_boundaries = _walk_live_domains_and_boundaries(
                    pre.raw.setup.flow
                )
            except Exception:
                live_domains, live_boundaries = [], []
            if live_domains:
                domains = live_domains
            if live_boundaries:
                boundaries = live_boundaries
        if domains:
            objects["domain"] = domains
        if boundaries:
            objects["boundary"] = boundaries
        return objects

    async def get_state(self, paths: list[str] | None = None) -> dict[str, Any]:
        """Get the state for the active CFX context.

        Parameters
        ----------
        paths : list[str] | None, default: None
            Backend paths to inspect.

        Returns
        -------
        dict[str, Any]
            Structured response payload for the requested operation.
        """
        object_types = paths if paths else ["flow", "mesh", "user"]
        pre = SessionManager.get_pre()
        result: dict[str, Any] = {}
        for obj_type in object_types:
            if obj_type not in ("flow", "mesh", "user"):
                result[obj_type] = {"error": f"Unknown object type: {obj_type}"}
            elif pre is None:
                result[obj_type] = {"error": "No active CFX-Pre session."}
            elif obj_type == "flow":
                flow_state = pre.raw.setup.flow.get_state()
                result[obj_type] = _augment_flow_state_with_live_tree(
                    flow_state, pre.raw.setup.flow
                )
            elif obj_type == "mesh":
                result[obj_type] = pre.raw.setup.mesh.get_state()
            elif obj_type == "user":
                result[obj_type] = pre.raw.setup.user.get_state()
        return result
