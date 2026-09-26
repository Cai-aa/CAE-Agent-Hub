"""Call the three cantilever steps through the ANSA MCP stdio server."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from fastmcp import Client


def payload(result):
    if result.is_error:
        raise RuntimeError("\n".join(item.text for item in result.content if hasattr(item, "text")))
    if isinstance(result.data, dict):
        return result.data
    if isinstance(result.structured_content, dict):
        return result.structured_content.get("result", result.structured_content)
    return json.loads(result.content[0].text)


async def main() -> None:
    root = Path(__file__).resolve().parents[1]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root / "src")
    env["PYTHONUTF8"] = "1"
    config = {"mcpServers": {"ansa": {
        "command": sys.executable, "args": ["-m", "ansa_mcp"],
        "cwd": str(root), "env": env,
    }}}
    inspect_only = len(sys.argv) == 3 and sys.argv[1] == "--inspect"
    run_id = sys.argv[2] if inspect_only else (sys.argv[1] if len(sys.argv) > 1 else None)
    stages = [] if run_id else [("prepare_cantilever_static_demo", {"confirm": True})]
    if not inspect_only:
        stages.append(("solve_cantilever_static_demo", None))
    stages.append(("inspect_cantilever_static_demo", None))
    async with Client(config, init_timeout=30, timeout=175) as client:
        for name, args in stages:
            if args is None:
                args = {"run_id": run_id}
                if name.startswith("solve"):
                    args["confirm"] = True
            data = payload(await client.call_tool(name, args, timeout=175))
            print(name + ": " + json.dumps(data, ensure_ascii=False))
            if not data.get("ok"):
                raise RuntimeError(name + " did not pass its completion checks")
            if name.startswith("prepare"):
                run_id = data["run_id"]


if __name__ == "__main__":
    asyncio.run(main())
