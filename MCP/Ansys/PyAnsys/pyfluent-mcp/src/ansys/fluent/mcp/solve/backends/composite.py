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

"""Composite backend: deterministic PyFluent solver operations.

The solve leaf requires a live PyFluent solver session for code execution
and live-model introspection.  This composite backend ensures that PyFluent
is **always** the execution engine, regardless of how the user initiates
the connection. Semantic orchestration is intentionally left to the host
application.

Typical usage from an MCP client::

    connect()  # launches / attaches PyFluent
    run_code(code)  # → PyFluent (always)
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from ansys.fluent.mcp.common.backend import Backend
from ansys.fluent.mcp.common.models import ConnectResult, RunCodeResult, SessionStatus
from ansys.fluent.mcp.solve.backends.pyfluent import PyFluentBackend

logger = logging.getLogger("ansys.fluent.mcp.backends.solve_composite")


class SolveCompositeBackend(Backend):
    """Composite backend that delegates deterministic operations to PyFluent.

    * **Execution & live context** are always handled by an in-process
      :class:`PyFluentBackend`.
    """

    kind = "pyfluent"

    def __init__(self, *, label: str = "Solve (PyFluent)") -> None:
        """Initialize the SolveCompositeBackend instance.

        Parameters
        ----------
        label : str
            Human-readable label attached to the operation or test double.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        super().__init__()
        self.label = label
        self._pyfluent = PyFluentBackend()

    # ------------------------------------------------------------------
    # Properties delegated to the PyFluent backend
    # ------------------------------------------------------------------

    @property
    def endpoint(self) -> Optional[str]:  # type: ignore[override]
        """Return the backend endpoint description.

        Returns
        -------
        Optional[str]
            Optional value produced by the operation.
        """
        return self._pyfluent.endpoint

    @endpoint.setter
    def endpoint(self, value: Optional[str]) -> None:
        # Endpoint is managed internally by the PyFluent backend.
        """Return the backend endpoint description.

        Parameters
        ----------
        value : Optional[str]
            Value to inspect, convert, or store.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        pass

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(  # type: ignore[override]
        self,
        *,
        # PyFluent connection params
        ip: Optional[str] = None,
        port: Optional[int] = None,
        password: Optional[str] = None,
        server_info_file: Optional[str] = None,
        precision: str = "double",
        processor_count: int = 1,
        ui_mode: str = "gui",
        product_version: Optional[str] = None,
        **kwargs: Any,
    ) -> ConnectResult:
        # Always connect PyFluent — this is the execution engine.
        """Connect to the configured backend or service.

        Parameters
        ----------
        ip : Optional[str]
            IP address of the Fluent server to connect to.
        port : Optional[int]
            Port number of the Fluent server to connect to.
        password : Optional[str]
            Password used when connecting to a Fluent server.
        server_info_file : Optional[str]
            Server-info file used to connect to an existing Fluent session.
        precision : str
            Solver precision requested for the Fluent session.
        processor_count : int
            Number of processors requested for the Fluent session.
        ui_mode : str
            Fluent UI mode requested for launch.
        product_version : Optional[str]
            Fluent product version requested for launch.
        kwargs : Any
            Additional launch options accepted by the PyFluent backend.

        Returns
        -------
        ConnectResult
            ConnectResult produced by the operation.
        """
        pf_result = await self._pyfluent.connect(
            ip=ip,
            port=port,
            password=password,
            server_info_file=server_info_file,
            precision=precision,
            processor_count=processor_count,
            ui_mode=ui_mode,
            product_version=product_version,
            **kwargs,
        )
        if pf_result.status != "ok":
            return pf_result

        self.invalidate_live_caches()
        self.invalidate_mesh_cache()
        return ConnectResult(
            status="ok",
            backend_kind=self.kind,
            endpoint=self._pyfluent.endpoint,
            message=f"PyFluent connected ({self._pyfluent._mode}).",
        )

    async def disconnect(self) -> None:
        """Close resources for the SolveCompositeBackend object.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        await self._pyfluent.disconnect()
        self.invalidate_cache()

    def is_connected(self) -> bool:
        """Return whether connected.

        Returns
        -------
        bool
            Boolean result of the operation.
        """
        return self._pyfluent.is_connected()

    def close_sync(self) -> None:
        """Best-effort synchronous cleanup for shutdown.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        self._pyfluent.close_sync()

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
        base = self._pyfluent.status(leaf)
        notes = list(base.notes)
        return SessionStatus(
            leaf=leaf,
            connected=self.is_connected(),
            backend=self.label,
            backend_kind=self.kind,
            endpoint=self._pyfluent.endpoint,
            capabilities=base.capabilities,
            notes=notes,
        )

    # ------------------------------------------------------------------
    # Live model context → always PyFluent
    # ------------------------------------------------------------------

    async def list_named_objects(self) -> dict[str, Any]:
        """List named objects entries.

        Returns
        -------
        dict[str, Any]
            Mapping containing the operation result.
        """
        return await self._pyfluent.list_named_objects()

    async def get_named_object_names(self, collection_path: str) -> list[str]:
        """Return the named object names.

        Parameters
        ----------
        collection_path : str
            Path for the collection.

        Returns
        -------
        list[str]
            List of results produced by the operation.
        """
        return await self._pyfluent.get_named_object_names(collection_path)

    async def find_named_object(self, name: str) -> list[dict[str, Any]]:
        """Find named object entries.

        Parameters
        ----------
        name : str
            Name of the object, module, or setting being processed.

        Returns
        -------
        list[dict[str, Any]]
            List of results produced by the operation.
        """
        return await self._pyfluent.find_named_object(name)

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
        return await self._pyfluent.get_state(paths=paths)

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
        return await self._pyfluent.get_active_status(paths)

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
        return await self._pyfluent.get_allowed_values(paths)

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
        return await self._pyfluent.get_targeted_context(
            paths_to_check=paths_to_check,
            named_object_types=named_object_types,
            instance_state_fetch=instance_state_fetch,
        )

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
        return await self._pyfluent.get_help(path)

    async def probe_path(self, paths: list[str]) -> dict[str, dict[str, Any]]:
        """Return the ``{exists, is_active, is_user_creatable, kind}`` envelope.

        Delegates to PyFluent so the executor / validator can pre-flight a
        batch of mutating writes against the same live session that will run
        them. The base ``Backend`` raises ``BackendUnavailableError``; without
        this delegation the ``probe_path`` / ``describe_path`` tools are dead.

        Parameters
        ----------
        paths : list[str]
            Fluent object paths to pre-flight.

        Returns
        -------
        dict[str, dict[str, Any]]
            Mapping of path to its probe envelope.
        """
        return await self._pyfluent.probe_path(paths)

    async def describe_named_object_template(self, path: str) -> dict[str, Any] | None:
        """Describe the child field shape of a NamedObject collection.

        Delegates to PyFluent's static-settings-class walk. The base
        ``Backend`` returns ``None`` (rendering ``template: null``); this
        delegation surfaces the real per-field template.

        Parameters
        ----------
        path : str
            NamedObject collection path to inspect.

        Returns
        -------
        dict[str, Any] | None
            Template mapping, or ``None`` when the path is not a NamedObject
            collection.
        """
        return await self._pyfluent.describe_named_object_template(path)

    async def get_command_arguments(self, path: str) -> dict[str, Any] | None:
        """Return the keyword-argument signature of a command path.

        Delegates to PyFluent so ``describe_path`` can fuse the create-command
        signature into its unified descriptor.

        Parameters
        ----------
        path : str
            Command path to introspect.

        Returns
        -------
        dict[str, Any] | None
            Argument signature, or ``None`` when the path is not a command.
        """
        return await self._pyfluent.get_command_arguments(path)

    async def list_fields(self, *, scope: str = "any") -> dict[str, Any] | None:
        """Enumerate solver field / variable names for reports & post.

        Delegates to PyFluent; the base ``Backend`` returns ``None`` and would
        otherwise strand the ``list_fields`` tool and any report-def / graphics
        recipe that validates a ``field`` argument against it.

        Parameters
        ----------
        scope : str
            Field-info scope hint (``"any"``, ``"cell"``, ``"node"``,
            ``"surface"``).

        Returns
        -------
        dict[str, Any] | None
            Mapping containing the available field names, or ``None``.
        """
        return await self._pyfluent.list_fields(scope=scope)

    async def mesh_adjacency_probe(
        self,
        cellzones: list[str],
        *,
        bc_filter: tuple[str, ...] | None = None,
    ) -> dict[str, list[str]]:
        """Return ``{cellzone -> [adjacent_face_zone_names]}`` from PyFluent."""
        return await self._pyfluent.mesh_adjacency_probe(
            cellzones,
            bc_filter=bc_filter,
        )

    async def solver_status(self) -> dict[str, Any]:
        """Return solver status information from the backend.

        Returns
        -------
        dict[str, Any]
            Mapping containing the operation result.
        """
        return await self._pyfluent.solver_status()

    async def mesh_counts(self) -> dict[str, int | None]:
        """Return mesh entity counts.

        Returns
        -------
        dict[str, int | None]
            Mapping containing the operation result.
        """
        return await self._pyfluent.mesh_counts()

    async def mesh_quality(self) -> dict[str, float | None]:
        """Return mesh quality information from the backend.

        Returns
        -------
        dict[str, float | None]
            Mapping containing the operation result.
        """
        return await self._pyfluent.mesh_quality()

    async def mesh_check(self) -> dict[str, Any]:
        """Run the backend mesh check operation.

        Returns
        -------
        dict[str, Any]
            Mapping containing the operation result.
        """
        return await self._pyfluent.mesh_check()

    # ------------------------------------------------------------------
    # Code execution → always PyFluent
    # ------------------------------------------------------------------

    async def run_code(
        self,
        code: str,
        *,
        namespace: dict[str, Any] | None = None,
        filename: str = "<mcp>",
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
        return await self._pyfluent.run_code(code, namespace=namespace, filename=filename)

    async def validate_code(self, code: str) -> RunCodeResult:
        """Validate code.

        Parameters
        ----------
        code : str
            Python code or command text to execute or validate.

        Returns
        -------
        RunCodeResult
            RunCodeResult produced by the operation.
        """
        return await self._pyfluent.validate_code(code)

    # ------------------------------------------------------------------
    # Visuals → PyFluent
    # ------------------------------------------------------------------

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
        return await self._pyfluent.screenshot(view=view)

    # ------------------------------------------------------------------
    # Cache management
    # ------------------------------------------------------------------

    def invalidate_cache(self) -> None:
        """Clear cached backend state.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        super().invalidate_cache()
        self._pyfluent.invalidate_cache()

    def invalidate_live_caches(self) -> None:
        """Clear cached live backend state.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        super().invalidate_live_caches()
        self._pyfluent.invalidate_live_caches()

    def invalidate_mesh_cache(self) -> None:
        """Clear mesh-probe caches on the composite and inner backend.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        super().invalidate_mesh_cache()
        self._pyfluent.invalidate_mesh_cache()
