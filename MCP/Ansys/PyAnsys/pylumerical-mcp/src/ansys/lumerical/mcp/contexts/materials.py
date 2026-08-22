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

"""Material-selection guidance shared by FDTD and MODE (``materials`` topic).

Both products use the same material database and ``addmaterial``/``setmaterial``
lumapi calls. The markdown below is therefore neutral
in its handle naming (``fdtd`` shown for brevity, ``mode`` works
identically).
"""

from __future__ import annotations


def get_guidelines_for_materials() -> str:
    """Built-in versus custom materials, anisotropic input. Applies to FDTD and MODE."""
    return """# Materials

This topic covers material selection in Lumerical **FDTD** and
**MODE**, which share the same material database and lumapi calls
(``addmaterial``, ``setmaterial``). Use the appropriate handle name
(``fdtd``, ``mode``) for the snippets below.

## Prefer Built-in Materials

Prefer entries from the built-in material library (e.g.
``"Si (Silicon) - Palik"``, ``"SiO2 (Glass) - Palik"``,
``"Au (Gold) - CRC"``) over custom materials. Only create a custom
material when:

- The user specifically requests a material that isn't in the
  library.
- The user provides material data that differs from the built-in
  models.
- A simplified constant-index dielectric is genuinely needed (e.g.
  for a quick sanity check or to match an analytic comparison).

## Querying the Material Library

### Get a list of all available materials
```python
material_names = fdtd.getmaterial()
_lum_print_json({"material_names": material_names})
```

### Get the properties of a specific material
```python
material_properties = fdtd.getmaterial("Si_custom")
_lum_print_json({"material_properties": material_properties})
```

### Get a property of a specific material
```python
material_property = fdtd.getmaterial("Si_custom", "Refractive Index")
_lum_print_json({"material_property": material_property})
```

## Creating Custom Materials

``addmaterial()`` returns a **name** (a string) that you must use
to set the material's permanent name. After the name is set, address
the material by that name for every subsequent property assignment.

### Correct pattern

```python
temp_mat_name = fdtd.addmaterial("Dielectric")
fdtd.setmaterial(temp_mat_name, "name", "Si_custom")
fdtd.setmaterial("Si_custom", "Refractive Index", core_index)
```

## Anisotropic Materials

Anisotropic materials are described by a 3x3 permittivity tensor
``eps_ij``. Three input modes are supported in FDTD and MODE; pick
the simplest one that matches the user's data.

### 1. Per-structure anisotropic indices (simplest)

If the structure's material is left as ``<Object defined dielectric>``
(or any other dielectric assignment on the structure), set the
structure's ``"index"`` property to a **semicolon-separated** list of
the diagonal indices ``n_xx;n_yy;n_zz``:

```python
fdtd.addrect({
    "name": "uniaxial_slab",
    "material": "<Object defined dielectric>",
    "index": "1.5;2.0;1.5",          # n_xx ; n_yy ; n_zz
    "x": 0, "x span": 5e-6,
    "y": 0, "y span": 5e-6,
    "z min": 0, "z max": 1e-6,
})
```

### 2. Diagonal-anisotropic custom material

Use this when several structures share the same diagonal-anisotropic
material, or when a non-trivial dispersion model is needed. Enable
diagonal anisotropy on the material and supply a 3-element index
vector:

```python
temp_mat_name = fdtd.addmaterial("(n,k) Material")
fdtd.setmaterial(temp_mat_name, "name", "uniaxial_n2p0")
fdtd.setmaterial("uniaxial_n2p0", "Anisotropy", 1)              # 1 = diagonal
fdtd.setmaterial("uniaxial_n2p0", "Refractive Index", [1.5, 2.0, 1.5])
# For absorbing materials, also:
# fdtd.setmaterial("uniaxial_n2p0", "Imaginary Refractive Index", [k_x, k_y, k_z])
```

### 3. Fully off-diagonal (general) anisotropy

A general (non-diagonal) tensor must be diagonalized first
(eigenvalue decomposition via lsf ``eig``) and then re-projected with
a **matrix transform grid attribute**. The diagonal eigenvalues go
into the material as in pattern 2; the unitary eigenvector matrix
``U = V'`` is attached as a grid attribute via
``addgridattribute("matrix transform")`` with its ``"U"`` property
set to the conjugate transpose of the eigenvectors.

This is the rarest case (Faraday rotation, MOKE, liquid crystal,
gyrotropic materials). Reach for it only when the user explicitly
asks. See the Ansys docs for the full pattern:
https://optics.ansys.com/hc/en-us/articles/360034394694

See also: ``fdtd_workflow`` (PML, FDTD chunked build),
``workflow`` (generic snippet/chunking rules), ``geometry``,
``fdtd_sources_monitors``, ``fdtd_run_and_results``.
"""


__all__ = ["get_guidelines_for_materials"]
