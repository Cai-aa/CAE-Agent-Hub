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

"""Product-agnostic sweep guidance (``sweeps`` and ``nested_sweeps`` topics).

Owns the generic lifecycle of any analysis task created with
``addsweep`` and configured via the matching ``setsweep`` /
``addsweepparameter`` / ``runsweep`` / ``getsweepresult`` /
``deletesweep`` lsf commands. Applies to FDTD, MODE, and INTERCONNECT.
The S-parameter matrix sweep flavour (``addsweep(3)``) has additional
product-specific rules and a Y-branch worked example in
:mod:`ansys.lumerical.mcp.contexts.s_parameter_sweep`.
"""

from __future__ import annotations


def get_guidelines_for_sweeps() -> str:
    """Product-agnostic sweep lifecycle: addsweep/setsweep/runsweep/getsweepresult."""
    return """# Lumerical Parametric Sweeps

This topic covers the **product-agnostic** lifecycle of analysis
tasks created with ``addsweep``: parameter sweeps, optimizations,
Monte Carlo analyses, S-parameter matrix sweeps (FDTD and MODE),
and corner sweeps (INTERCONNECT). All flavors share the same
``addsweep``/``setsweep``/``getsweep``/``addsweepparameter``/
``removesweepparameter``/``runsweep``/``getsweepresult``/
``deletesweep`` primitives.

Read ``workflow`` first for the chunked ``execute_python_code``
model and the do-not-assume / do-not-invent rules. For the
S-parameter matrix sweep (``addsweep(3)``) and the Y-branch
worked example, see ``s_parameter_sweep``.

## Dict-as-Struct Convention

``addsweepparameter`` and ``addsweepresult`` accept an lsf
``struct`` payload. Pass it as a Python **dict** -- lumapi
converts it automatically. This is the only sweep-specific
calling convention; otherwise the sweep commands behave like any
other lumapi method (see the examples below).

## Sweep Types

``addsweep(type)`` creates one analysis task as the top-most item
in the Optimizations and Sweeps tree. Pick the right type code:

- ``0`` -- parameter sweep (FDTD, MODE, DEVICE, INTERCONNECT).
  Default task name: ``"sweep"``.
- ``1`` -- optimization (FDTD, MODE). Default task name:
  ``"optimization"``.
- ``2`` -- Monte Carlo analysis (FDTD, MODE). Default task name:
  ``"Monte Carlo analysis"``.
- ``3`` -- S-parameter matrix sweep (FDTD, and MODE with EME).
  Default task name: ``"s-parameter sweep"``. See
  ``s_parameter_sweep``.
- ``4`` -- corner sweep (INTERCONNECT only). Default task name:
  ``"Corner sweep"``.

The default task name is what subsequent ``setsweep`` /
``addsweepparameter`` / ``runsweep`` / ``getsweepresult`` /
``deletesweep`` calls refer to until you rename the task via
``setsweep("<default>", "name", "<new_name>")``.

## Sweep Lifecycle

A typical sweep build follows this fixed order:

1. ``deletesweep("<name>")`` -- idempotent rebuild (see below).
2. ``addsweep(<type>)`` -- create the task.
3. ``setsweep("<name>", "<property>", <value>)`` -- configure.
4. ``addsweepparameter("<name>", <param>)`` -- add swept
   parameters (parameter sweep / optimization / Monte Carlo) or
   S-matrix rows (S-parameter sweep). Skip for default
   "Excite all ports" S-parameter sweeps.
5. ``addsweepresult("<name>", <result>)`` -- add result datasets.
6. ``runsweep("<name>")`` -- launch. Blocks until every child
   simulation completes.
7. ``getsweepresult("<name>", "<result>")`` -- pull results.

Always set both ``"type"`` and ``"number of points"`` on a parameter
sweep.

- ``"Ranges"``: set ``Start`` and ``Stop`` on the parameter payload.
- ``"Values"``: provide the explicit values on the parameter payload.

## Idempotent Rebuild Pattern

``addsweep`` does **not** replace an existing task -- it appends
a new one with an auto-incremented name (``"sweep"``, ``"sweep
1"``, ...). Re-running a setup snippet then silently accumulates
duplicates. Always lead setup with ``deletesweep`` first:

```python
fdtd = _lum_get("device")
fdtd.deletesweep("thickness_sweep")
fdtd.addsweep(0)
fdtd.setsweep("sweep", "name", "thickness_sweep")
fdtd.setsweep("thickness_sweep", "type", "Ranges")
fdtd.setsweep("thickness_sweep", "number of points", 10)
```

``deletesweep`` is a no-op when the named task does not exist,
so the pattern is safe on first run.

## Discovery Primitives

Do not guess property names, parameter names, or result names.
- ``<handle>.getsweep("<name>")`` -- returns a list of sweep properties.
- ``<handle>.getsweepresult("<name>")`` -- returns a list of result datasets.

## Parameter-Sweep Example

Sweep the ``thickness`` property of a structure across 10 values
between 50 nm and 150 nm. ``addsweepparameter`` accepts a struct
with ``Name`` / ``Parameter`` / ``Type`` / ``Start`` / ``Stop`` /
``Units`` fields (or ``Value_1`` ... ``Value_N`` for the "Values"
sweep type). ``addsweepresult`` accepts a struct with ``Name``
(the label used by ``getsweepresult``) and ``Result`` (the
absolute path to a monitor / analysis-group result on a child
simulation, e.g. ``"::model::R::T"``):

```python
fdtd = _lum_get("device")

fdtd.deletesweep("thickness_sweep")
fdtd.addsweep(0)
fdtd.setsweep("sweep", "name", "thickness_sweep")
fdtd.setsweep("thickness_sweep", "type", "Ranges")
fdtd.setsweep("thickness_sweep", "number of points", 10)

fdtd.addsweepparameter("thickness_sweep", {
    "Name": "thickness",
    "Parameter": "::model::AR structure::thickness",
    "Type": "Length",
    "Start": 50e-9,
    "Stop": 150e-9,
    "Units": "nm",
})

fdtd.addsweepresult("thickness_sweep", {
    "Name": "R",
    "Result": "::model::R::T",
})
fdtd.addsweepresult("thickness_sweep", {
    "Name": "T",
    "Result": "::model::T::T",
})

fdtd.runsweep("thickness_sweep")
_lum_print_json({"stage": "sweep_done", "ok": True})
```

To remove an added parameter, use ``removesweepparameter("<task>",
"<parameter_name>")`` (or the row index for S-parameter sweeps).
To remove an added result, use ``removesweepresult("<task>",
"<result_name>")``.

## Result Extraction

``getsweepresult`` returns a Lumerical dataset -- the same
**dict** contract enforced by ``getresult`` (see
``fdtd_run_and_results``).
Always dump first with ``_lum_print_json`` before indexing:

```python
fdtd = _lum_get("device")

result = fdtd.getsweepresult("thickness_sweep", "R")
_lum_print_json(result)            # confirm keys / shapes first
```

Then, in a follow-up snippet, index by string key against the
live (still-typed) ndarray:

```python
import numpy as np
fdtd = _lum_get("device")
result = fdtd.getsweepresult("thickness_sweep", "R")
_lum_print_json({
    "thickness_nm": (result["thickness"] * 1e9).flatten().tolist(),
    "R_mean": float(np.mean(result["T"])),
})
```

See also: ``workflow``, ``s_parameter_sweep``,
``fdtd_run_and_results``.
"""


