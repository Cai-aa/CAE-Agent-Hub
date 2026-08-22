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

"""List of tools in PyMechanical-MCP."""

import base64
import inspect
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any

from fastmcp.server import Context
from fastmcp.server.server import get_logger

# Import Mechanical at module level to avoid import during tool execution
# The import happens during server startup, before STDIO transport is active
from ansys.mechanical import core as pymechanical  # pyright: ignore[reportMissingTypeStubs]
from ansys.mechanical.mcp import app
from ansys.mechanical.mcp.helpers import (
    _is_docker,
    _probe_grpc_endpoint,
    get_info,
    list_instances,
    resolve_transport_mode,
)
from ansys.mechanical.mcp.server import session
from mcp.types import ImageContent, TextContent

logger = get_logger(__name__)


# Tag applied to all tools that require an active Mechanical connection.
# These tools are disabled at startup (before Mechanical is connected) and enabled
# once a connection is established via connect_to_mechanical or launch_mechanical.
REQUIRES_MECHANICAL_TAG = "requires_mechanical"


async def _resolve_launch_batch_mode(ctx: Context, batch: bool | None) -> bool:
    """Resolve the Mechanical launch mode.

    When the caller omits ``batch``, try to elicit a GUI-vs-batch choice from
    the MCP client. If elicitation is unavailable or the user declines, default
    to GUI mode for interactive workflows.
    """
    if batch is not None:
        return bool(batch)

    elicit = getattr(ctx, "elicit", None)
    if elicit is None or not inspect.iscoroutinefunction(elicit):
        return False

    try:
        result = await elicit(
            (
                "Choose how to launch Mechanical. GUI mode opens a visible "
                "Mechanical window and is recommended for interactive MCP "
                "workflows. Batch mode runs in the background without a visible UI."
            ),
            {
                "gui": {"title": "GUI (recommended)"},
                "batch": {"title": "Batch / background"},
            },
            response_title="Launch mode",
            response_description="Select how the Mechanical gRPC session should be started.",
        )
    except Exception as exc:
        logger.info(
            "Launch-mode elicitation unavailable; defaulting to GUI mode: %s",
            exc,
        )
        return False

    if result.action == "accept":
        selection = str(result.data)
        return selection == "batch"

    return False


# Access type-safe lifespan context in tools
@app.tool()  # I would have expected the tag ``lifecycle`` to be added here and not only in toolset
def check_mechanical_status(ctx: Context) -> str:
    """Check the status of Mechanical initialization.

    This tool retrieves comprehensive information from the connected Mechanical
    instance including version, project directory, and connection status.

    Parameters
    ----------
    ctx : Context
        MCP context containing the server session and application context.

    Returns
    -------
    str
        JSON string containing comprehensive Mechanical status information including:

        - connection: Basic connection information (version, project_directory, is_alive)
        - product_info: Product version and build information

        Returns an error message if Mechanical is not available or has exited.
    """
    mechanical = ctx.request_context.lifespan_context.mechanical

    if mechanical is None:
        return (
            "No Mechanical connection available. "
            "Use connect_to_mechanical tool to establish a connection."
        )

    try:
        # Check if Mechanical has exited
        if hasattr(mechanical, "exited") and mechanical.exited:
            return "Mechanical instance has exited. Reconnect or launch a new instance."

        info = get_info(mechanical)

        # Return as formatted JSON
        return json.dumps(info, indent=2)

    except Exception as e:
        error_msg = f"Error checking Mechanical status: {str(e)}"
        logger.error(error_msg)
        return error_msg


@app.tool(tags={"aali"})
def check_mechanical_installed(ctx: Context) -> str:
    """Check if Mechanical is installed on the system.

    This tool checks whether Ansys Mechanical is properly installed and
    available on the system by inspecting standard installation paths.

    .. note::

       When PyMechanical-MCP runs inside a Docker container, the host
       filesystem is not accessible.  In this case, the tool probes the
       configured gRPC endpoint instead and reports whether a Mechanical
       server is reachable.

    Returns
    -------
    str
        Status message indicating whether Mechanical is installed or reachable.
    """
    logger.info("Checking if Mechanical is installed...")

    # Inside Docker we can't inspect the host filesystem, but we can probe
    # the configured gRPC endpoint to see if Mechanical is reachable.
    # NOTE: We prefer the env var over the context value because the CLI
    # ``--ip`` flag defaults to ``127.0.0.1`` which is wrong inside a
    # container (it would probe the container itself, not the host).
    if _is_docker():
        ip = os.environ.get(
            "PYMECHANICAL_IP",
            ctx.request_context.lifespan_context.mechanical_ip or "host.docker.internal",
        )
        port = int(
            os.environ.get(
                "PYMECHANICAL_PORT",
                str(ctx.request_context.lifespan_context.mechanical_port or 10000),
            )
        )
        logger.info("Running inside Docker; probing %s:%s", ip, port)
        probe = _probe_grpc_endpoint(ip, port)
        if probe["reachable"]:
            return (
                f"Running inside a Docker container: local installation "
                f"check is not available.\n"
                f"However, a Mechanical gRPC server is reachable at "
                f"{ip}:{port}.\n"
                f"Use 'connect_to_mechanical' to establish a session."
            )
        return (
            f"Running inside a Docker container: local installation "
            f"check is not available.\n"
            f"No Mechanical gRPC server detected at {ip}:{port} "
            f"(error: {probe['error']}).\n"
            f"Start Mechanical on the host machine with gRPC "
            f"enabled on port {port}, then retry."
        )

    try:
        from ansys.mechanical.core.mechanical import check_valid_mechanical

        is_installed = check_valid_mechanical()

        if is_installed:
            logger.info("Mechanical installation found")
            return "Mechanical is installed on this system."
        else:
            logger.info("Mechanical installation not found")
            return (
                "Mechanical is not installed on this system or cannot be found in the "
                "standard locations. Ensure Ansys Mechanical is properly installed "
                "and the installation path is correct."
            )

    except Exception as e:
        error_msg = f"Error checking Mechanical installation: {str(e)}"
        logger.error(error_msg)
        return error_msg


