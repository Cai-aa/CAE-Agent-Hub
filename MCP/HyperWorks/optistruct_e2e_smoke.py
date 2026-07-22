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
                "create_project", {"name": "OptiStruct end-to-end cantilever"}
            )
        )
        prepared = _data(
            await client.call_tool(
                "prepare_optistruct_cantilever_analysis",
                {
                    "project_id": project["project_id"],
                    "name": "OptiStruct MCP Cantilever",
                    "dimensions": [100.0, 20.0, 10.0],
                    "divisions": [10, 2, 2],
                    "youngs_modulus": 210000.0,
                    "poissons_ratio": 0.3,
                    "density": 7.85e-9,
                    "total_force": -1000.0,
                    "force_direction": [0.0, 0.0, 1.0],
                    "gap_contacts": [
                        {
                            "grid_index": [10, 1, 0],
                            "ground_position": [100.0, 10.0, -1.0],
                            "stiffness": 100000.0,
                            "initial_gap": 0.0,
                        }
                    ],
                    "output_name": "cantilever.fem",
                },
            )
        )
        job = _data(
            await client.call_tool(
                "submit_solver_job",
                {
                    "project_id": project["project_id"],
                    "solver": "optistruct",
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
        log = _data(
            await client.call_tool(
                "tail_job_log", {"job_id": job["job_id"], "lines": 160}
            )
        )
        artifacts = _data(
            await client.call_tool(
                "get_solver_result_artifacts", {"job_id": job["job_id"]}
            )
        )
        report = {
            "project": project,
            "prepared": prepared,
            "job_id": job["job_id"],
            "state": status["state"],
            "return_code": status.get("return_code"),
            "artifacts": artifacts,
            "log_lines": log["lines"],
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if status["state"] != "COMPLETED" or artifacts["result_count"] < 1:
            raise RuntimeError("OptiStruct did not complete with a result artifact")


if __name__ == "__main__":
    asyncio.run(smoke())
