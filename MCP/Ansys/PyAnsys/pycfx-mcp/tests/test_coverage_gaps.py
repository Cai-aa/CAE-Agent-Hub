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

import io
import sys
from types import ModuleType, SimpleNamespace

import pytest

from ansys.cfx.mcp import cli
from ansys.cfx.mcp.cfx import CFXMCP, dependencies
from ansys.cfx.mcp.cfx.backend import CFXBackend, _build_safe_builtins
from ansys.cfx.mcp.cfx.sessions.post_session import PostSession
from ansys.cfx.mcp.cfx.sessions.pre_session import PreSession
from ansys.cfx.mcp.cfx.sessions.session_manager import SessionManager
from ansys.cfx.mcp.cfx.sessions.solver_session import SolverSession
from ansys.cfx.mcp.cfx.worker import main as worker_main
from ansys.cfx.mcp.common.backend import Backend
from ansys.cfx.mcp.common.base import select_named_objects_from_mapping
from ansys.cfx.mcp.common.errors import (
    BackendUnavailable,
    InvalidArguments,
    typed_guard,
)
from ansys.cfx.mcp.common.models import ConnectResult, RunCodeResult
from ansys.cfx.mcp.common.validation import sanitize_python_code, validate_python_source


class FakeBackend(Backend):
    kind = "pycfx"
    label = "Fake CFX"

    def __init__(self, *, connected: bool = True) -> None:
        super().__init__()
        self.connected = connected

    async def connect(self, **kwargs: object) -> ConnectResult:
        self.connected = True
        return ConnectResult(
            status="ok", backend_kind=self.kind, endpoint=str(kwargs.get("endpoint", "local"))
        )

    def is_connected(self) -> bool:
        return self.connected

    async def list_named_objects(self) -> dict[str, list[str]]:
        return {"wall": ["outer", "inner-shadow"], "inlet": ["inlet-1"]}

    async def get_state(self, paths: list[str] | None = None) -> dict[str, object]:
        return {path: {"value": path} for path in (paths or ["flow"])}

    async def find_api(self, query: str, *, top_k: int = 10, kinds=None, under=None):
        return [
            {"path": f"api.{query}", "kind": "Command", "score": 1.0, "docstring": "Run command"}
        ][:top_k]

    async def get_targeted_context(
        self, *, paths_to_check, named_object_types=None, instance_state_fetch=None
    ):
        return {"paths": paths_to_check, "named": named_object_types, "state": instance_state_fetch}

    async def get_help(self, path: str) -> dict[str, object]:
        return {"path": path, "description": "help"}

    async def solver_status(self) -> dict[str, object]:
        return {"backend_kind": self.kind, "connected": self.connected}

    async def run_code(self, code: str, **kwargs: object) -> RunCodeResult:
        return RunCodeResult(status="ok", stdout=code)

    async def screenshot(self, *, view: str | None = None) -> dict[str, object]:
        return {"format": "png", "view": view}

    async def activate_component(self) -> dict[str, object]:
        return {"status": "activated"}

    async def deactivate_component(self) -> dict[str, object]:
        return {"status": "deactivated"}

    async def update_component(self) -> dict[str, object]:
        return {"status": "updated"}

    async def refresh_component(self) -> dict[str, object]:
        return {"status": "refreshed"}

    async def error_remediation(self, remediation_request: str, *, context=None):
        return {"status": "ok", "markdown": remediation_request, "context": context}

    async def cfx_workflow(self, *, action: str, params: dict[str, object] | None = None):
        return {"status": "ok", "action": action, "params": params or {}}

    async def cfx_model_context(
        self,
        *,
        action: str = "summary",
        params: dict[str, object] | None = None,
        max_items: int = 20,
    ):
        return {"status": "ok", "action": action, "params": params or {}, "max_items": max_items}


def patch_pycfx_core(monkeypatch: pytest.MonkeyPatch, core_module: ModuleType) -> None:
    monkeypatch.setitem(sys.modules, "ansys.cfx.core", core_module)
    ansys_cfx = sys.modules.get("ansys.cfx")
    if ansys_cfx is not None:
        monkeypatch.setattr(ansys_cfx, "core", core_module, raising=False)


def reset_session_manager() -> None:
    SessionManager._pre = None
    SessionManager._solver = None
    SessionManager._post = None
    SessionManager._solver_input_file = None
    SessionManager._results_file = None


