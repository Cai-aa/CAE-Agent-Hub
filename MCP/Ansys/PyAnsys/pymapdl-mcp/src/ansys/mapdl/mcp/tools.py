# Copyright (C) 2025 - 2026 ANSYS, Inc. and/or its affiliates.
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

"""List of tools in PyMAPDL-MCP.

This module defines all MCP tools available in the PyMAPDL MCP server, organized into logical
tool sets for better organization and accessibility.

Tool sets
---------
Tools are grouped into the following tool sets via the ``toolsets://definition`` resource:

- **session_management**: Tools for managing MAPDL connections and instance discovery
- **file_management**: Tools for transferring files to/from MAPDL and managing saved models
- **command_execution**: Tools for executing MAPDL commands and scripts
- **visualization**: Tools for visualization and post-processing results
- **python_execution**: Tools for executing arbitrary Python and PyMAPDL code

The :func:`list_tool_sets` function exposes these tool set definitions as a resource.
"""

import base64
import json
import os
from pathlib import Path
import platform
import subprocess  # nosec B404
import tempfile
from typing import Any, cast

from ansys.common.mcp.tools import create_custom_plot, execute_python_code
from fastmcp.server import Context
from fastmcp.tools.base import ToolResult

# Import MAPDL at module level to avoid import during tool execution
# The import happens during server startup, before STDIO transport is active
from ansys.mapdl.mcp import app
from ansys.mapdl.mcp.helpers import connect_to_mapdl_in_persistent_python, logger
from mcp.types import ImageContent, TextContent

try:
    import pyvista  # noqa: F401  # Check if PyVista is available

    pyvista.OFF_SCREEN = True  # Set off-screen rendering globally for all tools

except ImportError:
    pass


def _text_result(text: str) -> ToolResult:
    """Wrap a plain text string in a single-content ToolResult."""
    return ToolResult([TextContent(type="text", text=text)])


def _open_image_in_viewer(image_path: str | Path) -> None:
    """Open an image file in the system's default image viewer.

    Parameters
    ----------
    image_path : str or Path
        Path to the image file to open.
    """
    try:
        system = platform.system()
        if system == "Darwin":
            subprocess.Popen(["open", str(image_path)])  # noqa: S603, S607  # nosec B603, B607
        elif system == "Windows":
            os.startfile(str(image_path))  # type: ignore[attr-defined]  # noqa: PTH123  # nosec B606
        else:
            subprocess.Popen(["xdg-open", str(image_path)])  # noqa: S603, S607  # nosec B603, B607
    except Exception as e:
        logger.warning(f"Failed to open image in viewer: {e}")


def _is_mapdl_crashed(mapdl: Any) -> bool:
    """Return True if the cached MAPDL instance has crashed or exited."""
    if hasattr(mapdl, "_exited") and mapdl._exited is True:
        return True
    if hasattr(mapdl, "_exiting") and mapdl._exiting is True:
        return True
    return False


def _get_mapdl(ctx: Context) -> tuple[Any, str | None]:
    """Retrieve the active MAPDL instance from context, running all guards.

    Returns ``(mapdl, None)`` on success, or ``(None, error_message)`` when any
    guard fails (missing context, no MAPDL connection, crashed instance).

    Parameters
    ----------
    ctx : Context
        The MCP request context.

    Returns
    -------
    tuple[Any, str | None]
        A 2-tuple of ``(mapdl_instance, error_text)``.  Exactly one of the two
        values is ``None`` at any given time.
    """
    if ctx.request_context is None:
        return None, "No request context available."

    mapdl = ctx.request_context.lifespan_context.mapdl

    if mapdl is None:
        return None, (
            "No MAPDL connection available. Use connect_to_mapdl tool to establish a connection."
        )

    if _is_mapdl_crashed(mapdl):
        return None, (
            "MAPDL instance has exited or is exiting. "
            "Please reconnect or launch a new instance using launch_mapdl_session."
        )

    return mapdl, None


def _four_view_commands(plot_command: str | list[str] = "EPLOT") -> str:
    """Return MAPDL commands string that sets up a 2x2 window composite view.

    Windows
    -------
    - Upper-left  (1) : Top view, looking from +Z
    - Upper-right (2) : Right-side view, looking from +X
    - Lower-left  (3) : Front view, looking from +Y
    - Lower-right (4) : Isometric view (1, 1, 1)

    The *plot_command* is appended so that MAPDL distributes the plot across
    all active windows in a single call.
    """
    if isinstance(plot_command, list):
        plot_command = "\n".join(plot_command)

    return (
        "/WINDOW,1,LTOP\n"
        "/WINDOW,2,RTOP\n"
        "/WINDOW,3,LBOT\n"
        "/WINDOW,4,RBOT\n"
        "/VIEW,1,0,0,1\n"
        "/VIEW,2,1,0,0\n"
        "/VIEW,3,0,1,0\n"
        "/VIEW,4,1,1,1\n"
        "/TRIAD,OFF\n"
        f"{plot_command}\n"
    )


_RESTORE_SINGLE_WINDOW = (
    "/WINDOW,1,FULL\n/WINDOW,2,OFF\n/WINDOW,3,OFF\n/WINDOW,4,OFF\n/TRIAD,ORIG\n"
)


def _capture_screenshot(
    mapdl: Any,
    pre_commands: str = "",
    prefix: str = "mapdl_screenshot_",
) -> tuple[Path, bytes, str]:
    """Run optional *pre_commands* then capture a MAPDL screenshot.

    Parameters
    ----------
    mapdl : :class:`~ansys.mapdl.core.Mapdl`
        Connected MAPDL instance.
    pre_commands : str, optional
        MAPDL command string to execute before taking the screenshot.
    prefix : str, optional
        Prefix for the temporary file name.

    Returns
    -------
    tuple[Path, bytes, str]
        *(screenshot_path, image_bytes, mime_type)*

    Raises
    ------
    FileNotFoundError
        If the screenshot file was not created by MAPDL.
    """
    temp_fd, temp_path = tempfile.mkstemp(suffix=".png", prefix=prefix)
    os.close(temp_fd)

    if pre_commands:
        mapdl.input_strings(pre_commands)  # type: ignore[union-attr]

    # Ignoring PTH123 since the file is created by MAPDL
    screenshot_path = mapdl.screenshot(savefig=temp_path)  # type: ignore[union-attr]

    raw_path = screenshot_path if screenshot_path else temp_path
    image_path = Path(raw_path)
    if not image_path.exists():
        raise FileNotFoundError(f"Screenshot file not found: {raw_path}")

    mime_type = "image/png"
    if image_path.suffix.lower() in (".jpg", ".jpeg"):
        mime_type = "image/jpeg"
    elif image_path.suffix.lower() == ".bmp":
        mime_type = "image/bmp"
    elif image_path.suffix.lower() == ".gif":
        mime_type = "image/gif"

    with open(image_path, "rb") as f:  # noqa: PTH123
        image_data = f.read()

    return image_path, image_data, mime_type


