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

"""S-parameter matrix sweep guidance shared by FDTD and MODE (``s_parameter_sweep``).

Both products expose ``addsweep(3)`` and the same
``runsweep``/``getsweepresult``/``exportsweep`` lifecycle for
extracting a full N x N S-matrix; the per-task property set differs
(documented inline). Snippets use the ``fdtd`` handle name for
brevity. The ``mode`` handle works identically (substitute the
appropriate name).
"""

from __future__ import annotations


def get_guidelines_for_s_parameter_sweep() -> str:
    """S-parameter matrix sweep recipe and Y-branch example for FDTD and MODE."""
    return """# S-Parameter Matrix Sweep (FDTD and MODE)

A single ``<handle>.run()`` only excites the one source port, so
its per-port ``"S"`` datasets give you one column of the S-matrix
-- never the full N x N matrix. For multi-port devices (Y-branch,
MZI, directional coupler, ring resonator, ...) the full matrix
comes from the **S-parameter matrix sweep** (``addsweep(3)``),
which launches N simulations (one per active source row) and
assembles the matrix from their per-port results. The same tool
is available in MODE with the EME solver.

## Prereqs

- ``sweeps`` -- generic sweep lifecycle, ``deletesweep``
  idempotent rebuild pattern, dict-as-struct convention,
  discovery primitives.
- ``fdtd_run_and_results`` -- the dataset-is-a-dict contract that
  ``getsweepresult`` shares with ``getresult``.

The snippets below use the ``fdtd`` handle name for brevity; the
``mode`` handle works identically (substitute the appropriate
name).

## When to Use the Sweep

- The user asks for the full S-matrix, all S_ij, "all the
  S-parameters", a reciprocity / passivity check, or a Touchstone
  / INTERCONNECT export.
- The device has more than two ports and the user wants the
  cross-couplings (e.g. S31 and S21 of a Y-branch, or every entry
  of a 4x4 directional-coupler matrix).
- The user wants the matrix at multiple wavelengths from a single
  command.

If the user only needs one S-parameter (e.g. just S21 of a
straight waveguide), a single ``fdtd.run()`` plus per-port
``getresult("FDTD::ports::output", "S")`` is enough -- the sweep
is overkill.

## FDTD vs. MODE Property Differences

Both flavours are created with ``addsweep(3)``; the editable
properties on the resulting task differ. Discover the live set
with ``?setsweep("s-parameter sweep");``.

- **FDTD**: ``name``, ``excite all ports``, ``calculate group
  delay``, ``invert sign``, ``map from``, ``active``, ``port``,
  ``mode``, ``map vector``, ``auto symmetry``, ``export setup``.
  The sweep launches one simulation per active row in the
  S-matrix setup table.
- **MODE / EME**: ``name``, ``number of points``, ``calculate
  group delay``, ``group delay wavelength``, ``parameter label``,
  ``start wavelength``, ``stop wavelength``, ``include group
  delay``. The sweep is over wavelength; one EME solve per
  wavelength point yields all S-matrix entries simultaneously.

## Setup, Run, Collect

The sweep is a layout-time analysis task that lives alongside the
ports group in the project file. Run it **after** the ports have
been added and the project saved, and **before** ``fdtd.run()`` --
the sweep launches its own simulations.

```python
fdtd = _lum_get("ybranch")

fdtd.deletesweep("s-parameter sweep")        # idempotent rebuild
fdtd.addsweep(3)                             # 3 = S-parameter matrix sweep
fdtd.setsweep("s-parameter sweep", "Excite all ports", True)

fdtd.runsweep("s-parameter sweep")
_lum_print_json({"stage": "s_parameter_sweep", "ok": True})
```

Notes:

- ``addsweep(3)`` is the matrix-sweep flavour; the task is named
  ``"s-parameter sweep"`` by default.
- With ``"Excite all ports" = true`` the table auto-populates
  with every (port, mode) pair and launches one simulation per
  row.
- For symmetric devices, set ``"auto symmetry" = true`` instead
  -- this halves the simulation count (see the Y-branch example
  below).
- ``runsweep`` blocks until every child simulation finishes, so
  the tool-call lock is held for the full duration. Warn the
  user about the expected wall-clock cost before kicking it off.
- The sweep does its own ``run`` internally; do **not** call
  ``fdtd.run()`` afterwards for the same project.

## Available Results

After ``runsweep`` returns, the matrix lives on the sweep task
(not on the FDTD root). Use ``fdtd.getsweepresult`` (not
``fdtd.getresult``). The shipped results are:

- ``"S matrix"`` -- dataset whose ``"S"`` attribute is a
  ``complex128`` ndarray of shape ``(N_freq, N_ports, N_ports)``.
  This **is** the full matrix, in contrast to the per-port
  ``(N_freq, N_modes)`` shape on ``FDTD::ports::<port>``.
- ``"S parameters"`` -- per-element dataset (``S11``, ``S12``,
  ..., ``SNN``), each a complex array vs. frequency.
- ``"S diagnostic"`` -- passivity and reciprocity violation vs.
  frequency.
- ``"group delay"`` -- only present if ``"calculate group
  delay"`` was enabled.

Always dump first, then index (see ``fdtd_run_and_results``).

## Worked Y-Branch Example

A 3-port symmetric Y-branch with fundamental TE and TM modes at
each port has 6 rows in the S-matrix setup table. Symmetry maps
the two output ports onto one another, so only 4 simulations are
actually needed -- ``"auto symmetry" = true`` configures the
mapping automatically.

```python
fdtd = _lum_get("ybranch")

fdtd.deletesweep("s-parameter sweep")
fdtd.addsweep(3)
fdtd.setsweep("s-parameter sweep", "Excite all ports", False)
fdtd.setsweep("s-parameter sweep", "auto symmetry", True)

fdtd.runsweep("s-parameter sweep")
_lum_print_json({"stage": "ybranch_sweep_done", "ok": True})
```

Collect, then verify the ~50/50 power split between the two
output arms:

```python
fdtd = _lum_get("ybranch")
matrix = fdtd.getsweepresult("s-parameter sweep", "S matrix")
_lum_print_json(matrix)            # confirm shapes / port order
```

```python
import numpy as np
fdtd = _lum_get("ybranch")
matrix = fdtd.getsweepresult("s-parameter sweep", "S matrix")
S = matrix["S"]                              # (N_freq, N_ports, N_ports)

# Port indices depend on the order ports appear in the table --
# always confirm via the dump above before hard-coding 0/1/2.
S21 = S[:, 1, 0]
S31 = S[:, 2, 0]
insertion_loss_dB = -10 * np.log10(np.abs(S21) ** 2 + np.abs(S31) ** 2)

diag = fdtd.getsweepresult("s-parameter sweep", "S diagnostic")
_lum_print_json({
    "lambda_nm": (matrix["lambda"] * 1e9).flatten().tolist(),
    "S21_dB": (20 * np.log10(np.abs(S21))).tolist(),
    "S31_dB": (20 * np.log10(np.abs(S31))).tolist(),
    "insertion_loss_dB": insertion_loss_dB.tolist(),
    "max_passivity": float(np.max(diag["passivity"])),
    "max_reciprocity_err": float(np.max(diag["reciprocity"])),
})
```

## Touchstone / INTERCONNECT Export

The same sweep task writes a ``.dat`` (Lumerical / INTERCONNECT)
or Touchstone file via ``exportsweep``. Do this **after**
``runsweep`` so the export sees populated data:

```python
fdtd = _lum_get("ybranch")
fdtd.exportsweep("s-parameter sweep", "/tmp/ybranch.dat")
_lum_print_json({"exported": "/tmp/ybranch.dat"})
```

For phase-sensitive INTERCONNECT circuits, enable
``"calculate group delay"`` on the sweep before ``runsweep``;
the exported file will include the group-delay header that the
Optical N-Port S-Parameter element's group-delay filter option
expects.

## Summary

- The full N x N S-matrix is **not** available from a single
  ``fdtd.run()``. Use the S-parameter matrix sweep.
- Recipe: ``deletesweep`` / ``addsweep(3)`` / configure with
  ``setsweep`` / ``runsweep`` / ``getsweepresult``.
- The matrix-sweep ``"S"`` array has shape
  ``(N_freq, N_ports, N_ports)`` -- in contrast to per-port
  ``"S"`` at ``FDTD::ports::<port>`` which is
  ``(N_freq, N_modes)``.
- Use ``"auto symmetry" = true`` for symmetric devices to halve
  the simulation count; confirm port ordering by dumping the
  ``"S matrix"`` dataset first.
- The sweep does its own ``run`` internally; do not also call
  ``fdtd.run()`` for the same project.
- Use ``exportsweep`` for Touchstone / INTERCONNECT export.

See also: ``sweeps``, ``fdtd_workflow``, ``fdtd_sources_monitors``,
``fdtd_run_and_results``.
"""


__all__ = ["get_guidelines_for_s_parameter_sweep"]