@app.tool(tags={REQUIRES_MECHANICAL_TAG})
def run_python_script(
    ctx: Context,
    script: str | None = None,
    file_path: str | None = None,
) -> str:
    """Execute a Python script inside Mechanical.

    This tool runs a Python script block inside the connected Mechanical instance
    using Mechanical's scripting API. The script has access to Mechanical's
    ``ExtAPI``, ``DataModel``, ``Model``, ``Tree``, and ``Graphics`` entry points.

    Provide either an inline ``script`` string or a ``file_path`` pointing to a
    local Python file. When ``file_path`` is given, its contents are read and
    executed inside Mechanical.

    Parameters
    ----------
    ctx : Context
        MCP context containing the server session and application context.
    script : str, optional
        The Python script to execute inside Mechanical. Required when
        ``file_path`` is not provided.
    file_path : str, optional
        Path to a local Python script file whose contents are executed inside
        Mechanical. Takes precedence over ``script`` when both are provided.

    Returns
    -------
    str
        Script execution result. Returns the string value of the last executed
        statement, or an empty string if the value cannot be returned as a string.
    """
    mechanical = ctx.request_context.lifespan_context.mechanical

    if mechanical is None:
        return (
            "No Mechanical connection available. "
            "Use connect_to_mechanical tool to establish a connection."
        )

    if file_path is not None:
        path = Path(file_path)
        if not path.exists():
            return f"Script file not found: {file_path}"
        try:
            script = path.read_text(encoding="utf-8")
        except Exception as e:
            error_msg = f"Error reading script file '{file_path}': {str(e)}"
            logger.error(error_msg)
            return error_msg

    if script is None:
        return "Provide either a 'script' string or a 'file_path' to execute."

    try:
        # Warn about f-strings: Mechanical < 2026 R1 uses IronPython 2.7 which doesn't support them
        if re.search(r'\bf["\']', script):
            logger.warning(
                "Detected f-string syntax in script. Mechanical versions before 2026 R1 "
                "use IronPython 2.7 which does not support f-strings. If execution fails, "
                "rewrite using .format() instead."
            )

        result = mechanical.run_python_script(script)
        return f"Script executed successfully. Result: {result}"
    except Exception as e:
        error_msg = f"Error executing script: {str(e)}"
        logger.error(error_msg)
        return error_msg


@app.tool(tags={"aali", "locked_connection"})
async def launch_mechanical(
    ctx: Context,
    exec_file: str | None = None,
    port: int | None = None,
    batch: bool | None = None,
    version: str | None = None,
    transport_mode: str | None = None,
) -> str:
    """Launch a new Mechanical instance.

    This tool starts a new Mechanical instance using PyMechanical's ``launch_mechanical``
    function. The launched instance will be automatically connected and stored in
    the context for subsequent operations. Once connected, additional tools become
    available to interact with it (including ``run_python_script``, ``screenshot``,
    and ``save_project``).

    Parameters
    ----------
    ctx : Context
        MCP context containing the server session and application context.
    exec_file : str, default: None
        path to the Mechanical executable. If ``None``, PyMechanical attempts
        to find the executable automatically.
    port : int, default: None
        gRPC port for Mechanical to listen on. If ``None``, ``10000`` is used.
    batch : bool | None, default: None
        Whether to launch Mechanical in batch mode. When omitted, PyMechanical-MCP
        tries to ask the client to choose between GUI and batch mode and falls back
        to GUI mode if elicitation is unavailable.
    version : str, default: None
        Mechanical version to run (such as "261" for 2026 R1). If ``None``, the
        latest installed version is used.
    transport_mode : str, default: None
        gRPC transport mode for the launched instance. Options are ``auto``,
        ``insecure``, ``mtls``, and ``wnua``. When ``None`` or ``auto``,
        PyMechanical applies the platform default.

    Returns
    -------
    str
        Launch status message with Mechanical version and connection information.
    """
    logger.info("Launching new Mechanical instance...")

    try:
        if _is_docker():
            target_port = int(os.environ.get("PYMECHANICAL_PORT", "10000"))
            return (
                "Launching Mechanical from inside a Docker container is not "
                "supported: the MCP server cannot start host processes.\n"
                f"Start Mechanical on the host machine with gRPC "
                f"enabled on port {target_port}, then use "
                f"'connect_to_mechanical' to establish a session."
            )

        # Check if there's already a connection
        if ctx.request_context.lifespan_context.mechanical is not None:
            return (
                "Already connected to a Mechanical instance. "
                "Disconnect first using disconnect_from_mechanical tool."
            )

        # Merge: tool parameter > CLI/env config > auto
        effective_mode = transport_mode
        if effective_mode is None:
            effective_mode = ctx.request_context.lifespan_context.grpc_transport_mode

        effective_certs = ctx.request_context.lifespan_context.certs_dir

        resolved_mode, resolved_certs = resolve_transport_mode(
            transport_mode=effective_mode,
            certs_dir=effective_certs,
        )

        resolved_batch = await _resolve_launch_batch_mode(ctx, batch)

        # Launch new Mechanical instance
        kwargs: dict[str, Any] = {
            "batch": resolved_batch,
            "loglevel": "INFO",
            "cleanup_on_exit": True,
            "start_timeout": 300,  # 5 minutes for graphical mode launches
        }

        if exec_file is not None:
            kwargs["exec_file"] = exec_file

        if port is not None:
            kwargs["port"] = port

        if version is not None:
            kwargs["version"] = version

        if resolved_mode is not None:
            kwargs["transport_mode"] = resolved_mode

        if resolved_certs is not None:
            kwargs["certs_dir"] = resolved_certs

        # Launch Mechanical
        mechanical = pymechanical.launch_mechanical(**kwargs)

        # Store in context for later use
        ctx.request_context.lifespan_context.mechanical = mechanical

        await ctx.enable_components(tags={REQUIRES_MECHANICAL_TAG})
        logger.info("Mechanical launched successfully!")
        return (
            f"Successfully launched Mechanical\n"
            f"Version: {mechanical.version}\n"
            f"Project Directory: {mechanical.project_directory}\n"
        )

    except Exception as e:
        error_msg = f"Failed to launch Mechanical: {str(e)}"
        logger.error(error_msg)
        return error_msg


