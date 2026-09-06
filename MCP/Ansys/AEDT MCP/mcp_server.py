#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import ImageContent, TextContent

from aedt_guidelines import get_guidelines
from aedt_installation import check_aedt_installation
from aedt_launcher import AedtLauncher
from aedt_target import AedtTarget
from session_discovery import SessionDiscovery
from worker_client import WorkerClient

AEDTAppType = Literal[
    "Hfss",
    "Maxwell2d",
    "Maxwell3d",
    "Q3d",
    "Q2d",
    "Icepak",
    "Circuit",
    "TwinBuilder",
    "Mechanical",
    "Emit",
    "RMXprt",
    "Hfss3dLayout",
]
GuidelinesContent = Literal[
    "workflow",
    "hfss",
    "maxwell",
    "icepak",
    "circuit",
    "geometry",
    "mesh",
    "boundaries",
    "postprocessing",
    "parametric",
]


INSTRUCTIONS = """Control Ansys Electronics Desktop through external PyAEDT brokers.

Call check_aedt_installed and check_aedt_status first. Every operation that
touches AEDT requires exactly one explicit PID or gRPC port; there is no implicit
or automatic session target. Prefer the gRPC port returned by launch_aedt for
MCP-launched sessions. The official PyAEDT-style tools support HFSS, Maxwell,
Icepak, Q2D/Q3D, Circuit, Twin Builder, Mechanical, Emit, RMxprt, and HFSS 3D
Layout. Each target reuses one external broker. Call disconnect_from_aedt or
release_connection when finished; MCP shutdown also releases PyAEDT.
"""

mcp = FastMCP("ansys-aedt-mcp-server", instructions=INSTRUCTIONS)
worker_client = WorkerClient()
session_discovery = SessionDiscovery(worker_client=worker_client)
aedt_launcher = AedtLauncher(worker_client=worker_client)


def _target(pid: int | None, port: int | None) -> AedtTarget:
    return AedtTarget.from_values(pid=pid, port=port)


async def _worker_call(
    command: str,
    *,
    pid: int | None,
    port: int | None,
    arguments: dict[str, Any] | None = None,
    timeout: float | None = None,
) -> dict[str, Any]:
    target = _target(pid, port)
    result = await worker_client.execute_async(
        target,
        command,
        arguments or {},
        timeout=timeout,
    )
    if not isinstance(result, dict):
        raise TypeError(f"AEDT worker command {command} returned a non-object result")
    return result


@mcp.tool()
async def list_aedt_sessions() -> dict[str, Any]:
    """List all detected AEDT processes and listener ports without attaching."""
    sessions = await asyncio.to_thread(session_discovery.list_sessions)
    return {"sessions": sessions, "selection_required": True}


@mcp.tool()
async def check_aedt_installed() -> dict[str, Any]:
    """Check local AEDT and PyAEDT installations without starting AEDT."""
    # PyAEDT's Windows installation discovery may touch thread-affine registry
    # state, so keep this short read-only probe on the MCP request thread.
    return check_aedt_installation()


@mcp.tool()
async def check_aedt_status(
    pid: int | None = None,
    port: int | None = None,
    timeout: float | None = None,
) -> dict[str, Any]:
    """Discover AEDT sessions, or probe one explicitly selected target."""
    if pid is None and port is None:
        sessions = await asyncio.to_thread(session_discovery.list_sessions)
        return {
            "connected": False,
            "sessions": sessions,
            "session_count": len(sessions),
            "selection_required": bool(sessions),
        }
    return await _worker_call("ping", pid=pid, port=port, timeout=timeout)


@mcp.tool()
async def launch_aedt(
    version: str | None = None,
    non_graphical: bool = False,
    confirm_new_session: bool | None = None,
    application: AEDTAppType | None = None,
    port: int = 0,
    install_dir: str = "",
    timeout: float | None = None,
) -> dict[str, Any]:
    """Launch an AEDT gRPC session, optionally opening a solver application."""
    sessions = await asyncio.to_thread(session_discovery.list_sessions)
    if sessions and confirm_new_session is False:
        return {
            "launched": False,
            "confirmation_required": True,
            "message": (
                "AEDT is already running. Select an existing PID/port, or call "
                "launch_aedt again with confirm_new_session=true."
            ),
            "sessions": sessions,
        }
    selected_version = version or "2026.1"
    result = await asyncio.to_thread(
        aedt_launcher.launch,
        version=selected_version,
        port=port,
        install_dir=install_dir or None,
        non_graphical=non_graphical,
        timeout=timeout,
    )
    result["launched"] = True
    if application:
        result["application"] = await _worker_call(
            "create_design",
            pid=None,
            port=int(result["port"]),
            arguments={"app_type": application},
            timeout=timeout,
        )
    return result


