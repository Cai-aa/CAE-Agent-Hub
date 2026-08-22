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

from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest

from ansys.cfx.mcp import CFXMCP
from ansys.cfx.mcp.cfx.backend import CFXBackend
from ansys.cfx.mcp.cfx.sessions.session_manager import SessionManager
from ansys.cfx.mcp.common.backend import Backend
from ansys.cfx.mcp.common.base import FluidsLeafMCP
from ansys.cfx.mcp.common.errors import BackendUnavailable


class _ConnectedBackend(CFXBackend):
    def is_connected(self) -> bool:
        return True


class _MinimalBackend(Backend):
    async def connect(self, **kwargs: object):
        raise NotImplementedError

    def is_connected(self) -> bool:
        return False


def test_cfx_mcp_exposes_compact_tool_surface() -> None:
    leaf = CFXMCP()

    assert set(leaf._exposed) == {
        "session_status",
        "connect",
        "disconnect",
        "cfx_workflow",
        "cfx_model_context",
        "run_code",
        "validate_code",
    }


def test_cfx_mcp_hides_low_level_tools_by_default() -> None:
    hidden_tools = {
        "list_named_objects",
        "find_named_object",
        "select_named_objects",
        "get_help",
        "get_targeted_context",
        "solver_status",
        "summarize_setup",
        "find_api",
        "get_state",
    }

    assert set(CFXMCP()._exposed).isdisjoint(hidden_tools)


def test_cfx_mcp_toolsets_include_exposed_cfx_tools_only() -> None:
    leaf = CFXMCP()
    toolsets = leaf.build_toolsets()
    tools_by_toolset = {toolset["name"]: set(toolset["tools"]) for toolset in toolsets}
    toolset_tools = set().union(*(toolset["tools"] for toolset in toolsets))

    assert tools_by_toolset["connection"] == {"session_status", "connect", "disconnect"}
    assert tools_by_toolset["code-validation"] == {"validate_code"}
    assert tools_by_toolset["cfx-workflow"] == {"cfx_workflow"}
    assert tools_by_toolset["cfx-model-context"] == {"cfx_model_context"}
    assert tools_by_toolset["code-execution"] == {"run_code", "validate_code"}
    assert toolset_tools == set(leaf._exposed)
    assert "api-discovery" not in tools_by_toolset
    assert "named-objects" not in tools_by_toolset
    assert "state-inspection" not in tools_by_toolset
    assert "visualization" not in tools_by_toolset
    assert "error-handling" not in tools_by_toolset
    assert "component-lifecycle" not in tools_by_toolset
    assert "reports" not in tools_by_toolset


def test_cfx_mcp_run_code_description_is_cfx_specific() -> None:
    description_source = inspect.getsource(FluidsLeafMCP._tool_run_code)

    assert "PyCFX" in description_source
    assert "cfx_model_context" in description_source
    assert "solver.settings" not in description_source


@pytest.mark.asyncio
async def test_common_find_api_default_is_dependency_free() -> None:
    with pytest.raises(BackendUnavailable):
        await _MinimalBackend().find_api("pressure")


@pytest.mark.asyncio
async def test_cfx_workflow_status_routes_to_solver_status(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        SessionManager,
        "status",
        staticmethod(
            lambda: {
                "pre": False,
                "solver": True,
                "post": False,
                "solver_input_file": "StaticMixer.def",
                "results_file": "StaticMixer.res",
            }
        ),
    )
    monkeypatch.setattr(
        SessionManager,
        "get_solver",
        staticmethod(lambda: SimpleNamespace(is_running=lambda: False)),
    )

    response = await _ConnectedBackend().cfx_workflow(action="status")

    assert response["status"] == "ok"
    assert response["action"] == "status"
    assert response["result"]["backend_kind"] == "pycfx"
    assert response["result"]["solver_connected"] is True
    assert response["result"]["results_file"] == "StaticMixer.res"


