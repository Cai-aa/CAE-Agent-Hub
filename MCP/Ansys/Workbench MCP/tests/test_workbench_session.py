from __future__ import annotations

import contextlib
import json
import sys
from types import SimpleNamespace

import pytest

from tools import workbench_session as ws


class FakeChannel:
    def __init__(self) -> None:
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1


class FakeWorkbench:
    def __init__(self, inventory: dict | None = None) -> None:
        self.inventory = inventory or {
            "framework_version": "25.2",
            "project_file": None,
            "systems": [],
            "system_count": 0,
        }
        self.started_systems: list[tuple[str, int]] = []
        self.exit_calls = 0
        self.scripts: list[str] = []
        self.channel = FakeChannel()
        self.stub = object()

    def run_script_string(self, script: str):
        self.scripts.append(script)
        return json.dumps(self.inventory)

    def start_mechanical_server(self, system_name: str, port: int = 0) -> int:
        self.started_systems.append((system_name, port))
        return 55123

    def exit(self) -> None:
        self.exit_calls += 1


class FakeMechanical:
    def __init__(self, state: dict | None = None) -> None:
        self.state = state or {
            "ok": True,
            "project_directory": r"C:\project_files\dp0\SYS\MECH",
            "model_present": True,
            "body_count": 7,
            "body_names": ["实体1", "实体2", "实体3", "销1", "销1 (1)", "销1 (2)", "销1 (3)"],
            "active_body_count": 7,
            "active_body_names": ["实体1", "实体2", "实体3", "销1", "销1 (1)", "销1 (2)", "销1 (3)"],
            "analysis_count": 1,
            "analyses": [{
                "name": "Static Structural",
                "analysis_type": "Static Structural",
                "working_directory": r"C:\beam\beam_v2_files\dp0\SYS\MECH",
            }],
        }
        self.calls: list[str] = []
        self.exit_calls = 0
        self._channel = FakeChannel()

    def run_python_script(self, code: str):
        self.calls.append(code)
        if "DataModelObjectCategory" in code:
            return json.dumps(self.state)
        return "user-result"

    def exit(self) -> None:
        self.exit_calls += 1
        raise AssertionError("Mechanical exit must not be called by a safe disconnect")


class EscapedFakeMechanical(FakeMechanical):
    """Return the ASCII-only payload produced by the Mechanical IronPython gate."""

    def run_python_script(self, code: str):
        self.calls.append(code)
        if "DataModelObjectCategory" not in code:
            return "user-result"
        escape = lambda value: value.encode("unicode_escape").decode("ascii")
        state = dict(self.state)
        state["project_directory"] = escape(r"C:\项目_files\dp0\SYS\MECH")
        state["body_names"] = [escape("实体1"), escape("销1")]
        state["active_body_names"] = list(state["body_names"])
        state["analyses"] = [
            {
                "name": escape("静态结构"),
                "analysis_type": escape("Static Structural"),
                "working_directory": escape(r"C:\项目_files\dp0\SYS\MECH"),
            }
        ]
        state["named_selection_count"] = 0
        state["named_selection_names"] = []
        return json.dumps(state, ensure_ascii=True)


@pytest.fixture(autouse=True)
def clear_sessions():
    ws._WORKBENCH_SESSIONS.clear()
    ws._WORKBENCH_ENDPOINT_INDEX.clear()
    ws._MODEL_SESSIONS.clear()
    ws._MODEL_INDEX.clear()
    ws._MODEL_OPENING.clear()
    ws._MODEL_ENDPOINTS.clear()
    yield
    ws._WORKBENCH_SESSIONS.clear()
    ws._WORKBENCH_ENDPOINT_INDEX.clear()
    ws._MODEL_SESSIONS.clear()
    ws._MODEL_INDEX.clear()
    ws._MODEL_OPENING.clear()
    ws._MODEL_ENDPOINTS.clear()


def mechanical_inventory() -> dict:
    return {
        "framework_version": "25.2",
        "project_file": r"C:\beam\beam_v2.wbpj",
        "systems": [
            {
                "name": "SYS",
                "display_text": "Beam Assembly Static - Solid Contact V2",
                "has_model": True,
                "has_solution": True,
            }
        ],
        "system_count": 1,
    }