# Tag applied to all tools that require an active MAPDL connection.
# These tools are disabled at startup (before MAPDL is connected) and enabled
# once a connection is established via connect_to_mapdl or launch_mapdl_session.
REQUIRES_MAPDL_TAG = "requires_mapdl"


# Access type-safe lifespan context in tools
@app.tool(tags={REQUIRES_MAPDL_TAG, "session_management"})
def check_mapdl_status(ctx: Context) -> ToolResult:
    """Check the status of MAPDL initialization.

    This tool extracts comprehensive information from PyMAPDL's API and returns it
    as a structured JSON object. It also checks whether the MAPDL instance has
    exited or is exiting.

    Parameters
    ----------
    ctx : Context
        The MCP context containing server session and application context.

    Returns
    -------
    ToolResult
        JSON string containing comprehensive MAPDL status information including:
        - connection: Basic connection info (version, port, ip, directory, is_alive)
        - information: Data from Information class (title, jobname, routine, units, etc.)
        - geometry: Geometry statistics (number of keypoints, lines, areas, volumes)
        - post_processing: Post-processing availability and result sets
        - mesh: Mesh statistics (number of nodes and elements)

        Returns an error message if MAPDL is not available or has exited.
    """
    mapdl, error = _get_mapdl(ctx)
    if error:
        return _text_result(error)

    try:
        from ansys.mapdl.mcp.helpers import get_info

        # Check if MAPDL has exited
        if hasattr(mapdl, "_exited") and mapdl._exited:
            return _text_result(
                "MAPDL instance has exited. Please reconnect or launch a new instance."
            )

        if hasattr(mapdl, "_exiting") and mapdl._exiting:
            return _text_result(
                "MAPDL instance is currently exiting. Please wait or launch a new instance."
            )

        info = get_info(mapdl)
        json_content = TextContent(type="text", text=json.dumps(info, indent=2))

        # Attempt to attach a four-view screenshot of the current selection
        try:
            logger.info("Capturing four-view screenshot for status report...")
            _, image_data, mime_type = _capture_screenshot(
                mapdl,
                pre_commands=_four_view_commands("EPLOT"),
                prefix="mapdl_status_",
            )
            base64_data = base64.b64encode(image_data).decode("utf-8")
            return ToolResult(
                [json_content, ImageContent(type="image", data=base64_data, mimeType=mime_type)]
            )
        except Exception as img_err:
            logger.warning(f"Could not capture four-view screenshot for status: {img_err}")
            return ToolResult([json_content])
        finally:
            try:
                mapdl.input_strings(_RESTORE_SINGLE_WINDOW)  # type: ignore[union-attr]
            except Exception as restore_err:
                logger.warning(f"Could not restore single-window layout: {restore_err}")

    except Exception as e:
        error_msg = f"Error checking MAPDL status: {str(e)}"
        logger.error(error_msg)
        return _text_result(error_msg)


@app.tool(tags={"aali", "session_management"})
def check_mapdl_installed(ctx: Context) -> ToolResult:
    """Check if MAPDL is installed on the system.

    This tool lists all ANSYS/MAPDL installations found on the system,
    including their version numbers and executable paths.

    Returns
    -------
    ToolResult
        Status message listing all found MAPDL installations, or a message
        indicating that no installation was found.
    """
    logger.info("Checking if MAPDL is installed...")

    try:
        from ansys.tools.common.path import (
            get_available_ansys_installations,
        )

        installations = get_available_ansys_installations()

        if not installations:
            logger.info("MAPDL installation not found")
            return _text_result(
                "MAPDL is not installed on this system or cannot be found in the "
                "standard locations. Please ensure ANSYS/MAPDL is properly installed "
                "and the installation path is correct."
            )

        lines = [f"MAPDL is installed on this system. Found {len(installations)} installation(s):"]
        for version_int, base_path in installations.items():
            is_student = version_int < 0
            abs_version = abs(version_int)
            ansys_bin_path = Path(base_path) / "ansys" / "bin"
            if os.name == "nt":
                ansys_bin = ansys_bin_path / "winx64" / f"ansys{abs_version}.exe"
            else:
                ansys_bin = ansys_bin_path / f"ansys{abs_version}"
            student_label = " (Student)" if is_student else ""
            lines.append(f"  - Version {abs_version}{student_label}: {ansys_bin}")

        logger.info(f"Found {len(installations)} MAPDL installation(s)")
        return _text_result("\n".join(lines))

    except Exception as e:
        error_msg = f"Error checking MAPDL installation: {str(e)}"
        logger.error(error_msg)
        return _text_result(error_msg)


@app.tool(tags={REQUIRES_MAPDL_TAG, "command_execution"})
def run_mapdl_command(ctx: Context, cmd: str, comment: str = "", header: str = "") -> ToolResult:
    """Execute an arbitrary MAPDL command.

    Parameters
    ----------
    ctx : Context
        The MCP context containing server session and application context.
    cmd : str
        The MAPDL command to execute.
    comment : str, optional
        An optional comment to include before the command execution. Default is empty string.
    header : str, optional
        An optional header to include before the command execution. Default is empty string.

    Returns
    -------
    ToolResult
        Command execution result.
    """
    mapdl, error = _get_mapdl(ctx)
    if error:
        return _text_result(error)

    if header:
        mapdl.com(f"# {header}", mute=True)
    if comment:
        for each_line in comment.splitlines():
            mapdl.com(f"{each_line}", mute=True)

    result = mapdl.run(cmd)
    return _text_result(f"MAPDL command executed successfully: {result}")