@pytest.mark.asyncio
async def test_cfx_model_context_limits_named_objects(monkeypatch: pytest.MonkeyPatch) -> None:
    async def list_named_objects(self: CFXBackend) -> dict[str, list[str]]:
        return {
            "flow": ["Flow Analysis 1", "Flow Analysis 2", "Flow Analysis 3"],
            "mesh": ["StaticMixer"],
            "user": ["Expr1", "Expr2", "Expr3"],
        }

    monkeypatch.setattr(CFXBackend, "list_named_objects", list_named_objects)

    response = await CFXBackend().cfx_model_context(
        action="list_named_objects",
        max_items=2,
    )

    assert response["status"] == "ok"
    assert response["objects"] == {
        "flow": ["Flow Analysis 1", "Flow Analysis 2", {"_truncated": True, "remaining": 1}],
        "mesh": ["StaticMixer"],
        "_truncated": True,
    }


@pytest.mark.asyncio
async def test_cfx_model_context_api_help_uses_cfx_catalog() -> None:
    response = await CFXBackend().cfx_model_context(
        action="api_help",
        params={"path": "solver.solution.start_run"},
    )

    assert response["status"] == "ok"
    assert response["help"]["path"] == "solver.solution.start_run"
    assert response["help"]["kind"] == "Command"
    assert "Start" in response["help"]["description"]


@pytest.mark.asyncio
async def test_validate_code_allows_cfx_import_name() -> None:
    result = await CFXBackend().validate_code("import ansys.cfx.core\nprint('ok')")

    assert result.status == "ok"


@pytest.mark.asyncio
async def test_run_code_uses_restricted_namespace() -> None:
    result = await CFXBackend().run_code("x = 41\nx + 1")

    assert result.status == "ok"
    assert result.stdout == "42\n"
    assert result.return_value == 42


@pytest.mark.asyncio
async def test_run_code_rejects_forbidden_import() -> None:
    result = await CFXBackend().run_code("import os\nprint(os.getcwd())")

    assert result.status == "error"
    assert result.error_code == "forbidden_import"
    assert "os" in (result.message or "")


@pytest.mark.asyncio
async def test_run_code_blocks_restricted_builtins_at_runtime() -> None:
    result = await CFXBackend().run_code("getattr(__builtins__, 'open')")

    assert result.status == "error"
    assert result.error_code == "forbidden_name"
    assert "__builtins__" in (result.message or "")


def test_collect_domains_and_boundaries_walks_nested_flow_state() -> None:
    from ansys.cfx.mcp.cfx.backend import _collect_domains_and_boundaries

    flow_state = {
        "Flow Analysis 1": {
            "domain": {
                "Default Domain": {
                    "boundary": {
                        "in1": {},
                        "in2": {},
                        "out": {},
                    }
                }
            }
        }
    }
    domains, boundaries = _collect_domains_and_boundaries(flow_state)
    assert domains == ["Default Domain"]
    assert boundaries == ["in1", "in2", "out"]


def test_collect_domains_and_boundaries_tolerates_partial_tree() -> None:
    from ansys.cfx.mcp.cfx.backend import _collect_domains_and_boundaries

    # Missing/partial branches must not raise and must yield empties.
    assert _collect_domains_and_boundaries(None) == ([], [])
    assert _collect_domains_and_boundaries({"Flow Analysis 1": None}) == ([], [])
    assert _collect_domains_and_boundaries(
        {"Flow Analysis 1": {"domain": {"Default Domain": None}}}
    ) == (
        ["Default Domain"],
        [],
    )


@pytest.mark.asyncio
async def test_list_named_objects_surfaces_nested_boundaries(monkeypatch) -> None:
    """``list_named_objects`` exposes domains/boundaries nested in flow."""
    flow_state = {
        "Flow Analysis 1": {
            "domain": {"Default Domain": {"boundary": {"in1": {}, "in2": {}, "out": {}}}}
        }
    }

    class _FakeFlow:
        def keys(self):
            return ["Flow Analysis 1"]

        def get_state(self):
            return flow_state

    class _FakeColl:
        def __init__(self, names):
            self._names = names

        def keys(self):
            return list(self._names)

    class _FakePre:
        raw = SimpleNamespace(
            setup=SimpleNamespace(
                flow=_FakeFlow(),
                mesh=_FakeColl(["StaticMixer"]),
                user=_FakeColl([]),
            )
        )

    monkeypatch.setattr(SessionManager, "get_pre", staticmethod(lambda: _FakePre()))

    result = await CFXBackend().list_named_objects()
    assert result["flow"] == ["Flow Analysis 1"]
    assert result["mesh"] == ["StaticMixer"]
    assert result["domain"] == ["Default Domain"]
    assert result["boundary"] == ["in1", "in2", "out"]