def test_launch_refuses_second_workbench(monkeypatch):
    monkeypatch.setattr(
        ws,
        "_workbench_processes",
        lambda strict=False: [{"pid": 10, "name": "RunWB2.exe", "command_line": []}],
    )
    monkeypatch.setattr(
        ws,
        "_load_pyworkbench",
        lambda: (_ for _ in ()).throw(AssertionError("launcher must not be loaded")),
    )

    result = ws.workbench_launch_managed()

    assert result["ok"] is False
    assert result["status"] == "blocked_existing_workbench"


def test_attach_current_and_inventory(monkeypatch):
    fake = FakeWorkbench(mechanical_inventory())
    monkeypatch.setattr(ws, "_load_pyworkbench", lambda: (lambda **_: fake, object))

    attached = ws.workbench_attach_current(port=51000)

    assert attached["ok"] is True
    session_id = attached["data"]["session_id"]
    inspected = ws.workbench_project_inventory(session_id)
    assert inspected["ok"] is True
    assert inspected["data"]["systems"][0]["name"] == "SYS"


def test_project_open_blocks_different_active_project(tmp_path, monkeypatch):
    target = tmp_path / "target.wbpj"
    target.write_text("placeholder", encoding="utf-8")
    fake = FakeWorkbench(mechanical_inventory())
    session_id = "wb_test"
    ws._WORKBENCH_SESSIONS[session_id] = ws.WorkbenchSession(
        session_id=session_id,
        client=fake,
        port=51000,
        security="insecure",
        owned=False,
    )
    monkeypatch.setattr(ws, "_workbench_inventory", lambda _: mechanical_inventory())

    result = ws.workbench_project_open(session_id, str(target))

    assert result["ok"] is False
    assert result["status"] == "blocked_active_project"
    assert not any("Open(FilePath=" in script for script in fake.scripts)


def test_project_open_verifies_target_identity(tmp_path, monkeypatch):
    target = tmp_path / "target.wbpj"
    target.write_text("placeholder", encoding="utf-8")
    fake = FakeWorkbench()
    session_id = "wb_test"
    ws._WORKBENCH_SESSIONS[session_id] = ws.WorkbenchSession(
        session_id=session_id,
        client=fake,
        port=51000,
        security="insecure",
        owned=True,
    )
    before = {
        "framework_version": "25.2",
        "project_file": None,
        "systems": [],
        "system_count": 0,
    }
    after = dict(before, project_file=str(target.resolve()))
    inventories = iter((before, after))
    monkeypatch.setattr(ws, "_workbench_inventory", lambda _: next(inventories))

    result = ws.workbench_project_open(session_id, str(target))

    assert result["ok"] is True
    assert result["status"] == "opened"
    assert result["evidence"]["project_path"] == str(target.resolve())
    assert any("Open(FilePath=" in script for script in fake.scripts)


def test_project_save_as_refuses_overwrite_and_verifies_identity(tmp_path, monkeypatch):
    fake = FakeWorkbench(mechanical_inventory())
    session_id = "wb_test"
    ws._WORKBENCH_SESSIONS[session_id] = ws.WorkbenchSession(
        session_id=session_id,
        client=fake,
        port=51000,
        security="insecure",
        owned=True,
    )
    existing = tmp_path / "existing.wbpj"
    existing.write_text("keep", encoding="utf-8")

    blocked = ws.workbench_project_save_as(session_id, str(existing))

    assert blocked["ok"] is False
    assert blocked["status"] == "target_exists"
    assert fake.scripts == []

    target = tmp_path / "nested" / "saved.wbpj"
    after = dict(mechanical_inventory(), project_file=str(target.resolve()))
    monkeypatch.setattr(ws, "_workbench_inventory", lambda _: after)

    saved = ws.workbench_project_save_as(session_id, str(target))

    assert saved["ok"] is True
    assert saved["status"] == "saved"
    assert target.parent.is_dir()
    assert any("Save(FilePath=" in script and "Overwrite=False" in script for script in fake.scripts)


