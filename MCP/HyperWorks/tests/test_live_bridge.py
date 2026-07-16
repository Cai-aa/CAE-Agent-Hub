from __future__ import annotations

import json
import socketserver
import tempfile
import threading
import unittest
from pathlib import Path

from hyperworks_mcp.live_bridge import BridgeError, LiveBridgeClient


TOKEN = "a" * 64


class _Handler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        request = json.loads(self.rfile.readline().decode("utf-8"))
        if request.get("token") != TOKEN:
            response = {
                "id": request.get("id"),
                "ok": False,
                "error": {"code": "UNAUTHORIZED", "message": "bad token"},
            }
        else:
            response = {
                "id": request["id"],
                "ok": True,
                "result": {"method": request["method"], "params": request["params"]},
            }
        self.wfile.write((json.dumps(response) + "\n").encode("utf-8"))


class LiveBridgeClientTests(unittest.TestCase):
    def test_authenticated_round_trip(self) -> None:
        server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                config = Path(tmp) / "bridge.json"
                config.write_text(
                    json.dumps(
                        {
                            "host": "127.0.0.1",
                            "port": server.server_address[1],
                            "token": TOKEN,
                        }
                    ),
                    encoding="utf-8",
                )
                result = LiveBridgeClient(config).call("ping", {"value": 3})
                self.assertEqual(result, {"method": "ping", "params": {"value": 3}})
        finally:
            server.shutdown()
            server.server_close()

    def test_missing_config_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(BridgeError, "config not found"):
                LiveBridgeClient(Path(tmp) / "missing.json").call("ping")


if __name__ == "__main__":
    unittest.main()
