from __future__ import annotations

import argparse
import asyncio
import json

from fastmcp import Client

from hyperworks_mcp.server import mcp


def _data(result) -> dict:
    return json.loads(result.content[0].text)


async def smoke(job_id: str, only: str | None = None) -> None:
    requests = [
        ("Displacement", "Displacement", "Mag", "node"),
        ("Stress", "Element Stresses (2D & 3D)", "vonMises", "element"),
    ]
    if only:
        requests = [item for item in requests if item[0].lower() == only.lower()]
    reports = []
    async with Client(mcp) as client:
        for _, data_type, component, entity_type in requests:
            report = _data(
                await client.call_tool(
                    "postprocess_solver_result_in_hyperview",
                    {
                        "job_id": job_id,
                        "data_type": data_type,
                        "data_component": component,
                        "entity_type": entity_type,
                        "overwrite": True,
                        "query_limit": 10,
                    },
                )
            )
            reports.append(report)
    print(json.dumps(reports, ensure_ascii=False, indent=2))
    for report in reports:
        if not report.get("postprocessed"):
            raise RuntimeError("HyperView did not confirm postprocessing")
        if report.get("query", {}).get("row_count", 0) < 1:
            raise RuntimeError("HyperView did not return result query rows")
        if report.get("screenshot", {}).get("size_bytes", 0) < 1:
            raise RuntimeError("HyperView did not create screenshot evidence")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("job_id")
    parser.add_argument("--only", choices=["Displacement", "Stress"])
    args = parser.parse_args()
    asyncio.run(smoke(args.job_id, args.only))
