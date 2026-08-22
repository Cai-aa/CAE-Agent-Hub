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

"""MODE-specific guideline topics."""

from __future__ import annotations


def get_guidelines_for_mode_fde_workflow() -> str:
    """MODE FDE build/setup workflow for straight and bent-waveguide tasks."""
    return """# MODE FDE Workflow

This topic covers the MODE Finite-Difference Eigenmode (FDE) solver
workflow for waveguide cross-sections, including bent-waveguide setup,
safe property-setting patterns, and sweep-safe project reuse.

Read ``workflow`` first for the generic snippet model and do-not-assume
rules. Pair this topic with ``geometry`` and ``materials`` for shared
layout/material conventions, and with ``mode_fde_results`` for the
``findmodes()`` / extraction half.

## When To Use FDE

Use FDE when the task is to solve waveguide cross-sectional modes,
effective index, loss, polarization, group index, or bent-waveguide
mode properties. FDE solves a cross-sectional eigenvalue problem; it is
not the right solver for full-device taper propagation or EME-style
port-to-port transmission.

## MODE FDE Build Stages

Prefer these stages as separate ``execute_python_code`` snippets:

1. Parameters: wavelength, materials, cladding/substrate, solver span,
   boundary conditions, number of trial modes, and bend settings if any.
2. Add the geometry and materials.
3. Add a bare ``FDE`` object.
4. Configure the FDE object incrementally with ``setnamed()``.
5. Save the setup file.
6. Stop and ask before solving; the solve/extract half lives in
   ``mode_fde_results``.

## Safe Object-Creation Pattern

For MODE FDE, prefer a bare ``addfde()`` followed by one-property-at-a-time
``setnamed("FDE", ...)`` calls. In practice, valid properties can be
rejected when they are packed into the constructor dict, while the same
properties succeed after the object exists.

Safe pattern:

```python
mode = _lum_get("mode_fde")
mode.addfde()
mode.setnamed("FDE", "solver type", "2D Z normal")
mode.setnamed("FDE", "wavelength", wavelength_m)
mode.setnamed("FDE", "number of trial modes", trial_modes)
_lum_print_json({"stage": "fde_configured", "ok": True})
```

Avoid assuming that constructor-time ``addfde({...})`` accepts the same
property surface or activation state as later ``setnamed()`` calls.

## Common FDE Property Names

Commonly-needed keys include:

- ``solver type``
- ``wavelength``
- ``number of trial modes``
- ``x``, ``x span``, ``y``, ``y span``
- boundary keys such as ``x min bc``, ``x max bc``, ``y min bc``,
  ``y max bc``
- ``bent waveguide``
- ``bend radius``
- ``bend orientation``
- ``calculate group index``

Do not assume that a visible alternate spelling such as
``center wavelength`` is active just because it appears in a property dump.
If a property is rejected as inactive, inspect the object state and switch
to the active canonical key.

## Bent Waveguide Setup

The FDE solver can solve bent waveguides directly. For bent-waveguide
tasks:

- set ``bent waveguide`` to enable the bent solver
- set ``bend radius`` explicitly
- set ``bend orientation`` explicitly when the bend plane matters
- use PML boundaries when bend radiation loss must escape the region

The bent-waveguide effective index depends on the chosen bend radius,
while the angular propagation constant is the radius-independent quantity.
Reported ``loss`` is the net waveguide loss in the chosen setup, not a
separate bend-only delta.

## Boundary Conditions

Metal is a common default in FDE, but it is usually the wrong default for
open bent-waveguide loss calculations. If the user asks for radiation or
bend loss, ask before silently leaving metal boundaries in place. Use PML
only when that matches the intended physics.

## Save-Before-Solve And Sweep-Safe Reuse

Always save a clean setup file before solving. After ``findmodes()`` or a
GUI run, MODE enters analysis mode. A solved project can then reject later
geometry or solver edits.

For parameter sweeps, keep a pre-run setup file and reopen that clean
layout-state file for each sweep point instead of mutating a saved
post-solve file.

## Property Discovery

If you need to inspect a property surface, probe locally and keep the probe
side-effect free. Prefer reading the existing FDE object over disposable
object creation that mutates the live project unnecessarily.

## See Also

Use ``mode_fde_results`` for ``findmodes()``, ``getdata()``, and TE/TM
reporting. Use ``mode_eme_workflow`` for taper, converter, and multi-cell
propagation devices where the EME solver is the right abstraction.
"""