@app.tool(tags={"aali", REQUIRES_MAPDL_TAG, "command_execution"})
def run_multiple_mapdl_commands(
    ctx: Context, commands: list[str], comment: str = "", header: str = ""
) -> ToolResult:
    """Execute multiple MAPDL commands in sequence.

    This tool is optimized for running multiple commands efficiently by using
    MAPDL's :meth:`~ansys.mapdl.core.Mapdl.input_strings` method, which processes
    commands in batch mode.
    This is significantly faster than executing commands one by one.

    Parameters
    ----------
    ctx : Context
        The MCP context containing server session and application context.
    commands : list[str]
        List of MAPDL commands to execute in sequence.
    comment : str, optional
        An optional comment to include before the command execution. Default is empty string.
    header : str, optional
        An optional header to include before the command execution. Default is empty string.

    Returns
    -------
    ToolResult
        Execution result with summary of commands executed.
    """
    mapdl, error = _get_mapdl(ctx)
    if error:
        return _text_result(error)

    if not commands:
        return _text_result("No commands provided. Please provide a list of commands to execute.")

    if not isinstance(commands, list):
        return _text_result("Commands must be provided as a list of strings.")

    # Filter out empty commands
    valid_commands = [cmd.strip() for cmd in commands if cmd and cmd.strip()]

    if not valid_commands:
        return _text_result("No valid commands found after filtering empty entries.")

    try:
        logger.info(f"Executing {len(valid_commands)} MAPDL commands using input_strings")

        if header:
            mapdl.com(f"# {header}", mute=True)
        if comment:
            for each_line in comment.splitlines():
                mapdl.com(f"{each_line}", mute=True)

        # Use input_strings for batch command execution
        result = mapdl.input_strings(valid_commands)

        success_msg = (
            f"Successfully executed {len(valid_commands)} MAPDL commands:\n"
            f"Commands:\n" + "\n".join(f"  {i + 1}. {cmd}" for i, cmd in enumerate(valid_commands))
        )

        if result:
            success_msg += f"\n\nOutput:\n{result}"

        return ToolResult(
            [
                TextContent(type="text", text="True"),
                TextContent(type="text", text=success_msg),
            ],
            structured_content={
                "success": True,
                "commands_executed": valid_commands,
                "output": result or "",
            },
        )

    except Exception as e:
        error_msg = (
            f"Error executing commands. Executed {len(valid_commands)} commands "
            f"but encountered error: {str(e)}\n"
            f"Commands that were attempted:\n"
            + "\n".join(f"  {i + 1}. {cmd}" for i, cmd in enumerate(valid_commands))
        )
        logger.error(error_msg)
        return ToolResult([TextContent(type="text", text=error_msg)])


@app.tool(tags={"aali", "locked_connection", "session_management"})
async def launch_mapdl_session(
    ctx: Context,
    exec_file: str | None = None,
    port: int | None = None,
    run_location: str | None = None,
    nproc: int | None = None,
    additional_switches: str = "",
) -> ToolResult:
    """Launch a new MAPDL instance.

    This tool starts a new MAPDL instance using PyMAPDL's
    :func:`~ansys.mapdl.core.launcher.launch_mapdl` function.
    The launched instance will be automatically connected and stored in the context
    for subsequent operations. The instance can be closed using the
    :func:`disconnect_from_mapdl` tool.
    Once you are connected to the launched instance, other tools become available
    to interact with it, such as :func:`run_mapdl_command`,
    :func:`check_mapdl_status`, :func:`screenshot`, and more.

    Parameters
    ----------
    ctx : Context
        The MCP context containing server session and application context.
    exec_file : str, optional
        The path to the MAPDL executable. If None, PyMAPDL will attempt to find
        the MAPDL executable automatically.
    port : int, optional
        The gRPC port for MAPDL to listen on. If None, a default port will be used.
    run_location : str, optional
        The directory where MAPDL will run and store files. If None, a temporary
        directory will be created.
    nproc : int | None, optional
        Number of processors to use. Default is None. MAPDL will decide based on
        available resources.
    additional_switches : str, optional
        Additional command line switches to pass to MAPDL. Default is empty string.

    Returns
    -------
    ToolResult
        Launch status message with MAPDL version and connection information.
    """
    logger.info("Launching new MAPDL instance...")

    if ctx.request_context is None:
        return _text_result("No request context available.")
    try:
        # Check if there's already a connection
        if ctx.request_context.lifespan_context.mapdl is not None:
            if _is_mapdl_crashed(ctx.request_context.lifespan_context.mapdl):
                logger.warning(
                    "Cached MAPDL instance has crashed or exited. Clearing the cached instance."
                )
                ctx.request_context.lifespan_context.mapdl = None
            else:
                return _text_result(
                    f"Already connected to MAPDL at "
                    f"{ctx.request_context.lifespan_context.mapdl._ip}:"
                    f"{ctx.request_context.lifespan_context.mapdl._port}. "
                    f"Please disconnect first using disconnect_from_mapdl tool."
                )

        # Launch new MAPDL instance
        kwargs: dict[str, Any] = {
            "nproc": nproc,
            "loglevel": "INFO",
            "port": port,
        }

        if exec_file is not None:
            kwargs["exec_file"] = exec_file

        if run_location is not None:
            kwargs["run_location"] = run_location

        if additional_switches:
            kwargs["additional_switches"] = additional_switches

        from ansys.mapdl import core as pymapdl  # pyright: ignore[reportMissingTypeStubs]

        mapdl = cast(pymapdl.Mapdl, pymapdl.launch_mapdl(**kwargs))

        # Store in context for later use
        ctx.request_context.lifespan_context.mapdl = mapdl

        await ctx.enable_components(tags={REQUIRES_MAPDL_TAG})
        logger.info(f"MAPDL launched successfully at {mapdl.ip}:{mapdl.port}!")
        return _text_result(
            f"Successfully launched MAPDL at {mapdl.ip}:{mapdl.port}\n"
            f"MAPDL Version: {mapdl.version}\n"
            f"Working Directory: {mapdl.directory}\n"
        )

    except Exception as e:
        error_msg = f"Failed to launch MAPDL: {str(e)}"
        logger.error(error_msg)
        return _text_result(error_msg)


