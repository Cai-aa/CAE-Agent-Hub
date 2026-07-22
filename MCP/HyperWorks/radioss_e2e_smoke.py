from __future__ import annotations

import asyncio
import json
import time

from fastmcp import Client

from hyperworks_mcp.server import mcp


def _data(result) -> dict:
    return json.loads(result.content[0].text)


async def smoke() -> None:
    async with Client(mcp) as client:
        project = _data(
            await client.call_tool(
                "create_project", {"name": "Radioss 0.8 explicit impact"}
            )
        )
        prepared = _data(
            await client.call_tool(
                "prepare_radioss_block_impact_analysis",
                {
                    "project_id": project["project_id"],
                    "name": "Radioss MCP TYPE7 impact",
                    "impactor_dimensions": [5.0, 6.0, 6.0],
                    "impactor_divisions": [2, 2, 2],
                    "target_dimensions": [2.0, 10.0, 10.0],
                    "target_divisions": [1, 2, 2],
                    "initial_gap": 1.0,
                    "initial_velocity": 5.0,
                    "end_time": 1.0,
                    "output_interval": 0.1,
                },
            )
        )
        job = _data(
            await client.call_tool(
                "submit_solver_job",
                {
                    "project_id": project["project_id"],
                    "solver": "radioss",
                    "input_file": prepared["input_file"],
                    "ncpu": 2,
                },
            )
        )
        deadline = time.time() + 180
        status = job
        while status["state"] == "RUNNING" and time.time() < deadline:
            await asyncio.sleep(1)
            status = _data(
                await client.call_tool("get_job_status", {"job_id": job["job_id"]})
            )
        artifacts = _data(
            await client.call_tool(
                "get_solver_result_artifacts", {"job_id": job["job_id"]}
            )
        )
        audit = _data(
            await client.call_tool(
                "audit_radioss_explicit_job", {"job_id": job["job_id"]}
            )
        )
        report = {
            "project": project,
            "prepared": prepared,
            "job_id": job["job_id"],
            "state": status["state"],
            "return_code": status.get("return_code"),
            "artifacts": artifacts,
            "audit": audit,
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if status["state"] != "COMPLETED" or status.get("return_code") != 0:
            raise RuntimeError("Radioss job did not complete successfully")
        if artifacts["result_count"] < 1 or not audit["passed"]:
            raise RuntimeError("Radioss result artifacts or explicit quality gates failed")


if __name__ == "__main__":
    asyncio.run(smoke())
