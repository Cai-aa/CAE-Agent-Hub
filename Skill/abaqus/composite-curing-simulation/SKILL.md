---
name: "composite-curing-simulation"
description: "Master skill for composite curing simulation with mold contact, friction, temperature, and Model Change springback in Abaqus. Invoke when user asks for curing simulation, springback analysis, composite layup with mold, or UMAT subroutine for composites. Routes to specialized sub-skills."
---

# Composite Curing Simulation

This is the **master routing skill** for composite material curing simulation. It provides an overview and routes to specialized sub-skills for each aspect of the workflow.

## When to Invoke

- User requests composite curing simulation with mold
- User mentions "固化仿真", "脱模回弹", "模具", "铺层"
- User wants to change ply angles or ply count in a curing model
- User needs to run Abaqus with UMAT for composite materials
- User provides a reference INP with mold/contact/temperature and wants to replicate it

## Critical: Mold Constraint vs No-Mold Constraint

**This is the most important distinction in the curing model.** Using the wrong constraint type produces physically incorrect results.

### P8_mold (Correct — With Mold Contact + Demolding)

The correct model includes a TOOL part, friction contact pairs, and Model Change demolding in the sp step. This produces **asymmetric** springback deformation reflecting real physics.

| Feature | P8_mold (Correct) |
|---------|-------------------|
| TOOL part | Present (TOOL-1 instance) |
| Contact pair | `com-surface` (S1) ↔ `tool-surface` (S4+S6), HARD contact |
| Friction | Temperature-dependent: 0.45 → 0.2 → 0.169 |
| Curing constraint | Mold contact (TOOL U1=0, U2=0 via _PickedSet327/328) |
| Demolding | `*Model Change, remove` on TOOL elements + contact pair in sp step |
| Springback constraint | Set-2 (inner corner nodes): U1=U2=U3=0 via `*Boundary, op=NEW` |
| Pressure | 0.6 MPa on S2 (inner surface), removed in sp step |
| Springback contour | **Asymmetric** (max displacement at free edges) |
| Spring-in angle | Positive (0.5°-1.6°), physically correct |

### P8_only (Incorrect — No Mold, ENCASTRE Constraint)

The incorrect model omits the TOOL part and uses ENCASTRE (full fixity) instead of mold contact. This produces **center-symmetric** deformation that does NOT reflect real curing physics.

| Feature | P8_only (Incorrect) |
|---------|---------------------|
| TOOL part | Absent |
| Contact pair | None |
| Friction | None |
| Curing constraint | ENCASTRE (U1=U2=U3=UR1=UR2=UR3=0) on inner surface |
| Demolding | None (no mold to remove) |
| Springback constraint | Same ENCASTRE remains |
| Springback contour | **Center-symmetric** (unphysical) |
| Spring-in angle | Does not reflect real physics |

### Why P8_only is Wrong

1. **No mold contact**: Without the TOOL part, there is no frictional constraint during curing. The composite is artificially fixed via ENCASTRE, which prevents any thermal expansion-driven slip at the mold interface.
2. **No demolding process**: The `*Model Change` step is what creates the physical springback mechanism — releasing the part from the mold allows residual stresses to relax into the final shape. Without it, the model simply releases a fully constrained part.
3. **Center-symmetric artifact**: ENCASTRE creates a symmetric constraint pattern, leading to symmetric deformation. Real curing springback is asymmetric because friction varies across the part surface.
4. **Missing friction history**: The temperature-dependent friction (0.45→0.2→0.169) captures the material state transitions (viscous→rubbery→glassy). Without contact, this physics is entirely absent.

### Template File

- **Correct template**: `P8_mold_V2.inp` — use this for all new simulations
- **Incorrect template**: `P8_only_recipe_1.inp` — do NOT use; archived for reference only

## Skill Architecture

```
composite-curing-simulation/
├── README.md                          # English overview
├── README.zh-CN.md                    # Chinese overview
├── SKILL.md                           # This file (master router)
├── core/
│   └── composite-curing/              # Main routing logic
├── modeling/
│   ├── composite-layup/               # Ply angles, thickness, count
│   ├── mold-geometry/                 # Tool/mold part setup
│   └── composite-mesh/               # C3D8 mesh, through-thickness
├── setup/
│   ├── curing-material/               # UMAT, COM/TOOL materials
│   ├── curing-contact/                # Contact pairs, friction
│   ├── curing-bc/                     # Boundary conditions, Set-2
│   ├── curing-load/                   # Pressure on inner surface
│   └── curing-temperature/            # Temperature fields
├── analysis/
│   ├── curing-steps/                  # 4-step process (vis/rub/glassy/sp)
│   └── springback-analysis/           # Model Change, mold removal
├── execution/
│   ├── curing-job/                    # Job submission with UMAT
│   └── socket-bridge/                 # Socket bridge connection
├── postprocessing/
│   ├── odb-extraction/                # ODB field output reading
│   └── csv-export/                    # CSV with coords + displacement
└── reference/
    └── curing-parameters/             # Complete parameter tables
```

## Quick Reference

### 4-Step Curing Process

