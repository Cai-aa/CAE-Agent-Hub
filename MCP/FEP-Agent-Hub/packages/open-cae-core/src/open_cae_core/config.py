from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class OpenCAEConfig:
    workspace_root: Path
    config_path: Path | None = None
    security: dict[str, Any] = field(default_factory=dict)
    freecad: dict[str, str] = field(default_factory=dict)
    elmer: dict[str, str] = field(default_factory=dict)
    gmsh: dict[str, str] = field(default_factory=dict)
    paraview: dict[str, str] = field(default_factory=dict)

    def executable(self, section: str, key: str) -> Path | None:
        value = getattr(self, section, {}).get(key, "")
        if not value:
            return None
        candidate = Path(value).expanduser()
        return candidate.resolve() if candidate.exists() else None


def _default_config_path() -> Path:
    explicit = os.environ.get("OPEN_CAE_CONFIG")
    if explicit:
        return Path(explicit).expanduser()
    return Path.home() / ".open-cae" / "config.toml"


def load_config(path: str | Path | None = None) -> OpenCAEConfig:
    config_path = Path(path).expanduser() if path else _default_config_path()
    raw: dict[str, Any] = {}
    if config_path.is_file():
        with config_path.open("rb") as stream:
            raw = tomllib.load(stream)

    workspace_value = os.environ.get("OPEN_CAE_WORKSPACE")
    if not workspace_value:
        workspace_value = raw.get("workspace", {}).get("root")
    if not workspace_value:
        workspace_value = str(Path.cwd() / "workspace")

    return OpenCAEConfig(
        workspace_root=Path(workspace_value).expanduser().resolve(),
        config_path=config_path if config_path.is_file() else None,
        security=dict(raw.get("security", {})),
        freecad=dict(raw.get("freecad", {})),
        elmer=dict(raw.get("elmer", {})),
        gmsh=dict(raw.get("gmsh", {})),
        paraview=dict(raw.get("paraview", {})),
    )

