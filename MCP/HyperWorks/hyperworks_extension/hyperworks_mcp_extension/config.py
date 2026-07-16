from __future__ import annotations

import json
import os
import secrets
from pathlib import Path


def default_config_path() -> Path:
    override = os.environ.get("HYPERWORKS_MCP_BRIDGE_CONFIG", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    local = os.environ.get("LOCALAPPDATA", "").strip()
    base = Path(local) if local else Path.home() / "AppData" / "Local"
    return base / "HyperWorksMCP" / "bridge.json"


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
    temporary.replace(path)


def load_config(path: Path | None = None) -> tuple[Path, dict]:
    target = (path or default_config_path()).expanduser().resolve()
    if target.is_file():
        value = json.loads(target.read_text(encoding="utf-8-sig"))
    else:
        value = {
            "version": 1,
            "host": "127.0.0.1",
            "port": 48761,
            "token": secrets.token_hex(32),
            "allowed_roots": [],
            "request_timeout_seconds": 600,
        }
        _write_json(target, value)
    if value.get("host") != "127.0.0.1":
        raise ValueError("Bridge host must be 127.0.0.1")
    port = int(value.get("port", 0))
    if not 1024 <= port <= 65535:
        raise ValueError("Bridge port must be between 1024 and 65535")
    token = str(value.get("token", ""))
    if len(token) < 32:
        raise ValueError("Bridge token must contain at least 32 characters")
    roots = []
    for item in value.get("allowed_roots", []):
        root = Path(item).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        roots.append(str(root))
    value.update(
        {
            "port": port,
            "token": token,
            "allowed_roots": roots,
            "request_timeout_seconds": max(
                10, min(int(value.get("request_timeout_seconds", 600)), 3600)
            ),
        }
    )
    return target, value


def write_status(config_path: Path, value: dict) -> None:
    _write_json(config_path.with_name("status.json"), value)