def _make_live_flow_coll():
    """Build a fake live flow collection mirroring a read-in StaticMixer.cfx.

    Crucially ``get_state()`` on the flow collection returns the analysis
    WITHOUT a nested ``domain`` map (as PyCFX does after opening a case),
    while the live ``get_object_names()`` walk exposes the real
    ``Default Domain`` and its boundaries.
    """

    class _NamedColl:
        def __init__(self, children):
            self._children = children

        def get_object_names(self):
            return list(self._children)

        def keys(self):
            return list(self._children)

        def __getitem__(self, name):
            return self._children[name]

    class _Boundary:
        pass

    default_domain = SimpleNamespace(
        boundary=_NamedColl({"in1": _Boundary(), "in2": _Boundary(), "out": _Boundary()})
    )

    class _FlowColl:
        # State-only payload: domain map intentionally absent.
        _state = {"Flow Analysis 1": {"solver_control": {}}}

        def get_state(self):
            return {k: dict(v) for k, v in self._state.items()}

        def get_object_names(self):
            return ["Flow Analysis 1"]

        def keys(self):
            return ["Flow Analysis 1"]

        def __getitem__(self, name):
            return SimpleNamespace(domain=_NamedColl({"Default Domain": default_domain}))

    return _FlowColl()


def test_walk_live_domains_and_boundaries_reads_loaded_case() -> None:
    from ansys.cfx.mcp.cfx.backend import _walk_live_domains_and_boundaries

    domains, boundaries = _walk_live_domains_and_boundaries(_make_live_flow_coll())
    assert domains == ["Default Domain"]
    assert boundaries == ["in1", "in2", "out"]


def test_walk_live_domains_and_boundaries_tolerates_none() -> None:
    from ansys.cfx.mcp.cfx.backend import _walk_live_domains_and_boundaries

    assert _walk_live_domains_and_boundaries(None) == ([], [])


def test_augment_flow_state_fills_missing_domain_tree() -> None:
    from ansys.cfx.mcp.cfx.backend import _augment_flow_state_with_live_tree

    flow_coll = _make_live_flow_coll()
    flow_state = flow_coll.get_state()
    # Sanity: the raw state lacks the domain tree.
    assert "domain" not in flow_state["Flow Analysis 1"]

    augmented = _augment_flow_state_with_live_tree(flow_state, flow_coll)
    domain_map = augmented["Flow Analysis 1"]["domain"]
    assert list(domain_map) == ["Default Domain"]
    assert list(domain_map["Default Domain"]["boundary"]) == ["in1", "in2", "out"]


def test_augment_flow_state_preserves_existing_domain_tree() -> None:
    from ansys.cfx.mcp.cfx.backend import _augment_flow_state_with_live_tree

    existing = {"Flow Analysis 1": {"domain": {"Already": {"boundary": {"keep": {}}}}}}
    augmented = _augment_flow_state_with_live_tree(existing, _make_live_flow_coll())
    # Existing domain tree must not be overwritten by the live walk.
    assert augmented["Flow Analysis 1"]["domain"] == {"Already": {"boundary": {"keep": {}}}}