| Step | Temperature | Pressure | Friction | Tool BC | Composite BC | Contact |
|------|------------|----------|----------|---------|-------------|---------|
| vis | 25→150°C | 0.6 MPa (S2) | 0.45 | U1=0, U2=0 | — | Active |
| rub | 150→180°C | 0.6 MPa (S2) | 0.2 | U1=0, U2=0 | — | Active |
| glassy | 180→25°C | — | 0.169 | U1=0, U2=0 | — | Active |
| sp | 25°C | — (removed) | — | — (removed) | Set-2: U1=U2=U3=0 | Removed |

### Constraint Summary (Critical)

| Phase | What is Constrained | How | Purpose |
|-------|---------------------|-----|---------|
| Curing (vis/rub/glassy) | TOOL-1: U1=0, U2=0 | `_PickedSet328, 1, 1` and `_PickedSet327, 2, 2` | Fix mold in space; composite held by friction |
| Curing (vis/rub/glassy) | Composite | Mold contact (friction) | Composite can slide/expand against mold |
| Springback (sp) | TOOL-1 | Removed via `*Model Change` | Mold is gone |
| Springback (sp) | Composite: Set-2 | `*Boundary, op=NEW` → U1=U2=U3=0 | Prevent rigid body motion only |

### Routing Guide

| User Request | Route To |
|-------------|----------|
| Change ply angles | `modeling/composite-layup` |
| Change ply count | `modeling/composite-layup` + `modeling/composite-mesh` |
| Set up mold | `modeling/mold-geometry` |
| Define UMAT material | `setup/curing-material` |
| Set up contact/friction | `setup/curing-contact` |
| Define boundary conditions | `setup/curing-bc` |
| Apply pressure | `setup/curing-load` |
| Set temperature fields | `setup/curing-temperature` |
| Configure curing steps | `analysis/curing-steps` |
| Set up springback | `analysis/springback-analysis` |
| Submit job with UMAT | `execution/curing-job` |
| Connect to Abaqus | `execution/socket-bridge` |
| Extract ODB results | `postprocessing/odb-extraction` |
| Export CSV data | `postprocessing/csv-export` |
| Batch extract + screenshots | `abaqus-odb-extraction` (standalone skill) |
| Look up parameters | `reference/curing-parameters` |

## Recommended Workflow Chain

```
core/composite-curing          → Start here
modeling/composite-layup       → Define plies
modeling/mold-geometry         → Set up mold
modeling/composite-mesh        → Verify mesh
setup/curing-material          → UMAT + TOOL materials
setup/curing-contact           → Contact + friction
setup/curing-bc                → Tool BCs + Set-2
setup/curing-load              → Pressure on S2
setup/curing-temperature       → Temperature fields
analysis/curing-steps          → 4-step sequence
analysis/springback-analysis   → Model Change
execution/curing-job           → Submit with UMAT
execution/socket-bridge        → Connect to Abaqus
postprocessing/odb-extraction  → Read results
postprocessing/csv-export      → Export data
abaqus-odb-extraction          → Batch automate (standalone skill)
```

## Key Files

- **Correct template INP**: `P8_mold_V2.inp` — contains TOOL part, contact, Model Change
- **Incorrect template INP**: `P8_only_recipe_1.inp` — archived, do NOT use
- **UMAT subroutine**: `Threestep.for` (4434 bytes, 4 state variables)
- **Environment file**: `abaqusis.env` (domains=4, no_domain_check=ON, ask_delete=OFF)
- **Abaqus CAE**: Must be open with socket bridge plugin (port 48152)

## Dataset Generation

For generating large datasets (50-100 cases) from the P8_mold_V2 template:

1. **INP generation**: Read template, replace 8 ply lines (indices 14153-14160), format: `0.250, 3, COM, <angle>, Ply-N`
2. **Batch submission**: `abq2020.bat job=NAME user=Threestep.for cpus=4 interactive`
3. **ODB extraction**: `abq2020.bat python extract_via_cli.py` (bypasses CAE filesystem isolation)
4. **Spring-in calculation**: SVD dual-arm plane fit on deformed coordinates
5. **Screenshots**: `abq2020.bat cae noUI=screenshot.py` with `LeafFromPartInstance` to hide mold

See the standalone `abaqus-odb-extraction` skill for complete automation scripts.

## Common Pitfalls

1. **Using P8_only instead of P8_mold**: Always use P8_mold_V2.inp as template. P8_only lacks mold contact and produces center-symmetric (unphysical) results.
2. **Ply count vs ply angles**: Changing ply angles is a text edit (replace ply lines); changing ply count requires mesh regeneration.
3. **Pressure surface**: Pressure is on S2 (inner surface), NOT S1 (outer/contact surface).
4. **Tool node numbering**: Tool and composite parts both start from node 1. Parse per-part.
5. **Set-2 node matching**: When mesh changes, match nodes by coordinates, not node ID.
6. **Filesystem isolation**: TRAE sandbox files are invisible to Abaqus CAE. Use `C:\Temp` or `abq2020.bat` for file operations.
7. **Python 2 vs 3**: Abaqus uses Python 2.7 — no f-strings, no `exist_ok`, `print` is statement in some contexts.
8. **MCP submit_job encoding bug**: `TypeError: unicode argument expected, got 'str'` — use command-line `abq2020.bat` instead.
