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

"""FDTD-specific guideline topics.

Owns every Lumerical FDTD-flavoured guideline:

- ``fdtd_workflow`` -- chunked **build/setup** stages, PML extension
  rule, disambiguation defaults.
- ``fdtd_workflow_example`` -- worked end-to-end build (straight
  silicon waveguide with TE port S-parameter extraction).
- ``fdtd_sources_monitors`` -- ``setglobalsource`` /
  ``setglobalmonitor`` rules, port-vs-mode-source decision,
  injection control via ``FDTD::ports``.
- ``fdtd_run_and_results`` -- FDTD-specific ``run()`` calling
  conventions (solver / resource type / resource name / CUDA /
  Cloud Burst), ``run()``-once + ``switchtolayout`` rule,
  dataset-as-dict contract, and ``getresult`` discovery.
- ``fdtd_boundary_conditions`` -- PML profiles (standard /
  stabilized / steep angle), symmetric / anti-symmetric, periodic,
  Bloch; decision guide.
- ``fdtd_mesh_and_convergence`` -- ``mesh accuracy`` semantics,
  conformal-mesh variants, mesh overrides, simulation time /
  auto-shutoff, divergence diagnostics.
- ``fdtd_source_types`` -- non-port source catalog: plane wave,
  BFAST, Gaussian, dipole, TFSF, imported source.
- ``fdtd_monitors_and_field_extraction`` -- monitor catalog,
  override-global pattern, mode expansion, reduce-before-print.
- ``fdtd_far_field_and_grating`` -- ``farfield2d/3d``,
  ``farfieldexact``, grating projections, NA filtering.

Cross-cutting topics that apply to several products live in their
own modules to avoid duplication.
"""

from __future__ import annotations


def get_guidelines_for_fdtd_workflow() -> str:
    """FDTD-specific build/setup workflow: stages, PML extension, disambiguation defaults."""
    return """# FDTD Workflow (Build & Setup)

This topic covers the FDTD-specific **build/setup** half of the
chunked ``execute_python_code`` workflow: the FDTD stage list, the
PML boundary-extension rule, and the FDTD-flavoured disambiguation
defaults. The matching **run + results** half (FDTD-specific
``run()`` calling conventions, ``run()``-once / ``switchtolayout``
rule, dataset-is-a-dict contract, ``getresult`` discovery) lives in
``fdtd_run_and_results``.

**Read ``workflow`` first** for the generic execution model
(``_lum_get`` / ``_lum_print_json`` helpers), snippet structure,
parameter management, and the "do NOT make assumptions / do NOT
invent or re-run" rules that apply to every Lumerical product.

## Disambiguation Defaults (FDTD)

Apply only when the user's request is ambiguous; if any parameter
is explicitly stated, follow the user. The product-agnostic
SI-units default lives in ``workflow``.

- **Geometry**: 3D unless the user explicitly asks for 2D.
- **Boundary conditions**: PML on all open boundaries (see "PML
  Boundary Extension" below).
- **Materials**: prefer built-in library entries (see ``materials``).

For **2D FDTD**, the simulation region is always **z-normal**, so the
computational plane is **XY**. Do not invent an arbitrary 2D plane
orientation. If the user asks for 2D, keep the pattern in XY and treat
out-of-plane extent as the Z axis.

## PML Boundary Extension

FDTD uses PML on all open boundaries. Any structure that should be
"infinitely extended" in a given direction (substrates, cladding
layers, waveguides continuing past the device) **must extend
comfortably past the inner PML boundary**, otherwise the material
interface coincides with the PML region and produces spurious
reflections.

Rules:

- The FDTD solver setting ``"extend structure through PML"`` is
  **on by default**, which automatically extends any structure
  that touches the inner PML edge through the PML layer. The
  manual extension pattern below is what makes the structure
  touch that inner edge in the first place, and is also required
  in the cases where you must turn this option **off**:
  - **Photonic crystals / periodic gratings** -- the periodic
    cell must end cleanly at the PML edge; turn auto-extend off.
  - **Metal layers near the PML** -- often the source of
    diverging simulations; truncate ~1 mesh cell short of the
    PML and disable auto-extend.
- **Calculate the extension from the simulation region span, not
  the nominal device dimension.** A 10 um waveguide inside a 12 um
  simulation region needs
  ``x span = sim_x_span + 2 * pml_extension``, not
  ``waveguide_length + 2 * pml_extension``.
- Apply only to the "infinite" axes. The waveguide's transverse
  width is finite and must NOT be extended.
- The exact ``pml_extension`` value is not critical; aim for
  something larger than the PML region thickness (which scales
  with PML-layer count and inversely with mesh size).

```python
sim_x_span = 12e-6           # simulation region span on the propagation axis
pml_extension = 1e-6         # how far past the sim region to extend

fdtd.addrect({               # waveguide: extended along x, finite in y/z
    "name": "waveguide",
    "x": 0, "x span": sim_x_span + 2 * pml_extension,
    "y": 0, "y span": waveguide_width,
    "z min": 0, "z max": waveguide_height,
})
```

See ``fdtd_workflow_example`` Step 4 for a worked substrate +
waveguide pair, and ``geometry`` for the dictionary-based ``addX``
syntax used here.

## FDTD Build Stages

Following ``workflow``'s chunking principle, an FDTD build
typically breaks into these stages -- one ``execute_python_code``
snippet each:

1. **Open session** -- ``open_session`` MCP tool with
   ``product="fdtd"``.
2. **Parameters + simulation region** -- declare dimensions,
   indices, wavelength, mesh accuracy, save path; call
   ``fdtd.addfdtd(...)``.
3. **Materials** -- only if custom materials are needed (see
   ``materials``).
4. **Geometry** -- substrate, waveguide, cladding, etc. See
   ``geometry`` for the dict-form ``addX`` syntax and the PML
   extension rule above.
5. **Sources and monitors** -- ``setglobalsource`` /
   ``setglobalmonitor``, ports vs. mode sources (see
   ``fdtd_sources_monitors``).
6. **Save** -- ``fdtd.save("<path>.fsp")``.
7. **Pause for user confirmation, then run and extract.** Final
   snippet calls ``fdtd.run()`` and pulls results via
   ``_lum_print_json(fdtd.getresult(...))``. The full FDTD-specific
   run + extraction guidance (solver / resource / GPU arguments,
   re-run rules, dataset-is-a-dict contract, the dump-before-index
   pattern) lives in ``fdtd_run_and_results``.

## Worked End-to-End Example

A full step-by-step build (straight silicon waveguide with TE port
S-parameter extraction) lives in ``fdtd_workflow_example``.

## Summary

- **Read ``workflow`` first** for the generic snippet / chunking /
  do-not-assume / wait-for-confirmation-before-run rules and the
  SI-units default.
- **Extend "infinite" structures past the sim region into the
  PML**, calculated from the sim region span (not the device
  dimension).
- **Datasets are dicts**: always
  ``_lum_print_json(<handle>.getresult(...))`` before indexing.
  See ``fdtd_run_and_results``.

See also: ``workflow``, ``fdtd_workflow_example``, ``materials``,
``geometry``, ``fdtd_sources_monitors``, ``fdtd_run_and_results``.
"""


