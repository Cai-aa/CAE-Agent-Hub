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

"""DEVICE finite-element IDE guideline topics.

Owns guidelines for the Lumerical finite-element solver environment (DEVICE IDE),
which hosts HEAT, CHARGE, FEEM, and DGTD:

- ``device_workflow`` -- chunked build/setup stages shared across all
  finite-element solvers: materials, geometry, solver addition, simulation
  region, boundary conditions, monitors, run, and results.
- ``device_materials`` -- model-material creation, property-family
  assignment (EM / CT / HT), and database discovery.
- ``device_simulation_region`` -- simulation-region ownership model,
  boundary types (Open / Closed / Shell), and solver linkage.
"""

from __future__ import annotations


def get_guidelines_for_device_workflow() -> str:
    """Finite-element IDE workflow shared by HEAT, CHARGE, FEEM, and DGTD."""
    return """# DEVICE Workflow (HEAT / CHARGE / FEEM / DGTD)

This topic covers the **build/setup and run/results** workflow for the
Lumerical finite-element design environment, which hosts the HEAT, CHARGE,
FEEM, and DGTD solvers.

**Read ``workflow`` first** for the generic execution model, snippet
structure, and the do-not-assume / do-not-invent rules.

For material creation, fetch ``device_materials``.
For simulation-region setup, fetch ``device_simulation_region``.
For geometry objects, fetch ``geometry``.

## Finite-Element Build Stages (Chunked)

Follow this order. Each stage maps to one ``execute_python_code`` snippet.

### Stage 1 -- Parameters

Declare all user-configurable values (solver type, domain extents, material
names, bias voltages, temperatures, mesh settings, etc.) with SI units.

### Stage 2 -- Create Model Materials

Build model materials before adding geometry. See ``device_materials``
for the full pattern. Key points:

- Use ``addmodelmaterial()`` then ``set("name", ...)`` to create the model.
- Attach property families with ``addmaterialproperties(family, db_name)``.
  Only add families the solver actually needs (``HT`` for thermal,
  ``CT`` for electrical, ``EM`` for optical).
- After each ``addmaterialproperties`` call, re-select the model material
  before adding the next family -- the selection shifts to the inserted
  property object.

```python
device.addmodelmaterial()
device.set("name", "silicon")
device.addmaterialproperties("HT", "Si (Silicon)")
device.select("materials::silicon")
device.addmaterialproperties("CT", "Si (Silicon)")
```

### Stage 3 -- Create Geometry

Use the shared ``geometry`` workflow (``addrect``, ``addcircle``, etc.).
Assign model materials to geometry objects with ``setnamed``:

```python
device.setnamed("Si_layer", "material", "silicon")
```

### Stage 4 -- Add Solver

Add the finite-element solver object with the appropriate ``add*`` command:

| Solver  | lumapi command  |
|---------|-----------------|
| HEAT    | ``addheatsolver()``   |
| CHARGE  | ``addchargesolver()`` |
| FEEM    | ``addfeemsolver()``   |
| DGTD    | ``adddgtdsolver()``   |

Solver objects have fixed names assigned by Lumerical and cannot be renamed.
After adding, configure its general settings directly using the fixed name:

```python
device.addheatsolver()
# The solver is accessible as "HEAT" -- do not attempt to rename it.
```

### Stage 5 -- Set Simulation Region

The simulation domain is a separate Simulation Region object, not the solver
itself. See ``device_simulation_region`` for the full pattern. Key points:

- New projects start with one Simulation Region already present.
- Set boundary types (``Open``, ``Closed``, or ``Shell``) per face independently.
- Set the solver's ``simulation region`` property to the exact region name:

```python
device.setnamed("HEAT", "simulation region", "HEAT simulation region")
```

### Stage 6 -- Add Doping (CHARGE only)

Doping profiles are required for CHARGE simulations and are added as children
of the CHARGE solver object. Skip this stage for HEAT, FEEM, and DGTD.

Common doping profiles and the corresponding constructors include
* constant: ``adddope()``
* diffusion: ``adddiffusion()``
* implant: ``addimplant()``

After adding, configure the doping region by name:

```python
device.adddope()
device.set("name", "p_doping")
device.setnamed("CHARGE::p_doping", "dopant type", "p")
device.setnamed("CHARGE::p_doping", "concentration", 1e23)  # in 1/m^3
```

### Stage 7 -- Add Boundary Conditions

Boundary conditions are children of the solver's ``boundary conditions``
sub-object. After adding a BC, it can be found under the solver's object tree and configured by
name.

```python
device.addtemperaturebc()
device.set("name", "Tbc")
device.setnamed("HEAT::boundary conditions::Tbc", "temperature", 330)
```

Some BC commands apply to multiple solvers. For example, ``addtemperaturebc()`` applies to both HEAT
and CHARGE. The correct solver needs to be defined in the syntax if multiple solvers are present.
For example, if both HEAT and CHARGE are present, the syntax is:

```python
device.addtemperaturebc("HEAT")  # when CHARGE solver is also present
```

Use ``device.getcommands()`` to discover the exact ``add*bc`` command
names available in the current session before adding any boundary condition.
Exception is device.addelectricalcontact() which is used to add electrical contact
boundary conditions for CHARGE solver. This command is only available when CHARGE solver is present
in the project.

### Stage 8 -- Add Monitors

Monitors are also children of the solver object. After adding a monitor,
it can be found under the solver's object tree and configured by name.

```python
device.addchargemonitor()
device.set("name", "charge_monitor")
device.setnamed("CHARGE::charge_monitor", "integrate total charge", True)
```

Monitors can also apply to multiple solvers. Set the solver name in the syntax when needed:

```python
device.addtemperaturemonitor("CHARGE")  # when HEAT, FEEM, or DGTD solver is also present
```

Use ``device.getcommands()`` to discover the exact ``add*monitor`` command
names available in the current session before adding any monitor.

### Stage 9 -- Save

```python
device.save(path)
```

### Stage 10 -- Run (requires explicit user confirmation)

```python
device.run("HEAT")          # pass the solver name
```

Do NOT call ``run()`` without explicit user confirmation. Finite-element
runs can be long and overwrite the project file.

### Stage 11 -- Collect Results

Results come from two sources:

1. **Monitors** -- call ``getresult(solver_name::monitor_name, dataset)`` on the monitor
   object.
2. **Solver object** -- the solver itself also exposes result datasets. Use
   ``getresult(solver_name, dataset)`` to access them.

Always inspect available datasets first:

```python
_lum_print_json({"monitor_results": device.getresult("temp_monitor"),
                 "solver_results": device.getresult("HEAT")})
```

Then index into specific fields only after confirming the dataset structure.

## Solver-Specific Notes

- **HEAT**: physics is thermal conduction / convection. BCs include
  fixed temperature, heat flux, and convection. Key result: temperature
  distribution.
- **CHARGE**: physics is drift-diffusion carrier transport. BCs include
  electrical contacts (Ohmic / Schottky). Key results: carrier densities,
  electric field, current density, band structure.
- **FEEM**: finite-element electromagnetic solver for waveguide modes.
  Workflow is similar but solver is optical; BCs are electromagnetic.
- **DGTD**: discontinuous Galerkin time-domain solver for broadband EM.
  Sources and monitors resemble FDTD but mesh and BCs are
  finite-element style.

## See Also

``device_materials``, ``device_simulation_region``, ``geometry``,
``workflow``.
"""


