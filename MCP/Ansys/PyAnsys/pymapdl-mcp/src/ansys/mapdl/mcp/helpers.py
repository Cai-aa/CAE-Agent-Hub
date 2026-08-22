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

"""Helper functions for PyMAPDL MCP."""

from typing import TYPE_CHECKING, Any

from ansys.common.mcp.helpers import logger
from fastmcp.server import Context

if TYPE_CHECKING:
    from ansys.mapdl.core import Mapdl  # pyright: ignore[reportMissingTypeStubs]


def list_instances(
    instances: bool = False,
    long: bool = False,
    cmd: bool = False,
    location: bool = False,
) -> str:
    """
    List running MAPDL instances on the system.

    This function scans all running processes to identify ANSYS MAPDL instances
    that are using gRPC communication. It returns a formatted table with information
    about each discovered instance.

    Parameters
    ----------
    instances : bool, optional
        If True, only show main MAPDL instances (exclude child processes).
        If False, show all MAPDL-related processes. Default is False.
    long : bool, optional
        If True, enable verbose output including command line and working directory.
        This automatically sets both `cmd` and `location` to True. Default is False.
    cmd : bool, optional
        If True, include the command line arguments in the output table.
        Default is False.
    location : bool, optional
        If True, include the working directory path in the output table.
        Default is False.

    Returns
    -------
    str
        A formatted table string containing information about MAPDL instances.
        The table includes columns for process name, status, gRPC port, PID,
        and optionally command line and working directory based on the parameters.

    Notes
    -----
    - This function identifies MAPDL processes by looking for "ansys" or "mapdl"
      in the process name and the presence of "-grpc" flag in command line arguments.
    - Only processes with status RUNNING, IDLE, or SLEEPING are considered valid.
    - Main instances are distinguished from child processes by counting their children.
    - Processes that no longer exist or are zombies are silently skipped.

    Examples
    --------
    >>> # List all MAPDL processes
    >>> print(list_instances())

    >>> # List only main instances with full details
    >>> print(list_instances(instances=True, long=True))

    >>> # List with command line information
    >>> print(list_instances(cmd=True))
    """
    import psutil
    from tabulate import tabulate

    # this copied from PyMAPDL, but it will be refactored there later
    # Assuming all ansys processes have -grpc flag
    mapdl_instances = []

    def is_grpc_based(proc):
        cmdline = proc.cmdline()
        return "-grpc" in cmdline

    def get_port(proc):
        cmdline = proc.cmdline()
        if "-port" in cmdline:
            ind_grpc = cmdline.index("-port")
            return cmdline[ind_grpc + 1]
        else:
            return "N/A"

    def is_valid_process(proc):
        valid_status = proc.status() in [
            psutil.STATUS_RUNNING,
            psutil.STATUS_IDLE,
            psutil.STATUS_SLEEPING,
        ]
        valid_ansys_process = ("ansys" in proc.name().lower()) or ("mapdl" in proc.name().lower())
        return valid_status and valid_ansys_process and is_grpc_based(proc)

    for proc in psutil.process_iter():
        # Check if the process is running and not suspended
        try:
            if is_valid_process(proc):
                # Checking the number of children we infer if the process is the main process,
                # or one of the main process thread.
                if len(proc.children(recursive=True)) < 2:
                    proc.ansys_instance = False
                else:
                    proc.ansys_instance = True
                mapdl_instances.append(proc)

        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            continue

    # printing
    if long:
        cmd = True
        location = True

    if instances:
        headers = ["Name", "Status", "gRPC port", "PID"]
    else:
        headers = ["Name", "Is Instance", "Status", "gRPC port", "PID"]

    if cmd:
        headers.append("Command line")
    if location:
        headers.append("Working directory")

    table = []
    for each_p in mapdl_instances:
        if instances and not each_p.ansys_instance:
            # Skip child processes if only printing instances
            continue

        proc_line = []
        proc_line.append(each_p.name())

        if not instances:
            proc_line.append(each_p.ansys_instance)

        proc_line.extend([each_p.status(), get_port(each_p), each_p.pid])

        if cmd:
            proc_line.append(" ".join(each_p.cmdline()))

        if location:
            try:
                proc_line.append(each_p.cwd())
            except (psutil.NoSuchProcess, psutil.ZombieProcess, psutil.AccessDenied):
                proc_line.append("N/A")

        table.append(proc_line)

    return str(tabulate(table, headers))


