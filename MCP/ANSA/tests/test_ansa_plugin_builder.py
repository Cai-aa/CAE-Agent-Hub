"""Offline checks for the machine-specific ANSA Plugin Manager candidate."""

from __future__ import annotations

import sys
import gc
import weakref
from pathlib import Path
from types import ModuleType

import pytest

from build_ansa_plugin import render_descriptor


def test_rendered_descriptor_uses_fixed_entry_and_three_buttons(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    entry = tmp_path / "ansa_mcp_plugin.py"
    entry.write_text("# entry\n", encoding="utf-8")
    captured = []
    ansa = ModuleType("ansa")
    ansa.session = ModuleType("ansa.session")  # type: ignore[attr-defined]
    # The real v25.1.2 API borrows the object; a strong reference in the mock
    # would hide the use-after-free regression that crashed Plugin Manager.
    ansa.session.setPluginInfos = lambda info: captured.append(weakref.ref(info))  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ansa", ansa)

    descriptor = render_descriptor(entry)
    assert "__ANSA_MCP_ENTRY_PATH__" not in descriptor
    namespace = {}
    exec(compile(descriptor, "ANSA_MCP_Bridge.ppl", "exec"), namespace)
    gc.collect()

    assert len(captured) == 1
    info = captured[0]()
    assert info is not None, "ANSA retains a borrowed reference to plugin metadata"
    assert Path(info.filepath) == entry.resolve()
    assert set(info.Buttons) == {
        "ANSA MCP:::Start",
        "ANSA MCP:::Status",
        "ANSA MCP:::Stop",
    }


def test_rendered_descriptor_requires_exact_existing_entry(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        render_descriptor(tmp_path / "ansa_mcp_plugin.py")
    other = tmp_path / "other.py"
    other.write_text("", encoding="utf-8")
    with pytest.raises(ValueError):
        render_descriptor(other)