@app.tool(tags={"aali", "locked_connection", "session_management"})
async def connect_to_mapdl(ctx: Context, port: int = 50052, ip: str = "localhost") -> ToolResult:
    """Connect to an existing MAPDL instance.

    This tool establishes a connection to a running MAPDL instance using the
    provided port and IP address. The connection is stored for subsequent
    operations and can be closed using the :func:`disconnect_from_mapdl` tool.
    Once you are connected to the MAPDL instance, other tools become available
    to interact with it, such as :func:`run_mapdl_command`,
    :func:`check_mapdl_status`, :func:`screenshot`, and more.

    Parameters
    ----------
    ctx : Context
        The MCP context containing server session and application context.
    port : int, optional
        The gRPC port where MAPDL is listening. Default is 50052.
    ip : str, optional
        The IP address where MAPDL is running. Default is "localhost".

    Returns
    -------
    ToolResult
        Connection status message with MAPDL version information.
    """
    logger.info(f"Connecting to MAPDL instance at {ip}:{port}...")

    if ctx.request_context is None:
        return _text_result("No request context available.")
    try:
        # Check if there's already a connection
        if ctx.request_context.lifespan_context.mapdl is not None:
            if _is_mapdl_crashed(ctx.request_context.lifespan_context.mapdl):
                logger.warning(
                    "Cached MAPDL instance has crashed or exited. Clearing the cached instance."
                )
                ctx.request_context.lifespan_context.mapdl = None
            else:
                return _text_result(
                    f"Already connected to MAPDL at "
                    f"{ctx.request_context.lifespan_context.mapdl._ip}:"
                    f"{ctx.request_context.lifespan_context.mapdl._port}. "
                    f"Please disconnect first using disconnect_from_mapdl tool."
                )

        # Connect to existing MAPDL instance
        _connect_kwargs: dict[str, Any] = {
            "start_instance": False,
            "ip": ip,
            "port": port,
            "cleanup_on_exit": False,  # Don't clean up since we didn't launch it
            "loglevel": "INFO",
        }

        from ansys.mapdl import core as pymapdl  # pyright: ignore[reportMissingTypeStubs]

        mapdl = pymapdl.Mapdl(**_connect_kwargs)

        # Store in context for later use
        ctx.request_context.lifespan_context.mapdl = mapdl

        await ctx.enable_components(tags={REQUIRES_MAPDL_TAG})
        logger.info(f"Connected to MAPDL successfully at {ip}:{port}!")
        return _text_result(
            f"Successfully connected to MAPDL at {ip}:{port}\nMAPDL Version: {mapdl.version}\n"
        )

    except Exception as e:
        error_msg = f"Failed to connect to MAPDL at {ip}:{port}: {str(e)}"
        logger.error(error_msg)
        return _text_result(error_msg)


@app.tool(tags={"aali", "locked_connection", REQUIRES_MAPDL_TAG, "session_management"})
async def disconnect_from_mapdl(ctx: Context) -> ToolResult:
    """Disconnect from the dynamically connected MAPDL instance.

    This tool closes the connection to the MAPDL instance that was established
    using the :func:`connect_to_mapdl` tool and releases the associated
    resources.

    Parameters
    ----------
    ctx : Context
        The MCP context containing server session and application context.

    Returns
    -------
    ToolResult
        Disconnection status message.
    """
    if ctx.request_context is None:
        return _text_result("No request context available.")
    mapdl = ctx.request_context.lifespan_context.mapdl

    if mapdl is None:
        return _text_result("No MAPDL connection to disconnect.")

    try:
        ip = mapdl._ip
        port = mapdl._port
        logger.info(f"Disconnecting from MAPDL at {ip}:{port}...")

        # Exit the MAPDL connection
        # Just disconnect the client
        mapdl.exit()
        del mapdl

        # Clear from context
        ctx.request_context.lifespan_context.mapdl = None

        await ctx.disable_components(tags={REQUIRES_MAPDL_TAG})
        logger.info("Disconnected successfully!")
        return _text_result(f"Successfully disconnected from MAPDL at {ip}:{port}")

    except Exception as e:
        error_msg = f"Error during disconnect: {str(e)}"
        logger.error(error_msg)
        # Still clear the reference even if disconnect failed
        ctx.request_context.lifespan_context.mapdl = None
        return _text_result(error_msg)


@app.tool(tags={"session_management"})
def list_mapdl_instances(ctx: Context) -> ToolResult:
    """List all MAPDL instances running on the local machine and any remotely connected instance.

    This tool uses PyMAPDL CLI's
    :func:`~ansys.mapdl.mcp.helpers.list_instances` function to discover
    MAPDL instances running on the machine by scanning for active gRPC
    servers and their associated metadata. It also includes any remotely
    connected MAPDL instance that was established via the
    :func:`connect_to_mapdl` tool.

    Returns
    -------
    ToolResult
        Formatted table containing information about all running MAPDL instances
        including their names, status, gRPC ports, IP addresses, PIDs, and
        working directories. If a remote instance is connected, it is listed in a
        separate section below the local instances.
    """
    logger.info("Searching for MAPDL instances using PyMAPDL CLI...")

    from tabulate import tabulate

    from ansys.mapdl.mcp.helpers import list_instances

    # Use PyMAPDL CLI's list_instances function with long=True for detailed output
    local_table = list_instances(long=True, instances=True)

    # Also include any remotely connected instance from the current session context
    if ctx.request_context is None:
        return _text_result(local_table)
    mapdl = ctx.request_context.lifespan_context.mapdl
    if mapdl is not None and not mapdl.is_local:
        remote_headers = ["IP", "Port", "Status", "Version", "Working directory"]
        remote_row = [
            mapdl.ip,
            mapdl.port,
            mapdl.check_status,
            mapdl.version,
            str(mapdl.directory),
        ]
        remote_table = tabulate([remote_row], remote_headers)
        return _text_result(f"{local_table}\n\nRemotely connected instance:\n{remote_table}")

    return _text_result(local_table)