def get_guidelines_for_fdtd_workflow_example() -> str:
    """Worked end-to-end FDTD example: straight silicon waveguide with TE ports."""
    return """# FDTD Workflow: Worked Example

A complete, step-by-step build of a straight silicon waveguide with TE
mode ports for S-parameter extraction. Read ``workflow`` and
``fdtd_workflow`` first -- the example is the worked counterpart to
those topics' rules, and it assumes you already understand the
chunked ``execute_python_code`` model, the ``_lum_get`` /
``_lum_print_json`` helpers, the "do NOT make assumptions" rules
(all in ``workflow``), and the FDTD-specific PML extension rule and
build-stage list (in ``fdtd_workflow``).

## User Request

"Silicon (n=3.48) waveguide, 500 nm wide x 220 nm tall x 10 um long,
on a 2 um SiO2 (n=1.44) substrate, air cladding, simulate at 1550 nm
with TE port source/monitors for S-parameters. Wait for confirmation
before running."

## Pre-Flight: Confirm Defaults Before Issuing Any Snippet

The user request above pins geometry, materials, wavelength, and the
source/monitor strategy, but leaves several solver-side knobs
implicit. Apply the ``workflow`` "Do NOT Make Assumptions" rules:
for **this** request, that means explicitly confirming or asking
about each of the following before issuing Step 1 -- do not silently
bake in a default.

- **Mesh accuracy** (integer 1-8 on ``addfdtd``). The Lumerical
  docs recommend **starting at 1-2** for a quick first run and
  raising it only as part of a convergence check; the FDTD solver
  reference defines accuracy 1 = 6 ppw, accuracy 2 = 10 ppw, and
  each step adds 4 ppw. Ask the user which accuracy they want
  rather than baking in an arbitrary "publication-grade" value.
- **Save path** for the ``.fsp``: ask. If the user says "anywhere",
  use ``/tmp/<session_name>.fsp`` (Linux/macOS) or
  ``%TEMP%\\<session_name>.fsp`` (Windows) and tell them.
- **Wavelength point count**: "simulate at 1550 nm" means a single
  point unless the user asks for a sweep.
- **Air cladding**: the FDTD background defaults to ``n = 1``
  (vacuum). Either substitute vacuum and say so, or add a custom
  dielectric for air (see ``materials``) -- never substitute
  silently.

The example below assumes the user confirmed ``mesh_accuracy = 2``
(a reasonable first-run value; raise for convergence testing) and
provided ``save_path``. Both are bound as Python variables in
Step 2 so the choices live in one place.

## The Build

Each ``execute_python_code`` snippet is one chunk in the build.

**Step 1 -- open the session** (tool: ``open_session``).
Do NOT pass ``hide`` -- only set it on explicit user request:

```json
{"name": "straight_wg", "product": "fdtd"}
```

**Step 2 -- parameters and simulation region**
(tool: ``execute_python_code``):

```python
fdtd = _lum_get("straight_wg")

waveguide_width = 500e-9
waveguide_height = 220e-9
waveguide_length = 10e-6
substrate_thickness = 2e-6

core_index = 3.48
clad_index = 1.44

wavelength = 1550e-9
pml_extension = 1e-6

# Confirmed with user during pre-flight; referenced (not hard-coded)
# by later snippets so the choices live in exactly one place.
mesh_accuracy = 2                         # 1-8; start low
save_path = "/tmp/straight_wg.fsp"

sim_x_span = waveguide_length
sim_y_span = 3e-6
sim_z_min = -substrate_thickness * 0.5
sim_z_max = waveguide_height + 1e-6

fdtd.addfdtd({
    "x": 0, "x span": sim_x_span,
    "y": 0, "y span": sim_y_span,
    "z min": sim_z_min, "z max": sim_z_max,
    "mesh accuracy": mesh_accuracy,
})

_lum_print_json({"stage": "region", "ok": True,
                 "mesh_accuracy": mesh_accuracy,
                 "save_path": save_path})
```

**Step 3 -- geometry, extended into the PML on the propagation axis**
(see ``geometry`` for ``addX`` syntax and ``fdtd_workflow`` for the
PML extension rule):

```python
fdtd = _lum_get("straight_wg")

fdtd.addrect({
    "name": "substrate",
    "material": "SiO2 (Glass) - Palik",
    "x": 0, "x span": sim_x_span + 2 * pml_extension,
    "y": 0, "y span": sim_y_span + 2 * pml_extension,
    "z min": -substrate_thickness, "z max": 0,
})

fdtd.addrect({
    "name": "waveguide",
    "material": "Si (Silicon) - Palik",
    "x": 0, "x span": sim_x_span + 2 * pml_extension,
    "y": 0, "y span": waveguide_width,
    "z min": 0, "z max": waveguide_height,
})

_lum_print_json({"stage": "geometry", "ok": True})
```

**Step 4 -- global source / monitor settings and ports**
(see ``fdtd_sources_monitors`` for the port-direction convention):

```python
fdtd = _lum_get("straight_wg")

fdtd.setglobalsource("wavelength start", wavelength)
fdtd.setglobalsource("wavelength stop", wavelength)
fdtd.setglobalmonitor("use source limits", True)
fdtd.setglobalmonitor("frequency points", 1)

port_y_span = 2e-6
port_z_center = waveguide_height / 2
port_z_span = 1.5e-6

fdtd.addport({
    "name": "input_port",
    "injection axis": "x-axis",
    "direction": "Forward",
    "mode selection": "fundamental TE mode",
    "x": -sim_x_span / 2 + 0.5e-6,
    "y": 0, "y span": port_y_span,
    "z": port_z_center, "z span": port_z_span,
})

fdtd.addport({
    "name": "output_port",
    "injection axis": "x-axis",
    "direction": "Backward",
    "mode selection": "fundamental TE mode",
    "x": sim_x_span / 2 - 0.5e-6,
    "y": 0, "y span": port_y_span,
    "z": port_z_center, "z span": port_z_span,
})

# Pick which port mode actually injects on this run. The
# ``FDTD::ports`` group owns the injection state (``source port`` +
# ``source mode``); per-port ``"mode selection"`` above only chooses
# which mode each port analyses. Without this step the active source
# defaults silently to whichever port was added first.
fdtd.setnamed("FDTD::ports", "source port", "input_port")
fdtd.setnamed("FDTD::ports", "source mode", "mode 1")

_lum_print_json({"stage": "ports", "ok": True})
```

**Step 5 -- save**. ``save_path`` was bound during Step 2 from the
value the user confirmed at pre-flight, so the agent neither
hard-codes a path here nor invents one:

```python
import os
fdtd = _lum_get("straight_wg")
fdtd.save(save_path)
_lum_print_json({"stage": "saved", "path": save_path,
                 "exists": os.path.isfile(save_path)})
```

**Pause here and ask the user to confirm before running.**

**Step 6 -- run and pull S-parameters.** ``run()`` is called exactly
once; the call blocks until the simulation completes. The ports
group itself is **not** a result provider, so we discover first
(``fdtd.getresult()``) and then index per-port at
``FDTD::ports::<port_name>``. See ``fdtd_run_and_results`` for the
FDTD-specific ``run()`` calling conventions, the
dataset-is-a-dict contract, and the dump-before-index pattern, and
``s_parameter_sweep`` if the user later wants the full N x N
S-matrix.

```python
fdtd = _lum_get("straight_wg")
fdtd.run()
_lum_print_json(fdtd.getresult())
```

After confirming the result providers in the printed output, dump
the per-port dataset structure before indexing:

```python
fdtd = _lum_get("straight_wg")
_lum_print_json(fdtd.getresult("FDTD::ports::output_port", "S"))
```

**Step 7 -- close the session** (tool: ``close_session``) when the
results have been delivered:

```json
{"name": "straight_wg"}
```

See also: ``fdtd_workflow``, ``materials``, ``geometry``,
``fdtd_sources_monitors``, ``fdtd_run_and_results``.
"""


