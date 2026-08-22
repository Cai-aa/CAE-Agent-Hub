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

"""Unit tests for :mod:`ansys.lumerical.mcp.contexts`.

These exercise the pure-Python content layer (no FastMCP / no
subprocess). They lock the topic -> anchor-string mapping so accidental
edits that drop a key section cause a test failure instead of silently
shipping a degraded guideline.
"""

from __future__ import annotations

import pytest

from ansys.lumerical.mcp.contexts import (
    _CONTENT_MAP,
    GuidelinesContent,
    get_guidelines_for,
    get_guidelines_for_fdtd_boundary_conditions,
    get_guidelines_for_fdtd_far_field_and_grating,
    get_guidelines_for_fdtd_mesh_and_convergence,
    get_guidelines_for_fdtd_monitors_and_field_extraction,
    get_guidelines_for_fdtd_run_and_results,
    get_guidelines_for_fdtd_source_types,
    get_guidelines_for_fdtd_sources_monitors,
    get_guidelines_for_fdtd_workflow,
    get_guidelines_for_fdtd_workflow_example,
    get_guidelines_for_geometry,
    get_guidelines_for_interconnect_commands,
    get_guidelines_for_interconnect_simulation,
    get_guidelines_for_interconnect_workflow,
    get_guidelines_for_materials,
    get_guidelines_for_mode_eme_workflow,
    get_guidelines_for_mode_fde_results,
    get_guidelines_for_mode_fde_workflow,
    get_guidelines_for_mode_varfdtd_workflow,
    get_guidelines_for_nested_sweeps,
    get_guidelines_for_s_parameter_sweep,
    get_guidelines_for_sweeps,
    get_guidelines_for_workflow,
)

# Per-topic byte cap: each guideline topic ships its full markdown
# verbatim through the ``get_guidelines_for`` MCP tool (no truncation),
# and that markdown becomes part of the agent's input context for every
# subsequent LLM turn. We cap each topic to keep them focused -- a
# guideline that has grown to multiple pages of text is almost always
# better split (see how ``fdtd_workflow_example`` was extracted from
# ``fdtd_workflow``). Some MCP clients have also been reported to
# handle very large tool responses poorly (see e.g.
# https://forum.cursor.com/t/mcp-server-message-too-long/52724), so the
# cap doubles as a defensive guard.
#
# 12 kB raw is roughly 3-4 pages of dense markdown, which is plenty for
# one focused topic. Bump cautiously; the right answer for "this topic
# wants more content" is usually to split it rather than relax the cap.
_MAX_TOPIC_BYTES = 12000

