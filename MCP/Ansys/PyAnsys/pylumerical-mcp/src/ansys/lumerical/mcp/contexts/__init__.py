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

"""Curated Lumerical scripting guidance returned by ``get_guidelines_for``.

This package powers a single MCP tool, :func:`get_guidelines_for`, that the
LLM is expected to call BEFORE generating any Lumerical Python (lumapi)
code. It returns authoritative markdown for a chosen topic so the model
does not have to rely on whatever priors it picked up at training time.

Topic taxonomy:

- ``workflow`` -- product-agnostic execution model, snippet structure,
  chunking, parameter management, and the do-not-assume / do-not-invent
  rules. Applies to every Lumerical product. Lives in
  :mod:`ansys.lumerical.mcp.contexts.general`.
- ``sweeps`` -- product-agnostic lifecycle of analysis tasks created
  with ``addsweep`` (parameter sweep, optimization, Monte Carlo,
  S-parameter, corner sweep). Applies to FDTD, MODE, and
  INTERCONNECT. Lives in :mod:`ansys.lumerical.mcp.contexts.sweeps`.
- ``pic`` -- shared guided-wave photonic simulation hygiene for
  optical elements: PML extension of continuing guided structures,
  mode-solver / port span padding, and avoiding accidental
  substrate-mode selection. Applies to FDTD, MODE, and FEEM. Lives in
  :mod:`ansys.lumerical.mcp.contexts.pic`.
- ``nested_sweeps`` -- product-agnostic hierarchical sweep guidance:
  build the inner sweep first, wrap it with ``insertsweep``, then run
  the outer parent sweep for all parameter combinations. Lives in
  :mod:`ansys.lumerical.mcp.contexts.sweeps`.
- ``materials`` and ``geometry`` -- shared between FDTD and MODE (and,
  for ``geometry``, DEVICE), since those products share the same
  material database and layout-object lumapi calls. Live in
  :mod:`ansys.lumerical.mcp.contexts.materials` and
  :mod:`ansys.lumerical.mcp.contexts.geometry`.
- ``s_parameter_sweep`` -- shared FDTD and MODE recipe for the
  ``addsweep(3)`` S-parameter matrix sweep, with a Y-branch worked
  example. Lives in
  :mod:`ansys.lumerical.mcp.contexts.s_parameter_sweep`.
- ``fdtd_workflow``, ``fdtd_workflow_example``,
  ``fdtd_sources_monitors``, ``fdtd_run_and_results``,
  ``fdtd_boundary_conditions``, ``fdtd_mesh_and_convergence``,
  ``fdtd_source_types``, ``fdtd_monitors_and_field_extraction``,
  ``fdtd_far_field_and_grating`` -- FDTD-specific topics split
  into a build/setup half (``fdtd_workflow`` +
  ``fdtd_workflow_example`` + ``fdtd_sources_monitors``), a
  run/results half (``fdtd_run_and_results``), and four deep-dive
  topics on boundary conditions, mesh/convergence, non-port
  source types, monitors and field extraction, and
  far-field/grating projections, all owned by
  :mod:`ansys.lumerical.mcp.contexts.fdtd`.
- ``interconnect_workflow`` and ``interconnect_commands`` --
  INTERCONNECT-specific topics covering build/setup workflow and
  command reference, both owned by
  :mod:`ansys.lumerical.mcp.contexts.interconnect`.
- ``device_workflow``, ``device_materials``, and
  ``device_simulation_region`` -- finite-element IDE (DEVICE)
  topics covering the shared HEAT / CHARGE / FEEM / DGTD build/run
  workflow, model-material creation, and simulation-region setup.
  Owned by :mod:`ansys.lumerical.mcp.contexts.device`.
- ``mode_fde_workflow``, ``mode_fde_results``, and
  ``mode_eme_workflow`` and ``mode_varfdtd_workflow`` -- MODE-specific
  topics covering FDE setup, FDE solve/results, EME setup/analysis
  workflow, and varFDTD setup/run guidance, all owned by
  :mod:`ansys.lumerical.mcp.contexts.mode`.
- The system prompt (:mod:`ansys.lumerical.mcp.prompts`) is itself
  product-agnostic and does not need to change for new product
  topics.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from ansys.lumerical.mcp.contexts.device import (
    get_guidelines_for_device_materials,
    get_guidelines_for_device_simulation_region,
    get_guidelines_for_device_workflow,
)
from ansys.lumerical.mcp.contexts.fdtd import (
    get_guidelines_for_fdtd_boundary_conditions,
    get_guidelines_for_fdtd_far_field_and_grating,
    get_guidelines_for_fdtd_mesh_and_convergence,
    get_guidelines_for_fdtd_monitors_and_field_extraction,
    get_guidelines_for_fdtd_run_and_results,
    get_guidelines_for_fdtd_source_types,
    get_guidelines_for_fdtd_sources_monitors,
    get_guidelines_for_fdtd_workflow,
    get_guidelines_for_fdtd_workflow_example,
)
from ansys.lumerical.mcp.contexts.general import get_guidelines_for_workflow
from ansys.lumerical.mcp.contexts.geometry import get_guidelines_for_geometry
from ansys.lumerical.mcp.contexts.interconnect import (
    get_guidelines_for_interconnect_commands,
    get_guidelines_for_interconnect_simulation,
    get_guidelines_for_interconnect_workflow,
)
from ansys.lumerical.mcp.contexts.materials import get_guidelines_for_materials
from ansys.lumerical.mcp.contexts.mode import (
    get_guidelines_for_mode_eme_workflow,
    get_guidelines_for_mode_fde_results,
    get_guidelines_for_mode_fde_workflow,
    get_guidelines_for_mode_varfdtd_workflow,
)
from ansys.lumerical.mcp.contexts.pic import get_guidelines_for_pic
from ansys.lumerical.mcp.contexts.s_parameter_sweep import (
    get_guidelines_for_s_parameter_sweep,
)
from ansys.lumerical.mcp.contexts.sweeps import (
    get_guidelines_for_nested_sweeps,
    get_guidelines_for_sweeps,
)
from ansys.lumerical.mcp.server import app

GuidelinesContent = Literal[
    "workflow",
    "sweeps",
    "pic",
    "nested_sweeps",
    "fdtd_workflow",
    "fdtd_workflow_example",
    "materials",
    "geometry",
    "fdtd_sources_monitors",
    "fdtd_run_and_results",
    "fdtd_boundary_conditions",
    "fdtd_mesh_and_convergence",
    "fdtd_source_types",
    "fdtd_monitors_and_field_extraction",
    "fdtd_far_field_and_grating",
    "s_parameter_sweep",
    "mode_fde_workflow",
    "mode_fde_results",
    "mode_eme_workflow",
    "mode_varfdtd_workflow",
    "interconnect_workflow",
    "interconnect_simulation",
    "interconnect_commands",
    "device_workflow",
    "device_materials",
    "device_simulation_region",
]


_CONTENT_MAP: dict[str, Callable[[], str]] = {
    "workflow": get_guidelines_for_workflow,
    "sweeps": get_guidelines_for_sweeps,
    "pic": get_guidelines_for_pic,
    "nested_sweeps": get_guidelines_for_nested_sweeps,
    "fdtd_workflow": get_guidelines_for_fdtd_workflow,
    "fdtd_workflow_example": get_guidelines_for_fdtd_workflow_example,
    "materials": get_guidelines_for_materials,
    "geometry": get_guidelines_for_geometry,
    "fdtd_sources_monitors": get_guidelines_for_fdtd_sources_monitors,
    "fdtd_run_and_results": get_guidelines_for_fdtd_run_and_results,
    "fdtd_boundary_conditions": get_guidelines_for_fdtd_boundary_conditions,
    "fdtd_mesh_and_convergence": get_guidelines_for_fdtd_mesh_and_convergence,
    "fdtd_source_types": get_guidelines_for_fdtd_source_types,
    "fdtd_monitors_and_field_extraction": (get_guidelines_for_fdtd_monitors_and_field_extraction),
    "fdtd_far_field_and_grating": get_guidelines_for_fdtd_far_field_and_grating,
    "s_parameter_sweep": get_guidelines_for_s_parameter_sweep,
    "mode_fde_workflow": get_guidelines_for_mode_fde_workflow,
    "mode_fde_results": get_guidelines_for_mode_fde_results,
    "mode_eme_workflow": get_guidelines_for_mode_eme_workflow,
    "mode_varfdtd_workflow": get_guidelines_for_mode_varfdtd_workflow,
    "interconnect_workflow": get_guidelines_for_interconnect_workflow,
    "interconnect_simulation": get_guidelines_for_interconnect_simulation,
    "interconnect_commands": get_guidelines_for_interconnect_commands,
    "device_workflow": get_guidelines_for_device_workflow,
    "device_materials": get_guidelines_for_device_materials,
    "device_simulation_region": get_guidelines_for_device_simulation_region,
}


@app.tool(tags={"guidelines"})
def get_guidelines_for(content: GuidelinesContent) -> str:
    """Fetch authoritative Lumerical scripting guidelines (markdown) for one topic.

    Call this tool BEFORE writing any Lumerical Python (lumapi) code, once
    per topic you need. Always fetch ``"workflow"`` first (the
    product-agnostic execution model and do-not-assume rules), then add
    the product-specific topics that match the task.

    Parameters
    ----------
    content : str
        Topic to retrieve. One of:

        - ``"workflow"`` -- product-agnostic execution model: chunked
          ``execute_python_code`` snippets against the persistent
          subprocess, the seeded ``_lum_get`` / ``_lum_print_json``
          helpers, per-product ``<handle>.run()`` calling conventions,
          and the do-not-assume / do-not-invent / do-not-re-run rules.
          Applies to FDTD, MODE, DEVICE, INTERCONNECT.
        - ``"sweeps"`` -- product-agnostic ``addsweep`` lifecycle
          (parameter sweep, optimization, Monte Carlo, S-parameter,
          corner sweep), the dict-as-struct payload convention for
          ``addsweepparameter`` / ``addsweepresult``, the
          ``deletesweep`` idempotent-rebuild pattern, and result
          extraction via ``getsweepresult``. Applies to FDTD, MODE,
          INTERCONNECT.
        - ``"pic"`` -- shared photonic simulation hygiene for optical
          elements: extending continuing guided structures through PML,
          giving ports / mode-solver windows enough wavelength-scale
          padding around the confined mode, and avoiding accidental
          substrate-mode selection. Applies to FDTD, MODE, and FEEM.
        - ``"nested_sweeps"`` -- product-agnostic hierarchical sweep
          workflow: build the inner sweep first, wrap it with
          ``insertsweep``, configure the outer sweep, then run the
          outer parent sweep to evaluate all parameter combinations.
        - ``"materials"`` -- built-in vs. custom material selection,
          the ``addmaterial()`` / ``setmaterial()`` handle pattern,
          and anisotropic material input (diagonal + grid-attribute
          general anisotropy). Shared by FDTD and MODE.
        - ``"geometry"`` -- dictionary-based ``addrect`` / ``addX``
          syntax for Lumerical layout objects and the ``"x span"``
          (not ``"x_span"``) property-naming convention. Shared by
          FDTD, MODE, and DEVICE.
        - ``"fdtd_workflow"`` -- FDTD-specific build/setup stages,
          disambiguation defaults (3D, PML on all open boundaries, SI
          units, built-in materials), and the PML boundary-extension
          rule. Pair with ``"fdtd_run_and_results"`` for the
          run/results half.
        - ``"fdtd_workflow_example"`` -- full worked example (straight
          silicon waveguide with TE port S-parameter extraction):
          pre-flight default-confirmation checklist followed by Steps
          1-8 with the exact ``execute_python_code`` snippet for each
          chunk.
        - ``"fdtd_sources_monitors"`` -- ``setglobalsource`` /
          ``setglobalmonitor`` usage (and the no-dict-syntax
          exception); prefer ``addport()`` over ``addmode()`` for
          S-parameter extraction; port direction convention.
        - ``"fdtd_run_and_results"`` -- FDTD-specific ``run()``
          arguments (solver / resource / GPU / Ansys Cloud Burst), the
          ``run()``-once + ``switchtolayout`` rule, the
          dataset-is-a-dict contract for ``getresult``, mandatory
          ``_lum_print_json`` inspection before indexing, the per-port
          S vs. full S-matrix distinction, and the
          ``fdtd.eval("<lsf>;")`` escape hatch.
        - ``"fdtd_boundary_conditions"`` -- BC decision guide and
          the four FDTD BC families: PML profiles (standard /
          stabilized / steep angle / custom), symmetric and
          anti-symmetric, periodic, and Bloch (plus when to switch
          to the BFAST plane-wave source for broadband angled
          incidence).
        - ``"fdtd_mesh_and_convergence"`` -- ``"mesh accuracy"``
          semantics (ppw vs. integer 1-8), conformal-mesh
          refinement variants, ``addmesh`` overrides for thin
          features and metals, ``simulation time`` / auto-shutoff
          interplay, and divergence diagnostics via the FDTD
          solver ``STATUS`` result.
        - ``"fdtd_source_types"`` -- non-port source catalog with
          a decision tree: ``addplane`` / BFAST plane-wave,
          ``addgaussian``, ``adddipole``, ``addtfsf``, and
          ``addimportedsource``; gotchas (TFSF interface
          crossings, broadband-angle injection, dipole homogeneous
          validation).
        - ``"fdtd_monitors_and_field_extraction"`` -- monitor type
          decision table (DFT power / profile / time / movie /
          index / mode-expansion), ``"override global monitor
          settings"`` pattern, mode-expansion analysis, and the
          ``reduce-before-print`` pattern that keeps 3D fields
          from blowing through the ``_lum_print_json`` truncation
          guard.
        - ``"fdtd_far_field_and_grating"`` -- turning near-field
          monitor data into ``farfield2d`` / ``farfield3d`` /
          ``farfieldexact`` projections, grating-order analysis
          (``gratingn1`` / ``gratingn2`` / ``grating`` /
          ``gratingangle`` / ``gratingpolar``), and NA / cone
          filtering via ``farfield3dintegrate``.
        - ``"s_parameter_sweep"`` -- full N x N S-matrix extraction
          via ``addsweep(3)`` / ``runsweep`` /
          ``getsweepresult("s-parameter sweep", "S matrix")``, with a
          Y-branch worked example (auto symmetry) and Touchstone /
          INTERCONNECT export. Shared by FDTD and MODE; fetch whenever
          the user asks for the full S-matrix of a multi-port device.
        - ``"mode_fde_workflow"`` -- MODE FDE-specific build/setup
          workflow: safe ``addfde()`` + ``setnamed()`` configuration,
          bent-waveguide keys, active-property caveats, and sweep-safe
          reuse of clean pre-run setup files.
        - ``"mode_fde_results"`` -- MODE FDE solve/result guidance:
          when to use ``findmodes()``, common ``getdata()`` fields
          such as ``neff`` / ``loss`` / ``TE polarization fraction`` /
          ``ng``, and robust TE/TM classification across sweeps.
        - ``"mode_eme_workflow"`` -- MODE EME-specific build/setup and
          analysis workflow: cell-group setup, matrix-style ``group spans`` /
          ``cells`` payloads, layout-vs-analysis mode rules,
          ``emepropagate()`` / ``emesweep()``, port hygiene, and
          user-S-matrix interpretation.
        - ``"mode_varfdtd_workflow"`` -- MODE varFDTD-specific
          build/setup workflow: when to use the 2.5D propagator,
          effective-index setup, bandwidth choices, supported source /
          monitor classes, and validation of generated effective
          materials.
        - ``"interconnect_workflow"`` -- INTERCONNECT-specific
          build/setup workflow: chunked stages for library validation,
          element addition and naming, port discovery, connections,
          property discovery, and save/run sequencing.
          Fetch for any INTERCONNECT photonic circuit task.
        - ``"interconnect_simulation"`` -- INTERCONNECT root element
          simulation configuration (``"simulation input"`` mode
          selector, time-domain property sets, ONA frequency-domain
          workflow) and ``getresult`` discovery pattern for analyzers.
          Fetch alongside ``"interconnect_workflow"`` for any
          simulation setup or result extraction task.
        - ``"interconnect_commands"`` -- INTERCONNECT-specific lumapi
          command reference: element library, design kits,
          measurements, scripted elements, optimization, and export
          commands. Fetch when you need the exact command name or
          signature for an INTERCONNECT operation.
        - ``"device_workflow"`` -- finite-element IDE (DEVICE) workflow
          shared by HEAT, CHARGE, FEEM, and DGTD: chunked stages for
          model-material creation, geometry, solver addition, simulation-
          region linkage, boundary conditions (children of the solver's
          ``boundary conditions`` object), monitors (children of the
          solver object), run, and result collection from both monitors
          and the solver object itself.
        - ``"device_materials"`` -- model-material creation via
          ``addmodelmaterial`` / ``addmaterialproperties``, property
          families (EM / CT / HT), selection hygiene after each
          ``addmaterialproperties`` call, and database discovery.
          Shared by HEAT, CHARGE, FEEM, and DGTD.
        - ``"device_simulation_region"`` -- simulation-region
          ownership model (region is separate from the solver object),
          per-face boundary types (Open / Closed / Shell), background
          material, and linking the region to a solver via
          ``setnamed(solver, "simulation region", region_name)``.
          Shared by HEAT, CHARGE, FEEM, and DGTD.
    """
    return _CONTENT_MAP[content]()


__all__ = [
    "GuidelinesContent",
    "get_guidelines_for",
    "get_guidelines_for_workflow",
    "get_guidelines_for_sweeps",
    "get_guidelines_for_pic",
    "get_guidelines_for_nested_sweeps",
    "get_guidelines_for_fdtd_workflow",
    "get_guidelines_for_fdtd_workflow_example",
    "get_guidelines_for_materials",
    "get_guidelines_for_geometry",
    "get_guidelines_for_fdtd_sources_monitors",
    "get_guidelines_for_fdtd_run_and_results",
    "get_guidelines_for_fdtd_boundary_conditions",
    "get_guidelines_for_fdtd_mesh_and_convergence",
    "get_guidelines_for_fdtd_source_types",
    "get_guidelines_for_fdtd_monitors_and_field_extraction",
    "get_guidelines_for_fdtd_far_field_and_grating",
    "get_guidelines_for_s_parameter_sweep",
    "get_guidelines_for_mode_fde_workflow",
    "get_guidelines_for_mode_fde_results",
    "get_guidelines_for_mode_eme_workflow",
    "get_guidelines_for_mode_varfdtd_workflow",
    "get_guidelines_for_interconnect_workflow",
    "get_guidelines_for_interconnect_simulation",
    "get_guidelines_for_interconnect_commands",
    "get_guidelines_for_device_workflow",
    "get_guidelines_for_device_materials",
    "get_guidelines_for_device_simulation_region",
]