def get_guidelines_for_fdtd_sources_monitors() -> str:
    """Global source/monitor settings and the port-vs-mode-source decision."""
    return """# FDTD Sources and Monitors

This topic covers two related conventions: using global source/monitor
settings instead of per-object configuration, and preferring ports over
mode sources whenever S-parameters are needed.

## Use Global Source and Monitor Settings

Lumerical FDTD provides global settings for sources and monitors that
apply to all objects of that type. **Always use global settings**
instead of configuring wavelength/frequency parameters on individual
sources and monitors.

### Guidelines

- Set wavelength range using ``setglobalsource`` for sources and
  ``setglobalmonitor`` for monitors.
- Individual sources and monitors should inherit from global settings
  by default.
- Only override global settings on individual objects when there is a
  specific reason (see exceptions below).

### When to override global source settings

- Multiple sources with different wavelength ranges are required.
- A specific source needs different frequency points than others.

### When to override global monitor settings

- Multiple monitors need to record at different frequency resolutions.
- A specific monitor needs a different wavelength range than the global
  setting.
- Power monitors vs. field monitors have different frequency
  requirements.

### Important: no dict syntax for global setters

Unlike most lumapi functions, ``setglobalsource`` and
``setglobalmonitor`` do **not** support dictionary-based initialization.
You must use individual ``set``-style calls for each property.

### Example: setting global source and monitor properties

```python
# Set global source properties (applies to all sources)
# NOTE: setglobalsource does NOT support dict syntax - use individual calls
fdtd.setglobalsource("wavelength start", 1.5e-6)
fdtd.setglobalsource("wavelength stop", 1.6e-6)

# Set global monitor properties (applies to all monitors)
# NOTE: setglobalmonitor does NOT support dict syntax - use individual calls
fdtd.setglobalmonitor("use source limits", True)   # Use same wavelength range as source
fdtd.setglobalmonitor("frequency points", 101)     # Number of frequency points to record

# Sources and monitors will automatically use these global settings
# No need to specify wavelength on individual objects
fdtd.addmode({
    "name": "source",
    "x": source_x,
    "y": 0,
    "y span": source_y_span,
    "z": source_z,
    "z span": source_z_span,
    "injection axis": "x-axis",
    "direction": "Forward"
    # wavelength settings inherited from global source
})

fdtd.addpower({
    "name": "transmission",
    "monitor type": "2D X-normal",
    "x": monitor_x,
    "y": 0,
    "y span": monitor_y_span,
    "z": monitor_z,
    "z span": monitor_z_span
    # frequency settings inherited from global monitor
})
```

## Use Ports Instead of Mode Sources

For any waveguide excitation where S-parameters are needed (single
waveguides, directional couplers, splitters, multi-port devices),
use ``addport()`` instead of ``addmode()``. A port is a combined
mode source + monitor with built-in S-parameter extraction; after
``fdtd.run()`` each port exposes its own ``"S"`` dataset at
``FDTD::ports::<port_name>`` (shape ``(N_freq, N_modes)``). For
the full N x N S-matrix across every active port, use the
S-parameter matrix sweep tool (see ``s_parameter_sweep``) --
``FDTD::ports`` itself is a group, not a result provider, and
``getresult("FDTD::ports", "S")`` raises
``'FDTD::ports is not a result provider'``.

### Injection control: the ``FDTD::ports`` group, not the port

Per-port ``"mode selection"`` (e.g. ``"fundamental TE mode"``)
chooses **which mode each port analyses**. Which port mode actually
**injects** on a given ``fdtd.run()`` is owned by the
``FDTD::ports`` group via its ``source port`` and ``source mode``
properties; only one port mode injects per run. Always set this
explicitly rather than relying on whichever port was added first:

```python
fdtd.setnamed("FDTD::ports", "source port", "input_port")
fdtd.setnamed("FDTD::ports", "source mode", "mode 1")
```

For the full N x N matrix the S-parameter sweep tool rotates this
source-port selection through every active port automatically;
do not loop ``fdtd.run()`` manually.

### Other FDTD source types

``addport()`` and ``addmode()`` are not the only sources. Reach
for the others when ports/modes don't apply:

- ``addplane`` -- plane-wave (free-space scattering, transmission
  / reflection through gratings or thin films).
- ``addgaussian`` -- focused Gaussian / scalar beam.
- ``adddipole`` -- point electric / magnetic dipole (LED, antenna,
  Purcell-factor problems).
- ``addtfsf`` -- total-field / scattered-field plane wave for
  isolated scatterer cross-sections (RCS, absorption).
- ``addimportedsource`` -- field profile imported from a
  monitor or external file.

A port is the right choice whenever the structure has a clean
waveguide cross-section at the source plane; the source types
above are for plane-wave illumination, free-space radiation, and
non-waveguide problems.

### Port ``direction`` convention

For S-parameter extraction with ports at opposite ends of a
waveguide, the ports must **face into the simulation domain**:

- **Input port** at the low-coordinate end of the propagation axis
  (e.g. ``x = -L/2``) is the active source, injecting light toward
  the device. Its ``direction`` is ``"Forward"``.
- **Output port** at the high-coordinate end (e.g. ``x = +L/2``) is
  passive (transmission monitor). Its ``direction`` is
  ``"Backward"`` -- the port surface normal points back into the
  simulation, which is what makes a wave travelling in ``+x``
  register as "incoming" for that port and gives the right sign
  convention for ``S21``.

A common mistake is to set both ports to ``"Forward"``. The
simulation will still run and per-port ``getresult`` calls (e.g.
``getresult("FDTD::ports::output_port", "S")``) will still return
numbers, but the "incident vs. transmitted" labelling at the output
port is wrong, so the resulting S-parameters do not have the
conventional meaning.

### Example: using ports for S-parameter measurement

```python
# Input port: active TE source + reflection (S11) monitor.
# Direction "Forward" so it injects light in +x toward the device.
fdtd.addport({
    "name": "input_port",
    "injection axis": "x-axis",
    "direction": "Forward",
    "mode selection": "fundamental TE mode",
    "x": input_x,
    "y": 0,
    "y span": port_y_span,
    "z": port_z_center,
    "z span": port_z_span
})

# Output port: transmission (S21) monitor.
# Direction "Backward" so the port faces into the simulation domain
# and a wave travelling in +x registers as "incoming" for this port.
fdtd.addport({
    "name": "output_port",
    "injection axis": "x-axis",
    "direction": "Backward",
    "mode selection": "fundamental TE mode",
    "x": output_x,
    "y": 0,
    "y span": port_y_span,
    "z": port_z_center,
    "z span": port_z_span
})

# After simulation, per-port S-parameters can be extracted using:
# S = fdtd.getresult("FDTD::ports::output_port", "S")
# (See ``fdtd_run_and_results`` for the dataset-is-a-dict contract
# and the dump-before-index pattern.) For the full N x N S-matrix
# across every active port, see ``s_parameter_sweep``.
```

See also: ``fdtd_workflow``, ``materials``, ``geometry``,
``fdtd_run_and_results``, ``s_parameter_sweep``.
"""


