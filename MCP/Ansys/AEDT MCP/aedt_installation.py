from __future__ import annotations

import os
import re
from importlib import metadata
from pathlib import Path
from typing import Any

_ROOT_PATTERN = re.compile(r"^(?:ANSYSEM|AWP)_ROOT(?P<code>\d{3})$")


def _version_from_code(code: str) -> str:
    return f"20{code[:2]}.{int(code[2])}"


def check_aedt_installation() -> dict[str, Any]:
    installed: dict[str, str] = {}
    for key, value in os.environ.items():
        match = _ROOT_PATTERN.fullmatch(key)
        if match is None or not value:
            continue
        root = Path(value)
        if key.startswith("AWP_ROOT"):
            candidates = (root / "AnsysEM", root)
        else:
            candidates = (root,)
        executable = next(
            (
                candidate / "ansysedt.exe"
                for candidate in candidates
                if (candidate / "ansysedt.exe").is_file()
            ),
            None,
        )
        if executable is None:
            continue
        if executable.is_file():
            installed.setdefault(
                _version_from_code(match.group("code")),
                str(executable.parent.resolve()),
            )

    configured = os.environ.get("AEDT_INSTALL_DIR")
    configured_version = os.environ.get("AEDT_VERSION", "configured")
    if configured:
        root = Path(configured)
        executable = (
            root if root.name.lower() == "ansysedt.exe" else root / "ansysedt.exe"
        )
        if executable.is_file():
            installed.setdefault(configured_version, str(executable.parent.resolve()))

    try:
        pyaedt_version = metadata.version("pyaedt")
    except metadata.PackageNotFoundError:
        pyaedt_version = None

    selected = configured_version if configured_version in installed else None
    if selected not in installed:
        selected = next(iter(installed), None)
    return {
        "installed": bool(installed),
        "version": selected,
        "installation_directory": installed.get(selected) if selected else None,
        "installed_versions": installed,
        "pyaedt_version": pyaedt_version,
        "discovery": "environment",
    }