def get_guidelines_for_mode_fde_results() -> str:
    """MODE FDE solve/result extraction guidance."""
    return """# MODE FDE Results

This topic covers solving FDE modes, extracting common mode properties,
and classifying TE-like and TM-like modes in MODE.

Read ``workflow`` first, then ``mode_fde_workflow`` for setup. This topic
assumes the geometry and FDE object already exist and the user has agreed
to solve.

## Solving Modes

For FDE mode solving, prefer ``findmodes()``. Do not assume that generic
``run()`` is the right entry point for cross-sectional mode extraction.

```python
mode = _lum_get("mode_fde")
num_modes = mode.findmodes()
_lum_print_json({"stage": "modes_found", "num_modes": num_modes})
```

If group index is required, enable ``calculate group index`` before the
solve. Save before solving so the results have a stable project file.

Each solved mode is stored as a D-card named ``mode1``, ``mode2``, and so
on under the FDE solver result tree.

## Analysis Mode After Solve

After ``findmodes()`` the project behaves like analysis mode. Do not assume
that the same saved file is safe to mutate for a sweep. Reopen the clean
pre-run setup file when changing geometry or solver settings across sweep
points.

## FDE Analysis Commands

The key analysis commands the agent should know are:

- ``findmodes()`` to calculate the supported modes
- ``selectmode(...)`` to choose which solved mode or modes subsequent
  analysis should act on
- ``setanalysis("property", value)`` to configure FDE analysis-tab
  settings such as mode tracking and detailed dispersion calculation
- ``getanalysis("property")`` to inspect the current analysis settings
  before changing them
- ``frequencysweep()`` to run the frequency sweep using the current
  analysis settings

Use ``setnamed("FDE", ...)`` for solver-object setup in layout mode, and
use ``setanalysis(...)`` / ``getanalysis(...)`` for analysis-tab settings
after the mode solve context is available. Do not mix these two property
surfaces.

## Mode Selection Before Analysis

``selectmode(...)`` can target a mode by index, by name, or by a list of
selected modes. Use it before ``frequencysweep()`` when the sweep should
track a specific mode or mode set.

Representative Python pattern:

```python
mode = _lum_get("mode_fde")
mode.findmodes()
mode.selectmode(1)
mode.setanalysis("track selected mode", 1)
mode.setanalysis("detailed dispersion calculation", 1)
_lum_print_json({"stage": "mode_selected", "selected_mode": 1})
```

Do not assume the desired sweep target is always the first raw mode index.
When needed, classify the modes first and then select the physically
intended one.

## Frequency Sweep

``frequencysweep()`` performs a frequency sweep using the current FDE
analysis settings. It does not return data directly. Instead, it creates a
result object named ``frequencysweep`` under the FDE solver result tree.

Representative Python pattern:

```python
mode = _lum_get("mode_fde")
mode.findmodes()
mode.selectmode(1)
mode.setanalysis("track selected mode", 1)
mode.setanalysis("detailed dispersion calculation", 1)
mode.frequencysweep()
_lum_print_json({"stage": "frequency_sweep_done", "ok": True})
```

## Result Discovery Under FDE

After ``findmodes()``, the solved mode data is available under result paths
such as ``FDE::data::mode1``, ``FDE::data::mode2``, and so on. After
``frequencysweep()``, sweep data is available under
``FDE::data::frequencysweep``.

In the CAD or LSF prompt, selecting the FDE solver and using
``?getresult;`` reveals the available result objects under ``FDE``. Use
that discovery step when the exact result containers are unclear.

In Python lumapi, once the result path is known, pull fields from those
objects with ``getdata(...)``.

## Common Result Fields

For a solved mode card such as ``mode1``, commonly-used ``getdata()``
fields include:

- ``neff``
- ``loss``
- ``TE polarization fraction``
- ``ng`` when group index was enabled

Representative extraction pattern:

```python
mode = _lum_get("mode_fde")
payload = {
    "mode1_neff": mode.getdata("mode1", "neff"),
    "mode1_loss": mode.getdata("mode1", "loss"),
    "mode1_te_fraction": mode.getdata("mode1", "TE polarization fraction"),
}
_lum_print_json(payload)
```

Solved modes do not necessarily appear as ordinary layout objects in a
generic object-tree listing. Use the mode-card result getters directly
instead of assuming they are discoverable from the layout tree alone.

Representative Python extraction patterns:

```python
mode = _lum_get("mode_fde")
payload = {
  "mode1_neff": mode.getdata("FDE::data::mode1", "neff"),
  "mode1_loss": mode.getdata("FDE::data::mode1", "loss"),
}
_lum_print_json(payload)
```

```python
mode = _lum_get("mode_fde")
payload = {
  "dispersion": mode.getdata("FDE::data::frequencysweep", "D"),
  "dispersion_frequency": mode.getdata("FDE::data::frequencysweep", "f_D"),
  "neff_sweep": mode.getdata("FDE::data::frequencysweep", "neff"),
  "frequency": mode.getdata("FDE::data::frequencysweep", "f"),
}
_lum_print_json(payload)
```

## TE/TM Classification

Do not rely on mode index stability across bend radius or other sweeps.
``mode1`` at one parameter point is not guaranteed to represent the same
polarization family at another point.

Prefer this classification rule:

1. extract ``TE polarization fraction`` for the candidate solved modes
2. split the family into TE-like and TM-like modes using that fraction
3. within each family, select the physically relevant mode by highest
   ``neff`` or by the user-requested criterion

This is the robust pattern for bent-waveguide sweeps where ordering shifts.

## Bent-Waveguide Notes

For bent-waveguide FDE results:

- ``neff`` is the bent-waveguide effective index tied to the chosen radius
- ``loss`` is usually reported per length, not per angle
- mode ordering can change as radius changes

If the user needs the angular propagation quantity rather than the usual
effective index/loss pair, inspect the available result fields before
assuming a specific card name.

## Result Extraction Style

Keep snippets compact. Prefer explicit assignments over long loop-heavy
blocks when working in the persistent subprocess. If a result-extraction
snippet starts accumulating loops and formatting complexity, split it into
another ``execute_python_code`` call.

## Reporting Guidance

When the user asks for the fundamental TE and TM modes, report the exact
selection rule you used, for example: "highest-neff TE-like mode by
TE polarization fraction". This avoids silently treating a raw mode index
as a physical label.

## See Also

Use ``mode_fde_workflow`` for setup and sweep-safe file reuse. Use
``mode_eme_workflow`` when the task is device propagation, taper-length
optimization, or user S-matrix extraction rather than cross-sectional mode
analysis.
"""