@app.tool(tags={"aali", "locked_connection"})
async def connect_to_mechanical(
    ctx: Context,
    port: int = 10000,
    ip: str = "127.0.0.1",
    transport_mode: str | None = None,
) -> str:
    """Connect to an existing Mechanical instance.

    This tool establishes a connection to a running Mechanical instance using the
    provided port and IP address. The connection is stored for subsequent
    operations and can be closed using the ``disconnect_from_mechanical`` tool. Once
    connected, additional tools become available to interact with it
    (including ``run_python_script``, ``screenshot``, and ``save_project``).

    Parameters
    ----------
    ctx : Context
        MCP context containing the server session and application context.
    port : int, default: 10000
        gRPC port where Mechanical is listening.
    ip : str, default: "127.0.0.1"
        IP address where Mechanical is running.
    transport_mode : str, default: None
        gRPC transport mode. Options are ``"auto"``, ``"insecure"``, ``"mtls"``,
        and ``"wnua"``. When ``None`` or ``"auto"``, the mode is determined automatically.
        On Windows, it defers to PyMechanical's default ( ``"wnua"``). On Linux/Docker,
        it uses ``"mtls"`` if certificates are found. Otherwise it uses ``"insecure"``.

    Returns
    -------
    str
        Connection status message with Mechanical version information.
    """
    # When running in Docker the function parameter defaults (127.0.0.1 /
    # 10000) point at the container itself, not the host.  Prefer the
    # environment variables which are pre-configured in the Dockerfile.

    if _is_docker():
        if ip == "127.0.0.1":
            ip = os.environ.get("PYMECHANICAL_IP", ip)
        if port == 10000:
            port = int(os.environ.get("PYMECHANICAL_PORT", str(port)))

    logger.info(f"Connecting to Mechanical instance at {ip}:{port}...")

    try:
        # Check if there's already a connection
        if ctx.request_context.lifespan_context.mechanical is not None:
            return (
                "Already connected to a Mechanical instance. "
                "Disconnect first using disconnect_from_mechanical tool."
            )

        # Merge: tool parameter > CLI/env config > auto
        effective_mode = transport_mode
        if effective_mode is None:
            effective_mode = ctx.request_context.lifespan_context.grpc_transport_mode

        effective_certs = ctx.request_context.lifespan_context.certs_dir

        resolved_mode, resolved_certs = resolve_transport_mode(
            transport_mode=effective_mode,
            certs_dir=effective_certs,
        )

        logger.info(
            f"Resolved gRPC transport: mode={resolved_mode!r}, certs_dir={resolved_certs!r}"
        )

        # Build connection kwargs
        connect_kwargs: dict[str, Any] = {
            "ip": ip,
            "port": port,
            "cleanup_on_exit": False,
        }
        if resolved_mode is not None:
            connect_kwargs["transport_mode"] = resolved_mode
        if resolved_certs is not None:
            connect_kwargs["certs_dir"] = resolved_certs

        # Connect to existing Mechanical instance
        mechanical = pymechanical.connect_to_mechanical(**connect_kwargs)

        # Store in context for later use
        ctx.request_context.lifespan_context.mechanical = mechanical

        await ctx.enable_components(tags={REQUIRES_MECHANICAL_TAG})
        logger.info(f"Connected to Mechanical successfully at {ip}:{port}!")
        return (
            f"Successfully connected to Mechanical at {ip}:{port}\n"
            f"Version: {mechanical.version}\n"
            f"Transport mode: {resolved_mode or 'default'}\n"
        )

    except Exception as e:
        error_msg = f"Failed to connect to Mechanical at {ip}:{port}: {str(e)}"
        logger.error(error_msg)
        return error_msg


@app.tool(tags={"aali", "locked_connection", REQUIRES_MECHANICAL_TAG})
async def disconnect_from_mechanical(ctx: Context) -> str:
    """Disconnect from the connected Mechanical instance.

    This tool closes the connection to the Mechanical instance and releases
    the associated resources.

    Parameters
    ----------
    ctx : Context
        MCP context containing the server session and application context.

    Returns
    -------
    str
        Disconnection status message.
    """
    mechanical = ctx.request_context.lifespan_context.mechanical

    if mechanical is None:
        return "No Mechanical connection to disconnect."

    try:
        logger.info("Disconnecting from Mechanical...")

        # Exit the Mechanical connection
        mechanical.exit()

        # Clear from context
        ctx.request_context.lifespan_context.mechanical = None

        await ctx.disable_components(tags={REQUIRES_MECHANICAL_TAG})
        logger.info("Disconnected successfully!")
        return "Successfully disconnected from Mechanical"

    except Exception as e:
        error_msg = f"Error during disconnect: {str(e)}"
        logger.error(error_msg)
        # Still clear the reference even if disconnect failed
        ctx.request_context.lifespan_context.mechanical = None
        return error_msg


@app.tool()
def list_mechanical_instances() -> str:
    """List all Mechanical instances running on the local machine.

    This tool discovers Mechanical instances running on the machine by
    scanning for active gRPC servers and their associated metadata.

    .. note::

       When the MCP server runs inside a Docker container, host process
       scanning is not available.  In this case, the tool probes the
       configured gRPC endpoint and reports its reachability.

    Returns
    -------
    str
        Formatted table of Mechanical instances, or reachability status
        when running in Docker.
    """
    logger.info("Searching for Mechanical instances...")

    if _is_docker():
        # Can't scan host processes from Docker; probe the configured endpoint.
        ip = os.environ.get("PYMECHANICAL_IP", "host.docker.internal")
        port = int(os.environ.get("PYMECHANICAL_PORT", "10000"))
        probe = _probe_grpc_endpoint(ip, port)
        if probe["reachable"]:
            return (
                f"Running inside a Docker container: host process "
                f"scanning is not available.\n"
                f"Mechanical gRPC endpoint at {ip}:{port} is REACHABLE.\n"
                f"Use 'connect_to_mechanical' to establish a session."
            )
        return (
            f"Running inside a Docker container: host process "
            f"scanning is not available.\n"
            f"Mechanical gRPC endpoint at {ip}:{port} is "
            f"NOT REACHABLE (error: {probe['error']}).\n"
            f"Start Mechanical on the host machine with gRPC "
            f"enabled on port {port}, then retry."
        )

    return list_instances(long=True, instances=True)


@app.tool(tags={REQUIRES_MECHANICAL_TAG})
def list_files(ctx: Context) -> str:
    """List files in the Mechanical working directory.

    This tool lists all files in the working directory of the connected
    Mechanical instance.

    Parameters
    ----------
    ctx : Context
        MCP context containing the server session and application context.

    Returns
    -------
    str
        List of files in the working directory.
    """
    mechanical = ctx.request_context.lifespan_context.mechanical

    if mechanical is None:
        return (
            "No Mechanical connection available. "
            "Use connect_to_mechanical tool to establish a connection."
        )

    try:
        files = mechanical.list_files()
        if not files:
            return "No files found in the working directory."

        file_list = "\n".join(f"  - {f}" for f in files)
        return f"Files in working directory:\n{file_list}"
    except Exception as e:
        error_msg = f"Error listing files: {str(e)}"
        logger.error(error_msg)
        return error_msg


@app.tool(tags={REQUIRES_MECHANICAL_TAG})
def upload_file(ctx: Context, file_path: str) -> str:
    """Upload a file to the Mechanical instance.

    This tool uploads a local file to the Mechanical instance's working directory.

    Parameters
    ----------
    ctx : Context
        MCP context containing the server session and application context.
    file_path : str
        Path to the local file to upload.

    Returns
    -------
    str
        Upload status message.
    """
    mechanical = ctx.request_context.lifespan_context.mechanical

    if mechanical is None:
        return (
            "No Mechanical connection available. "
            "Use connect_to_mechanical tool to establish a connection."
        )

    if not Path(file_path).exists():
        return f"File not found: {file_path}"

    try:
        result = mechanical.upload(file_path, progress_bar=False)
        return f"Successfully uploaded file: {result}"
    except Exception as e:
        error_msg = f"Error uploading file: {str(e)}"
        logger.error(error_msg)
        return error_msg