@mcp.tool()
async def connect_to_aedt(
    pid: int | None = None,
    port: int | None = None,
    machine: str = "localhost",
    version: str | None = None,
    non_graphical: bool = True,
    project_name: str | None = None,
    design_name: str | None = None,
    timeout: float | None = None,
) -> dict[str, Any]:
    """Connect a broker to one explicit local AEDT PID or gRPC port."""
    if machine.lower() not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError(
            "this explicit-target AEDT MCP currently supports local sessions only"
        )
    return await _worker_call(
        "connect_to_aedt",
        pid=pid,
        port=port,
        arguments={
            "machine": machine,
            "version": version,
            "non_graphical": non_graphical,
            "project_name": project_name,
            "design_name": design_name,
        },
        timeout=timeout,
    )


@mcp.tool()
async def disconnect_from_aedt(
    pid: int | None = None,
    port: int | None = None,
    close_projects: bool = False,
    close_desktop: bool | None = None,
    timeout: float | None = None,
) -> dict[str, Any]:
    """Disconnect one broker, explicitly choosing whether AEDT should close."""
    if close_desktop is None:
        return {
            "disconnected": False,
            "choice_required": True,
            "message": (
                "Set close_desktop=false to keep AEDT open or true to close it."
            ),
        }
    target = _target(pid, port)
    result = await _worker_call(
        "disconnect_from_aedt",
        pid=pid,
        port=port,
        arguments={
            "close_projects": close_projects,
            "close_desktop": close_desktop,
        },
        timeout=timeout,
    )
    await worker_client.release_async(target, timeout=timeout)
    return result


@mcp.tool()
async def check_aedt_connection(
    pid: int | None = None,
    port: int | None = None,
    timeout: float | None = None,
) -> dict[str, Any]:
    """Run a real PyAEDT health probe against one explicit PID or gRPC port."""
    return await _worker_call("ping", pid=pid, port=port, timeout=timeout)


@mcp.tool()
async def release_connection(
    pid: int | None = None,
    port: int | None = None,
    timeout: float | None = None,
) -> dict[str, Any]:
    """Release the broker for one explicit AEDT target without closing AEDT."""
    target = _target(pid, port)
    return await worker_client.release_async(target, timeout=timeout)


@mcp.tool()
async def get_pyaedt_logs(
    tail_lines: int = 200,
    contains: str | None = None,
    max_chars: int = 40000,
    pid: int | None = None,
    port: int | None = None,
    timeout: float | None = None,
) -> dict[str, Any]:
    """Return PyAEDT file logs and native AEDT messages for one target."""
    return await _worker_call(
        "get_pyaedt_logs",
        pid=pid,
        port=port,
        arguments={
            "tail_lines": tail_lines,
            "contains": contains,
            "max_chars": max_chars,
        },
        timeout=timeout,
    )


@mcp.tool()
async def run_python_script(
    script_path: str,
    pid: int | None = None,
    port: int | None = None,
    timeout: float | None = None,
) -> dict[str, Any]:
    """Execute a Python script through the selected AEDT Desktop session."""
    return await _worker_call(
        "run_python_script",
        pid=pid,
        port=port,
        arguments={"script_path": script_path},
        timeout=timeout,
    )


@mcp.tool()
async def run_python_code(
    code: str,
    pid: int | None = None,
    port: int | None = None,
    timeout: float | None = None,
) -> dict[str, Any]:
    """Execute inline Python in the persistent PyAEDT broker namespace."""
    return await _worker_call(
        "run_python_code",
        pid=pid,
        port=port,
        arguments={"code": code},
        timeout=timeout,
    )


@mcp.tool()
async def list_projects(
    pid: int | None = None,
    port: int | None = None,
    timeout: float | None = None,
) -> dict[str, Any]:
    """List all open projects in one explicit AEDT target."""
    return await _worker_call("list_projects", pid=pid, port=port, timeout=timeout)


@mcp.tool()
async def list_designs(
    project_name: str | None = None,
    pid: int | None = None,
    port: int | None = None,
    timeout: float | None = None,
) -> dict[str, Any]:
    """List designs in one project or across all open projects."""
    return await _worker_call(
        "list_designs",
        pid=pid,
        port=port,
        arguments={"project_name": project_name},
        timeout=timeout,
    )


@mcp.tool()
async def open_project(
    project_path: str,
    design_name: str | None = None,
    pid: int | None = None,
    port: int | None = None,
    timeout: float | None = None,
) -> dict[str, Any]:
    """Open an AEDT project and optionally activate a named design."""
    return await _worker_call(
        "open_project",
        pid=pid,
        port=port,
        arguments={
            "project_path": project_path,
            "design_name": design_name,
        },
        timeout=timeout,
    )