@app.tool(tags={"aali", REQUIRES_MAPDL_TAG, "visualization"})
def screenshot(
    ctx: Context,
    commands: str = "",
    show_plot_on_popup: bool = False,
    four_view: bool = False,
) -> ToolResult:
    """Capture a screenshot of the current MAPDL graphics window.

    All plots use the MAPDL backend, which is the preferred and recommended
    way to obtain plot images, especially for large or complex models, as it
    leverages MAPDL's native plotting capabilities.

    MAPDL Native Plot Commands (use with screenshot):

    - Geometry: ``APLOT``, ``LPLOT``, ``KPLOT``, ``VPLOT``
    - Mesh: ``EPLOT``, ``NPLOT``
    - Post-processing: ``PLNSOL``, ``PLESOL``, ``PLDISP``

    For custom matplotlib or PyVista plots, use the :func:`custom_plot` tool
    instead.

    Parameters
    ----------
    ctx : Context
        The MCP context containing server session and application context.
    commands : str, optional
        Optional MAPDL commands to execute before taking the screenshot.
        Avoid running commands that are not related to plotting or visualization.
        This can be used to set up the plot or visualization before capturing.
        Avoid running long or complex commands that may delay the screenshot.
        Default is empty string.
    show_plot_on_popup : bool, optional
        If ``True``, open the captured image in the system's default image
        viewer as an external popup window in addition to returning it to the
        LLM. Default is ``False``.
    four_view : bool, optional
        When ``True``, the graphics window is split into four quadrants before
        the screenshot is taken. When *commands* is provided together with
        ``four_view=True``, the *commands* string is used as the plot command
        that populates all four windows (default ``EPLOT`` when *commands* is
        empty). The window layout is automatically restored after the
        screenshot. Default is ``False``. See Notes for the quadrant layout.

    Returns
    -------
    ToolResult
        A result containing:

        - TextContent with the screenshot file path
        - ImageContent with the base64-encoded image data
    """
    mapdl, error = _get_mapdl(ctx)
    if error:
        return _text_result(error)

    try:
        if four_view:
            logger.info("Capturing four-view MAPDL screenshot...")
            plot_cmd = commands if commands else "EPLOT"
            pre_commands = _four_view_commands(plot_cmd)
            prefix = "mapdl_4view_"
        else:
            logger.info("Capturing MAPDL screenshot...")
            pre_commands = commands
            prefix = "mapdl_screenshot_"

        try:
            screenshot_path, image_data, mime_type = _capture_screenshot(
                mapdl, pre_commands, prefix
            )
        finally:
            if four_view:
                try:
                    mapdl.input_strings(_RESTORE_SINGLE_WINDOW)  # type: ignore[union-attr]
                except Exception as restore_err:
                    logger.warning(f"Could not restore single-window layout: {restore_err}")

        base64_data = base64.b64encode(image_data).decode("utf-8")

        if show_plot_on_popup:
            _open_image_in_viewer(str(screenshot_path))

        logger.info(f"Screenshot captured successfully: {screenshot_path}")

        return ToolResult(
            [
                TextContent(type="text", text=f"Screenshot saved to: {screenshot_path}"),
                ImageContent(type="image", data=base64_data, mimeType=mime_type),
            ]
        )

    except Exception as e:
        error_msg = f"Failed to capture screenshot: {str(e)}"
        logger.error(error_msg)
        return _text_result(error_msg)


####################################################################################################
# Tools that uses the PythonPersistentSession


@app.tool(tags={REQUIRES_MAPDL_TAG, "python_execution", "command_execution"})
async def run_python_code(
    ctx: Context,
    code: str,
    timeout: int = 60,
) -> ToolResult:
    """Execute arbitrary Python and PyMAPDL code in the persistent Python session.

    This tool should be used for custom Python code execution, particularly for:

    - Custom data processing and analysis
    - Creating custom matplotlib plots not available in MAPDL
    - Advanced PyVista visualizations beyond MAPDL's native capabilities
    - NumPy/Pandas data manipulation and custom visualization

    .. important:: For MAPDL native plotting (``APLOT``, ``LPLOT``, ``KPLOT``,
       post_processing plots, etc.), use the normal MAPDL session commands
       with the :func:`screenshot` tool instead, as they provide interactive
       plots that are directly accessible.

    Parameters
    ----------
    ctx : Context
        The MCP context containing server session and application context.
    code : str
        The Python code to execute.
    timeout : int, optional
        Maximum time in seconds to allow for code execution. Default is 60 seconds.

    Returns
    -------
    ToolResult
        Execution result or error message.

    Examples
    --------
    Execute simple Python code to compute a value:

    >>> code = '''
    ... result = sum([i**2 for i in range(10)])
    ... print(f"Sum of squares: {result}")
    ... '''
    >>> run_python_code(ctx, code)

    Execute PyMAPDL code:

    >>> code = '''
    ... displacements = mapdl.get_array("NODE", item1="U", it1num="Y")
    ... print(f"Displacements: {displacements}")
    ... '''
    >>> run_python_code(ctx, code)
    """
    if ctx.request_context is None:
        return _text_result(
            json.dumps(
                {"success": False, "error": "No request context available."}, ensure_ascii=False
            )
        )
    session = ctx.request_context.lifespan_context.python_session

    if session is None:
        return _text_result(
            json.dumps(
                {
                    "success": False,
                    "error": "No Python session available. The persistent Python session was not initialized.",  # noqa: E501
                },
                ensure_ascii=False,
            )
        )

    # Check if MAPDL is connected in the persistent session
    mapdl_instance = session.metadata.get("mapdl", None)
    if mapdl_instance is None or isinstance(mapdl_instance, str):
        mapdl_instance = connect_to_mapdl_in_persistent_python(ctx)

    if mapdl_instance is None or isinstance(mapdl_instance, str):
        try:
            mapdl_instance = connect_to_mapdl_in_persistent_python(ctx)
        except Exception as e:
            error_msg = f"Failed to connect to MAPDL in persistent Python session: {str(e)}"
            logger.error(error_msg)
            return _text_result(
                json.dumps(
                    {"success": False, "error": error_msg},
                    ensure_ascii=False,
                    indent=2,
                )
            )

    result: str = await execute_python_code(
        ctx=ctx,
        code=code,
        timeout=timeout,
    )
    return _text_result(result)


