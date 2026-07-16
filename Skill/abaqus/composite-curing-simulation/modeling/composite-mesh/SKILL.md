---
name: "composite-mesh"
description: "Generate through-thickness mesh for composite curing simulation. Invoke when user needs C3D8 solid elements, composite mesh, or through-thickness element layout."
---

# Composite Through-Thickness Mesh

This skill generates the through-thickness mesh for the composite (P8) part in curing
simulation. It covers element type selection, through-thickness discretization, in-plane
mesh layout, surface element set identification, and mesh quality considerations.

## Element Type

The composite part uses **C3D8** elements: 8-node linear brick elements with full
integration.

```
*Element, type=C3D8
1, <n1>, <n2>, <n3>, <n4>, <n5>, <n6>, <n7>, <n8>
```

### Why C3D8 (Not C3D8R)

| Property         | C3D8 (Full Integration)        | C3D8R (Reduced Integration)    |
|------------------|--------------------------------|--------------------------------|
| Integration pts  | 8 (2x2x2)                      | 1 (centroid)                   |
| Hourglassing     | No                             | Yes (needs control)            |
| Accuracy         | Higher for bending             | Lower for bending              |
| Use case         | Composite plies (this model)   | Tool/mold (this model)         |

Full integration (C3D8) is preferred for the composite because:
- Each ply is a single element layer through the thickness, so bending accuracy matters
- No hourglass control is needed
- Stress recovery is more accurate at the integration points

The tool/mold part uses C3D8R (reduced integration) because it is a bulk body where
hourglassing is less of a concern and computational efficiency matters more.

## Through-Thickness Direction

The through-thickness direction is along the **X-axis**, spanning from X = -1 to X = 0.
This means the composite thickness is 1 unit (1 mm in model units) in the X direction.

```
X = -1.0  +-----------------------------------+
         |  Ply-1 (element layer 1)           |
X = -0.75+-----------------------------------+   (4-ply: 0.25 mm each)
         |  Ply-2 (element layer 2)           |
X = -0.5 +-----------------------------------+
         |  Ply-3 (element layer 3)           |
X = -0.25+-----------------------------------+
         |  Ply-4 (element layer 4)           |
X = 0.0  +-----------------------------------+
```

The stack direction in `*Solid Section, composite` is **3**, which corresponds to this
X-axis through-thickness direction via the orientation definition.

## 4-Ply Mesh

The 4-ply mesh has 4 elements through the thickness, each 0.25 mm thick (total 1 mm).

### Mesh Statistics

| Property                    | Value   |
|-----------------------------|---------|
| Through-thickness elements  | 4       |
| Ply thickness               | 0.25 mm |
| Total thickness             | 1.0 mm  |
| In-plane nodes per layer    | 605     |
| Total elements              | 2160    |
| Total nodes                 | 3025    |

### Node Layout

- **Through-thickness nodes**: 5 (4 elements + 1)
- **In-plane nodes per layer**: 605
- **Total nodes**: 605 x 5 = 3025

### Element Layout

- **In-plane elements per layer**: 540 (2160 total / 4 layers)
- **Through-thickness layers**: 4
- **Total elements**: 540 x 4 = 2160

## 8-Ply Mesh

The 8-ply mesh has 8 elements through the thickness, each 0.125 mm thick (total 1 mm).

### Mesh Statistics

| Property                    | Value   |
|-----------------------------|---------|
| Through-thickness elements  | 8       |
| Ply thickness               | 0.125 mm|
| Total thickness             | 1.0 mm  |
| In-plane nodes per layer    | 605     |
| Total elements              | 4320    |
| Total nodes                 | 5445    |

### Node Layout

- **Through-thickness nodes**: 9 (8 elements + 1)
- **In-plane nodes per layer**: 605
- **Total nodes**: 605 x 9 = 5445

### Element Layout

- **In-plane elements per layer**: 540 (4320 total / 8 layers)
- **Through-thickness layers**: 8
- **Total elements**: 540 x 8 = 4320

## In-Plane Mesh

The in-plane mesh is shared between the 4-ply and 8-ply models. Both have **605 nodes per
through-thickness layer** and **540 elements per through-thickness layer**.

### In-Plane Layout

| Property                    | Value   |
|-----------------------------|---------|
| Nodes per layer             | 605     |
| Elements per layer          | 540     |
| Shape                       | L-bracket |
| In-plane dimensions         | 100 mm  |

The in-plane mesh defines the L-bracket shape. The through-thickness discretization
(4 or 8 layers) is applied on top of this in-plane mesh by extruding nodes and elements
in the X direction.

## Element Connectivity Pattern

