# Copyright (C) 2026 Synopsys, Inc. and ANSYS, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""List of tools in PyAEDT-MCP.

This module provides MCP tools for interacting with Ansys Electronics Desktop (AEDT)
through PyAEDT library. It supports all AEDT applications including HFSS, Maxwell,
Icepak, Circuit, and Q3D.
"""

import base64
import json
import os
from pathlib import Path
import shutil
import subprocess  # nosec B404
import sys
import tempfile
from typing import Any, Literal

from ansys.aedt.core.internal.aedt_versions import aedt_versions
from fastmcp.server import Context
from fastmcp.server.server import get_logger

from ansys.aedt.mcp import app
from ansys.aedt.mcp.helpers import (
    _is_docker,
    _probe_grpc_endpoint,
    discover_available_aedt_sessions,
    get_aedt_info,
)
from ansys.aedt.mcp.server import session
from mcp.types import ImageContent, TextContent

logger = get_logger(__name__)


# Tag applied to all tools that require an active AEDT connection.
# These tools are disabled at startup (before AEDT is connected) and enabled
# once a connection is established via connect_to_aedt or launch_aedt.
REQUIRES_AEDT_TAG = "requires_aedt"

# Tool timeout tiers (seconds)
_TIMEOUT_QUICK = 30  # status checks, listing, info queries
_TIMEOUT_MEDIUM = 120  # connect, open/save, create design, screenshot
_TIMEOUT_LONG = 600  # launch, script execution, analysis, exports


def _build_disconnected_status_message(connectable_sessions: list[dict[str, Any]]) -> str:
    """Build a user-facing status message when the MCP is not attached to AEDT."""
    base_message = (
        "No AEDT connection is available in this MCP session. "
        "Use 'connect_to_aedt' or 'launch_aedt' to establish a connection."
    )
    if not connectable_sessions:
        return base_message
    if len(connectable_sessions) == 1:
        session_info = connectable_sessions[0]
        return (
            f"{base_message} Found one running gRPC AEDT session on port {session_info['port']} "
            "that can be attached with 'connect_to_aedt', or launch a new session with "
            "'launch_aedt(confirm_new_session=True)'."
        )
    session_list = ", ".join(str(session_info["port"]) for session_info in connectable_sessions)
    return (
        f"{base_message} Multiple running gRPC AEDT sessions are available on "
        f"ports {session_list}. "
        "Ask the user which session to connect to, or whether to open a new session, "
        "before calling 'connect_to_aedt' or 'launch_aedt(confirm_new_session=True)'."
    )


def _build_launch_blocked_message(connectable_sessions: list[dict[str, Any]]) -> str | None:
    """Build a user-facing message when launching should defer to an existing session."""
    if not connectable_sessions:
        return None
    if len(connectable_sessions) == 1:
        session_info = connectable_sessions[0]
        return (
            "A running AEDT gRPC session is already available. "
            f"Ask the user whether to connect to PID {session_info['pid']} on port "
            f"{session_info['port']} or to open a new session. If the user wants a new AEDT "
            "session, call launch_aedt(confirm_new_session=True)."
        )
    return (
        "Multiple running AEDT gRPC sessions are already available. "
        "Ask the user which session to connect to, or whether to open a new session. "
        "If the user wants a new AEDT session, call 'launch_aedt(confirm_new_session=True)'.\n"
        + _summarize_available_sessions(connectable_sessions)
    )


def _summarize_available_sessions(sessions: list[dict[str, Any]]) -> str:
    """Format discovered sessions for a selection prompt."""
    lines = []
    for session_info in sessions:
        non_graphical = session_info["non_graphical"]
        if non_graphical is None:
            ui_mode = "Unknown"
        else:
            ui_mode = "Non-graphical" if non_graphical else "Graphical"
        lines.append(
            "- "
            f"PID {session_info['pid']}, "
            f"port {session_info['port']}, "
            f"version {session_info['version']}, "
            f"UI {ui_mode}, "
            f"edition {'Student' if session_info.get('student_version', False) else 'Standard'}"
        )
    return "\n".join(lines)


def _open_file_in_default_viewer(path: Path) -> str | None:
    """Open a file with the system's default viewer.

    Returns
    -------
    str | None
        ``None`` when the file was opened successfully, otherwise a short
        message describing why the viewer could not be launched.
    """
    if _is_docker():
        return "Viewer launch skipped inside Docker."

    try:
        if hasattr(os, "startfile"):
            os.startfile(path)  # type: ignore[attr-defined]  # nosec B606
        elif sys.platform == "darwin":
            viewer = shutil.which("open")
            if viewer is None:
                return "Viewer launch failed: 'open' executable was not found."
            # The executable path is resolved explicitly and arguments are passed as a list.
            subprocess.Popen([viewer, str(path)])  # nosec
        else:
            viewer = shutil.which("xdg-open")
            if viewer is None:
                return "Viewer launch failed: 'xdg-open' executable was not found."
            # The executable path is resolved explicitly and arguments are passed as a list.
            subprocess.Popen([viewer, str(path)])  # nosec
    except Exception as exc:
        return f"Viewer launch failed: {exc}"

    return None


def _configure_pyaedt_runtime_settings(enable_grpc: bool = False) -> None:
    """Configure PyAEDT runtime settings for safer MCP execution.

    Parameters
    ----------
    enable_grpc : bool, default: False
        Whether to force gRPC API mode.
    """
    try:
        # Preferred import path in newer PyAEDT versions.
        from ansys.aedt.core import settings
    except Exception:
        # Backward-compatible import path.
        from ansys.aedt.core.generic.settings import settings

    if enable_grpc:
        settings.use_grpc_api = True

    # Prevent AEDT shutdown when user-provided code raises.
    settings.release_on_exception = False


def _resolve_pyaedt_log_file() -> str | None:
    """Resolve the active PyAEDT global log file path.

    Returns
    -------
    str | None
        Absolute path to the active PyAEDT log file, or ``None`` when no
        readable log file can be resolved.
    """
    try:
        from ansys.aedt.core.aedt_logger import pyaedt_logger

        raw_logger = getattr(pyaedt_logger, "logger", None)
        if raw_logger is not None:
            for handler in getattr(raw_logger, "handlers", []):
                handler_path = getattr(handler, "baseFilename", None)
                if handler_path and Path(handler_path).is_file():
                    return str(Path(handler_path).expanduser().resolve())

        logger_filename = getattr(pyaedt_logger, "filename", None)
        if logger_filename and Path(logger_filename).is_file():
            return str(Path(logger_filename).expanduser().resolve())
    except Exception:
        logger.debug("Failed to resolve PyAEDT log file from pyaedt_logger.", exc_info=True)

    try:
        from ansys.aedt.core import settings

        logger_file_path = getattr(settings, "logger_file_path", None)
        if logger_file_path:
            candidate = Path(logger_file_path).expanduser()
            if candidate.is_file():
                return str(candidate.resolve())
            if candidate.is_dir():
                log_candidates = sorted(
                    candidate.glob("pyaedt*.log"),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                )
                if log_candidates:
                    return str(log_candidates[0].resolve())
    except Exception:
        logger.debug(
            "Failed to resolve PyAEDT log file from settings.logger_file_path.",
            exc_info=True,
        )

    return None


# AEDT Application types supported
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


def _get_aedt_app_class(app_type: AEDTAppType) -> Any | None:
    """Resolve an AEDT application type to the corresponding PyAEDT class."""
    import ansys.aedt.core as aedt

    app_map = {
        "Hfss": aedt.Hfss,
        "Maxwell2d": aedt.Maxwell2d,
        "Maxwell3d": aedt.Maxwell3d,
        "Q3d": aedt.Q3d,
        "Q2d": aedt.Q2d,
        "Icepak": aedt.Icepak,
        "Circuit": aedt.Circuit,
        "TwinBuilder": aedt.TwinBuilder,
        "Mechanical": aedt.Mechanical,
        "Emit": aedt.Emit,
        "RMXprt": getattr(aedt, "Rmxprt", None),
        "Hfss3dLayout": aedt.Hfss3dLayout,
    }
    return app_map.get(app_type)


@app.tool(tags={"aedt_tools"}, timeout=_TIMEOUT_QUICK)
def check_aedt_status(ctx: Context) -> str:
    """Check the status of AEDT initialization.

    This tool is always reachable, even before a connection has been established.
    When no AEDT session is active, it returns a short hint describing how to
    establish one (``launch_aedt`` or ``connect_to_aedt``). When a session is
    active, it returns full status information.

    This makes the tool the recommended pre-flight call to decide whether to
    ``launch_aedt`` (no active session) or ``connect_to_aedt`` (existing
    session detected).

    This tool retrieves comprehensive information from the connected AEDT
    instance including version, active projects, designs, and
    connection details.

    Parameters
    ----------
    ctx : Context
        MCP context containing server session and application context.

    Returns
    -------
    str
        JSON string containing comprehensive AEDT status information including:

        - connection: Basic connection info (version, machine, port, is_grpc)
        - projects: List of open projects
        - active_project: Currently active project name
        - active_design: Currently active design name
        - installed_versions: Available AEDT versions on the system

        Returns an error message if AEDT is not available.
    """
    desktop = ctx.request_context.lifespan_context.desktop
    available_sessions = discover_available_aedt_sessions()
    connectable_sessions = [
        session_info for session_info in available_sessions if session_info.get("connectable")
    ]

    if desktop is None:
        payload = {
            "connected": False,
            "message": _build_disconnected_status_message(connectable_sessions),
            "available_sessions": available_sessions,
            "connectable_sessions": connectable_sessions,
            "session_count": len(available_sessions),
            "connectable_session_count": len(connectable_sessions),
        }
        return json.dumps(payload, indent=2)

    try:
        info = get_aedt_info(desktop)
        info["connected"] = True
        info["available_sessions"] = available_sessions
        info["connectable_sessions"] = connectable_sessions
        return json.dumps(info, indent=2)

    except Exception as e:
        error_msg = f"Error checking AEDT status: {str(e)}"
        logger.error(error_msg)
        return error_msg


@app.tool(tags={"aedt_tools"}, timeout=_TIMEOUT_QUICK)
def get_pyaedt_logs(
    ctx: Context,
    tail_lines: int = 200,
    contains: str | None = None,
    max_chars: int = 40000,
) -> str:
    """Return recent entries from the PyAEDT global logger.

    This tool reads the active PyAEDT global log file and returns a tail view
    of the log contents. Optionally filter lines using a case-insensitive
    substring.

    Parameters
    ----------
    ctx : Context
        MCP context. Included for tool signature consistency.
    tail_lines : int, default: 200
        Number of recent lines to return after filtering.
    contains : str, default: None
        Case-insensitive substring used to filter log lines.
    max_chars : int, default: 40000
        Hard cap for returned log text length.

    Returns
    -------
    str
        JSON string with log metadata and selected log text.
    """
    del ctx  # tool does not require an active AEDT connection

    if tail_lines <= 0:
        return "Invalid parameter: tail_lines must be greater than 0."
    if max_chars <= 0:
        return "Invalid parameter: max_chars must be greater than 0."

    safe_tail_lines = min(tail_lines, 5000)
    safe_max_chars = min(max_chars, 200000)

    try:
        log_file = _resolve_pyaedt_log_file()
        if log_file is None:
            return (
                "PyAEDT global log file could not be resolved. "
                "Run a PyAEDT operation first to initialize the logger."
            )

        with Path(log_file).open("r", encoding="utf-8", errors="replace") as file_handle:
            all_lines = file_handle.readlines()

        filtered_lines = all_lines
        if contains:
            filter_token = contains.lower()
            filtered_lines = [line for line in all_lines if filter_token in line.lower()]

        selected_lines = filtered_lines[-safe_tail_lines:]
        log_text = "".join(selected_lines)

        truncated = False
        if len(log_text) > safe_max_chars:
            log_text = log_text[-safe_max_chars:]
            truncated = True

        payload = {
            "log_file": log_file,
            "contains": contains,
            "total_lines": len(all_lines),
            "matched_lines": len(filtered_lines),
            "returned_lines": len(selected_lines),
            "tail_lines_requested": tail_lines,
            "max_chars_requested": max_chars,
            "truncated": truncated,
            "logs": log_text,
        }
        return json.dumps(payload, indent=2)

    except Exception as e:
        error_msg = f"Error reading PyAEDT logs: {str(e)}"
        logger.error(error_msg)
        return error_msg


@app.tool(tags={"aedt_tools"}, timeout=_TIMEOUT_QUICK)
def check_aedt_installed(ctx: Context) -> str:
    """Check if AEDT is installed on the system.

    This tool checks for valid AEDT installations on the system and
    returns information about available versions.

    When running inside a Docker container, the tool probes the remote
    gRPC endpoint (``AEDT_MACHINE:AEDT_PORT``) instead of searching
    for a local AEDT installation.

    Returns
    -------
    str
        Status message indicating whether AEDT is installed and which versions
        are available.
    """
    logger.info("Checking if AEDT is installed...")

    # ------- Docker path: probe the remote gRPC endpoint -------
    if _is_docker():
        host = os.environ.get("AEDT_MACHINE", "host.docker.internal")
        port = int(os.environ.get("AEDT_PORT", "50051"))
        probe = _probe_grpc_endpoint(host, port)
        if probe["reachable"]:
            return f"Running inside Docker. AEDT gRPC endpoint at {host}:{port} is reachable."
        return (
            f"Running inside Docker. AEDT gRPC endpoint at "
            f"{host}:{port} is NOT reachable (error: {probe['error']}). "
            f"Ensure AEDT is started with: ansysedt.exe -grpcsrv {port}"
        )

    # ------- Native path: search for local installation -------
    try:
        installed_versions = dict(aedt_versions.installed_versions)
        if not installed_versions:
            return "No AEDT versions found installed on this system."

        target_version = aedt_versions.current_version or aedt_versions.latest_version
        if target_version not in installed_versions:
            target_version = next(iter(installed_versions))

        return (
            f"AEDT is installed on this system.\n"
            f"Version: {target_version}\n"
            f"Installation Directory: {installed_versions[target_version]}\n"
            f"Installed Versions: {', '.join(installed_versions)}"
        )
    except Exception as e:
        error_msg = f"Error checking AEDT installation: {str(e)}"
        logger.error(error_msg)
        return error_msg


@app.tool(tags={"aedt_tools", "locked_connection"}, timeout=_TIMEOUT_MEDIUM)
async def launch_aedt(
    ctx: Context,
    version: str | None = None,
    non_graphical: bool = False,
    confirm_new_session: bool = False,
    application: AEDTAppType | None = None,
) -> str:
    """Launch a new AEDT instance.

    This tool starts a new AEDT instance using PyAEDT's ``Desktop`` class,
    or it launches directly into a specific AEDT application session when requested.
    The launched instance is automatically connected and stored in the context
    for subsequent operations.

    Parameters
    ----------
    ctx : Context
        MCP context containing server session and application context.
    version : str, default: None
        AEDT version to launch (such as ``"2026.1"`` or ``"261"``). If ``None``, the latest
        installed version is used.
    non_graphical : bool, default: False
        Whether to launch AEDT in non-graphical mode. If ``False``, AEDT launches with
        the GUI visible.
    confirm_new_session : bool, default: False
        Whether a new AEDT instance should be launched even
        when one or more connectable AEDT sessions are already available.
    application : AEDTAppType, default: None
        AEDT application to launch directly, such as ``"Hfss"`` or ``"Maxwell3d"``.
        If ``None``, AEDT launches in desktop mode.

    Returns
    -------
    str
        Launch status message with AEDT version and connection information.
    """
    launch_target = application or "Desktop"
    logger.info(f"Launching new AEDT {launch_target} instance...")

    # Docker guard: launching a local AEDT inside a container is not supported
    if _is_docker():
        return (
            "Launching a local AEDT instance from inside a Docker container "
            "is not supported. Use the connect_to_aedt tool to connect to an "
            "AEDT instance running on the host or a remote machine."
        )

    try:
        # Check if there's already a connection
        if ctx.request_context.lifespan_context.desktop is not None:
            return (
                "Already connected to an AEDT instance. "
                "Disconnect first using 'disconnect_from_aedt'."
            )

        if not confirm_new_session:
            discovered_sessions = [
                session_info
                for session_info in discover_available_aedt_sessions()
                if session_info.get("connectable")
            ]
            launch_blocked_message = _build_launch_blocked_message(discovered_sessions)
            if launch_blocked_message is not None:
                return launch_blocked_message

        from ansys.aedt.core import Desktop

        _configure_pyaedt_runtime_settings()

        kwargs: dict[str, Any] = {
            "non_graphical": non_graphical,
            "new_desktop": True,
        }

        if application is None:
            if version is None:
                version = aedt_versions.current_version or aedt_versions.latest_version
                if not version:
                    raise RuntimeError("No AEDT versions found installed on this system.")
            kwargs["version"] = version
            desktop = Desktop(**kwargs)
            launched_target = "AEDT"
        else:
            app_class = _get_aedt_app_class(application)
            if app_class is None:
                return f"Unsupported application type: {application}"

            if version is None:
                version = aedt_versions.current_version or aedt_versions.latest_version
                if not version:
                    raise RuntimeError("No AEDT versions found installed on this system.")
            kwargs["version"] = version
            app_instance = app_class(**kwargs)
            desktop = getattr(app_instance, "desktop_class", None)
            if desktop is None:
                raise RuntimeError(
                    f"Unable to resolve AEDT handle from launched {application} session."
                )
            launched_target = application

        # Store in context for later use
        ctx.request_context.lifespan_context.desktop = desktop
        ctx.request_context.lifespan_context.aedt_port = getattr(desktop, "port", None)

        await ctx.enable_components(tags={REQUIRES_AEDT_TAG})
        logger.info(f"AEDT launched successfully! Target: {launched_target}")
        return (
            f"Successfully launched {launched_target}\n"
            f"Version: {desktop.aedt_version_id}\n"
            f"Installation Directory: {desktop.aedt_install_dir}\n"
            f"Non-graphical Mode: {non_graphical}\n"
            f"gRPC Mode: {desktop.is_grpc_api}\n"
        )

    except Exception as e:
        error_msg = f"Failed to launch AEDT: {str(e)}"
        logger.error(error_msg)
        return error_msg


@app.tool(tags={"aedt_tools", "locked_connection"}, timeout=_TIMEOUT_MEDIUM)
async def connect_to_aedt(
    ctx: Context,
    port: int | None = None,
    machine: str = "localhost",
    version: str | None = None,
    non_graphical: bool = True,
    project_name: str | None = None,
    design_name: str | None = None,
) -> str:
    """Connect to an existing AEDT instance via gRPC.

    This tool establishes a connection to a running AEDT instance using gRPC.
    The AEDT instance must be started with a gRPC server enabled:
    `ansysedt.exe -grpcsrv <port>`

    Parameters
    ----------
    ctx : Context
        MCP context containing server session and application context.
    port : int, default: None
        gRPC port where AEDT is listening. If ``None``, the tool can
        auto-select a discovered local gRPC session or fall back to 50051.
    machine : str, default: ``"localhost"``
        Machine hostname or IP address where AEDT is running.
    version : str, default: ``None``
        AEDT version to connect to. If ``None``, the tool automatically detects
        the version.
    non_graphical : bool, default: ``True``
        Whether AEDT is running in non-graphical mode.
    project_name : str, default: ``None``
        Project name to activate when connecting directly to a design.
    design_name : str, default: ``None``
        Design name to attach directly to a PyAEDT application session.
        If ``None``, the connection remains at the AEDT level.

    Returns
    -------
    str
        Connection status message with AEDT version information.
    """
    logger.info("Connecting to AEDT instance at %s:%s...", machine, port or 50051)

    # Check if there's already a connection
    if ctx.request_context.lifespan_context.desktop is not None:
        return (
            "Already connected to an AEDT session. Disconnect first using 'disconnect_from_aedt'."
        )

    # Docker env-var override: when defaults are used and we are inside a
    # container, prefer AEDT_MACHINE / AEDT_PORT from the environment so
    # the container automatically reaches the host AEDT instance.
    if _is_docker():
        if machine == "localhost":
            machine = os.environ.get("AEDT_MACHINE", "host.docker.internal")
        if port is None:
            port = int(os.environ.get("AEDT_PORT", "50051"))
        logger.info(f"Docker detected – using AEDT endpoint {machine}:{port}")
    elif machine == "localhost" and port is None:
        discovered_sessions = [
            session_info
            for session_info in discover_available_aedt_sessions()
            if session_info.get("connectable")
        ]
        if len(discovered_sessions) == 1:
            port = int(discovered_sessions[0]["port"])
            logger.info("Auto-selected local AEDT gRPC session on port %s", port)
        elif len(discovered_sessions) > 1:
            return (
                "Multiple running AEDT gRPC sessions are available. "
                "Ask the user which one to attach, or whether to open a new session. "
                "If the user explicitly asks for a new session, call "
                "launch_aedt(confirm_new_session=True).\n"
                + _summarize_available_sessions(discovered_sessions)
            )

    if port is None:
        port = 50051

    try:
        from ansys.aedt.core import Desktop, get_pyaedt_app

        _configure_pyaedt_runtime_settings(enable_grpc=True)

        # Connect to existing AEDT instance
        kwargs: dict[str, Any] = {
            "non_graphical": non_graphical,
            "new_desktop": False,
            "machine": machine,
            "port": port,
        }

        if version is not None:
            kwargs["version"] = version

        desktop = Desktop(**kwargs)

        open_projects: list[str] = []
        try:
            project_list = getattr(desktop, "project_list", None)
            if project_list is not None:
                open_projects = list(project_list)
        except TypeError:
            open_projects = []

        connected_app = None
        if design_name is not None:
            connected_app = get_pyaedt_app(
                project_name=project_name,
                design_name=design_name,
                desktop=desktop,
            )

        # Store in context for later use
        ctx.request_context.lifespan_context.desktop = desktop
        ctx.request_context.lifespan_context.aedt_port = port

        await ctx.enable_components(tags={REQUIRES_AEDT_TAG})
        logger.info(f"Connected to AEDT successfully at {machine}:{port}!")
        message = (
            f"Successfully connected to AEDT at {machine}:{port}\n."
            f"Version: {desktop.aedt_version_id}\n"
            f"gRPC Mode: {desktop.is_grpc_api}\n"
        )
        if connected_app is not None:
            message += (
                f"Project: {connected_app.project_name}\n"
                f"Design: {connected_app.design_name}\n"
                f"Application: {connected_app.design_type}\n"
            )
        elif not open_projects:
            message += (
                "No open projects are available in this AEDT session. "
                "If the user asked for a specific solver such as Hfss, Maxwell3d, "
                "Maxwell2d, Icepak, Circuit, Q3d, Q2d, TwinBuilder, Mechanical, "
                "Emit, RMXprt, or Hfss3dLayout, call create_design with the matching "
                "app_type to open that workflow in this session.\n"
            )
            if design_name is None:
                message += (
                    "Tip: provide design_name"
                    + (" and project_name" if project_name is None else "")
                    + " if you want to connect directly to a specific AEDT design.\n"
                )
        else:
            message += (
                "Tip: provide design_name"
                + (" and project_name" if project_name is None else "")
                + " if you want to connect directly to a specific AEDT design.\n"
            )
        return message

    except Exception as e:
        error_msg = f"Failed to connect to AEDT at {machine}:{port}: {str(e)}"
        logger.error(error_msg)
        return error_msg


@app.tool(tags={"aedt_tools", "locked_connection", REQUIRES_AEDT_TAG}, timeout=_TIMEOUT_MEDIUM)
async def disconnect_from_aedt(
    ctx: Context,
    close_projects: bool = False,
    close_desktop: bool | None = None,
) -> str:
    """Disconnect from the AEDT instance.

    This tool detaches the MCP session from the AEDT instance and releases
    associated resources. It can either keep the AEDT window open or close
    the AEDT desktop entirely.

    Parameters
    ----------
    ctx : Context
        MCP context containing server session and application context.
    close_projects : bool, default: ``False``
        Whether to close all open projects before disconnecting.
    close_desktop : bool, default: ``None``
        Whether to close the AEDT desktop on disconnect. Set to ``False`` to
        keep the AEDT window open after detaching the MCP session. When ``None``,
        the tool asks the caller to choose before disconnecting.

    Returns
    -------
    str
        Disconnection status message.
    """
    desktop = ctx.request_context.lifespan_context.desktop

    if desktop is None:
        return "No AEDT connection to disconnect."

    if close_desktop is None:
        return (
            "Specify whether to close the AEDT desktop during disconnect. "
            "Use 'disconnect_from_aedt(close_desktop=False)' to keep the AEDT window open, "
            "or 'disconnect_from_aedt(close_desktop=True)' to close AEDT."
        )

    try:
        logger.info("Disconnecting from AEDT...")

        # Release AEDT
        desktop.release_desktop(close_projects=close_projects, close_on_exit=close_desktop)
        ctx.request_context.lifespan_context.desktop = None
        ctx.request_context.lifespan_context.aedt_port = None

        await ctx.disable_components(tags={REQUIRES_AEDT_TAG})
        logger.info("Disconnected from AEDT successfully!")
        if close_desktop:
            return "Successfully disconnected from AEDT and closed the desktop session."
        return "Successfully disconnected from AEDT while keeping the desktop session open."

    except Exception as e:
        error_msg = f"Error during AEDT disconnect: {str(e)}"
        logger.error(error_msg)
        ctx.request_context.lifespan_context.desktop = None
        ctx.request_context.lifespan_context.aedt_port = None
        return error_msg


@app.tool(tags={"aedt_tools", REQUIRES_AEDT_TAG}, timeout=_TIMEOUT_LONG)
def run_python_script(ctx: Context, script_path: str) -> str:
    """Execute a Python script file inside AEDT.

    This tool runs a Python script from a file path within the AEDT environment,
    using AEDT's built-in Python interpreter. The script has access to all AEDT
    APIs including oDesktop, oProject, and oDesign.

    Parameters
    ----------
    ctx : Context
        MCP context containing server session and application context.
    script_path : str
        Path to the Python script file to execute.

    Returns
    -------
    str
        Script execution result or error message.
    """
    desktop = ctx.request_context.lifespan_context.desktop

    if desktop is None:
        return "No AEDT connection is available. Use 'connect_to_aedt' or 'launch_aedt' first."

    try:
        if not Path(script_path).exists():
            return f"Script file not found: {script_path}"

        logger.info(f"Executing script: {script_path}")
        result = desktop.odesktop.RunScript(script_path)
        return f"Script executed successfully.\nResult: {result}"

    except Exception as e:
        error_msg = f"Error executing script {script_path}: {str(e)}"
        logger.error(error_msg)
        return error_msg


@app.tool(tags={"aedt_tools", REQUIRES_AEDT_TAG}, timeout=_TIMEOUT_LONG)
def run_python_code(ctx: Context, code: str) -> str:
    """Execute Python code inside AEDT.

    This tool runs inline Python code within the AEDT environment. The code
    has access to the connected AEDT instance via the ``desktop`` variable.

    Parameters
    ----------
    ctx : Context
        MCP context containing server session and application context.
    code : str
        The Python code to execute. The code has access to:

        - `desktop`: PyAEDT instance
        - `odesktop`: Native AEDT oDesktop COM object
        - `aedt_port`: gRPC port of the connected AEDT instance

    Returns
    -------
    str
        Code execution result or error message.
    """
    desktop = ctx.request_context.lifespan_context.desktop

    if desktop is None:
        return "No AEDT connection is available. Use 'connect_to_aedt' or 'launch_aedt' first."

    try:
        logger.info("Executing inline Python code in AEDT...")

        _configure_pyaedt_runtime_settings()

        # Include aedt_port so user code can do Hfss(..., port=aedt_port)
        local_ns = {
            "desktop": desktop,
            "odesktop": desktop.odesktop,
            "aedt_port": getattr(desktop, "port", ctx.request_context.lifespan_context.aedt_port),
        }

        # This tool's explicit contract is to execute user-provided Python inside AEDT.
        exec(code, local_ns)  # nosec B102
        result = local_ns.get("result", "Code executed successfully. (No result variable set.)")
        return str(result)

    except Exception as e:
        error_msg = f"Error executing code: {str(e)}"
        logger.error(error_msg)
        return error_msg


@app.tool(tags={"aedt_tools", REQUIRES_AEDT_TAG}, timeout=_TIMEOUT_QUICK)
def list_designs(ctx: Context, project_name: str | None = None) -> str:
    """List projects and designs for the connected AEDT instance.

    Parameters
    ----------
    ctx : Context
        MCP context containing server session and application context.
    project_name : str, default: None
        Optional project name to limit the response to a single project.
        If``None``, all open projects and their designs are returned.

    Returns
    -------
    str
        JSON string containing the connected instance projects and designs.
    """
    desktop = ctx.request_context.lifespan_context.desktop

    if desktop is None:
        return "No AEDT connection is available. Use 'connect_to_aedt' or 'launch_aedt' first."

    try:
        if project_name is not None:
            projects = [project_name]
        else:
            projects = list(desktop.project_list)

        project_entries = []
        total_design_count = 0
        for project in projects:
            designs = desktop.design_list(project)
            project_entries.append(
                {
                    "project": project,
                    "designs": designs,
                    "count": len(designs),
                }
            )
            total_design_count += len(designs)

        active_project = None
        if callable(getattr(desktop, "active_project", None)):
            current_project = desktop.active_project()
            if current_project is not None and hasattr(current_project, "GetName"):
                active_project = str(current_project.GetName())

        active_design = None
        if callable(getattr(desktop, "active_design", None)):
            current_design = desktop.active_design()
            if current_design is not None and hasattr(current_design, "GetName"):
                active_design = str(current_design.GetName())

        result = {
            "active_project": active_project,
            "active_design": active_design,
            "projects": project_entries,
            "project_count": len(project_entries),
            "design_count": total_design_count,
        }
        if project_name is not None and project_entries:
            result["project"] = project_entries[0]["project"]
            result["designs"] = project_entries[0]["designs"]
            result["count"] = project_entries[0]["count"]
        return json.dumps(result, indent=2)

    except Exception as e:
        error_msg = f"Error listing designs: {str(e)}"
        logger.error(error_msg)
        return error_msg


@app.tool(tags={"aedt_tools", REQUIRES_AEDT_TAG}, timeout=_TIMEOUT_QUICK)
def list_projects(ctx: Context) -> str:
    """List all open AEDT projects.

    Parameters
    ----------
    ctx : Context
        MCP context containing server session and application context.

    Returns
    -------
    str
        JSON string containing the list of open projects and their count.
    """
    desktop = ctx.request_context.lifespan_context.desktop

    if desktop is None:
        return "No AEDT connection is available. Use 'connect_to_aedt' or 'launch_aedt' first."

    try:
        projects = list(desktop.project_list)
        result = {
            "open_projects": projects,
            "count": len(projects),
        }
        return json.dumps(result, indent=2)

    except Exception as e:
        error_msg = f"Error listing projects: {str(e)}"
        logger.error(error_msg)
        return error_msg


@app.tool(tags={"aedt_tools", REQUIRES_AEDT_TAG}, timeout=_TIMEOUT_MEDIUM)
def open_project(ctx: Context, project_path: str, design_name: str | None = None) -> str:
    """Open an AEDT project.

    Parameters
    ----------
    ctx : Context
        MCP context containing server session and application context.
    project_path : str, default: None
        Full path to the AEDT project file.
    design_name : str, default: None
        Name of the design to activate after opening. If ``None``, the first design
        is used

    Returns
    -------
    str
        Status message with project and design information.
    """
    desktop = ctx.request_context.lifespan_context.desktop

    if desktop is None:
        return "No AEDT connection is available. Use 'connect_to_aedt' or 'launch_aedt' first."

    try:
        if not Path(project_path).exists():
            return f"Project file not found: {project_path}"

        logger.info(f"Opening project: {project_path}")
        desktop.load_project(project_path, design_name=design_name)

        return (
            f"Successfully opened project: {project_path}\n"
            f"Active design: {design_name or 'First design in project'}"
        )

    except Exception as e:
        error_msg = f"Error opening project: {str(e)}"
        logger.error(error_msg)
        return error_msg


@app.tool(tags={"aedt_tools", REQUIRES_AEDT_TAG}, timeout=_TIMEOUT_MEDIUM)
def save_project(ctx: Context, project_name: str | None = None, save_as: str | None = None) -> str:
    """Save an AEDT project.

    Parameters
    ----------
    ctx : Context
        MCP context containing server session and application context.
    project_name : str, default: None
        Name of the project to save. If ``None``, the active project is saved.
    save_as : str, default: None
        Path to save the project to. If ``None``, the existing location is used.

    Returns
    -------
    str
        Status message confirming the save operation.
    """
    desktop = ctx.request_context.lifespan_context.desktop

    if desktop is None:
        return "No AEDT connection is available. Use 'connect_to_aedt' or 'launch_aedt' first."

    try:
        logger.info(f"Saving project: {project_name or 'active project'}")

        if save_as:
            desktop.save_project(project_path=save_as)
            return f"Project saved to: {save_as}"
        else:
            desktop.save_project(project_name=project_name)
            return f"Project saved successfully: {project_name or 'active project'}"

    except Exception as e:
        error_msg = f"Error saving project: {str(e)}"
        logger.error(error_msg)
        return error_msg


@app.tool(tags={"aedt_tools", REQUIRES_AEDT_TAG}, timeout=_TIMEOUT_MEDIUM)
def create_design(
    ctx: Context,
    app_type: AEDTAppType,
    design_name: str | None = None,
    project_name: str | None = None,
    solution_type: str | None = None,
) -> str:
    """Create a new design in AEDT.

    Parameters
    ----------
    ctx : Context
        MCP context containing server session and application context.
    app_type : str
        AEDT application type. Options are ``"Hfss"``, ``"Maxwell2d"``,
        ``"Maxwell3d"``, ``"Q3d"``, ``"Q2d"``, ``"Icepak"``, ``"Circuit"``,
        ``"TwinBuilder"``, ``"Mechanical"``, ``"Emit"``, ``"RMXprt"``,
        and ``"Hfss3dLayout"``.
    design_name : str, default: None
        Name for the new design. If ``None``, an auto-generated name is used.
    project_name : str, default: None
        Project to create design in. If ``None``, the active project is used.
    solution_type : str, default: None
        Solution type for the design (app-specific).

    Returns
    -------
    str
        Status message with the created design information.
    """
    desktop = ctx.request_context.lifespan_context.desktop

    if desktop is None:
        return "No AEDT connection is available. Use 'connect_to_aedt' or 'launch_aedt' first."

    try:
        app_class = _get_aedt_app_class(app_type)
        if app_class is None:
            return f"Unsupported application type: {app_type}"

        logger.info(f"Creating {app_type} design: {design_name}")

        kwargs: dict[str, Any] = {}
        if design_name:
            kwargs["design"] = design_name
        if project_name:
            kwargs["project"] = project_name
        if solution_type:
            kwargs["solution_type"] = solution_type

        app_instance = app_class(**kwargs)

        return (
            f"Successfully created {app_type} design\n"
            f"Design Name: {app_instance.design_name}\n"
            f"Project: {app_instance.project_name}\n"
            f"Solution Type: {app_instance.solution_type}\n"
        )

    except Exception as e:
        error_msg = f"Error creating design: {str(e)}"
        logger.error(error_msg)
        return error_msg


@app.tool(tags={"aedt_tools", REQUIRES_AEDT_TAG}, timeout=_TIMEOUT_LONG)
def analyze_design(
    ctx: Context,
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
) -> str:
    """Run analysis on an AEDT design.

    Parameters
    ----------
    ctx : Context
        MCP context containing server session and application context.
    setup_name : str, default: None
        Name of the setup to analyze. If ``None``, all setups in the target design
        are analyzed.
    project_name : str, default: None
        Name of the project to analyze. If ``None``, the active project is used.
    design_name : str, default: None
        Name of the design to analyze. If ``None``, the active design is used.
    num_cores : int, default: None
        Number of CPU cores to use for analysis.
    num_tasks : int, default: None
        Number of HPC tasks to use for analysis.
    num_gpus : int, default: None
        Number of GPUs to use for analysis.
    acf_file : str, default: None
        Full path to a custom ACF file for HPC configuration.
    use_auto_settings : bool, default: True
        Whether to use automatic HPC settings when supported.
    solve_in_batch : bool, default: False
        Whether to solve the design in batch mode.
    machine : str, default: "localhost"
        Target machine name for remote or batch solves.
    run_in_thread : bool, default: False
        Whether to submit the batch solve in a background thread.
    revert_to_initial_mesh : bool, default: False
        Whether to revert to the initial mesh before solving.
    analyze_all_designs : bool, default: False
        Whether to analalyze all designs. When ``True``, ``Desktop.analyze_all``
        is called for the target project/design. This
        analyzes all setups in a design or all designs in a project.

    Returns
    -------
    str
        Status message with analysis results.
    """
    desktop = ctx.request_context.lifespan_context.desktop

    if desktop is None:
        return "No AEDT connection is available. Use connect_to_aedt or launch_aedt first."

    try:
        if analyze_all_designs:
            if setup_name:
                return (
                    "`setup_name` cannot be used when `analyze_all_designs=True`. "
                    "Use design-level analysis to solve a specific setup."
                )

            logger.info(
                "Running AEDT analyze_all on project=%s design=%s",
                project_name or "active project",
                design_name or "all designs",
            )

            result = desktop.analyze_all(project=project_name, design=design_name)
            if not result:
                return "Analysis failed during AEDT-wide 'analyze_all' invocation."

            return (
                "Analysis completed successfully.\n"
                f"Project: {project_name or 'active project'}\n"
                f"Design Scope: {design_name or 'all designs'}\n"
                "Mode: desktop analyze_all\n"
                f"Result: {result}"
            )

        from ansys.aedt.core import get_pyaedt_app

        app_instance = get_pyaedt_app(
            project_name=project_name,
            design_name=design_name,
            desktop=desktop,
        )

        resolved_project_name = app_instance.project_name or project_name
        resolved_design_name = app_instance.design_name or design_name

        logger.info(
            "Running design analysis on project=%s design=%s setup=%s",
            resolved_project_name or app_instance.project_name or "active project",
            resolved_design_name or app_instance.design_name or "active design",
            setup_name or "all setups",
        )

        result = app_instance.analyze(
            setup=setup_name,
            cores=num_cores,
            tasks=num_tasks,
            gpus=num_gpus,
            acf_file=acf_file,
            use_auto_settings=use_auto_settings,
            solve_in_batch=solve_in_batch,
            machine=machine,
            run_in_thread=run_in_thread,
            revert_to_initial_mesh=revert_to_initial_mesh,
            blocking=False,
        )

        if not result:
            return (
                "Analysis failed.\n"
                f"Project: {resolved_project_name or app_instance.project_name or 'Unknown'}\n"
                f"Design: {resolved_design_name or app_instance.design_name or 'Unknown'}\n"
                f"Setup: {setup_name or 'all setups'}"
            )

        return (
            "Analysis started successfully and is running asynchronously.\n"
            f"Project: {resolved_project_name or app_instance.project_name or 'Unknown'}\n"
            f"Design: {resolved_design_name or app_instance.design_name or 'Unknown'}\n"
            f"Setup: {setup_name or 'all setups'}\n"
            f"Mode: {'batch' if solve_in_batch else 'interactive'}\n"
            f"Result: {result}\n"
            "Check the simulation status in AEDT before running dependent operations."
        )

    except Exception as e:
        error_msg = f"Error during analysis: {str(e)}"
        logger.error(error_msg)
        return error_msg


@app.tool(tags={"aedt_tools", REQUIRES_AEDT_TAG}, timeout=_TIMEOUT_LONG)
def export_results(
    ctx: Context,
    output_path: str,
    export_type: str = "touchstone",
    setup_name: str | None = None,
) -> str:
    """Export simulation results from AEDT.

    Parameters
    ----------
    ctx : Context
        MCP context containing server session and application context.
    output_path : str
        Path to export the results to.
    export_type : str, default: ``"touchstone"``
        Type of export. Options are ``"touchstone"``, ``"profile"``,
        ``"convergence"``, and ``"mesh"``.
    setup_name : str, default: None
        Setup name for the export. If ``None``, the active setup is used.

    Returns
    -------
    str
        Status message with export file path.
    """
    desktop = ctx.request_context.lifespan_context.desktop

    if desktop is None:
        return "No AEDT connection is available. Use connect_to_aedt or launch_aedt first."

    try:
        logger.info(f"Exporting {export_type} results to: {output_path}")

        try:
            from ansys.aedt.core import get_pyaedt_app

            app_instance = get_pyaedt_app(desktop=desktop)
        except Exception as resolve_error:
            logger.info("Unable to resolve active design for export: %s", resolve_error)
            return (
                "Export functionality requires an active application. "
                "Connect to a design or provide an active design context first."
            )
        if app_instance is None:
            return (
                "Export functionality requires an active application. "
                "Connect to a design or provide an active design context first."
            )

        setup_kwargs = {}
        if setup_name is not None:
            setup_kwargs["setup"] = setup_name

        if export_type == "touchstone":
            if not hasattr(app_instance, "export_touchstone"):
                return (
                    f"Touchstone export is not available for {type(app_instance).__name__} designs."
                )
            result = app_instance.export_touchstone(output_file=output_path, **setup_kwargs)
            return f"Touchstone exported to: {output_path}\nResult: {result}"

        elif export_type == "profile":
            if not hasattr(app_instance, "export_profile"):
                return f"Profile export is not available for {type(app_instance).__name__} designs."
            result = app_instance.export_profile(output_file=output_path, **setup_kwargs)
            return f"Profile exported to: {output_path}\nResult: {result}"

        elif export_type == "convergence":
            if not hasattr(app_instance, "export_convergence"):
                return (
                    "Convergence export is not available for "
                    f"{type(app_instance).__name__} designs."
                )
            result = app_instance.export_convergence(output_file=output_path, **setup_kwargs)
            return f"Convergence data exported to: {output_path}\nResult: {result}"

        elif export_type == "mesh":
            if not hasattr(app_instance, "export_mesh_stats"):
                return f"Mesh export is not available for {type(app_instance).__name__} designs."
            result = app_instance.export_mesh_stats(output_file=output_path, **setup_kwargs)
            return f"Mesh stats exported to: {output_path}\nResult: {result}"

        else:
            return (
                f"Unknown export type: {export_type}. "
                "Supported: touchstone, profile, convergence, mesh."
            )

    except Exception as e:
        error_msg = f"Error exporting results: {str(e)}"
        logger.error(error_msg)
        return error_msg


@app.tool(tags={REQUIRES_AEDT_TAG}, timeout=_TIMEOUT_MEDIUM)
def screenshot(
    ctx: Context,
    path: str = "screenshot.jpg",
    project: str | None = None,
    design: str | None = None,
    plot_type: str = "model",
    resolution: Literal["1080p", "4k"] = "1080p",
    open_viewer: bool = True,
) -> list[TextContent | ImageContent]:
    """Capture a screenshot of the current AEDT design view.

    This tool captures the current design preview as an image. It supports
    model views, field plots, and mesh visualizations, depending on what's
    currently displayed in AEDT.

    Parameters
    ----------
    ctx : Context
        MCP context containing server session and application context.
    path : str, default: ``"screenshot.jpg"``
        Output image path.
    project : str, default: None
        Project containing the design to capture. If ``None``, the active project is used.
    design : str, default: None
        Design to capture. If ``None``, the active design is used.
    plot_type : str, default: ``"model"``
        Type of screenshot. Options are ``"model"``, ``"field"``, and ``"mesh"``.
    resolution : {``"1080p"``, ``"4k"``}, default: ``"1080p"``
        Image resolution. ``"1080p"`` exports a 1920 x 1080 image, while ``"4k"``
        exports a 3840 x 2160 image.
    open_viewer : bool, default: True
        Whether to open the saved screenshot in the system image viewer.

    Returns
    -------
    list[TextContent | ImageContent]
        A list containing:

        - TextContent with the screenshot file path
        - ImageContent with the base64-encoded image data
    """
    desktop = ctx.request_context.lifespan_context.desktop

    if desktop is None:
        return [
            TextContent(
                type="text",
                text=(
                    "No AEDT connection is available. Use 'connect_to_aedt' or 'launch_aedt' first."
                ),
            )
        ]

    try:
        logger.info(f"Capturing AEDT screenshot (type: {plot_type})...")
        try:
            from ansys.aedt.core import get_pyaedt_app

            app_instance = get_pyaedt_app(
                project_name=project,
                design_name=design,
                desktop=desktop,
            )
        except Exception as resolve_error:
            return [TextContent(type="text", text=f"Cannot capture screenshot: {resolve_error}")]

        resolved_output = Path(path).expanduser().resolve()
        if resolved_output.suffix.lower() not in {".jpg", ".jpeg"}:
            resolved_output = resolved_output.with_suffix(".jpg")
        output_path = str(resolved_output)
        width, height = (3840, 2160) if resolution == "4k" else (1920, 1080)

        # Export image as JPG
        try:
            app_instance.post.export_model_picture(
                full_name=output_path,
                width=width,
                height=height,
            )
        except Exception as export_error:
            raise RuntimeError(
                f"Failed to export screenshot: {export_error}. "
                "Try saving the project first before exporting an image."
            ) from export_error

        image_path = Path(output_path)
        if not image_path.exists():
            raise RuntimeError(f"Screenshot file not created: {output_path}")

        with image_path.open("rb") as f:
            image_data = f.read()
        base64_data = base64.b64encode(image_data).decode("utf-8")
        mime_type = "image/jpeg"

        viewer_message = None
        if open_viewer:
            viewer_message = _open_file_in_default_viewer(image_path)

        logger.info(f"Screenshot captured successfully: {output_path}")

        status_lines = [
            f"Screenshot saved to '{output_path}'",
            f"Design: {app_instance.design_name}",
            f"Project: {app_instance.project_name}",
        ]
        if open_viewer:
            status_lines.append(viewer_message or "Opened screenshot in the default image viewer.")

        return [
            TextContent(
                type="text",
                text="\n".join(status_lines),
            ),
            ImageContent(type="image", data=base64_data, mimeType=mime_type),
        ]

    except Exception as e:
        error_msg = f"Error: {str(e)}"
        logger.error(error_msg)
        return [TextContent(type="text", text=error_msg)]


@app.tool(tags={"aedt_tools", REQUIRES_AEDT_TAG}, timeout=_TIMEOUT_MEDIUM)
def export_config(
    ctx: Context,
    output: str | None = None,
    project: str | None = None,
    design: str | None = None,
    overwrite: bool = False,
) -> str:
    """Export the active design configuration as a JSON file.

    Parameters
    ----------
    ctx : Context
        MCP context containing server session and application context.
    output : str, default: None
        Path to output the JSON file to. If ``None``, the configuration is exported to a
        temporary file and returned inline.
    project : str, default: None
        Project containing the design to export.
    design : str, default: None
        Design to export configuration from.
    overwrite : bool, default: False
        Whether to overwrite an existing configuration file.

    Returns
    -------
    str
        JSON string containing the exported configuration and associated
        design metadata. When ``output`` is provided, the returned JSON string also
        includes the written configuration file path.
    """
    desktop = ctx.request_context.lifespan_context.desktop

    if desktop is None:
        return "No AEDT connection is available. Use connect_to_aedt or launch_aedt first."

    temp_config_file: str | None = None

    try:
        from ansys.aedt.core import get_pyaedt_app

        app_instance = get_pyaedt_app(
            project_name=project,
            design_name=design,
            desktop=desktop,
        )

        if output:
            config_target = output if output.lower().endswith(".json") else f"{output}.json"
        else:
            fd, config_target = tempfile.mkstemp(suffix=".json")
            os.close(fd)
            Path(config_target).unlink()
            temp_config_file = config_target

        config_file = app_instance.configurations.export_config(
            config_file=config_target, overwrite=overwrite
        )
        if not config_file:
            raise RuntimeError("Failed to export configuration.")

        with Path(config_file).open("r", encoding="utf-8") as file_handle:
            config_content = json.load(file_handle)

        data: dict[str, Any] = {
            "config": config_content,
            "design": app_instance.design_name,
            "project": app_instance.project_name,
        }
        if output:
            data["config_file"] = config_file

        return json.dumps(data, indent=2)

    except Exception as e:
        error_msg = f"Error: {str(e)}"
        logger.error(error_msg)
        return error_msg
    finally:
        if temp_config_file and Path(temp_config_file).exists():
            Path(temp_config_file).unlink()


@app.tool(tags={"aedt_tools", REQUIRES_AEDT_TAG}, timeout=_TIMEOUT_MEDIUM)
def clear_aedt(ctx: Context, close_projects: bool = True) -> str:
    """Clear the AEDT state by closing all projects.

    Parameters
    ----------
    ctx : Context
        MCP context containing server session and application context.
    close_projects : bool, default: True
        Whether to close all open projects.

    Returns
    -------
    str
        Status message confirming the clear operation.
    """
    desktop = ctx.request_context.lifespan_context.desktop

    if desktop is None:
        return "No AEDT connection is available."

    try:
        logger.info("Clearing AEDT state...")

        if close_projects:
            projects = desktop.project_list
            for proj in projects:
                desktop.odesktop.CloseProject(proj)

        desktop.clear_messages()

        return f"AEDT state is cleared. Closed {len(projects) if close_projects else 0} project(s)."

    except Exception as e:
        error_msg = f"Error clearing AEDT: {str(e)}"
        logger.error(error_msg)
        return error_msg


@app.tool(tags={"aedt_tools", REQUIRES_AEDT_TAG}, timeout=_TIMEOUT_QUICK)
def get_model_info(ctx: Context, design_name: str | None = None) -> str:
    """Get information about the current model/design.

    Parameters
    ----------
    ctx : Context
        MCP context containing server session and application context.
    design_name : str, default: None
        Name of the design to get information for. If ``None``, the active design
        is used.

    Returns
    -------
    str
        JSON string containing model information.
    """
    desktop = ctx.request_context.lifespan_context.desktop

    if desktop is None:
        return "No AEDT connection is available. Use 'connect_to_aedt' or 'launch_aedt' first."

    try:
        design_type = desktop.design_type(design_name=design_name)
        project_path = desktop.project_path()

        result = {
            "design_name": design_name or "Active Design",
            "design_type": design_type,
            "project_path": project_path,
        }
        return json.dumps(result, indent=2)

    except Exception as e:
        error_msg = f"Error getting model info: {str(e)}"
        logger.error(error_msg)
        return error_msg


# Conditionally disable tools based on session configuration
# Tools tagged with "locked_connection" should be disabled when connection is locked
if session.locked_connection:
    app.disable(tags={"locked_connection"})
