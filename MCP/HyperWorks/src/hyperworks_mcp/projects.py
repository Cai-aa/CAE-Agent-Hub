from __future__ import annotations

import json
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from .security import validate_tcl
from .settings import PROJECT_ID_RE, Settings, safe_filename, within


def _write_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


class ProjectService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def create(self, name: str) -> dict[str, Any]:
        clean = name.strip()
        if not clean or len(clean) > 120:
            raise ValueError("Project name must contain 1 to 120 characters")
        project_id = (
            "project_" + time.strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
        )
        root = self.settings.workspace / "projects" / project_id
        for child in ("input", "scripts", "output", "runs"):
            (root / child).mkdir(parents=True, exist_ok=True)
        manifest = {
            "project_id": project_id,
            "name": clean,
            "root": str(root),
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "files": [],
            "scripts": [],
        }
        _write_json(root / "project.json", manifest)
        return manifest

    def root(self, project_id: str) -> Path:
        if not PROJECT_ID_RE.fullmatch(project_id):
            raise ValueError("Invalid project_id")
        root = within(
            self.settings.workspace / "projects" / project_id,
            self.settings.workspace / "projects",
        )
        if not (root / "project.json").is_file():
            raise ValueError(f"Project not found: {project_id}")
        return root

    def manifest(self, project_id: str) -> dict[str, Any]:
        root = self.root(project_id)
        value = json.loads((root / "project.json").read_text(encoding="utf-8"))
        value["files"] = [
            path.relative_to(root).as_posix()
            for path in sorted((root / "input").rglob("*"))
            if path.is_file()
        ]
        value["scripts"] = [
            path.relative_to(root).as_posix()
            for path in sorted((root / "scripts").glob("*.tcl"))
            if path.is_file() and not path.name.startswith("__mcp_")
        ]
        return value

    def import_file(
        self, project_id: str, source_file: str, destination_name: str | None
    ) -> dict[str, Any]:
        source = Path(source_file).expanduser().resolve()
        if not source.is_file():
            raise ValueError(f"Source file not found: {source}")
        if source.stat().st_size > 20 * 1024**3:
            raise ValueError("Source file exceeds the 20 GB import limit")
        name = safe_filename(destination_name or source.name)
        target = within(self.root(project_id) / "input" / name, self.root(project_id))
        if target.exists():
            raise ValueError(f"Destination already exists: {target.name}")
        shutil.copy2(source, target)
        return {
            "project_id": project_id,
            "source": str(source),
            "imported_file": str(target),
            "size_bytes": target.stat().st_size,
        }

    def write_tcl(self, project_id: str, name: str, content: str) -> dict[str, Any]:
        validation = validate_tcl(content)
        filename = safe_filename(name, ".tcl")
        root = self.root(project_id)
        target = within(root / "scripts" / filename, root)
        target.write_text(content.replace("\r\n", "\n"), encoding="utf-8")
        return {
            "project_id": project_id,
            "script_file": str(target),
            **validation,
        }

    def script(self, project_id: str, name: str) -> Path:
        filename = safe_filename(name, ".tcl")
        root = self.root(project_id)
        path = within(root / "scripts" / filename, root)
        if not path.is_file():
            raise ValueError(f"Tcl script not found: {filename}")
        return path

    def input_file(self, project_id: str, name: str) -> Path:
        filename = safe_filename(name)
        root = self.root(project_id)
        path = within(root / "input" / filename, root)
        if not path.is_file():
            raise ValueError(f"Input file not found: {filename}")
        return path
