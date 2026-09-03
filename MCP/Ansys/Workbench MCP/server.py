from __future__ import annotations

from dotenv import load_dotenv
from fastmcp import FastMCP

from tools.workbench_bridge import (
    detect_workbench_environment,
    get_workbench_job_status,
    launch_mechanical_script,
    launch_workbench_journal,
    list_workbench_jobs,
    read_workbench_job_log,
)
from tools.workbench_file_queue import (
    list_queue as queue_list,
    queue_execute_python,
    queue_get_state,
    queue_install_info,
    queue_ping,
    read_response as queue_read_response,
    submit_request as queue_submit_request,
    trigger_socket_process_queue,
)
from tools.workbench_socket_timer import (
    socket_timer_execute_python,
    socket_timer_ping,
    socket_timer_state,
    socket_timer_stop,
)
from tools.mechanical_workflows import (
    mechanical_configure_rotor_model,
    mechanical_create_analysis_chain,
    mechanical_create_named_selection,
    mechanical_export_evidence,
    mechanical_extract_modal_results,
    mechanical_extract_structural_results,
    mechanical_geometry_inventory,
    mechanical_import_geometry,
    mechanical_mesh_and_validate,
    mechanical_probe_session,
    mechanical_readiness,
    mechanical_solve_analysis,
    mechanical_workflow_status,
    validate_mesh_spec,
    validate_rotor_job_spec,
    workbench_create_prestressed_modal_chain,
)


from tools.workbench_session import (
    workbench_attach_current,
    workbench_bootstrap_current,
    workbench_launch_managed,
    workbench_model_execute_python,
    workbench_model_open,
    workbench_model_state,
    workbench_project_inventory,
    workbench_project_open,
    workbench_project_save_as,
    workbench_session_disconnect,
    workbench_session_status,
)


load_dotenv()

mcp = FastMCP("Ansys Workbench MCP")


@mcp.tool()
def workbench_detect_tool() -> dict:
    """Detect RunWB2.exe, PyMechanical CLI, ANSYS_ROOT, and job directories."""
    return detect_workbench_environment()


@mcp.tool()
def workbench_run_journal_tool(
    journal_path: str,
    cwd: str | None = None,
    batch: bool = True,
    extra_args: list[str] | None = None,
) -> dict:
    """Launch a Workbench journal asynchronously."""
    return launch_workbench_journal(journal_path=journal_path, cwd=cwd, batch=batch, extra_args=extra_args)


@mcp.tool()
def mechanical_run_script_tool(
    script_path: str,
    revision: int = 261,
    graphical: bool = False,
    project_file: str | None = None,
    script_args: str | None = None,
) -> dict:
    """Launch ansys-mechanical.exe for a Mechanical Python script."""
    return launch_mechanical_script(
        script_path=script_path,
        revision=revision,
        graphical=graphical,
        project_file=project_file,
        script_args=script_args,
    )


@mcp.tool()
def workbench_job_status_tool(job_id: str) -> dict:
    """Return status for a Workbench or Mechanical job launched by this MCP."""
    return get_workbench_job_status(job_id)


@mcp.tool()
def workbench_job_log_tool(job_id: str, stream: str = "stdout", tail_chars: int = 12000) -> dict:
    """Read stdout or stderr for a Workbench or Mechanical job."""
    return read_workbench_job_log(job_id=job_id, stream=stream, tail_chars=tail_chars)


@mcp.tool()
def workbench_list_jobs_tool(limit: int = 20) -> dict:
    """List recent Workbench or Mechanical jobs."""
    return list_workbench_jobs(limit=limit)


@mcp.tool()
def workbench_queue_install_info_tool() -> dict:
    """Show paths and instructions for the Mechanical file queue bridge."""
    return queue_install_info()


@mcp.tool()
def workbench_queue_list_tool() -> dict:
    """List pending queue requests, responses, and recent archive entries."""
    return queue_list()


@mcp.tool()
def workbench_queue_submit_tool(action: str, payload: dict | None = None) -> dict:
    """Submit a raw request to the Mechanical file queue."""
    return queue_submit_request(action=action, payload=payload)


@mcp.tool()
def workbench_queue_response_tool(request_id: str) -> dict:
    """Read a queued Mechanical response by request id."""
    return queue_read_response(request_id)