def test_model_open_is_unique_and_idempotent(monkeypatch):
    workbench = FakeWorkbench(mechanical_inventory())
    mechanical = FakeMechanical()
    session_id = "wb_test"
    ws._WORKBENCH_SESSIONS[session_id] = ws.WorkbenchSession(
        session_id=session_id,
        client=workbench,
        port=51000,
        security="insecure",
        owned=False,
    )
    monkeypatch.setattr(ws, "_workbench_inventory", lambda _: mechanical_inventory())
    monkeypatch.setattr(ws, "_load_pymechanical", lambda: (lambda **_: mechanical))

    first = ws.workbench_model_open(session_id=session_id)
    second = ws.workbench_model_open(session_id=session_id)

    assert first["ok"] is True
    assert first["status"] == "model_ready"
    assert first["evidence"]["mechanical_port"] == 55123
    assert workbench.started_systems == [("SYS", 0)]
    assert second["ok"] is True
    assert second["status"] == "already_open"
    assert second["idempotent"] is True
    assert second["data"]["model_session_id"] == first["data"]["model_session_id"]


def test_model_state_enforces_expected_counts(monkeypatch):
    mechanical = FakeMechanical()
    workbench = FakeWorkbench(mechanical_inventory())
    ws._WORKBENCH_SESSIONS["wb_test"] = ws.WorkbenchSession(
        session_id="wb_test",
        client=workbench,
        port=51000,
        security="insecure",
        owned=False,
    )
    model_id = "model_test"
    ws._MODEL_SESSIONS[model_id] = ws.ModelSession(
        model_session_id=model_id,
        workbench_session_id="wb_test",
        system_name="SYS",
        client=mechanical,
        port=55123,
        transport_mode="insecure",
        project_file=ws._normalize_path(r"C:\beam\beam_v2.wbpj"),
    )

    result = ws.workbench_model_state(
        model_session_id=model_id,
        expected_body_count=7,
        expected_analysis_count=2,
    )

    assert result["ok"] is False
    assert result["status"] == "model_gate_failed"
    assert "Expected 2 analyses" in result["errors"][0]


def test_disconnect_never_terminates_mechanical():
    workbench = FakeWorkbench()
    mechanical = FakeMechanical()
    session_id = "wb_test"
    model_id = "model_test"
    ws._WORKBENCH_SESSIONS[session_id] = ws.WorkbenchSession(
        session_id=session_id,
        client=workbench,
        port=51000,
        security="insecure",
        owned=False,
    )
    ws._MODEL_SESSIONS[model_id] = ws.ModelSession(
        model_session_id=model_id,
        workbench_session_id=session_id,
        system_name="SYS",
        client=mechanical,
        port=55123,
        transport_mode="insecure",
    )
    ws._MODEL_INDEX[(session_id, "SYS")] = model_id

    result = ws.workbench_session_disconnect(session_id)

    assert result["ok"] is True
    assert workbench.exit_calls == 0
    assert mechanical.exit_calls == 0
    assert workbench.channel is None
    assert mechanical._channel is None
    assert session_id not in ws._WORKBENCH_SESSIONS
    assert model_id not in ws._MODEL_SESSIONS


def test_disconnect_supports_workbench_client_without_exit_method():
    channel = FakeChannel()
    client = SimpleNamespace(channel=channel, stub=object())
    ws._WORKBENCH_SESSIONS["wb_test"] = ws.WorkbenchSession(
        session_id="wb_test",
        client=client,
        port=51000,
        security="mtls",
        owned=False,
    )

    result = ws.workbench_session_disconnect("wb_test")

    assert result["ok"] is True
    assert channel.close_calls == 1
    assert client.channel is None
    assert client.stub is None


def test_model_state_enforces_exact_project_system_bodies_and_analysis_type():
    workbench = FakeWorkbench(mechanical_inventory())
    mechanical = FakeMechanical()
    ws._WORKBENCH_SESSIONS["wb_test"] = ws.WorkbenchSession(
        session_id="wb_test",
        client=workbench,
        port=51000,
        security="mtls",
        owned=False,
    )
    ws._MODEL_SESSIONS["model_test"] = ws.ModelSession(
        model_session_id="model_test",
        workbench_session_id="wb_test",
        system_name="SYS",
        client=mechanical,
        port=55123,
        transport_mode="insecure",
        project_file=ws._normalize_path(r"C:\beam\beam_v2.wbpj"),
    )

    result = ws.workbench_model_state(
        model_session_id="model_test",
        expected_project_path=r"C:\beam\beam_v2.wbpj",
        expected_system_name="SYS",
        expected_body_count=7,
        expected_body_names=["实体1", "实体2", "实体3", "销1", "销1 (1)", "销1 (2)", "销1 (3)"],
        expected_analysis_count=1,
        expected_analysis_names=["Static Structural"],
        expected_analysis_types=["Static Structural"],
    )

    assert result["ok"] is True
    assert result["status"] == "model_ready"
    assert result["evidence"]["project_file"] == ws._normalize_path(r"C:\beam\beam_v2.wbpj")