def get_guidelines_for_fdtd_run_and_results() -> str:
    """FDTD run + results: solver args, run-once + ``switchtolayout``, datasets, ``getresult``."""
    return """# FDTD Run and Results

This topic covers the FDTD-specific **run and results** half of the
workflow: the ``run()`` calling conventions (solver / resource type
/ resource name / CUDA / Cloud Burst arguments documented for the
``run`` script command), the run-once + ``switchtolayout`` rule for
re-running, the dataset-is-a-dict contract for extracting data, and
the per-port S-parameter contract (and where the full N x N
S-matrix actually comes from).

The product-agnostic ``run()`` semantics (blocks, returns no data,
raises on failure; ``save()`` before ``run()``; ask the user before
invoking it) live in ``workflow``; the FDTD build/setup half (build
stages, PML extension, disambiguation defaults) lives in
``fdtd_workflow``.

## Running an FDTD Simulation

### Solver / Resource / GPU Arguments

The lsf positional arguments documented for the ``run`` script
command map 1:1 to Python positional arguments on the handle. All
forms are optional overrides for **a single call** -- they do not
mutate the project's saved solver / resource defaults.

```python
fdtd = _lum_get("project_name")
fdtd.run()                              # use project defaults
fdtd.run("FDTD")                        # pick the solver: "FDTD" or
                                        # "RCWA" (RCWA is CPU-only)
fdtd.run("FDTD", "GPU")                 # pick resource type:
                                        # "CPU" or "GPU"
fdtd.run("FDTD", "GPU", "my_cluster")   # also pick a named resource
                                        # set from the resource
                                        # configuration window
fdtd.run("FDTD", "GPU", "my_cluster",
         [0, 1])                        # pin specific GPUs via
                                        # CUDA_VISIBLE_DEVICES
                                        # (single value or list)
```

For Ansys Cloud Burst Compute submission (FDTD only). The
``getresource`` signature takes the resource **name** only -- not
the ``(solver, resource_type, name)`` triple used by ``run()``:

```python
burst_settings = fdtd.getresource("burst")
# ... edit fields on burst_settings as needed ...
fdtd.run("FDTD", "GPU", "burst", burst_settings)
```

For **2D FDTD**, prefer ``CPU`` instead of ``GPU``. If a user explicitly
asks for GPU on a 2D job, warn that the run may be unsupported or limited
on GPU in the current environment and confirm before proceeding.

### Run Once; ``switchtolayout`` to Re-run

FDTD's ``run()`` is meant to be called **once** per project state:

- After ``run()`` the project is in **analysis mode** and the
  layout is frozen. Mutating geometry, sources, or monitors at this
  point raises an lsf error.
- To re-run after editing the layout, drop back to layout mode via
  ``fdtd.switchtolayout()``. **This discards every single-run
  result** (per-port ``"S"``, monitor data); always extract first:

  ```python
  _lum_print_json(fdtd.getresult("FDTD::ports::output_port", "S"))
  fdtd.switchtolayout()
  # ... mutate parameters / objects ...
  fdtd.save(save_path)
  fdtd.run()
  ```

  Sweep results (``getsweepresult(...)``) survive a layout switch;
  single-run monitor / port data does not.

- **Only re-run when the user has explicitly asked for it.** A
  follow-up question about an existing result does not warrant
  another solver call.
- A single ``fdtd.run()`` excites **one port mode** -- whichever
  ``source port`` + ``source mode`` is currently selected on the
  ``FDTD::ports`` group (see ``fdtd_sources_monitors``). The
  per-port ``"S"`` dataset gives one column of the full S-matrix.
  For the full N x N S-matrix of a multi-port device, use the
  S-parameter matrix sweep (see ``s_parameter_sweep``); do not
  loop ``fdtd.run()`` manually with different active ports.

### Read the Error Message Before Changing the Model

If ``fdtd.run(...)`` fails, inspect the actual error text before changing
geometry, sources, or monitors.

- GPU limitation or unsupported-feature message: treat it as a resource
  issue first; for 2D FDTD, switch to ``CPU`` before changing the model.
- Named resource unavailable: retry with project defaults or confirm the
  requested resource name.
- Divergence or physics/setup error: debug the layout and solver setup,
  not the resource type.

## Datasets Are Dicts, Not Objects

Every Lumerical *dataset* (the thing returned by ``fdtd.getresult(...)``,
``fdtd.getdata(...)``, ``fdtd.getelectric(...)``, etc.) is surfaced by
PyLumerical as a **plain Python dict**. There is no attribute access:

```python
# WRONG -- these will raise AttributeError
result = fdtd.getresult("FDTD::ports::input", "S")
result.S          # AttributeError
result.lambda_    # AttributeError

# RIGHT -- index by string key
result = fdtd.getresult("FDTD::ports::input", "S")
s_column = result["S"]
wavelengths = result["lambda"]
```

## Discover Before You Reach (Always)

Do not guess monitor names, dataset names, or property keys. Use the
discovery primitives **first**, then drill down by string key:

```python
fdtd = _lum_get("straight_wg")

# 1. List every monitor / analysis group that has results. The
#    "FDTD::ports" group itself is NOT in this list -- the ports
#    group is a container, not a result provider (see below).
_lum_print_json(fdtd.getresult())

# 2. List the dataset names available on a specific port. The valid
#    path is "FDTD::ports::<port_name>", never just "FDTD::ports".
_lum_print_json(fdtd.getresult("FDTD::ports::input"))

# 3. Pull a specific dataset (then dump it before indexing).
_lum_print_json(fdtd.getresult("FDTD::ports::input", "S"))
```

For object properties (rather than results), use ``getnamed`` /
``setnamed``:

```python
fdtd = _lum_get("straight_wg")
_lum_print_json(fdtd.getnamed("input_port"))   # all properties of input_port
```

## Per-Port S Versus Full S-Matrix

Assuming an aggregate S-matrix exists where it does not is the most
common FDTD post-processing mistake. The rules:

- **``FDTD::ports`` is a group, not a result provider.** Calling
  ``fdtd.getresult("FDTD::ports", ...)`` raises
  ``LumApiError: 'FDTD::ports is not a result provider'``. The
  Lumerical KB is explicit: "results are available from the
  individual port objects inside the port group."
- **Per-port S** lives at ``FDTD::ports::<port_name>``. The ``"S"``
  dataset is a ``complex128`` ndarray of shape ``(N_freq, N_modes)``
  for that monitor port relative to whichever port was the source
  on the run that produced it. After a single ``fdtd.run()``, only
  the configured source port injects, so the S-values you can read
  are one column (and its reflection) of the full matrix -- never
  the matrix itself.
- **The full N x N S-matrix is a sweep result**, not a single-run
  result. It is produced by the S-parameter matrix sweep tool
  (``addsweep(3)`` + ``runsweep("s-parameter sweep")``) which
  launches N simulations, one per active source row. After the
  sweep runs, the matrix is read with
  ``fdtd.getsweepresult("s-parameter sweep", "S matrix")``. See
  ``s_parameter_sweep`` for the recipe.

Port names depend on how the build added ports; never hard-code
labels like ``"Through"`` / ``"Drop"`` / ``"Input"`` without first
confirming them via ``fdtd.getresult()``.

```python
fdtd = _lum_get("straight_wg")

# Step 1: dump it. ALWAYS dump first.
result = fdtd.getresult("FDTD::ports::output", "S")
_lum_print_json(result)
```

The agent reads the printed JSON, confirms the keys (``"S"``,
``"lambda"``, ``"f"``, ...) and shapes, and only **then** writes a
follow-up snippet that indexes them.

```python
import numpy as np
fdtd = _lum_get("straight_wg")

# Step 2: now that we know the shape, pull what we want. ``S`` is
# shape (N_freq, N_modes); for a single-mode port the only mode
# index is 0, so ``S[:, 0]`` is the per-frequency complex
# transmission from the source port to this port.
result = fdtd.getresult("FDTD::ports::output", "S")
_lum_print_json({
    "S21_abs": np.abs(result["S"][:, 0]).tolist(),
    "lambda_nm": (result["lambda"] * 1e9).flatten().tolist(),
})
```

Implications:

- For a per-port S column at one wavelength (a handful of complex
  numbers) you can dump the whole dataset and read it directly.
- For a 3D field monitor (``E``, ``H``) you will hit the truncation
  guard. **Don't** raise ``max_array_size`` to "fix" this -- the LLM
  context window cannot absorb a multi-MB field anyway. Instead,
  either:

  * Reduce in the subprocess before printing
    (``_lum_print_json({"intensity_at_z0": (abs(E)**2).sum(axis=-1).tolist()})``),
    or
  * Save the array to disk inside the subprocess
    (``np.savez(...)``) and only print the path / a small summary.

## End-to-End Example: Pull S-Parameters After ``run()``

This is the typical "after confirmation" snippet referenced from
``fdtd_workflow`` step 7. It runs once, dumps available result
providers and the per-port dataset structure first, and only then
indexes into ``"S"`` -- in three separate ``execute_python_code``
calls so the agent never indexes into a shape it has not actually
inspected.

```python
# First snippet: run + list every result provider.
fdtd = _lum_get("straight_wg")
fdtd.run()
_lum_print_json(fdtd.getresult())
```

```python
# Second snippet (after confirming the provider names): dump the
# per-port dataset structure for the monitor port.
fdtd = _lum_get("straight_wg")
_lum_print_json(fdtd.getresult("FDTD::ports::output_port", "S"))
```

```python
# Third snippet: pull the specific quantities the user asked for.
# ``S`` is a live numpy complex array of shape (N_freq, N_modes),
# so vectorised numpy works directly -- see ``workflow``'s
# "Printed JSON Is a Snapshot" callout.
import numpy as np
fdtd = _lum_get("straight_wg")
result = fdtd.getresult("FDTD::ports::output_port", "S")
S21 = result["S"][:, 0]
_lum_print_json({
    "lambda_nm": (result["lambda"] * 1e9).flatten().tolist(),
    "S21_dB": (20 * np.log10(np.abs(S21))).tolist(),
})
```

For the full N x N S-matrix of a multi-port device (Y-branch, MZI,
directional coupler, ...), one ``fdtd.run()`` is not enough; use
the S-parameter matrix sweep tool. See ``s_parameter_sweep``.

## Summary

- **Use FDTD-specific ``run()`` arguments** for one-off solver /
  resource / GPU overrides; see "Running an FDTD Simulation" above.
- **Call ``run()`` once.** Extract results first, then
  ``fdtd.switchtolayout()`` (which discards single-run results) to
  re-edit -- and only when the user has asked for another simulation.
- **Datasets are dicts.** No attribute access; index with string keys.
- **Always ``_lum_print_json(result)`` before indexing into an
  unfamiliar dataset.**
- **``FDTD::ports`` is not a result provider.** Use
  ``FDTD::ports::<port_name>`` for per-port S
  (shape ``(N_freq, N_modes)``), and the S-parameter matrix sweep
  tool for the full N x N S-matrix.
- **Use ``getresult()`` first** to list every real result provider --
  don't guess monitor or dataset names.
- **Heavy arrays must be reduced or saved to disk** in the subprocess
  before they leave through ``_lum_print_json``.

See also: ``workflow``, ``fdtd_workflow``, ``materials``,
``geometry``, ``fdtd_sources_monitors``, ``s_parameter_sweep``.
"""