@app.tool(tags={"aali", REQUIRES_MAPDL_TAG, "visualization"})
def custom_plot(
    ctx: Context,
    plot_code: str,
    plot_type: str = "matplotlib",
    timeout: int = 60,
) -> ToolResult:
    """Create a custom plot using matplotlib or PyVista in the persistent Python session.

    This tool is specifically designed for creating custom plots that are NOT available
    in MAPDL's native plotting capabilities. Use this when you need:

    - Custom matplotlib visualizations (line plots, bar charts, histograms, etc.)
    - Advanced PyVista 3D visualizations beyond MAPDL defaults
    - Combined data from multiple sources
    - Custom data processing with visualization

    .. important:: For standard MAPDL plots (``APLOT``, ``LPLOT``, ``KPLOT``,
       post_processing plots), use the normal MAPDL commands with the
       :func:`screenshot` tool instead for interactive plots.

    The persistent Python session has pre-configured matplotlib (Agg backend) and
    PyVista (off-screen rendering) with helper functions:

    - save_matplotlib_plot(filename, dpi)
    - save_plot(plotter, filename)

    Parameters
    ----------
    ctx : Context
        The MCP context containing server session and application context.
    plot_code : str
        Python code to create the plot. Should use matplotlib.pyplot or PyVista.
        For matplotlib, the code should create the figure/plot but NOT call plt.show().
        Use the save_matplotlib_plot() or save_plot() helper functions to return
        the plot.
    plot_type : str, optional
        Type of plot: "matplotlib" or "pyvista". Default is "matplotlib".
    timeout : int, optional
        Maximum time in seconds for plot generation. Default is 60 seconds.

    Returns
    -------
    ToolResult
        A result containing:
        - TextContent with the plot creation status message
        - ImageContent with the base64-encoded image data if successful

    Examples
    --------
    Create a custom matplotlib line plot:

    >>> plot_code = '''
    ... import matplotlib.pyplot as plt
    ... import numpy as np
    ...
    ... # Extract data from MAPDL
    ... displacements = mapdl.get_array("NODE", item1="U", it1num="Y")
    ...
    ... # Create custom plot
    ... plt.figure(figsize=(10, 6))
    ... plt.plot(displacements)
    ... plt.xlabel("Node Number")
    ... plt.ylabel("Displacement (m)")
    ... plt.title("Custom Displacement Plot")
    ... plt.grid(True)
    ...
    ... # Save and return
    ... result = save_matplotlib_plot(dpi=150)
    ... print(result)
    ... '''
    >>> custom_plot(ctx, plot_code, plot_type="matplotlib")
    """
    if ctx.request_context is None:
        return _text_result("No request context available.")
    session = ctx.request_context.lifespan_context.python_session

    if session is None:
        return _text_result(
            "No Python session available. The persistent Python session was not initialized."
        )

    # Check if MAPDL is connected in the persistent session
    mapdl_instance = session.metadata.get("mapdl", None)
    if mapdl_instance is None or isinstance(mapdl_instance, str):
        mapdl_instance = connect_to_mapdl_in_persistent_python(ctx)

    if mapdl_instance is None or isinstance(mapdl_instance, str):
        if isinstance(mapdl_instance, str):
            error_msg = mapdl_instance
        else:
            error_msg = "An error occurred while connecting to MAPDL in the persistent Python session. Please, restart the session and try again."  # noqa: E501
        return _text_result(f"Failed to connect to MAPDL in persistent Python session: {error_msg}")

    result: list[TextContent | ImageContent] | str = create_custom_plot(
        ctx=ctx,
        plot_code=plot_code,
        plot_type=plot_type,
        timeout=timeout,
    )
    if isinstance(result, str):
        return _text_result(result)
    return ToolResult(result)


####################################################################################################
# File management tools


@app.tool(tags={REQUIRES_MAPDL_TAG, "file_management"})
def upload_file(ctx: Context, file_path: str) -> ToolResult:
    """Upload a local file to the MAPDL instance working directory.

    The file is transferred over gRPC from the local filesystem to the remote
    (or local) MAPDL working directory so that MAPDL commands such as
    ``RESUME``, ``CDREAD``, or ``FILE`` can reference it by its base name.

    Parameters
    ----------
    ctx : Context
        The MCP context containing server session and application context.
    file_path : str
        Absolute or relative path to the file on the **local** filesystem.

    Returns
    -------
    ToolResult
        Text message with the uploaded filename on success, or an error
        description if the file cannot be found or the transfer fails.

    Examples
    --------
    Upload a database file before resuming a model:

    >>> upload_file(ctx, "/home/user/project/beam.db")
    >>> resume_model(ctx, "beam", "db")
    """
    mapdl, error = _get_mapdl(ctx)
    if error:
        return _text_result(error)

    if not Path(file_path).is_file():
        return _text_result(f"File not found: '{file_path}'")

    try:
        uploaded_name = mapdl.upload(file_path, progress_bar=False)
        logger.info(f"Uploaded '{file_path}' to MAPDL working directory as '{uploaded_name}'.")
        return _text_result(
            f"File uploaded successfully. "
            f"The file is now available in the MAPDL working directory as '{uploaded_name}'."
        )
    except Exception as e:
        error_msg = f"Failed to upload '{file_path}': {e}"
        logger.error(error_msg)
        return _text_result(error_msg)


