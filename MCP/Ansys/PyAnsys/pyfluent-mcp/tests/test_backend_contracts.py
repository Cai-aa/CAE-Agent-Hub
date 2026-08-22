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

import asyncio

import pytest

from ansys.fluent.mcp.common.backend import Backend
from ansys.fluent.mcp.common.errors import BackendUnavailableError
from ansys.fluent.mcp.common.models import ConnectResult, RunCodeResult, SessionStatus
from ansys.fluent.mcp.solve.backends import composite


class ContractBackend(Backend):
    kind = "pyfluent"
    label = "Contract backend"

    def __init__(self, mapping=None, connected=False):
        """Initialize the ContractBackend instance.

        Parameters
        ----------
        mapping : Any
            Mapping used by the fake backend or helper under test.
        connected : Any
            Whether the fake or test backend should report an active connection.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        super().__init__()
        self.mapping = mapping
        self.connected = connected

    async def connect(self, **_kwargs):
        """Connect to the configured backend or service.

        Parameters
        ----------
        _kwargs : Any
            Keyword arguments forwarded to the wrapped call.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        self.connected = True
        return ConnectResult(status="ok", backend_kind=self.kind)

    def is_connected(self):
        """Return whether connected.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        return self.connected

    async def list_named_objects(self):
        """List named objects entries.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        if self.mapping is None:
            raise BackendUnavailableError("missing mapping")
        return self.mapping