def get_guidelines_for_nested_sweeps() -> str:
    """Product-agnostic nested sweep workflow based on ``insertsweep``."""
    return """# Lumerical Nested Sweeps

Nested sweeps are hierarchical: create the **inner sweep** first, then
wrap it with an **outer sweep** using ``insertsweep``. Use this when the
task needs **all combinations** of two swept parameters.

Read ``workflow`` first, then ``sweeps`` for the normal ``addsweep``
lifecycle. The only extra command here is ``insertsweep``.

## Core Rule

- create the inner sweep first
- wrap it with ``insertsweep("<child_name>")``
- add the child result to the parent sweep by result name only
- configure and run the outer sweep only
- use ``getsweepresult("<outer_name>", ...)`` on the outer sweep

When a parent sweep exposes a child sweep result, the ``Result`` field is
just the child result name. Do not prepend a hierarchical path such as
``::outer_sweep::inner_sweep::child_result``. Once the child result has been
added to the parent, the parent can access it directly.

## Compact Example

```python
fdtd = _lum_get("device")

fdtd.deletesweep("inner_sweep")
fdtd.addsweep(0)
fdtd.setsweep("sweep", "name", "inner_sweep")

fdtd.insertsweep("inner_sweep")
fdtd.setsweep("sweep", "name", "outer_sweep")

fdtd.addsweepresult("inner_sweep", {
    "Name": "R_inner",
    "Result": "::model::R::T",
})
fdtd.addsweepresult("outer_sweep", {
    "Name": "R",
    "Result": "R_inner"
})

# Propagate child results upward by name only, with no path prefix.
fdtd.runsweep("outer_sweep")
_lum_print_json(fdtd.getsweepresult("outer_sweep"))
```

For deeper nesting, repeat the same pattern one level at a time. If
``bottom_sweep`` defines ``bottom_result_1`` and ``bottom_result_2``, then
``mid_sweep`` should add results that point to ``bottom_result_1`` and
``bottom_result_2`` by name only. Then ``top_sweep`` should add results that
point to the mid-level result names, again by name only. None of these parent
assignments need a sweep path prefix.

Do not separately run the inner sweep after it has been wrapped.
The lower-level result must be added as a result on the parent sweep, and the
final collection happens from the top-level sweep only.


See also: ``workflow``, ``sweeps``, ``s_parameter_sweep``.
"""


__all__ = ["get_guidelines_for_sweeps", "get_guidelines_for_nested_sweeps"]