def test_cli_parser_defaults_and_http_run() -> None:
    args = cli._argparser().parse_args([])
    assert args.transport == "stdio"
    assert args.host == "127.0.0.1"
    assert args.port == 0

    server = SimpleNamespace(calls=[])
    server.run = lambda **kwargs: server.calls.append(kwargs)

    cli._run(server, cli._argparser().parse_args(["--transport", "http", "--port", "9000"]))

    assert server.calls == [{"transport": "http", "host": "127.0.0.1", "port": 9000}]


def test_cli_build_server_rejects_unknown_backend() -> None:
    args = cli._argparser().parse_args(["--backend", "other"])

    with pytest.raises(SystemExit, match="unknown backend kind"):
        cli._build_server(args)


@pytest.mark.parametrize(
    ("kwargs", "missing"),
    [
        ({"intent": "set inlet boundary"}, ["session:cfx_pre"]),
        ({"intent": "start solver run"}, ["artifact:def_file"]),
        ({"recipe_name": "cfx_post_contour_create"}, ["artifact:res_file", "session:cfx_post"]),
    ],
)
def test_prerequisite_checks_report_missing_context(
    kwargs: dict[str, object], missing: list[str]
) -> None:
    check = dependencies.check_cfx_prerequisites(**kwargs)

    assert check["ready"] is False
    assert check["missing_ids"] == missing
    assert dependencies.primary_clarification(check)["id"] in {
        "start_cfx_pre",
        "provide_cfx_def_file",
        "start_cfx_post",
    }


def test_prerequisite_checks_accept_existing_artifacts_and_sessions() -> None:
    check = dependencies.check_cfx_prerequisites(
        intent="postprocess contour and start solver run",
        context={"solver_input_file": "case.def"},
        status={"post": True, "results_file": "case.res"},
    )

    assert check == {"ready": True, "missing_ids": [], "clarifications": []}
    assert dependencies.primary_clarification({"clarifications": []}) is None


def test_validate_python_source_strict_rejects_imports_names_and_tui() -> None:
    assert validate_python_source("import math\nvalue = math.sqrt(4)", strict=True).status == "ok"

    forbidden_import = validate_python_source("import pathlib", strict=True)
    assert forbidden_import.status == "error"
    assert forbidden_import.error_code == "forbidden_import"

    forbidden_name = validate_python_source("missing_name + 1", strict=True)
    assert forbidden_name.status == "error"
    assert forbidden_name.error_code == "forbidden_name"

    forbidden_tui = validate_python_source("solver.tui.file.read_case('x.cas')", strict=True)
    assert forbidden_tui.status == "error"
    assert forbidden_tui.error_code == "forbidden_call"


def test_validate_python_source_handles_syntax_empty_and_cache() -> None:
    empty = validate_python_source("")
    assert empty.error_code == "invalid_arguments"

    syntax = validate_python_source("for")
    assert syntax.error_code == "syntax_error"

    first = validate_python_source("x = 1\nx + 1", strict=True)
    second = validate_python_source("x = 1\nx + 1", strict=True)
    assert first is second


def test_validate_python_source_strict_allows_common_binding_forms() -> None:
    code = """
from math import sqrt as root

total = 0
total += 1
label: str = "ok"

def combine(first, *rest, named=None, **extra):
    return first + len(rest) + len(extra)

class Marker:
    pass

for index, (name, *values) in enumerate([("a", 1, 2)]):
    total += index + len(name) + len(values)

with session as current:
    total += 1

scale = lambda value=1, *items, key=None, **kwargs: value + len(items) + len(kwargs)
if (assigned := root(4)):
    total += int(assigned)
try:
    raise ValueError("x")
except ValueError as exc:
    message = str(exc)
__return__ = combine(total) + scale()
"""
    result = validate_python_source(
        code,
        strict=True,
        extra_allowed_names={"__return__", "current"},
    )

    assert result.status == "ok"


def test_validate_python_source_forbidden_call_edge_cases() -> None:
    assert validate_python_source("eval('1')").error_code == "forbidden_call"
    assert validate_python_source("getattr(obj, '__globals__')").error_code == "forbidden_call"
    assert validate_python_source("obj.__subclasses__()").error_code == "forbidden_call"
    assert validate_python_source("getattr(solver, 'tui')").error_code == "forbidden_call"
    assert (
        validate_python_source("danger()", forbidden_calls={"danger"}).error_code
        == "forbidden_call"
    )


