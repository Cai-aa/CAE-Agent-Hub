import json
import sys
import time
from types import SimpleNamespace

import pytest

from ansa_mcp_bridge.monitor import Monitor, compare_snapshots
from ansa_mcp_bridge.runtime import BridgeRuntime
from ansa_mcp_bridge.dashboard import Dashboard


def sample(count=0, database="demo.ansa", **kwargs):
    return {"database": database, "deck": 1, "counts": {"GRID": count}, "errors": {}, **kwargs}


def test_monitor_redacts_and_bounds_without_recording_python():
    token = "a" * 64
    m = Monitor(token)
    for _ in range(115):
        event = m.begin("execute_python_step", {"code": "private_model_data = 'secret'", "token": token,
                                              "fields": {"password": "hidden"}, "step_name": "test"})
        m.finish(event, time.monotonic(), {"python_result": {"private": "data"}},
                 RuntimeError("token=" + token + " password=abc"))
    encoded = json.dumps(m.export())
    assert len(m.events) == 100 and len(m.errors) == 20
    assert len(m.export()["events"]) == 100
    assert all(x not in encoded for x in (token, "private_model_data", "hidden", "password=abc", "python_result"))
    assert "sha256" in encoded
    assert m.events[-1]["status"] == "failed"


@pytest.mark.parametrize("before,after,status", [
    (sample(2), sample(5), "sampled"),
    (sample(), sample(errors={"FACE": "unsupported"}), "partial"),
    (sample(), sample(database="another.ansa"), "context_changed"),
    (sample(), {"error": "unavailable"}, "unavailable"),
    (None, sample(), "unavailable"),
])
def test_delta_never_treats_missing_or_changed_context_as_zero(before, after, status):
    change = compare_snapshots(before, after)
    assert change["status"] == status
    if status == "sampled":
        assert change["counts"]["GRID"] == {"before": 2, "after": 5, "delta": 3}


def make_runtime(tmp_path, monkeypatch):
    import ansa_mcp_bridge.runtime as module
    monkeypatch.setattr(module, "load_config", lambda: (tmp_path / "bridge.json", {
        "host": "127.0.0.1", "port": 48762, "token": "b" * 64,
        "allowed_roots": [str(tmp_path)], "request_timeout_seconds": 120}))
    runtime = BridgeRuntime()
    monkeypatch.setattr(runtime, "refresh_session", lambda: True)
    return runtime


def test_runtime_records_reads_deltas_errors_and_replay(tmp_path, monkeypatch):
    runtime = make_runtime(tmp_path, monkeypatch)
    calls = []
    snapshots = iter([sample(0), sample(1), sample(1), sample(1), sample(1), sample(1)])
    monkeypatch.setattr(runtime, "_model_snapshot", lambda: next(snapshots))

    def dispatch(method, params):
        calls.append(method)
        if params.get("fail"):
            raise RuntimeError("OUTCOME_UNKNOWN: write may have started")
        return {"idempotent_replay": params.get("replay", False)}

    runtime.registry = SimpleNamespace(dispatch=dispatch)
    runtime.dispatch("ping", {})
    assert runtime.monitor.events[-1]["status"] == "completed"
    runtime.dispatch("create_entity", {})
    assert runtime.monitor.last_change["counts"]["GRID"]["delta"] == 1
    runtime.dispatch("create_entity", {"replay": True})
    assert runtime.monitor.events[-1]["status"] == "replayed"
    with pytest.raises(RuntimeError, match="OUTCOME_UNKNOWN"):
        runtime.dispatch("create_entity", {"fail": True})
    assert runtime.monitor.events[-1]["status"] == "outcome_unknown"
    assert len(calls) == 4