Each C3D8 element has 8 nodes. The connectivity follows the standard Abaqus brick element
node ordering:

```
        8-------7
       /|      /|
      5-------6 |
      | |     | |
      | 4-----|-3
      |/      |/
      1-------2
```

### Node Ordering Convention

| Node | Position              |
|------|-----------------------|
| 1    | Bottom face, corner 1 |
| 2    | Bottom face, corner 2 |
| 3    | Bottom face, corner 3 |
| 4    | Bottom face, corner 4 |
| 5    | Top face, corner 1    |
| 6    | Top face, corner 2    |
| 7    | Top face, corner 3    |
| 8    | Top face, corner 4    |

### Through-Thickness Element Assignment

Element N in the through-thickness direction has nodes at two consecutive X-coordinate
layers. For the 4-ply mesh:

- **Element layer 1** (Ply-1): nodes at X = -1.0 and X = -0.75
- **Element layer 2** (Ply-2): nodes at X = -0.75 and X = -0.5
- **Element layer 3** (Ply-3): nodes at X = -0.5 and X = -0.25
- **Element layer 4** (Ply-4): nodes at X = -0.25 and X = 0.0

For element N (where N is the global element number), the through-thickness layer is:

```python
layer = (N - 1) // in_plane_element_count
# in_plane_element_count = 540 for both 4-ply and 8-ply models
```

### Connectivity Example

For a 4-ply model with 540 in-plane elements per layer:

- Elements 1-540: layer 0 (Ply-1, X from -1.0 to -0.75)
- Elements 541-1080: layer 1 (Ply-2, X from -0.75 to -0.5)
- Elements 1081-1620: layer 2 (Ply-3, X from -0.5 to -0.25)
- Elements 1621-2160: layer 3 (Ply-4, X from -0.25 to 0.0)

Each element's 8 nodes consist of 4 nodes from the lower X layer and 4 nodes from the
upper X layer, with matching in-plane positions.

## Surface Element Sets

Two surface element sets are defined for the composite part. These sets identify the
elements on the outer and inner surfaces of the L-bracket, which are used for contact
and pressure application.

### _com-surface_S1 (Outer Surface)

```
*Elset, elset=_com-surface_S1, internal
<element_numbers>
```

- **Surface face**: S1
- **Location**: Outer surface of the composite (facing the mold)
- **Purpose**: Contact surface (slave) with the tool's `tool-surface`
- **Selection rule**: Every Nth element in the through-thickness direction at the outer
  surface face

### __PickedSurf337_S2 (Inner Surface)

```
*Elset, elset=__PickedSurf337_S2, internal
<element_numbers>
```

- **Surface face**: S2
- **Location**: Inner surface of the composite (away from the mold)
- **Purpose**: Pressure application surface (`*Dsload _PickedSurf337, P, 0.6`)
- **Selection rule**: Every Nth element in the through-thickness direction at the inner
  surface face

### Surface Selection Pattern

For the surface element sets, elements are selected from specific through-thickness
positions. The S1 face corresponds to one side of the through-thickness stack, and the
S2 face corresponds to the other side.

```python
# For a 4-ply model (4 through-thickness layers, 540 elements per layer)
# S1 (outer) elements: layer 0, specific in-plane elements
# S2 (inner) elements: layer 3, specific in-plane elements

# The surface elements are every Nth element where N depends on the
# in-plane mesh pattern at the surface face
```

## How to Identify Surface Elements from Connectivity

To identify which elements belong to the S1 or S2 surface, examine the element
connectivity and node coordinates.

### Step-by-Step Method

1. **Parse all elements**: Read the `*Element, type=C3D8` block to get all element
   connectivities.

2. **Parse all nodes**: Read the `*Node` block to get all node coordinates.

3. **Identify surface nodes**: Find nodes that lie on the outer surface (S1) or inner
   surface (S2) by checking their in-plane coordinates against the bracket boundary.

4. **Identify surface elements**: For each element, check if it has a face (4 nodes)
   that lies entirely on the target surface. The face is identified by the S1 or S2
   face label in the C3D8 element convention.

5. **Build element set**: Collect all element IDs that have a face on the target surface.

### Python Example