@app.tool(tags={REQUIRES_MAPDL_TAG, "file_management"})
def download_file(ctx: Context, file_name: str, target_dir: str | None = None) -> ToolResult:
    """Download a file from the MAPDL instance working directory to the local filesystem.

    Use this tool to retrieve result files (e.g. ``file.rst``, ``file.db``),
    log files, or any other file produced by the current MAPDL session.
    Glob patterns such as ``"file*"`` or ``"*.rst"`` are supported.

    Parameters
    ----------
    ctx : Context
        The MCP context containing server session and application context.
    file_name : str
        Name of the file in the MAPDL working directory to download.
        Supports glob patterns (e.g. ``"file*"``).
        Use the ``check_mapdl_status`` tool or the
        ``files://mapdl/working_directory`` resource to inspect available files.
    target_dir : str, optional
        Local directory where the file(s) will be saved.  Defaults to the
        current Python working directory when ``None``.

    Returns
    -------
    ToolResult
        Text message listing the downloaded files on success, or an error
        description if the download fails.

    Examples
    --------
    Download the main result file:

    >>> download_file(ctx, "file.rst", "/home/user/results")

    Download all output files:

    >>> download_file(ctx, "file*")
    """
    # Check target_dir exists
    if target_dir and not Path(target_dir).is_dir():
        error_msg = f"The folder {target_dir} doesn't exist. The file could not be downloaded."
        logger.error(error_msg)
        return _text_result(error_msg)

    # Get the MAPDL instance
    mapdl, error = _get_mapdl(ctx)
    if error:
        return _text_result(error)

    try:
        downloaded = mapdl.download(file_name, target_dir=target_dir, progress_bar=False)
        if not downloaded:
            return _text_result(f"No files matched '{file_name}' in the MAPDL working directory.")
        logger.info(f"Downloaded {len(downloaded)} file(s): {downloaded}")
        files_list = "\n".join(f"  - {f}" for f in downloaded)
        return _text_result(f"Successfully downloaded {len(downloaded)} file(s):\n{files_list}")
    except Exception as e:
        error_msg = f"Failed to download '{file_name}': {e}"
        logger.error(error_msg)
        return _text_result(error_msg)


@app.tool(tags={REQUIRES_MAPDL_TAG, "file_management"})
def resume_model(ctx: Context, file_name: str, extension: str = "db") -> ToolResult:
    """Resume a previously saved MAPDL model from a database or archive file.

    This tool restores the MAPDL database from a ``.db`` binary database file
    or a ``.cdb`` coded ASCII archive file.  If the file is on the local
    filesystem (not yet in the MAPDL working directory), upload it first with
    the ``upload_file`` tool.

    Parameters
    ----------
    ctx : Context
        The MCP context containing server session and application context.
    file_name : str
        Name of the file **without extension** as it exists in the MAPDL
        working directory (e.g. ``"beam"`` for ``beam.db``).
    extension : str, optional
        File extension that identifies the file format. Accepted values:

        * ``"db"`` *(default)* — binary MAPDL database (RESUME command).
        * ``"cdb"`` — coded ASCII database (CDREAD command).

    Returns
    -------
    ToolResult
        MAPDL command output on success, or an error description.

    Examples
    --------
    Resume from a binary database:

    >>> resume_model(ctx, "beam", "db")

    Resume from a coded archive:

    >>> resume_model(ctx, "model", "cdb")
    """
    mapdl, error = _get_mapdl(ctx)
    if error:
        return _text_result(error)

    ext = extension.lower().strip(".")
    if ext not in ("db", "cdb"):
        return _text_result(
            f"Unsupported extension '{extension}'. Use 'db' for binary database files "
            "or 'cdb' for coded ASCII archive files."
        )

    try:
        if ext == "db":
            output = mapdl.resume(file_name, ext)
        else:
            output = mapdl.cdread("db", file_name, ext)

        msg = output if output else f"Model resumed successfully from '{file_name}.{ext}'."
        logger.info(f"Resumed model from '{file_name}.{ext}'.")
        return _text_result(msg)
    except Exception as e:
        error_msg = f"Failed to resume model from '{file_name}.{ext}': {e}"
        logger.error(error_msg)
        return _text_result(error_msg)


@app.tool(tags={REQUIRES_MAPDL_TAG, "file_management"})
def open_results(ctx: Context, file_name: str | None = None) -> ToolResult:
    """Enter POST1 and optionally set the active results file for post-processing.

    This tool switches MAPDL into the POST1 post-processor and, when a file
    name is supplied, points MAPDL at that results file.  Use it before
    querying displacements, stresses, or other result quantities.

    If the RST file is stored on the local filesystem (not yet in the MAPDL
    working directory), upload it first with the ``upload_file`` tool.

    Parameters
    ----------
    ctx : Context
        The MCP context containing server session and application context.
    file_name : str, optional
        Name of the result file **without extension** in the MAPDL working
        directory (e.g. ``"beam"`` for ``beam.rst``).  When omitted, MAPDL
        uses the current jobname result file.

    Returns
    -------
    ToolResult
        Status message indicating whether POST1 was entered and the results
        file was set, or an error description.

    Examples
    --------
    Open the default results file:

    >>> open_results(ctx)

    Open a specific RST file:

    >>> open_results(ctx, "beam")
    """
    mapdl, error = _get_mapdl(ctx)
    if error:
        return _text_result(error)

    try:
        mapdl.post1()
        if file_name:
            mapdl.file(file_name, "rst")
            msg = (
                f"Entered POST1 and set active results file to '{file_name}.rst'. "
                "You can now query result quantities."
            )
        else:
            msg = (
                "Entered POST1 using the current jobname results file. "
                "You can now query result quantities."
            )
        logger.info(msg)
        return _text_result(msg)
    except Exception as e:
        error_msg = f"Failed to open results: {e}"
        logger.error(error_msg)
        return _text_result(error_msg)


####################################################################################################
# File path resources


@app.resource("files://mapdl/working_directory")
def mapdl_working_directory() -> str:
    """Return the working directory of the connected MAPDL instance.

    This resource provides the absolute path to the directory where MAPDL
    stores all its output files (``file.rst``, ``file.db``, log files, etc.).
    The path is updated dynamically each time this resource is read.

    Returns
    -------
    str
        Absolute path to the MAPDL working directory, or a message indicating
        that MAPDL is not connected.
    """
    from ansys.mapdl.mcp.server import app as _app

    mapdl = getattr(getattr(_app, "context", None), "mapdl", None)

    if mapdl is None:
        return "MAPDL is not connected. Use connect_to_mapdl or launch_mapdl_session."

    try:
        return str(mapdl.directory)
    except Exception as e:
        return f"Could not retrieve working directory: {e}"


