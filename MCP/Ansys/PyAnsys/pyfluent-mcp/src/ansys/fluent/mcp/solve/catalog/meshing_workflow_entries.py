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

"""Synthetic ApiEntry catalogue for classic PyFluent meshing workflows.

These entries are injected into the meshing-session :class:`ApiIndex` so
that BM25 retrieval surfaces the correct ``workflow.TaskObject[...]``
idiom — including default argument keys and constant string values — for
every standard meshing task, rather than only the low-level generated
schema paths that live in ``ansys/fluent/core/generated/api_tree/api_objects.json``.

Source of truth
---------------
* ``D:/Repos/pyfluent/tests/test_meshing_workflow.py``  (watertight + 2D +
  fault-tolerant workflow patterns)

Adding a new task
-----------------
Add an :func:`_entry` call to :func:`get_meshing_workflow_entries`.  No
other changes are needed; ``get_meshing_api_index`` already injects
everything this function returns.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from ansys.fluent.mcp.solve.catalog.index import ApiEntry

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tok(text: str) -> list[str]:
    """Tokenise *text* identically to :func:`index._tokenise`."""
    return _TOKEN_RE.findall(text.lower())


def _entry(
    *,
    path: str,
    kind: str,
    raw: str,
    tokens_text: str,
    doc: str = "",
) -> "ApiEntry":
    """Build a synthetic :class:`ApiEntry` for a meshing workflow construct.

    Parameters
    ----------
    path:
        Unique dotted path used as the index key.  Must not collide with
        real ``api_objects.json`` entries.  Use the convention
        ``workflow.task_object.<snake_task_name>`` for tasks and
        ``workflow.<snake_command>`` for workflow-level commands.
    kind:
        One of ``"WorkflowTask"``, ``"WorkflowCommand"``.
    raw:
        Canonical runnable code snippet returned to the agent/LLM as the
        ``raw`` field.  User-supplied values are shown as ``<placeholders>``.
    tokens_text:
        Space-separated words used for BM25 scoring.  Include task display
        name words, argument key words, and important constant strings.
    doc:
        Human-readable description (optional; used for diagnostics only).
    """
    from ansys.fluent.mcp.solve.catalog.index import ApiEntry

    return ApiEntry(
        raw=raw,
        path=path,
        kind=kind,
        session="meshing_session",
        tokens=_tok(tokens_text),
        doc=doc,
    )


# ---------------------------------------------------------------------------
# Watertight Geometry workflow — full task sequence
# ---------------------------------------------------------------------------

_WT_INIT = _entry(
    path="workflow.initialize_watertight_geometry",
    kind="WorkflowCommand",
    raw=(
        'meshing.workflow.InitializeWorkflow(WorkflowType="Watertight Geometry")\n'
        '# Access tasks via  meshing.workflow.TaskObject["<Task Name>"]'
    ),
    tokens_text=("initialize workflow watertight geometry setup classic 3d solid"),
    doc="Initialize the Watertight Geometry meshing workflow.",
)

_WT_IMPORT_GEOMETRY = _entry(
    path="workflow.task_object.import_geometry",
    kind="WorkflowTask",
    raw=(
        'workflow.TaskObject["Import Geometry"].Arguments.set_state({\n'
        '    "FileName": r"<path/to/geometry.scdoc>",\n'
        '    "LengthUnit": "mm",  # "mm" | "in" | "cm" | "m" | "ft" | "um"\n'
        "})\n"
        'workflow.TaskObject["Import Geometry"].Execute()'
    ),
    tokens_text=(
        "import geometry cad file filename length unit mm in cm m ft um "
        "inches millimeter centimeter meter feet scdoc pmdb fmd agdb step iges"
    ),
    doc="Task: Import Geometry.  Set FileName and LengthUnit then Execute.",
)

_WT_ADD_LOCAL_SIZING = _entry(
    path="workflow.task_object.add_local_sizing",
    kind="WorkflowTask",
    raw=(
        "# Simplest form — just add a child and execute:\n"
        'workflow.TaskObject["Add Local Sizing"].AddChildToTask()\n'
        'workflow.TaskObject["Add Local Sizing"].Execute()\n'
        "\n"
        "# With explicit BOI / Edge / Curvature control:\n"
        'workflow.TaskObject["Add Local Sizing"].Arguments.set_state({\n'
        '    "BOIControlName": "boi_1",\n'
        '    "BOIExecution": "Body Of Influence",  # "Body Of Influence" |\n'
        '    # "Edge Size" | "Curvature"\n'
        '    "BOISize": 0.1,\n'
        '    "BOIZoneorLabel": "label",\n'
        "})\n"
        'workflow.TaskObject["Add Local Sizing"].AddChildAndUpdate(DeferUpdate=False)'
    ),
    tokens_text=(
        "add local sizing boi body influence edge curvature size control "
        "refinement face zone label draw size"
    ),
    doc="Task: Add Local Sizing.  AddChildToTask then Execute, or set BOI arguments.",
)

_WT_GENERATE_SURFACE_MESH = _entry(
    path="workflow.task_object.generate_surface_mesh",
    kind="WorkflowTask",
    raw=(
        'workflow.TaskObject["Generate the Surface Mesh"].Arguments.set_state({\n'
        '    "CFDSurfaceMeshControls": {\n'
        '        "MaxSize": 0.1,          # maximum surface cell size\n'
        '        "MinSize": 0.01,         # minimum surface cell size\n'
        '        "SizeFunctions": "Curvature",  # "Curvature" | "Proximity" | "Fixed"\n'
        "    },\n"
        "})\n"
        'workflow.TaskObject["Generate the Surface Mesh"].Execute()'
    ),
    tokens_text=(
        "generate surface mesh max size min size curvature proximity fixed "
        "cfd surface controls maximum minimum"
    ),
    doc=(
        "Task: Generate the Surface Mesh.  CFDSurfaceMeshControls: MaxSize, MinSize, SizeFunctions."
    ),
)

_WT_DESCRIBE_GEOMETRY = _entry(
    path="workflow.task_object.describe_geometry",
    kind="WorkflowTask",
    raw=(
        'describe_geo = workflow.TaskObject["Describe Geometry"]\n'
        "describe_geo.UpdateChildTasks(SetupTypeChanged=False)\n"
        "describe_geo.Arguments.set_state({\n"
        '    "SetupType": "The geometry consists of only fluid regions with no voids",\n'
        '    # Alternative: "The geometry consists of both fluid and solid regions"\n'
        "})\n"
        "describe_geo.UpdateChildTasks(SetupTypeChanged=True)\n"
        "describe_geo.Execute()"
    ),
    tokens_text=(
        "describe geometry setup type fluid solid regions voids only "
        "update child tasks setup type changed"
    ),
    doc="Task: Describe Geometry.  SetupType: fluid-only vs fluid+solid.",
)

_WT_UPDATE_BOUNDARIES = _entry(
    path="workflow.task_object.update_boundaries",
    kind="WorkflowTask",
    raw=(
        'workflow.TaskObject["Update Boundaries"].Arguments.set_state({\n'
        '    "BoundaryLabelList": ["wall-inlet"],\n'
        '    "BoundaryLabelTypeList": ["wall"],       # "wall" | "velocity-inlet" |\n'
        '    # "pressure-outlet" | "symmetry" | "interior"\n'
        '    "OldBoundaryLabelList": ["wall-inlet"],\n'
        '    "OldBoundaryLabelTypeList": ["velocity-inlet"],\n'
        "})\n"
        'workflow.TaskObject["Update Boundaries"].Execute()'
    ),
    tokens_text=(
        "update boundaries boundary label list type wall velocity inlet "
        "pressure outlet symmetry interior zone rename retype"
    ),
    doc=(
        "Task: Update Boundaries.  "
        "Set BoundaryLabelList, BoundaryLabelTypeList, OldBoundaryLabelList, "
        "OldBoundaryLabelTypeList."
    ),
)

_WT_UPDATE_REGIONS = _entry(
    path="workflow.task_object.update_regions",
    kind="WorkflowTask",
    raw=(
        'workflow.TaskObject["Update Regions"].Execute()\n'
        "# Optionally override region types before executing:\n"
        '# workflow.TaskObject["Update Regions"].Arguments.set_state({\n'
        '#     "FarFieldRegionList": [...],\n'
        '#     "FluidRegionList": [...],\n'
        "# })"
    ),
    tokens_text="update regions fluid solid far field region list zone type",
    doc="Task: Update Regions.  Usually just Execute() after Update Boundaries.",
)

_WT_ADD_BOUNDARY_LAYERS = _entry(
    path="workflow.task_object.add_boundary_layers",
    kind="WorkflowTask",
    raw=(
        'add_bl = workflow.TaskObject["Add Boundary Layers"]\n'
        "add_bl.AddChildToTask()\n"
        "add_bl.InsertCompoundChildTask()\n"
        "# child task name defaults to e.g. 'smooth-transition_1'\n"
        'workflow.TaskObject["smooth-transition_1"].Arguments.set_state({\n'
        '    "BLControlName": "smooth-transition_1",\n'
        '    "OffsetMethodType": "smooth-transition",  # "smooth-transition" |\n'
        '    # "uniform" | "aspect-ratio" | "last-ratio"\n'
        '    "NumberOfLayers": 5,\n'
        '    "FirstLayerHeight": 0.001,  # relevant for "uniform" / "last-ratio"\n'
        "})\n"
        "add_bl.Arguments = {}\n"
        "add_bl.Execute()"
    ),
    tokens_text=(
        "add boundary layers bl inflation smooth transition uniform aspect ratio "
        "last ratio first layer height number layers offset method prism insert compound"
    ),
    doc=(
        "Task: Add Boundary Layers.  "
        "AddChildToTask, InsertCompoundChildTask, set BLControlName / "
        "OffsetMethodType / NumberOfLayers, then Execute."
    ),
)

_WT_GENERATE_VOLUME_MESH = _entry(
    path="workflow.task_object.generate_volume_mesh",
    kind="WorkflowTask",
    raw=(
        'workflow.TaskObject["Generate the Volume Mesh"].Arguments.set_state({\n'
        '    "VolumeFill": "poly-hexcore",  # "poly-hexcore" | "poly" | "tet" | "hexcore"\n'
        '    "VolumeFillControls": {\n'
        '        "HexMaxCellLength": 0.3,  # maximum hex cell edge length (poly-hexcore)\n'
        "    },\n"
        "})\n"
        'workflow.TaskObject["Generate the Volume Mesh"].Execute()'
    ),
    tokens_text=(
        "generate volume mesh poly hexcore tet polyhedra hexahedral fill "
        "volume fill controls hex max cell length"
    ),
    doc=("Task: Generate the Volume Mesh.  VolumeFill: poly-hexcore | poly | tet | hexcore."),
)

# ---------------------------------------------------------------------------
# Post-workflow commands
# ---------------------------------------------------------------------------

_CHECK_MESH = _entry(
    path="workflow.check_mesh",
    kind="WorkflowCommand",
    raw="meshing.meshing.check_mesh()",
    tokens_text="check mesh quality meshing verify validate",
    doc="Check mesh quality in meshing mode after volume mesh generation.",
)

_SWITCH_TO_SOLVER = _entry(
    path="workflow.switch_to_solver",
    kind="WorkflowCommand",
    raw=(
        "# Switch from meshing mode to solver mode after meshing is complete:\n"
        "solver = meshing.switch_to_solver()"
    ),
    tokens_text="switch to solver solution mode from meshing transition",
    doc="Switch from meshing mode to solver mode.",
)

# ---------------------------------------------------------------------------
# Fault-tolerant Meshing workflow — init
# ---------------------------------------------------------------------------

_FT_INIT = _entry(
    path="workflow.initialize_fault_tolerant",
    kind="WorkflowCommand",
    raw=(
        'meshing.workflow.InitializeWorkflow(WorkflowType="Fault-tolerant Meshing")\n'
        '# Access tasks via  meshing.workflow.TaskObject["<Task Name>"]'
    ),
    tokens_text="initialize workflow fault tolerant meshing dirty cad repair",
    doc="Initialize the Fault-tolerant Meshing workflow.",
)

# ---------------------------------------------------------------------------
# 2D Meshing workflow tasks
# ---------------------------------------------------------------------------

_2D_INIT = _entry(
    path="workflow.initialize_2d_meshing",
    kind="WorkflowCommand",
    raw=(
        'meshing.workflow.InitializeWorkflow(WorkflowType="2D Meshing")\n'
        '# Access tasks via  meshing.workflow.TaskObject["<Task Name>"]'
    ),
    tokens_text="initialize workflow 2d meshing two dimensional airfoil planar",
    doc="Initialize the 2D Meshing workflow.",
)

_2D_LOAD_CAD_GEOMETRY = _entry(
    path="workflow.task_object.load_cad_geometry_2d",
    kind="WorkflowTask",
    raw=(
        'workflow.TaskObject["Load CAD Geometry"].Arguments.set_state({\n'
        '    "FileName": r"<path/to/geometry.fmd>",\n'
        '    "LengthUnit": "mm",\n'
        '    "Refaceting": {"Refacet": False},\n'
        "})\n"
        'workflow.TaskObject["Load CAD Geometry"].Execute()'
    ),
    tokens_text="load cad geometry 2d filename length unit refaceting fmd",
    doc="Task: Load CAD Geometry (2D Meshing workflow).",
)

_2D_DEFINE_GLOBAL_SIZING = _entry(
    path="workflow.task_object.define_global_sizing",
    kind="WorkflowTask",
    raw=(
        'workflow.TaskObject["Define Global Sizing"].Arguments.set_state({\n'
        '    "CurvatureNormalAngle": 20,\n'
        '    "MaxSize": 2000,\n'
        '    "MinSize": 5,\n'
        '    "SizeFunctions": "Curvature",  # "Curvature" | "Proximity" | "Fixed"\n'
        "})\n"
        'workflow.TaskObject["Define Global Sizing"].Execute()'
    ),
    tokens_text=("define global sizing curvature normal angle max size min size size functions 2d"),
    doc="Task: Define Global Sizing (2D Meshing workflow).",
)

_2D_ADD_BOUNDARY_LAYERS = _entry(
    path="workflow.task_object.add_2d_boundary_layers",
    kind="WorkflowTask",
    raw=(
        'workflow.TaskObject["Add 2D Boundary Layers"].Arguments.set_state({\n'
        '    "AddChild": "yes",\n'
        '    "BLControlName": "smooth-transition_1",\n'
        '    "NumberOfLayers": 5,\n'
        '    "OffsetMethodType": "smooth-transition",  # "smooth-transition" |\n'
        '    # "uniform" | "aspect-ratio"\n'
        "})\n"
        'workflow.TaskObject["Add 2D Boundary Layers"].AddChildAndUpdate(DeferUpdate=False)'
    ),
    tokens_text=(
        "add 2d boundary layers smooth transition uniform aspect ratio offset method number layers"
    ),
    doc="Task: Add 2D Boundary Layers (2D Meshing workflow).",
)

_2D_EXPORT_MESH = _entry(
    path="workflow.task_object.export_fluent_2d_mesh",
    kind="WorkflowTask",
    raw=(
        'workflow.TaskObject["Export Fluent 2D Mesh"].Arguments.set_state({\n'
        '    "FileName": r"case1.msh.h5",\n'
        "})\n"
        'workflow.TaskObject["Export Fluent 2D Mesh"].Execute()'
    ),
    tokens_text="export fluent 2d mesh filename msh h5 save write",
    doc="Task: Export Fluent 2D Mesh (2D Meshing workflow).",
)


# ---------------------------------------------------------------------------
# Public catalogue
# ---------------------------------------------------------------------------


def get_meshing_workflow_entries() -> "list[ApiEntry]":
    """Return all synthetic ApiEntry records for classic meshing workflows.

    :meth:`get_meshing_api_index` passes this list to :class:`ApiIndex`
    via ``extra_entries``.  The entries are injected before BM25 statistics
    are built, so they participate fully in ranking alongside the real
    ``api_objects.json`` entries.

    Returns
    -------
    list[ApiEntry]
        Synthetic entries for Watertight Geometry, Fault-tolerant Meshing,
        and 2D Meshing workflow tasks.
    """
    return [
        # Watertight Geometry — full task sequence
        _WT_INIT,
        _WT_IMPORT_GEOMETRY,
        _WT_ADD_LOCAL_SIZING,
        _WT_GENERATE_SURFACE_MESH,
        _WT_DESCRIBE_GEOMETRY,
        _WT_UPDATE_BOUNDARIES,
        _WT_UPDATE_REGIONS,
        _WT_ADD_BOUNDARY_LAYERS,
        _WT_GENERATE_VOLUME_MESH,
        # Post-workflow
        _CHECK_MESH,
        _SWITCH_TO_SOLVER,
        # Fault-tolerant Meshing
        _FT_INIT,
        # 2D Meshing
        _2D_INIT,
        _2D_LOAD_CAD_GEOMETRY,
        _2D_DEFINE_GLOBAL_SIZING,
        _2D_ADD_BOUNDARY_LAYERS,
        _2D_EXPORT_MESH,
    ]


__all__ = ["get_meshing_workflow_entries"]