def get_info(mapdl: "Mapdl") -> dict[str, str | dict[str, Any]]:
    """
    Get information from the MAPDL instance.

    Parameters
    ----------
    mapdl : :class:`~ansys.mapdl.core.Mapdl`
        MAPDL instance

    Returns
    -------
    dict[str, str | dict[str, Any]]
        Dictionary containing MAPDL information with the following hierarchy:

        .. code-block:: text

            {
              "connection": {
                  "name": str,        # Instance name
                  "ip": str,          # IP address
                  "port": int,        # gRPC port
                  "version": str,     # MAPDL version string
                  "directory": str,   # Working directory
                  "status": str,      # Connection status
                  "is_local": bool,   # Whether the instance is local
                  "jobname": str,     # MAPDL jobname
                  "platform": str,    # OS platform
              },
              "information": {
                  "title": str,       # Analysis title (/TITLE)
                  "jobname": str,     # Jobname from Information class
                  "routine": str,     # Current MAPDL routine (e.g. PREP7, SOLU)
                  "units": str,       # Unit system
                  "revision": str,    # MAPDL revision string
                  "product": str,     # MAPDL product name
              },
              "geometry": {
                  "n_keypoint": int,  # Number of keypoints
                  "n_line": int,      # Number of lines
                  "n_area": int,      # Number of areas
                  "n_volu": int,      # Number of volumes
              },
              "mesh": {
                  "n_node": int,      # Number of nodes
                  "n_elem": int,      # Number of elements
              },
              "components": {
                  "count": int,               # Total number of named components
                  "items": {                  # Mapping of component name to entity type
                      "<name>": "<type>",     # e.g. "MY_NODES": "NODES"
                      ...                     # Types: NODES, ELEMS, KP, LINE, AREA, VOLU
                  },
              },
              "materials": {
                  "count": int,       # Number of material reference numbers defined
                  "ids": [int, ...],  # List of defined material reference numbers
              },
              "sections": {
                  "count": int,       # Number of sections defined
                  "ids": [int, ...],  # List of defined section IDs
                  "types": {          # Mapping of section ID to section type string
                      "<id>": "<type>",   # e.g. "1": "SHELL"
                      ...
                  },
              },
              "post_processing": {
                  "available": bool,  # Whether post-processing is accessible
                  "nsets": int,       # Number of result sets in the result file
              },
            }

        Any sub-dict may also contain an ``"error"`` key (string) when that
        section failed to retrieve, so callers should always check for it.
    """
    with mapdl.run_as_routine("PREP7"):
        info: dict[str, str | dict[str, Any]] = {}

        # Basic connection information
        info["connection"] = {
            "name": mapdl.name,
            "ip": mapdl.ip,
            "port": mapdl.port,
            "version": mapdl.version,
            "directory": str(mapdl.directory),
            "status": mapdl.check_status.title(),
            "is_local": mapdl.is_local,
            "jobname": mapdl.jobname,
            "platform": mapdl.platform,
        }

        # Information class attributes
        info_class: dict[str, str] = {}
        try:
            information = getattr(mapdl, "info", None)
            if information is not None:
                info_class["title"] = getattr(information, "title", "")
                info_class["jobname"] = getattr(information, "jobname", "")
                info_class["routine"] = getattr(information, "routine", "")
                info_class["units"] = getattr(information, "units", "")
                info_class["revision"] = getattr(information, "revision", "")
                info_class["product"] = getattr(information, "product", "")
        except Exception as e:
            logger.warning(f"Error extracting information class data: {e}")
            info_class["error"] = str(e)
        info["information"] = info_class

        # Geometry class attributes
        geometry_info: dict[str, int | str] = {}
        try:
            # Try to get number of keypoints, lines, areas, volumes
            geometry_info["n_keypoint"] = mapdl.geometry.n_keypoint
            geometry_info["n_line"] = mapdl.geometry.n_line
            geometry_info["n_area"] = mapdl.geometry.n_area
            geometry_info["n_volu"] = mapdl.geometry.n_volu
        except Exception as e:
            logger.warning(f"Error extracting geometry data: {e}")
            geometry_info["error"] = str(e)
        info["geometry"] = geometry_info

        # Mesh information
        mesh_info: dict[str, int | str] = {}
        try:
            mesh_info["n_node"] = mapdl.mesh.n_node
            mesh_info["n_elem"] = mapdl.mesh.n_elem
        except Exception as e:
            logger.warning(f"Error extracting mesh data: {e}")
            mesh_info["error"] = str(e)
        info["mesh"] = mesh_info

        # Parts
        parts_info: dict[str, Any] = {}
        try:
            parts_info["count"] = int(mapdl.get_value("PART", 0, "NUMP"))
        except Exception as e:
            logger.warning(f"Error extracting parts data: {e}")
            parts_info["error"] = str(e)
        info["parts"] = parts_info

        # Named components (mapdl.components is a ComponentManager)
        components_info: dict[str, Any] = {}
        try:
            comp_manager = getattr(mapdl, "components", None)
            if comp_manager is not None:
                components_info["count"] = len(comp_manager)
                components_info["items"] = dict(comp_manager.items())
            else:
                components_info["count"] = 0
                components_info["items"] = {}
        except Exception as e:
            logger.warning(f"Error extracting components data: {e}")
            components_info["error"] = str(e)
        info["components"] = components_info

        # Material reference numbers
        materials_info: dict[str, Any] = {}
        try:
            materials_info["count"] = int(mapdl.get_value("MAT", 0, "COUNT"))
            materials_info["max_id"] = int(mapdl.get_value("MAT", 0, "NUM", "MAX"))
        except Exception as e:
            logger.warning(f"Error extracting materials data: {e}")
            materials_info["error"] = str(e)
        info["materials"] = materials_info

        # Section definitions
        sections_info: dict[str, Any] = {}
        try:
            sections_info["count"] = int(mapdl.get_value("SECP", 0, "COUNT"))
            sections_info["max_id"] = int(mapdl.get_value("SECP", 0, "NUM", "MAX"))
        except Exception as e:
            logger.warning(f"Error extracting sections data: {e}")
            sections_info["error"] = str(e)
        info["sections"] = sections_info

        # Post_processing class attributes
        post_info: dict[str, str | int | bool] = {}
        try:
            # Try to get common post-processing information
            if hasattr(mapdl, "post_processing"):
                post_info["available"] = True
                # Check for number of result sets
                if hasattr(mapdl.post_processing, "nsets"):
                    post_info["nsets"] = mapdl.post_processing.nsets
            else:
                post_info["available"] = False
        except Exception as e:
            logger.warning(f"Error extracting post_processing data: {e}")
            post_info["error"] = str(e)
        info["post_processing"] = post_info

    return info