def get_guidelines_for_mode_eme_workflow() -> str:
    """MODE EME build/setup and analysis workflow."""
    return """# MODE EME Workflow

This topic covers the MODE Eigenmode Expansion (EME) workflow for taper,
converter, and multi-section propagation devices: EME setup, cell-group
configuration, analysis-mode propagation, and result interpretation.

Read ``workflow`` first. Pair this topic with ``geometry`` and
``materials`` for shared build conventions.

## When To Use EME

Use EME for longitudinal devices where propagation through multiple cells,
cell groups, or ports matters: tapers, spot-size converters, bends,
periodic sections, and user S-matrix extraction.

Use FDE instead when the task is only cross-sectional mode properties.

## MODE EME Build Stages

Prefer these stages as separate snippets:

1. Parameters: wavelength, geometry, port intent, number of cell groups,
   group spans, cells per group, and modes per group.
2. Add geometry.
3. Add the EME object.
4. Configure the EME setup in layout mode.
5. Save the setup file.
6. Ask before the mode-calculation / propagation step.
7. After the user confirms, run the EME calculation to enter analysis mode.
8. In analysis mode, use ``emepropagate()`` / ``emesweep()`` and extract
   the user S-matrix or other requested results.

## Layout Mode Versus Analysis Mode

This is the most important EME rule.

- In layout mode, configure geometry, ports, and cell groups.
- Running the EME calculation moves the project into analysis mode.
- ``emepropagate()`` and propagation sweeps belong to analysis mode.
- Geometry and most object edits are blocked in analysis mode.

If you need to modify ports, geometry, or solver setup after a run, call
``switchtolayout()`` only after the user confirms that existing analysis
results may be discarded.

## Cell Groups And Group Spans

The longitudinal extent is controlled by cell-group settings, not by
assuming a direct ``x span`` edit on the EME solver object in every state.

Common setup keys include:

- ``number of cell groups``
- ``group spans``
- ``cells``
- ``number of modes for all cell groups``
- ``allow custom eigensolver settings`` when group-specific settings are
  required

For ``group spans`` and ``cells``, do not assume plain Python lists are the
accepted payload. MODE commonly expects matrix-shaped values. When a list is
rejected, switch to the matrix format that the live object accepts.

## Coordinate Updates And Alignment

When changing EME longitudinal spans, do not assume the solver center stays
fixed. Updating ``group spans`` can shift the region center. If the device
must stay centered, explicitly re-apply the intended ``x`` position after
the span update and verify the final bounds.

This matters for taper-length sweeps: set the span-defining properties
first, then re-center, then verify the EME bounds before propagating.

## Ports

Inspect the actual port objects present in the saved project before using
the user S-matrix as a two-port metric. Disposable probe ports can mutate a
live session and leave extra enabled ports behind.

Before reporting port-to-port transmission:

1. verify the expected port count
2. verify which modes are enabled at each port
3. remove unintended ports in layout mode if necessary
4. rerun the EME calculation before trusting the user S-matrix

## Propagation And Sweeps

Use ``emepropagate()`` for the current analysis configuration. Use
``emesweep()`` for propagation-length or wavelength sweeps after the EME
mode solve has been performed.

Keep in mind:

- propagation sweep settings can use internal enum values rather than
  free-form strings
- propagation changes can often be made in analysis mode without
  recalculating the modes
- changing geometry or port definitions requires returning to layout mode

## EME Analysis Commands

The key EME analysis commands the agent should know are:

- ``setemeanalysis("property", value)`` to configure the EME analysis
  window in analysis mode
- ``getemeanalysis("property")`` to inspect the current EME analysis
  settings before changing or using them
- ``emepropagate()`` to run the current propagation analysis
- ``emesweep()`` or ``emesweep("...")`` to run a configured sweep
- ``getemesweep("...")`` to retrieve sweep datasets
- ``exportemesweep("filename", "format")`` to export wavelength-sweep
  data for downstream use, including INTERCONNECT

If the valid analysis-window properties are unclear, discover them first
instead of guessing. In lumapi Python, use explicit getters/setters such as
``mode.getemeanalysis("group spans")`` and
``mode.setemeanalysis("group spans", value)``.

Supported EME sweep modes include:

- ``emesweep()`` or ``emesweep("propagation sweep")``
- ``emesweep("wavelength sweep")``
- ``emesweep("mode convergence sweep")``

## Python Examples

Representative Python lumapi patterns:

```python
mode = _lum_get("eme_device")

# Inspect current analysis settings before changing them.
group_spans = mode.getemeanalysis("group spans")
_lum_print_json({"group_spans": group_spans})
```

```python
mode = _lum_get("eme_device")

# Run the current propagated analysis state.
mode.emepropagate()
result = mode.getresult("EME", "user s matrix")
_lum_print_json(result)
```

```python
mode = _lum_get("eme_device")

# Configure and run a propagation sweep in analysis mode.
mode.setemeanalysis("propagation sweep", 1)
mode.setemeanalysis("parameter", "group span 2")
mode.setemeanalysis("start", 10e-6)
mode.setemeanalysis("stop", 200e-6)
mode.setemeanalysis("number of points", 10)
mode.emesweep()
dataset = mode.getemesweep("S")
_lum_print_json(dataset)
```

```python
mode = _lum_get("eme_device")

# Configure and run a wavelength sweep, then export it.
mode.setemeanalysis("wavelength sweep", 1)
mode.setemeanalysis("start wavelength", 1.5e-6)
mode.setemeanalysis("stop wavelength", 1.6e-6)
mode.setemeanalysis("number of wavelength points", 31)
mode.setemeanalysis("calculate group delays", 1)
mode.emesweep("wavelength sweep")
mode.exportemesweep("s_param", "touchstone")
_lum_print_json({"stage": "wavelength_sweep_exported", "ok": True})
```

```python
mode = _lum_get("eme_device")

# Run a mode convergence sweep and retrieve its dataset.
mode.setemeanalysis("mode convergence sweep", 1)
mode.setemeanalysis("start mode", 4)
mode.setemeanalysis("mode interval", 1)
mode.emesweep("mode convergence sweep")
dataset = mode.getemesweep("S_mode_convergence_sweep")
_lum_print_json(dataset)
```

Keep these mode-specific distinctions in mind:

- ``emepropagate()`` is for the current propagated analysis state, not for
  parameter sweeps
- propagation, wavelength, and mode-convergence sweeps are configured with
  ``setemeanalysis(...)`` and run with ``emesweep(...)``
- wavelength-sweep export uses ``exportemesweep(...)`` and applies to the
  EME analysis wavelength sweep result

## Results To Prefer

The most decision-useful result for a taper or converter is typically the
``user s matrix`` or ``power normalized user s matrix`` after confirming the
port configuration. Do not assume that overlap, ``Pmatrix``, or other
normalized helper results are the correct loss metric for every task.

Always inspect the returned result payload before indexing into it, and say
which S-matrix element you are treating as the transmission metric.

## Analysis-Mode Hygiene

Keep exploratory probes side-effect free where possible. Avoid adding
disposable ports or helper objects to a live session unless you are also
cleaning them up deliberately. If the session has been heavily probed, a
fresh session opened from the saved file is often the safer base for the
production run.

## See Also

Use ``s_parameter_sweep`` when the task is the formal S-parameter matrix
sweep utility shared by FDTD and MODE. Use ``mode_fde_workflow`` and
``mode_fde_results`` for cross-sectional mode solving rather than device
propagation.
"""


