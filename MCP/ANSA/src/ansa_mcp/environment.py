from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Iterable

from .settings import Settings


LAUNCHER_NAMES = ("ansa64.bat", "ansa.bat", "ansa64.exe", "ansa.exe")


def _candidate_roots(settings: Settings) -> Iterable[Path]:
    seen: set[Path] = set()

    def emit(path: Path | None):
        if path is None:
            return
        resolved = path.expanduser().resolve()
        if resolved not in seen:
            seen.add(resolved)
            yield resolved

    yield from emit(settings.installation_root)
    if settings.executable:
        yield from emit(settings.executable.parent)

    for name in ("BETA_CAE_HOME", "ANSA_ROOT"):
        raw = os.environ.get(name, "").strip()
        if raw:
            yield from emit(Path(raw))

    bases = [
        Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "BETA_CAE_Systems",
        Path(os.environ.get("ProgramW6432", "C:/Program Files")) / "BETA_CAE_Systems",
        Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local"))) / "Programs/BETA_CAE_Systems",
    ]
    for base in bases:
        if not base.is_dir():
            continue
        for child in sorted(base.glob("ansa_v*"), key=lambda p: tuple(int(x) for x in re.findall(r"\d+", p.name)), reverse=True):
            if child.is_dir():
                yield from emit(child)


def find_launcher(settings: Settings) -> Path | None:
    if settings.executable and settings.executable.is_file():
        return settings.executable
    for root in _candidate_roots(settings):
        if root.is_file():
            return root
        for name in LAUNCHER_NAMES:
            candidate = root / name
            if candidate.is_file():
                return candidate
    return None


def find_installation(settings: Settings) -> Path | None:
    launcher = find_launcher(settings)
    if launcher:
        return launcher.parent
    for root in _candidate_roots(settings):
        if root.is_dir():
            return root
    return None


def environment_report(settings: Settings) -> dict:
    installation = find_installation(settings)
    launcher = find_launcher(settings)
    docs = (
        installation / "docs" / "extending" / "python_api" / "html"
        if installation
        else None
    )
    remote_control = (
        installation / "scripts" / "RemoteControl" / "ansa" / "AnsaProcessModule.py"
        if installation
        else None
    )
    return {
        "installation_root": str(installation) if installation else None,
        "launcher": str(launcher) if launcher else None,
        "python_api_docs": str(docs) if docs and docs.is_dir() else None,
        "official_iap_client": (
            str(remote_control) if remote_control and remote_control.is_file() else None
        ),
        "workspace": str(settings.workspace),
        "installation_policy": "Windows; ANSA_HOME/ANSA_EXECUTABLE select nonstandard drive or version. No user-specific drive assumptions.",
        "capabilities": {
            "installation_detected": bool(installation),
            "launcher_detected": bool(launcher),
            "python_api_docs_detected": bool(docs and docs.is_dir()),
            "official_iap_detected": bool(
                remote_control and remote_control.is_file()
            ),
            "official_iap_enabled": False,
            "live_authenticated_bridge": False,
        },
        "official_iap_policy": {
            "enabled": False,
            "reason": (
                "ANSA Listener/IAP accepts remote Python script text/files and does not "
                "provide this MCP's challenge-bound HMAC authentication, named methods, "
                "or explicit per-step confirmation."
            ),
        },
    }

