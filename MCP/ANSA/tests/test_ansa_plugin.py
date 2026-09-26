"""Offline checks for the ANSA Plugins ribbon descriptor and callbacks."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import ModuleType

import pytest


PLUGIN_ROOT = Path(__file__).resolve().parents[1] / "ansa_plugin"


def test_descriptor_has_three_buttons_and_local_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = []
    ansa = ModuleType("ansa")
    ansa.session = ModuleType("ansa.session")  # type: ignore[attr-defined]
    ansa.session.setPluginInfos = captured.append  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ansa", ansa)
    descriptor = PLUGIN_ROOT / "ANSA_MCP_Bridge.ppl.disabled"

    exec(compile(descriptor.read_text(encoding="utf-8"), str(descriptor), "exec"),
         {"__file__": str(descriptor)})

    assert len(captured) == 1
    info = captured[0]
    assert Path(info.filepath) == PLUGIN_ROOT / "ansa_mcp_plugin.py"
    assert {item[0] for item in info.Buttons.values()} == {
        "start_bridge", "show_bridge_status", "stop_bridge"
    }


def test_plugin_start_status_stop_use_same_validated_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    installed_root = tmp_path / "installed"
    installed_root.mkdir()
    config_path = tmp_path / "bridge.json"
    config_path.write_text(
        json.dumps({"plugin_root": str(installed_root)}), encoding="utf-8"
    )
    (installed_root / "bridge_config_path.txt").write_text(
        str(config_path), encoding="utf-8"
    )
    calls = []
    bridge = ModuleType("ansa_mcp_bridge")
    current = {"state": "offline"}

    def start(*, dock_to_database=False):
        calls.append(("start", dock_to_database))
        current["state"] = "online"
        return dict(current)

    def stop():
        calls.append(("stop",))
        current["state"] = "offline"
        return dict(current)

    bridge.start = start  # type: ignore[attr-defined]
    bridge.status = lambda: dict(current)  # type: ignore[attr-defined]
    bridge.stop = stop  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ansa_mcp_bridge", bridge)
    monkeypatch.setattr(sys, "path", list(sys.path))
    source = (PLUGIN_ROOT / "ansa_mcp_plugin.py").read_text(encoding="utf-8")
    namespace = {"__file__": str(installed_root / "ansa_mcp_plugin.py")}
    exec(compile(source, namespace["__file__"], "exec"), namespace)

    assert namespace["start_bridge"]()["state"] == "online"
    assert namespace["start_bridge"]()["state"] == "online"
    assert namespace["show_bridge_status"]()["state"] == "online"
    assert namespace["stop_bridge"]()["state"] == "offline"
    assert calls == [("start", True), ("stop",)]
    assert str(installed_root) in sys.path