def test_backend_default_status_cache_and_name_lookup():
    """Verify that backend default status cache and name lookup.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    backend = ContractBackend(
        {
            "setup.boundary_conditions.wall": ["hot-wall", "cold-wall"],
            "setup.boundary_conditions.velocity_inlet": ["inlet-1"],
        },
        connected=True,
    )
    backend.endpoint = "local"

    status = backend.status("solve")
    assert status == SessionStatus(
        leaf="solve",
        connected=True,
        backend="Contract backend",
        backend_kind="pyfluent",
        endpoint="local",
    )
    assert asyncio.run(backend.get_named_object_names("setup.boundary_conditions.wall")) == [
        "hot-wall",
        "cold-wall",
    ]
    assert asyncio.run(backend.find_named_object("HOT-wall")) == [
        {"collection_path": "setup.boundary_conditions.wall", "name": "hot-wall", "exact": False}
    ]
    pattern_hits = asyncio.run(backend.find_named_object("*wall"))
    assert {hit["name"] for hit in pattern_hits} == {"hot-wall", "cold-wall"}
    assert all(hit["is_pattern"] for hit in pattern_hits)
    assert asyncio.run(backend.find_named_object("  ")) == []

    backend._cache_put("named", {"a": 1})
    assert backend._cache_get("named", ttl=30) == {"a": 1}
    assert backend._cache_get("named", ttl=-1) is None
    backend._cache_put("named", {"b": 2})
    backend.invalidate_live_caches()
    assert backend._cache_get("named", ttl=30) is None


def test_backend_default_methods_and_validation(monkeypatch):
    """Verify that backend default methods and validation.

    Parameters
    ----------
    monkeypatch : Any
        Pytest fixture used to patch environment variables or dependencies.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    backend = ContractBackend(mapping=None)

    assert asyncio.run(backend.disconnect()) is None
    assert asyncio.run(backend.get_command_arguments("x")) is None
    assert asyncio.run(backend.describe_named_object_template("x")) is None
    assert asyncio.run(backend.list_fields()) is None
    assert asyncio.run(backend.validate_code("x = 1")).status == "ok"
    assert asyncio.run(backend.find_named_object("x")) == []
    assert asyncio.run(backend.get_named_object_names("x")) == []

    async def raises_unavailable(call):
        """Create an unavailable-backend error helper.

        Parameters
        ----------
        call : Any
            Call to supply to the function.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        with pytest.raises(BackendUnavailableError):
            await call()

    asyncio.run(raises_unavailable(lambda: backend.get_state()))
    asyncio.run(raises_unavailable(lambda: backend.get_active_status(["x"])))
    asyncio.run(raises_unavailable(lambda: backend.get_allowed_values(["x"])))
    asyncio.run(raises_unavailable(lambda: backend.get_node_attrs(["x"], ["active?"])))
    asyncio.run(raises_unavailable(lambda: backend.probe_path(["x"])))
    asyncio.run(raises_unavailable(lambda: backend.get_help("x")))
    asyncio.run(raises_unavailable(lambda: backend.solver_status()))
    asyncio.run(raises_unavailable(lambda: backend.get_targeted_context(paths_to_check=["x"])))
    asyncio.run(raises_unavailable(lambda: backend.mesh_adjacency_probe(["fluid"])))
    asyncio.run(raises_unavailable(lambda: backend.run_code("x = 1")))
    asyncio.run(raises_unavailable(lambda: backend.mesh_counts()))
    asyncio.run(raises_unavailable(lambda: backend.mesh_quality()))
    asyncio.run(raises_unavailable(lambda: backend.mesh_check()))
    asyncio.run(raises_unavailable(lambda: backend.activate_component()))
    asyncio.run(raises_unavailable(lambda: backend.deactivate_component()))
    asyncio.run(raises_unavailable(lambda: backend.update_component()))
    asyncio.run(raises_unavailable(lambda: backend.refresh_component()))
    asyncio.run(raises_unavailable(lambda: backend.screenshot()))

    class Hit:
        def to_tool_dict(self):
            """Convert the object to a tool response dictionary.

            Returns
            -------
            None
                The function completes through its side effects.
            """
            return {"path": "setup.models.energy", "kind": "Parameter"}

    class Retriever:
        async def retrieve(self, query, top_k, kinds, under):
            """Retrieve API hits that match the query and filters.

            Parameters
            ----------
            query : Any
                Search text or user request to evaluate.
            top_k : Any
                Maximum number of results to return.
            kinds : Any
                Optional result kinds used to narrow the operation.
            under : Any
                Optional path prefix used to scope the operation.

            Returns
            -------
            None
                The function completes through its side effects.
            """
            assert (query, top_k, kinds, under) == ("energy", 2, ["Parameter"], "setup")
            return [Hit()]

    monkeypatch.setattr(
        "ansys.fluent.mcp.solve.catalog.retriever.get_default_api_retriever",
        lambda: Retriever(),
    )
    assert asyncio.run(backend.find_api("energy", top_k=2, kinds=["Parameter"], under="setup")) == [
        {"path": "setup.models.energy", "kind": "Parameter"}
    ]

    class EmptyRetriever:
        async def retrieve(self, *_args, **_kwargs):
            """Retrieve API hits that match the query and filters.

            Parameters
            ----------
            _args : Any
                Positional arguments forwarded to the wrapped call.
            _kwargs : Any
                Keyword arguments forwarded to the wrapped call.

            Returns
            -------
            None
                The function completes through its side effects.
            """
            return []

    monkeypatch.setattr(
        "ansys.fluent.mcp.solve.catalog.retriever.get_default_api_retriever",
        lambda: EmptyRetriever(),
    )
    with pytest.raises(BackendUnavailableError):
        asyncio.run(backend.find_api("none"))


class FakePyFluent:
    def __init__(self):
        """Initialize the FakePyFluent instance.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        self.endpoint = "pyfluent://fake"
        self._mode = "attach"
        self.connected = False
        self.invalidated = 0
        self.closed = False
        self.calls = []

    async def connect(self, **kwargs):
        """Connect to the configured backend or service.

        Parameters
        ----------
        kwargs : Any
            Keyword arguments forwarded to the callable.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        self.calls.append(("connect", kwargs))
        self.connected = kwargs.get("status", "ok") == "ok"
        if not self.connected:
            return ConnectResult(status="error", error_code="failed", backend_kind="pyfluent")
        return ConnectResult(status="ok", backend_kind="pyfluent", endpoint=self.endpoint)

    async def disconnect(self):
        """Close resources for the FakePyFluent object.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        self.calls.append(("disconnect", None))
        self.connected = False

    def is_connected(self):
        """Return whether connected.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        return self.connected

    def close_sync(self):
        """Close backend resources from synchronous code.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        self.closed = True

    def status(self, leaf):
        """Return backend status information.

        Parameters
        ----------
        leaf : Any
            Leaf MCP server instance under test.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        return SessionStatus(
            leaf=leaf,
            connected=self.connected,
            backend="PyFluent",
            backend_kind="pyfluent",
            notes=["base"],
        )

    def invalidate_cache(self):
        """Clear cached backend state.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        self.invalidated += 1

    def invalidate_live_caches(self):
        """Clear cached live backend state.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        self.invalidated += 1

    def invalidate_mesh_cache(self):
        """Clear cached mesh-probe results.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        self.invalidated += 1

    async def list_named_objects(self):
        """List named objects entries.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        return {"bc": ["inlet"]}

    async def find_named_object(self, name):
        """Find named object entries.

        Parameters
        ----------
        name : Any
            Name of the object, module, or setting being processed.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        return [{"name": name}]

    async def get_state(self, paths=None):
        """Return the state.

        Parameters
        ----------
        paths : Any
            Fluent object paths supplied to the operation.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        return {"paths": paths}

    async def get_active_status(self, paths):
        """Return the active status.

        Parameters
        ----------
        paths : Any
            Fluent object paths supplied to the operation.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        return {path: True for path in paths}

    async def get_allowed_values(self, paths):
        """Return the allowed values.

        Parameters
        ----------
        paths : Any
            Fluent object paths supplied to the operation.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        return {path: ["a"] for path in paths}

    async def get_targeted_context(self, **kwargs):
        """Return the targeted context.

        Parameters
        ----------
        kwargs : Any
            Keyword arguments forwarded to the callable.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        return kwargs

    async def get_help(self, path):
        """Return the help.

        Parameters
        ----------
        path : Any
            Filesystem path or API path to process.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        return {"path": path}

    async def solver_status(self):
        """Return solver status information from the backend.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        return {"initialized": True}

    async def mesh_counts(self):
        """Return mesh entity counts.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        return {"cell_count": 1, "face_count": 2, "node_count": 3}

    async def mesh_quality(self):
        """Return mesh quality information from the backend.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        return {"min_orthogonal_quality": 0.5}

    async def mesh_check(self):
        """Run the backend mesh check operation.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        return {"raw": "ok"}

    async def run_code(self, code, *, namespace=None, filename="<mcp>"):
        """Execute Python code through the backend runtime.

        Parameters
        ----------
        code : Any
            Python code or command text to execute or validate.
        namespace : Any
            Namespace used to resolve the backend object or route.
        filename : Any
            File name or path used by the backend operation.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        return RunCodeResult(status="ok", stdout=code, return_value=filename)

    async def validate_code(self, code):
        """Validate code.

        Parameters
        ----------
        code : Any
            Python code or command text to execute or validate.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        return RunCodeResult(status="ok", stdout=code)

    async def screenshot(self, *, view=None):
        """Capture a screenshot from the backend runtime.

        Parameters
        ----------
        view : Any
            Graphics view or camera preset requested by the caller.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        return {"view": view}