@app.resource("files://mapdl/rst_path")
def mapdl_rst_path() -> str:
    """Return the expected path to the current MAPDL result file (RST).

    The path is constructed from the MAPDL working directory and the current
    jobname.  Before reading this file with an external application, ensure
    the simulation has finished running.

    Returns
    -------
    str
        Absolute path to ``<working_directory>/<jobname>.rst``, or a message
        indicating that MAPDL is not connected.
    """
    from ansys.mapdl.mcp.server import app as _app

    mapdl = getattr(getattr(_app, "context", None), "mapdl", None)
    if mapdl is None:
        return "MAPDL is not connected. Use connect_to_mapdl or launch_mapdl_session."
    try:
        return str(Path(mapdl.directory) / f"{mapdl.jobname}.rst")
    except Exception as e:
        return f"Could not retrieve RST path: {e}"


@app.resource("files://mapdl/db_path")
def mapdl_db_path() -> str:
    """Return the expected path to the current MAPDL database file (DB).

    The path is constructed from the MAPDL working directory and the current
    jobname.  This file is written by the MAPDL ``SAVE`` command and can be
    restored with the ``resume_model`` tool.

    Returns
    -------
    str
        Absolute path to ``<working_directory>/<jobname>.db``, or a message
        indicating that MAPDL is not connected.
    """
    from ansys.mapdl.mcp.server import app as _app

    mapdl = getattr(getattr(_app, "context", None), "mapdl", None)

    if mapdl is None:
        return "MAPDL is not connected. Use connect_to_mapdl or launch_mapdl_session."
    try:
        return str(Path(mapdl.directory) / f"{mapdl.jobname}.db")
    except Exception as e:
        return f"Could not retrieve DB path: {e}"


####################################################################################################
# Tool set definitions


@app.resource("toolsets://definition")
def list_tool_sets() -> list[dict]:
    """Tool set definition resource that lists available tool sets for PyMAPDL MCP.

    Returns
    -------
    list[dict]
        List of tool set definitions, each containing:

        - ``name``: Unique identifier for the tool set
        - ``description``: Human-readable description of the tool set
        - ``skill``: Instructions for the AI agent on when and how to use these tool sets
        - ``tools``: List of tool function names in this set

    Examples
    --------
    >>> list_tool_sets()
    [
        {
            "name": "session_management",
            "description": "Tools for managing MAPDL session connections and instances",
            "skill": (
                "Use these tools to manage MAPDL connections and sessions. "
                "Start by checking available installations with check_mapdl_installed, "
                "then launch a new session with launch_mapdl_session or connect to an existing "
                "instance with connect_to_mapdl. Use check_mapdl_status to verify the connection"
                "status. List active instances with list_mapdl_instances and disconnect when done"
                " using disconnect_from_mapdl."
            ),
            "tools": [
                "check_mapdl_installed",
                "check_mapdl_status",
                "launch_mapdl_session",
                "connect_to_mapdl",
                "disconnect_from_mapdl",
                "list_mapdl_instances",
            ],
        }
    ]

    """
    return [
        {
            "name": "session_management",
            "description": "Tools for managing MAPDL session connections and instances",
            "skill": (
                "Use these tools to manage MAPDL connections and sessions. "
                "Start by checking available installations with check_mapdl_installed, "
                "then launch a new session with launch_mapdl_session or connect to an existing "
                "instance with connect_to_mapdl. Use check_mapdl_status to verify the connection"
                "status. List active instances with list_mapdl_instances and disconnect when done"
                " using disconnect_from_mapdl."
            ),
            "tools": [
                "check_mapdl_installed",
                "check_mapdl_status",
                "launch_mapdl_session",
                "connect_to_mapdl",
                "disconnect_from_mapdl",
                "list_mapdl_instances",
            ],
        },
        {
            "name": "command_execution",
            "description": "Tools for executing MAPDL commands and scripts",
            "skill": (
                "Use these tools to execute MAPDL commands and scripts. "
                "Use run_mapdl_command for single commands with optional comments and headers. "
                "Use run_multiple_mapdl_commands for batch execution of multiple commands, which "
                "is optimized for performance. Alternatively, use run_python_code to execute "
                "MAPDL commands via PyMAPDL for more complex scripting scenarios. Always ensure "
                "a MAPDL connection is active before executing commands."
            ),
            "tools": [
                "run_mapdl_command",
                "run_multiple_mapdl_commands",
                "run_python_code",
            ],
        },
        {
            "name": "visualization",
            "description": "Tools for visualization, custom analysis, and post-processing",
            "skill": (
                "Use these tools for visualization and post-processing of MAPDL results. "
                "Use screenshot to capture MAPDL native plots (``APLOT``, ``EPLOT``, "
                "``PLNSOL``, etc.). "
                "Use custom_plot to create custom matplotlib or PyVista visualizations for "
                "custom analysis. For visualization workflows, use custom_plot rather than "
                "run_python_code."
            ),
            "tools": [
                "screenshot",
                "custom_plot",
            ],
        },
        {
            "name": "python_execution",
            "description": "Tools for executing arbitrary Python and PyMAPDL commands",
            "skill": (
                "Use run_python_code to execute general-purpose Python and PyMAPDL commands "
                "for scripting, data processing, and automation. For visualization output, "
                "use custom_plot so images are returned correctly through the plotting pipeline."
            ),
            "tools": [
                "run_python_code",
            ],
        },
        {
            "name": "file_management",
            "description": (
                "Tools for transferring files to/from MAPDL and loading saved models or results"
            ),
            "skill": (
                "Use these tools to manage files in the MAPDL working directory. "
                "Upload local files to MAPDL with upload_file before referencing them in "
                "commands. "
                "Download any file produced by MAPDL (results, logs, databases) with "
                "download_file. "
                "Restore a previously saved model with resume_model "
                "(supports .db and .cdb formats). "
                "Enter POST1 and point MAPDL at a result file with open_results before querying "
                "displacements, stresses, or other result quantities. "
                "Use the resources files://mapdl/working_directory, files://mapdl/rst_path, and "
                "files://mapdl/db_path to discover the paths to MAPDL output files."
            ),
            "tools": [
                "upload_file",
                "download_file",
                "resume_model",
                "open_results",
            ],
        },
    ]