@mcp.tool()
def workbench_queue_ping_tool(wait_timeout: float = 2.0) -> dict:
    """Submit a queue ping and wait briefly for the Mechanical-side response."""
    return queue_ping(wait_timeout=wait_timeout)


@mcp.tool()
def workbench_queue_state_tool(wait_timeout: float = 2.0) -> dict:
    """Read project state through the Mechanical queue bridge."""
    return queue_get_state(wait_timeout=wait_timeout)


@mcp.tool()
def workbench_queue_execute_python_tool(code: str, wait_timeout: float = 2.0) -> dict:
    """Execute Python inside Mechanical through the queue bridge."""
    return queue_execute_python(code=code, wait_timeout=wait_timeout)


@mcp.tool()
def workbench_queue_process_with_socket_timer_tool(timeout: float = 2.0) -> dict:
    """Ask the socket timer bridge to process pending queue requests."""
    return trigger_socket_process_queue(timeout=timeout)


@mcp.tool()
def workbench_socket_timer_ping_tool(timeout: float = 10.0) -> dict:
    """Ping the Mechanical socket timer bridge."""
    return socket_timer_ping(timeout=timeout)


@mcp.tool()
def workbench_socket_timer_state_tool(timeout: float = 10.0) -> dict:
    """Read state from the Mechanical socket timer bridge."""
    return socket_timer_state(timeout=timeout)


@mcp.tool()
def workbench_socket_timer_execute_python_tool(code: str, timeout: float = 60.0) -> dict:
    """Execute Python inside Mechanical through the socket timer bridge."""
    return socket_timer_execute_python(code=code, timeout=timeout)


@mcp.tool()
def workbench_socket_timer_stop_tool(timeout: float = 10.0) -> dict:
    """Stop the Mechanical socket timer bridge."""
    return socket_timer_stop(timeout=timeout)


@mcp.tool()
def mechanical_readiness_tool(timeout: float = 5.0) -> dict:
    """Check the Mechanical bridge and report the model-readiness contract."""
    return mechanical_readiness(timeout=timeout)


@mcp.tool()
def mechanical_probe_session_tool(transport: str = "queue", wait_timeout: float = 5.0) -> dict:
    """Prove Project, Model, and Model.Analyses availability inside Mechanical."""
    return mechanical_probe_session(transport=transport, wait_timeout=wait_timeout)


@mcp.tool()
def workbench_create_prestressed_modal_chain_tool(
    project_path: str,
    geometry_path: str | None = None,
    include_baseline_modal: bool = True,
    overwrite_policy: str = "error",
    launch: bool = True,
) -> dict:
    """Create a Static Structural -> prestressed Modal Workbench project chain."""
    return workbench_create_prestressed_modal_chain(
        project_path=project_path,
        geometry_path=geometry_path,
        include_baseline_modal=include_baseline_modal,
        overwrite_policy=overwrite_policy,
        launch=launch,
    )


@mcp.tool()
def mechanical_geometry_inventory_tool(transport: str = "queue", wait_timeout: float = 10.0) -> dict:
    """List bodies, geometry entity ids, named selections, contacts, and analyses."""
    return mechanical_geometry_inventory(transport=transport, wait_timeout=wait_timeout)


@mcp.tool()
def mechanical_import_geometry_tool(
    geometry_path: str,
    import_name: str = "WB_MCP_Geometry_Import",
    process_named_selections: bool = True,
    process_coordinate_systems: bool = True,
    replace_existing: bool = False,
    transport: str = "queue",
    wait_timeout: float = 30.0,
) -> dict:
    """Import a supported CAD file into the loaded Mechanical model."""
    return mechanical_import_geometry(
        geometry_path=geometry_path,
        import_name=import_name,
        process_named_selections=process_named_selections,
        process_coordinate_systems=process_coordinate_systems,
        replace_existing=replace_existing,
        transport=transport,
        wait_timeout=wait_timeout,
    )


@mcp.tool()
def mechanical_create_named_selection_tool(
    name: str,
    entity_ids: list[int],
    replace_existing: bool = False,
    transport: str = "queue",
    wait_timeout: float = 10.0,
) -> dict:
    """Create a Mechanical geometry named selection from explicit entity ids."""
    return mechanical_create_named_selection(
        name=name,
        entity_ids=entity_ids,
        replace_existing=replace_existing,
        transport=transport,
        wait_timeout=wait_timeout,
    )


