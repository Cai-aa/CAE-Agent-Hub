from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

from fastmcp import Client


def _data(result) -> dict:
    return json.loads(result.content[0].text)


async def smoke(timeout_seconds: int) -> None:
    root = Path(__file__).resolve().parent
    environment = dict(os.environ)
    environment.update(
        {
            "PYTHONPATH": str(root / "src"),
            "PYTHONUTF8": "1",
            "HYPERWORKS_MCP_WORKSPACE": environment.get(
                "HYPERWORKS_MCP_WORKSPACE", str(root / "workspace")
            ),
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
        project = _data(
            await client.call_tool("create_project", {"name": "hmbatch smoke test"})
        )
        await client.call_tool(
            "write_tcl_script",
            {
                "project_id": project["project_id"],
                "name": "smoke.tcl",
                "content": 'puts "HyperWorks MCP live batch smoke"\n',
            },
        )
        job = _data(
            await client.call_tool(
                "run_hmbatch",
                {"project_id": project["project_id"], "script_name": "smoke.tcl"},
            )
        )
        deadline = time.time() + timeout_seconds
        status = job
        while status["state"] == "RUNNING" and time.time() < deadline:
            await asyncio.sleep(1)
            status = _data(
                await client.call_tool("get_job_status", {"job_id": job["job_id"]})
            )
        log = _data(
            await client.call_tool(
                "tail_job_log", {"job_id": job["job_id"], "lines": 80}
            )
        )
        print(
            json.dumps(
                {
                    "project_id": project["project_id"],
                    "job_id": job["job_id"],
                    "state": status["state"],
                    "return_code": status.get("return_code"),
                    "success_marker_detected": status.get("success_marker_detected"),
                    "log_lines": log["lines"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        if status["state"] != "COMPLETED":
            raise RuntimeError(f"hmbatch smoke did not complete successfully: {status['state']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run a real, license-using hmbatch smoke test")
    parser.add_argument("--run", action="store_true", help="confirm the live hmbatch launch")
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()
    if not args.run:
        parser.error("Pass --run to confirm this live HyperMesh Batch check")
    asyncio.run(smoke(args.timeout))
