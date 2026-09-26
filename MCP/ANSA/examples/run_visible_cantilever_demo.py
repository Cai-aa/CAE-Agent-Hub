"""Run the fixed cantilever in the already-open ANSA GUI through MCP stdio.

The user must first load the current ansa_plugin/start_ansa_mcp.py in a new,
empty ANSA GUI session and keep its bridge window open.  The script never
controls the desktop UI or invokes ANSA Python directly from this process.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
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
        "command": sys.executable,
        "args": ["-m", "ansa_mcp"],
        "cwd": str(root),
        "env": env,
    }}}
    async with Client(config, init_timeout=30, timeout=175) as client:
        async def call(name: str, args: dict):
            data = payload(await client.call_tool(name, args, timeout=175))
            print(name + ": " + json.dumps(data, ensure_ascii=False), flush=True)
            if data.get("ok") is False:
                raise RuntimeError(name + " failed its completion checks")
            return data

        status = await call("get_live_bridge_status", {})
        if not status.get("connected"):
            raise RuntimeError("Authenticated bridge is offline; load the bridge in ANSA first")
        capabilities = await call("get_live_capabilities", {})
        if "import_fixed_cantilever" not in capabilities.get("methods", []):
            raise RuntimeError("Loaded bridge is older than this visible workflow")
        session = await call("get_live_session_info", {})
        staged = await call("stage_visible_cantilever_static_demo", {"confirm": True})
        run_id = staged["run_id"]
        common = {
            "run_id": run_id,
            "expected_database": session["database"],
            "expected_session_nonce": session["session_nonce"],
            "confirm": True,
        }
        await call("import_visible_cantilever_static_demo", {
            **common, "operation_id": "visible-import-" + uuid.uuid4().hex,
        })
        after_import = await call("get_live_session_info", {})
        if after_import["session_nonce"] != session["session_nonce"]:
            raise RuntimeError("ANSA bridge session changed after import")
        await call("export_visible_cantilever_static_demo", {
            **common,
            "expected_database": after_import["database"],
            "operation_id": "visible-export-" + uuid.uuid4().hex,
        })
        await call("solve_visible_cantilever_static_demo", {
            "run_id": run_id, "confirm": True,
        })
        await call("inspect_visible_cantilever_static_demo", {"run_id": run_id})
        print("Visible ANSA model and solver evidence completed; run_id=" + run_id, flush=True)


if __name__ == "__main__":
    asyncio.run(main())
