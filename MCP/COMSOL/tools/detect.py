from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from .mph_session import mph_availability


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNS_DIR = ROOT / "comsol_runs"


def _path_from_env(*names: str) -> Path | None:
    for name in names:
        value = os.environ.get(name)
        if value and value.strip():
            path = Path(value.strip()).expanduser()
            if path.exists():
                return path.resolve()
    return None


def _which(name: str) -> Path | None:
    found = shutil.which(name)
    return Path(found).resolve() if found else None


def _first_existing(candidates: list[Path]) -> Path | None:
    for candidate in candidates:
        try:
            if candidate.exists():
                return candidate.resolve()
        except OSError:
            continue
    return None


def _find_under(base: Path, names: set[str], max_depth: int = 5) -> dict[str, Path]:
    found: dict[str, Path] = {}
    if not base.exists() or not base.is_dir():
        return found

    base_parts = len(base.parts)
    try:
        for path in base.rglob("*"):
            if len(path.parts) - base_parts > max_depth:
                continue
            if path.name.lower() in names and path.is_file():
                found.setdefault(path.name.lower(), path.resolve())
    except OSError:
        return found
    return found


def common_comsol_roots() -> list[Path]:
    roots: list[Path] = []
    for env_name in ("COMSOL_ROOT", "COMSOL_HOME"):
        value = os.environ.get(env_name)
        if value:
            roots.append(Path(value).expanduser())

    roots.extend(
        [
            Path("C:/Program Files/COMSOL"),
            Path("C:/Program Files (x86)/COMSOL"),
            Path("G:/Program Files/COMSOL"),
            Path("/usr/local/comsol"),
            Path("/opt/comsol"),
        ]
    )
    return roots


def _installation_roots() -> list[Path]:
    roots: list[Path] = []
    for root in common_comsol_roots():
        roots.append(root)
        if root.name.lower() == "multiphysics":
            continue
        try:
            for child in root.iterdir():
                candidate = child / "Multiphysics"
                if candidate.exists():
                    roots.append(candidate)
        except OSError:
            continue
    deduped: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root).lower()
        if key not in seen:
            deduped.append(root)
            seen.add(key)
    return deduped


def find_comsol_root() -> Path | None:
    explicit = _path_from_env("COMSOL_ROOT", "COMSOL_HOME")
    if explicit:
        return explicit

    comsol_exe = find_comsol_exe()
    if comsol_exe:
        parts = list(comsol_exe.parents)
        for parent in parts:
            if parent.name.lower() == "multiphysics":
                return parent
        if len(parts) >= 3:
            return parts[2]
    return _first_existing(
        [root for root in _installation_roots() if root.name.lower() == "multiphysics" and root.exists()]
    )


def _executable_candidates(root: Path | None, exe_name: str) -> list[Path]:
    candidates: list[Path] = []
    if root:
        candidates.extend(
            [
                root / "bin" / "win64" / exe_name,
                root / "bin" / exe_name,
                root / "Multiphysics" / "bin" / "win64" / exe_name,
                root / "Multiphysics" / "bin" / exe_name,
            ]
        )
    return candidates


def find_comsol_exe() -> Path | None:
    explicit = _path_from_env("COMSOL_EXE")
    if explicit:
        return explicit
    on_path = _which("comsol.exe") or _which("comsol")
    if on_path:
        return on_path

    for root in _installation_roots():
        direct = _first_existing(_executable_candidates(root, "comsol.exe") + _executable_candidates(root, "comsol"))
        if direct:
            return direct
        found = _find_under(root, {"comsol.exe", "comsol"}, max_depth=4)
        if found:
            return next(iter(found.values()))
    return None


def find_comsolbatch_exe() -> Path | None:
    explicit = _path_from_env("COMSOLBATCH_EXE", "COMSOL_BATCH_EXE")
    if explicit:
        return explicit
    on_path = _which("comsolbatch.exe") or _which("comsolbatch")
    if on_path:
        return on_path

    root = find_comsol_root()
    direct = _first_existing(_executable_candidates(root, "comsolbatch.exe") + _executable_candidates(root, "comsolbatch"))
    if direct:
        return direct
    return None