@mcp.tool()
def mechanical_create_analysis_chain_tool(
    static_name: str = "Rotating_Static",
    baseline_modal_name: str = "Modal_Zero_RPM",
    prestressed_modal_name: str = "Modal_Prestressed",
    mode_count: int = 6,
    include_baseline_modal: bool = True,
    replace_existing: bool = False,
    transport: str = "queue",
    wait_timeout: float = 15.0,
) -> dict:
    """Create idempotent rotating-static, baseline-modal, and prestressed-modal analyses."""
    return mechanical_create_analysis_chain(
        static_name=static_name,
        baseline_modal_name=baseline_modal_name,
        prestressed_modal_name=prestressed_modal_name,
        mode_count=mode_count,
        include_baseline_modal=include_baseline_modal,
        replace_existing=replace_existing,
        transport=transport,
        wait_timeout=wait_timeout,
    )


@mcp.tool()
def mechanical_validate_rotor_job_tool(spec: dict) -> dict:
    """Validate rotor contacts, support, material, axis, and rotational-speed inputs."""
    return validate_rotor_job_spec(spec)


@mcp.tool()
def mechanical_configure_rotor_model_tool(
    spec: dict,
    transport: str = "queue",
    wait_timeout: float = 20.0,
) -> dict:
    """Configure material, bonded contacts, bore support, and rotational velocity."""
    return mechanical_configure_rotor_model(spec=spec, transport=transport, wait_timeout=wait_timeout)


@mcp.tool()
def mechanical_validate_mesh_job_tool(spec: dict) -> dict:
    """Validate global and named-selection local mesh sizing inputs."""
    return validate_mesh_spec(spec)


@mcp.tool()
def mechanical_mesh_and_validate_tool(
    spec: dict,
    transport: str = "queue",
    wait_timeout: float = 60.0,
) -> dict:
    """Apply mesh sizing, generate the mesh, and return node/element evidence."""
    return mechanical_mesh_and_validate(spec=spec, transport=transport, wait_timeout=wait_timeout)


@mcp.tool()
def mechanical_solve_analysis_tool(
    analysis_names: list[str],
    save_after: bool = True,
    transport: str = "queue",
    wait_timeout: float = 2.0,
) -> dict:
    """Submit ordered Mechanical analyses for solve; poll instead of resubmitting after timeout."""
    return mechanical_solve_analysis(
        analysis_names=analysis_names,
        save_after=save_after,
        transport=transport,
        wait_timeout=wait_timeout,
    )


@mcp.tool()
def mechanical_workflow_status_tool(request_id: str | None = None, timeout: float = 5.0) -> dict:
    """Poll a submitted workflow response or return current bridge readiness."""
    return mechanical_workflow_status(request_id=request_id, timeout=timeout)


@mcp.tool()
def mechanical_extract_structural_results_tool(
    analysis_name: str = "Rotating_Static",
    transport: str = "queue",
    wait_timeout: float = 15.0,
) -> dict:
    """Extract managed deformation, stress, and contact-tool result records."""
    return mechanical_extract_structural_results(
        analysis_name=analysis_name,
        transport=transport,
        wait_timeout=wait_timeout,
    )


@mcp.tool()
def mechanical_extract_modal_results_tool(
    analysis_names: list[str] | None = None,
    mode_count: int = 6,
    transport: str = "queue",
    wait_timeout: float = 15.0,
) -> dict:
    """Extract modal frequencies and compare baseline with prestressed modes."""
    return mechanical_extract_modal_results(
        analysis_names=analysis_names,
        mode_count=mode_count,
        transport=transport,
        wait_timeout=wait_timeout,
    )


@mcp.tool()
def mechanical_export_evidence_tool(
    output_dir: str,
    result_names: list[str],
    overwrite_policy: str = "error",
    transport: str = "queue",
    wait_timeout: float = 30.0,
) -> dict:
    """Export result images and tables with error, versioned, or replace policy."""
    return mechanical_export_evidence(
        output_dir=output_dir,
        result_names=result_names,
        overwrite_policy=overwrite_policy,
        transport=transport,
        wait_timeout=wait_timeout,
    )


@mcp.tool()
def workbench_session_status_tool() -> dict:
    """Inspect Workbench/Mechanical processes and managed MCP sessions."""
    return workbench_session_status()


