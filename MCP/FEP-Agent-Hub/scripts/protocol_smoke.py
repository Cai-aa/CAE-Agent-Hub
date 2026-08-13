from __future__ import annotations

import asyncio
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


SERVERS = {
    "freecad": "freecad_mcp.server",
    "elmer": "elmer_mcp.server",
    "paraview": "paraview_mcp.server",
}


async def inspect(name: str, module: str) -> tuple[int, int, int]:
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", module],
        env=os.environ.copy(),
    )
    async with stdio_client(parameters) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            resources = await session.list_resources()
            templates = await session.list_resource_templates()
            print(
                f"{name}: tools={len(tools.tools)} "
                f"resources={len(resources.resources)} templates={len(templates.resourceTemplates)}"
            )
            return len(tools.tools), len(resources.resources), len(templates.resourceTemplates)


async def main() -> int:
    results = {name: await inspect(name, module) for name, module in SERVERS.items()}
    expected = {"freecad": 15, "elmer": 17, "paraview": 17}
    return 0 if all(results[name][0] == count for name, count in expected.items()) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