def get_guidelines_for_fdtd_boundary_conditions() -> str:
    """FDTD boundary conditions: PML profiles, symmetric/anti-symmetric, periodic, Bloch."""
    return """# FDTD Boundary Conditions

This topic covers the four boundary-condition (BC) families used by
the FDTD solver: **PML** (absorbing, open boundaries), **symmetric
/ anti-symmetric** (mirror-plane speed-up), **periodic** (unit-cell
simulation under normal incidence), and **Bloch** (unit-cell under
angled / phase-shifted excitation). PML-extension geometry rules
live in ``fdtd_workflow``; this topic explains how to pick the
right BC and its key sub-options.

## PML (absorbing, open boundaries)

PML is the default for open boundaries -- it absorbs outgoing light
with minimal reflection. The FDTD simulation region exposes four
predefined PML **profiles** (set on the Boundary Conditions tab):

- **Standard** -- best overall absorption with few layers; default.
  Use whenever no material interface cuts through the PML region.
- **Stabilized** -- use when a material interface cuts through PML
  (substrates, claddings ending mid-PML, metal stacks). Suppresses
  the localised exponential-growth instability that the standard
  profile can develop at such interfaces, at the cost of needing
  more PML layers.
- **Steep Angle** -- use when PML is combined with periodic / Bloch
  BCs (gratings, metasurfaces), where light scatters at angles
  nearly parallel to the PML surface.
- **Custom** -- exposes every PML parameter (LAYERS, KAPPA, SIGMA,
  ALPHA, polynomial orders). Reach for it only after the predefined
  profiles fail.

PML profiles can be set **per-boundary**: uncheck
``"same settings on all boundaries"`` on the FDTD solver object,
then only the offending boundary needs the heavier ``stabilized``
profile. This avoids paying the layer-count cost on every face.

Increasing the layer count lowers reflection on any profile;
diverging or noisy simulations are often fixed by switching to
``stabilized`` or raising the layer count on a single boundary.

## Symmetric / Anti-Symmetric (mirror-plane speed-up)

If the EM fields have a plane of symmetry, replace the open BC on
that plane with a symmetry BC and shrink the sim region accordingly.
Each plane gives a 2x speed-up (4x or 8x for multiple symmetries).

Picking the right one is **source-driven**, not just structure-
driven:

- ``"symmetric"`` -- the source's **electric field polarisation is
  tangential** to the symmetry plane (Lumerical colour code: blue
  arrow along the blue BC face).
- ``"anti-symmetric"`` -- the electric polarisation is **normal**
  to the plane (blue arrow into the green BC face).

Common gotchas:

- A wrong choice produces silently incorrect results -- there is no
  warning. Always validate by re-running once without symmetry and
  comparing.
- **Do not shrink the sim region manually**; the GUI greys out the
  half that won't be simulated. In a script just set the BC and
  leave the span alone -- the solver handles unfolding.
- ``getdata`` / ``getelectric`` / ``getmagnetic`` auto-unfold the
  fields back to the full region; monitors entirely inside the
  greyed half record no data.

## Periodic (unit-cell, normal incidence)

For genuinely periodic structures excited at normal incidence,
set the lateral BCs to ``"periodic"`` and draw exactly one unit
cell. The solver simply copies the field at one face to the
opposite face.

Both the **structure** and the **fields** must be periodic. If a
plane wave hits the cell at an angle, fields differ by a phase
between cells -- periodic BCs are then wrong; use Bloch instead.
A single dipole inside a periodic cell (e.g. OLED) is also
non-periodic in the field sense and should not use periodic BCs.

Extend the structure through the periodic boundary so the material
in the one-mesh-cell BC region is correct.

## Bloch (unit-cell, angled / phase-shifted excitation)

Bloch BCs generalise periodic by applying a phase correction
``exp(-i k_bloch * a)`` between opposite faces. Use them for:

- **Periodic structures under angled plane-wave illumination**
  (gratings, metasurfaces, angle-of-incidence sweeps).
- **Bandstructure** calculations, where ``kx`` / ``ky`` / ``kz`` is
  swept manually.

Key flags and costs:

- ``"set based on source angle"`` is on by default and computes the
  Bloch vector from the plane-wave source's angle. Disable it only
  for bandstructure work where ``kx`` is set manually.
- Bloch uses **complex-valued time-domain fields**, so memory and
  runtime can roughly double, and time-domain field / movie
  monitors record complex values (take the real part if needed).
- For **broadband angled** sweeps, the ordinary plane-wave + Bloch
  combination has a frequency-dependent angle; switch to the
  ``BFAST`` source instead (BFAST manages BCs internally and
  overrides Bloch).

## Choosing the Right BC at a Glance

- Free-space scattering / radiation -> PML on all open faces.
- Symmetric structure + suitably polarised source -> add symmetric
  or anti-symmetric on the mirror plane (one per plane).
- Infinite periodic array, normal incidence -> periodic on lateral
  faces + PML on top/bottom (use ``steep angle`` PML).
- Infinite periodic array, angled incidence (single freq) ->
  Bloch on lateral faces + PML on top/bottom.
- Infinite periodic array, broadband angled incidence -> BFAST
  source (its built-in BCs replace Bloch).

See also: ``fdtd_workflow``, ``fdtd_sources_monitors``,
``fdtd_run_and_results``.
"""


