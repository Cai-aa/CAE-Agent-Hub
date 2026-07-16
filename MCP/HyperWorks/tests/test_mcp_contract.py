from __future__ import annotations

import unittest

from fastmcp import Client

from hyperworks_mcp.server import mcp


class MCPContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_tools_and_resources_are_discoverable(self) -> None:
        async with Client(mcp) as client:
            tools = await client.list_tools()
            names = {tool.name for tool in tools}
            self.assertTrue(
                {
                    "get_environment",
                    "create_project",
                    "import_project_file",
                    "write_tcl_script",
                    "run_hmbatch",
                    "launch_hypermesh",
                    "submit_solver_job",
                    "get_job_status",
                    "tail_job_log",
                    "cancel_job",
                    "list_job_artifacts",
                    "get_live_bridge_status",
                    "get_live_session_info",
                    "get_live_model_summary",
                    "list_live_entities",
                    "get_live_entity",
                    "select_live_entities_interactively",
                    "set_live_entity_attributes",
                    "get_live_model_metrics",
                    "save_live_model",
                }.issubset(names)
            )
            resources = await client.list_resources()
            self.assertIn(
                "hyperworks://environment", {str(item.uri) for item in resources}
            )


if __name__ == "__main__":
    unittest.main()
