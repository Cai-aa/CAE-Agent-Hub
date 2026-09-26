from __future__ import annotations

import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
START_WRAPPER = PROJECT_ROOT / "ansa_plugin" / "start_ansa_mcp.py"


def _wrapper_source() -> str:
    return START_WRAPPER.read_text(encoding="utf-8-sig")


def _namespace_without_file() -> dict[str, Any]:
    namespace: dict[str, Any] = {"__name__": "__main__"}
    assert "__file__" not in namespace
    return namespace


def test_start_wrapper_falls_back_to_configured_plugin_root_without_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plugin_root = tmp_path / "installed-plugin"
    plugin_root.mkdir()
    config_path = tmp_path / "bridge.json"
    config_path.write_text(
        json.dumps({"plugin_root": str(plugin_root)}), encoding="utf-8"
    )

    expected_result = {"started": True}
    fake_bridge = ModuleType("ansa_mcp_bridge")
    fake_bridge.start = lambda: expected_result  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ansa_mcp_bridge", fake_bridge)
    monkeypatch.setenv("ANSA_MCP_BRIDGE_CONFIG", str(config_path))
    monkeypatch.setattr(sys, "path", list(sys.path))

    namespace = _namespace_without_file()
    exec(compile(_wrapper_source(), str(START_WRAPPER), "exec"), namespace)

    assert namespace["START_RESULT"] is expected_result
    assert sys.path[0] == str(plugin_root.resolve())


def test_installed_pointer_overrides_different_process_localappdata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plugin_root = tmp_path / "installed-plugin"
    plugin_root.mkdir()
    config_path = tmp_path / "shared" / "bridge.json"
    config_path.parent.mkdir()
    config_path.write_text(
        json.dumps({"plugin_root": str(plugin_root)}), encoding="utf-8"
    )
    (plugin_root / "bridge_config_path.txt").write_text(
        str(config_path) + "\n", encoding="utf-8"
    )
    monkeypatch.setenv("ANSA_MCP_BRIDGE_CONFIG", str(tmp_path / "wrong.json"))
    monkeypatch.setattr(sys, "path", list(sys.path))
    fake_bridge = ModuleType("ansa_mcp_bridge")
    fake_bridge.start = lambda: {  # type: ignore[attr-defined]
        "config": __import__("os").environ["ANSA_MCP_BRIDGE_CONFIG"]
    }
    monkeypatch.setitem(sys.modules, "ansa_mcp_bridge", fake_bridge)

    namespace = {
        "__name__": "__main__",
        "__file__": str(plugin_root / "start_ansa_mcp.py"),
    }
    exec(compile(_wrapper_source(), str(START_WRAPPER), "exec"), namespace)

    assert namespace["START_RESULT"]["config"] == str(config_path)
    assert sys.path[0] == str(plugin_root)


def test_installed_pointer_rejects_another_plugin_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plugin_root = tmp_path / "installed-plugin"
    plugin_root.mkdir()
    config_path = tmp_path / "bridge.json"
    config_path.write_text(
        json.dumps({"plugin_root": str(tmp_path / "different-plugin")}),
        encoding="utf-8",
    )
    (plugin_root / "bridge_config_path.txt").write_text(
        str(config_path), encoding="utf-8"
    )
    monkeypatch.setenv("ANSA_MCP_BRIDGE_CONFIG", str(config_path))
    namespace = {
        "__name__": "__main__",
        "__file__": str(plugin_root / "start_ansa_mcp.py"),
    }
    with pytest.raises(RuntimeError, match="another plugin root"):
        exec(compile(_wrapper_source(), str(START_WRAPPER), "exec"), namespace)


def test_start_wrapper_records_start_failure_without_leaking_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plugin_root = tmp_path / "installed-plugin"
    plugin_root.mkdir()
    config_path = tmp_path / "bridge.json"
    secret_token = "token-that-must-not-appear-in-startup-log"
    config_path.write_text(
        json.dumps(
            {
                "plugin_root": str(plugin_root),
                "token": secret_token,
            }
        ),
        encoding="utf-8",
    )

    def _fail_start() -> None:
        raise RuntimeError("synthetic bridge startup failure")

    fake_bridge = ModuleType("ansa_mcp_bridge")
    fake_bridge.start = _fail_start  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ansa_mcp_bridge", fake_bridge)
    monkeypatch.setenv("ANSA_MCP_BRIDGE_CONFIG", str(config_path))
    monkeypatch.setattr(sys, "path", list(sys.path))

    namespace = _namespace_without_file()
    with pytest.raises(RuntimeError, match="synthetic bridge startup failure"):
        exec(compile(_wrapper_source(), str(START_WRAPPER), "exec"), namespace)

    error_log = config_path.with_name("startup-error.log")
    assert Path(namespace["ERROR_LOG"]) == error_log
    contents = error_log.read_text(encoding="utf-8")
    assert "synthetic bridge startup failure" in contents
    assert secret_token not in contents