def connect_to_mapdl_in_persistent_python(
    ctx: Context,
) -> Any:
    """Connect to the MAPDL instance in the persistent Python session.

    This tool connects to the MAPDL instance from within the persistent Python session.
    It assumes that the persistent session has already been created.


    Parameters
    ----------
    ctx : Context
        The MCP context containing server session and application context.

    Returns
    -------
    str
        Connection status message.
    """
    if ctx.request_context is None:
        return "No request context available."
    session = ctx.request_context.lifespan_context.python_session

    if session is None:
        return "No Python session available. The persistent Python session was not initialized."

    try:
        # Check if already connected
        if session.metadata.get("mapdl", None) is not None:
            mapdl = session.metadata["mapdl"]
            return (
                f"Already connected to persistent PyMAPDL session with MAPDL at "
                f"{mapdl._ip}:{mapdl._port}."
            )

        # First, check if MAPDL is available in lifespan context
        mapdl_instance = ctx.request_context.lifespan_context.mapdl
        if mapdl_instance is None:
            return (
                "No MAPDL instance available in lifespan context. "
                "Please launch or connect to MAPDL first using ``launch_mapdl_session``"
                "or ``connect_to_mapdl`` tools."
            )

        connection_code = f"""
# Connect to the persistent MAPDL instance
from ansys.mapdl.core import Mapdl  # pyright: ignore[reportMissingTypeStubs]

mapdl = Mapdl(
    start_instance=False,
    ip='{mapdl_instance.ip}',
    port={mapdl_instance.port},
    cleanup_on_exit=False,
)
        """
        session.execute(connection_code)

        # Store in persistent session
        session.metadata["mapdl"] = mapdl_instance

        logger.info(
            "Connected to persistent PyMAPDL session successfully at"
            f" {mapdl_instance.ip}:{mapdl_instance.port}!"
        )

    except Exception as e:
        error_msg = f"Failed to connect to MAPDL in the persistent PyMAPDL session: {str(e)}"
        logger.error(error_msg)

    return session.metadata.get("mapdl", None)
