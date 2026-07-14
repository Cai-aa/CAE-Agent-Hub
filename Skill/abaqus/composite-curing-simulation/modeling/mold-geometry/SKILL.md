---
name: "mold-geometry"
description: "Create mold/tool geometry for composite curing simulation. Invoke when user needs to set up mold part, tool surfaces, or mold-composite contact geometry."
---

# Mold / Tool Geometry

This skill creates the mold (tool) part for composite curing simulation. The mold is a
separate part in the Abaqus assembly that contacts the composite outer surface during
curing and is removed in the springback step via `*Model Change`.

## Tool Part Structure

The tool is defined as a separate `*Part` block with its own nodes, elements, and sets.
It is independent from the composite (P8) part and has its own node and element numbering
starting from 1.

### Part Definition

```
*Part, name=tool
*Node
1, <x>, <y>, <z>
2, <x>, <y>, <z>
...
*Element, type=C3D8R
1, <n1>, <n2>, <n3>, <n4>, <n5>, <n6>, <n7>, <n8>
2, <n1>, <n2>, <n3>, <n4>, <n5>, <n6>, <n7>, <n8>
...
*End Part
```

### Key Properties

- **Part name**: `tool`
- **Element type**: C3D8R (8-node linear brick, reduced integration) for the mold
- **Node numbering**: Starts from 1, independent from the composite part
- **Element numbering**: Starts from 1, independent from the composite part

**Important**: Both the tool part and the composite (P8) part start their node and element
numbering from 1. When parsing the INP file, you must parse nodes and elements per-part,
not globally. The assembly-level instance prefix (e.g., `tool-1.` or `P8-1.`) distinguishes
them in the assembly context.

## Tool Material

The tool material is defined with elastic properties and thermal expansion. It is a
linear elastic isotropic material representing the mold (typically steel or aluminum).

```
*Material, name=TOOL
*Elastic
69000., 0.33
*Expansion
 2.52e-05,
```

### Material Properties

| Property             | Value      | Description                                  |
|----------------------|------------|----------------------------------------------|
| Young's modulus (E)  | 69000.     | Elastic modulus in model units (MPa)         |
| Poisson's ratio (nu) | 0.33       | Isotropic Poisson's ratio                    |
| Thermal expansion    | 2.52e-05   | Coefficient of thermal expansion (1/C)       |

The thermal expansion coefficient allows the mold to expand and contract with temperature
changes during the curing cycle, which affects the contact pressure and friction behavior.

## Tool Section

The tool elements are assigned the TOOL material via a `*Solid Section` card:

```
*Solid Section, elset=_PickedSet2, material=TOOL
,
```

- **elset**: `_PickedSet2` (element set containing all tool elements)
- **material**: `TOOL` (references the `*Material, name=TOOL` card)
- The data line is empty (just a comma) because no additional section properties are
  needed for a homogeneous solid section.

## Mold Geometry

The mold is an L-shaped bracket that matches the composite part shape but extends beyond
the composite boundaries to ensure full contact coverage.

### Dimensions

| Property              | Composite (P8) | Tool (Mold)    | Description                          |
|-----------------------|----------------|----------------|--------------------------------------|
| In-plane length       | 100 mm         | 120 mm         | Mold extends 10 mm beyond each end   |
| Through-thickness     | 1 mm           | (mold body)    | Mold is a solid body, not a shell    |
| Shape                 | L-shaped       | L-shaped       | Matching bracket geometry            |

The mold extends beyond the composite (e.g., 120 mm vs 100 mm) so that the contact
surface fully covers the composite outer surface even after thermal expansion and
deformation during curing.

### Geometry Layout

```
     +-------------------+
     |                   |
     |    Tool (Mold)    |   120 mm
     |                   |
     +---+---------------+
         |               |
         |  Composite    |   100 mm (inside mold)
         |  (P8)         |
         +---------------+
```