# ---------------------------------------------------------------------------
# Topic -> anchor strings that MUST appear in the returned markdown.
#
# Each anchor is taken from a section header or call-out that is the
# reason the topic exists. If one of these disappears we want to know
# before the regression reaches a user.
# ---------------------------------------------------------------------------
_TOPIC_ANCHORS: dict[str, tuple[str, ...]] = {
    "workflow": (
        "# Lumerical MCP Workflow",
        "## Workflow Order",
        "## Execution Model",
        "## Printed JSON Is a Snapshot",
        "## Snippet Structure",
        "## Chunked Workflow",
        "## Parameter Management",
        "## Running Simulations",
        "## Plot Theme",
        "## Critical Instructions: Do NOT Make Assumptions",
        "## Critical Instructions: Do NOT Invent or Re-run",
        "interconnect_workflow",
        "mode_fde_workflow",
        "mode_eme_workflow",
        "notes",
        "_lum_get",
        "_lum_print_json",
        "open_session",
        "SI units",
        "FDTD",
        "MODE",
        "INTERCONNECT",
        "pic",
        '"turbo"',
        '"coolwarm"',
        "fdtd_run_and_results",
    ),
    "sweeps": (
        "# Lumerical Parametric Sweeps",
        "addsweep",
        "setsweep",
        "getsweep",
        "addsweepparameter",
        "removesweepparameter",
        "runsweep",
        "getsweepresult",
        "deletesweep",
        '"type"',
        '"number of points"',
        "s_parameter_sweep",
    ),
    "pic": (
        "# PIC Simulation Basics",
        "PML",
        "0.5",
        "1`` times the simulation wavelength",
        "substrate",
        "TE/TM",
        "waveguide",
        "FEEM",
    ),
    "nested_sweeps": (
        "# Lumerical Nested Sweeps",
        "insertsweep",
        "inner sweep",
        "outer sweep",
        "all combinations",
        "getsweepresult",
        "result name only",
        "top-level sweep only",
        "Do not separately run the inner sweep",
    ),
    "fdtd_workflow": (
        "# FDTD Workflow",
        "## Disambiguation Defaults",
        "z-normal",
        "XY",
        "## PML Boundary Extension",
        "## FDTD Build Stages",
        "addfdtd",
        "fdtd.run()",
        "workflow",
        "fdtd_workflow_example",
        "geometry",
        "materials",
    ),
    "fdtd_workflow_example": (
        "# FDTD Workflow: Worked Example",
        "Pre-Flight",
        "mesh_accuracy",
        "save_path",
        "Step 1",
        "Step 7",
        "fundamental TE mode",
    ),
    "materials": (
        "# Materials",
        "FDTD",
        "MODE",
        "addmaterial",
        "setmaterial",
        "Anisotropic Materials",
        "Anisotropy",
    ),
    "geometry": (
        "# Geometry",
        "Dictionary-Based",
        "addrect",
        "FDTD",
        "MODE",
        "Property-Name Conventions",
        "GDS",
        "Layer Builder",
        "addlayerbuilder",
        "loadgdsfile",
        "loadprocessfile",
        '"first axis"',
    ),
    "fdtd_sources_monitors": (
        "# FDTD Sources and Monitors",
        "setglobalsource",
        "setglobalmonitor",
        "addport",
        "addmode",
    ),
    "fdtd_run_and_results": (
        "# FDTD Run and Results",
        "## Running an FDTD Simulation",
        "### Solver / Resource / GPU Arguments",
        "For **2D FDTD**, prefer ``CPU`` instead of ``GPU``.",
        "### Run Once",
        "## Read the Error Message Before Changing the Model",
        "Datasets Are Dicts",
        "_lum_print_json",
        "getresult",
        "Per-Port S Versus Full S-Matrix",
        "is not a result provider",
        "FDTD::ports::<port_name>",
        "switchtolayout",
        'fdtd.run("FDTD", "GPU")',
        "Cloud Burst",
    ),
    "s_parameter_sweep": (
        "# S-Parameter Matrix Sweep (FDTD and MODE)",
        "addsweep(3)",
        "runsweep",
        "getsweepresult",
        "S matrix",
        "auto symmetry",
        "exportsweep",
        "Touchstone",
        "Y-Branch",
    ),
    "mode_fde_workflow": (
        "# MODE FDE Workflow",
        "## When To Use FDE",
        "## MODE FDE Build Stages",
        "addfde()",
        'setnamed("FDE",',
        "bent waveguide",
        "bend radius",
        "calculate group index",
        "pre-run setup file",
        "mode_fde_results",
    ),
    "mode_fde_results": (
        "# MODE FDE Results",
        "## Solving Modes",
        "findmodes()",
        "selectmode(...)",
        'setanalysis("property", value)',
        'getanalysis("property")',
        "frequencysweep()",
        "FDE::data::mode1",
        "FDE::data::frequencysweep",
        "## Common Result Fields",
        "getdata()",
        "TE polarization fraction",
        "ng",
        "## TE/TM Classification",
        "highest-neff",
    ),
    "mode_eme_workflow": (
        "# MODE EME Workflow",
        "## When To Use EME",
        "## MODE EME Build Stages",
        "## Layout Mode Versus Analysis Mode",
        "emepropagate()",
        "emesweep()",
        "## EME Analysis Commands",
        'setemeanalysis("property", value)',
        'getemeanalysis("property")',
        'getemesweep("S")',
        'exportemesweep("s_param", "touchstone")',
        "group spans",
        "user s matrix",
        "power normalized user s matrix",
        "switchtolayout()",
    ),
    "mode_varfdtd_workflow": (
        "# MODE varFDTD Workflow",
        "## When To Use varFDTD",
        "## Recommended Workflow",
        "2.5D effective-index",
        "## Information Required Before Setup",
        "## Effective Index Settings",
        "slab-mode position",
        "narrowband",
        "broadband",
        "import source and port",
        "effective index monitor",
        "clamping to",
        "simulation time",
        "## Validation And Physicality Checks",
    ),
    "fdtd_boundary_conditions": (
        "# FDTD Boundary Conditions",
        "## PML",
        "Standard",
        "Stabilized",
        "Steep Angle",
        "## Symmetric",
        "## Periodic",
        "## Bloch",
        "BFAST",
    ),
    "fdtd_mesh_and_convergence": (
        "# FDTD Mesh and Convergence",
        "## Global Mesh Accuracy",
        "## Conformal Mesh Refinement",
        "## Mesh Override Regions",
        "addmesh",
        "## Simulation Time and Auto-Shutoff",
        "auto shutoff min",
        "## Divergence Diagnostics",
    ),
    "fdtd_source_types": (
        "# FDTD Source Types",
        "## Decision Tree",
        "addplane",
        "addbfastplanewave",
        "addgaussian",
        "adddipole",
        "addtfsf",
        "addimportedsource",
    ),
    "fdtd_monitors_and_field_extraction": (
        "# FDTD Monitors and Field Extraction",
        "## Choosing a Monitor Type",
        "adddftmonitor",
        "addmodeexpansion",
        "## Override Global Monitor Settings",
        "## Reduce Before You Print",
        "_lum_print_json",
    ),
    "fdtd_far_field_and_grating": (
        "# FDTD Far-Field and Grating Projections",
        "## Far-Field Projection",
        "farfield3d",
        "farfieldexact",
        "## Grating Projection",
        "gratingn1",
        "gratingn2",
        "## NA / Angular Filtering",
    ),
    "interconnect_workflow": (
        "# INTERCONNECT Workflow",
        "Discover before configure",
        "lum_",
        "getports()",
        "description",
    ),
    "interconnect_simulation": (
        "# INTERCONNECT Simulation",
        "simulation input",
        "sequence length",
        "time window",
        "samples per bit",
        "measurement/BER",
        "sum/signal",
    ),
    "interconnect_commands": (
        "# INTERCONNECT Commands Reference",
        "getproperties()",
        "setnamed(element)",
        "ispropertyactive",
        "sum/signal",
        "measurement/BER",
        "Lumerical_dataset",
    ),
}


