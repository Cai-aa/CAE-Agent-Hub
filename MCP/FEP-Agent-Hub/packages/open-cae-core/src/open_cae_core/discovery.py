from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Iterable


def first_executable(candidates: Iterable[str | Path | None]) -> Path | None:
    for value in candidates:
        if not value:
            continue
        candidate = Path(value).expanduser()
        if candidate.is_file():
            return candidate.resolve()
        located = shutil.which(str(value))
        if located:
            return Path(located).resolve()
    return None


def command_version(
    exe: Path | None,
    args: list[str],
    *,
    timeout: float = 15,
) -> str | None:
    if not exe:
        return None
    import subprocess

    try:
        result = subprocess.run(
            [str(exe), *args],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            errors="replace",
            shell=False,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    output = "\n".join(part for part in (result.stdout, result.stderr) if part).strip()
    return output or None


def extract_version(text: str | None) -> str | None:
    if not text:
        return None
    match = re.search(r"(?i)(?:version[: ]+|version\s*=\s*)?v?(\d+\.\d+(?:\.\d+)?(?:[-\w.]*)?)", text)
    return match.group(1) if match else None


def windows_drive_candidates(*relative_paths: str) -> list[Path]:
    candidates: list[Path] = []
    for drive in ("C:", "D:", "E:", "F:"):
        if not Path(drive + "\\").exists():
            continue
        candidates.extend(Path(drive + "\\") / relative for relative in relative_paths)
    return candidates