@app.tool(tags={REQUIRES_MECHANICAL_TAG})
def download_file(ctx: Context, file_name: str, target_dir: str | None = None) -> str:
    """Download a file from the Mechanical instance.

    This tool downloads a file from the Mechanical instance's working directory
    to the local filesystem.

    Parameters
    ----------
    ctx : Context
        MCP context containing the server session and application context.
    file_name : str
        Name of the file to download from the Mechanical working directory.
    target_dir : str, optional
        Local directory to save the downloaded file. If ``None``, the current directory is used.

    Returns
    -------
    str
        Download status message with local file path.
    """
    mechanical = ctx.request_context.lifespan_context.mechanical

    if mechanical is None:
        return (
            "No Mechanical connection available. "
            "Use connect_to_mechanical tool to establish a connection."
        )

    try:
        local_paths = mechanical.download(
            file_name,
            target_dir=target_dir,
            progress_bar=False,
        )
        if local_paths:
            return f"Successfully downloaded file(s): {', '.join(local_paths)}"
        else:
            return f"No files matching '{file_name}' found to download."
    except Exception as e:
        error_msg = f"Error downloading file: {str(e)}"
        logger.error(error_msg)
        return error_msg


@app.tool(tags={REQUIRES_MECHANICAL_TAG})
def clear_mechanical(ctx: Context) -> str:
    """Clear the Mechanical database.

    This tool clears the current database in the Mechanical instance,
    providing a fresh start for a new analysis.

    Parameters
    ----------
    ctx : Context
        MCP context containing the server session and application context.

    Returns
    -------
    str
        Clear status message.
    """
    mechanical = ctx.request_context.lifespan_context.mechanical

    if mechanical is None:
        return (
            "No Mechanical connection available. "
            "Use connect_to_mechanical tool to establish a connection."
        )

    try:
        mechanical.clear()
        return "Mechanical database cleared successfully."
    except Exception as e:
        error_msg = f"Error clearing database: {str(e)}"
        logger.error(error_msg)
        return error_msg


@app.resource("files://mechanical/working_directory")
def mechanical_working_directory() -> str:
    """Return the working directory of the connected Mechanical instance.

    This resource provides the absolute path to the active project directory
    used by the connected Mechanical instance. The value is resolved lazily
    each time the resource is read.

    Returns
    -------
    str
        Absolute path to the Mechanical project directory, or a message
        indicating that Mechanical is not connected.
    """
    mechanical = getattr(getattr(app, "context", None), "mechanical", None)

    if mechanical is None:
        return "Mechanical is not connected. Use connect_to_mechanical or launch_mechanical."

    try:
        return str(mechanical.project_directory)
    except Exception as e:
        return f"Could not retrieve project directory: {e}"


@app.tool(tags={REQUIRES_MECHANICAL_TAG})
def get_model_info(ctx: Context) -> str:
    """Get information about the current model in Mechanical.

    This tool retrieves information about the current model including
    geometry, mesh, and analysis settings by executing a script inside
    Mechanical.

    Parameters
    ----------
    ctx : Context
        MCP context containing the server session and application context.

    Returns
    -------
    str
        JSON string containing model information.
    """
    mechanical = ctx.request_context.lifespan_context.mechanical

    if mechanical is None:
        return (
            "No Mechanical connection available. "
            "Use connect_to_mechanical tool to establish a connection."
        )

    try:
        # Script to gather model information
        script = """
import json

model_info = {}

# Get Project info
project = ExtAPI.DataModel.Project
model_info['project'] = {
    'product_version': project.ProductVersion,
    'name': project.Name if hasattr(project, 'Name') else 'N/A',
}

# Get Model info
model = Model
model_info['model'] = {
    'name': model.Name if hasattr(model, 'Name') else 'N/A',
}

# Get Geometry info
if hasattr(model, 'Geometry') and model.Geometry is not None:
    geom = model.Geometry
    model_info['geometry'] = {
        'body_count': geom.Children.Count if hasattr(geom, 'Children') else 0,
    }
else:
    model_info['geometry'] = {'body_count': 0}

# Get Mesh info
if hasattr(model, 'Mesh') and model.Mesh is not None:
    mesh = model.Mesh
    nodes = mesh.Nodes
    elements = mesh.Elements
    node_count = nodes.Count if hasattr(nodes, 'Count') else (
        nodes if isinstance(nodes, int) else 0
    )
    element_count = elements.Count if hasattr(elements, 'Count') else (
        elements if isinstance(elements, int) else 0
    )
    model_info['mesh'] = {
        'node_count': node_count,
        'element_count': element_count,
    }
else:
    model_info['mesh'] = {'node_count': 0, 'element_count': 0}

# Get Analysis count
if hasattr(model, 'Analyses') and model.Analyses is not None:
    model_info['analyses_count'] = model.Analyses.Count
else:
    model_info['analyses_count'] = 0

json.dumps(model_info)
"""
        result = mechanical.run_python_script(script)
        return str(result) if result else json.dumps({"error": "Could not retrieve model info"})
    except Exception as e:
        error_msg = f"Error getting model info: {str(e)}"
        logger.error(error_msg)
        return error_msg


