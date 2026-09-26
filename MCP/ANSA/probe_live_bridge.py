"""Read-only liveness probe for the in-process ANSA bridge."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

# Prefer the checked-out implementation when the probe is run directly without
# installing the project.  LiveBridgeClient owns the authenticated wire v3
# handshake; this probe must never construct a token-bearing socket request.
_PROJECT_ROOT = Path(__file__).resolve().parent
_SOURCE_ROOT = _PROJECT_ROOT / "src"
if str(_SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(_SOURCE_ROOT))

from ansa_mcp.bridge_client import LiveBridgeClient  # noqa: E402


def _default_config_path() -> Path:
    override = os.environ.get("ANSA_MCP_BRIDGE_CONFIG", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return (base / "ANSAMCP" / "bridge.json").resolve()


def _load_config() -> tuple[Path, dict[str, Any]]:
    path = _default_config_path()
    if not path.is_file():
        raise RuntimeError(f"bridge config not found: {path}")
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if value.get("host") != "127.0.0.1":
        raise RuntimeError("bridge host must be 127.0.0.1")
    if re.fullmatch(r"[0-9a-fA-F]{64}", str(value.get("token", ""))) is None:
        raise RuntimeError("bridge token must contain exactly 64 hexadecimal characters")
    port = int(value.get("port", 0))
    if not 1024 <= port <= 65535:
        raise RuntimeError("bridge port must be between 1024 and 65535")
    return path, value


def main() -> int:
    report: dict[str, Any] = {"probe": "ansa-mcp-live-bridge", "connected": False}
    try:
        config_path, config = _load_config()
        timeout = min(float(config.get("request_timeout_seconds", 120)), 10.0)
        timeout = max(timeout, 0.1)
        client = LiveBridgeClient(config_path)
        report.update(
            {
                "config_path": str(config_path),
                "endpoint": f"{config['host']}:{int(config['port'])}",
                "ping": client.call("ping", timeout=timeout),
                "capabilities": client.call("get_capabilities", timeout=timeout),
                "session": client.call("get_session_info", timeout=timeout),
                "connected": True,
            }
        )
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["connected"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
