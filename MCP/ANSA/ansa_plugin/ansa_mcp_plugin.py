"""ANSA Plugins ribbon callbacks for the authenticated MCP bridge.

The docked panel remains the bridge's visible lifetime owner. Closing it
stops the bridge; the Start button can create a new authenticated session.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _configure_bridge() -> Path:
    plugin_root = Path(__file__).resolve().parent
    pointer = plugin_root / "bridge_config_path.txt"
    if not pointer.is_file():
        raise RuntimeError("ANSA MCP bridge is not installed: config path pointer missing")
    config_path = Path(pointer.read_text(encoding="utf-8-sig").strip())
    if not config_path.is_absolute() or not config_path.is_file():
        raise RuntimeError("ANSA MCP config pointer is not an existing absolute file")
    config = json.loads(config_path.read_text(encoding="utf-8-sig"))
    configured_root = config.get("plugin_root") if isinstance(config, dict) else None
    if not isinstance(configured_root, str) or (
        os.path.normcase(os.path.abspath(configured_root))
        != os.path.normcase(str(plugin_root))
    ):
        raise RuntimeError("ANSA MCP config pointer targets another plugin root")
    os.environ["ANSA_MCP_BRIDGE_CONFIG"] = str(config_path)
    if str(plugin_root) not in sys.path:
        sys.path.insert(0, str(plugin_root))
    return config_path


def start_bridge():
    """Start a new docked runtime; never restart an already-live bridge."""
    _configure_bridge()
    from ansa_mcp_bridge import start, status

    current = status()
    if current.get("state") in ("online", "starting"):
        print("ANSA MCP bridge is already running; leave its current panel open.")
        return current
    return start(dock_to_database=True)


def show_bridge_status():
    _configure_bridge()
    from ansa_mcp_bridge import status

    current = status()
    state = current.get("state", "offline")
    port = current.get("port")
    message = f"ANSA MCP bridge: {state}"
    if port is not None:
        message += f" on 127.0.0.1:{port}"
    print(message)
    return current


def stop_bridge():
    _configure_bridge()
    from ansa_mcp_bridge import stop

    return stop()
