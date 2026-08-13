from __future__ import annotations

from pathlib import Path
from typing import Any

from open_cae_core.config import OpenCAEConfig
from open_cae_core.discovery import command_version, extract_version, first_executable


def probe_freecad(config: OpenCAEConfig) -> dict[str, Any]:
    cmd = first_executable(
        [
            config.executable("freecad", "cmd"),
            "FreeCADCmd.exe",
            Path("E:/FreeCAD/bin/FreeCADCmd.exe"),
            Path("C:/Program Files/FreeCAD 1.1/bin/FreeCADCmd.exe"),
        ]
    )
    gui = first_executable(
        [
            config.executable("freecad", "exe"),
            "FreeCAD.exe",
            cmd.with_name("FreeCAD.exe") if cmd else None,
            Path("E:/FreeCAD/bin/FreeCAD.exe"),
        ]
    )
    version_output = command_version(cmd, ["--version"])
    return {
        "freecad_exe": str(gui) if gui else None,
        "freecadcmd_exe": str(cmd) if cmd else None,
        "version": extract_version(version_output),
        "version_output": version_output,
        "headless_ok": bool(cmd),
        "gui_available": bool(gui),
        "live_bridge": False,
    }

