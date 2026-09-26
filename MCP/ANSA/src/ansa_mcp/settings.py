from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    workspace: Path
    installation_root: Path | None
    executable: Path | None

    @classmethod
    def from_env(cls) -> "Settings":
        workspace = Path(
            os.environ.get("ANSA_MCP_WORKSPACE", str(PACKAGE_ROOT / "workspace"))
        ).expanduser().resolve()
        raw_home = os.environ.get("ANSA_HOME", "").strip()
        raw_executable = os.environ.get("ANSA_EXECUTABLE", "").strip()
        return cls(
            workspace=workspace,
            installation_root=Path(raw_home).expanduser().resolve() if raw_home else None,
            executable=(
                Path(raw_executable).expanduser().resolve() if raw_executable else None
            ),
        )

    def ensure(self) -> None:
        self.workspace.mkdir(parents=True, exist_ok=True)


def within(path: Path, root: Path) -> Path:
    resolved = path.expanduser().resolve()
    allowed = root.expanduser().resolve()
    try:
        resolved.relative_to(allowed)
    except ValueError as exc:
        raise ValueError(f"Path is outside the allowed workspace: {resolved}") from exc
    return resolved


def safe_relative_path(value: str, *, suffix: str | None = None) -> Path:
    candidate = Path(value)
    if candidate.is_absolute() or not candidate.parts or ".." in candidate.parts:
        raise ValueError("path must be relative and must not contain parent traversal")
    if any(part in {"", ".", ".."} for part in candidate.parts):
        raise ValueError("path contains an invalid segment")
    if any(char in str(candidate) for char in '<>:"|?*'):
        raise ValueError("path contains characters that are invalid on Windows")
    if suffix and candidate.suffix.lower() != suffix.lower():
        candidate = candidate.with_suffix(suffix)
    return candidate