def test_sanitize_python_code_replaces_only_name_tokens() -> None:
    sanitized, fixes = sanitize_python_code(
        "flag = true\ntext = 'false null'\n# false\nvalue = null"
    )

    assert sanitized == "flag = True\ntext = 'false null'\n# false\nvalue = None"
    assert fixes == ["line 1: true -> True", "line 4: null -> None"]
    assert sanitize_python_code("unterminated = (")[1] == []
    assert sanitize_python_code("value = True") == ("value = True", [])
    assert sanitize_python_code("   ") == ("   ", [])


def test_safe_builtins_allow_safe_imports_only() -> None:
    safe_import = _build_safe_builtins()["__import__"]

    assert safe_import("math").sqrt(9) == 3
    with pytest.raises(ImportError, match="not permitted"):
        safe_import("os")
    with pytest.raises(ImportError, match="relative imports"):
        safe_import("math", level=1)


@pytest.mark.asyncio
async def test_backend_defaults_find_and_cache_behavior() -> None:
    backend = FakeBackend()
    backend._cache_put("answer", 42)
    assert backend._cache_get("answer", ttl=60) == 42
    assert backend.status("cfx").connected is True

    assert await backend.get_named_object_names("missing") == []
    with pytest.raises(BackendUnavailable):
        await backend.mesh_counts()

    backend.invalidate_live_caches()
    assert backend._cache_get("answer", ttl=60) is None


@pytest.mark.asyncio
async def test_backend_find_named_object_literal_and_pattern_matching() -> None:
    backend = FakeBackend()

    literal = await backend.find_named_object("outer")
    pattern = await backend.find_named_object("*shadow|inlet-*")

    assert literal == [{"collection_path": "wall", "name": "outer", "exact": True}]
    assert {match["name"] for match in pattern} == {"inner-shadow", "inlet-1"}
    assert all(match["pattern_source"] == "*shadow|inlet-*" for match in pattern)


def test_select_named_objects_from_mapping_filters_patterns_and_collection_aliases() -> None:
    result = select_named_objects_from_mapping(
        {"setup/boundary-conditions/wall": ["outer-wall", "inner-wall-shadow", "inlet"]},
        collection="setup.boundary_conditions.wall",
        pattern="*wall*",
        include_shadows=False,
        exclude=["inner*"],
    )

    assert result["names"] == ["outer-wall"]
    assert result["count"] == 1

    missing = select_named_objects_from_mapping({"flow": []}, collection="mesh")
    assert missing["available_collections"] == ["flow"]


@pytest.mark.asyncio
async def test_cfx_backend_catalog_context_and_workflow_helpers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_session_manager()
    backend = CFXBackend()
    hits = await backend.find_api("start solver run", top_k=2)
    assert {hit["path"] for hit in hits} >= {"Solver.from_install", "solver.solution.start_run"}

    assert await backend.find_api("", top_k=2) == []
    assert await backend.get_allowed_values(["domain.fluid_models.heat_transfer_model.option"]) == {
        "domain.fluid_models.heat_transfer_model.option": [
            "None",
            "Isothermal",
            "Thermal Energy",
            "Total Energy",
        ]
    }
    assert await backend.get_active_status(["pre.setup.flow"]) == {"pre.setup.flow": False}

    help_payload = await backend.get_help("solver.solution.start_run")
    assert help_payload["kind"] == "Command"
    assert "Start" in help_payload["description"]

    async def list_named_objects(self: CFXBackend) -> dict[str, list[str]]:
        return {"flow": ["Flow 1"], "mesh": []}

    monkeypatch.setattr(CFXBackend, "list_named_objects", list_named_objects)
    context = await backend.get_targeted_context(
        paths_to_check=["solver.solution.start_run"],
        named_object_types=["flow"],
        instance_state_fetch=["flow"],
    )
    assert context["named_objects"] == {"flow": ["Flow 1"]}
    assert context["help"]["solver.solution.start_run"]["kind"] == "Command"


