"""Tests for the non-plugin ANSA user-script button fallback."""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

import pytest


CONTROLS = Path(__file__).resolve().parents[1] / "ansa_plugin" / "ansa_mcp_controls.py"


def test_loading_controls_only_registers_buttons(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registered = []
    ansa = ModuleType("ansa")
    ansa.session = ModuleType("ansa.session")  # type: ignore[attr-defined]

    def defbutton(group, label):
        def decorate(function):
            registered.append((group, label, function))
            return function
        return decorate

    ansa.session.defbutton = defbutton  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ansa", ansa)
    monkeypatch.setattr(sys, "path", list(sys.path))
    namespace = {"__file__": str(CONTROLS)}
    exec(compile(CONTROLS.read_text(encoding="utf-8"), str(CONTROLS), "exec"), namespace)

    assert [(group, label) for group, label, _ in registered] == [
        ("ANSA MCP", "Start"),
        ("ANSA MCP", "Status"),
        ("ANSA MCP", "Stop"),
    ]
    assert str(CONTROLS.parent) in sys.path
    assert "ansa_mcp_plugin" not in sys.modules


def test_buttons_dispatch_only_when_pressed(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    ansa = ModuleType("ansa")
    ansa.session = ModuleType("ansa.session")  # type: ignore[attr-defined]
    ansa.session.defbutton = lambda group, label: lambda function: function  # type: ignore[attr-defined]
    plugin = ModuleType("ansa_mcp_plugin")
    plugin.start_bridge = lambda: calls.append("start")  # type: ignore[attr-defined]
    plugin.show_bridge_status = lambda: calls.append("status")  # type: ignore[attr-defined]
    plugin.stop_bridge = lambda: calls.append("stop")  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ansa", ansa)
    monkeypatch.setitem(sys.modules, "ansa_mcp_plugin", plugin)
    namespace = {"__file__": str(CONTROLS)}
    exec(compile(CONTROLS.read_text(encoding="utf-8"), str(CONTROLS), "exec"), namespace)
    assert calls == []
    namespace["ansa_mcp_start"]()
    namespace["ansa_mcp_status"]()
    namespace["ansa_mcp_stop"]()
    assert calls == ["start", "status", "stop"]


def test_button_callback_restores_script_directory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ansa = ModuleType("ansa")
    ansa.session = ModuleType("ansa.session")  # type: ignore[attr-defined]
    ansa.session.defbutton = lambda group, label: lambda function: function  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ansa", ansa)
    monkeypatch.delitem(sys.modules, "ansa_mcp_plugin", raising=False)
    monkeypatch.setattr(sys, "path", list(sys.path))
    namespace = {"__file__": str(CONTROLS)}
    exec(compile(CONTROLS.read_text(encoding="utf-8"), str(CONTROLS), "exec"), namespace)

    # ANSA may replace the Python module search path after Load Script returns.
    sys.path.remove(str(CONTROLS.parent))
    assert str(CONTROLS.parent) not in sys.path
    plugin = namespace["_plugin_module"]()

    assert str(CONTROLS.parent) in sys.path
    assert Path(plugin.__file__).resolve() == CONTROLS.parent / "ansa_mcp_plugin.py"
