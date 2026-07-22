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
                    "get_hyperstudy_capabilities",
                    "prepare_hyperstudy_math_study",
                    "generate_hyperstudy_study",
                    "prepare_optistruct_cantilever_analysis",
                    "prepare_radioss_block_impact_analysis",
                    "list_analysis_templates",
                    "get_analysis_template",
                    "prepare_analysis_template",
                    "get_solver_result_artifacts",
                    "audit_radioss_explicit_job",
                    "postprocess_solver_result_in_hyperview",
                    "extract_solver_time_history_in_hypergraph",
                    "generate_solver_job_report",
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
                    "get_live_connection_capabilities",
                    "get_live_safety_airbag_capabilities",
                    "get_live_session_info",
                    "get_live_model_summary",
                    "list_live_entities",
                    "get_live_entity",
                    "select_live_entities_interactively",
                    "set_live_entity_attributes",
                    "create_live_nodes",
                    "create_live_elements",
                    "create_live_material",
                    "create_live_solver_card_entity",
                    "create_live_nodal_load",
                    "create_live_pressure_load",
                    "create_live_loadstep",
                    "create_live_rigid_link",
                    "create_live_rbe3",
                    "create_live_weld",
                    "create_live_spot_weld",
                    "create_live_connector",
                    "create_live_solid_block",
                    "create_live_solid_cylinder",
                    "import_live_cad",
                    "automesh_live_surfaces",
                    "solid_map_live_solids",
                    "tetra_mesh_live_solids",
                    "repair_live_mesh_quality",
                    "create_live_cylindrical_ogrid",
                    "get_live_mesh_quality",
                    "create_live_checkpoint",
                    "rollback_live_checkpoint",
                    "load_live_model",
                    "refresh_live_view",
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
