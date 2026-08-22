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

"""Product-agnostic Lumerical workflow guidance (``workflow`` topic).

Owns the generic execution model, snippet structure, chunking principle,
parameter management, and "do NOT make assumptions / do NOT invent or
re-run" rules that apply to every Lumerical product (FDTD, MODE, DEVICE,
INTERCONNECT). Product-specific topics live in
:mod:`ansys.lumerical.mcp.contexts.fdtd` (and future
``mode``/``device``/``interconnect`` modules).
"""

from __future__ import annotations


def get_guidelines_for_workflow() -> str:
    """Product-agnostic execution model, snippet structure, chunking, do-not rules."""
    return """# Lumerical MCP Workflow (Generic)

This topic covers the **product-agnostic** rules for driving any
Lumerical simulation (FDTD, MODE, DEVICE, INTERCONNECT) through the
PyLumerical MCP server: the snippet-based execution model, the
chunking strategy, parameter management, and the
"do NOT make assumptions / do NOT invent or re-run" rules.

For product-specific build details (per-product chunked stages,
boundary conditions, source/monitor conventions), pair this topic
with the matching product workflow guide -- currently
``fdtd_workflow``, ``mode_fde_workflow``, ``mode_eme_workflow``, or
``interconnect_workflow``.

For guided-wave optical simulations of photonic elements, also fetch
``pic`` before choosing solver windows, ports, or PML-facing geometry.

**Official lumapi documentation**: https://developer.ansys.com/docs/lumerical/python-lumapi

## Workflow Order

For every Lumerical product, drive the build in this
product-agnostic order. Each step is one or more chunked
``execute_python_code`` snippets (see "Snippet Structure" and
"Chunked Workflow Principle" below); the per-product stage list
refines this for the chosen product.

1. **Open or attach** a session via the ``open_session`` MCP tool
   with the appropriate ``product`` argument.
2. **Configure** the simulation environment.
3. **Add** structures, sources, and monitors.
4. **Save** the project file (``<handle>.save(<path>)``).
5. **Run** the simulation -- only after the user has explicitly
   confirmed (see "Running Simulations" below).
6. **Extract** results via lumapi getters (see the product
   run-and-results topic, e.g. ``fdtd_run_and_results``).

## Execution Model

You do **not** write a standalone ``.py`` file. Every Lumerical
interaction is a short Python snippet sent to the
``execute_python_code`` tool. The server runs each snippet inside a
single, long-lived Python subprocess that has the following names
pre-seeded as globals:

- ``FDTD``, ``MODE``, ``DEVICE``, ``INTERCONNECT`` from
  ``ansys.lumerical.core`` (already imported).
- ``_lumerical_sessions`` -- live registry of open handles, keyed by
  the ``name`` you chose at ``open_session`` time.
- ``_lum_get(name)`` -- returns the live Lumerical handle for
  ``name``.
- ``_lum_print_json(obj, *, max_array_size=200_000, indent=None)``
  -- serializes numpy arrays / complex / dict / list and prints one
  JSON document. This is the **only** way structured data leaves
  the subprocess; everything else only escapes as ``print()``-ed
  text.
- ``_lum_open`` / ``_lum_close`` / ``_lum_list`` /
  ``_lum_close_all`` -- prefer the top-level ``open_session`` /
  ``close_session`` / ``list_sessions`` MCP tools instead of
  calling these helpers directly.

Never write ``import lumapi`` or instantiate ``lumapi.FDTD()`` (or
``MODE`` / ``DEVICE`` / ``INTERCONNECT``) inside a snippet. The
``open_session`` MCP tool already constructed the handle; reach it
with ``_lum_get(name)``.

## Printed JSON Is a Snapshot, Not the Live Value

``_lum_print_json`` lossy-converts Python values to JSON for transport
back to the agent. The shape you read in the printed output is **not**
the shape of the live Python object that the next snippet runs
against.

- ``numpy.ndarray`` is serialized as a nested JSON list, but the live
  value is still an ndarray. Use array operations (``arr[:, 0, 0]``,
  ``np.abs(arr)``, ``np.angle(arr)``) in follow-up code, not
  ``[x[0] for x in arr]``.
- Python / numpy ``complex`` is serialized as
  ``{"real": ..., "imag": ...}``, but the live value is a
  ``complex128`` scalar. Use ``.real``, ``.imag``, ``abs(z)``,
  ``np.angle(z)`` -- never index a complex scalar like a dict.

```python
S = fdtd.getresult("FDTD::ports::Through", "S")["S"]   # complex128 ndarray, shape (N, 1)

# WRONG -- treats the JSON serialization as the live shape.
T = np.array([abs(x[0]["real"] + 1j * x[0]["imag"]) ** 2 for x in S])

# RIGHT -- S is already a numpy complex array.
T = np.abs(S[:, 0]) ** 2
```

## Snippet Structure

Every ``execute_python_code`` snippet should follow this shape:

```python
lum = _lum_get("<session_name>")    # variable name is your choice;
                                    # by convention "fdtd" / "mode" /
                                    # "device" / "ic" matches the product

# ... lumapi calls against `lum` ...

_lum_print_json({"stage": "<what this snippet did>", "ok": True})
```

Notes:

- The first line grabs the live handle. The session must already be
  open via ``open_session(name="<session_name>", product="...")``.
- The final ``_lum_print_json(...)`` is the snippet's return value
  to the agent. Use a small status dict for setup stages; use
  ``_lum_print_json(<handle>.getresult(...))`` to return real data.
- **Variables persist across snippets.** A ``waveguide_width`` set
  in one ``execute_python_code`` call is still bound when the next
  snippet runs against the same MCP server, which is what makes
  chunking cheap.

## Chunked Workflow Principle

Prefer many small ``execute_python_code`` calls -- one per build
stage -- over a single mega-snippet. Why chunk: if stage N fails,
you fix and retry stage N only; earlier stages' state lives on in
the subprocess. The product-specific stage list lives in the
matching product workflow topic (see ``fdtd_workflow``,
``mode_fde_workflow``, ``mode_eme_workflow``, or
``interconnect_workflow``).

Keep each snippet compact and structurally simple. In practice,
snippets that mix long loops, nested ``try`` / ``except`` blocks,
and decorative blank lines are harder to debug when the downstream
runtime rejects or parses them incorrectly. If a stage wants more than one
tight code block, split it into another snippet instead of forcing a
single large submission.

## Parameter Management & Python Style

All user-configurable parameters belong in the **parameters**
snippet (the early-stage snippet), declared before any geometry or
sources reference them. Use descriptive names (``waveguide_width``,
not ``w``), group related values together, document units inline,
and follow PEP 8. **Use SI units (meters, seconds, hertz) by
default**, unless the user explicitly specifies otherwise. Keep
each snippet focused on one build stage. Let lumapi exceptions
propagate -- the MCP envelope already captures the traceback.

## Running Simulations

``run()`` is the universal entry point for launching a Lumerical
simulation. Every product (FDTD, MODE, DEVICE, INTERCONNECT) exposes
it as a Python method on the live handle. The no-argument form
``<handle>.run()`` uses the solver and resource configured in the
project file. It **blocks until the simulation finishes**, **returns
no data**, and **raises** on solver failure -- let the exception
propagate so the MCP envelope captures the traceback; do not wrap
``run()`` in ``try`` / ``except``.

When ``run()`` returns, all simulation results are written back into
the project file currently loaded on the handle (the GUI then
re-loads it). Always call ``<handle>.save(<path>)`` **before**
``run()`` so a file exists on disk for the results to be saved into.

**Pause and ask the user to confirm before calling ``run()``.** A
solver call can take minutes (longer for sweeps) and overwrites the
project file in place.

```python
fdtd = _lum_get("straight_wg")
fdtd.save(save_path)          # results are written back into this file
fdtd.run()                    # blocks; raises on solver error
_lum_print_json({"stage": "ran", "ok": True})
```

Once a simulation is run, the solver goes into ANALYSIS mode and no
simulation objects can be added or modified (Except for the "Analysis"
tab of analysis groups). You must call ``switchtolayout()`` before
modifying any objects. Note that any available results will be lost
once the solver is switched back to LAYOUT mode.

## Plot Theme

When generating matplotlib plots from Lumerical results, follow the
project colormap conventions.

- **Default 2D map** (continuous, no sign convention): ``"turbo"``
  -- the project-preferred general-purpose colormap.
- **Signed field components** (``Re(E)``, ``Im(E)``, ``Re(H)``, ...):
  ``"coolwarm"`` with symmetric limits ``vmin=-V, vmax=+V`` (where
  ``V = float(np.max(np.abs(field)))``) so zero maps to the neutral
  white centre.
- **Intensity / power** (non-negative -- ``|E|^2``, transmission,
  source profiles): ``"turbo"`` with the lowest sample pinned to
  **black**, ``vmin=0``.

## Critical Instructions: Do NOT Make Assumptions

If any parameter, specification, or requirement is not explicitly
provided, **STOP and ask** -- do not guess. Specifically, ask
before choosing:

- **Units** for any dimensional parameter (nm vs. um vs. m).
- **Material properties** (refractive indices, dispersion model,
  wavelength) -- do not silently substitute literature values.
- **Simulation settings**: mesh accuracy, boundary conditions,
  wavelength point count, simulation time.
- **Save path** for the project file.
- **Background medium**: most solvers default to vacuum
  (``n = 1``); air is ``n ~= 1.000293``. The difference is usually
  below numerical noise -- substitute and say so, or add an
  explicit material; never substitute silently.

If a prompt asks for an element's ``notes`` or similar free-text
metadata and that field is empty, fall back to authoritative nearby
metadata such as ``description``, library path, prefix, and the
verified property table. Do not invent missing notes.

## Command Discovery: Use getcommands() Before Inventing

When you need to know what commands are available for a given product,
call ``getcommands()`` on the handle. It returns a newline-delimited
string of **every** lumapi command available in the current session.
This covers all lumapi commands for adding objects, setting properties,
extracting results, and controlling sweeps.

Filter the result for the category you need before calling any command:

```python
all_cmds = handle.getcommands().splitlines()

# Examples of targeted filtering:
add_cmds   = [c for c in all_cmds if c.startswith("add")]
get_cmds   = [c for c in all_cmds if c.startswith("get")]
set_cmds   = [c for c in all_cmds if c.startswith("set")]
bc_cmds    = [c for c in all_cmds if "bc" in c.lower()]
mon_cmds   = [c for c in all_cmds if "monitor" in c.lower()]

_lum_print_json({"add": add_cmds, "bc": bc_cmds, "monitor": mon_cmds})
```

Replace ``handle`` with the actual session handle (``fdtd``, ``mode``,
``device``, etc.). Never guess or invent any command name from memory --
always confirm via ``getcommands()`` first.

## Critical Instructions: Do NOT Invent or Re-run

1. **Don't re-import seeded modules.** ``FDTD`` / ``MODE`` /
   ``DEVICE`` / ``INTERCONNECT`` are already pre-imported. Never
   write ``import ansys.lumerical.core`` in a snippet.
2. **Use the MCP tools for session lifecycle.** Use
   ``open_session`` / ``close_session``, not ``_lum_open`` /
   ``_lum_close`` from inside ``execute_python_code``. Calling the
   helpers directly desyncs the server registry from the subprocess
   registry.
3. **Datasets, discovery, and re-running** are product-specific:
   the dataset-is-a-dict contract for ``getresult``, the
   ``<handle>.eval("<lsf>;")`` escape hatch, and the ``run()``-once
   / ``switchtolayout`` rules live in ``fdtd_run_and_results``.
   Fetch that topic before extracting any simulation results.

See also:

- generic workflow companions: ``geometry``, ``materials``, ``pic``,
  ``sweeps``, ``nested_sweeps``, ``s_parameter_sweep``
- FDTD setup/results: ``fdtd_workflow``, ``fdtd_sources_monitors``,
  ``fdtd_run_and_results``
- FDTD deep dives: ``fdtd_boundary_conditions``,
  ``fdtd_mesh_and_convergence``, ``fdtd_source_types``,
  ``fdtd_monitors_and_field_extraction``,
  ``fdtd_far_field_and_grating``
- MODE: ``mode_fde_workflow``, ``mode_fde_results``,
  ``mode_eme_workflow``
- INTERCONNECT: ``interconnect_workflow``, ``interconnect_simulation``
"""


__all__ = ["get_guidelines_for_workflow"]