def get_guidelines_for_mode_varfdtd_workflow() -> str:
    """MODE varFDTD build/setup workflow."""
    return """# MODE varFDTD Workflow

This topic covers the MODE variational FDTD (varFDTD) workflow for planar
integrated photonic devices that can be modeled with a 2.5D effective-index
approximation. varFDTD reduces a 3D structure to a 2D propagation problem by
deriving effective material properties from a reference vertical slab mode.

Read ``workflow`` first. Pair this topic with ``geometry`` and ``materials``.
Use FDE first when the user still needs cross-sectional mode design inputs;
use varFDTD for the larger planar propagation problem after those inputs are
known.

## When To Use varFDTD

Use varFDTD for slab and ridge waveguides, ring resonators, and other planar
photonic components where the vertical physics is well represented by a chosen
reference slab mode and coupling between supported vertical slab modes is
limited.

Prefer varFDTD over full 3D FDTD when the device fits that 2.5D assumption and
the main goal is efficient guided-wave propagation through a planar structure.

Do not use varFDTD as a substitute for FDE mode solving, and do not treat it as
an exact replacement for full 3D FDTD when the vertical approximation is weak.
Its accuracy depends directly on whether the selected slab mode and
polarization are physically representative of the actual device.

## Information Required Before Setup

Before building the model, obtain or confirm:

- geometry dimensions and layout
- material assignments and any required dispersive models
- simulation-region position and spans
- background index
- simulation time and acceptable auto-shutoff behavior
- wavelength or frequency range of interest
- the slab-mode position and polarization or mode choice for the effective
  index model

Do not invent these values. The wavelength range matters not only for sources
and monitors, but also for effective-material generation, meshing behavior, and
bandwidth-dependent fitting.

## Recommended Workflow

1. Confirm the device is suitable for the 2.5D varFDTD approximation.
2. Build the geometry and assign the intended material models.
3. Add the varFDTD simulation region and set its position, spans, background
   index, and simulation time.
4. Configure the Effective Index settings carefully, especially slab-mode
   position, polarization or explicit mode selection, and bandwidth model.
5. Inspect the generated effective materials using test points or an effective
   index monitor before relying on the setup.
6. Add supported sources and the monitors needed for field, power, or
   mode-expansion analysis.
7. Save the setup file and ask before running.
8. Validate the setup with convergence checks and effective-material sanity
   checks before trusting production results.

## Effective Index Settings

The Effective Index tab is the solver-specific core of the workflow because it
defines how the original 3D structure is converted into the 2D effective-index
model.

Key settings include:

- slab-mode position: place this sample point inside the intended core region so
  the reference vertical slab mode is computed from the right part of the
  device
- polarization or explicit mode selection: this choice directly affects the
  generated effective indices
- effective-index method: use the solver's supported formulation instead of
  assuming one method is always correct
- simulation bandwidth mode: choose narrowband for single-frequency or very
  narrowband studies, and broadband when a dispersive effective-material fit is
  required over a wavelength range
- test points: use them to inspect generated effective materials in selected
  parts of the structure
- clamp to physical material properties: enable this when the effective-index
  procedure produces clearly nonphysical values such as an artificial negative
  imaginary index

If the geometry is made of z-extruded structures with vertical sidewalls, use
the available meshing optimization for that case when appropriate.

## Mesh And Boundary Conditions

varFDTD uses a rectangular Cartesian mesh. A practical starting point is auto
non-uniform meshing with mesh accuracy 1 or 2 for quick initial checks, then
increase resolution during convergence testing.

The meshing algorithm refines automatically in high-index and highly absorbing
regions, but that does not remove the need for user-driven convergence checks.

Supported boundary conditions include:

- PML
- PEC or metal
- PMC
- periodic
- Bloch
- symmetric and anti-symmetric

Choose boundaries that match the physical problem and the source symmetry. Do
not assume a symmetry or periodic boundary is safe unless it is justified by the
actual device and excitation.

## Sources And Monitors

Most standard FDTD sources are available in varFDTD, but import source and port
objects are not supported. Do not suggest port-based setup for varFDTD.

Most standard monitor types behave similarly to their FDTD counterparts. The
effective index monitor is specific to this workflow and reports the generated
2D effective-index profile associated with the chosen slab mode and test-point
configuration.

Typical analysis monitors include:

- field monitors
- power monitors
- mode-expansion monitors
- optional effective index monitors for validating the generated materials

These are commonly used to extract field profiles, transmission, and related
guided-wave metrics.

## Validation And Physicality Checks

Reliable varFDTD results require convergence testing on:

- mesh density
- bandwidth settings
- boundary conditions

Also verify that the selected slab mode and polarization are physically
appropriate for the device under study.

Use test points or an effective index monitor to inspect the generated effective
indices and compare them with the expected material-property bounds of the
original structure. If the generated values are nonphysical, enable clamping to
physical material properties and recheck the effective-material results before
continuing.

## Layout / Analysis Behavior

The generic workflow rules still apply here: ask before running, and after a
run only switch back to layout if the user has explicitly confirmed that
discarding results is acceptable.

## See Also

Use ``mode_fde_workflow`` and ``mode_fde_results`` when the task is still at
the cross-sectional design stage. Use FDTD topics only when the user needs full
3D simulation rather than the MODE varFDTD approximation.
"""


__all__ = [
    "get_guidelines_for_mode_eme_workflow",
    "get_guidelines_for_mode_fde_results",
    "get_guidelines_for_mode_fde_workflow",
    "get_guidelines_for_mode_varfdtd_workflow",
]
