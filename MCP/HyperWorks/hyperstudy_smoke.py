from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from fastmcp import Client

from hyperworks_mcp.server import mcp


def _data(result) -> dict:
    return json.loads(result.content[0].text)


async def smoke() -> None:
    async with Client(mcp) as client:
        project = _data(
            await client.call_tool(
                "create_project", {"name": "HyperStudy API smoke test"}
            )
        )
        prepared = _data(
            await client.call_tool(
                "prepare_hyperstudy_math_study",
                {
                    "project_id": project["project_id"],
                    "study_name": "MCP Math Tradeoff",
                    "variables": [
                        {
                            "label": "Width",
                            "varname": "width",
                            "lower": 1.0,
                            "nominal": 2.0,
                            "upper": 4.0,
                        },
                        {
                            "label": "Height",
                            "varname": "height",
                            "lower": 1.0,
                            "nominal": 3.0,
                            "upper": 6.0,
                        },
                    ],
                    "responses": [
                        {
                            "label": "Area",
                            "varname": "area",
                            "expression": "width*height",
                        }
                    ],
                    "doe": {"design": "Hammersley", "runs": 12},
                    "optimization": {
                        "design": "GRSM",
                        "max_evaluations": 20,
                        "goals": [
                            {
                                "label": "Minimize area",
                                "varname": "min_area",
                                "response": "area",
                                "type": "Minimize",
                            }
                        ],
                    },
                },
            )
        )
        job = _data(
            await client.call_tool(
                "generate_hyperstudy_study",
                {
                    "project_id": project["project_id"],
                    "script_name": prepared["script_name"],
                },
            )
        )
        deadline = time.time() + 120
        status = job
        while status["state"] == "RUNNING" and time.time() < deadline:
            await asyncio.sleep(1)
            status = _data(
                await client.call_tool("get_job_status", {"job_id": job["job_id"]})
            )
        log = _data(
            await client.call_tool(
                "tail_job_log", {"job_id": job["job_id"], "lines": 120}
            )
        )
        study_file = Path(prepared["expected_study_file"])
        result = {
            "project_id": project["project_id"],
            "job_id": job["job_id"],
            "state": status["state"],
            "return_code": status.get("return_code"),
            "study_file": str(study_file),
            "study_file_exists": study_file.is_file(),
            "study_file_size": study_file.stat().st_size if study_file.is_file() else 0,
            "log_lines": log["lines"],
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if status["state"] != "COMPLETED" or not study_file.is_file():
            raise RuntimeError("HyperStudy API smoke test did not create the study")


if __name__ == "__main__":
    asyncio.run(smoke())
