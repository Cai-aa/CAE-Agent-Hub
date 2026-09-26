"""Read-only diagnostics for the external ANSA MCP environment.

The probe deliberately does not import ANSA's embedded ``ansa`` module, open a
socket, start ANSA, or modify the bridge configuration.
"""

from __future__ import annotations

import json
import os
import platform
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ansa_mcp.environment import environment_report as ansa_environment_report  # noqa: E402
from ansa_mcp.settings import Settings  # noqa: E402


def _default_config_path() -> Path:
    override = os.environ.get("ANSA_MCP_BRIDGE_CONFIG", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return (base / "ANSAMCP" / "bridge.json").resolve()


def _path_report(raw_value: str) -> dict[str, Any]:
    if not raw_value.strip():
        return {"configured": False, "path": None, "exists": False}
    path = Path(raw_value).expanduser().resolve()
    return {
        "configured": True,
        "path": str(path),
        "exists": path.exists(),
        "is_file": path.is_file(),
        "is_directory": path.is_dir(),
    }


def _config_report(path: Path) -> dict[str, Any]:
    report: dict[str, Any] = {"path": str(path), "exists": path.is_file()}
    if not path.is_file():
        report["valid"] = False
        report["error"] = "bridge config not found"
        return report
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        host = str(value.get("host", ""))
        port = int(value.get("port", 0))
        token = str(value.get("token", ""))
        token_length = len(token)
        allowed_roots = [str(Path(item).expanduser()) for item in value.get("allowed_roots", [])]
        errors: list[str] = []
        if host != "127.0.0.1":
            errors.append("host must be 127.0.0.1")
        if not 1024 <= port <= 65535:
            errors.append("port must be between 1024 and 65535")
        if re.fullmatch(r"[0-9a-fA-F]{64}", token) is None:
            errors.append("token must contain exactly 64 hexadecimal characters")
        if not allowed_roots:
            errors.append("allowed_roots must not be empty")
        report.update(
            {
                "valid": not errors,
                "version": value.get("version"),
                "host": host,
                "port": port,
                "token_present": re.fullmatch(r"[0-9a-fA-F]{64}", token) is not None,
                "token_length": token_length,
                "allowed_roots": allowed_roots,
                "allowed_roots_exist": [Path(item).expanduser().is_dir() for item in allowed_roots],
                "errors": errors,
            }
        )
    except Exception as exc:  # diagnostic script: preserve the actionable parse error
        report.update({"valid": False, "error": f"{type(exc).__name__}: {exc}"})
    return report


def environment_report() -> dict[str, Any]:
    settings = Settings.from_env()
    workspace = settings.workspace
    return {
        "probe": "ansa-mcp-environment",
        "python": {
            "executable": sys.executable,
            "version": platform.python_version(),
            "supported": sys.version_info >= (3, 10),
            "platform": platform.platform(),
        },
        "project": {
            "root": str(ROOT),
            "src_exists": SRC.is_dir(),
            "workspace": str(workspace),
            "workspace_exists": workspace.is_dir(),
            "workspace_writable": os.access(workspace, os.W_OK) if workspace.exists() else False,
        },
        "installation_hints": {
            "ANSA_HOME": _path_report(os.environ.get("ANSA_HOME", "")),
            "ANSA_EXECUTABLE": _path_report(os.environ.get("ANSA_EXECUTABLE", "")),
        },
        "ansa_environment": ansa_environment_report(settings),
        "bridge_config": _config_report(_default_config_path()),
        "notes": [
            "This probe is read-only and does not contact or start ANSA.",
            "A valid config does not prove that an ANSA bridge is loaded or reachable.",
        ],
    }


if __name__ == "__main__":
    print(json.dumps(environment_report(), ensure_ascii=False, indent=2))