def test_mechanical_state_decodes_unicode_escape_and_handles_empty_named_selections():
    mechanical = EscapedFakeMechanical(
        {
            "ok": True,
            "application_version": "25.2",
            "project_directory": "unused",
            "model_present": True,
            "body_count": 2,
            "body_names": [],
            "active_body_count": 2,
            "active_body_names": [],
            "analysis_count": 1,
            "analyses": [],
        }
    )

    state = ws._mechanical_state(mechanical)

    assert state["project_directory"] == r"C:\项目_files\dp0\SYS\MECH"
    assert state["body_names"] == ["实体1", "销1"]
    assert state["active_body_names"] == ["实体1", "销1"]
    assert state["analyses"][0]["name"] == "静态结构"
    assert state["named_selection_count"] == 0
    assert state["named_selection_names"] == []
    emitted = mechanical.calls[-1]
    assert "unicode_escape" in emitted
    assert 'getattr(model, "NamedSelections", None)' in emitted
    assert "DataModelObjectCategory.NamedSelection" in emitted


def test_launch_fails_closed_when_process_inventory_is_unavailable(monkeypatch):
    monkeypatch.setattr(
        ws,
        "_workbench_processes",
        lambda strict=False: (_ for _ in ()).throw(RuntimeError("inventory unavailable")),
    )
    monkeypatch.setattr(
        ws,
        "_load_pyworkbench",
        lambda: (_ for _ in ()).throw(AssertionError("launcher must not be loaded")),
    )

    result = ws.workbench_launch_managed()

    assert result["ok"] is False
    assert result["status"] == "launch_failed"
    assert "inventory unavailable" in result["errors"][0]


