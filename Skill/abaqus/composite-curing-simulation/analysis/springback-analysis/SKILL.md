# Springback Analysis

## Description

Configure springback analysis with Model Change for mold removal. Invoke when user needs mold removal, springback step, or Model Change setup.

## Content

Springback occurs in the sp (springback) step, which is the 4th and final step of the curing simulation. During this step, the mold/tool is removed and the composite part is allowed to deform freely, constrained only at the Set-2 inner corner.

### Model Change: Remove Contact Pair

The contact pair between the composite surface and the tool surface is removed:

```
*Model Change, type=CONTACT PAIR, remove
com-surface, tool-surface
```

### Model Change: Remove Tool Elements

All tool elements are removed from the analysis using Model Change:

```
*Model Change, remove
_PickedSet329,
```

- `_PickedSet329` = all tool elements (element numbers 1 to 1672)

### Boundary Conditions in sp Step

The sp step uses `op=NEW` which replaces ALL previous boundary conditions:

- **Previous tool BCs removed:** Use an empty `*Boundary, op=NEW` to clear previous tool constraints
- **New constraint applied:** Set-2 is constrained with U1=U2=U3=0

```
*Boundary, op=NEW
Set-2, 1, 1, 0.
Set-2, 2, 2, 0.
Set-2, 3, 3, 0.
```

### Loads in sp Step

- **Pressure removed:** Use `*Dsload, op=NEW` with no data lines to remove all distributed loads

```
*Dsload, op=NEW
```

### Temperature

Temperature is maintained at 25°C during the springback step.

### Result

After mold removal, the composite springs back freely and is constrained only at the Set-2 inner corner. The springback displacement (U1, U2, U3) at the last frame of the sp step represents the final part shape deviation.

### Key Points

- The sp step is the final step where the part is released from the mold
- Model Change must remove both the contact pair AND the tool elements
- Using `op=NEW` on boundary conditions and loads ensures a clean state for springback
- The final deformation is captured in the last frame of the sp step
- This displacement data is used to evaluate part quality and springback deviation