@app.tool(tags={REQUIRES_MECHANICAL_TAG})
def screenshot(
    ctx: Context,
    view_type: str = "model",
) -> list[TextContent | ImageContent]:
    """Capture a screenshot of the current Mechanical view.

    This tool captures the current graphics view from Mechanical as an image.
    It can capture model views, mesh views, or result contour plots.

    Parameters
    ----------
    ctx : Context
        MCP context containing the server session and application context.
    view_type : str, default: ``"model"``
        Type of view to capture. Options are ``"model"``, ``"mesh"``, and ``"result"``.


    Returns
    -------
    list[TextContent | ImageContent]
        A list containing:

        - TextContent with the screenshot file path
        - ImageContent with the base64-encoded image data
    """
    mechanical = ctx.request_context.lifespan_context.mechanical

    if mechanical is None:
        return [
            TextContent(
                type="text",
                text=(
                    "No Mechanical connection available. "
                    "Use connect_to_mechanical tool to establish a connection."
                ),
            )
        ]

    try:
        logger.info(f"Capturing Mechanical screenshot (type: {view_type})...")

        # Create a temporary file with .png extension
        temp_fd, temp_path = tempfile.mkstemp(suffix=".png", prefix="mechanical_screenshot_")
        os.close(temp_fd)

        # Script to capture screenshot using Mechanical's Graphics API
        script = f"""
import os

# Get the Graphics object
graphics = ExtAPI.Graphics

# Try different export approaches for version compatibility
try:
    # Approach 1: Use GraphicsImageExportFormat enum when available.
    settings = Ansys.Mechanical.Graphics.GraphicsImageExportSettings()
    settings.Resolution = GraphicsResolutionType.EnhancedResolution
    settings.Width = 1920
    settings.Height = 1080
    graphics.ExportImage(r"{temp_path}", GraphicsImageExportFormat.PNG, settings)
except:
    # Approach 2: Simpler export (older versions)
    graphics.ExportImage(r"{temp_path}")

r"{temp_path}"
"""
        try:
            result = mechanical.run_python_script(script)
            logger.info(f"Screenshot script result: {result}")
        except Exception as e:
            logger.warning(f"Graphics export failed: {e}")
            return [TextContent(type="text", text=f"Screenshot capture failed: {str(e)}")]

        # Verify file was created
        image_path = Path(temp_path)
        if not image_path.exists():
            return [TextContent(type="text", text=f"Screenshot file not created: {temp_path}")]

        # Read image data
        with image_path.open("rb") as f:
            image_data = f.read()

        # Encode to base64
        base64_data = base64.b64encode(image_data).decode("utf-8")

        # Determine mime type
        mime_type = "image/png"

        logger.info(f"Screenshot captured successfully: {temp_path}")

        # Clean up temp file
        try:
            Path(temp_path).unlink()
        except OSError:
            pass

        # Return both text (file path) and image content
        return [
            TextContent(type="text", text="Screenshot captured successfully."),
            ImageContent(type="image", data=base64_data, mimeType=mime_type),
        ]

    except Exception as e:
        error_msg = f"Failed to capture screenshot: {str(e)}"
        logger.error(error_msg)
        return [TextContent(type="text", text=error_msg)]


####################################################################################################
# Tools that use the PersistentPythonSession


