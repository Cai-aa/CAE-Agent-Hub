from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main() -> None:
    root = Path(__file__).resolve().parents[1]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root / "src")
    with tempfile.TemporaryDirectory(prefix="adams-protocol-") as directory:
        env["ADAMS_MCP_WORKSPACE"] = directory
        await check_protocol(env)


async def check_protocol(env: dict[str, str]) -> None:
    params = StdioServerParameters(command=sys.executable, args=["-m", "adams_mcp.server"], env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            resources = await session.list_resources()
            probe = await session.call_tool("adams_environment_probe", {})
            probe_payload = probe.structuredContent
            if probe_payload is None and probe.content:
                text_content = getattr(probe.content[0], "text", "")
                try:
                    probe_payload = json.loads(text_content)
                except json.JSONDecodeError:
                    probe_payload = text_content
            assert not probe.isError, probe
            assert isinstance(probe_payload, dict) and probe_payload.get("ok"), probe_payload
            assert len(tools.tools) == 16, len(tools.tools)
            assert len(resources.resources) == 3, len(resources.resources)
            created = await session.call_tool("adams_project_create", {"project_id": "protocol_smoke", "model_name": "PROTOCOL_SMOKE"})
            assert not created.isError, created
            data = created.structuredContent or json.loads(created.content[0].text)
            assert data["ok"], data
            print(json.dumps({"status": "PASS", "tool_count": len(tools.tools), "resource_count": len(resources.resources), "tools": [item.name for item in tools.tools], "probe": probe_payload}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