def get_guidelines_for_fdtd_mesh_and_convergence() -> str:
    """FDTD mesh accuracy, conformal mesh, mesh overrides, auto-shutoff, divergence."""
    return """# FDTD Mesh and Convergence

This topic covers the four levers that determine FDTD accuracy and
runtime: the global ``mesh accuracy`` knob, **conformal mesh**
refinement variants, **mesh override** regions for local
refinement, and the **simulation time / auto-shutoff** controls
plus divergence diagnostics.

## Global Mesh Accuracy

The FDTD solver's ``"mesh accuracy"`` property is an integer
1-8 that sets the auto-mesh's points-per-wavelength (ppw) in the
highest-index material:

- ``1`` -> ~6 ppw (very coarse; fast smoke test)
- ``2`` -> ~10 ppw (sensible starting point)
- each step adds 4 ppw, so ``3`` -> 14, ..., ``8`` -> 30+

Guidance from the Lumerical docs:

- **Start at 1-2.** Get a working build, then raise accuracy as
  part of a convergence test (rerun at successively higher values
  and watch the metric of interest stop changing).
- Memory and runtime scale with the cube (3D) of mesh density, so
  jumping straight to 6+ can be very expensive.
- The auto-mesh sees only **dielectric** index; for metals or
  thin features you almost always need a local override (below).

## Conformal Mesh Refinement

The "Mesh refinement" pull-down on the FDTD solver picks how
sub-cell material boundaries are handled. Useful options:

- **Staircase** -- no sub-cell treatment; each Yee cell takes one
  material. Fastest, least accurate; use only for sanity checks.
- **Conformal variant 0** (default) -- the conformal mesh
  technology (CMT) on dielectrics only; metals and PEC fall back
  to staircase. Good default for most photonic structures.
- **Conformal variant 1** -- CMT on everything **except** PEC and
  interfaces involving a metal. Enables sub-cell accuracy for
  most dispersive metals; verify with a convergence test before
  trusting it.
- **Conformal variant 2** -- CMT on all materials including
  metals. Most accurate sub-cell treatment, but can be less stable
  on lossy / dispersive interfaces.
- **Dielectric volume average** -- averages permittivity over the
  cell; reasonable for slowly varying dielectrics.

## Mesh Override Regions

Drop an ``addmesh`` block over a sub-region whenever the auto-mesh
can't see the feature you care about (thin metal layer, small gap,
sub-wavelength corner). Override regions force a finer grid only
inside their bounds:

```python
fdtd.addmesh({
    "name": "metal_film_override",
    "x": 0, "x span": 2e-6,
    "y": 0, "y span": 2e-6,
    "z": metal_z, "z span": metal_thickness + 2 * dx,
    "dx": 5e-9, "dy": 5e-9, "dz": 2e-9,
    "based on a structure": False,
})
```

Tips:

- Always cover the full physical feature **plus** ~1-2 mesh cells
  on each side; clipping the override is a common mistake.
- For thin (< lambda/100) layers, target ``dz`` to give at least
  2 cells across the layer; otherwise the material is invisible
  to the solver.
- Override regions can also be "based on a structure" so they
  follow geometry edits.

## Simulation Time and Auto-Shutoff

Two FDTD-solver fields cap the run:

- ``"simulation time"`` (fs) -- hard wall-clock-equivalent
  upper bound. Default is generous; halve it for quick sanity
  checks.
- ``"auto shutoff min"`` -- the solver stops early when the
  remaining field energy drops below this fraction of the peak.
  Default ``1e-5`` is fine for transmission/reflection;
  resonators and cavities may need ``1e-6`` or smaller to capture
  long ring-down tails.

The ``STATUS`` integer result on the FDTD solver after ``run()``
tells you which one fired:

- ``1`` -- ran to ``simulation time`` (no shutoff). Often means
  the simulation hadn't decayed enough; lower ``auto shutoff min``
  or extend ``simulation time``.
- ``2`` -- auto-shutoff fired (the healthy case).
- ``3`` -- diverged (see below).

## Divergence Diagnostics

If a run diverges (NaNs, fields blowing up), the most common
causes documented in the Lumerical KB:

- **Material interfaces cut through PML** -> switch the offending
  face to the ``stabilized`` PML profile (see
  ``fdtd_boundary_conditions``).
- **Metals touching PML** -> truncate the metal ~1 mesh cell short
  of the inner PML edge and disable ``"extend structure through
  PML"`` on the solver.
- **Under-resolved metals / corners** -> add a local mesh override
  (above) or raise global accuracy.
- **Anisotropic / dispersive material outside its valid range** ->
  re-fit the material model or restrict the source bandwidth.

After a diverging run, ``fdtd.getresult("FDTD", "simulationdata")``
exposes diagnostics (field-energy log, mesh stats); use them
before re-running blindly.

See also: ``fdtd_workflow``, ``fdtd_boundary_conditions``,
``fdtd_run_and_results``.
"""


