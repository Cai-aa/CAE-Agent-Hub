from __future__ import annotations

import asyncio

import server


HIGH_LEVEL_TOOLS = {
    "workbench_session_status_tool",
    "workbench_bootstrap_current_tool",
    "workbench_attach_current_tool",
    "workbench_launch_managed_tool",
    "workbench_project_inventory_tool",
    "workbench_project_open_tool",
    "workbench_project_save_as_tool",
    "workbench_model_open_tool",
    "workbench_model_state_tool",
    "workbench_model_execute_python_tool",
    "workbench_session_disconnect_tool",
}


MECHANICAL_WORKFLOW_TOOLS = {
    "mechanical_readiness_tool",
    "mechanical_probe_session_tool",
    "workbench_create_prestressed_modal_chain_tool",
    "mechanical_geometry_inventory_tool",
    "mechanical_import_geometry_tool",
    "mechanical_create_named_selection_tool",
    "mechanical_create_analysis_chain_tool",
    "mechanical_validate_rotor_job_tool",
    "mechanical_configure_rotor_model_tool",
    "mechanical_validate_mesh_job_tool",
    "mechanical_mesh_and_validate_tool",
    "mechanical_solve_analysis_tool",
    "mechanical_workflow_status_tool",
    "mechanical_extract_structural_results_tool",
    "mechanical_extract_modal_results_tool",
    "mechanical_export_evidence_tool",
}


def test_server_registers_complete_merged_v020_tool_surface():
    tools = asyncio.run(server.mcp.get_tools())

    assert len(tools) == 45
    assert HIGH_LEVEL_TOOLS <= set(tools)
    assert MECHANICAL_WORKFLOW_TOOLS <= set(tools)