# ---------------------------------------------------------------------------
# Topic -> markdown
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("topic", list(_TOPIC_ANCHORS.keys()))
def test_get_guidelines_for_returns_non_empty_markdown(topic: str) -> None:
    text = get_guidelines_for(topic)  # type: ignore[arg-type]
    assert isinstance(text, str)
    assert text.strip(), f"{topic!r} returned empty content"
    # Topic must start with an H1 heading (markdown convention used in the module).
    assert text.lstrip().startswith("# "), f"{topic!r} did not start with an H1 heading"


@pytest.mark.parametrize("topic", list(_TOPIC_ANCHORS.keys()))
def test_get_guidelines_for_contains_expected_anchors(topic: str) -> None:
    text = get_guidelines_for(topic)  # type: ignore[arg-type]
    missing = [anchor for anchor in _TOPIC_ANCHORS[topic] if anchor not in text]
    assert not missing, f"{topic!r} guidance is missing required anchors: {missing!r}"


# ---------------------------------------------------------------------------
# _CONTENT_MAP shape
# ---------------------------------------------------------------------------


def test_content_map_keys_match_literal_topics() -> None:
    """The _CONTENT_MAP keys must match the GuidelinesContent Literal exactly.

    If they drift, FastMCP will happily accept a Literal value at the
    schema layer but ``get_guidelines_for`` will raise KeyError at call
    time -- exactly the kind of bug this test catches.
    """
    literal_topics = set(GuidelinesContent.__args__)  # type: ignore[attr-defined]
    map_topics = set(_CONTENT_MAP.keys())
    assert literal_topics == map_topics