The composite sits inside or against the mold. The mold's inner surface contacts the
composite's outer surface (S1 face) during the curing steps.

## Tool Surfaces

The tool defines two surface element sets that together form the contact surface with the
composite. These surfaces are referenced by the `*Surface` card in the assembly.

### Surface Element Sets

```
*Elset, elset=_tool-surface_S4, internal
<element_numbers>
*Elset, elset=_tool-surface_S6, internal
<element_numbers>
```

### Surface Definitions

| Surface Set           | Face | Description                                    |
|-----------------------|------|------------------------------------------------|
| `_tool-surface_S4`    | S4   | Tool face 4 (one side of the L-bracket)        |
| `_tool-surface_S6`    | S6   | Tool face 6 (other side of the L-bracket)      |

### Assembly-Level Surface

The two element sets are combined into a single surface in the assembly:

```
*Surface, type=ELEMENT, name=tool-surface
_tool-surface_S4, S4
_tool-surface_S6, S6
```

- **Surface name**: `tool-surface`
- **Type**: ELEMENT (element-based surface)
- **Master surface**: This surface acts as the master surface in the contact pair with
  the composite's `com-surface` (slave surface)

The S4 and S6 faces correspond to the two planar faces of the L-shaped mold that contact
the two arms of the L-shaped composite bracket.

## Assembly

The tool part is instantiated in the assembly alongside the composite part.

### Instance Definition

```
*Assembly, name=Assembly
*Instance, name=tool-1, part=tool
<node/element translations if needed>
*End Instance
*Instance, name=P8-1, part=P8
*End Instance
```

### Instance Naming

| Instance | Part | Description                          |
|----------|------|--------------------------------------|
| `tool-1` | tool | Mold instance in the assembly        |
| `P8-1`   | P8   | Composite instance in the assembly   |

When referencing nodes or elements in the assembly context, use the instance prefix:
- Tool node 54 becomes `tool-1.54`
- Composite node 1 becomes `P8-1.1`

## Tool Node Numbering

The tool part's node numbering starts from 1, completely independent from the composite
part. This means both parts can have a node 1, node 2, etc.

### Parsing Rules

1. **Per-part parsing**: When reading the INP file, parse each `*Part` block separately.
   Reset the node and element counters at each `*Part` boundary.

2. **Assembly references**: In the assembly section, nodes and elements are referenced
   with the instance prefix (e.g., `tool-1.54` or `P8-1.3025`). The prefix distinguishes
   which part the node belongs to.

3. **Set definitions**: Sets defined inside a `*Part` block use local numbering. Sets
   defined in the `*Assembly` block use instance-prefixed numbering.

### Example: Tool Reference Node

The tool has a reference node (node 54) used for the springback constraint:

```
# Inside tool Part
*Node
54, <x>, <y>, <z>

# In Assembly, as part of Set-2
*Nset, nset=Set-2, instance=tool-1
54,
```

## Common Pitfalls

1. **Global node numbering**: Do not assume node IDs are unique across parts. Both tool
   and P8 start from node 1. Always use instance prefixes in the assembly context.

2. **Surface face selection**: The S4 and S6 faces must correspond to the actual mold
   faces that contact the composite. If the mold geometry is modified, verify that the
   face labels still point to the correct contact faces.

3. **Mold extension**: The mold must extend beyond the composite to maintain contact
   coverage during thermal expansion. If the mold is too small, the contact pair may
   separate prematurely.

4. **Material assignment**: The tool section must reference `material=TOOL`. If the
   material name is misspelled or the `*Material, name=TOOL` card is missing, Abaqus
   will error.

5. **Thermal expansion**: The tool's thermal expansion coefficient (2.52e-05) affects
   contact pressure during temperature changes. Do not remove the `*Expansion` card
   even if the tool is treated as rigid-like.

6. **Element type**: The tool uses C3D8R (reduced integration), while the composite uses
   C3D8 (full integration). Do not mix these up when editing the INP file.
