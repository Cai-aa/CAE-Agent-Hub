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

"""Helper functions for PyAEDT-MCP.

This module provides utility functions for working with AEDT
instances and extracting information from them.
"""

from dataclasses import asdict
from pathlib import Path
import socket
from typing import Any

from ansys.common.mcp import get_logger

logger = get_logger(__name__)


def _is_docker() -> bool:
    """Detect whether the current process is running inside a Docker container."""
    return Path("/.dockerenv").exists() or Path("/run/.containerenv").exists()


def _probe_grpc_endpoint(host: str, port: int, timeout: float = 2.0) -> dict[str, Any]:
    """Test whether a gRPC endpoint is reachable via a TCP connect probe.

    Parameters
    ----------
    host : str
        Hostname or IP address to probe.
    port : int
        TCP port number.
    timeout : float, optional
        Connection timeout in seconds.  Default is ``2.0``.

    Returns
    -------
    dict[str, Any]
        ``{"reachable": bool, "host": str, "port": int, "error": str | None}``
    """
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return {"reachable": True, "host": host, "port": port, "error": None}
    except Exception as e:
        return {"reachable": False, "host": host, "port": port, "error": str(e)}


def discover_available_aedt_sessions() -> list[dict[str, Any]]:
    """Discover AEDT sessions currently running on the local system.

    Returns
    -------
    list[dict[str, Any]]
        Session metadata similar to the PyAEDT CLI ``session list`` output.
        Each entry includes whether the session is connectable from PyAEDT-MCP,
        which currently requires gRPC mode with a known port.
    """
    from ansys.aedt.core.cli.aedt import _discover_aedt_sessions

    sessions = _discover_aedt_sessions()
    normalized_sessions = []
    for session_info in sessions:
        normalized = asdict(session_info)
        normalized["connectable"] = (
            normalized.get("mode") == "grpc" and normalized.get("port") is not None
        )
        normalized_sessions.append(normalized)
    return normalized_sessions


def get_aedt_info(desktop: Any) -> dict[str, Any]:
    """Get comprehensive information from an AEDT instance.

    Parameters
    ----------
    desktop : Any
        AEDT instance.

    Returns
    -------
    dict[str, Any]
        Dictionary containing AEDT information including:
        - connection: Connection details (version, machine, port, grpc mode)
        - projects: List of open projects
        - active_project: Currently active project
        - installed_versions: Available AEDT versions
    """
    info: dict[str, Any] = {
        "connection": {},
        "projects": [],
        "active_project": None,
        "active_design": None,
        "installed_versions": [],
    }

    try:
        # Connection information
        info["connection"] = {
            "version": (
                str(desktop.aedt_version_id) if hasattr(desktop, "aedt_version_id") else "Unknown"
            ),
            "version_string": (
                str(desktop.aedt_version_string)
                if hasattr(desktop, "aedt_version_string")
                else "Unknown"
            ),
            "install_dir": (
                str(desktop.aedt_install_dir) if hasattr(desktop, "aedt_install_dir") else "Unknown"
            ),
            "is_grpc": desktop.is_grpc_api if hasattr(desktop, "is_grpc_api") else False,
            "machine": str(desktop.machine) if hasattr(desktop, "machine") else "localhost",
            "port": desktop.port if hasattr(desktop, "port") else None,
            "non_graphical": desktop.non_graphical if hasattr(desktop, "non_graphical") else True,
            "process_id": desktop.aedt_process_id if hasattr(desktop, "aedt_process_id") else None,
        }
    except Exception as e:
        info["connection"]["error"] = str(e)

    try:
        # Project list
        info["projects"] = desktop.project_list if hasattr(desktop, "project_list") else []
    except Exception as e:
        info["projects_error"] = str(e)

    try:
        # Active project
        active_proj = (
            desktop.active_project()
            if hasattr(desktop, "active_project") and callable(desktop.active_project)
            else None
        )
        if active_proj:
            info["active_project"] = (
                active_proj.GetName() if hasattr(active_proj, "GetName") else str(active_proj)
            )
    except Exception:
        info["active_project"] = None

    try:
        # Active design
        active_design = (
            desktop.active_design()
            if hasattr(desktop, "active_design") and callable(desktop.active_design)
            else None
        )
        if active_design:
            info["active_design"] = (
                active_design.GetName() if hasattr(active_design, "GetName") else str(active_design)
            )
    except Exception:
        info["active_design"] = None

    try:
        # Installed versions
        if hasattr(desktop, "installed_versions"):
            info["installed_versions"] = list(desktop.installed_versions.keys())
    except Exception as e:
        info["installed_versions_error"] = str(e)

    return info