@pytest.mark.asyncio
async def test_cfx_backend_workflow_branches_with_fake_sessions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_session_manager()
    backend = CFXBackend()
    calls: list[tuple[str, object]] = []
    fake_pre = SimpleNamespace(
        import_mesh=lambda path: calls.append(("import", path)),
        write_solver_input=lambda path: calls.append(("write", path)),
    )
    fake_solver = SimpleNamespace(
        wait_for_run=lambda interval, timeout: calls.append(("wait", (interval, timeout))),
        get_results_file_name=lambda: "case.res",
        is_running=lambda: False,
    )
    monkeypatch.setattr(SessionManager, "get_pre", staticmethod(lambda: fake_pre))
    monkeypatch.setattr(SessionManager, "get_solver", staticmethod(lambda: fake_solver))
    monkeypatch.setattr(
        SessionManager, "set_results_file", staticmethod(lambda value: calls.append(("res", value)))
    )
    monkeypatch.setattr(
        SessionManager,
        "status",
        staticmethod(
            lambda: {"pre": True, "solver": True, "post": False, "solver_input_file": "case.def"}
        ),
    )

    assert (await backend.cfx_workflow(action="import_mesh", params={"mesh_file": "mesh.msh"}))[
        "status"
    ] == "ok"
    assert (await backend.cfx_workflow(action="write_def", params={"path": "case.def"}))[
        "status"
    ] == "ok"
    waited = await backend.cfx_workflow(action="wait_solver", params={"interval": 1, "timeout": 2})

    assert waited["results_file"] == "case.res"
    assert calls == [
        ("import", "mesh.msh"),
        ("write", "case.def"),
        ("wait", (1, 2)),
        ("res", "case.res"),
    ]
    assert (await backend.cfx_workflow(action="unknown"))["allowed_actions"]


def test_cfx_backend_live_path_resolution_and_python_sanitizers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_session_manager()
    backend = CFXBackend()
    raw = SimpleNamespace(setup={"flow": {"Flow 1": {"domain": {"Default Domain": "domain"}}}})
    monkeypatch.setattr(SessionManager, "get_pre", staticmethod(lambda: SimpleNamespace(raw=raw)))

    assert (
        backend._resolve_live_path("pre.setup.flow['Flow 1'].domain['Default Domain']") == "domain"
    )
    assert backend._describe_live_node({"b": 2, "a": 1})["child_names"] == ["a", "b"]
    assert backend._coerce_allowed_values_payload([{"name": "A"}, {"value": "B"}, "C"]) == [
        "A",
        "B",
        "C",
    ]
    assert backend._get_static_allowed_values("domain.fluid_definition.Water.option") == [
        "Material Library",
        "User Material",
    ]

    code = (
        'pre.setup.flow["Flow Analysis 1"].domain["Default Domain"].fluid_definition.Water.option = "Material Library"\n'  # noqa: E501
        'pre.setup.flow["Flow Analysis 1"].domain["Default Domain"].fluid_definition.Water.material = "Water"'  # noqa: E501
    )
    sanitized = backend._sanitize_cfx_python_code(code, context={"fluid_name": "Water"})
    assert ".fluid_definition.Water" not in sanitized
    assert '.fluid_definition["Water"].material' in sanitized

    material_only = 'domain.fluid_definition["Water"].material = "Water"'
    assert backend._ensure_fluid_definition_option_line(
        material_only,
        fluid_definition_name="Water",
    ).splitlines() == [
        'domain.fluid_definition["Water"].option = "Material Library"',
        'domain.fluid_definition["Water"].material = "Water"',
    ]


@pytest.mark.asyncio
async def test_cfx_mcp_tool_closures_call_backend_and_validate_inputs() -> None:
    backend = FakeBackend()
    leaf = CFXMCP(
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
            "error_remediation",
            "cfx_workflow",
            "cfx_model_context",
        )
    )
    leaf._backends = {"pycfx": backend}
    leaf._active_kind = "pycfx"

    async def call_tool(tool_name: str, **kwargs: object):
        tool = await leaf.get_tool(tool_name)
        return await tool.fn(**kwargs)

    assert (await call_tool("session_status")).connected is True
    assert (await call_tool("connect", backend_kind="missing")).error_code == "invalid_arguments"
    assert (await call_tool("list_named_objects", limit=1))["_pagination"]["truncated"] is True
    assert (await call_tool("list_named_objects", limit=0)).error_code == "invalid_arguments"
    assert (await call_tool("find_named_object", name="outer"))[0]["name"] == "outer"
    assert (
        await call_tool(
            "select_named_objects", collection="wall", pattern="*", include_shadows=False
        )
    )["names"] == ["outer"]
    assert (await call_tool("find_api", query="start", compact=True))[0]["summary"] == "Run command"
    assert (await call_tool("get_state", paths=["flow"], key="Flow 1")).get("flow[Flow 1]")
    assert (
        await call_tool("get_state", paths=["flow"], key="bad]key")
    ).error_code == "invalid_arguments"
    assert (await call_tool("get_targeted_context", paths_to_check=["a"]))["paths"] == ["a"]
    assert (await call_tool("get_help", path="api.path"))["path"] == "api.path"
    assert (await call_tool("solver_status"))["backend_kind"] == "pycfx"
    assert (await call_tool("run_code", code="print(1)")).stdout == "print(1)"
    assert (await call_tool("run_code", code=" ")).error_code == "invalid_arguments"
    assert (await call_tool("validate_code", code="x = 1")).status == "ok"
    assert (await call_tool("screenshot", view="front"))["view"] == "front"
    assert (await call_tool("manage_cfx", action="activate"))["status"] == "activated"
    assert (await call_tool("manage_cfx", action="bad")).error_code == "invalid_arguments"
    assert (await call_tool("error_remediation", remediation_request="fix", context={"x": 1}))[
        "markdown"
    ] == "fix"
    assert (
        await call_tool("error_remediation", remediation_request=" ")
    ).error_code == "invalid_arguments"
    assert (await call_tool("cfx_workflow", action="status"))["status"] in {"ok", "error"}
    assert (await call_tool("cfx_model_context", action="find_api", params={"query": "run"}))[
        "status"
    ] == "ok"