@mcp.tool()
async def create_design(
    app_type: AEDTAppType,
    design_name: str | None = None,
    project_name: str | None = None,
    solution_type: str | None = None,
    pid: int | None = None,
    port: int | None = None,
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create HFSS, Maxwell, Icepak, Q2D/Q3D, Circuit, or another AEDT design."""
    return await _worker_call(
        "create_design",
        pid=pid,
        port=port,
        arguments={
            "app_type": app_type,
            "design_name": design_name,
            "project_name": project_name,
            "solution_type": solution_type,
        },
        timeout=timeout,
    )


@mcp.tool()
async def get_project_info(
    pid: int | None = None,
    port: int | None = None,
    timeout: float | None = None,
) -> dict[str, Any]:
    """Return project and active design metadata for one explicit AEDT target."""
    return await _worker_call("project_info", pid=pid, port=port, timeout=timeout)


@mcp.tool()
async def close_projects(
    project_names: list[str],
    save: bool = False,
    pid: int | None = None,
    port: int | None = None,
    timeout: float | None = None,
) -> dict[str, Any]:
    """Close only the named projects in one explicit AEDT target."""
    return await _worker_call(
        "close_projects",
        pid=pid,
        port=port,
        arguments={"project_names": project_names, "save": save},
        timeout=timeout,
    )


@mcp.tool()
async def create_hfss_design(
    project_name: str,
    design_name: str,
    solution_type: str = "DrivenModal",
    pid: int | None = None,
    port: int | None = None,
    timeout: float | None = None,
) -> dict[str, Any]:
    """Create or activate a named HFSS design in one explicit AEDT target."""
    return await _worker_call(
        "create_hfss_design",
        pid=pid,
        port=port,
        arguments={
            "project_name": project_name,
            "design_name": design_name,
            "solution_type": solution_type,
        },
        timeout=timeout,
    )


@mcp.tool()
async def save_project(
    project_name: str | None = None,
    save_as: str | None = None,
    path: str = "",
    pid: int | None = None,
    port: int | None = None,
    timeout: float | None = None,
) -> dict[str, Any]:
    """Save a named or active project, optionally to a new path."""
    return await _worker_call(
        "save_project",
        pid=pid,
        port=port,
        arguments={
            "project_name": project_name,
            "save_as": save_as,
            "path": path,
        },
        timeout=timeout,
    )


@mcp.tool()
async def validate_design(
    project_name: str | None = None,
    design_name: str | None = None,
    pid: int | None = None,
    port: int | None = None,
    timeout: float | None = None,
) -> dict[str, Any]:
    """Validate an AEDT design without starting a solve."""
    return await _worker_call(
        "validate_design",
        pid=pid,
        port=port,
        arguments={
            "project_name": project_name,
            "design_name": design_name,
        },
        timeout=timeout,
    )


@mcp.tool()
async def analyze_design(
    setup_name: str | None = None,
    project_name: str | None = None,
    design_name: str | None = None,
    num_cores: int | None = None,
    num_tasks: int | None = None,
    num_gpus: int | None = None,
    acf_file: str | None = None,
    use_auto_settings: bool = True,
    solve_in_batch: bool = False,
    machine: str = "localhost",
    run_in_thread: bool = False,
    revert_to_initial_mesh: bool = False,
    analyze_all_designs: bool = False,
    icepak_safe_mode: bool = True,
    pid: int | None = None,
    port: int | None = None,
    timeout: float | None = None,
) -> dict[str, Any]:
    """Validate and submit an analysis; Icepak uses safe single-core defaults."""
    return await _worker_call(
        "analyze_design",
        pid=pid,
        port=port,
        arguments={
            "setup_name": setup_name,
            "project_name": project_name,
            "design_name": design_name,
            "num_cores": num_cores,
            "num_tasks": num_tasks,
            "num_gpus": num_gpus,
            "acf_file": acf_file,
            "use_auto_settings": use_auto_settings,
            "solve_in_batch": solve_in_batch,
            "machine": machine,
            "run_in_thread": run_in_thread,
            "revert_to_initial_mesh": revert_to_initial_mesh,
            "analyze_all_designs": analyze_all_designs,
            "icepak_safe_mode": icepak_safe_mode,
        },
        timeout=timeout if timeout is not None else 600.0,
    )


@mcp.tool()
async def export_results(
    output_path: str,
    export_type: str = "touchstone",
    setup_name: str | None = None,
    pid: int | None = None,
    port: int | None = None,
    timeout: float | None = None,
) -> dict[str, Any]:
    """Export results, including Icepak residual history and mesh statistics."""
    return await _worker_call(
        "export_results",
        pid=pid,
        port=port,
        arguments={
            "output_path": output_path,
            "export_type": export_type,
            "setup_name": setup_name,
        },
        timeout=timeout if timeout is not None else 600.0,
    )


@mcp.tool()
async def screenshot(
    path: str = "screenshot.jpg",
    project: str | None = None,
    design: str | None = None,
    plot_type: str = "model",
    resolution: Literal["1080p", "4k"] = "1080p",
    open_viewer: bool = True,
    pid: int | None = None,
    port: int | None = None,
    timeout: float | None = None,
) -> list[TextContent | ImageContent]:
    """Capture an AEDT design view and return MCP text and image content."""
    result = await _worker_call(
        "screenshot",
        pid=pid,
        port=port,
        arguments={
            "path": path,
            "project": project,
            "design": design,
            "plot_type": plot_type,
            "resolution": resolution,
            "open_viewer": open_viewer,
        },
        timeout=timeout,
    )
    encoded = str(result.pop("data_base64"))
    mime_type = str(result.pop("mime_type", "image/jpeg"))
    return [
        TextContent(
            type="text",
            text=json.dumps(result, ensure_ascii=False, indent=2),
        ),
        ImageContent(type="image", data=encoded, mimeType=mime_type),
    ]


@mcp.tool()
async def export_config(
    output: str | None = None,
    project: str | None = None,
    design: str | None = None,
    overwrite: bool = False,
    pid: int | None = None,
    port: int | None = None,
    timeout: float | None = None,
) -> dict[str, Any]:
    """Export an active design configuration as JSON and return it inline."""
    return await _worker_call(
        "export_config",
        pid=pid,
        port=port,
        arguments={
            "output": output,
            "project": project,
            "design": design,
            "overwrite": overwrite,
        },
        timeout=timeout,
    )


@mcp.tool()
async def clear_aedt(
    close_projects: bool = True,
    pid: int | None = None,
    port: int | None = None,
    timeout: float | None = None,
) -> dict[str, Any]:
    """Clear AEDT messages and optionally close all open projects."""
    return await _worker_call(
        "clear_aedt",
        pid=pid,
        port=port,
        arguments={"close_projects": close_projects},
        timeout=timeout,
    )


@mcp.tool()
async def get_model_info(
    design_name: str | None = None,
    pid: int | None = None,
    port: int | None = None,
    timeout: float | None = None,
) -> dict[str, Any]:
    """Return active model, design type, and project path metadata."""
    return await _worker_call(
        "get_model_info",
        pid=pid,
        port=port,
        arguments={"design_name": design_name},
        timeout=timeout,
    )


@mcp.tool()
def get_guidelines_for(content: GuidelinesContent) -> str:
    """Return solver and workflow guidance, including an Icepak checklist."""
    return get_guidelines(content)


@mcp.tool()
async def start_analysis(
    project_name: str,
    design_name: str,
    setup_name: str,
    pid: int | None = None,
    port: int | None = None,
    blocking: bool = False,
    timeout: float | None = None,
) -> dict[str, Any]:
    """Start a named HFSS analysis; non-blocking is the default."""
    return await _worker_call(
        "start_analysis",
        pid=pid,
        port=port,
        arguments={
            "project_name": project_name,
            "design_name": design_name,
            "setup_name": setup_name,
            "blocking": blocking,
        },
        timeout=timeout,
    )


@mcp.tool()
async def get_analysis_status(
    project_name: str,
    design_name: str,
    setup_name: str = "",
    pid: int | None = None,
    port: int | None = None,
    timeout: float | None = None,
) -> dict[str, Any]:
    """Return running state and setup metadata for one explicit HFSS design."""
    return await _worker_call(
        "analysis_status",
        pid=pid,
        port=port,
        arguments={
            "project_name": project_name,
            "design_name": design_name,
            "setup_name": setup_name,
        },
        timeout=timeout,
    )


@mcp.tool()
async def build_wr90_waveguide(
    pid: int | None = None,
    port: int | None = None,
    project_name: str = "Classic_WR90_Waveguide",
    design_name: str = "WR90_TE10",
    output_dir: str = "",
    solve: bool = True,
    timeout: float | None = None,
) -> dict[str, Any]:
    """Build, validate, solve, and export a classic WR-90 TE10 HFSS case."""
    destination = output_dir.strip() or str(
        Path(__file__).resolve().parent / "test-artifacts" / "WR90_Waveguide"
    )
    return await _worker_call(
        "build_wr90_waveguide",
        pid=pid,
        port=port,
        arguments={
            "project_name": project_name,
            "design_name": design_name,
            "solution_type": "DrivenModal",
            "output_dir": destination,
            "solve": solve,
        },
        timeout=timeout if timeout is not None else 1800.0,
    )


@mcp.resource("aedt://status")
def aedt_status() -> str:
    """Return discovery-only status without attaching to any AEDT process."""
    return json.dumps(
        {
            "connected": False,
            "selection_required": True,
            "sessions": session_discovery.list_sessions(),
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.resource("aedt://agent-instructions")
def agent_instructions() -> str:
    return INSTRUCTIONS


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
