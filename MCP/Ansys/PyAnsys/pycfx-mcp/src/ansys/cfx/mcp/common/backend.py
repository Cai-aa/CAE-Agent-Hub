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
talks to a supported fluids product or service. MCP tools are the public wire
surface; backends are implementation-facing.

A backend implements only the operations its product supports. Unsupported
operations raise `BackendUnavailable` so the typed-error guard converts them
to a clean error code instead of a 500 error code.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import fnmatch
import time
from typing import Any, Optional

from ansys.cfx.mcp.common.errors import BackendUnavailable
from ansys.cfx.mcp.common.models import (
    ConnectResult,
    RemediationResult,
    RunCodeResult,
    SessionStatus,
)


class Backend(ABC):
    """Common interface for all backends.

    Concrete subclasses override only the methods their product supports.
    Default implementations raise a `BackendUnavailable` error.
    """

    #: Short identifier surfaced to MCP clients (for example, "pycfx").
    kind: str = "unknown"
    #: Human-readable name surfaced in `session.status`.
    label: str = "Unknown backend"

    def __init__(self) -> None:
        """Initialize this object with the dependencies required for later operations.

        Returns
        -------
        None
            No value is returned. Side effects are applied to the relevant cache, session, or
            server.
        """
        self._cache: dict[str, tuple[float, Any]] = {}

    # ---- lifecycle ----------------------------------------------------

    @abstractmethod
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
        ...

    async def disconnect(self) -> None:
        """Disconnect this backend from its active CFX runtime or service.

        Returns
        -------
        None
            No value is returned. Side effects are applied to the relevant cache, session, or
            server.
        """
        return None

    @abstractmethod
    def is_connected(self) -> bool:
        """Whether the backend is currently connected.

        Returns
        -------
        bool
            Whether the backend currently has an active CFX connection.
        """
        ...

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
        return SessionStatus(
            leaf=leaf,
            connected=self.is_connected(),
            backend=self.label,
            backend_kind=self.kind,  # type: ignore[arg-type]
            endpoint=getattr(self, "endpoint", None),
        )

    # ---- remediation --------------------------------------------------

    async def error_remediation(
        self,
        remediation_request: str,
        *,
        context: Optional[dict[str, Any]] = None,
    ) -> RemediationResult:
        """Return recovery guidance for a failed backend operation.

        Parameters
        ----------
        remediation_request : str
            Error text, failing code, or diagnostic request to explain and remediate.
        context : Optional[dict[str, Any]], default: None
            Optional backend status, validation result, or MCP tool context.

        Returns
        -------
        RemediationResult
            Structured remediation advice from the backend.
        """
        raise BackendUnavailable(f"{self.label} does not support error_remediation.")

    # ---- live model context ------------------------------------------

    async def list_named_objects(self) -> dict[str, Any]:
        """List named objects available in the active context.

        Returns
        -------
        dict[str, Any]
            Structured response payload for the requested operation.
        """
        raise BackendUnavailable(f"{self.label} does not expose named objects.")

    async def select_named_objects(self, names: list[str]) -> list[str]:
        """Return the subset of requested named objects that are available.

        Parameters
        ----------
        names : list[str]
            Candidate named-object names.

        Returns
        -------
        list[str]
            Matching named-object names.
        """
        raise BackendUnavailable(f"{self.label} does not expose selectable named objects.")

    async def get_help(self, path: str) -> dict[str, Any]:
        """Return help information for a backend-specific API path.

        Parameters
        ----------
        path : str
            API path to describe.

        Returns
        -------
        dict[str, Any]
            Structured help payload.
        """
        raise BackendUnavailable(f"{self.label} does not expose API help.")

    async def solver_status(self) -> dict[str, Any]:
        """Return solver status information for the backend.

        Returns
        -------
        dict[str, Any]
            Structured solver-status payload.
        """
        raise BackendUnavailable(f"{self.label} does not expose solver status.")

    async def get_named_object_names(self, collection_path: str) -> list[str]:
        """Return named object names for the active CFX context.

        Parameters
        ----------
        collection_path : str
            Named-object collection path to read, such as a boundary or domain collection.

        Returns
        -------
        list[str]
            Names in the requested collection, or an empty list when named objects are not
            available.
        """
        try:
            mapping = await self.list_named_objects()
        except BackendUnavailable:
            return []
        names = mapping.get(collection_path) or []
        return [str(n) for n in names]

    async def find_named_object(self, name: str) -> list[dict[str, Any]]:
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
        if not name or not name.strip():
            return []
        target = name.strip()
        try:
            mapping = await self.list_named_objects()
        except BackendUnavailable:
            return []

        if any(char in target for char in "*?[") or "|" in target:
            results: list[dict[str, Any]] = []
            patterns = [part.strip() for part in target.split("|") if part.strip()]
            for coll_path, names in (mapping or {}).items():
                live_names = [str(n) for n in (names or [])]
                for pattern in patterns:
                    for match in sorted(
                        name for name in live_names if fnmatch.fnmatchcase(name, pattern)
                    ):
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
        raise BackendUnavailable(f"{self.label} does not expose state.")

    async def get_active_status(self, paths: list[str]) -> dict[str, bool]:
        """Get the active/inactive status for a CFX path or component.

        Parameters
        ----------
        paths : list[str]
            Backend paths to inspect.

        Returns
        -------
        dict[str, Any]
            Structured active-status payload for the requested path or component.
        """
        raise BackendUnavailable(f"{self.label} does not expose active status.")

    async def get_allowed_values(self, paths: list[str]) -> dict[str, list[Any]]:
        """Get allowed values for a CFX path from live state or schema metadata.

        Parameters
        ----------
        paths : list[str]
            Backend paths to inspect.

        Returns
        -------
        dict[str, list[Any]]
            Structured allowed-values payload for the requested path.
        """
        raise BackendUnavailable(f"{self.label} does not expose allowed values.")

    async def get_node_attrs(
        self,
        paths: list[str],
        attrs: list[str],
    ) -> dict[str, dict[str, Any]]:
        """Get selected attributes for one or more backend nodes.

        Parameters
        ----------
        paths : list[str]
            Backend node paths whose attributes should be retrieved.
        attrs : list[str]
            Attributes to retrieve from a backend node.

        Returns
        -------
        dict[str, dict[str, Any]]
            Mapping from each requested path to its available attribute values.
        """
        raise BackendUnavailable(f"{self.label} does not expose node attrs.")

    async def get_node_attrs_bulk(
        self,
        parent_path: str,
        attrs: list[str],
    ) -> dict[str, dict[str, Any]]:
        """Get selected attributes for children under a parent backend node.

        Parameters
        ----------
        parent_path : str
            Parent CFX path that owns the requested child fields.
        attrs : list[str]
            Attributes to retrieve from a backend node.

        Returns
        -------
        dict[str, dict[str, Any]]
            Mapping from child path to the requested attribute values.
        """
        return {}

    async def probe_path(self, paths: list[str]) -> dict[str, dict[str, Any]]:
        """Check whether a backend path can be resolved.

        Parameters
        ----------
        paths : list[str]
            Backend paths to resolve against the live state or schema metadata.

        Returns
        -------
        dict[str, dict[str, Any]]
            Resolution details for each requested path.
        """
        raise BackendUnavailable(f"{self.label} does not expose path probes.")

    async def get_command_arguments(self, path: str) -> dict[str, Any] | None:
        """Get argument metadata for a command-like CFX path.

        Parameters
        ----------
        path : str
            Command-like backend path whose arguments should be described.

        Returns
        -------
        dict[str, Any] | None
            Argument metadata when the backend can describe the command. Otherwise,
            ``None`` is returned.
        """
        return None

    async def describe_named_object_template(self, path: str) -> dict[str, Any] | None:
        """Describe the fields used when creating a named CFX object.

        Parameters
        ----------
        path : str
            Named-object collection or type path to describe.

        Returns
        -------
        dict[str, Any] | None
            Template metadata for creating the object, or ``None`` when unavailable.
        """
        return None

    async def list_fields(self, *, scope: str = "any") -> dict[str, Any] | None:
        """List fields available for a backend object or schema scope.

        Parameters
        ----------
        scope : str, default:``'any'``
            Scope used to filter available fields.

        Returns
        -------
        dict[str, Any] | None
            Requested CFX data or metadata for the active session.
        """
        return None

    async def get_targeted_context(
        self,
        *,
        paths_to_check: list[str],
        named_object_types: list[str] | None = None,
        instance_state_fetch: list[str] | None = None,
    ) -> dict[str, Any]:
        """Return a compact context slice for the requested CFX paths or objects.

        Parameters
        ----------
        paths_to_check : list[str]
            CFX paths to check against the live state or schema metadata.
        named_object_types : list[str] | None, default: None
            Named-object categories to include in context output.
        instance_state_fetch : list[str] | None, default: None
            Optional callback used to fetch the live instance state.

        Returns
        -------
        dict[str, Any]
            Structured response payload for the requested operation.
        """
        raise BackendUnavailable(f"{self.label} does not expose targeted context.")

    async def mesh_adjacency_probe(
        self,
        cellzones: list[str],
        *,
        bc_filter: tuple[str, ...] | None = None,
    ) -> dict[str, list[str]]:
        """Return mesh adjacency information for candidate boundary locations.

        Parameters
        ----------
        cellzones : list[str]
            Mesh cell zones used for adjacency probing.
        bc_filter : tuple[str, ...] | None, default: None
            Optional boundary-condition filter for adjacency output.

        Returns
        -------
        dict[str, list[str]]
            Value computed by the helper for the requested CFX workflow.
        """
        raise BackendUnavailable(f"{self.label} does not expose mesh adjacency.")

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
            Optional result categories for narrowing the search.
        under : str | None, default: None
            Optional CFX path prefix for scoping the search.

        Returns
        -------
        list[dict[str, Any]]
            List of structured records matching the request.
        """
        raise BackendUnavailable(f"{self.label} does not expose API search.")

    # ---- code execution ----------------------------------------------

    async def run_code(
        self,
        code: str,
        *,
        namespace: dict[str, Any] | None = None,
        filename: str = "<ansys-cfx-mcp>",
    ) -> RunCodeResult:
        """Execute Python code against the active CFX backend namespace.

        Parameters
        ----------
        code : str
            Python source code submitted for validation, grounding, or execution.
        namespace : dict[str, Any] | None, default: None
            Execution namespace containing safe builtins and active CFX objects.
        filename : str, default: ``"<ansys-cfx-mcp>"``
            Synthetic filename used in compile diagnostics.

        Returns
        -------
        RunCodeResult
            Execution or validation result returned to the MCP caller.
        """
        raise BackendUnavailable(f"{self.label} does not support run_code.")

    async def validate_code(self, code: str) -> RunCodeResult:
        """Validate Python code without mutating the active backend.

        Parameters
        ----------
        code : str
            Python source code submitted for validation, grounding, or execution.

        Returns
        -------
        RunCodeResult
            Execution or validation result returned to the MCP caller.
        """
        from ansys.cfx.mcp.common.validation import validate_python_source

        return validate_python_source(code)

    # ---- mesh introspection ------------------------------------------

    async def mesh_counts(self) -> dict[str, int | None]:
        """Return mesh entity counts reported by the backend.

        Returns
        -------
        dict[str, int | None]
            Value computed by the helper for the requested CFX workflow.
        """
        raise BackendUnavailable(f"{self.label} does not expose mesh counts.")

    async def mesh_quality(self) -> dict[str, float | None]:
        """Return mesh quality metrics reported by the backend.

        Returns
        -------
        dict[str, float | None]
            Value computed by the helper for the requested CFX workflow.
        """
        raise BackendUnavailable(f"{self.label} does not expose mesh quality.")

    async def mesh_check(self) -> dict[str, Any]:
        """Run backend mesh checks and return their diagnostics.

        Returns
        -------
        dict[str, Any]
            Structured response payload for the requested operation.
        """
        raise BackendUnavailable(f"{self.label} does not expose mesh check.")

    # ---- component lifecycle -----------------------------------------

    async def activate_component(self) -> dict[str, Any]:
        """Activate a backend component for later operations.

        Returns
        -------
        dict[str, Any]
            Structured response payload for the requested operation.
        """
        raise BackendUnavailable(f"{self.label} does not support activate_component.")

    async def deactivate_component(self) -> dict[str, Any]:
        """Deactivate a backend component that should no longer receive operations.

        Returns
        -------
        dict[str, Any]
            Structured response payload for the requested operation.
        """
        raise BackendUnavailable(f"{self.label} does not support deactivate_component.")

    async def update_component(self) -> dict[str, Any]:
        """Update backend component state with new data.

        Returns
        -------
        dict[str, Any]
            Structured response payload for the requested operation.
        """
        raise BackendUnavailable(f"{self.label} does not support update_component.")

    async def refresh_component(self) -> dict[str, Any]:
        """Refresh backend component state from the active session.

        Returns
        -------
        dict[str, Any]
            Structured response payload for the requested operation.
        """
        raise BackendUnavailable(f"{self.label} does not support refresh_component.")

    # ---- visuals ------------------------------------------------------

    async def screenshot(self, *, view: Optional[str] = None) -> dict[str, Any]:
        """Capture a screenshot from the active backend, when supported.

        Parameters
        ----------
        view : Optional[str], default: None
            Optional view name for the screenshot capture.

        Returns
        -------
        dict[str, Any]
            Structured response payload for the requested operation.
        """
        raise BackendUnavailable(f"{self.label} does not support screenshot.")

    # ---- caching helpers ---------------------------------------------

    def _cache_get(self, key: str, ttl: float) -> Any | None:
        """Return a cached backend value when it exists and has not expired.

        Parameters
        ----------
        key : str
            Cache key identifying the value to read, write, or invalidate.
        ttl : float
            Time-to-live in seconds for the cached backend value.

        Returns
        -------
        Any | None
            Cached value when present and fresh. Otherwise, ``None`` is returned.
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
        """Store a backend value in the local cache with an optional time to live.

        Parameters
        ----------
        key : str
            Cache key identifying the value to read, write, or invalidate.
        value : Any
            Value to store in the target cache or data structure.

        Returns
        -------
        None
            No value is returned. The backend cache is updated in place.
        """
        self._cache[key] = (time.monotonic(), value)

    def invalidate_cache(self) -> None:
        """Clear cached backend data that may no longer reflect the active CFX session.

        Returns
        -------
        None
            No value is returned. Side effects are applied to the relevant cache, session, or
            server.
        """
        self._cache.clear()

    def invalidate_live_caches(self) -> None:
        """Clear live CFX session caches after the model or session state changes.

        Returns
        -------
        None
            No value is returned. Side effects are applied to the relevant cache, session, or
            server.
        """
        self.invalidate_cache()