def test_observation_failure_never_repeats_or_hides_committed_write(tmp_path, monkeypatch):
    runtime = make_runtime(tmp_path, monkeypatch)
    runtime.monitor.capture_changes = False
    calls = []
    runtime.registry = SimpleNamespace(dispatch=lambda *args: calls.append(args) or {"saved": True})
    monkeypatch.setattr(runtime.monitor, "finish", lambda *a: (_ for _ in ()).throw(RuntimeError("bad observer")))
    assert runtime.dispatch("save_database", {}) == {"saved": True}
    assert len(calls) == 1
    assert runtime.monitor.errors[-1]["source"] == "monitor"


def test_export_preserves_prior_files_and_excludes_token(tmp_path, monkeypatch):
    runtime = make_runtime(tmp_path, monkeypatch)
    runtime.monitor.add_error("test", runtime.token)
    first, second = runtime.export_monitor(), runtime.export_monitor()
    assert first != second and first.is_file() and second.is_file()
    assert first.parent == tmp_path / "diagnostics"
    assert runtime.token not in first.read_text(encoding="utf-8")


class FakeGui:
    constants = SimpleNamespace(BCVertical=1, BCRenameType_None=0,
                                BCWidgetWidth=1, BCWrapAtWordBoundaryOrAnywhere=4)

    def __init__(self):
        self.calls = []
        self.values = {}
        self.selected = None

    def __getattr__(self, name):
        def call(*args):
            self.calls.append((name, args))
            if name == "BCListViewGetSelectedItem":
                return self.selected
            if name == "BCListViewItemGetUserData":
                return self.values[args[0]]
            if name == "BCListViewItemSetUserData":
                self.values[args[0]] = args[1]
            if name == "BCCheckBoxIsChecked":
                return False
            return len(self.calls)
        return call


def test_dashboard_renders_and_selection_does_not_execute_or_delete(tmp_path, monkeypatch):
    gui = FakeGui()
    monkeypatch.setitem(sys.modules, "ansa", SimpleNamespace(guitk=gui))
    runtime = make_runtime(tmp_path, monkeypatch)
    panel = Dashboard(runtime, "window")
    event = runtime.monitor.begin("ping", {})
    runtime.monitor.finish(event, time.monotonic())
    panel.tick()
    gui.selected = next(iter(gui.values))
    before = len(gui.calls)
    assert panel._selected(panel.timeline, None) == 0
    assert all(c[0] != "BCListViewClear" for c in gui.calls[before:])
    assert panel.selected_sequence == 1
    assert panel._capture(panel.capture, 0, None) == 0
    assert runtime.monitor.capture_changes is False
    panel._copy(None, None)
    assert any(c[0] == "BCApplicationClipboardSetText" for c in gui.calls)
    assert len(runtime.monitor.events) == 1


def test_dashboard_contains_minimum_width_and_wraps_diagnostics(tmp_path, monkeypatch):
    gui = FakeGui()
    monkeypatch.setitem(sys.modules, "ansa", SimpleNamespace(guitk=gui))
    runtime = make_runtime(tmp_path, monkeypatch)
    panel = Dashboard(runtime, "window")
    calls = gui.calls
    assert ("BCScrollAreaSetWidget", (panel.scroll_area, panel.content)) in calls
    assert ("BCScrollAreaSetWidgetResizable", (panel.scroll_area, True)) in calls
    attach = next(i for i, (name, _) in enumerate(calls) if name == "BCScrollAreaSetWidget")
    assert any(name == "BCBoxLayoutCreate" and args[0] == panel.content
               for name, args in calls[:attach])
    assert ("BCWindowSetSize", ("window", 320, 740)) in calls
    assert [args[2] for name, args in calls if name == "BCTabWidgetAddTab"] == ["记录", "模型", "诊断"]
    for widget in (panel.details, panel.model_text, panel.diagnostic_text):
        assert ("BCTextEditSetWordWrap", (widget, gui.constants.BCWidgetWidth)) in calls
        assert ("BCTextEditSetWrapPolicy", (widget, gui.constants.BCWrapAtWordBoundaryOrAnywhere)) in calls
