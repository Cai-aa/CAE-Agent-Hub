---
name: "composite-layup"
description: "Define composite layup with ply angles, thickness, and count. Invoke when user asks to change ply angles, modify layup, or adjust ply count for curing simulation."
---

# Composite Layup Definition

This skill defines and modifies the composite layup for curing simulation. It covers ply
angles, ply thickness, ply count, and the orientation system used by the `*Solid Section,
composite` card in Abaqus.

## Ply Definition Format

The composite layup is defined inside the P8 Part using `*Solid Section, composite`. Each
ply is specified on a single data line with five fields:

```
*Solid Section, elset=CompositeLayup-1-1, composite, orientation=Ori-1, stack direction=3, layup=CompositeLayup-1
<thickness>, 3, COM, <angle>, Ply-<N>
```

### Field Breakdown

| Field | Value    | Description                                                        |
|-------|----------|--------------------------------------------------------------------|
| 1     | thickness| Ply thickness in model units (mm). E.g., `1.` or `0.250`           |
| 2     | 3        | Stack direction index (always 3 for this model)                    |
| 3     | COM      | Material name (references `*Material, name=COM` with UMAT)         |
| 4     | angle    | Ply angle in degrees. E.g., `0.`, `45.`, `-45.`, `90.`             |
| 5     | Ply-N    | Ply label (N is the ply number, starting from 1)                   |

All plies are listed consecutively under a single `*Solid Section` card. The element set
(`CompositeLayup-1-1`) covers all elements in the composite part.

### Example: 4-Ply Layup (1 mm each)

```
*Solid Section, elset=CompositeLayup-1-1, composite, orientation=Ori-1, stack direction=3, layup=CompositeLayup-1
1., 3, COM, 0., Ply-1
1., 3, COM, 0., Ply-2
1., 3, COM, 0., Ply-3
1., 3, COM, 0., Ply-4
```

### Example: 8-Ply Layup (0.25 mm each)

```
*Solid Section, elset=CompositeLayup-1-1, composite, orientation=Ori-1, stack direction=3, layup=CompositeLayup-1
0.250, 3, COM, 0., Ply-1
0.250, 3, COM, 0., Ply-2
0.250, 3, COM, 0., Ply-3
0.250, 3, COM, 0., Ply-4
0.250, 3, COM, 0., Ply-5
0.250, 3, COM, 0., Ply-6
0.250, 3, COM, 0., Ply-7
0.250, 3, COM, 0., Ply-8
```

## How to Change Ply Angles

Changing ply angles is a **text-level edit**. You modify the 4th field (angle in degrees)
in each ply data line. No mesh regeneration is required.

### Step-by-Step

1. Locate the `*Solid Section, composite` block in the INP file.
2. For each ply line, replace the 4th field with the desired angle.
3. Save the INP file. The mesh and element connectivity remain unchanged.

### Regex Pattern for Automated Replacement

When automating ply angle changes with Python, use the following regex pattern to replace
a specific ply's angle:

```python
import re

def change_ply_angle(content, ply_num, angle):
    """
    Replace the angle of a specific ply in the *Solid Section composite block.

    Args:
        content: Full INP file content as a string.
        ply_num: Ply number (integer, e.g., 1 for Ply-1).
        angle: New angle in degrees (float, e.g., 45.0).

    Returns:
        Updated INP content as a string.
    """
    pattern = r'(0\.250,\s*3,\s*COM,\s*)([0-9.\-]+)(,\s*Ply-' + str(ply_num) + ')'
    replacement = r'\g<1>' + str(float(angle)) + r'\g<3>'
    return re.sub(pattern, replacement, content)
```

**Note**: The regex above assumes 0.25 mm ply thickness (8-ply model). For a 4-ply model
with 1 mm thickness, adjust the thickness portion of the pattern:

```python
# For 4-ply model (1.0 mm per ply)
pattern = r'(1\.,\s*3,\s*COM,\s*)([0-9.\-]+)(,\s*Ply-' + str(ply_num) + ')'
```

### Example Layup Sequences

#### [0]*8 Layup (all 0 degrees)

```
0.250, 3, COM, 0., Ply-1
0.250, 3, COM, 0., Ply-2
0.250, 3, COM, 0., Ply-3
0.250, 3, COM, 0., Ply-4
0.250, 3, COM, 0., Ply-5
0.250, 3, COM, 0., Ply-6
0.250, 3, COM, 0., Ply-7
0.250, 3, COM, 0., Ply-8
```

#### [45/-45]*4 Layup (alternating 45 and -45 degrees)

```
0.250, 3, COM, 45., Ply-1
0.250, 3, COM, -45., Ply-2
0.250, 3, COM, 45., Ply-3
0.250, 3, COM, -45., Ply-4
0.250, 3, COM, 45., Ply-5
0.250, 3, COM, -45., Ply-6
0.250, 3, COM, 45., Ply-7
0.250, 3, COM, -45., Ply-8
```

#### [90]*8 Layup (all 90 degrees)

```
0.250, 3, COM, 90., Ply-1
0.250, 3, COM, 90., Ply-2
0.250, 3, COM, 90., Ply-3
0.250, 3, COM, 90., Ply-4
0.250, 3, COM, 90., Ply-5
0.250, 3, COM, 90., Ply-6
0.250, 3, COM, 90., Ply-7
0.250, 3, COM, 90., Ply-8
```

