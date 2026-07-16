---
name: "curing-bc"
description: "Define boundary conditions for composite curing simulation: mold contact constraints (TOOL U1=0, U2=0), springback Set-2 constraints, and Model Change demolding. Invoke when setting up BCs, constraints, or boundary conditions for curing models with mold."
---

# Curing Boundary Conditions

This skill defines all boundary conditions for the P8_mold curing model, including the critical distinction between mold-constrained (correct) and ENCASTRE-constrained (incorrect) approaches.

## When to Invoke

- User asks to set up boundary conditions for a curing model
- User mentions "约束", "边界条件", "固支", "模具约束"
- User needs to define Set-2 for springback
- User encounters constraint-related issues (e.g., symmetric deformation)

## Critical: Two Constraint Paradigms

### Correct: Mold Contact Constraint (P8_mold)

The mold (TOOL-1) is fixed in space, and the composite is held only by friction contact with the mold. This allows the composite to slide and expand during curing, which is the real physical mechanism.

**Curing steps (vis/rub/glassy):**
```
*Boundary
_PickedSet328, 1, 1          # TOOL U1 = 0
_PickedSet327, 2, 2          # TOOL U2 = 0
```

**Springback step (sp):**
```
*Boundary, op=NEW
Set-2, 1, 1                   # Composite inner corner U1 = 0
Set-2, 2, 2                   # Composite inner corner U2 = 0
Set-2, 3, 3                   # Composite inner corner U3 = 0
```

The `op=NEW` keyword **removes** all previous boundary conditions and applies only Set-2 constraints. This is critical — without `op=NEW`, the mold constraints would remain active during springback.

### Incorrect: ENCASTRE Constraint (P8_only)

The composite inner surface is fully fixed (all 6 DOFs) throughout the entire simulation. There is no mold, no contact, no demolding.

```
*Boundary
_PickedSet246, 1, 6           # ENCASTRE: U1=U2=U3=UR1=UR2=UR3=0
```

This produces center-symmetric deformation because:
1. No friction → no asymmetric resistance to thermal expansion
2. No demolding → no physical springback mechanism
3. Full rotational fixity prevents any angle change at the constraint

## TOOL Boundary Conditions (P8_mold Only)

The TOOL part has two constraint sets:

| Set Name | DOF | Value | Purpose |
|----------|-----|-------|---------|
| `_PickedSet328` | U1 | 0 | Prevent mold sliding in X |
| `_PickedSet327` | U2 | 0 | Prevent mold sliding in Y |

**Why only U1 and U2?**
- The mold is a rigid body; fixing U1 and U2 prevents translation
- U3 (vertical) is constrained by the contact algorithm
- Rotations are implicitly constrained by the rigid body definition
- This allows the mold to "press down" on the composite via contact pressure

## Set-2: Springback Constraint

Set-2 is a node set on the composite part at the **inner corner** of the L-bracket. It is activated only in the sp (springback) step.

**Purpose**: Prevent rigid body motion after the mold is removed. Without Set-2, the composite would float freely after demolding.

**How Set-2 is defined**:
- Nodes at the inner corner of the L-bracket (near origin)
- Selected by coordinate proximity: X ≈ 0 AND Y ≈ 0
- Typically 9-25 nodes (the corner mesh region)

**When mesh changes**: Set-2 must be redefined by matching node coordinates, not node IDs, because renumbering occurs with mesh changes.

## Model Change: Demolding Process

The sp step includes `*Model Change` to remove the TOOL elements and contact pair:

```
*Step, name=sp
*Model Change, remove
TOOL-1.EL                   # Remove all TOOL elements
*Model Change, remove
TOOL-1, com-surface         # Remove contact surface
*Model Change, remove
TOOL-1, tool-surface        # Remove contact surface
*Boundary, op=NEW
Set-2, 1, 3                  # Apply springback constraint
```

**Sequence in sp step**:
1. Remove TOOL elements (mold disappears)
2. Remove contact surfaces (no more contact)
3. Remove old boundary conditions (TOOL constraints gone)
4. Apply Set-2 constraints (new BC for springback)
5. Allow residual stresses to relax → springback deformation

## Pressure Boundary Condition

Pressure (0.6 MPa) is applied on **S2** (inner surface) during curing and removed in sp step:

```
** Curing steps (vis/rub/glassy):
*Dsload
P8-1.S2, P, 0.6              # 0.6 MPa on inner surface

** Springback step (sp):
** (no *Dsload — pressure removed)
```

**Why S2 (inner surface)?**
- The pressure represents autoclave pressure pressing the composite against the mold
- S2 is the surface facing the mold (inner surface)
- S1 is the outer surface (contact surface with mold)

## Boundary Condition Summary Table

| Step | TOOL-1 BC | Composite BC | Contact | Pressure |
|------|-----------|-------------|---------|----------|
| vis | U1=0, U2=0 | None (friction-held) | Active | 0.6 MPa (S2) |
| rub | U1=0, U2=0 | None (friction-held) | Active | 0.6 MPa (S2) |
| glassy | U1=0, U2=0 | None (friction-held) | Active | None |
| sp | **Removed** (Model Change) | Set-2: U1=U2=U3=0 (op=NEW) | **Removed** | None |

## Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| Center-symmetric deformation | Using ENCASTRE instead of mold contact | Use P8_mold_V2.inp template |
| Composite floats away in sp step | Missing Set-2 constraint | Add `*Boundary, op=NEW` with Set-2 |
| Mold still visible in sp step | Missing `*Model Change, remove` | Add Model Change for TOOL elements |
| Over-constraint in sp step | TOOL BCs not removed | Use `op=NEW` keyword to clear old BCs |
| No springback deformation | Pressure not removed in sp | Remove `*Dsload` in sp step |
