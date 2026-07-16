# Curing Load Setup

## Description

Define pressure loads for composite curing simulation. Invoke when user needs to apply pressure on composite surface during curing.

## Pressure Application Surface

Pressure is applied on the **inner surface** of the composite, NOT the outer/contact surface.

- **_PickedSurf337** (S2 of composite): Pressure application surface (inner face).
- The contact surface (com-surface, S1) is on the opposite face and is NOT used for pressure application.

### Surface Identification

- **S1**: Outer face of composite (contact surface with mold) - used for contact pair.
- **S2**: Inner face of composite (opposite to contact face) - used for pressure application.

The pressure represents the autoclave pressure applied to the composite during curing. It is applied on the inner surface so that it pushes the composite against the mold, ensuring proper contact and compaction.

## Load Definition

The pressure load is defined using the `*Dsload` (distributed surface load) keyword:

```
*Dsload
_PickedSurf337, P, 0.6
```

- **_PickedSurf337**: The surface name (inner face of composite, S2).
- **P**: Pressure load type (normal pressure on the surface).
- **0.6**: Pressure magnitude = 0.6 MPa (typical autoclave curing pressure).

## Pressure Application Schedule

The pressure is applied only during specific steps of the curing cycle:

### vis Step (Viscous State)

```
*Dsload
_PickedSurf337, P, 0.6
```

- Pressure = 0.6 MPa applied during the viscous (high-temperature) step.
- The pressure compacts the composite against the mold while the resin is in a low-viscosity state.

### rub Step (Rubbery State)

```
*Dsload
_PickedSurf337, P, 0.6
```

- Pressure = 0.6 MPa maintained during the rubbery step.
- The pressure continues to hold the composite against the mold as the material transitions to a rubbery state.

### glassy Step (Glassy State)

No pressure is applied in the glassy step. The pressure is implicitly removed because it is not re-specified. Abaqus carries forward loads from previous steps unless they are modified or removed.

However, since the glassy step represents cooling to room temperature, the pressure should be explicitly removed to avoid carrying it into the springback step.

### sp Step (Springback)

The pressure is explicitly removed using `op=NEW`:

```
*Dsload, op=NEW
```

- **op=NEW**: With no data lines following, this removes all previously applied distributed loads.
- This ensures no pressure acts on the composite during springback, allowing the part to deform freely after the tool is removed.

## Pressure Removal Summary

| Step | Pressure (MPa) | Action |
|------|---------------|--------|
| vis  | 0.6           | Apply pressure |
| rub  | 0.6           | Maintain pressure |
| glassy | 0 (implicit) | Pressure not re-specified |
| sp   | 0 (explicit)  | op=NEW removes all loads |

## Notes

- The pressure magnitude (0.6 MPa) is a typical autoclave pressure for composite curing. Adjust based on the specific curing cycle requirements.
- The pressure must be applied on the inner surface (S2) to push the composite against the mold. Applying pressure on the contact surface (S1) would cause numerical issues with the contact algorithm.
- The `op=NEW` option in the sp step is essential to remove the pressure before springback analysis. Without it, the pressure would continue to act on the free composite, producing incorrect springback results.
- In the glassy step, the pressure is implicitly removed (not re-specified). If the analysis uses `op=MOD` (default), the load from the previous step is carried forward. Verify the load state in the glassy step based on the specific analysis requirements.
- The distributed load type `P` applies a uniform pressure normal to the surface. For non-uniform pressure, use a analytical field or tabular amplitude.