def test_pre_and_post_session_wrappers_delegate_to_raw_session() -> None:
    raw_pre = SimpleNamespace(file=SimpleNamespace(calls=[]), exited=False)
    raw_pre.file.import_mesh = lambda file_name: raw_pre.file.calls.append(("import", file_name))
    raw_pre.file.open_case = lambda file_name: raw_pre.file.calls.append(("open_case", file_name))
    raw_pre.file.write_solver_input = lambda file_name: raw_pre.file.calls.append(
        ("write", file_name)
    )
    raw_pre.exit = lambda: setattr(raw_pre, "exited", True)
    pre_session = PreSession(raw_pre, mode="attach")

    pre_session.import_mesh("mesh.gtm")
    pre_session.open_case("StaticMixer.cfx")
    pre_session.write_solver_input("case.def")
    assert pre_session.raw is raw_pre
    assert pre_session.mode == "attach"
    assert raw_pre.file.calls == [
        ("import", "mesh.gtm"),
        ("open_case", "StaticMixer.cfx"),
        ("write", "case.def"),
    ]
    pre_session.exit()
    assert raw_pre.exited is True
    assert pre_session.is_active is False

    raw_post = SimpleNamespace(file=SimpleNamespace(calls=[]), exited=False)
    raw_post.file.load_results = lambda file_name: raw_post.file.calls.append(("load", file_name))
    raw_post.exit = lambda: setattr(raw_post, "exited", True)
    post_session = PostSession(raw_post)
    assert post_session.raw is raw_post
    post_session.load_results("StaticMixer_001.res")
    assert raw_post.file.calls == [("load", "StaticMixer_001.res")]
    post_session.exit()
    assert raw_post.exited is True
    assert post_session.is_active is False


@pytest.mark.asyncio
async def test_cfx_backend_run_code_namespace_and_errors() -> None:
    reset_session_manager()
    backend = CFXBackend()

    invalid = await backend.run_code("   ")
    assert invalid.error_code == "invalid_arguments"

    result = await backend.run_code("value = 5\n__return__ = value * 2")
    assert result.status == "ok"
    assert result.return_value == 10

    expr = await backend.run_code("value + 1")
    assert expr.stdout == "6\n"
    assert expr.return_value == 6

    failed = await backend.run_code("1 / 0")
    assert failed.status == "error"
    assert failed.error_code == "exec_error"


def test_session_manager_status_close_and_active_detection() -> None:
    reset_session_manager()
    closed: list[str] = []
    SessionManager._pre = SimpleNamespace(is_active=lambda: True, exit=lambda: closed.append("pre"))
    SessionManager._solver = SimpleNamespace(is_active=True, exit=lambda: closed.append("solver"))
    SessionManager._post = SimpleNamespace(
        is_active=lambda: False, exit=lambda: closed.append("post")
    )
    SessionManager._solver_input_file = "case.def"
    SessionManager._results_file = "case.res"

    status = SessionManager.status()
    assert status["pre"] is True
    assert status["solver"] is True
    assert status["post"] is False

    SessionManager.disconnect()
    assert closed == ["post", "solver", "pre"]
    assert SessionManager.status()["pre"] is False