def test_solve_composite_delegates_to_pyfluent(monkeypatch):
    """Verify that solve composite delegates to pyfluent.

    Parameters
    ----------
    monkeypatch : Any
        Pytest fixture used to patch environment variables or dependencies.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    created = []

    def factory():
        """Create a test backend or handler instance.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        fake = FakePyFluent()
        created.append(fake)
        return fake

    monkeypatch.setattr(composite, "PyFluentBackend", factory)
    backend = composite.SolveCompositeBackend(label="Solve Test")
    fake = created[0]

    result = asyncio.run(backend.connect(ip="127.0.0.1", port=1234, password="pw"))
    assert result.status == "ok"
    assert result.message == "PyFluent connected (attach)."
    assert fake.calls[0][0] == "connect"
    assert fake.calls[0][1]["ip"] == "127.0.0.1"
    assert backend.endpoint == "pyfluent://fake"
    backend.endpoint = "ignored"
    assert backend.endpoint == "pyfluent://fake"

    status = backend.status("solve")
    assert status.backend == "Solve Test"
    assert status.notes == ["base"]
    assert asyncio.run(backend.list_named_objects()) == {"bc": ["inlet"]}
    assert asyncio.run(backend.find_named_object("inlet")) == [{"name": "inlet"}]
    assert asyncio.run(backend.get_state(["x"])) == {"paths": ["x"]}
    assert asyncio.run(backend.get_active_status(["x"])) == {"x": True}
    assert asyncio.run(backend.get_allowed_values(["x"])) == {"x": ["a"]}
    assert asyncio.run(backend.get_targeted_context(paths_to_check=["x"])) == {
        "paths_to_check": ["x"],
        "named_object_types": None,
        "instance_state_fetch": None,
    }
    assert asyncio.run(backend.get_help("x")) == {"path": "x"}
    assert asyncio.run(backend.solver_status()) == {"initialized": True}
    assert asyncio.run(backend.mesh_counts())["cell_count"] == 1
    assert asyncio.run(backend.mesh_quality())["min_orthogonal_quality"] == 0.5
    assert asyncio.run(backend.mesh_check()) == {"raw": "ok"}
    assert asyncio.run(backend.run_code("print(1)", filename="cell.py")).return_value == "cell.py"
    assert asyncio.run(backend.validate_code("x = 1")).stdout == "x = 1"
    assert asyncio.run(backend.screenshot(view="front")) == {"view": "front"}

    backend.invalidate_cache()
    backend.invalidate_live_caches()
    assert fake.invalidated >= 3
    backend.close_sync()
    assert fake.closed is True
    asyncio.run(backend.disconnect())
    assert fake.connected is False


def test_solve_composite_returns_pyfluent_connect_error(monkeypatch):
    """Verify that solve composite returns pyfluent connect error.

    Parameters
    ----------
    monkeypatch : Any
        Pytest fixture used to patch environment variables or dependencies.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    fake = FakePyFluent()

    async def fail_connect(**_kwargs):
        """Connect to the configured backend or service.

        Parameters
        ----------
        _kwargs : Any
            Keyword arguments forwarded to the wrapped call.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        return ConnectResult(status="error", error_code="failed", backend_kind="pyfluent")

    fake.connect = fail_connect
    monkeypatch.setattr(composite, "PyFluentBackend", lambda: fake)
    backend = composite.SolveCompositeBackend()

    result = asyncio.run(backend.connect())
    assert result.status == "error"
    assert result.error_code == "failed"