def get_guidelines_for_device_materials() -> str:
    """Material-library creation and database discovery for DEVICE finite-element solvers."""
    return """# Device Materials

This topic covers material handling in the DEVICE finite-element solver environment used by
finite-element solvers such as HEAT, CHARGE, FEEM, and DGTD.
Unlike FDTD and MODE, these workflows should not assume that a built-in database
material is assigned directly to a geometry object.

Read ``workflow`` first for the generic execution model and do-not-assume rules,
and ``device_workflow`` for the DEVICE-specific build stages. Use this topic whenever
the task involves building or inspecting material models in the DEVICE
solver or IDE.

## Material Model Pattern

In the DEVICE environment, create a model material in the materials object
library first, then attach the required property families to that material.

The standard pattern is:

1. call ``device.addmodelmaterial()``
2. call ``device.set("name", ...)`` to name the model material
3. add the needed property families with ``device.addmaterialproperties(family, db_name)``
4. re-select the model material with ``device.select("materials::<name>")`` before each
   additional property insertion, because the selection shifts to the inserted property
5. assign the model material to geometry with ``device.setnamed(obj, "material", name)``

Representative pattern:

```python
device.addmodelmaterial()
device.set("name", "silicon")
device.addmaterialproperties("EM", "Si (Silicon) - Palik")
device.select("materials::silicon")
device.addmaterialproperties("CT", "Si (Silicon)")
device.select("materials::silicon")
device.addmaterialproperties("HT", "Si (Silicon)")
```

## Property Families

The main property families imported from the DEVICE material databases are:

- ``EM`` for optical or electromagnetic properties
- ``CT`` for conductive or electrical transport properties
- ``HT`` for thermal or heat-transport properties

Only add the families that the requested solver workflow actually needs. For
example, a thermal-only HEAT task may only need ``HT``, while an electro-thermal
CHARGE task may need both ``CT`` and ``HT`` and may also carry ``EM`` data when
the model is coupled to upstream optical workflows.

## Exploring Available Database Entries

Do not guess material names from memory when the task depends on the exact name
present in the DEVICE databases. Use ``addmaterialproperties`` without a
material name to query what is available for each property family. Note that the
query only works when a model material is selected.

In this environment, the query result can come back either as a Python list or
as one newline-delimited string. Normalize it before filtering so the workflow
does not accidentally treat one long string as one material name.

```python
em_names = device.addmaterialproperties("EM")
ct_names = device.addmaterialproperties("CT")
ht_names = device.addmaterialproperties("HT")
if isinstance(em_names, str):
    em_names = em_names.splitlines()
if isinstance(ct_names, str):
    ct_names = ct_names.splitlines()
if isinstance(ht_names, str):
    ht_names = ht_names.splitlines()
_lum_print_json({"EM": em_names, "CT": ct_names, "HT": ht_names})
```

This is the DEVICE analogue of ``getmaterial()`` in the FDTD and MODE
material workflow.

## Selection Hygiene

After ``addmaterialproperties(...)`` the selection moves from the model material
to the inserted property object. Re-select the material model before adding the
next property family.

```python
device.select("materials::silicon")
device.addmaterialproperties("CT", "Si (Silicon)")
```

If a snippet fails while adding multiple properties, the first cheap check is to
inspect whether the selection is still on the material model rather than on one
of its child properties.

## When To Query Versus When To Reuse

Prefer querying the database names when:

- the user names a material loosely rather than with the exact database string
- the workflow needs to know whether a property family exists for a given
  material in ``EM``, ``CT``, or ``HT``
- a shared model material is being assembled from several databases and name
  mismatches would be easy to miss
- the database query returned one newline-delimited string and needs
  ``splitlines()`` before exact-name filtering

Reuse an already-known exact database string only when it has already been
confirmed in the current session or is explicitly given by the user.

## See Also

``workflow`` for the generic execution model. ``device_workflow`` for HEAT / CHARGE / FEEM / DGTD
solver setup. ``device_simulation_region`` for simulation-region and boundary setup.
"""