def test_content_map_values_are_the_per_topic_functions() -> None:
    assert _CONTENT_MAP["workflow"] is get_guidelines_for_workflow
    assert _CONTENT_MAP["sweeps"] is get_guidelines_for_sweeps
    assert _CONTENT_MAP["nested_sweeps"] is get_guidelines_for_nested_sweeps
    assert _CONTENT_MAP["fdtd_workflow"] is get_guidelines_for_fdtd_workflow
    assert _CONTENT_MAP["fdtd_workflow_example"] is get_guidelines_for_fdtd_workflow_example
    assert _CONTENT_MAP["materials"] is get_guidelines_for_materials
    assert _CONTENT_MAP["geometry"] is get_guidelines_for_geometry
    assert _CONTENT_MAP["fdtd_sources_monitors"] is get_guidelines_for_fdtd_sources_monitors
    assert _CONTENT_MAP["fdtd_run_and_results"] is get_guidelines_for_fdtd_run_and_results
    assert _CONTENT_MAP["fdtd_boundary_conditions"] is get_guidelines_for_fdtd_boundary_conditions
    assert _CONTENT_MAP["fdtd_mesh_and_convergence"] is get_guidelines_for_fdtd_mesh_and_convergence
    assert _CONTENT_MAP["fdtd_source_types"] is get_guidelines_for_fdtd_source_types
    assert (
        _CONTENT_MAP["fdtd_monitors_and_field_extraction"]
        is get_guidelines_for_fdtd_monitors_and_field_extraction
    )
    assert (
        _CONTENT_MAP["fdtd_far_field_and_grating"] is get_guidelines_for_fdtd_far_field_and_grating
    )
    assert _CONTENT_MAP["s_parameter_sweep"] is get_guidelines_for_s_parameter_sweep
    assert _CONTENT_MAP["mode_fde_workflow"] is get_guidelines_for_mode_fde_workflow
    assert _CONTENT_MAP["mode_fde_results"] is get_guidelines_for_mode_fde_results
    assert _CONTENT_MAP["mode_eme_workflow"] is get_guidelines_for_mode_eme_workflow
    assert _CONTENT_MAP["mode_varfdtd_workflow"] is get_guidelines_for_mode_varfdtd_workflow
    assert _CONTENT_MAP["interconnect_workflow"] is get_guidelines_for_interconnect_workflow
    assert _CONTENT_MAP["interconnect_simulation"] is get_guidelines_for_interconnect_simulation
    assert _CONTENT_MAP["interconnect_commands"] is get_guidelines_for_interconnect_commands


# ---------------------------------------------------------------------------
# Per-topic byte cap: keep each topic focused so the agent's context
# window doesn't fill up with one verbose markdown blob.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("topic", list(_CONTENT_MAP.keys()))
def test_topic_fits_within_response_budget(topic: str) -> None:
    """Each topic's markdown must stay under ``_MAX_TOPIC_BYTES``.

    There is no truncation in :func:`get_guidelines_for`; the markdown
    ships verbatim and lands in the agent's input context for every
    subsequent LLM turn. This test is the gate that prevents a single
    topic from quietly growing into a multi-page document. The right
    response to a failure here is almost always to split the topic
    (see how ``fdtd_workflow_example`` was extracted from
    ``fdtd_workflow``), not to relax the cap.
    """
    raw_bytes = len(get_guidelines_for(topic).encode("utf-8"))  # type: ignore[arg-type]
    assert raw_bytes <= _MAX_TOPIC_BYTES, (
        f"{topic!r} guidance is {raw_bytes} bytes, over the "
        f"{_MAX_TOPIC_BYTES}-byte per-topic budget. Split the topic "
        f"(see fdtd_workflow / fdtd_workflow_example) or trim "
        f"non-essential content rather than raising the cap."
    )


# ---------------------------------------------------------------------------
# Failure paths
# ---------------------------------------------------------------------------


def test_get_guidelines_for_unknown_topic_raises_keyerror() -> None:
    """FastMCP enforces the Literal at the schema boundary; this guard
    documents what happens if someone bypasses that and calls the
    function directly with an unknown topic."""
    with pytest.raises(KeyError):
        get_guidelines_for("not_a_real_topic")  # type: ignore[arg-type]
