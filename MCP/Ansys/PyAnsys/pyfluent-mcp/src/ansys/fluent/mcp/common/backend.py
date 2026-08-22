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

"""Backend abstraction.

Every leaf has one or more backends. A backend is the thing that actually
talks to a Fluids product (Fluent solver, Fluent meshing, Discovery, Prime,
or the Fluids One service). Tools are MCP-client-facing; backends are
implementation-facing.

A backend implements only the operations its product supports. Unsupported
operations raise `BackendUnavailableError` so the typed-error guard converts them
to a clean error code instead of a 500.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import time
from typing import Any, Optional

from ansys.fluent.mcp.common.errors import BackendUnavailableError
from ansys.fluent.mcp.common.models import (
    ConnectResult,
    RunCodeResult,
    SessionStatus,
)


class Backend(ABC):
    """Common interface for all backends.

    Concrete subclasses override only the methods their product supports.
    Default implementations raise `BackendUnavailableError`.
    """

    #: Short identifier surfaced to MCP clients (e.g. "fluids_one", "pyfluent").
    kind: str = "unknown"
    #: Human-readable name surfaced in `session.status`.
    label: str = "Unknown backend"

    #: Substrings matched against ``run_code`` snippets by
    #: :meth:`maybe_invalidate_mesh_cache`. Subclasses may extend.
    MESH_MUTATION_MARKERS: tuple[str, ...] = (
        "file.read_case",
        "file.read_mesh",
        "file.read_case_data",
        "file.replace_mesh",
        "mesh.replace",
        "mesh.modify_zones.append_mesh",
        "mesh.modify_zones.remesh",
        "mesh.adapt.",
        "mesh.repair_improve.",
        "solution.run_calculation.mesh_motion",
    )

    def __init__(self) -> None:
        """Initialize the Backend instance.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        self._cache: dict[str, tuple[float, Any]] = {}
        self._mesh_cache: dict[str, tuple[float, Any]] = {}

    # ---- lifecycle ----------------------------------------------------

    @abstractmethod
    async def connect(self, **kwargs: Any) -> ConnectResult:
        """Connect to the configured backend or service.

        Parameters
        ----------
        kwargs : Any
            Keyword arguments forwarded to the callable.

        Returns
        -------
        ConnectResult
            ConnectResult produced by the operation.
        """
        ...

    async def disconnect(self) -> None:
        """Override if the backend holds a persistent resource.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        return None

    @abstractmethod
    def is_connected(self) -> bool:
        """Return whether connected.

        Returns
        -------
        bool
            Boolean result of the operation.
        """
        ...

    def status(self, leaf: str) -> SessionStatus:
        """Return backend status information.

        Parameters
        ----------
        leaf : str
            Leaf MCP server instance under test.

        Returns
        -------
        SessionStatus
            SessionStatus produced by the operation.
        """
        return SessionStatus(
            leaf=leaf,
            connected=self.is_connected(),
            backend=self.label,
            backend_kind=self.kind,  # type: ignore[arg-type]
            endpoint=getattr(self, "endpoint", None),
        )

    # ---- live model context ------------------------------------------

    async def list_named_objects(self) -> dict[str, Any]:
        """List named objects entries.

        Returns
        -------
        dict[str, Any]
            Mapping containing the operation result.
        """
        raise BackendUnavailableError(f"{self.label} does not expose named objects.")

    async def get_named_object_names(self, collection_path: str) -> list[str]:
        """Return the instance names for a single named-object collection.

        Default implementation calls :meth:`list_named_objects` and
        filters. Backends with a direct ``get_object_names()`` accessor
        (e.g. PyFluent) should override this for a cheaper single-node
        round-trip.

        Parameters
        ----------
        collection_path : str
            Path to the named-object collection.

        Returns
        -------
        list[str]
            Collection containing the operation results.
        """
        try:
            mapping = await self.list_named_objects()
        except BackendUnavailableError:
            return []
        names = mapping.get(collection_path) or []
        return [str(n) for n in names]

    async def find_named_object(self, name: str) -> list[dict[str, Any]]:
        """Resolve a symbolic name across every named-object collection.

        Accepts:

        * Literal identifiers (``"inlet-1"``) — exact and substring
          matches are returned, exact first.
        * Glob patterns (``"wall-*"``, ``"*bar*|*tabzone*"``) — every
          live name matching the pattern is returned with
          ``"exact": True`` (the pattern itself stands in for an exact
          intent against the matched key) and an ``"is_pattern": True``
          flag on each entry plus a top-level ``pattern_source``
          payload so callers know the source query was a pattern.

        Default implementation calls :meth:`list_named_objects` and
        filters; backends with a faster index may override.

        Parameters
        ----------
        name : str
            Name of the object, module, or setting being processed.

        Returns
        -------
        list[dict[str, Any]]
            Mapping containing the operation result.
        """
        if not name or not name.strip():
            return []
        target = name.strip()
        try:
            mapping = await self.list_named_objects()
        except BackendUnavailableError:
            return []

        from ansys.fluent.mcp.solve.lib.pattern import expand_pattern, is_pattern

        if is_pattern(target):
            results: list[dict[str, Any]] = []
            for coll_path, names in (mapping or {}).items():
                live_names = [str(n) for n in (names or [])]
                for match in expand_pattern(target, live_names):
                    results.append(
                        {
                            "collection_path": coll_path,
                            "name": match,
                            "exact": True,
                            "is_pattern": True,
                            "pattern_source": target,
                        }
                    )
            return results

        target_lc = target.lower()
        exact: list[dict[str, Any]] = []
        partial: list[dict[str, Any]] = []
        for coll_path, names in (mapping or {}).items():
            for n in names or []:
                ns = str(n)
                if ns == target:
                    exact.append({"collection_path": coll_path, "name": ns, "exact": True})
                elif target_lc == ns.lower() or target_lc in ns.lower() or ns.lower() in target_lc:
                    partial.append({"collection_path": coll_path, "name": ns, "exact": False})
        return exact + partial

    async def get_state(self, paths: list[str] | None = None) -> dict[str, Any]:
        """Return the state.

        Parameters
        ----------
        paths : list[str] | None
            Fluent object paths supplied to the operation.

        Returns
        -------
        dict[str, Any]
            Mapping containing the operation result.
        """
        raise BackendUnavailableError(f"{self.label} does not expose state.")

    async def get_active_status(self, paths: list[str]) -> dict[str, bool]:
        """Return the active status.

        Parameters
        ----------
        paths : list[str]
            Fluent object paths supplied to the operation.

        Returns
        -------
        dict[str, bool]
            Mapping containing the operation result.
        """
        raise BackendUnavailableError(f"{self.label} does not expose active status.")

    async def get_allowed_values(self, paths: list[str]) -> dict[str, list[Any]]:
        """Return the allowed values.

        Parameters
        ----------
        paths : list[str]
            Fluent object paths supplied to the operation.

        Returns
        -------
        dict[str, list[Any]]
            Mapping containing the operation result.
        """
        raise BackendUnavailableError(f"{self.label} does not expose allowed values.")

    async def get_node_attrs(
        self,
        paths: list[str],
        attrs: list[str],
    ) -> dict[str, dict[str, Any]]:
        """Batched per-node settings-attribute fetch.

        Returns ``{path: {attr: value}}``. Backends with a live solver
        session should override; the default raises
        :class:`BackendUnavailableError` so callers can fall back to the
        per-attr accessors (``get_active_status``,
        ``get_allowed_values``).

        Parameters
        ----------
        paths : list[str]
            Fluent object paths supplied to the operation.
        attrs : list[str]
            Attribute names requested from the backend object.

        Returns
        -------
        dict[str, dict[str, Any]]
            Mapping containing the operation result.
        """
        raise BackendUnavailableError(f"{self.label} does not expose node attrs.")

    async def get_node_attrs_bulk(
        self,
        parent_path: str,
        attrs: list[str],
    ) -> dict[str, dict[str, Any]]:
        """Recursively fetch attributes for all children of ``parent_path``.

        Calls ``node.get_attrs(attrs, recursive=True)`` in a single Scheme
        RPC, replacing N per-field round-trips when the caller needs metadata
        for a whole subtree (e.g. validating every field in a ``set_named``
        value dict).

        Returns ``{relative_child_path: {attr: value}}``.  Attr spellings
        follow the Scheme convention (``"min"``, ``"max"``,
        ``"units-quantity"``, ``"allowed-values"``, ``"active?"``).

        The default returns ``{}`` so callers can fall back gracefully to
        per-path ``get_node_attrs`` calls.

        Parameters
        ----------
        parent_path : str
            Parent Fluent object path used for bulk lookup.
        attrs : list[str]
            Attribute names requested from the backend object.

        Returns
        -------
        dict[str, dict[str, Any]]
            Mapping containing the operation result.
        """
        return {}

    async def probe_path(self, paths: list[str]) -> dict[str, dict[str, Any]]:
        """Cheap pre-flight probe for a batch of settings paths.

        Returns ``{path: {exists, is_active, is_user_creatable, kind}}``
        in a single batched RPC. Live backends should override; the
        default raises :class:`BackendUnavailableError`.

        Parameters
        ----------
        paths : list[str]
            Fluent object paths supplied to the operation.

        Returns
        -------
        dict[str, dict[str, Any]]
            Mapping containing the operation result.
        """
        raise BackendUnavailableError(f"{self.label} does not expose path probes.")

    async def get_command_arguments(self, path: str) -> dict[str, Any] | None:
        """Return the keyword-argument signature of a command path.

        Returns ``None`` if the backend cannot introspect commands or the
        path is not a command. The result shape is::

            {"argument_names": ["type", "name"], "arguments": {"type": {...}, ...}}

        Backends with a live solver session should override.

        Parameters
        ----------
        path : str
            Fluent object path or file-system path to inspect.

        Returns
        -------
        dict[str, Any] | None
            Mapping containing the operation result.
        """
        return None

    async def get_help(self, path: str) -> dict[str, Any]:
        """Return the help.

        Parameters
        ----------
        path : str
            Filesystem path or API path to process.

        Returns
        -------
        dict[str, Any]
            Mapping containing the operation result.
        """
        raise BackendUnavailableError(f"{self.label} does not expose API help.")

    async def solver_status(self) -> dict[str, Any]:
        """Return solver status information from the backend.

        Returns
        -------
        dict[str, Any]
            Mapping containing the operation result.
        """
        raise BackendUnavailableError(f"{self.label} does not expose solver status.")

    async def describe_named_object_template(self, path: str) -> dict[str, Any] | None:
        """Describe the field shape of a fresh child of a named-object collection.

        Returns ``None`` when the backend cannot introspect templates.
        Live backends should override.

        Parameters
        ----------
        path : str
            Fluent object path or file-system path to inspect.

        Returns
        -------
        dict[str, Any] | None
            Mapping containing the operation result.
        """
        return None

    async def list_fields(self, *, scope: str = "any") -> dict[str, Any] | None:
        """Enumerate solver field/variable names available for reports/post.

        Returns ``None`` when unavailable.

        Parameters
        ----------
        scope : str
            Scope used to limit the field or API lookup.

        Returns
        -------
        dict[str, Any] | None
            Mapping containing the operation result.
        """
        return None

    async def get_targeted_context(
        self,
        *,
        paths_to_check: list[str],
        named_object_types: list[str] | None = None,
        instance_state_fetch: list[str] | None = None,
    ) -> dict[str, Any]:
        """Return the targeted context.

        Parameters
        ----------
        paths_to_check : list[str]
            Fluent object paths to validate or inspect.
        named_object_types : list[str] | None
            Named-object families that should be considered during lookup.
        instance_state_fetch : list[str] | None
            Whether named-object instance state should be fetched.

        Returns
        -------
        dict[str, Any]
            Mapping containing the operation result.
        """
        raise BackendUnavailableError(f"{self.label} does not expose targeted context.")

    async def mesh_adjacency_probe(
        self,
        cellzones: list[str],
        *,
        bc_filter: tuple[str, ...] | None = None,
    ) -> dict[str, list[str]]:
        """Return ``{cellzone -> [adjacent_face_zone_names]}``.

        Implementations walk every BC family that exposes
        ``adjacent_cell_zone`` (wall, velocity_inlet, pressure_outlet,
        mass_flow_inlet, …) and invert the mapping. Coupled-wall
        ``shadow_face_zone`` entries are added to BOTH sides so
        cellzone↔cellzone neighbour queries (set-intersection on
        shared face names) find CHT solid–fluid pairs.

        ``bc_filter`` restricts the walk to the listed BC families
        (e.g. ``("wall",)`` to answer "walls adjacent to X",
        ``("velocity_inlet", "pressure_inlet")`` for inlets, ...).
        ``None`` (default) walks every supported family. The shadow
        traversal only contributes when ``"wall"`` is in scope (or
        the filter is None) — interior families have no shadow
        concept.

        Limitation: interior face zones are not enumerated — they are
        gated INACTIVE on ``boundary_conditions.interior[*]`` and the
        ``mesh.adjacency`` Command's argument-binding side-channel is
        broken on Fluent ≥ 27.1. Callers needing interior coverage
        must supplement with ``run_code``.

        Backends without a live solver session must raise
        :class:`BackendUnavailableError`.

        Parameters
        ----------
        cellzones : list[str]
            Cell zone names used for the mesh adjacency query.
        bc_filter : tuple[str, ...] | None
            Boundary-condition filter used to limit the probe.

        Returns
        -------
        dict[str, list[str]]
            Mapping containing the operation result.
        """
        raise BackendUnavailableError(f"{self.label} does not expose mesh adjacency.")

    async def find_api(
        self,
        query: str,
        *,
        top_k: int = 10,
        kinds: list[str] | None = None,
        under: str | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve candidate Fluent settings APIs for ``query``.

        Uses the configured lexical :class:`ApiRetriever`, which
        performs BM25 ranking over the bundled Fluent API catalog
        and PyFluent class docstrings.

        Returns a list of ``{path, kind, score, ...}`` hits.
        Backends may override to add live cross-checks (e.g. filter
        out paths whose immediate parent does not exist on the
        connected solver).

        Parameters
        ----------
        query : str
            Search query supplied by the caller.
        top_k : int
            Maximum number of search hits to return.
        kinds : list[str] | None
            Optional API object kinds used to filter search results.
        under : str | None
            Optional root path used to constrain API search results.

        Returns
        -------
        list[dict[str, Any]]
            Mapping containing the operation result.
        """
        from ansys.fluent.mcp.solve.catalog.retriever import get_default_api_retriever

        retriever = get_default_api_retriever()
        hits = await retriever.retrieve(query, top_k=top_k, kinds=kinds, under=under)
        if not hits:
            raise BackendUnavailableError(
                "No API retriever returned results. "
                "Install pyfluent and ensure the lexical API index is available."
            )
        return [h.to_tool_dict() for h in hits]

    # ---- code execution ----------------------------------------------

    async def run_code(
        self,
        code: str,
        *,
        namespace: dict[str, Any] | None = None,
        filename: str = "<ansys-fluent-mcp>",
    ) -> RunCodeResult:
        """Execute Python code through the backend runtime.

        Parameters
        ----------
        code : str
            Python code or command text to execute or validate.
        namespace : dict[str, Any] | None
            Namespace used to resolve the backend object or route.
        filename : str
            File name or path used by the backend operation.

        Returns
        -------
        RunCodeResult
            RunCodeResult produced by the operation.
        """
        raise BackendUnavailableError(f"{self.label} does not support run_code.")

    async def validate_code(self, code: str) -> RunCodeResult:
        """Default validation: AST parse + forbidden-call scan.

        Backends with a live solver session can override to add semantic
        checks against the connected model.

        Parameters
        ----------
        code : str
            Python code snippet to validate or execute.

        Returns
        -------
        RunCodeResult
            Result produced by the function.
        """
        from ansys.fluent.mcp.common.validation import validate_python_source

        return validate_python_source(code)

    # ---- mesh introspection ------------------------------------------

    async def mesh_counts(self) -> dict[str, int | None]:
        """Return live mesh element totals.

        Output shape: ``{"cell_count", "face_count", "node_count"}`` —
        each value is an ``int`` when the underlying solver exposes the
        count, or ``None`` when the count is unavailable (no mesh
        loaded, partition pending, or the backend has no introspection
        path to mesh totals). Callers MUST treat ``None`` as
        ``unknown`` — never as zero.

        The default raises :class:`BackendUnavailableError` so backends that
        have no live solver (Fluids One geometry / mesh / post leaves)
        decline the probe; the smart-defaults wrapper catches this and
        falls back to an all-``None`` payload. Solve backends override
        this to query Fluent (e.g. via the Scheme variables
        ``tinfo/n-cells`` etc.).

        Returns
        -------
        dict[str, int | None]
            Mapping containing the operation result.
        """
        raise BackendUnavailableError(f"{self.label} does not expose mesh counts.")

    async def mesh_quality(self) -> dict[str, float | None]:
        """Return live mesh-quality summary statistics.

        Output shape:
        ``{"min_orthogonal_quality", "max_ortho_skew", "max_aspect_ratio"}``
        — each value is a ``float`` in its native Fluent range (orthogonal
        quality 0..1 where higher is better; ortho skew 0..1 where lower
        is better; aspect ratio ≥ 1) or ``None`` when the metric is not
        available (no mesh loaded, ``mesh.quality`` failed, or the report
        wording on the connected Fluent build doesn't match the parser).

        Callers MUST treat ``None`` as ``unknown`` — never as a passing
        score. Backends should cache the result (mesh quality is
        invariant between mutations) and invalidate on mesh-modifying
        operations (case load, scale, translate, rotate, adapt, repair).

        The default raises :class:`BackendUnavailableError`. Solve backends
        override this to invoke Fluent's ``mesh.quality`` settings
        command and parse the captured transcript.

        Returns
        -------
        dict[str, float | None]
            Mapping containing the operation result.
        """
        raise BackendUnavailableError(f"{self.label} does not expose mesh quality.")

    async def mesh_check(self) -> dict[str, Any]:
        """Return Fluent's full ``mesh.check`` report as structured data.

        Output shape (all keys optional — a value is ``None`` when the
        corresponding line was not present in the captured transcript):

        .. code-block::

            {
                "domain_extents": {"x": (min, max), "y": (min, max), "z": (min, max)},
                "volume_min": float | None,
                "volume_max": float | None,
                "volume_total": float | None,
                "face_area_min": float | None,
                "face_area_max": float | None,
                "errors": list[str],          # lines preceded by "Error:"
                "warnings": list[str],        # lines preceded by "Warning:"
                "raw": str,                   # the verbatim transcript chunk
            }

        ``mesh.check`` is the right pre-flight diagnostic — it covers
        topology (left-handed cells, non-positive volumes, face
        handedness, periodic / boundary-pair sanity) on top of the bulk
        statistics. It does NOT print quality numbers in modern Fluent
        builds (see :meth:`mesh_quality` for those).

        The default raises :class:`BackendUnavailableError`.

        Returns
        -------
        dict[str, Any]
            Mapping containing the operation result.
        """
        raise BackendUnavailableError(f"{self.label} does not expose mesh check.")

    # ---- component lifecycle -----------------------------------------

    async def activate_component(self) -> dict[str, Any]:
        """Start or resume the managed Fluids One component.

        Sends POST ``/api/session/components/<instance>/activate``.
        Returns a status dict. Backends that do not talk to Fluids One
        raise :class:`BackendUnavailableError`.

        Returns
        -------
        dict[str, Any]
            Mapping containing the operation result.
        """
        raise BackendUnavailableError(f"{self.label} does not support activate_component.")

    async def deactivate_component(self) -> dict[str, Any]:
        """Stop the managed Fluids One component.

        Sends POST ``/api/session/components/<instance>/deactivate``.
        Returns a status dict. Backends that do not talk to Fluids One
        raise :class:`BackendUnavailableError`.

        Returns
        -------
        dict[str, Any]
            Mapping containing the operation result.
        """
        raise BackendUnavailableError(f"{self.label} does not support deactivate_component.")

    async def update_component(self) -> dict[str, Any]:
        """Update the managed Fluids One component.

        Sends POST ``/api/session/components/<instance>/update``.
        Returns a status dict. Backends that do not talk to Fluids One
        raise :class:`BackendUnavailableError`.

        Returns
        -------
        dict[str, Any]
            Mapping containing the operation result.
        """
        raise BackendUnavailableError(f"{self.label} does not support update_component.")

    async def refresh_component(self) -> dict[str, Any]:
        """Refresh the managed Fluids One component.

        Sends POST ``/api/session/components/<instance>/refresh``.
        Returns a status dict. Backends that do not talk to Fluids One
        raise :class:`BackendUnavailableError`.

        Returns
        -------
        dict[str, Any]
            Mapping containing the operation result.
        """
        raise BackendUnavailableError(f"{self.label} does not support refresh_component.")

    # ---- visuals ------------------------------------------------------

    async def screenshot(self, *, view: Optional[str] = None) -> dict[str, Any]:
        """Capture a screenshot from the backend runtime.

        Parameters
        ----------
        view : Optional[str]
            Graphics view or camera preset requested by the caller.

        Returns
        -------
        dict[str, Any]
            Mapping containing the operation result.
        """
        raise BackendUnavailableError(f"{self.label} does not support screenshot.")

    # ---- caching helpers ---------------------------------------------

    def _cache_get(self, key: str, ttl: float) -> Any | None:
        """Return a cached value for the requested key.

        Parameters
        ----------
        key : str
            Key used to look up or store the associated value.
        ttl : float
            Ttl to supply to the function.

        Returns
        -------
        Any | None
            Optional value produced by the operation.
        """
        entry = self._cache.get(key)
        if entry is None:
            return None
        ts, value = entry
        if time.monotonic() - ts > ttl:
            self._cache.pop(key, None)
            return None
        return value

    def _cache_put(self, key: str, value: Any) -> None:
        """Store a value in the cache under the requested key.

        Parameters
        ----------
        key : str
            Key used to look up or store the associated value.
        value : Any
            Value to inspect, convert, or store.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        self._cache[key] = (time.monotonic(), value)

    def _mesh_cache_get(self, key: str, ttl: float | None = None) -> Any | None:
        """Return a cached mesh-probe value for ``key``.

        Parameters
        ----------
        key : str
            Key used to look up the associated value.
        ttl : float | None
            Optional TTL in seconds; ``None`` means session-scoped.

        Returns
        -------
        Any | None
            Optional value produced by the operation.
        """
        entry = self._mesh_cache.get(key)
        if entry is None:
            return None
        ts, value = entry
        if ttl is not None and time.monotonic() - ts > ttl:
            self._mesh_cache.pop(key, None)
            return None
        return value

    def _mesh_cache_put(self, key: str, value: Any) -> None:
        """Store a mesh-probe value under ``key``.

        Parameters
        ----------
        key : str
            Key used to store the associated value.
        value : Any
            Value to store.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        self._mesh_cache[key] = (time.monotonic(), value)

    def invalidate_mesh_cache(self) -> None:
        """Drop cached mesh-probe results.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        self._mesh_cache.clear()

    def maybe_invalidate_mesh_cache(self, code: str) -> bool:
        """Drop the mesh cache when ``code`` matches a mutation marker.

        Parameters
        ----------
        code : str
            ``run_code`` snippet to inspect.

        Returns
        -------
        bool
            ``True`` when the cache was cleared.
        """
        if not code:
            return False
        for marker in self.MESH_MUTATION_MARKERS:
            if marker and marker in code:
                self.invalidate_mesh_cache()
                return True
        return False

    def invalidate_cache(self) -> None:
        """Clear cached backend state.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        self._cache.clear()
        self._mesh_cache.clear()

    def invalidate_live_caches(self) -> None:
        """Drop caches that depend on solver state.

        Called by the framework after every ``run_code`` and after
        ``connect``. The mesh-probe cache is preserved; use
        :meth:`invalidate_mesh_cache` or
        :meth:`maybe_invalidate_mesh_cache` to drop it explicitly.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        self._cache.clear()