@pytest.mark.asyncio
async def test_list_named_objects_falls_back_to_live_walk(monkeypatch) -> None:
    """When ``get_state()`` omits the domain map, walk the live tree."""

    class _FakeColl:
        def __init__(self, names):
            self._names = names

        def keys(self):
            return list(self._names)

    flow_coll = _make_live_flow_coll()

    class _FakePre:
        raw = SimpleNamespace(
            setup=SimpleNamespace(
                flow=flow_coll,
                mesh=_FakeColl(["StaticMixer"]),
                user=_FakeColl([]),
            )
        )

    monkeypatch.setattr(SessionManager, "get_pre", staticmethod(lambda: _FakePre()))

    result = await CFXBackend().list_named_objects()
    assert result["flow"] == ["Flow Analysis 1"]
    assert result["domain"] == ["Default Domain"]
    assert result["boundary"] == ["in1", "in2", "out"]


@pytest.mark.asyncio
async def test_get_state_flow_augments_with_live_domain_tree(monkeypatch) -> None:
    """``get_state(['flow'])`` carries the domain tree for a read-in case."""

    flow_coll = _make_live_flow_coll()

    class _FakePre:
        raw = SimpleNamespace(setup=SimpleNamespace(flow=flow_coll))

    monkeypatch.setattr(SessionManager, "get_pre", staticmethod(lambda: _FakePre()))

    result = await CFXBackend().get_state(["flow"])
    domain_map = result["flow"]["Flow Analysis 1"]["domain"]
    assert list(domain_map) == ["Default Domain"]
    assert list(domain_map["Default Domain"]["boundary"]) == ["in1", "in2", "out"]


@pytest.mark.asyncio
async def test_connect_mode_rejects_invalid_value() -> None:
    result = await CFXBackend().connect(mode="bogus")

    assert result.status == "error"
    assert result.error_code == "connect_failed"
    assert "Invalid mode" in (result.message or "")


@pytest.mark.asyncio
async def test_connect_mode_attach_requires_attach_params() -> None:
    result = await CFXBackend().connect(mode="attach")

    assert result.status == "error"
    assert result.error_code == "connect_failed"
    assert "requires attach parameters" in (result.message or "")


@pytest.mark.asyncio
async def test_connect_mode_launch_rejects_attach_params() -> None:
    result = await CFXBackend().connect(mode="launch", ip="127.0.0.1", port=12345)

    assert result.status == "error"
    assert result.error_code == "connect_failed"
    assert "cannot be combined with attach parameters" in (result.message or "")


@pytest.mark.asyncio
async def test_connect_mode_auto_infers_launch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default ``mode='auto'`` preserves the prior inferred-launch behaviour."""
    calls: dict[str, bool] = {}

    monkeypatch.setattr(
        SessionManager,
        "launch_pre",
        staticmethod(lambda **_kwargs: calls.setdefault("launch_pre", True)),
    )
    monkeypatch.setattr(
        SessionManager,
        "attach_pre",
        staticmethod(lambda **_kwargs: calls.setdefault("attach_pre", True)),
    )

    result = await CFXBackend().connect()

    assert result.status == "ok"
    assert result.endpoint == "local"
    assert calls == {"launch_pre": True}


@pytest.mark.asyncio
async def test_connect_mode_auto_infers_attach(monkeypatch: pytest.MonkeyPatch) -> None:
    """Supplying ip/port still attaches when ``mode`` is left at the default."""
    calls: dict[str, bool] = {}

    monkeypatch.setattr(
        SessionManager,
        "launch_pre",
        staticmethod(lambda **_kwargs: calls.setdefault("launch_pre", True)),
    )
    monkeypatch.setattr(
        SessionManager,
        "attach_pre",
        staticmethod(lambda **_kwargs: calls.setdefault("attach_pre", True)),
    )

    result = await CFXBackend().connect(ip="127.0.0.1", port=12345)

    assert result.status == "ok"
    assert result.endpoint == "127.0.0.1:12345"
    assert calls == {"attach_pre": True}


@pytest.mark.asyncio
async def test_connect_mode_launch_explicit_launches(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, bool] = {}

    monkeypatch.setattr(
        SessionManager,
        "launch_pre",
        staticmethod(lambda **_kwargs: calls.setdefault("launch_pre", True)),
    )

    result = await CFXBackend().connect(mode="launch")

    assert result.status == "ok"
    assert calls == {"launch_pre": True}
