from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

from fastmcp import Client


async def smoke() -> None:
    root = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix="hyperworks_mcp_stdio_") as workspace:
        environment = dict(os.environ)
        environment.update(
            {
                "PYTHONPATH": str(root / "src"),
                "PYTHONUTF8": "1",
                "HYPERWORKS_MCP_WORKSPACE": workspace,
            }
        )
        config = {
            "mcpServers": {
                "hyperworks": {
                    "command": sys.executable,
                    "args": ["-m", "hyperworks_mcp"],
                    "cwd": str(root),
                    "env": environment,
                }
            }
        }
        async with Client(config, init_timeout=20) as client:
            tools = await client.list_tools()
            result = await client.call_tool("get_environment", {})
            print(f"stdio_ok=true tools={len(tools)}")
            print(result.content[0].text)


if __name__ == "__main__":
    asyncio.run(smoke())