def get_guidelines_for_device_simulation_region() -> str:
    """Simulation-region setup shared by HEAT, CHARGE, FEEM, DGTD, and peers."""
    return """# Device Simulation Region

This topic covers simulation-region setup for HEAT, CHARGE, FEEM, and DGTD.

Read ``workflow`` first for the generic execution model and do-not-assume
rules, and ``device_workflow`` for the DEVICE-specific build stages.

## What Matters For MCP Workflows

- The simulation region is a separate object from the solver.
- A solver does not define its computational domain by itself.
- Link each solver to a region explicitly by name.

Use this topic whenever the task depends on domain size, boundary behavior,
or background material.

## Region Definition (Script-Facing)

Define the region with explicit geometry and boundary intent:

- choose dimension (2D or 3D) (Note that default is 2D Y-Normal)
- set per-face boundary behavior (``Open``, ``Closed``, ``Shell``)
- set region extents explicitly (center + span or min/max)
- set background material when using a fully closed domain

Do not infer domain extents from nearby solids. Set region geometry directly.

## Solver-To-Region Linkage

Bind each solver to the intended region via the solver's
``simulation region`` property:

```python
device.setnamed("CHARGE", "simulation region", "CHARGE simulation region")
```

Use the same pattern for HEAT, FEEM, DGTD, and any additional finite-element
solver in the project.

## Quick Validation Checks

- Verify solver-to-region mapping first.
- Verify boundary mode on each face (especially mixed boundary setups).
- Verify background material is consistent with solver physics and boundary
  choice.

## See Also

``workflow`` for the generic execution model. ``device_materials`` for shared model-material
creation and database discovery. ``device_workflow`` for HEAT / CHARGE / FEEM / DGTD solver
configuration, simulation region setup, boundary conditions, monitors, and results.
"""


__all__ = [
    "get_guidelines_for_device_workflow",
    "get_guidelines_for_device_materials",
    "get_guidelines_for_device_simulation_region",
]