def get_guidelines_for_fdtd_source_types() -> str:
    """FDTD source-type catalog: plane wave, Gaussian, dipole, TFSF, import, BFAST."""
    return """# FDTD Source Types

This topic catalogues the FDTD source families beyond ports and
mode sources (``fdtd_sources_monitors`` covers those). Pick the
source that matches the physics, not the source you happen to
know best.

## Decision Tree

- **Guided mode** (waveguide cross-section, want S-parameters) ->
  ``addport()`` (or ``addmode()`` if S-params not needed). See
  ``fdtd_sources_monitors``.
- **Plane wave at normal or fixed angle, single frequency** ->
  ``addplane`` (planar wave source).
- **Plane wave, broadband and angled** -> ``addbfastplanewave`` /
  BFAST source -- the only correct broadband-angled source.
- **Focused free-space beam (lens, fiber tip)** -> ``addgaussian``
  (paraxial) or the scalar/vector "thin lens" mode.
- **Isolated scatterer cross-section** (RCS, absorption,
  scattering efficiency) -> ``addtfsf`` (Total-Field
  Scattered-Field).
- **Point emitter** (LED active region, Purcell factor, antenna) ->
  ``adddipole``.
- **Field profile recorded elsewhere or computed externally** ->
  ``addimportedsource``.

## Plane Wave (``addplane``)

A finite-sized plane wave injected through one face of the sim
region. Pair with periodic or Bloch lateral BCs for true
infinite-array behaviour.

Gotchas:

- **Edge effects.** A finite plane wave inside the sim region has
  diffraction at its edges; either size it larger than every
  monitor of interest, or use periodic / Bloch BCs to enforce
  laterally infinite injection.
- **Angled injection of a broadband pulse** suffers from the
  frequency-dependent-angle problem (each frequency component
  refracts to a different angle when combined with Bloch BCs).
  Use BFAST instead.

## BFAST (``addbfastplanewave``)

Broadband Fixed Angle Source Technique. A specialised plane-wave
source for broadband angled sweeps that internally enforces the
correct fixed-angle injection at every frequency in the band.
BFAST automatically overrides Bloch BCs on the lateral faces.

Use BFAST whenever you need a transmission / reflection spectrum
at an oblique angle of incidence.

## Gaussian / Thin-lens beam (``addgaussian``)

Focused beam with user-set waist radius and beam center. Paraxial
form is the default; the "thin lens" option produces a more
accurate vector beam at high NA.

Common applications: fiber-to-chip coupling efficiency, focused
spot inside a metasurface, microscope illumination.

## Dipole (``adddipole``)

Idealised electric or magnetic point dipole, optionally with a
fixed polarisation vector. Required source for:

- **LED / OLED** quantum efficiency (sweep dipole position /
  orientation to integrate over the emissive layer).
- **Purcell factor** vs free-space dipole.
- **Antenna** input impedance and radiation pattern (combine with
  far-field projection, see ``fdtd_far_field_and_grating``).

In an inhomogeneous environment the dipole couples to nearby
structure; always validate with a homogeneous-medium reference
run (Lumerical KB: *Testing FDTD dipole sources in homogeneous
materials*).

## TFSF (``addtfsf``)

Total-Field / Scattered-Field source: a closed box that injects a
plane wave **inside** while subtracting the incident field
**outside**. Power monitors outside the box record only scattered
fields; monitors inside record total fields.

Standard use cases:

- Scattering cross-section / RCS of an isolated particle.
- Absorption cross-section of a nanostructure on a substrate.

Gotcha: TFSF assumes the background outside the box is what is
**inside** the TFSF boundary at simulation start. Avoid having
the TFSF box cross a material interface; substrates that pierce
the box produce spurious scattered fields. The Lumerical KB
includes a dedicated *Tips and best practices when using the FDTD
TFSF source* article -- consult it for any non-trivial geometry.

## Imported Source (``addimportedsource``)

Injects a spatial field profile recorded by a monitor (typically
from a smaller FDE / MODE simulation) or loaded from an external
file. Use when:

- You want to inject a mode computed by a different simulation
  (multi-stage workflow).
- You want a custom illumination profile that none of the analytic
  sources match (engineered wavefront, measured aperture).

The companion KB articles document the spatial-profile import
(monitor-data and equation forms) and the **custom time signal**
mechanism for shaping the pulse temporal envelope.

## Source-Bandwidth and Global Settings

Wavelength / frequency range and pulse length are controlled by
``setglobalsource``. Per-source overrides are documented but rarely
needed -- see ``fdtd_sources_monitors`` for the global vs.
per-source rules. For very-narrow-band or very-broadband sources,
``setglobalsource("optimize for short pulse", False)`` improves
spectral accuracy at the cost of a longer source signal.

See also: ``fdtd_sources_monitors``, ``fdtd_boundary_conditions``,
``fdtd_far_field_and_grating``, ``fdtd_workflow``.
"""


def get_guidelines_for_fdtd_monitors_and_field_extraction() -> str:
    """FDTD monitor catalog + field-extraction patterns (override-global, reduce-before-print)."""
    return """# FDTD Monitors and Field Extraction

This topic covers the FDTD monitor catalogue (which monitor to add
for which question), the ``override global monitor settings``
flag, mode-expansion analysis, and the **reduce-before-print**
pattern that keeps multi-megabyte field arrays from blowing through
the ``_lum_print_json`` truncation guard.

Related: ``fdtd_sources_monitors`` (global settings,
``setglobalmonitor``), ``fdtd_run_and_results`` (datasets-as-dicts
contract, ``getresult`` discovery, large-array safety),
``fdtd_far_field_and_grating`` (turning monitor data into a
far-field projection).

## Choosing a Monitor Type

- **Power / flux through a plane** -- ``addpower`` (alias of
  ``adddftmonitor``); frequency-domain, integrates E x H.
- **Field profile at a few frequencies** -- ``addprofile`` /
  ``adddftmonitor``; frequency-domain spatial fields.
- **Transient field history** -- ``addtime``; time-domain at a
  point or 1D / 2D slice.
- **Real-time animation** -- ``addmovie``; time-domain frames.
- **Index distribution** -- ``addindex``; snapshot of material
  indices on the mesh.
- **Modal content of a guided wave** -- ``addmodeexpansion``;
  decomposes monitor data into mode amplitudes.
- **S-parameters** -- ``addport`` (see ``fdtd_sources_monitors``).

In modern FDTD, ``addpower`` and ``addprofile`` are aliases for
specific configurations of the DFT monitor (``adddftmonitor``);
either form is acceptable. Prefer the explicit ``adddftmonitor``
when migrating to the modern UI / GUI.

## Override Global Monitor Settings

By default monitors inherit wavelength / frequency points from
``setglobalmonitor`` (set those globally first; see
``fdtd_sources_monitors``). Override per-monitor only when you
have a reason:

```python
fdtd.addprofile({
    "name": "high_res_profile",
    "monitor type": "2D Z-normal",
    "x": 0, "x span": 5e-6,
    "y": 0, "y span": 5e-6,
    "z": 0,
    "override global monitor settings": True,
    "use wavelength spacing": True,
    "use source limits": False,
    "wavelength center": 1.55e-6,
    "wavelength span": 50e-9,
    "frequency points": 51,
})
```

Common reasons to override:

- A field monitor needs finer spectral resolution than the power
  monitors used for the bulk of the spectrum.
- A monitor only cares about a sub-band of the source spectrum.
- A movie monitor needs a different time-window than other
  time-domain monitors.

Resonator simulations frequently override to use **apodization**
on time-domain monitors so that the long pulse tail (from a
high-Q cavity) does not artificially extend the DFT integration.

## Mode-Expansion Monitor

``addmodeexpansion`` attaches to a field monitor and decomposes
the recorded field into mode amplitudes. Used whenever you need:

- Power coupled into a specific waveguide mode (rather than total
  power through a plane).
- Per-mode S-parameters from a non-port monitor.

Workflow:

1. Add a 2D field monitor that spans the waveguide cross-section.
2. ``addmodeexpansion`` over the same plane; link it to the monitor
   via the ``"monitors for expansion"`` property.
3. Set the modal cross-section (``"mode selection"``) the same way
   a mode source picks its mode.
4. After ``run()``, read ``getresult("<mode_expansion_name>",
   "expansion for ...")`` and index ``"a"`` (forward) and ``"b"``
   (backward) amplitudes.

Ports already do this internally -- use mode expansion only when
you cannot use a port (e.g., multi-mode analysis at a non-port
plane).

## Reduce Before You Print

``_lum_print_json`` truncates arrays larger than ``max_array_size``
(200,000 by default) to a ``{"__truncated__": True, ...}`` stub
(see ``fdtd_run_and_results`` large-array safety). For 3D field
monitors **always reduce inside the subprocess** before printing:

```python
fdtd = _lum_get("device")
E = fdtd.getelectric("profile")            # ndarray (Nx, Ny, Nz, Nf, 3)
intensity_xy = (abs(E) ** 2).sum(axis=(2, -1))   # collapse z + vec
_lum_print_json({
    "intensity_xy": intensity_xy.tolist(),
    "x_nm": (fdtd.getdata("profile", "x") * 1e9).flatten().tolist(),
    "y_nm": (fdtd.getdata("profile", "y") * 1e9).flatten().tolist(),
})
```

Or save the heavy array to disk and only print the path:

```python
import numpy as np
fdtd = _lum_get("device")
E = fdtd.getelectric("profile")
out_path = "/tmp/E_profile.npz"
np.savez(out_path, E=E)
_lum_print_json({"saved": out_path, "shape": list(E.shape)})
```

**Never** raise ``max_array_size`` to "fix" a truncation; the
agent's context window cannot absorb a multi-megabyte array
anyway.

See also: ``fdtd_run_and_results``, ``fdtd_sources_monitors``,
``fdtd_far_field_and_grating``.
"""


