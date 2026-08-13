from __future__ import annotations

from pathlib import Path
from typing import Any

from open_cae_core.config import OpenCAEConfig
from open_cae_core.discovery import command_version, extract_version, first_executable


def probe_paraview(config: OpenCAEConfig) -> dict[str, Any]:
    base = Path("E:/ParaView/bin")
    pvpython = first_executable([config.executable("paraview", "pvpython"), "pvpython.exe", base / "pvpython.exe"])
    gui = first_executable([config.executable("paraview", "gui"), "paraview.exe", base / "paraview.exe"])
    pvbatch = first_executable([config.executable("paraview", "pvbatch"), "pvbatch.exe", base / "pvbatch.exe"])
    output = command_version(pvpython, ["--version"])
    return {
        "paraview_exe": str(gui) if gui else None,
        "pvpython_exe": str(pvpython) if pvpython else None,
        "pvbatch_exe": str(pvbatch) if pvbatch else None,
        "version": extract_version(output),
        "version_output": output,
        "headless_available": bool(pvpython),
        "pvbatch_optional": True,
        "live_bridge": False,
    }

