import json
import shutil
import sys
import zipfile
from pathlib import Path
from types import ModuleType
from types import SimpleNamespace

import pytest

from build_ansa_plugin_package import build_package


def test_package_relocates_and_dispatches_future_enabled_bridge(tmp_path, monkeypatch):
    bridge = tmp_path / "bridge" / "ansa_mcp_plugin.py"
    bridge.parent.mkdir()
    bridge.write_text(
        "from __future__ import annotations\n"
        "def start_bridge(): return 'started'\n"
        "def show_bridge_status(): return 'status'\n"
        "def stop_bridge(): return 'stopped'\n",
        encoding="utf-8",
    )
    result = build_package(bridge, tmp_path / "package")
    with zipfile.ZipFile(result["archive"]) as bundle:
        assert bundle.testzip() is None
        assert "ANSA_MCP_Bridge/src/ansa_mcp_ui.py" in bundle.namelist()
    relocated = tmp_path / "relocated"
    shutil.move(result["directory"], relocated)
    ansa = ModuleType("ansa")
    ansa.session = ModuleType("ansa.session")
    ansa.session.setPluginInfos = lambda info: None
    monkeypatch.setitem(sys.modules, "ansa", ansa)
    descriptor = relocated / "ANSA_MCP_Bridge.ppl"
    namespace = {"__file__": str(descriptor)}
    exec(compile(descriptor.read_text(), str(descriptor), "exec"), namespace)
    callback = Path(namespace["x"].filepath)
    assert callback.is_relative_to(relocated)
    calls = {"__file__": str(callback)}
    exec(compile("_injected = True\n" + callback.read_text(), str(callback), "exec"), calls)
    assert calls["_bridge_module"]().start_bridge() == "started"
    assert calls["_bridge_module"]().show_bridge_status() == "status"
    assert calls["_bridge_module"]().stop_bridge() == "stopped"
    assert (callback.parent / "ansa_mcp_bridge/dashboard.py").is_file()
    assert (callback.parent / "ansa_mcp_bridge/monitor.py").is_file()
    manifest = json.loads((relocated / "manifest.json").read_text())
    assert manifest["credentials_included"] is False
    assert manifest["runtime_bundled"] is True
    assert manifest["version"] == "0.5.0"


def test_package_refuses_overwrite(tmp_path):
    entry = tmp_path / "ansa_mcp_plugin.py"
    entry.write_text("", encoding="utf-8")
    output = tmp_path / "existing"
    output.mkdir()
    with pytest.raises(FileExistsError):
        build_package(entry, output)


def test_portable_package_has_no_machine_path_and_requires_existing_config(tmp_path, monkeypatch):
    result = build_package(None, tmp_path / "portable", minimum_ansa_version="24.0.0")
    assert result["manifest"]["bridge_entry"] is None
    assert result["manifest"]["portable_configuration"] is True
    folder = Path(result["directory"])
    descriptor = (folder / "ANSA_MCP_Bridge.ppl").read_text(encoding="utf-8")
    assert 'minHostApplicationVersion = "v24.0.0"' in descriptor
    ui = folder / "ANSA_MCP_Bridge/src/ansa_mcp_ui.py"
    source = ui.read_text(encoding="utf-8")
    assert "_BRIDGE_ENTRY = None" in source
    monkeypatch.setenv("ANSA_MCP_BRIDGE_CONFIG", str(tmp_path / "missing.json"))
    namespace = {"__file__": str(ui)}
    exec(compile(source, str(ui), "exec"), namespace)
    with pytest.raises(RuntimeError, match="configuration missing"):
        namespace["_runtime_module"]()
    assert not (tmp_path / "missing.json").exists()


def test_bridge_source_parses_with_python39_grammar():
    import ast
    source = Path(__file__).resolve().parents[1] / "ansa_plugin/ansa_mcp_bridge"
    for file in source.glob("*.py"):
        ast.parse(file.read_text(encoding="utf-8"), filename=str(file), feature_version=(3, 9))


def test_bundled_runtime_is_loaded_and_live_legacy_runtime_is_rejected(tmp_path, monkeypatch):
    entry = tmp_path / "ansa_mcp_plugin.py"
    entry.write_text("def _configure_bridge(): pass\n", encoding="utf-8")
    result = build_package(entry, tmp_path / "package")
    ui = Path(result["directory"]) / "ANSA_MCP_Bridge/src/ansa_mcp_ui.py"
    namespace = {"__file__": str(ui)}
    exec(compile(ui.read_text(encoding="utf-8"), str(ui), "exec"), namespace)
    monkeypatch.delitem(sys.modules, "_ansa_mcp_bundled_runtime_050", raising=False)
    monkeypatch.setitem(sys.modules, "ansa_mcp_bridge", SimpleNamespace(status=lambda: {"state": "offline"}))
    bundled = namespace["_runtime_module"]()
    assert bundled.__file__.startswith(str(ui.parent))
    assert bundled.status()["state"] == "offline"
    monkeypatch.setitem(sys.modules, "ansa_mcp_bridge", SimpleNamespace(status=lambda: {"state": "online"}))
    with pytest.raises(RuntimeError, match="restart ANSA"):
        namespace["_runtime_module"]()
