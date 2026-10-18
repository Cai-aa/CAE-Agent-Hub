from __future__ import annotations

import os
import re
import shutil
import tomllib
from dataclasses import dataclass
from pathlib import Path


DEFAULT_CONFIG = Path.home() / ".adams-mcp" / "config.toml"


@dataclass(frozen=True)
class Settings:
    adams_root: Path
    launcher: Path
    release: str
    workspace: Path
    live_host: str = "127.0.0.1"
    live_port: int = 5002
    connect_timeout_sec: float = 5.0
    command_timeout_sec: float = 30.0
    batch_timeout_sec: float = 300.0
    raw_commands_enabled: bool = False

    def __post_init__(self) -> None:
        # Windows temporary directories may use an 8.3 alias; compare canonical paths.
        object.__setattr__(self, "workspace", self.workspace.expanduser().resolve())

    @classmethod
    def load(cls, config_path: Path | None = None) -> "Settings":
        config_path = config_path or Path(os.getenv("ADAMS_MCP_CONFIG", DEFAULT_CONFIG))
        data: dict[str, object] = {}
        if config_path.is_file():
            with config_path.open("rb") as handle:
                data = tomllib.load(handle)

        root_value = os.getenv("ADAMS_ROOT") or data.get("adams_root") or ""
        launcher_value = os.getenv("ADAMS_LAUNCHER") or data.get("launcher") or ""
        release = str(os.getenv("ADAMS_RELEASE") or data.get("release") or "unknown")
        workspace_value = os.getenv("ADAMS_MCP_WORKSPACE") or data.get("workspace")

        launcher = Path(str(launcher_value)).expanduser() if launcher_value else _discover_launcher()
        if root_value:
            root = Path(str(root_value)).expanduser()
        elif launcher:
            root = launcher.parent.parent
        else:
            root = Path()

        workspace = Path(str(workspace_value)).expanduser() if workspace_value else Path.home() / "Documents" / "AdamsMCP" / "workspace"
        host = str(data.get("live_host", "127.0.0.1"))
        if host not in {"127.0.0.1", "localhost"}:
            raise ValueError("live_host must be localhost; remote Command Server connections are disabled")

        settings = cls(
            adams_root=root.resolve() if str(root) else root,
            launcher=launcher.resolve() if launcher else Path(),
            release=release,
            workspace=workspace.resolve(),
            live_host="127.0.0.1",
            live_port=int(os.getenv("ADAMS_COMMAND_SERVER_PORT") or data.get("live_port", 5002)),
            connect_timeout_sec=float(data.get("connect_timeout_sec", 5.0)),
            command_timeout_sec=float(data.get("command_timeout_sec", 30.0)),
            batch_timeout_sec=float(data.get("batch_timeout_sec", 300.0)),
            raw_commands_enabled=str(os.getenv("ADAMS_MCP_RAW_COMMANDS", data.get("raw_commands_enabled", False))).lower() in {"1", "true", "yes", "on"},
        )
        settings.workspace.mkdir(parents=True, exist_ok=True)
        (settings.workspace / "projects").mkdir(exist_ok=True)
        (settings.workspace / "runs").mkdir(exist_ok=True)
        return settings


def _discover_launcher() -> Path:
    env = os.getenv("ADAMS_LAUNCHER")
    if env and Path(env).is_file():
        return Path(env)
    located = shutil.which("adams2024_1.bat") or shutil.which("mdi.bat")
    if located:
        return Path(located)
    candidates: list[Path] = []
    for base in (Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "MSC.Software",):
        if base.exists():
            candidates.extend(base.glob("**/bin/adams*.bat"))
            candidates.extend(base.glob("**/common/mdi.bat"))
    return sorted(candidates, key=lambda item: _version_key(item.name), reverse=True)[0] if candidates else Path()


def _version_key(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", value))
