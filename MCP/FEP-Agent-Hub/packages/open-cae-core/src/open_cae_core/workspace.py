from __future__ import annotations

import re
from pathlib import Path

from .errors import WorkspaceViolation


class WorkspaceGuard:
    def __init__(self, root: str | Path, *, create: bool = True) -> None:
        self.root = Path(root).expanduser().resolve()
        if create:
            self.root.mkdir(parents=True, exist_ok=True)

    def resolve(
        self,
        value: str | Path,
        *,
        allowed_extensions: set[str] | None = None,
        must_exist: bool = False,
    ) -> Path:
        raw = str(value)
        if raw.startswith("\\\\") or raw.startswith("//"):
            raise WorkspaceViolation("UNC paths are disabled")
        candidate = Path(value)
        if not candidate.is_absolute():
            candidate = self.root / candidate
        resolved = candidate.resolve(strict=False)
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise WorkspaceViolation(f"Path escapes workspace: {value}") from exc
        if allowed_extensions and resolved.suffix.lower() not in {
            extension.lower() for extension in allowed_extensions
        }:
            raise WorkspaceViolation(f"Extension not allowed: {resolved.suffix}")
        if must_exist and not resolved.exists():
            raise WorkspaceViolation(f"Path does not exist: {resolved}")
        return resolved

    def relative(self, path: str | Path) -> str:
        resolved = Path(path).resolve()
        try:
            return resolved.relative_to(self.root).as_posix()
        except ValueError as exc:
            raise WorkspaceViolation(f"Path escapes workspace: {path}") from exc

    def ensure_project(self, project: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", project):
            raise WorkspaceViolation("Project name must be a safe single path segment")
        root = self.resolve(project)
        for child in ("geometry", "mesh", "solver", "results", "post", "evidence"):
            (root / child).mkdir(parents=True, exist_ok=True)
        return root

