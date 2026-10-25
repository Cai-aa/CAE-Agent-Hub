from __future__ import annotations

import json
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from tools.bridge_client import ComsolBridgeClient


class BridgeClientTests(unittest.TestCase):
    def test_timed_out_reply_cannot_poison_later_requests(self):
        with tempfile.TemporaryDirectory() as tmp:
            script=Path(tmp)/'slow.py'
            script.write_text('import sys,time\nfor line in sys.stdin:\n time.sleep(10)\n',encoding='utf8')
            client=ComsolBridgeClient(); client.start([sys.executable,str(script)],cwd=tmp)
            try:
                with self.assertRaises(TimeoutError): client.request('ping',timeout=.1)
                self.assertFalse(client.is_running())
            finally: client.stop()

    def test_client_round_trips_to_line_json_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "fake_bridge.py"
            script.write_text(
                textwrap.dedent(
                    """
                    import json
                    import sys

                    for line in sys.stdin:
                        request = json.loads(line)
                        method = request.get("method")
                        if method == "shutdown":
                            print(json.dumps({"id": request["id"], "ok": True, "result": {"shutdown": True}}), flush=True)
                            break
                        print(json.dumps({"id": request["id"], "ok": True, "result": {"method": method}}), flush=True)
                    """
                ),
                encoding="utf-8",
            )

            client = ComsolBridgeClient()
            start = client.start(command=[sys.executable, str(script)], cwd=tmp)
            self.assertTrue(start["ok"])

            self.assertEqual(client.request("ping")["method"], "ping")
            self.assertTrue(client.stop()["ok"])


if __name__ == "__main__":
    unittest.main()