## How to Change Ply Count

Changing ply count is **not** a text-level edit. The number of through-thickness elements
in the mesh must match the ply count. You cannot simply add or remove ply lines in the INP
file, because the element connectivity and node layout are tied to the mesh topology.

### Why Mesh Regeneration Is Required

Each ply corresponds to one layer of C3D8 elements through the thickness. The `*Solid
Section, composite` card assigns one ply per element layer. If you add a ply line without
adding a corresponding element layer, Abaqus will error because there are more plies than
element layers. If you remove a ply line, elements will be left without a ply assignment.

### Approach: Merge Strategy

When the reference INP has 4 plies but 8 plies are needed (or vice versa), use the merge
strategy to swap the P8 Part from a pre-built model that already has the correct mesh.

1. **Source P8 model** (correct ply count, e.g., `P8_only_recipe_1.inp` for 8 plies):
   Contains the correct through-thickness mesh and composite layup.

2. **Reference model** (e.g., `Job-0_0_0_0.inp`): Contains the mold, contact, loads,
   and steps that should be preserved.

3. **Merge**: Replace the reference model's P8 Part (nodes, elements, connectivity,
   composite layup) with the source model's P8 Part. Then update all assembly-level sets
   that reference P8 nodes or elements.

### Key Updates Needed When Merging

- Replace P8 Part: nodes, elements, connectivity, and `*Solid Section, composite` block
- Update `_PickedSet333` node/element ranges (e.g., 3025 to 5445 nodes, 2160 to 4320 elements)
- Replace `_com-surface_S1` elset (composite outer surface elements)
- Replace `__PickedSurf337_S2` elset (composite inner surface elements)
- Replace `_PickedSet334/335/336` nsets (reference points)
- Match `Set-2` nodes by coordinate matching (inner corner nodes for springback constraint)
- Remove `SET-EXPORT` nset if present (reference-specific)

## 4-Ply vs 8-Ply Comparison

| Property                  | 4-Ply Model              | 8-Ply Model              |
|---------------------------|--------------------------|--------------------------|
| Ply thickness             | 1.0 mm each              | 0.25 mm each             |
| Total thickness           | 4.0 mm                   | 2.0 mm                   |
| Through-thickness elements| 4                        | 8                        |
| Total elements            | 2160                     | 4320                     |
| Total nodes               | 3025                     | 5445                     |
| In-plane nodes per layer  | 605                      | 605                      |
| Ply angle granularity     | Coarse (4 angles)        | Fine (8 angles)          |
| Mesh generation           | Built into reference INP | Requires separate model  |

**Note**: The in-plane mesh (605 nodes per through-thickness layer) is shared between the
4-ply and 8-ply models. Only the through-thickness discretization differs.

## Orientation Definition

The ply angles are interpreted relative to a local coordinate system defined by the
`*Orientation` card. The orientation must be defined before the `*Solid Section, composite`
card that references it.

### Orientation Card

```
*Orientation, name=Ori-1, system=RECTANGULAR
<origin_x>, <origin_y>, <origin_z>,
<a1_x>, <a1_y>, <a1_z>,
<a2_x>, <a2_y>, <a2_z>
*Distribution Table, name=Ori-Table
ANGLES,
*Distribution, location=ELEMENT, table=Ori-Table
<elset_name>, <angle_offset>
```

### Orientation Parameters

| Parameter | Value        | Description                                              |
|-----------|--------------|----------------------------------------------------------|
| name      | Ori-1        | Orientation name (referenced by `*Solid Section`)        |
| system    | RECTANGULAR  | Rectangular coordinate system                            |
| Origin    | 0., 0., 0.   | Origin of the local coordinate system                    |
| a-axis    | Defined per model | Direction of the local 1-axis (fiber reference direction) |
| b-axis    | Defined per model | Direction of the local 2-axis (transverse direction)     |

The stack direction (3rd field in `*Solid Section`) corresponds to the local 3-axis, which
is the through-thickness direction. Ply angles are measured as rotations about this axis.

### Distribution Table for Discrete Orientations

When different element sets need different orientation offsets, use a distribution table.
The table maps element sets to angle offsets:

```
*Distribution Table, name=Ori-Table
ANGLES,
*Distribution, location=ELEMENT, table=Ori-Table
Ply-1-elset, 0.
Ply-2-elset, 0.
Ply-3-elset, 0.
Ply-4-elset, 0.
```

In this model, all element layers share the same base orientation (Ori-1). The ply-specific
angles come from the 4th field in each `*Solid Section, composite` data line, not from the
distribution table. The distribution table is used when the base orientation itself needs to
vary by element set.

## Common Pitfalls

1. **Ply count mismatch**: Adding ply lines without corresponding element layers causes
   Abaqus errors. Always regenerate the mesh when changing ply count.
2. **Angle format**: Angles must include a decimal point (e.g., `0.` not `0`, `45.` not
   `45`). Abaqus parses these as floating-point values.
3. **Stack direction**: The stack direction is always 3 for this model. Changing it will
   misalign the ply assignment with the mesh.
4. **Material name**: The material name in the ply line must match the `*Material, name=`
   card exactly (case-sensitive). For this model, it is `COM`.
5. **Ply numbering**: Ply labels (Ply-1, Ply-2, ...) must be sequential and unique. Gaps
   or duplicates will cause errors.