```python
def identify_surface_elements(elements, nodes, surface_face='S1'):
    """
    Identify elements on a given surface face.

    Args:
        elements: Dict of {element_id: [node1, ..., node8]}
        nodes: Dict of {node_id: (x, y, z)}
        surface_face: 'S1' (outer) or 'S2' (inner)

    Returns:
        List of element IDs on the surface.
    """
    # C3D8 face definitions: face -> node indices (0-based)
    face_nodes = {
        'S1': [0, 1, 2, 3],  # Bottom face (nodes 1,2,3,4)
        'S2': [4, 5, 6, 7],  # Top face (nodes 5,6,7,8)
    }

    # Determine target X coordinate for the surface
    if surface_face == 'S1':
        target_x = -1.0  # Outer surface (X = -1)
    else:
        target_x = 0.0   # Inner surface (X = 0)

    surface_elements = []
    for elem_id, node_list in elements.items():
        face_idx = face_nodes[surface_face]
        face_node_ids = [node_list[i] for i in face_idx]
        # Check if all face nodes are at the target X coordinate
        all_on_surface = all(
            abs(nodes[nid][0] - target_x) < 1e-6
            for nid in face_node_ids
        )
        if all_on_surface:
            surface_elements.append(elem_id)

    return sorted(surface_elements)
```

### Face Label Reference

| Face | Node Indices (0-based) | Node Numbers (1-based) | Description          |
|------|------------------------|------------------------|----------------------|
| S1   | 0, 1, 2, 3            | 1, 2, 3, 4            | Bottom face (X = -1) |
| S2   | 4, 5, 6, 7            | 5, 6, 7, 8            | Top face (X = 0)     |
| S3   | 0, 1, 5, 4            | 1, 2, 6, 5            | Side face            |
| S4   | 1, 2, 6, 5            | 2, 3, 7, 6            | Side face            |
| S5   | 2, 3, 7, 6            | 3, 4, 8, 7            | Side face            |
| S6   | 3, 0, 4, 7            | 4, 1, 5, 8            | Side face            |

**Note**: The exact face-to-node mapping depends on the element node ordering in the INP
file. Always verify by checking node coordinates against the expected surface position.

## Mesh Quality Considerations for Curing Simulation

### Aspect Ratio

- Through-thickness element size: 0.25 mm (4-ply) or 0.125 mm (8-ply)
- In-plane element size: Should be comparable to avoid high aspect ratios
- Maximum aspect ratio: Keep below 10:1 for accurate stress recovery

### Through-Thickness Resolution

- **4 plies**: Minimum resolution for capturing ply-level behavior. Each ply is a single
  element layer, so stress is constant through the ply thickness.
- **8 plies**: Better resolution for capturing through-thickness stress gradients. Each
  ply is still a single element layer, but the ply thickness is halved.

### Contact Surface Quality

- The S1 surface (outer/contact surface) must have a smooth, continuous element layout
  with no gaps or overlaps.
- Element faces on the contact surface should be as uniform as possible to ensure
  accurate contact pressure distribution.
- Avoid highly distorted elements on the contact surface, as they can cause contact
  convergence issues.

### Temperature Gradient Resolution

- During curing, temperature changes from 25C to 180C and back. The through-thickness
  mesh must be fine enough to capture temperature gradients if they exist.
- For thin composites (1 mm total thickness), the temperature is approximately uniform
  through the thickness, so 4 plies may be sufficient.
- For thicker composites, more through-thickness elements may be needed.

### Mesh Regeneration When Changing Ply Count

When changing from 4 plies to 8 plies (or vice versa), the entire through-thickness mesh
must be regenerated. This is because:

1. The number of through-thickness nodes changes (5 for 4-ply, 9 for 8-ply)
2. The element connectivity changes (different node pairings)
3. The total node and element counts change (3025/2160 for 4-ply, 5445/4320 for 8-ply)
4. All assembly-level sets referencing P8 nodes or elements must be updated

Use the merge strategy described in `modeling/composite-layup` to swap the P8 Part from
a pre-built model with the correct mesh.

## Common Pitfalls

1. **Element type mismatch**: The composite uses C3D8 (full integration), while the tool
   uses C3D8R (reduced integration). Do not swap these.

2. **Through-thickness direction**: The thickness is along the X-axis (from -1 to 0), not
   the Z-axis. This is set by the orientation and stack direction, not by the mesh alone.

3. **Surface face labels**: S1 is the outer/contact surface (X = -1), and S2 is the
   inner/pressure surface (X = 0). Do not confuse these when defining surface element sets.

4. **Node count verification**: After mesh generation, verify the total node count matches
   the expected value (3025 for 4-ply, 5445 for 8-ply). A mismatch indicates a mesh error.

5. **In-plane mesh sharing**: The in-plane mesh (605 nodes per layer, 540 elements per
   layer) is the same for both 4-ply and 8-ply models. Only the through-thickness
   discretization differs.

6. **Element numbering continuity**: Elements are numbered sequentially through the
   through-thickness layers. Element layer boundaries occur at multiples of the in-plane
   element count (540). Use this to assign ply labels correctly.
