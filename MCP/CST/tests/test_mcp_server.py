from __future__ import annotations

import asyncio
import json
import sys
import unittest
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

import mcp_server


REPO_ROOT = Path(__file__).resolve().parent.parent


class MCPServerTests(unittest.TestCase):
    def test_registers_tools_and_resources(self):
        async def check():
            tools = await mcp_server.mcp.list_tools()
            tool_names = {tool.name for tool in tools}
            resources = await mcp_server.mcp.list_resources()
            resource_uris = {str(resource.uri) for resource in resources}
            contents = list(await mcp_server.mcp.read_resource("cst://agent-instructions"))
            return tool_names, resource_uris, contents

        tool_names, resource_uris, contents = asyncio.run(check())

        self.assertIn("cst_detect_tool", tool_names)
        self.assertIn("cst_sweep_preview_tool", tool_names)
        self.assertIn("cst_create_schematic_project_tool", tool_names)
        self.assertEqual(resource_uris, {"cst://agent-instructions", "cst://environment"})
        self.assertTrue(contents)
        self.assertIn("CST Studio Suite", contents[0].content)

    def test_call_tool_sweep_preview(self):
        async def check():
            return await mcp_server.mcp.call_tool(
                "cst_sweep_preview_tool",
                {"parameters": {"w": "1:2:1"}},
            )

        result = asyncio.run(check())
        if hasattr(result, "content"):
            content = result.content
        elif isinstance(result, tuple):
            content = result[0]
        else:
            content = result
        payload = json.loads(content[0].text)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["case_count"], 2)

    def test_stdio_handshake_and_tool_call(self):
        async def check():
            params = StdioServerParameters(
                command=sys.executable,
                args=[str(REPO_ROOT / "mcp_server.py")],
                cwd=str(REPO_ROOT),
            )
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as client:
                    init = await client.initialize()
                    tools = await client.list_tools()
                    resources = await client.list_resources()
                    call = await client.call_tool(
                        "cst_sweep_preview_tool",
                        {"parameters": {"w": "1:2:1"}},
                    )
                    return init, tools, resources, call

        init, tools, resources, call = asyncio.run(check())

        server_info = getattr(init, "server_info", None) or getattr(init, "serverInfo", None)
        self.assertIsNotNone(server_info)
        self.assertEqual(server_info.name, "cst-studio-suite-mcp")
        self.assertGreaterEqual(len(tools.tools), 50)
        self.assertEqual(
            {str(resource.uri) for resource in resources.resources},
            {"cst://agent-instructions", "cst://environment"},
        )
        is_error = getattr(call, "is_error", getattr(call, "isError", False))
        self.assertFalse(is_error)
        payload = json.loads(call.content[0].text)
        self.assertEqual(payload["cases"], [{"w": 1}, {"w": 2}])


if __name__ == "__main__":
    unittest.main()