@mcp.tool()
def workbench_bootstrap_current_tool(
    expected_project_path: str | None = None,
    expected_system_name: str | None = None,
    security: str = "wnua",
    host: str = "localhost",
    bridge_timeout: float = 10.0,
) -> dict:
    """Safely attach to the one existing Workbench through its live bridge."""
    return workbench_bootstrap_current(
        expected_project_path=expected_project_path,
        expected_system_name=expected_system_name,
        security=security,
        host=host,
        bridge_timeout=bridge_timeout,
    )


@mcp.tool()
def workbench_attach_current_tool(
    port: int,
    security: str = "mtls",
    host: str = "localhost",
) -> dict:
    """Attach to an existing Workbench instance whose StartServer port is known."""
    return workbench_attach_current(port=port, security=security, host=host)


@mcp.tool()
def workbench_launch_managed_tool(
    version: str = "252",
    show_gui: bool = True,
    server_workdir: str | None = None,
    use_insecure_connection: bool = False,
) -> dict:
    """Launch one PyWorkbench-managed instance; refuse when Workbench already exists."""
    return workbench_launch_managed(
        version=version,
        show_gui=show_gui,
        server_workdir=server_workdir,
        use_insecure_connection=use_insecure_connection,
    )


@mcp.tool()
def workbench_project_inventory_tool(session_id: str) -> dict:
    """List the active Workbench project and its exact internal system names."""
    return workbench_project_inventory(session_id=session_id)


@mcp.tool()
def workbench_project_open_tool(session_id: str, project_path: str) -> dict:
    """Open an existing .wbpj in a managed empty Workbench session."""
    return workbench_project_open(session_id=session_id, project_path=project_path)


@mcp.tool()
def workbench_project_save_as_tool(
    session_id: str,
    target_path: str,
    overwrite: bool = False,
) -> dict:
    """Save the active Workbench project under a new path without overwriting by default."""
    return workbench_project_save_as(
        session_id=session_id,
        target_path=target_path,
        overwrite=overwrite,
    )


@mcp.tool()
def workbench_model_open_tool(
    session_id: str,
    system_name: str | None = None,
    transport_mode: str | None = None,
    connect_timeout: float = 120.0,
    mechanical_port: int | None = None,
) -> dict:
    """Start and connect to the Mechanical Model for one exact Workbench system."""
    return workbench_model_open(
        session_id=session_id,
        system_name=system_name,
        transport_mode=transport_mode,
        connect_timeout=connect_timeout,
        mechanical_port=mechanical_port,
    )


@mcp.tool()
def workbench_model_state_tool(
    model_session_id: str,
    expected_body_count: int | None = None,
    expected_analysis_count: int | None = None,
    expected_project_path: str | None = None,
    expected_system_name: str | None = None,
    expected_body_names: list[str] | None = None,
    expected_analysis_names: list[str] | None = None,
    expected_analysis_types: list[str] | None = None,
) -> dict:
    """Verify a Workbench-managed Mechanical Model by body and analysis counts."""
    return workbench_model_state(
        model_session_id=model_session_id,
        expected_body_count=expected_body_count,
        expected_analysis_count=expected_analysis_count,
        expected_project_path=expected_project_path,
        expected_system_name=expected_system_name,
        expected_body_names=expected_body_names,
        expected_analysis_names=expected_analysis_names,
        expected_analysis_types=expected_analysis_types,
    )


@mcp.tool()
def workbench_model_execute_python_tool(model_session_id: str, code: str) -> dict:
    """Execute Mechanical Python in one explicitly selected model session."""
    return workbench_model_execute_python(model_session_id=model_session_id, code=code)


@mcp.tool()
def workbench_session_disconnect_tool(session_id: str) -> dict:
    """Disconnect MCP clients without closing Workbench or Mechanical processes."""
    return workbench_session_disconnect(session_id=session_id)


def main() -> None:
    """Run the stdio MCP server without a Unicode startup banner."""

    # Codex consumes MCP stdio and diagnostic streams as UTF-8.  Suppress the
    # Rich/Unicode startup banner so a Windows legacy code page cannot corrupt
    # the startup stream before the initialize handshake completes.
    mcp.run(show_banner=False)


if __name__ == "__main__":
    main()
