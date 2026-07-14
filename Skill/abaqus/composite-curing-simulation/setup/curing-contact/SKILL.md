---
name: "curing-contact"
description: "Define contact pairs and friction for composite curing simulation: mold-composite contact (S1↔S4+S6), temperature-dependent friction (0.45→0.2→0.169), HARD contact property. Invoke when setting up contact, friction, or mold interaction in curing models."
---

# Curing Contact Setup

Define the frictional contact between the composite (P8-1) and the mold (TOOL-1). This is the physical mechanism that constrains the composite during curing and creates asymmetric springback upon demolding.

## When to Invoke

- User asks to set up contact between composite and mold
- User mentions "接触", "摩擦", "模具接触", "contact pair"
- User needs to change friction coefficients
- User encounters contact-related convergence issues

## Contact Pair Definition

```
*Surface, type=ELEMENT, name=com-surface
P8-1.S1                      # Composite outer surface (contact with mold)

*Surface, type=ELEMENT, name=tool-surface
TOOL-1.S4, S6                # Mold contact surfaces

*Contact Pair, interaction=INTER-1, type=SURFACE TO SURFACE
com-surface, tool-surface    # Master: tool, Slave: composite
```

**Surface assignments**:

| Surface | Part | Element Face | Role |
|---------|------|-------------|------|
| `com-surface` | P8-1 (composite) | S1 (outer) | Slave surface |
| `tool-surface` | TOOL-1 (mold) | S4 + S6 | Master surface |

**Why S1 on composite?**
- S1 is the element face on the outer surface of the composite
- This is the face that physically touches the mold
- S2 is the inner surface (where pressure is applied)

**Why S4+S6 on TOOL?**
- The mold is an L-shaped bracket with two contact faces
- S4 and S6 correspond to the two inner faces of the mold L-shape
- Both faces must be included to capture full contact

## Contact Interaction Property

```
*Surface Interaction, name=INTER-1
*Friction
0.45                         # Step vis: viscous state friction
*Surface Behavior, pressure-overclosure=HARD
```

## Temperature-Dependent Friction

Friction changes with material state (temperature-dependent). Each step has a different friction coefficient:

| Step | Temperature Range | Material State | Friction Coefficient |
|------|------------------|----------------|---------------------|
| vis | 25°C → 150°C | Viscous (rubbery) | 0.45 |
| rub | 150°C → 180°C | Rubbery | 0.20 |
| glassy | 180°C → 25°C | Glassy (cured) | 0.169 |
| sp | 25°C | — | N/A (contact removed) |

**Physics behind friction change**:
- **Viscous (0.45)**: High friction because resin is viscous and sticky; composite strongly adheres to mold
- **Rubbery (0.20)**: Lower friction as resin becomes more rubbery; some slip occurs
- **Glassy (0.169)**: Lowest friction as material vitrifies; cured composite can slide more freely on mold

**How to implement per-step friction**:
```
*Step, name=vis
*Change Friction, interaction=INTER-1
0.45, 

*Step, name=rub
*Change Friction, interaction=INTER-1
0.20, 

*Step, name=glassy
*Change Friction, interaction=INTER-1
0.169, 
```

## HARD Contact Behavior

```
*Surface Behavior, pressure-overclosure=HARD
```

- **HARD**: Standard hard contact — no penetration allowed, no tension
- Pressure transfers only when surfaces are in contact
- Gap opens when pressure goes to zero (no adhesion)

## Contact in Springback Step (sp)

In the sp step, contact is **completely removed** via Model Change:

```
*Step, name=sp
*Model Change, remove
TOOL-1.EL                    # Remove mold elements
*Model Change, remove
TOOL-1, com-surface          # Remove composite contact surface assignment
*Model Change, remove
TOOL-1, tool-surface         # Remove tool contact surface assignment
```

After Model Change:
- No contact pair exists
- No friction
- Composite is free to deform (constrained only by Set-2)
- Residual stresses drive springback deformation

## Why Contact Creates Asymmetric Springback

1. **Friction varies spatially**: Different regions of the composite experience different normal pressures, leading to varying frictional resistance
2. **L-bracket geometry**: The corner region has higher contact pressure than the arm tips, creating non-uniform constraint
3. **Thermal expansion**: During heating, the composite expands and slides against the mold; friction resists this sliding asymmetrically
4. **Demolding release**: When the mold is removed, the stored frictional energy releases unevenly, causing asymmetric deformation
5. **Result**: Maximum displacement at free edges (arm tips), minimum at the corner — this is the correct physical pattern

## P8_only vs P8_mold Contact Comparison

| Aspect | P8_mold (Correct) | P8_only (Incorrect) |
|--------|-------------------|---------------------|
| Contact pair | com-surface ↔ tool-surface | None |
| Friction | 0.45 → 0.2 → 0.169 | None |
| Contact behavior | HARD | None |
| Demolding | Model Change removes contact | No demolding |
| Composite constraint | Friction (allows slip) | ENCASTRE (no slip) |
| Springback pattern | Asymmetric (correct) | Center-symmetric (wrong) |

## Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| Penetration in ODB | Contact not properly defined | Verify surface assignments (S1 on composite, S4+S6 on tool) |
| No springback | Contact not removed in sp | Add `*Model Change, remove` for TOOL elements and surfaces |
| Convergence issues | Friction too high | Check friction values: 0.45/0.2/0.169 for vis/rub/glassy |
| Symmetric deformation | No contact (P8_only model) | Use P8_mold_V2.inp with proper contact pair |
| CPRESS = 0 everywhere | Wrong surface pair | Verify master/slave assignment; tool is master |