@app.tool(tags={REQUIRES_MECHANICAL_TAG})
def run_python_code(
    ctx: Context,
    code: str,
    timeout: int = 60,
) -> str:
    """Execute Python code in the persistent Python session for data processing.

    **IMPORTANT:** This tool runs in a separate Python process and does NOT have access
    to the Mechanical gRPC connection. Use this tool for:

    - Custom data processing and analysis (NumPy, Pandas, and SciPy)
    - Creating Matplotlib plots and visualizations
    - Postprocessing results exported from Mechanical
    - General Python computations

    For code that needs to run inside Mechanical (such as IronPython with ``ExtAPI`` or ``Model``),
    use the 'run_python_script' tool instead.

    Parameters
    ----------
    ctx : Context
        MCP context containing the server session and application context.
    code : str
        Python code to execute. You should use standard Python libraries.
        This tool does NOT have access to Mechanical's ``ExtAPI``, ``Model``,
        or other internal objects.
    timeout : int, default: 60
        Maximum time in seconds to allow for code execution.

    Returns
    -------
    str
        Execution result or error message. Returns JSON for structured output.
    """
    session = ctx.request_context.lifespan_context.python_session

    if session is None:
        return json.dumps(
            {
                "success": False,
                "error": (
                    "No Python session available. "
                    "The persistent Python session was not initialized."
                ),
            },
            ensure_ascii=False,
        )

    try:
        # Sanitize the input code
        sanitized_code = _sanitize_output(code)

        logger.info(f"Executing Python code in persistent session:\n{sanitized_code}")

        # Execute code in persistent session
        result = session.execute(sanitized_code, timeout=timeout)

        # Parse the result
        if isinstance(result, dict):
            stdout = _sanitize_output(result.get("stdout", ""))
            stderr = _sanitize_output(result.get("stderr", ""))

            if result.get("success"):
                return json.dumps(
                    {
                        "success": True,
                        "stdout": stdout,
                        "stderr": stderr,
                        "message": "Python code executed successfully",
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            else:
                error_msg = result.get("error", "Unknown error occurred")
                error_msg = _sanitize_output(error_msg)
                return json.dumps(
                    {
                        "success": False,
                        "stdout": stdout,
                        "stderr": stderr,
                        "error": error_msg,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
        else:
            return json.dumps(
                {
                    "success": True,
                    "stdout": _sanitize_output(str(result)) if result else "",
                    "stderr": "",
                    "message": "Python code executed successfully",
                },
                ensure_ascii=False,
                indent=2,
            )

    except TimeoutError:
        error_dict = {
            "success": False,
            "error": f"Python code execution timed out after {timeout} seconds",
        }
        logger.error(error_dict["error"])
        return json.dumps(error_dict, ensure_ascii=False)

    except Exception as e:
        error_dict = {
            "success": False,
            "error": f"Error executing Python code: {str(e)}",
        }
        logger.error(error_dict["error"])
        return json.dumps(error_dict, ensure_ascii=False)


@app.tool(tags={"aali", REQUIRES_MECHANICAL_TAG})
def create_custom_plot(
    ctx: Context,
    plot_code: str,
    plot_type: str = "matplotlib",
    timeout: int = 60,
) -> list[TextContent | ImageContent] | str:
    """Create a custom plot using Matplotlib in the persistent Python session.

    IMPORTANT: This tool runs in a separate Python process and does not have access
    to the Mechanical gRPC connection. Use this to:

    - Visualize data that was exported/saved from Mechanical.
    - Create plots from result files (such as CSV and TXT).
    - Perform postprocessing visualizations.

    For plots that need data directly from Mechanical, first use ``run_python_script``
    to export the data to a file. Then use this tool to create the visualization.

    Parameters
    ----------
    ctx : Context
        MCP context containing the server session and application context.
    plot_code : str
        Python code to create the plot. You should use ``matplotlib.pyplot``.
        For Matplotlib, the code should create the figure or plot but not call ``plt.show()``.
        Use the ``save_matplotlib_plot()`` helper function to return the plot.
    plot_type : str, default:``"matplotlib"``
        Type of plot. Options are ``"matplotlib"`` and ``"pyvista"``.
    timeout : int, default: 60
        Maximum time in seconds for plot generation.

    Returns
    -------
    list[TextContent | ImageContent]
        A list containing:

        - TextContent with the plot creation status message
        - ImageContent with the base64-encoded image data if successful

        Or, a JSON string with error details if failed.
    """
    session = ctx.request_context.lifespan_context.python_session

    if session is None:
        return [
            TextContent(
                type="text",
                text=(
                    "No Python session available. "
                    "The persistent Python session was not initialized."
                ),
            )
        ]

    try:
        logger.info(f"Creating custom {plot_type} plot in persistent session")

        # Sanitize the plot code
        sanitized_plot_code = _sanitize_output(plot_code)

        # Execute the plot code
        result = session.execute(sanitized_plot_code, timeout=timeout)

        # Parse the result
        if isinstance(result, dict):
            stdout = _sanitize_output(result.get("stdout", ""))
            stderr = _sanitize_output(result.get("stderr", ""))

            if result.get("success"):
                # Try to extract plot data from stdout
                plot_data = stdout.strip()

                # Check if the output contains a base64 data URI
                if "data:image/png;base64," in plot_data:
                    # Extract the base64 part
                    base64_data = plot_data.split("data:image/png;base64,")[1].strip()

                    return [
                        TextContent(
                            type="text",
                            text=f"Custom {plot_type} plot created successfully",
                        ),
                        ImageContent(type="image", data=base64_data, mimeType="image/png"),
                    ]
                elif plot_data.startswith("Plot saved to"):
                    return [
                        TextContent(
                            type="text",
                            text=f"Custom {plot_type} plot created successfully\n{plot_data}",
                        )
                    ]
                else:
                    return [
                        TextContent(
                            type="text",
                            text=f"Plot created but unexpected output format:\n{stdout}",
                        )
                    ]
            else:
                error_msg = result.get("error", "Unknown error occurred")
                error_msg = _sanitize_output(error_msg)
                return [
                    TextContent(
                        type="text",
                        text=(
                            f"Error creating custom {plot_type} plot: "
                            f"{error_msg}\nStdout: {stdout}\n"
                            f"Stderr: {stderr}"
                        ),
                    )
                ]
        else:
            sanitized = _sanitize_output(str(result)) if result else "No result"
            return [
                TextContent(
                    type="text",
                    text=f"Unexpected result format: {sanitized}",
                )
            ]

    except TimeoutError:
        error_msg = f"Plot creation timed out after {timeout} seconds"
        logger.error(error_msg)
        return [TextContent(type="text", text=error_msg)]

    except Exception as e:
        error_msg = f"Error creating custom plot: {str(e)}"
        logger.error(error_msg)
        return [TextContent(type="text", text=error_msg)]


####################################################################################################
# Project Management Tools


@app.tool(tags={REQUIRES_MECHANICAL_TAG})
def save_project(ctx: Context, file_path: str | None = None) -> str:
    """Save the current Mechanical project.

    This tool saves the current project to disk. If ``file_path`` is provided,
    the project is saved to that location (Save As). Otherwise, the project
    is saved in place.

    Parameters
    ----------
    ctx : Context
        MCP context containing the server session and application context.
    file_path : str, default: None
        Full path for saving the project (Save As). The path should end with
        a ``.mechdb`` extension. If ``None``, the project is savedin the current location.

    Returns
    -------
    str
        Save status message with the project file path.
    """
    mechanical = ctx.request_context.lifespan_context.mechanical

    if mechanical is None:
        return (
            "No Mechanical connection available. "
            "Use connect_to_mechanical tool to establish a connection."
        )

    try:
        if file_path is not None:
            # Validate extension
            if not file_path.lower().endswith(".mechdb"):
                file_path = file_path + ".mechdb"

            # Ensure parent directory exists
            parent = Path(file_path).parent
            if not parent.exists():
                return f"Directory does not exist: {parent}"

            # Save As: use scripting API. json.dumps() safely escapes the
            # path into a Python string literal so embedded quotes,
            # backslashes, or other special characters cannot break out of
            # the script.
            script = f"ExtAPI.DataModel.Project.SaveAs({json.dumps(file_path)})"
            mechanical.run_python_script(script)
            return f"Project saved to: {file_path}"
        else:
            # Save in place
            script = "ExtAPI.DataModel.Project.Save()"
            mechanical.run_python_script(script)
            # Get the saved path
            proj_dir = mechanical.project_directory
            return f"Project saved successfully. Project directory: {proj_dir}"

    except Exception as e:
        error_msg = f"Error saving project: {str(e)}"
        logger.error(error_msg)
        return error_msg


@app.tool(tags={REQUIRES_MECHANICAL_TAG})
def open_project(ctx: Context, file_path: str) -> str:
    """Open an existing Mechanical project file.

    This tool opens a MECHDB project file in the connected Mechanical instance.
    Any unsaved work in the current project is lost.

    Parameters
    ----------
    ctx : Context
        MCP context containing the server session and application context.
    file_path : str
        Full path to the MECHDB file to open.

    Returns
    -------
    str
        Open status message with project information.
    """
    mechanical = ctx.request_context.lifespan_context.mechanical

    if mechanical is None:
        return (
            "No Mechanical connection is available. "
            "Use connect_to_mechanical tool to establish a connection."
        )

    if not Path(file_path).exists():
        return f"Project file not found: {file_path}"

    if not file_path.lower().endswith(".mechdb"):
        return f"Invalid file type. Expected MECHDB file. Got: {file_path}"

    try:
        # json.dumps() safely escapes the path into a Python string literal so
        # embedded quotes, backslashes, or other characters cannot break out
        # of the script body.
        script = f"ExtAPI.DataModel.Project.Open({json.dumps(file_path)})"
        mechanical.run_python_script(script)

        # Get project info after opening
        info_script = """
import json
project = ExtAPI.DataModel.Project
info = {
    "name": project.Name if hasattr(project, 'Name') else 'N/A',
    "product_version": project.ProductVersion,
}
# Count bodies and analyses
model = Model
info["body_count"] = model.Geometry.GetChildren(
    DataModelObjectCategory.Body, True
).Count if hasattr(model, 'Geometry') and model.Geometry else 0
info["analyses_count"] = model.Analyses.Count if hasattr(model, 'Analyses') else 0
json.dumps(info)
"""
        result = mechanical.run_python_script(info_script)
        return f"Project opened successfully: {file_path}\nProject info: {result}"

    except Exception as e:
        error_msg = f"Error opening project: {str(e)}"
        logger.error(error_msg)
        return error_msg


@app.tool(tags={REQUIRES_MECHANICAL_TAG})
def solve_analysis(
    ctx: Context,
    analysis_index: int = 0,
    wait: bool = True,
) -> str:
    """Solve the specified analysis in Mechanical.

    This tool runs the solver for the specified analysis and returns the
    solution status. It checks for common issues and provides diagnostic
    information if the solve fails.

    Parameters
    ----------
    ctx : Context
        MCP context containing the server session and application context.
    analysis_index : int, default: 0
        Index of the analysis to solve (0-based). The default, ``0``,
        corresponds to the first analysis.
    wait : bool, default: True
        Whether to wait for the solution to complete.

    Returns
    -------
    str
        JSON string with solution status, timing, and result summary.
    """
    mechanical = ctx.request_context.lifespan_context.mechanical

    if mechanical is None:
        return (
            "No Mechanical connection is available. "
            "Use connect_to_mechanical tool to establish a connection."
        )

    try:
        script = f"""
import json
import time

# Validate analysis index
if Model.Analyses.Count == 0:
    result = json.dumps({{"success": False, "error": "No analyses are defined in the model."}})
elif {analysis_index} >= Model.Analyses.Count:
    result = json.dumps({{
        "success": False,
        "error": (
            "Analysis index {analysis_index} is out of range. "
            "Model has {{0}} analyses."
        ).format(Model.Analyses.Count)
    }})
else:
    analysis = Model.Analyses[{analysis_index}]

    # Pre-solve checks
    warnings = []
    mesh = Model.Mesh
    if mesh is None or mesh.Elements == 0:
        warnings.append("No mesh is generated. Mesh must be generated before solving.")

    # Solve (always wait - background solve not supported with local solve config)
    start_time = time.time()
    analysis.Solve(True)
    elapsed = time.time() - start_time

    # Get solution status
    solution = analysis.Solution
    status = str(solution.Status)

    # Build result
    solve_result = {{
        "success": status == "Done",
        "status": status,
        "analysis_name": analysis.Name,
        "analysis_type": str(analysis.AnalysisType),
        "elapsed_seconds": round(elapsed, 2),
        "warnings": warnings,
    }}

    # If solved successfully, get result summary
    if status == "Done":
        result_count = 0
        for i in range(solution.Children.Count):
            child = solution.Children[i]
            if hasattr(child, 'Maximum'):
                result_count += 1
        solve_result["result_objects_count"] = result_count

    result = json.dumps(solve_result)

result
"""
        result = mechanical.run_python_script(script)
        return (
            str(result)
            if result
            else json.dumps({"success": False, "error": "No response from solver"})
        )

    except Exception as e:
        error_msg = f"Error during solve: {str(e)}"
        logger.error(error_msg)
        return json.dumps({"success": False, "error": error_msg})


@app.tool(tags={REQUIRES_MECHANICAL_TAG})
def export_results(
    ctx: Context,
    result_type: str = "all",
    export_format: str = "png",
    output_dir: str | None = None,
) -> str:
    """Export results from the solved analysis.

    This tool exports result images (contour plots) and/or data from the
    current solution. It can export individual result types or all available
    results at once.

    Parameters
    ----------
    ctx : Context
        MCP context containing the server session and application context.
    result_type : str, default: ``"all"``
        Type of result to export. Options are ``"all"``, ``"deformation"``, ``"stress"``,
         ``"strain"``, or a specific result object name.
    export_format : str, default: ``"png"``
        Export format. Use ``"png"`` for images, ``"txt"`` for text data, or ``"both"`` for
        images and text.
    output_dir : str, default: None
        Directory to save exported files. If ``None``, uses the project directory.

    Returns
    -------
    str
        JSON string with export status and file paths.
    """
    mechanical = ctx.request_context.lifespan_context.mechanical

    if mechanical is None:
        return (
            "No Mechanical connection available. "
            "Use connect_to_mechanical tool to establish a connection."
        )

    try:
        # Determine output directory
        if output_dir is None:
            output_dir = mechanical.project_directory

        # Strip trailing backslash to avoid breaking raw string literals
        output_dir = output_dir.rstrip("\\")

        if not Path(output_dir).exists():
            Path(output_dir).mkdir(parents=True, exist_ok=True)

        script = f"""
import json
import os

output_dir = {json.dumps(output_dir)}
result_type = {json.dumps(result_type)}
export_format = {json.dumps(export_format)}

solution = Model.Analyses[0].Solution if Model.Analyses.Count > 0 else None

if solution is None:
    result = json.dumps({{"success": False, "error": "No analysis found in the model"}})
elif str(solution.Status) != "Done":
    result = json.dumps({{
        "success": False,
        "error": "Solution has not been completed. Status: {{0}}".format(solution.Status)
    }})
else:
    exported_files = []
    errors = []

    # Evaluate all results first
    try:
        solution.EvaluateAllResults()
    except:
        pass

    # Iterate through result objects
    for i in range(solution.Children.Count):
        child = solution.Children[i]

        # Check if this is a result object (has Maximum property)
        if not hasattr(child, 'Maximum'):
            continue

        # Filter by result_type
        child_name = child.Name
        if result_type != "all":
            if result_type.lower() == "deformation" and "Deformation" not in child_name:
                continue
            elif result_type.lower() == "stress" and "Stress" not in child_name:
                continue
            elif result_type.lower() == "strain" and "Strain" not in child_name:
                continue
            elif result_type.lower() not in ["all", "deformation", "stress", "strain"]:
                if result_type.lower() not in child_name.lower():
                    continue

        # Activate the result for export
        child.Activate()

        safe_name = child_name.replace(" ", "_").replace("/", "_")

        # Export image
        if export_format in ("png", "both"):
            try:
                img_path = os.path.join(output_dir, safe_name + ".png")
                Graphics.ExportImage(img_path, GraphicsImageExportFormat.PNG)
                exported_files.append(img_path)
            except Exception as e:
                errors.append("Image export failed for {{0}}: {{1}}".format(child_name, str(e)))

        # Export text data
        if export_format in ("txt", "both"):
            try:
                txt_path = os.path.join(output_dir, safe_name + ".txt")
                child.ExportToTextFile(txt_path)
                exported_files.append(txt_path)
            except Exception as e:
                errors.append("Text export failed for {{0}}: {{1}}".format(child_name, str(e)))

    result = json.dumps({{
        "success": len(exported_files) > 0,
        "exported_files": exported_files,
        "file_count": len(exported_files),
        "errors": errors,
        "output_directory": output_dir,
    }})

result
"""
        result = mechanical.run_python_script(script)
        return str(result) if result else json.dumps({"success": False, "error": "No response"})

    except Exception as e:
        error_msg = f"Error exporting results: {str(e)}"
        logger.error(error_msg)
        return json.dumps({"success": False, "error": error_msg})


####################################################################################################
# Internal helpers


def _sanitize_output(text: str) -> str:
    """Sanitize output text to handle encoding issues.

    This function removes or replaces problematic Unicode characters that can cause
    encoding issues on Windows systems with limited character sets.

    Parameters
    ----------
    text : str
        The text to sanitize.

    Returns
    -------
    str
        The sanitized text with problematic characters removed or replaced.
    """
    if not isinstance(text, str):
        return text

    # Replace common problematic Unicode characters with ASCII alternatives
    replacements = {
        # Checkmarks and crosses
        "\u2713": "[OK]",  # checkmark
        "\u2717": "[X]",  # cross
        # Box drawing characters
        "\u2514": "\\",  # box drawing
        "\u2502": "|",  # box drawing
        "\u2500": "-",  # box drawing
        "\u2510": "\\",  # box drawing
        "\u250c": "/",  # box drawing
        "\u2518": "/",  # box drawing
        # Block elements
        "\u2588": "#",  # block
        "\u2589": "#",  # block
        "\u258a": "#",  # block
        "\u258c": "|",  # block
        "\u2590": "|",  # block
        # Superscript and subscript characters
        "\u00b9": "^1",  # superscript 1
        "\u00b2": "^2",  # superscript 2
        "\u00b3": "^3",  # superscript 3
        "\u2074": "^4",  # superscript 4
        "\u2075": "^5",  # superscript 5
        "\u2076": "^6",  # superscript 6
        "\u2077": "^7",  # superscript 7
        "\u2078": "^8",  # superscript 8
        "\u2079": "^9",  # superscript 9
        "\u2070": "^0",  # superscript 0
        # Other commonly problematic characters
        "\u2022": "*",  # bullet
        "\u2023": "*",  # triangular bullet
        "\u2219": "*",  # bullet operator
        "\u00a0": " ",  # non-breaking space
        "\u200b": "",  # zero-width space
        "\u200c": "",  # zero-width non-joiner
        "\u200d": "",  # zero-width joiner
        "\ufeff": "",  # zero-width no-break space
    }

    for unicode_char, replacement in replacements.items():
        text = text.replace(unicode_char, replacement)

    # Remove any remaining characters that can't be encoded in ascii
    try:
        text.encode("ascii")
    except UnicodeEncodeError:
        text = text.encode("ascii", errors="replace").decode("ascii")

    return text


@app.tool(tags={REQUIRES_MECHANICAL_TAG})
def get_mechanical_logs(
    ctx: Context,
    source: str = "messages",
    tail_lines: int = 200,
    contains: str | None = None,
    max_chars: int = 40000,
) -> str:
    """Return recent log entries from the connected Mechanical instance.

    This tool provides visibility into Mechanical session activity by reading
    either the application message list or solver output log file.

    Parameters
    ----------
    ctx : Context
        MCP context containing the server session and application context.
    source : str, optional
        Log source to read. Options are:

        - ``"messages"`` (default): Application messages (errors, warnings,
          info) from ``ExtAPI.Application.Messages``.
        - ``"solve_log"``: Raw solver transcript from ``solve.out`` in the
          project directory.

    tail_lines : int, default: 200
        Number of most recent lines to return.
    contains : str, optional
        Case-insensitive substring filter applied to each line.
    max_chars : int, default: 40000
        Maximum character count for the returned log text.

    Returns
    -------
    str
        JSON string with log metadata and selected log text.
    """
    mechanical = ctx.request_context.lifespan_context.mechanical

    if mechanical is None:
        return (
            "No Mechanical connection is available. "
            "Use connect_to_mechanical tool to establish a connection."
        )

    if tail_lines <= 0:
        return "Invalid parameter: tail_lines must be greater than 0."
    if max_chars <= 0:
        return "Invalid parameter: max_chars must be greater than 0."

    safe_tail_lines = min(tail_lines, 5000)
    safe_max_chars = min(max_chars, 200000)

    try:
        if source == "messages":
            return _get_mechanical_messages(mechanical, safe_tail_lines, contains, safe_max_chars)
        elif source == "solve_log":
            return _get_mechanical_solve_log(mechanical, safe_tail_lines, contains, safe_max_chars)
        else:
            return json.dumps(
                {
                    "error": (
                        f"Unknown source: {source!r}. Accepted values: 'messages', 'solve_log'."
                    )
                }
            )
    except Exception as e:
        error_msg = f"Error reading Mechanical logs: {str(e)}"
        logger.error(error_msg)
        return json.dumps({"error": error_msg})


def _get_mechanical_messages(
    mechanical: Any,
    tail_lines: int,
    contains: str | None,
    max_chars: int,
) -> str:
    """Read application messages from Mechanical via ExtAPI."""
    script = """
import json
msgs = ExtAPI.Application.Messages
entries = []
for i in range(msgs.Count):
    m = msgs[i]
    entries.append({
        "severity": str(m.Severity),
        "source": str(m.Source) if hasattr(m, 'Source') else "",
        "summary": str(m.Summary) if hasattr(m, 'Summary') else str(m),
    })
json.dumps(entries)
"""
    raw = mechanical.run_python_script(script)

    try:
        entries = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        # Fallback: treat raw output as line-delimited text
        entries = None

    if entries is not None:
        lines = [
            f"[{e.get('severity', '?')}] {e.get('source', '')}: {e.get('summary', '')}"
            for e in entries
        ]
    else:
        lines = (raw or "").splitlines()

    # Filter
    if contains:
        token = contains.lower()
        lines = [ln for ln in lines if token in ln.lower()]

    total = len(lines)
    selected = lines[-tail_lines:]
    text = "\n".join(selected)

    truncated = False
    if len(text) > max_chars:
        text = text[-max_chars:]
        truncated = True

    return json.dumps(
        {
            "source": "messages",
            "total_messages": total,
            "returned_lines": len(selected),
            "tail_lines_requested": tail_lines,
            "contains": contains,
            "truncated": truncated,
            "logs": text,
        },
        indent=2,
    )


def _get_mechanical_solve_log(
    mechanical: Any,
    tail_lines: int,
    contains: str | None,
    max_chars: int,
) -> str:
    """Read the solve.out log file from the Mechanical project directory."""
    project_dir = str(mechanical.project_directory)
    solve_log = Path(project_dir) / "solve.out"

    if not solve_log.exists():
        # Try looking one level up or in common locations
        candidates = list(Path(project_dir).rglob("solve.out"))
        if candidates:
            solve_log = candidates[0]
        else:
            return json.dumps(
                {
                    "source": "solve_log",
                    "error": (
                        f"solve.out not found in {project_dir}. "
                        "Run a solve first to generate solver output."
                    ),
                }
            )

    with solve_log.open("r", encoding="utf-8", errors="replace") as f:
        all_lines = f.readlines()

    filtered = all_lines
    if contains:
        token = contains.lower()
        filtered = [ln for ln in all_lines if token in ln.lower()]

    total = len(all_lines)
    matched = len(filtered)
    selected = filtered[-tail_lines:]
    text = "".join(selected)

    truncated = False
    if len(text) > max_chars:
        text = text[-max_chars:]
        truncated = True

    return json.dumps(
        {
            "source": "solve_log",
            "log_file": str(solve_log),
            "total_lines": total,
            "matched_lines": matched,
            "returned_lines": len(selected),
            "tail_lines_requested": tail_lines,
            "contains": contains,
            "truncated": truncated,
            "logs": text,
        },
        indent=2,
    )


# Conditionally disable tools based on session configuration
if session.on_aali:
    app.disable(tags={"aali"})

if session.locked_connection:
    app.disable(tags={"locked_connection"})