def find_mphserver_exe() -> Path | None:
    explicit = _path_from_env("COMSOL_MPHSERVER_EXE", "MPHSERVER_EXE")
    if explicit:
        return explicit
    on_path = _which("comsolmphserver.exe") or _which("mphserver.exe") or _which("mphserver")
    if on_path:
        return on_path

    root = find_comsol_root()
    direct = _first_existing(_executable_candidates(root, "comsolmphserver.exe") + _executable_candidates(root, "mphserver.exe") + _executable_candidates(root, "mphserver"))
    if direct:
        return direct
    return None


def find_java_exe() -> Path | None:
    explicit = _path_from_env("JAVA_EXE")
    if explicit:
        return explicit
    root = find_comsol_root()
    candidates: list[Path] = []
    if root:
        candidates.extend(
            [
                root / "java" / "win64" / "jre" / "bin" / "java.exe",
                root / "java" / "win64" / "bin" / "java.exe",
                root / "java" / "glnxa64" / "jre" / "bin" / "java",
                root / "java" / "maci64" / "jre" / "bin" / "java",
            ]
        )
    return _first_existing(candidates) or _which("java.exe") or _which("java")


def find_api_jars(root: Path | None = None) -> list[str]:
    root = root or find_comsol_root()
    if not root or not root.exists():
        return []

    likely_names = {
        "comsol.jar",
        "comsolclient.jar",
        "comsolmodel.jar",
        "comsolapi.jar",
        "mph.jar",
        "com.comsol.api_1.0.0.jar",
        "com.comsol.clientapi_1.0.0.jar",
        "com.comsol.client_1.0.0.jar",
        "com.comsol.communication_1.0.0.jar",
        "com.comsol.model_1.0.0.jar",
        "com.comsol.mph_1.0.0.jar",
        "com.comsol.nativebasicutil_1.0.0.jar",
        "com.comsol.nativejni_1.0.0.jar",
        "com.comsol.nativemph_1.0.0.jar",
        "com.comsol.nativeutil_1.0.0.jar",
        "com.comsol.systemutils_1.0.0.jar",
        "com.comsol.util_1.0.0.jar",
    }
    jars: list[Path] = []
    for subdir in ("apiplugins", "plugins", "mli", "java", "bin"):
        base = root / subdir
        if not base.exists():
            continue
        try:
            jars.extend(
                path.resolve()
                for path in base.glob("*.jar")
                if path.name.lower() in likely_names
            )
        except OSError:
            continue

    if not jars:
        try:
            jars = [path.resolve() for path in root.rglob("*.jar") if path.name.lower() in likely_names]
        except OSError:
            jars = []
    return [str(path) for path in sorted(set(jars))]


def runs_dir() -> Path:
    value = os.environ.get("COMSOL_MCP_RUNS_DIR")
    return Path(value).expanduser().resolve() if value else DEFAULT_RUNS_DIR


def detect_comsol_environment() -> dict[str, Any]:
    root = find_comsol_root()
    comsol_exe = find_comsol_exe()
    batch_exe = find_comsolbatch_exe()
    mphserver_exe = find_mphserver_exe()
    java_exe = find_java_exe()
    api_jars = find_api_jars(root)

    return {
        "comsol_root": str(root) if root else None,
        "comsol_exe": str(comsol_exe) if comsol_exe else None,
        "comsolbatch_exe": str(batch_exe) if batch_exe else None,
        "mphserver_exe": str(mphserver_exe) if mphserver_exe else None,
        "java_exe": str(java_exe) if java_exe else None,
        "api_jars": api_jars,
        "api_jars_found": bool(api_jars),
        "runs_dir": str(runs_dir()),
        "bridge_command": os.environ.get("COMSOL_MCP_BRIDGE_COMMAND") or None,
        "bridge_jar": os.environ.get("COMSOL_MCP_BRIDGE_JAR") or None,
        "mph": mph_availability(),
        "available": bool(comsol_exe or batch_exe or mphserver_exe),
        "notes": [
            "License availability is not asserted by detection; validate by starting a bridge or COMSOL job.",
        ],
    }
