"""Opt-in ANSA host for an isolated native-package smoke test (not pytest)."""
import importlib
import json
import os
import runpy
import time
import traceback
from pathlib import Path

from ansa import betascript, guitk, session

ROOT = Path(os.environ["ANSA_MCP_DASHBOARD_TEST_ROOT"]).resolve(strict=True)
MODE = os.environ["ANSA_MCP_DASHBOARD_TEST_MODE"]
report = {"pid": os.getpid(), "gui_mode": bool(guitk.BCApplicationIsGuiMode())}
code = 1
try:
    if MODE == "install":
        api = runpy.run_path(os.environ["ANSA_MCP_TEST_PACKAGER_API"])
        api["no_gui_plugin_installer"](os.environ["ANSA_MCP_TEST_BPKG"], 2, None)
        report["installed"] = (ROOT / "profile/.BETA/ANSA/version_25.1.2/plugins/ANSA_MCP_Bridge.ppl").is_file()
        assert report["installed"]
    else:
        # Load the native button entry, then redirect ONLY its config locator
        # inside this disposable process to the test's fresh credentials/port.
        betascript.RunPluginFunction("ANSA_MCP_Bridge", "ANSA MCP", "Status")
        app = importlib.import_module("ANSA_MCP_Bridge_root.app")
        assert app._BRIDGE_ENTRY is None, "This test validates the redistributable package config path"
        bundled = app._runtime_module()
        runtime_module = importlib.import_module(bundled.__name__ + ".runtime")
        deadline = time.monotonic() + 100

        def _finish_impl(data):
            runtime = runtime_module._RUNTIME
            if runtime is not None and runtime.dashboard is not None:
                (ROOT / "ready.json").write_text(json.dumps({"pid": os.getpid(), "port": runtime.port}), encoding="utf-8")
            if (ROOT / "finish").is_file() or time.monotonic() > deadline:
                if runtime is not None and runtime.dashboard is not None:
                    panel = runtime.dashboard
                    # Use the real GUITK callback dispatch, not a mock signature.
                    guitk.BCCheckBoxSetChecked(panel.capture, False)
                    assert runtime.monitor.capture_changes is False
                    guitk.BCCheckBoxSetChecked(panel.capture, True)
                    assert runtime.monitor.capture_changes is True
                    report["checkbox_callback_verified"] = True
                    item = guitk.BCListViewGetItem(panel.timeline, 0)
                    guitk.BCListViewSetSelected(panel.timeline, item, True)
                    assert panel.selected_sequence is not None
                    report["selection_callback_verified"] = True
                    panel._check(None, None)
                    panel._refresh_model(None, None)
                    assert "GRID: 1" in guitk.BCTextEditGetText(panel.model_text)
                    report["monitor"] = runtime.monitor.export()
                    report["connection_label"] = guitk.BCLabelText(panel.connection)
                    report["context_label"] = guitk.BCLabelText(panel.context)
                    report["model_text"] = guitk.BCTextEditGetText(panel.model_text)
                    report["timeline_rows"] = guitk.BCListViewTopLevelItemCount(panel.timeline)
                    report["diagnostic_export"] = str(runtime.export_monitor())
                    runtime.stop()
                return 0
            guitk.BCTimerSingleShot(250, finish_when_requested, None)
            return 0

        def finish_when_requested(data):
            try:
                return _finish_impl(data)
            except Exception:
                report["callback_error"] = traceback.format_exc()
                runtime = runtime_module._RUNTIME
                if runtime is not None:
                    runtime.stop()
                return 0

        guitk.BCTimerSingleShot(500, finish_when_requested, None)
        betascript.RunPluginFunction("ANSA_MCP_Bridge", "ANSA MCP", "Start")
        assert (ROOT / "finish").is_file(), "live test timed out"
        assert runtime_module._RUNTIME is None
        assert not report.get("callback_error"), report.get("callback_error")
        assert report.get("timeline_rows", 0) >= 4
    report["ok"] = True
    code = 0
except Exception:
    report["ok"] = False
    report["error"] = traceback.format_exc()
(ROOT / (MODE + "_report.json")).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print("DASHBOARD TEST", MODE, "OK", report["ok"], flush=True)
session.Quit(code)
