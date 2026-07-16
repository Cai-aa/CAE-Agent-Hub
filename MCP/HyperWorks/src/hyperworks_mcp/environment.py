from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from .settings import Settings


RELATIVE_TOOLS = {
    "runhwx": Path("hwdesktop/hwx/bin/win64/runhwx.exe"),
    "hmbatch": Path("hwdesktop/hm/bin/win64/hmbatch.exe"),
    "hmbatch_fallback": Path("hwdesktop/hw/bin/win64/hmbatch.exe"),
    "hyperstudy_batch": Path("hwdesktop/hst/bin/win64/hstbatch.exe"),
    "framework_hwx": Path("common/framework/win64/hwx/bin/win64/hwx.exe"),
    "optistruct": Path("hwsolvers/scripts/optistruct.bat"),
    "radioss": Path("hwsolvers/scripts/radioss.bat"),
}


def normalize_installation_root(path: Path) -> Path:
    candidate = path.expanduser().resolve()
    if candidate.is_file():
        candidate = candidate.parent
    for current in (candidate, *candidate.parents):
        if (current / "hwdesktop").is_dir() and (
            (current / "common").is_dir() or (current / "hwsolvers").is_dir()
        ):
            return current
    return candidate


def _candidate_roots(settings: Settings) -> Iterable[Path]:
    seen: set[str] = set()
    raw_candidates: list[Path] = []
    for key in ("HYPERWORKS_HOME", "ALTAIR_HOME"):
        value = os.environ.get(key, "").strip()
        if value:
            raw_candidates.append(Path(value))
    if settings.installation_root:
        raw_candidates.append(settings.installation_root)
    standard_bases: list[Path] = []
    for key in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)"):
        value = os.environ.get(key, "").strip()
        if value:
            standard_bases.append(Path(value) / "Altair")
    system_drive = os.environ.get("SystemDrive", "").strip()
    if system_drive:
        standard_bases.append(Path(system_drive + "\\") / "Altair")

    for base in standard_bases:
        if base.is_dir():
            raw_candidates.extend(
                sorted(
                    (item for item in base.iterdir() if item.is_dir()),
                    key=lambda item: item.name,
                    reverse=True,
                )
            )
    for raw in raw_candidates:
        root = normalize_installation_root(raw)
        key = os.path.normcase(str(root))
        if key not in seen:
            seen.add(key)
            yield root


def discover_installation(settings: Settings) -> Path | None:
    for root in _candidate_roots(settings):
        if any((root / rel).is_file() for rel in RELATIVE_TOOLS.values()):
            return root
    return None


def _external_solver(env_name: str) -> Path | None:
    value = os.environ.get(env_name, "").strip()
    if not value:
        return None
    path = Path(value).expanduser().resolve()
    return path if path.is_file() else None


def tool_paths(settings: Settings) -> dict[str, Path | None]:
    root = discover_installation(settings)
    found: dict[str, Path | None] = {name: None for name in RELATIVE_TOOLS}
    if root:
        for name, relative in RELATIVE_TOOLS.items():
            candidate = root / relative
            found[name] = candidate if candidate.is_file() else None
    if not found["hmbatch"]:
        found["hmbatch"] = found["hmbatch_fallback"]
    found["optistruct"] = _external_solver("OPTISTRUCT_EXECUTABLE") or found[
        "optistruct"
    ]
    found["radioss"] = _external_solver("RADIOSS_EXECUTABLE") or found["radioss"]
    return found


def environment_report(settings: Settings) -> dict:
    root = discover_installation(settings)
    paths = tool_paths(settings)
    solver_available = bool(paths["optistruct"] or paths["radioss"])
    notes: list[str] = []
    if root and not solver_available:
        notes.append(
            "HyperMesh Desktop is available, but no OptiStruct or Radioss launcher was found. "
            "Install HyperWorks Solvers or set OPTISTRUCT_EXECUTABLE/RADIOSS_EXECUTABLE."
        )
    if not root:
        notes.append("No HyperWorks installation was detected. Set HYPERWORKS_HOME.")
    return {
        "installation_root": str(root) if root else None,
        "workspace": str(settings.workspace),
        "workspace_writable": settings.workspace.is_dir() and os.access(settings.workspace, os.W_OK),
        "tools": {
            name: {"available": bool(path), "path": str(path) if path else None}
            for name, path in paths.items()
            if name != "hmbatch_fallback"
        },
        "capabilities": {
            "launch_hypermesh_gui": bool(paths["runhwx"]),
            "run_hypermesh_batch_tcl": bool(paths["hmbatch"]),
            "run_hyperstudy_batch": bool(paths["hyperstudy_batch"]),
            "run_optistruct": bool(paths["optistruct"]),
            "run_radioss": bool(paths["radioss"]),
            "live_python_bridge": False,
        },
        "notes": notes,
    }