def test_solver_session_delegates_to_raw_session() -> None:
    solution = SimpleNamespace(
        calls=[],
        start_run=lambda: solution.calls.append(("start", None)),
        stop_run=lambda wait_for_run=True: solution.calls.append(("stop", wait_for_run)),
        wait_for_run=lambda interval, timeout: solution.calls.append(("wait", interval, timeout)),
        get_results_file_name=lambda: "case.res",
        is_running=lambda: True,
    )
    raw = SimpleNamespace(solution=solution, exited=False)
    raw.exit = lambda: setattr(raw, "exited", True)
    session = SolverSession(raw)

    session.start_run()
    session.stop_run(wait=False)
    session.wait_for_run(interval=2, timeout=3)

    assert session.get_results_file_name() == "case.res"
    assert session.is_running() is True
    assert solution.calls == [("start", None), ("stop", False), ("wait", 2, 3)]
    session.exit()
    assert raw.exited is True
    assert session.is_active is False


def test_pre_session_launch_selects_install_or_container(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    def make_session():
        return SimpleNamespace(
            file=SimpleNamespace(new_case=lambda: calls.append(("new_case", {})))
        )

    def launch_from_install(**kwargs: object):
        calls.append(("from_install", kwargs))
        return make_session()

    def launch_from_container(**kwargs: object):
        calls.append(("from_container", kwargs))
        return make_session()

    core_module = ModuleType("ansys.cfx.core")
    core_module.PreProcessing = SimpleNamespace(
        from_install=launch_from_install,
        from_container=launch_from_container,
    )
    patch_pycfx_core(monkeypatch, core_module)

    install_session = PreSession.launch(
        launcher="from_install", cleanup_on_exit=False, case_file_name="case.cfx"
    )
    container_session = PreSession.launch(
        launcher="from_container",
        cleanup_on_exit=False,
        container_dict={"image": "cfx:test"},
        additional_arguments="--batch",
    )

    assert install_session.mode == "from_install"
    assert container_session.mode == "from_container"
    assert calls[0] == (
        "from_install",
        {
            "cleanup_on_exit": False,
            "start_timeout": 60,
            "additional_arguments": "",
            "case_file_name": "case.cfx",
        },
    )
    assert calls[1] == (
        "from_container",
        {
            "cleanup_on_exit": False,
            "start_timeout": 60,
            "additional_arguments": "--batch",
            "container_dict": {"image": "cfx:test"},
        },
    )
    assert calls[2] == ("new_case", {})


def test_pre_session_launch_rejects_invalid_launcher() -> None:
    with pytest.raises(ValueError, match="launcher"):
        PreSession.launch(launcher="bad")

    with pytest.raises(ValueError, match="case_file_name"):
        PreSession.launch(launcher="from_container", case_file_name="case.cfx")


@pytest.mark.parametrize("exception", [InvalidArguments("bad"), RuntimeError("boom")])
@pytest.mark.asyncio
async def test_typed_guard_converts_errors(exception: Exception) -> None:
    @typed_guard
    async def guarded():
        raise exception

    result = await guarded()

    assert result.status == "error"
    assert result.error_code in {"invalid_arguments", "internal_error"}


def test_worker_protocol_handles_success_error_unknown_and_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    launched = SimpleNamespace(file=SimpleNamespace(new_case=lambda: None), exited=False)
    launched.exit = lambda: setattr(launched, "exited", True)
    launched_from_container = SimpleNamespace(
        file=SimpleNamespace(new_case=lambda: None), exited=False
    )
    launched_from_container.exit = lambda: setattr(launched_from_container, "exited", True)
    core_module = ModuleType("ansys.cfx.core")
    core_module.PreProcessing = SimpleNamespace(
        from_install=lambda **kwargs: launched,
        from_container=lambda **kwargs: launched_from_container,
    )
    patch_pycfx_core(monkeypatch, core_module)
    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO(
            '{"cmd": "launch_pre", "launcher": "from_container", "kwargs": {"cleanup_on_exit": false}}\n'  # noqa: E501
            '{"cmd": "run_code", "code": "x = 1"}\n'
            '{"cmd": "unknown"}\n'
            '{"cmd": "run_code", "code": "raise ValueError(\'bad\')"}\n'
            '{"cmd": "exit"}\n'
        ),
    )
    stdout = io.StringIO()
    monkeypatch.setattr(sys, "stdout", stdout)

    worker_main()

    lines = [line for line in stdout.getvalue().splitlines() if line]
    assert [line.split('"status": "', 1)[1].split('"', 1)[0] for line in lines] == [
        "ok",
        "ok",
        "error",
        "error",
        "ok",
    ]
    assert launched.exited is False
    assert launched_from_container.exited is True
