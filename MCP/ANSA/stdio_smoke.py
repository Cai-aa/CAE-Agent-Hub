"""Offline stdio MCP handshake smoke test.

This starts only the external Python MCP process.  It does not start ANSA and a
passing result is not evidence of a live bridge or usable ANSA session.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

from fastmcp import Client


async def smoke() -> None:
    root = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix="ansa_mcp_stdio_") as workspace:
        environment = dict(os.environ)
        environment.update(
            {
                "PYTHONPATH": str(root / "src"),
                "PYTHONUTF8": "1",
                "ANSA_MCP_WORKSPACE": workspace,
            }
        )
        config = {
            "mcpServers": {
                "ansa": {
                    "command": sys.executable,
                    "args": ["-m", "ansa_mcp"],
                    "cwd": str(root),
                    "env": environment,
                }
            }
        }
        async with Client(config, init_timeout=20) as client:
            tools = await client.list_tools()
            result = await client.call_tool("get_environment", {})
            print(f"stdio_ok=true tools={len(tools)}")
            if result.content:
                print(result.content[0].text)


if __name__ == "__main__":
    asyncio.run(smoke())