def test_model_open_reuses_cached_endpoint_after_connect_failure(monkeypatch):
    workbench = FakeWorkbench(mechanical_inventory())
    mechanical = FakeMechanical()
    session_id = "wb_test"
    ws._WORKBENCH_SESSIONS[session_id] = ws.WorkbenchSession(
        session_id=session_id,
        client=workbench,
        port=51000,
        security="wnua",
        owned=False,
    )
    calls = []

    def connect(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise RuntimeError("transient connect failure")
        return mechanical

    monkeypatch.setattr(ws, "_load_pymechanical", lambda: connect)

    first = ws.workbench_model_open(session_id=session_id)
    second = ws.workbench_model_open(session_id=session_id)

    assert first["ok"] is False
    assert second["ok"] is True
    assert workbench.started_systems == [("SYS", 0)]
    assert len(calls) == 2
    assert calls[0]["transport_mode"] is None
    assert calls[1]["port"] == 55123


def test_bootstrap_current_is_idempotent_and_identity_gated(monkeypatch):
    expected_project = r"C:\beam\beam_v2.wbpj"
    fake = FakeWorkbench(mechanical_inventory())
    connect_calls = []

    monkeypatch.setattr(
        ws,
        "_process_inventory",
        lambda strict=False: [
            {"pid": 10, "parent_pid": 1, "name": "RunWB2.exe"},
            {"pid": 11, "parent_pid": 10, "name": "AnsysFWW.exe"},
            {"pid": 12, "parent_pid": 11, "name": "AnsysWBU.exe"},
        ],
    )
    monkeypatch.setattr(
        ws,
        "_exclusive_launch_guard",
        lambda timeout=30.0: contextlib.nullcontext(),
    )
    monkeypatch.setattr(
        ws,
        "_bootstrap_bridge_report",
        lambda timeout: {
            "ok": True,
            "pid": 11,
            "server_port": 57117,
            "project_file": expected_project,
            "systems": ["SYS"],
            "start_called": False,
        },
    )

    def connect_workbench(**kwargs):
        connect_calls.append(kwargs)
        return fake

    monkeypatch.setattr(ws, "_load_pyworkbench", lambda: (connect_workbench, object))

    first = ws.workbench_bootstrap_current(
        expected_project_path=expected_project,
        expected_system_name="SYS",
    )
    second = ws.workbench_bootstrap_current(
        expected_project_path=expected_project,
        expected_system_name="SYS",
    )

    assert first["ok"] is True
    assert first["status"] == "bootstrapped"
    assert second["ok"] is True
    assert second["status"] == "already_bootstrapped"
    assert first["data"]["session_id"] == second["data"]["session_id"]
    assert connect_calls == [
        {"port": 57117, "host": "localhost", "security": "wnua"}
    ]


def test_process_inventory_strict_fails_on_candidate_access_error(monkeypatch):
    class Candidate:
        info = {"pid": 99, "name": "AnsysFWW.exe"}

        def as_dict(self, attrs):
            raise PermissionError("access denied")

    fake_psutil = SimpleNamespace(process_iter=lambda attrs: [Candidate()])
    monkeypatch.setitem(sys.modules, "psutil", fake_psutil)

    with pytest.raises(RuntimeError, match="candidate ANSYS process"):
        ws._process_inventory(strict=True)


def test_bootstrap_bridge_report_rejects_execution_failure(monkeypatch):
    monkeypatch.setattr(
        ws,
        "socket_timer_execute_python",
        lambda code, timeout: {
            "ok": True,
            "response": {"ok": True, "execution": {"ok": False, "stderr": "boom"}},
        },
    )

    with pytest.raises(RuntimeError, match="execution failed"):
        ws._bootstrap_bridge_report(timeout=1.0)


def test_model_open_attaches_explicit_existing_port_without_start(monkeypatch):
    workbench = FakeWorkbench(mechanical_inventory())
    mechanical = FakeMechanical()
    ws._WORKBENCH_SESSIONS["wb_test"] = ws.WorkbenchSession(
        session_id="wb_test",
        client=workbench,
        port=57117,
        security="wnua",
        owned=False,
    )
    calls = []

    def connect(**kwargs):
        calls.append(kwargs)
        return mechanical

    monkeypatch.setattr(ws, "_load_pymechanical", lambda: connect)

    result = ws.workbench_model_open(
        session_id="wb_test",
        system_name="SYS",
        mechanical_port=59120,
    )

    assert result["ok"] is True
    assert workbench.started_systems == []
    assert calls[0]["port"] == 59120
    assert calls[0]["transport_mode"] is None


def test_model_execute_refuses_when_identity_gate_fails(monkeypatch):
    workbench = FakeWorkbench(mechanical_inventory())
    mechanical = FakeMechanical()
    ws._WORKBENCH_SESSIONS["wb_test"] = ws.WorkbenchSession(
        session_id="wb_test",
        client=workbench,
        port=57117,
        security="wnua",
        owned=False,
    )
    ws._MODEL_SESSIONS["model_test"] = ws.ModelSession(
        model_session_id="model_test",
        workbench_session_id="wb_test",
        system_name="SYS",
        client=mechanical,
        port=59120,
        transport_mode=None,
        project_file=ws._normalize_path(r"C:\beam\beam_v2.wbpj"),
    )
    monkeypatch.setattr(
        ws,
        "workbench_model_state",
        lambda **kwargs: {
            "ok": False,
            "status": "model_gate_failed",
            "errors": ["project switched"],
        },
    )

    result = ws.workbench_model_execute_python("model_test", "1 + 1")

    assert result["ok"] is False
    assert result["status"] == "identity_gate_failed"
    assert mechanical.calls == []


def test_bootstrap_bridge_report_preserves_unicode_project_path(monkeypatch):
    captured: dict[str, str] = {}
    expected_path = r"D:\工程文件\ansys\0001.wbpj"

    def fake_socket_execute(code: str, timeout: float) -> dict:
        captured["code"] = code
        report = {
            "ok": True,
            "phase": "SERVER_REUSE_OR_START_ONCE",
            "pid": 1234,
            "server_port": 57117,
            "project_file": expected_path,
            "systems": ["SYS"],
            "start_called": False,
        }
        return {
            "ok": True,
            "response": {
                "ok": True,
                "execution": {
                    "ok": True,
                    "stdout": "WB_BOOTSTRAP_JSON:"
                    + json.dumps(report, ensure_ascii=True)
                    + "\n",
                },
            },
        }

    monkeypatch.setattr(ws, "socket_timer_execute_python", fake_socket_execute)

    result = ws._bootstrap_bridge_report(timeout=1.0)

    assert result["project_file"] == expected_path
    assert "unicode(GetProjectFile())" in captured["code"]
    assert "str(GetProjectFile())" not in captured["code"]