def get_guidelines_for_fdtd_far_field_and_grating() -> str:
    """FDTD far-field and grating projection: farfield2d/3d, farfieldexact, NA filtering."""
    return """# FDTD Far-Field and Grating Projections

This topic covers turning **near-field** monitor data (recorded on
a plane inside the sim region) into:

- **Far-field projections** -- the angular intensity distribution
  many wavelengths away from the source (antennas, scatterers,
  fiber-coupling efficiency).
- **Grating projections** -- the per-order diffraction efficiency
  of a periodic structure (gratings, metasurfaces).

Read ``fdtd_monitors_and_field_extraction`` first for the monitor
that feeds these projections; read ``fdtd_boundary_conditions``
for the periodic / Bloch setup that grating projections require.

## Far-Field Projection (free-space radiation)

The fast path uses the script commands ``farfield2d`` (line
monitor) or ``farfield3d`` (plane monitor) on a frequency-domain
field monitor:

```python
fdtd = _lum_get("antenna")

# Discover what's on the monitor first (see fdtd_run_and_results
# 'datasets-are-dicts' contract).
_lum_print_json(fdtd.getresult("upper_hemisphere"))

# Project to the far-field hemisphere at a single frequency.
# Last argument controls angular resolution: number of samples in
# the angular grid. Larger -> finer angular detail, more memory.
import numpy as np
# Default is 1 for the first frequency point; adjust if the monitor
# records a custom spectrum.
freq_idx = 1
n_pts = 201
ff = fdtd.farfield3d("upper_hemisphere", freq_idx, n_pts)
_lum_print_json({"farfield_shape": list(np.shape(ff))})
```
# Warning: Do not try to get the farfield result using getresult()
# it is not a dataset and will not be visible until after you run the projection command.
# Always run the projection command first, then inspect the result with getresult()
# If you try to get the farfield result before running the projection command,
# the tool may go into a state where it waits for user input via the GUI
# and does not respond to further commands until you click "OK" on the GUI prompt.

Useful companions:

- ``farfield3dintegrate`` -- integrates the far-field pattern over
  an arbitrary cone (NA, divergence, fraction of power into a
  given solid angle).
- ``farfieldexact`` -- replaces the FFT-based default with an
  exact Green's-function integral. Slower but needed for tilted
  hemispheres, high-NA collection, or when the FFT-based result
  shows artefacts.
- ``farfieldfilter`` / ``farfieldspherical`` -- map the result
  onto a numerical-aperture cone or a (theta, phi) sphere.

Setup tips (Lumerical KB *Far-field projections in FDTD overview*):

- Place the monitor **outside** the immediate near-field of the
  emitter (>= a few wavelengths away) but **inside** the inner
  PML edge.
- For sources above a substrate, the substrate must extend through
  the monitor plane; otherwise the projection assumes the wrong
  background medium.
- A single monitor projects into the half-space facing it; use
  multiple monitors (or a bounding box of six) for full-sphere
  patterns.

## Grating Projection (periodic structures)

For a periodic device under plane-wave (or BFAST) illumination,
the far field is a discrete set of diffraction orders. Compute
them with ``gratingn1`` / ``gratingn2`` (order indices) and
``gratingbloch1`` / ``gratingbloch2`` (Bloch-vector components),
combined with grating-projection helpers:

```python
fdtd = _lum_get("grating")

# Order indices visible in the upper half-space.
n1 = fdtd.gratingn1("T_monitor")     # in-plane order along axis 1
n2 = fdtd.gratingn2("T_monitor")     # in-plane order along axis 2

# Per-order power (transmission) -- normalised diffraction
# efficiency.
T_orders = fdtd.grating("T_monitor")
_lum_print_json({"n1": n1.tolist(),
                 "n2": n2.tolist(),
                 "T_orders": T_orders.tolist()})
```

Companion commands:

- ``gratingpolar`` -- per-order amplitude split into TE / TM
  polarisations.
- ``gratingangle`` -- elevation / azimuth angle of each order
  versus frequency (useful for sweeping incidence angle).
- ``gratingvector`` -- the full diffraction-order k-vectors.

Setup requirements:

- Lateral BCs must be **periodic** (normal incidence) or **Bloch**
  / **BFAST** (angled incidence) -- see
  ``fdtd_boundary_conditions``.
- The monitor must span exactly one unit cell.
- The source must be a plane wave (or BFAST plane wave); finite
  beams produce a continuum, not discrete orders.

## NA / Angular Filtering for Coupling Efficiency

For fiber-coupling or microscope-objective efficiency, project
to the far field then filter by numerical aperture:

```python
fdtd = _lum_get("gc")
ff = fdtd.farfield3d("up", 0, 401)
# Fraction of radiated power inside NA=0.4 cone, centred on +z.
T_NA = fdtd.farfield3dintegrate(ff, 401, 401, 0.4, 0, 0)
_lum_print_json({"T_into_NA": float(T_NA)})
```

See also: ``fdtd_monitors_and_field_extraction``,
``fdtd_boundary_conditions``, ``fdtd_sources_monitors``,
``s_parameter_sweep``.
"""


__all__ = [
    "get_guidelines_for_fdtd_workflow",
    "get_guidelines_for_fdtd_workflow_example",
    "get_guidelines_for_fdtd_sources_monitors",
    "get_guidelines_for_fdtd_run_and_results",
    "get_guidelines_for_fdtd_boundary_conditions",
    "get_guidelines_for_fdtd_mesh_and_convergence",
    "get_guidelines_for_fdtd_source_types",
    "get_guidelines_for_fdtd_monitors_and_field_extraction",
    "get_guidelines_for_fdtd_far_field_and_grating",
]
