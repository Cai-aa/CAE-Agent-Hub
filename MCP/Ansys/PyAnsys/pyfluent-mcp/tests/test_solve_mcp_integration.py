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
from pathlib import Path
import re

from ansys.fluent.mcp.common.models import (
    ConnectResult,
    RunCodeResult,
    SessionStatus,
)
from ansys.fluent.mcp.solve import mcp as solve_mcp


class IntegrationBackend:
    kind = "pyfluent"
    label = "integration"
    endpoint = "local://integration"

    def __init__(self):
        """Initialize the IntegrationBackend instance.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        self.connected = True
        self.field_scopes = []
        self.connect_kwargs = []
        self.invalidated = 0
        self.lifecycle_actions = []
        self.run_code_snippets = []

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
        self.connected = True
        self.connect_kwargs.append(kwargs)
        return ConnectResult(status="ok", backend_kind="pyfluent", endpoint=self.endpoint)

    async def disconnect(self):
        """Close resources for the IntegrationBackend object.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        self.connected = False

    def is_connected(self):
        """Return whether connected.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        return self.connected

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
            backend=self.label,
            backend_kind=self.kind,
            endpoint=self.endpoint,
        )

    def invalidate_live_caches(self):
        """Clear cached live backend state.

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
        return {
            "setup.boundary_conditions.wall": ["wall-1", "wall-2", "wall-2-shadow"],
            "setup.boundary_conditions.velocity_inlet": ["inlet-a", "backup-inlet"],
        }

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
        mapping = await self.list_named_objects()
        target = name.strip().lower()
        return [
            {"collection_path": collection, "name": item, "exact": item.lower() == target}
            for collection, names in mapping.items()
            for item in names
            if target in item.lower()
        ]

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
        return {"paths": paths or [], "state": "ready"}

    async def get_targeted_context(
        self, *, paths_to_check, named_object_types=None, instance_state_fetch=None
    ):
        """Return the targeted context.

        Parameters
        ----------
        paths_to_check : Any
            Fluent object paths to validate or inspect.
        named_object_types : Any
            Named-object families that should be considered during lookup.
        instance_state_fetch : Any
            Whether named-object instance state should be fetched.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        return {
            "paths_to_check": paths_to_check,
            "named_object_types": named_object_types,
            "instance_state_fetch": instance_state_fetch,
        }

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
        return {"path": path, "docstring": "help text", "children": ["child"]}

    async def solver_status(self):
        """Return solver status information from the backend.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        return {"initialized": True, "iterations": 12}

    async def find_api(self, query, *, top_k=10, kinds=None, under=None):
        """Find api entries.

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
        return [
            {
                "path": f"{under or 'setup'}.temperature",
                "kind": (kinds or ["Parameter"])[0],
                "score": 0.9,
                "docstring": f"Temperature result for {query}\nMore detail",
            }
        ][:top_k]

    async def run_code(self, code, **kwargs):
        """Execute Python code through the backend runtime.

        Parameters
        ----------
        code : Any
            Python code or command text to execute or validate.
        kwargs : Any
            Keyword arguments forwarded to the callable.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        self.run_code_snippets.append(code)
        summary_match = re.search(r"file_name='([^']+)'", code)
        if summary_match:
            with Path(summary_match.group(1)).open("w", encoding="utf-8") as output:
                output.write("Summary text")
        if "list_simulation_reports" in code:
            return RunCodeResult(status="ok", stdout="listed", return_value=["default-report"])
        return RunCodeResult(status="ok", stdout="ran", return_value={"ok": True})

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
        return RunCodeResult(status="ok", stdout="valid", return_value={"code": code})

    async def activate_component(self):
        """Exercise the activate component test helper.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        self.lifecycle_actions.append("activate")
        return {"status": "ok", "action": "activate"}

    async def deactivate_component(self):
        """Exercise the deactivate component test helper.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        self.lifecycle_actions.append("deactivate")
        return {"status": "ok", "action": "deactivate"}

    async def update_component(self):
        """Update component.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        self.lifecycle_actions.append("update")
        return {"status": "ok", "action": "update"}

    async def refresh_component(self):
        """Exercise the refresh component test helper.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        self.lifecycle_actions.append("refresh")
        return {"status": "ok", "action": "refresh"}

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
        return {"format": "png", "data": "abc123", "view": view}

    async def mesh_counts(self):
        """Return mesh entity counts.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        return {"cell_count": 42, "face_count": 84, "node_count": 126}

    async def mesh_quality(self):
        """Return mesh quality information from the backend.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        return {"min_orthogonal_quality": 0.25, "max_skewness": 0.9}

    async def mesh_check(self):
        """Run the backend mesh check operation.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        return {"warnings": []}

    async def list_fields(self, *, scope):
        """List fields entries.

        Parameters
        ----------
        scope : Any
            Scope to supply to the function.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        self.field_scopes.append(scope)
        return {"fields": ["pressure", "velocity"], "scope": scope}


def _structured(result):
    """Create a structured test response.

    Parameters
    ----------
    result : Any
        Result object or payload to process.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    payload = getattr(result, "structured_content", None) or result.structuredContent
    if isinstance(payload, dict) and set(payload) == {"result"}:
        return payload["result"]
    return payload


def _make_server(monkeypatch, backend, expose_tools=("session_status",)):
    """Exercise the make server test helper.

    Parameters
    ----------
    monkeypatch : Any
        Pytest fixture used to patch environment variables or dependencies.
    backend : Any
        Backend instance used to perform the operation.
    expose_tools : Any
        Whether MCP tools should be registered on the server.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    monkeypatch.setattr(solve_mcp, "SolveCompositeBackend", lambda: backend)
    monkeypatch.setattr(solve_mcp, "_discover_external_solve_backends", lambda: {})
    return solve_mcp.SolveMCP(expose_tools=expose_tools, default_backend_kind="pyfluent")