def get_design_info(app: Any) -> dict[str, Any]:
    """Get information about an AEDT application or design.

    Parameters
    ----------
    app : Any
        AEDT application instance (such as HFSS, Maxwell3d, Icepak, and so on).

    Returns
    -------
    dict[str, Any]
        Dictionary containing design information.
    """
    info: dict[str, Any] = {}

    try:
        info["design_name"] = app.design_name if hasattr(app, "design_name") else "Unknown"
        info["project_name"] = app.project_name if hasattr(app, "project_name") else "Unknown"
        info["design_type"] = app.design_type if hasattr(app, "design_type") else "Unknown"
        info["solution_type"] = app.solution_type if hasattr(app, "solution_type") else "Unknown"
        info["working_directory"] = (
            app.working_directory if hasattr(app, "working_directory") else "Unknown"
        )
        info["project_path"] = app.project_path if hasattr(app, "project_path") else "Unknown"
    except Exception as e:
        info["error"] = str(e)

    try:
        # Setup information
        if hasattr(app, "setups"):
            info["setups"] = [s.name if hasattr(s, "name") else str(s) for s in app.setups]
        else:
            info["setups"] = []
    except Exception:
        info["setups"] = []

    try:
        # Boundary information
        if hasattr(app, "boundaries"):
            info["boundaries"] = [b.name if hasattr(b, "name") else str(b) for b in app.boundaries]
        else:
            info["boundaries"] = []
    except Exception:
        info["boundaries"] = []

    try:
        # Variable information
        if hasattr(app, "variable_manager") and hasattr(app.variable_manager, "design_variables"):
            info["design_variables"] = list(app.variable_manager.design_variables.keys())
        else:
            info["design_variables"] = []
    except Exception:
        info["design_variables"] = []

    return info


def parse_aedt_version(version_str: str | None) -> str | None:
    """Parse and normalize an AEDT version string.

    Parameters
    ----------
    version_str : str | None
        Version string in various formats (such as "2026.1", "261", or "26.1").

    Returns
    -------
    str | None
        Normalized version string or ``None`` if invalid.
    """
    if version_str is None:
        return None

    version_str = str(version_str).strip()

    # Already in correct format
    if len(version_str) == 3 and version_str.isdigit():
        return version_str

    # Format: "2026.1" -> "261"
    if "." in version_str:
        parts = version_str.split(".")
        if len(parts) == 2:
            try:
                year = int(parts[0])
                release = int(parts[1])
                if year >= 2000:
                    return f"{year % 100}{release}"
            except ValueError:
                pass

    # Format: "26.1" -> "261"
    if "." in version_str:
        try:
            parts = version_str.split(".")
            if len(parts) == 2:
                return f"{parts[0]}{parts[1]}"
        except (ValueError, IndexError):
            pass

    return version_str


def get_design_type_map() -> dict[str, Any]:
    """Get a mapping from AEDT design-type strings to PyAEDT application classes.

    The keys are the design-type identifiers returned by
    ``Desktop.design_type()``. The values are the corresponding PyAEDT
    application classes that can be instantiated to attach to an existing
    AEDT session.

    Returns
    -------
    dict[str, Any]
        Mapping of design-type string to a PyAEDT application class.
    """
    import ansys.aedt.core as aedt_module

    return {
        "HFSS": aedt_module.Hfss,
        "Maxwell 3D": aedt_module.Maxwell3d,
        "Maxwell 2D": aedt_module.Maxwell2d,
        "Icepak": aedt_module.Icepak,
        "Q3D Extractor": aedt_module.Q3d,
        "2D Extractor": aedt_module.Q2d,
        "Circuit Design": aedt_module.Circuit,
        "Twin Builder": aedt_module.TwinBuilder,
        "Mechanical": aedt_module.Mechanical,
        "EMIT": aedt_module.Emit,
        "RMxprt": getattr(aedt_module, "Rmxprt", None),
        "HFSS 3D Layout Design": aedt_module.Hfss3dLayout,
    }


def resolve_design_app(
    desktop: Any,
    project_name: str | None = None,
    design_name: str | None = None,
) -> tuple[Any, str | None, str | None]:
    """Resolve and attach to the PyAEDT application for a target design.

    Parameters
    ----------
    desktop : Any
        Connected AEDT instance.
    project_name : str, default: None
        Project name to resolve. If ``None``, the active project is used.
    design_name : str, default: None
        Design name to resolve. If ``None``, the active design is used.

    Returns
    -------
    tuple[Any, str | None, str | None]
        Tuple containing the attached PyAEDT application instance, resolved project
        name, and resolved design name.

    Raises
    ------
    RuntimeError
        If the design type is unsupported.
    """
    active_project = (
        desktop.active_project() if callable(getattr(desktop, "active_project", None)) else None
    )
    resolved_project_name = project_name or (
        active_project.GetName()
        if active_project is not None and hasattr(active_project, "GetName")
        else None
    )

    active_design = (
        desktop.active_design() if callable(getattr(desktop, "active_design", None)) else None
    )
    resolved_design_name = design_name or (
        active_design.GetName()
        if active_design is not None and hasattr(active_design, "GetName")
        else None
    )

    design_type = desktop.design_type(design_name=resolved_design_name)
    app_class = get_design_type_map().get(design_type)
    if app_class is None:
        raise RuntimeError(f"Unsupported design type '{design_type}'")

    app_kwargs: dict[str, Any] = {"new_desktop": False}
    if resolved_project_name:
        app_kwargs["project"] = resolved_project_name
    if resolved_design_name:
        app_kwargs["design"] = resolved_design_name

    app_instance = app_class(**app_kwargs)
    return (
        app_instance,
        resolved_project_name or getattr(app_instance, "project_name", None),
        resolved_design_name or getattr(app_instance, "design_name", None),
    )
