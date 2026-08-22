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

"""Dictionary-based ``addX`` syntax shared by FDTD, MODE, and DEVICE.

All three products use the same lumapi calls (``addrect``,
``addcircle``, ``addsphere``, ...) and the same dictionary form.
Substitute the appropriate handle name (``fdtd``, ``mode``,
``device``) for the snippets below.
"""

from __future__ import annotations


def get_guidelines_for_geometry() -> str:
    """Dictionary-based ``addX`` syntax for Lumerical layout objects (FDTD/MODE/DEVICE)."""
    return """# Geometry

This topic covers the dictionary-based syntax used to add layout
objects (``addrect``, ``addcircle``, ``addsphere``, ``addring``,
``addpoly``, ``addgroup``, ...) in Lumerical. **FDTD**, **MODE**, and
**DEVICE** use the same lumapi calls and the same dictionary form;
substitute the appropriate handle name (``fdtd``, ``mode``, ``device``)
for the snippets below.

## Use Dictionary-Based Object Creation

When adding objects, pass a single dict to the ``addX`` call instead
of issuing sequential ``set()`` calls. The dict form is more concise,
easier to read, and faster for the agent to generate correctly.

### Preferred (dictionary-based)

```python
fdtd.addrect({
    "name": "substrate",
    "material": "SiO2 (Glass) - Palik",
    "x": 0, "x span": 10e-6,
    "y": 0, "y span": 5e-6,
    "z min": -2e-6, "z max": 0,
})
```

The same dict-form rule applies to every layout-object constructor
(``addcircle``, ``addsphere``, ``addring``, ``addpoly``,
``addgroup``, ``addimport``, ...) and to MODE and DEVICE handles
(``mode.addrect({...})`` or ``device.addrect({...})``).

## Property-Name Conventions

Property keys passed in the dict use the **lumapi string names** with
spaces preserved -- ``"x span"``, ``"z min"``, ``"mesh order"``,
``"first axis"``, ``"rotation 1"``. Do **not** convert them to
Python identifiers (``"x_span"`` will be silently ignored). When in
doubt, dump the object's properties with
``_lum_print_json(fdtd.getnamed("<name>"))`` to see the exact key
spellings the live session expects.

## GDS and Process-File Workflows

When a task provides both **GDS** geometry and a **process file**,
prefer **Layer Builder** over manually reconstructing extruded solids
from raw polygons.

- Treat the lithographic pattern as an **XY-plane** layout.
- Treat thickness, etch depth, and stack build-up as the **Z-axis** part
    of the model.
- Do not invent layer-to-material, layer-to-thickness, or etch mappings
    if the GDS layer map or process file is incomplete.

A Layer Builder can be added and configured fully from script.

### Add a Layer Builder Object

Use ``addlayerbuilder`` to create the Layer Builder object in the active
simulation.

### Pattern Geometry

- ``loadgdsfile`` loads GDS geometry into the Layer Builder object.
- ``getcelllist`` and ``getlayerlist`` return the available cells and
    layers from the loaded GDS.
- ``savegdsfile`` exports the Layer Builder pattern geometry back to GDS.
- ``set`` / ``setnamed`` and ``get`` / ``getnamed`` can write or inspect
    polygon vertices through the ``"geometry"`` property.

### Process Layers

There are two valid setup patterns:

- Build layers from scratch with ``addlayer``, then configure them with
    ``setlayer`` and inspect them with ``getlayer``.
- Load the full stack from a process file with ``loadprocessfile`` and
    export it with ``saveprocessfile``.

In addition to the normal process-layer properties, ``setlayer`` can also
override graphical opacity with ``"pattern alpha"`` and
``"background alpha"``.

### Rotation and Background

- Access Layer Builder rotation with normal ``set`` / ``setnamed`` calls.
    The only axis property you should set is ``"first axis"``, and its only
    valid value is ``"z"``.
- Access background geometry with normal ``set`` / ``setnamed`` and
    ``get`` / ``getnamed`` calls on the Layer Builder object.

Prefer Layer Builder when the workflow is fundamentally a process-driven
layout plus stack definition. Prefer manual geometry objects only when the
task is not actually a Layer Builder flow.
"""


__all__ = ["get_guidelines_for_geometry"]