def test_solve_mcp_registers_and_calls_domain_tools_through_runtime(monkeypatch):
    """Verify that solve mcp registers and calls domain tools through runtime.

    Parameters
    ----------
    monkeypatch : Any
        Pytest fixture used to patch environment variables or dependencies.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    backend = IntegrationBackend()

    async def scenario():
        """Run the test scenario helper.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        server = _make_server(monkeypatch, backend)

        tools = await server.list_tools()
        tool_names = {tool.name for tool in tools}

        assert "session_status" in tool_names
        assert {"mesh_quality", "list_fields", "compare_files"}.issubset(tool_names)

        mesh = _structured(await server.call_tool("mesh_quality", {"include_check": True}))
        fields = _structured(await server.call_tool("list_fields", {"scope": " cell "}))

        assert mesh == {
            "connected": True,
            "cell_count": 42,
            "face_count": 84,
            "node_count": 126,
            "quality": {"min_orthogonal_quality": 0.25, "max_skewness": 0.9},
            "check": {"warnings": []},
        }
        assert fields == {"connected": True, "fields": ["pressure", "velocity"], "scope": "cell"}
        assert backend.field_scopes == ["cell"]

    asyncio.run(scenario())


def test_solve_mcp_runtime_covers_general_tool_surface(monkeypatch):
    """Verify that solve mcp runtime covers general tool surface.

    Parameters
    ----------
    monkeypatch : Any
        Pytest fixture used to patch environment variables or dependencies.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    backend = IntegrationBackend()

    async def observer(**kwargs):
        """Record an observer notification for the test.

        Parameters
        ----------
        kwargs : Any
            Keyword arguments forwarded to the callable.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        observer.calls.append(kwargs)

    observer.calls = []

    async def scenario():
        """Run the test scenario helper.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        server = _make_server(
            monkeypatch,
            backend,
            expose_tools=(
                "session_status",
                "connect",
                "disconnect",
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
            ),
        )
        server.register_run_code_observer(observer)

        assert _structured(await server.call_tool("session_status", {}))["connected"] is True
        assert _structured(await server.call_tool("disconnect", {})) == {"status": "ok"}
        assert _structured(await server.call_tool("session_status", {}))["connected"] is False
        connect = _structured(
            await server.call_tool("connect", {"connect_kwargs": {"host": "127.0.0.1"}})
        )
        assert connect["status"] == "ok"
        assert backend.connect_kwargs == [{"host": "127.0.0.1"}]

        meshing_connect = _structured(
            await server.call_tool("connect", {"connect_kwargs": {"mode": "meshing"}})
        )
        assert meshing_connect["status"] == "ok"
        assert backend.connect_kwargs[-1] == {"mode": "meshing"}

        listed = _structured(
            await server.call_tool("list_named_objects", {"limit": 1, "offset": 1})
        )
        assert listed["setup.boundary_conditions.wall"] == ["wall-2"]
        assert listed["_pagination"]["truncated"] is True
        found = _structured(await server.call_tool("find_named_object", {"name": "inlet"}))
        assert {item["name"] for item in found} == {"inlet-a", "backup-inlet"}
        selected = _structured(
            await server.call_tool(
                "select_named_objects",
                {
                    "collection": "setup.boundary_conditions.wall",
                    "pattern": "wall-*",
                    "include_shadows": False,
                    "exclude": ["wall-2"],
                },
            )
        )
        assert selected["names"] == ["wall-1"]

        assert _structured(
            await server.call_tool("get_state", {"paths": ["setup.wall"], "key": "outer"})
        ) == {
            "paths": ["setup.wall[outer]"],
            "state": "ready",
        }
        assert _structured(
            await server.call_tool("get_targeted_context", {"paths_to_check": ["setup"]})
        ) == {
            "paths_to_check": ["setup"],
            "named_object_types": [],
            "instance_state_fetch": [],
        }
        assert _structured(await server.call_tool("get_help", {"path": "setup.wall"}))[
            "children"
        ] == ["child"]
        assert _structured(await server.call_tool("solver_status", {}))["iterations"] == 12
        compact_hits = _structured(
            await server.call_tool("find_api", {"query": "temperature", "compact": True})
        )
        assert compact_hits == [
            {
                "path": "setup.temperature",
                "kind": "Parameter",
                "score": 0.9,
                "summary": "Temperature result for temperature",
            }
        ]

        validated = _structured(await server.call_tool("validate_code", {"code": "print('x')"}))
        assert validated["stdout"] == "valid"
        executed = _structured(await server.call_tool("run_code", {"code": "print('x')"}))
        assert executed["stdout"] == "ran"
        assert backend.invalidated == 1
        assert observer.calls[0]["code"] == "print('x')"
        assert observer.calls[0]["error"] is None

        assert _structured(await server.call_tool("screenshot", {"view": "front"})) == {
            "format": "png",
            "data": "abc123",
            "view": "front",
        }
        assert (
            _structured(await server.call_tool("manage_fluent", {"action": "activate"}))["action"]
            == "activate"
        )
        assert (
            _structured(await server.call_tool("manage_fluent", {"action": "refresh"}))["action"]
            == "refresh"
        )
        assert backend.lifecycle_actions == ["activate", "refresh"]
        assert _structured(await server.call_tool("summarize_setup", {})) == {
            "summary": "Summary text"
        }
        reports = _structured(await server.call_tool("simulation_report", {"action": "list"}))
        assert reports == {"reports": ["default-report"], "stdout": "listed"}
        invalid_report = _structured(await server.call_tool("simulation_report", {"action": "bad"}))
        assert invalid_report["error"] == "invalid action 'bad'"

    asyncio.run(scenario())
