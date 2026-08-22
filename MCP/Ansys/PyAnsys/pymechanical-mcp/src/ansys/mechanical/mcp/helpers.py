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

"""Helper functions for PyMechanical-MCP."""

import logging
import os
from pathlib import Path
import socket
import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ansys.mechanical.core import Mechanical

logger = logging.getLogger(__name__)

# Valid transport modes supported by PyMechanical's gRPC layer.
VALID_TRANSPORT_MODES = {"auto", "insecure", "mtls", "wnua"}


def _is_linux() -> bool:
    """Return True when running on a Linux / POSIX platform (incl. Docker)."""
    return sys.platform.startswith("linux") or sys.platform == "darwin"


def _is_docker() -> bool:
    """Return True when running inside a Docker container."""
    return Path("/.dockerenv").exists() or Path("/run/.containerenv").exists()


def _probe_grpc_endpoint(host: str, port: int, timeout: float = 3.0) -> dict[str, Any]:
    """Test whether a gRPC endpoint is reachable via a TCP connect probe.

    Parameters
    ----------
    host : str
        Hostname or IP address.
    port : int
        gRPC port number.
    timeout : float
        Seconds to wait before giving up.

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


def _find_certs_dir(certs_dir: str | None = None) -> Path | None:
    """Locate a certificate directory that contains the required mTLS files.

    Checks, in order:
    1. An explicit *certs_dir* argument.
    2. The ``ANSYS_GRPC_CERTIFICATES`` environment variable.
    3. A ``certs/`` directory relative to the current working directory.

    Parameters
    ----------
    certs_dir : str | None
        Explicit path supplied by the user/CLI.

    Returns
    -------
    Path | None
        The resolved directory if it contains ``ca.crt``, ``client.crt``,
        and ``client.key``; otherwise ``None``.
    """
    candidates: list[Path] = []

    if certs_dir is not None:
        candidates.append(Path(certs_dir))

    env_val = os.environ.get("ANSYS_GRPC_CERTIFICATES")
    if env_val:
        candidates.append(Path(env_val))

    # Fallback: conventional relative directory
    candidates.append(Path("certs"))

    required_files = ("ca.crt", "client.crt", "client.key")

    for candidate in candidates:
        if candidate.is_dir() and all((candidate / f).is_file() for f in required_files):
            logger.info("mTLS certificates found in: %s", candidate)
            return candidate

    return None


def resolve_transport_mode(
    transport_mode: str | None = None,
    certs_dir: str | None = None,
) -> tuple[str | None, str | None]:
    """Determine the gRPC transport mode and certificate directory to use.

    The resolution strategy follows:

    1. **Explicit override**: If the caller (CLI flag, environment variable, or tool
       parameter) supplies a concrete mode (``insecure``, ``mtls``, or
       ``wnua``), honor it unconditionally.
    2. **Auto-detect** (``transport_mode`` is ``None`` or ``"auto"``):
         - On **Windows**: Return ``None`` so that PyMechanical applies its
           own platform default (``wnua``).
         - On **Linux / Docker**: Return ``"mtls"`` plus the resolved
           certificate directory when mTLS certificate files are found.
           Otherwise, return ``"insecure"`` (the only mode that can
           succeed without certificates). WNUA is Windows-only.

    Parameters
    ----------
    transport_mode : str | None
        Transport mode requested by the user. Options are
        ``"auto"`` (default), ``"insecure"``, ``"mtls"``, and ``"wnua"``.
        ``None`` is treated identically to ``"auto"``.
    certs_dir : str | None
        Explicit path to a directory containing ``ca.crt``,
        ``client.crt``, and ``client.key`` for mTLS.

    Returns
    -------
    tuple[str | None, str | None]
        ``(resolved_transport_mode, resolved_certs_dir)``

        ``resolved_transport_mode`` is ``None`` when the caller should let
        PyMechanical choose (for example, Windows auto-detect).
        ``resolved_certs_dir`` is ``None`` unless mTLS is selected and
        certificates were located.

    Raises
    ------
    ValueError
        If ``transport_mode`` is not one of the accepted values.
    """
    # Normalise
    mode = (transport_mode or "auto").strip().lower()

    if mode not in VALID_TRANSPORT_MODES:
        raise ValueError(
            f"Invalid transport_mode {transport_mode!r}.  "
            f"Accepted values: {', '.join(sorted(VALID_TRANSPORT_MODES))}"
        )

    # --- Explicit mode (not auto) -------------------------------------------
    if mode != "auto":
        resolved_certs = None
        if mode == "mtls":
            cert_path = _find_certs_dir(certs_dir)
            if cert_path is not None:
                resolved_certs = str(cert_path)
            else:
                # User explicitly asked for mTLS but certs are missing.
                # Let PyMechanical raise its own descriptive FileNotFoundError
                # rather than silently falling back.
                resolved_certs = certs_dir  # may still be None
                logger.warning(
                    "transport_mode='mtls' requested but certificate files "
                    "were not found. PyMechanical will raise an error at "
                    "connection time."
                )
        return mode, resolved_certs

    # --- Auto-detect ---------------------------------------------------------
    if not _is_linux():
        # Windows: let PyMechanical apply its default (wnua).
        logger.info(
            "Auto-detect: Windows platform detected; deferring "
            "transport_mode to PyMechanical default (wnua)."
        )
        return None, None

    # Linux / macOS / Docker
    cert_path = _find_certs_dir(certs_dir)
    if cert_path is not None:
        logger.info(
            "Auto-detect: Linux platform with mTLS certificates found at "
            "%s; using transport_mode='mtls'.",
            cert_path,
        )
        return "mtls", str(cert_path)

    logger.info(
        "Auto-detect: Linux platform without mTLS certificates; using transport_mode='insecure'."
    )
    return "insecure", None


def list_instances(
    instances: bool = False,
    long: bool = False,
    cmd: bool = False,
    location: bool = False,
) -> str:
    """
    List running Mechanical instances on the system.

    This function scans all running processes to identify Ansys Mechanical instances
    that are using gRPC communication. It returns a formatted table with information
    about each discovered instance.

    Parameters
    ----------
    instances : bool, default: False
        If ``True``, only show main Mechanical instances (exclude child processes).
        If ``False``, show all Mechanical-related processes.
    long : bool, default: False
        If ``True``, enable verbose output including command line and working directory.
        This automatically sets both ``cmd`` and ``location`` to ``True``.
    cmd : bool, default: False
        If ``True``, include the command-line arguments in the output table.
    location : bool, default: False
        If ``True``, include the working directory path in the output table.

    Returns
    -------
    str
        A formatted table string containing information about Mechanical instances.
        The table includes columns for process name, status, gRPC port, PID,
        and optionally the command line and working directory based on the parameters.

    Notes
    -----
    - This function identifies Mechanical processes by looking for ``AnsysWBU`` or
      ``mechanical`` in the process name or command line.
    - Only processes with status ``RUNNING``, ``IDLE``, or ``SLEEPING`` are considered valid.
    """
    import psutil
    from tabulate import tabulate

    mechanical_instances = []

    def is_grpc_based(proc):
        """Check if process uses gRPC."""
        cmdline = proc.cmdline()
        # Check for --port flag or grpc indicators
        return (
            "--port" in cmdline
            or "-grpc" in cmdline
            or any("grpc" in arg.lower() for arg in cmdline)
        )

    def get_port(proc):
        """Extract port from command line."""
        cmdline = proc.cmdline()
        if "--port" in cmdline:
            try:
                ind_port = cmdline.index("--port")
                return cmdline[ind_port + 1]
            except (IndexError, ValueError):
                pass
        return "N/A"

    def is_valid_process(proc):
        """Check if process is a valid Mechanical instance."""
        valid_status = proc.status() in [
            psutil.STATUS_RUNNING,
            psutil.STATUS_IDLE,
            psutil.STATUS_SLEEPING,
        ]
        name_lower = proc.name().lower()
        cmdline_str = " ".join(proc.cmdline()).lower()

        # Check for Mechanical process indicators
        is_mechanical = (
            "ansyswbu" in name_lower
            or "mechanical" in name_lower
            or "ansys mechanical" in cmdline_str
            or "ansys-mechanical" in cmdline_str
        )

        return valid_status and is_mechanical

    for proc in psutil.process_iter():
        try:
            if is_valid_process(proc):
                # Check if it's a main process or child
                if len(proc.children(recursive=True)) < 2:
                    proc.ansys_instance = False
                else:
                    proc.ansys_instance = True
                mechanical_instances.append(proc)

        except (psutil.NoSuchProcess, psutil.ZombieProcess, psutil.AccessDenied):
            continue

    # Configure output columns
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
    for each_p in mechanical_instances:
        if instances and not each_p.ansys_instance:
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


def get_info(mechanical: "Mechanical") -> dict[str, str | dict[str, Any]]:
    """
    Get information from the Mechanical instance.

    Parameters
    ----------
    mechanical : Mechanical
        Mechanical instance.

    Returns
    -------
    dict[str, str | dict[str, Any]]
        Dictionary containing Mechanical information.
    """
    info: dict[str, str | dict[str, Any]] = {}

    # Basic connection information
    try:
        info["connection"] = {
            "version": mechanical.version,
            "project_directory": str(mechanical.project_directory),
            "is_alive": mechanical.is_alive,
            "name": mechanical.name if hasattr(mechanical, "name") else "N/A",
            "busy": mechanical.busy if hasattr(mechanical, "busy") else False,
            "exited": mechanical.exited if hasattr(mechanical, "exited") else False,
        }
    except Exception as e:
        logger.warning(f"Error extracting connection info: {e}")
        info["connection"] = {"error": str(e)}

    # Product information
    try:
        product_info = mechanical.get_product_info()
        info["product_info"] = {
            "raw": product_info if product_info else "N/A",
        }
    except Exception as e:
        logger.warning(f"Error extracting product info: {e}")
        info["product_info"] = {"error": str(e)}

    # Try to get model information via script
    try:
        script = """
import json
model_info = {}

# Get Project info
project = ExtAPI.DataModel.Project
model_info['product_version'] = project.ProductVersion

# Get Model name
model = Model
model_info['model_name'] = model.Name if hasattr(model, 'Name') else 'N/A'

json.dumps(model_info)
"""
        result = mechanical.run_python_script(script)
        if result:
            import json

            model_data = json.loads(result)
            info["model"] = model_data
    except Exception as e:
        logger.warning(f"Error extracting model info via script: {e}")
        info["model"] = {"error": str(e)}

    return info
