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

"""Toolset definitions for PyAnsys MCP service discovery.

Exposes the ``toolsets://definition`` MCP resource that groups every tool
registered on PyAEDT-MCP into logical, user-facing categories.
Each toolset entry follows the schema agreed across the Ansys MCP family:

``{"name": str, "description": str, "skill": str, "tools": list[str]}``

The catalogue is a pure discovery aid — it does not affect tool visibility,
gating, or runtime behavior. Visibility is still controlled by the existing
``REQUIRES_AEDT_TAG`` / ``aedt_tools`` / ``locked_connection`` tags applied
in :mod:`ansys.aedt.mcp.tools`.
"""

from typing import Any

from ansys.aedt.mcp import app

#: Master catalogue mapping every logical toolset to its metadata + tool list.
#: When you register a new tool with ``@app.tool``, add it to one of these
#: toolsets so it is discoverable through ``toolsets://definition``.
_TOOLSET_CATALOGUE: dict[str, dict[str, Any]] = {
    "lifecycle": {
        "description": (
            "Tools for installing, launching, connecting to, disconnecting "
            "from, and tearing down AEDT sessions."
        ),
        "skill": (
            "Call check_aedt_installed once at startup to confirm the AEDT "
            "binary is on disk. First call check_aedt_status before every "
            "workflow to see whether this MCP already has a live AEDT "
            "connection and to discover local AEDT sessions that can be "
            "attached. If multiple connectable sessions are reported, ask the "
            "user which session to connect to and include the option to open "
            "a new session instead. If one connectable session is reported, "
            "ask whether to connect to it or open a new instance. Prefer "
            "connect_to_aedt to attach to a running session (machine + gRPC "
            "port). Only use launch_aedt(confirm_new_session=True) after the "
            "user explicitly confirms a new instance is needed. If the user "
            "directly asks for a new instance or new AEDT session, skip the "
            "question and call launch_aedt(confirm_new_session=True). If the "
            "connected session has no open projects and the user asked for a "
            "specific solver such as Hfss or Maxwell3d, call create_design "
            "with the matching app_type. Call "
            "disconnect_from_aedt for a graceful detach "
            "and clear_aedt to fully release the AEDT process."
        ),
        "tools": [
            "check_aedt_installed",
            "check_aedt_status",
            "launch_aedt",
            "connect_to_aedt",
            "disconnect_from_aedt",
            "clear_aedt",
        ],
    },
    "project-management": {
        "description": (
            "Tools for opening, saving, listing, and creating AEDT projects and designs."
        ),
        "skill": (
            "Use list_projects to enumerate open AEDT projects, list_designs "
            "to enumerate designs in a project, open_project to load a "
            ".aedt/.aedtz file, save_project to persist changes, and "
            "create_design to add a new design (HFSS, Maxwell, Icepak, etc.) "
            "to the active project."
        ),
        "tools": [
            "list_projects",
            "list_designs",
            "open_project",
            "save_project",
            "create_design",
        ],
    },
    "simulation": {
        "description": ("Tools for configuring and running AEDT solver analyses."),
        "skill": (
            "Use analyze_design to run a configured setup/sweep on the "
            "active design. Use export_config to persist the current setup "
            "and sweep configuration for reproducibility or sharing."
        ),
        "tools": [
            "analyze_design",
            "export_config",
        ],
    },
    "scripting": {
        "description": (
            "Tools for executing arbitrary PyAEDT Python code or scripts "
            "against the live Desktop session."
        ),
        "skill": (
            "Use run_python_code to execute a short inline snippet "
            "(introspection, parameter tweaks, custom geometry). Use "
            "run_python_script to execute a full .py file from disk. Both "
            "share the same persistent Python session, so variables and "
            "imports defined in one call remain available in subsequent calls."
        ),
        "tools": [
            "run_python_code",
            "run_python_script",
        ],
    },
    "inspection": {
        "description": (
            "Tools for inspecting the active model, capturing screenshots, "
            "and reading PyAEDT runtime logs."
        ),
        "skill": (
            "Use get_model_info to retrieve a structured summary of the "
            "active design (solids, boundaries, materials, excitations). "
            "Use screenshot to capture the current 3D modeler view as a PNG "
            "for the user. Use get_pyaedt_logs to retrieve recent PyAEDT log "
            "lines when diagnosing failures."
        ),
        "tools": [
            "get_model_info",
            "screenshot",
            "get_pyaedt_logs",
        ],
    },
    "results": {
        "description": (
            "Tools for extracting and exporting solver results from a solved AEDT design."
        ),
        "skill": (
            "Use export_results after a successful analyze_design call to "
            "write field/network/parameter results to disk in a "
            "human-readable or post-processable format."
        ),
        "tools": [
            "export_results",
        ],
    },
    "guidelines": {
        "description": (
            "Reference tool for retrieving PyAEDT / AEDT scripting "
            "guidelines (workflow, HFSS, Maxwell, Icepak, Circuit, "
            "geometry, mesh, boundaries, postprocessing, parametric)."
        ),
        "skill": (
            "Call get_guidelines_for once per topic before generating "
            "PyAEDT code or invoking a workflow tool. It returns the "
            "authoritative scripting patterns and best practices for the "
            "requested topic. This tool is only registered when the "
            "server is launched with --include-context-tools."
        ),
        "tools": [
            "get_guidelines_for",
        ],
    },
}


def _build_toolsets() -> list[dict[str, Any]]:
    """Return the toolset catalogue as the list[dict] payload expected by clients."""
    return [
        {
            "name": name,
            "description": entry["description"],
            "skill": entry["skill"],
            "tools": list(entry["tools"]),
        }
        for name, entry in _TOOLSET_CATALOGUE.items()
    ]


@app.resource(
    "toolsets://definition",
    name="toolsets_definition",
    description="Toolset definitions for PyAnsys MCP service discovery.",
    mime_type="application/json",
)
def get_toolsets() -> list[dict[str, Any]]:
    """Get toolset definitions for PyAnsys MCP service discovery."""
    return _build_toolsets()
