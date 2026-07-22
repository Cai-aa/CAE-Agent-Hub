from __future__ import annotations

import argparse
import asyncio
import json

from fastmcp import Client

from hyperworks_mcp.server import mcp


def _data(result) -> dict:
    return json.loads(result.content[0].text)


async def smoke() -> None:
    report: dict = {"rollback_completed": False}
    checkpoint_file = None
    async with Client(mcp) as client:
        audit = _data(await client.call_tool("get_live_connection_capabilities", {}))
        before = _data(
            await client.call_tool(
                "get_live_model_summary",
                {"entity_types": ["node", "element", "system"]},
            )
        )
        checkpoint = _data(
            await client.call_tool(
                "create_live_checkpoint", {"label": "before_connection_smoke"}
            )
        )
        checkpoint_file = checkpoint["checkpoint_file"]
        report.update(
            {
                "audit": audit,
                "before": before,
                "checkpoint_file": checkpoint_file,
            }
        )
        try:
            nodes = _data(
                await client.call_tool(
                    "create_live_nodes",
                    {
                        "coordinates": [
                            [30.0, 0.0, 0.0],
                            [30.0, 2.0, 0.0],
                            [30.0, -2.0, 0.0],
                            [35.0, 2.0, 2.0],
                            [35.0, -2.0, 2.0],
                            [35.0, -2.0, -2.0],
                            [35.0, 2.0, -2.0],
                            [40.0, 0.0, 0.0],
                        ]
                    },
                )
            )
            node_ids = nodes["ids"]
            rigid = _data(
                await client.call_tool(
                    "create_live_rigid_link",
                    {
                        "independent_node_id": node_ids[0],
                        "dependent_node_ids": node_ids[1:3],
                        "refresh": False,
                    },
                )
            )
            rbe3 = _data(
                await client.call_tool(
                    "create_live_rbe3",
                    {
                        "independent_node_ids": node_ids[3:7],
                        "refresh": False,
                    },
                )
            )
            weld = _data(
                await client.call_tool(
                    "create_live_weld",
                    {
                        "independent_node_id": node_ids[0],
                        "dependent_node_id": node_ids[7],
                        "length": 10.0,
                        "refresh": False,
                    },
                )
            )
            created_element_ids = [
                *rigid["element_ids"],
                *rbe3["element_ids"],
                *weld["element_ids"],
            ]
            created_elements = [
                _data(result)
                for result in await asyncio.gather(
                    *[
                        client.call_tool(
                            "get_live_entity",
                            {
                                "entity_type": "element",
                                "entity_id": element_id,
                                "attributes": ["id", "config", "type"],
                            },
                        )
                        for element_id in created_element_ids
                    ]
                )
            ]
            report.update(
                {
                    "nodes": nodes,
                    "rigid_link": rigid,
                    "rbe3": rbe3,
                    "weld": weld,
                    "created_elements": created_elements,
                    "after_creation": _data(
                        await client.call_tool(
                            "get_live_model_summary",
                            {"entity_types": ["node", "element", "system"]},
                        )
                    ),
                }
            )
        finally:
            if checkpoint_file:
                report["rollback"] = _data(
                    await client.call_tool(
                        "rollback_live_checkpoint",
                        {
                            "checkpoint_file": checkpoint_file,
                            "confirm": True,
                        },
                    )
                )
                report["after_rollback"] = _data(
                    await client.call_tool(
                        "get_live_model_summary",
                        {"entity_types": ["node", "element", "system"]},
                    )
                )
                report["rollback_completed"] = True

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run checkpointed live RBE3, rigid-link, and weld MCP validation"
    )
    parser.add_argument(
        "--run", action="store_true", help="confirm temporary live-model modification"
    )
    args = parser.parse_args()
    if not args.run:
        parser.error("Pass --run to confirm the checkpointed live-model test")
    asyncio.run(smoke())
