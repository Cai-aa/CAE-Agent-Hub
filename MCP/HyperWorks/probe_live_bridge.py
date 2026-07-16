from __future__ import annotations

import json

from hyperworks_mcp.live_bridge import LiveBridgeClient


if __name__ == "__main__":
    client = LiveBridgeClient()
    result = {"status": client.status(connect_timeout=1.0)}
    if result["status"]["connected"]:
        result["capabilities"] = client.call("get_capabilities", timeout=10)
        result["session"] = client.call("get_session_info", timeout=10)
    print(json.dumps(result, ensure_ascii=False, indent=2))
