"""Exercise Abaqus MCP over stdio with either supported SDK major version."""
import json
from pathlib import Path
from queue import Queue
import subprocess
import sys
from threading import Thread
import unittest


class ServerStartupTests(unittest.TestCase):
    def test_stdio_registration_and_offline_call(self):
        server = Path(__file__).resolve().parents[1]
        with subprocess.Popen(
            [sys.executable, "-u", "mcp_server.py"], cwd=server,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, encoding="utf-8",
        ) as process:
            responses = Queue()

            def receive():
                for line in process.stdout:
                    responses.put(line)
                responses.put(None)

            Thread(target=receive, daemon=True).start()

            def request(method, request_id=None, **params):
                message = {"jsonrpc": "2.0", "method": method, "params": params}
                if request_id is not None:
                    message["id"] = request_id
                process.stdin.write(json.dumps(message) + "\n")
                process.stdin.flush()
                if request_id is None:
                    return
                response = responses.get(timeout=20)
                self.assertIsNotNone(response, "MCP server exited before replying")
                reply = json.loads(response)
                self.assertEqual(reply.get("id"), request_id)
                self.assertNotIn("error", reply)
                return reply["result"]

            try:
                info = request(
                    "initialize", 1, protocolVersion="2025-11-25", capabilities={},
                    clientInfo={"name": "abaqus-startup-test", "version": "1"},
                )
                self.assertEqual(info["serverInfo"]["name"], "abaqus-mcp-server")
                request("notifications/initialized")
                tools = request("tools/list", 2)["tools"]
                self.assertTrue(
                    {"ping", "inspect_job_files", "inspect_part_mesh", "inspect_odb"}
                    <= {tool["name"] for tool in tools}
                )
                resources = request("resources/list", 3)["resources"]
                self.assertIn("abaqus://status", {resource["uri"] for resource in resources})
                reply = request(
                    "tools/call", 4, name="inspect_job_files",
                    arguments={"job_name": "NotPresent", "job_directory": str(server / "tests" / "fixtures")},
                )
                self.assertFalse(reply.get("isError"), reply)
                result = reply.get("structuredContent") or json.loads(reply["content"][0]["text"])
                self.assertEqual(result["state"], "unknown")
            finally:
                process.stdin.close()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
