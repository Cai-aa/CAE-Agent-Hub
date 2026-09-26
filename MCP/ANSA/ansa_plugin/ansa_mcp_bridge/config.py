from __future__ import annotations

import json
import os
import re
import secrets
from pathlib import Path


TOKEN_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def default_config_path() -> Path:
    override = os.environ.get("ANSA_MCP_BRIDGE_CONFIG", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    local = os.environ.get("LOCALAPPDATA", "").strip()
    base = Path(local) if local else Path.home() / "AppData" / "Local"
    return base / "ANSAMCP" / "bridge.json"


def _default_workspace() -> Path:
    override = os.environ.get("ANSA_MCP_WORKSPACE", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return (Path.home() / "Documents" / "ANSAMCP" / "workspace").resolve()


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False),
        encoding="utf-8",
    )
    temporary.replace(path)


def load_config(path: Path | None = None) -> tuple[Path, dict]:
    target = (path or default_config_path()).expanduser().resolve()
    if target.is_file():
        value = json.loads(target.read_text(encoding="utf-8-sig"))
    else:
        value = {
            "version": 1,
            "host": "127.0.0.1",
            "port": 48762,
            "token": secrets.token_hex(32),
            "allowed_roots": [str(_default_workspace())],
            "request_timeout_seconds": 120,
        }
        write_json(target, value)

    if not isinstance(value, dict):
        raise ValueError("Bridge configuration must be a JSON object")

    if int(value.get("version", 0)) != 1:
        raise ValueError("Unsupported bridge config version")
    if value.get("host") != "127.0.0.1":
        raise ValueError("Bridge host must be 127.0.0.1")
    port = int(value.get("port", 0))
    if not 1024 <= port <= 65535:
        raise ValueError("Bridge port must be between 1024 and 65535")
    token = str(value.get("token", ""))
    if not TOKEN_RE.fullmatch(token):
        raise ValueError("Bridge token must contain exactly 64 hexadecimal characters")

    configured_roots = value.get("allowed_roots")
    if not isinstance(configured_roots, list) or not configured_roots:
        raise ValueError("allowed_roots must be a non-empty list")

    validated_roots = []
    for index, item in enumerate(configured_roots):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(
                f"allowed_roots[{index}] must be a non-empty string"
            )
        candidate = Path(item)
        if not candidate.is_absolute():
            raise ValueError(f"allowed_roots[{index}] must be an absolute path")
        validated_roots.append(candidate)

    roots = []
    for candidate in validated_roots:
        root = candidate.expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        roots.append(str(root))

    value.update(
        {
            "version": 1,
            "port": port,
            "token": token,
            "allowed_roots": roots,
            "request_timeout_seconds": max(
                10, min(int(value.get("request_timeout_seconds", 120)), 3600)
            ),
        }
    )
    return target, value


def write_status(config_path: Path, value: dict) -> None:
    safe = dict(value)
    safe.pop("token", None)
    write_json(config_path.with_name("status.json"), safe)
