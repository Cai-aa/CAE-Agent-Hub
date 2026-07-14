---
name: "composite-curing"
description: "Master skill for composite curing simulation with mold contact, friction, temperature, and Model Change springback in Abaqus. Routes to appropriate specialized skills."
---

# Composite Curing Simulation (Master Router)

This is the master routing skill for composite curing simulation. It does not perform
work directly. Instead, it classifies the user's request and routes to the appropriate
specialized sub-skill within the `composite-curing-simulation` collection.

## When to Invoke

Invoke this skill when the user's request falls into any of the following categories:

- **Curing simulation**: User asks to run or set up a composite curing simulation in Abaqus
- **Springback analysis**: User mentions springback, mold removal, demolding, or `*Model Change`
- **Mold contact**: User needs mold/tool contact geometry, contact pairs, or friction setup
- **Composite layup with mold**: User wants to define or modify a composite layup that interacts with a mold during curing
- **UMAT for composites**: User needs to run Abaqus with a UMAT subroutine for composite materials (e.g., `Threestep.for`)
- **Temperature-dependent friction**: User mentions changing friction coefficients across curing steps
- **Ply angle or ply count changes**: User wants to modify ply angles, ply count, or layup sequence in an existing curing model

If the request is a single, well-scoped sub-task (e.g., only changing a ply angle), you
may route directly to the relevant sub-skill without invoking this router first. Use this
router when the request spans multiple stages or when the user is unsure which sub-skill applies.

## Architecture Overview

The curing model consists of **two parts** in the Abaqus assembly:

1. **P8 (Composite Part)**: An L-shaped bracket with through-thickness solid elements (C3D8).
   The composite layup is defined via `*Solid Section, composite` with a stack direction of 3.
   The through-thickness direction is along the **X-axis** (from -1 to 0).

2. **Tool (Mold Part)**: A separate rigid-like mold part that contacts the composite outer
   surface during curing. The mold is removed in the springback step via `*Model Change`.

### Through-Thickness Direction

The composite thickness lies along the **X-axis**. For a 4-ply layup, the thickness spans
from X = -1 to X = 0 (1 mm total, 0.25 mm per ply). For an 8-ply layup, the same total
thickness of 1 mm is divided into 8 plies of 0.125 mm each. The stack direction in
`*Solid Section` is **3** (the third local axis defined by the orientation).

### 4-Step Curing Process

| Step | Name     | Temperature   | Pressure   | Friction (mu) | Purpose                        |
|------|----------|---------------|------------|---------------|--------------------------------|
| 1    | vis      | 25C to 150C   | 0.6 MPa    | 0.45          | Viscous heating phase          |
| 2    | rub      | 150C to 180C  | 0.6 MPa    | 0.2           | Rubbery curing phase           |
| 3    | glassy   | 180C to 25C   | (removed)  | 0.169         | Glassy cooling phase           |
| 4    | sp       | 25C (held)    | (removed)  | (inactive)    | Springback after mold removal  |

## Routing Table

Use the table below to determine which sub-skill to invoke. When multiple sub-skills are
relevant, invoke them in the order listed under "Recommended Chain Order".

| User Intent / Keywords                                  | Sub-Skill                          | Category        |
|---------------------------------------------------------|------------------------------------|-----------------|
| Ply angles, ply count, thickness, layup sequence        | `modeling/composite-layup`         | modeling        |
| Tool part, mold surfaces, mold geometry, tool material  | `modeling/mold-geometry`           | modeling        |
| C3D8 elements, through-thickness mesh, composite mesh   | `modeling/composite-mesh`          | modeling        |
| UMAT, COM material, TOOL material, Depvar, Expansion    | `setup/curing-material`            | setup           |
| Contact pair, friction properties, Change Friction      | `setup/curing-contact`             | setup           |
| Tool BCs, Set-2 springback constraint, boundary         | `setup/curing-bc`                  | setup           |
| Pressure on inner surface S2, Dsload                    | `setup/curing-load`                | setup           |
| Temperature fields, initial conditions, predefined      | `setup/curing-temperature`         | setup           |
| 4-step process, vis/rub/glassy/sp, Static step setup    | `analysis/curing-steps`            | analysis        |
| Model Change, mold removal, springback step             | `analysis/springback-analysis`     | analysis        |
| Job submission with UMAT, JobFromInputFile              | `execution/curing-job`             | execution       |
| Socket bridge usage, TCP port 48152, Abaqus kernel      | `execution/socket-bridge`          | execution       |
| ODB field output, stress/strain/displacement extraction | `postprocessing/odb-extraction`    | postprocessing  |
| CSV export with coordinates + displacement              | `postprocessing/csv-export`        | postprocessing  |

## Recommended Chain Order

For a complete curing simulation from scratch, follow this chain order. Each stage depends
on the output of the previous stage:

```text
1. modeling/composite-layup        # Define ply angles, thickness, count
2. modeling/mold-geometry          # Create tool/mold part and surfaces
3. modeling/composite-mesh         # Generate through-thickness C3D8 mesh
4. setup/curing-material           # Define COM (UMAT) and TOOL materials
5. setup/curing-contact            # Set up contact pair and friction properties
6. setup/curing-bc                 # Apply tool BCs and Set-2 springback constraint
7. setup/curing-load               # Apply pressure on inner surface S2
8. setup/curing-temperature        # Define temperature fields and initial conditions
9. analysis/curing-steps           # Configure 4-step process (vis/rub/glassy/sp)
10. analysis/springback-analysis   # Configure Model Change and mold removal
11. execution/curing-job           # Submit job with UMAT subroutine
12. execution/socket-bridge        # Connect to Abaqus kernel via socket bridge
13. postprocessing/odb-extraction  # Extract ODB field outputs
14. postprocessing/csv-export      # Export CSV with coordinates + displacement
```

### Stage Dependencies

- **Modeling** (steps 1-3) must be completed before **Setup** (steps 4-8), because
  material assignments, contact surfaces, and boundary sets reference the mesh.
- **Setup** (steps 4-8) must be completed before **Analysis** (steps 9-10), because
  steps reference loads, BCs, and contact pairs defined in setup.
- **Analysis** (steps 9-10) must be completed before **Execution** (steps 11-12),
  because the job is submitted from the complete INP.
- **Postprocessing** (steps 13-14) runs after the job completes successfully.

## Common Routing Scenarios

### Scenario 1: Change Ply Angles Only

User says: "Change the layup to [45/-45]*4."

Route to: `modeling/composite-layup` only. This is a text-level INP edit that does
not require mesh regeneration.

### Scenario 2: Change Ply Count

User says: "Switch from 4 plies to 8 plies."

Route to: `modeling/composite-layup` (for layup definition) then
`modeling/composite-mesh` (for mesh regeneration). Changing ply count requires
regenerating the through-thickness mesh, not just editing ply lines.

### Scenario 3: Run Full Curing Simulation

User says: "Run a curing simulation with the default layup."

Route through the full chain: `modeling/*` then `setup/*` then `analysis/*` then
`execution/*` then `postprocessing/*`.

### Scenario 4: Extract Results

User says: "Get the displacement results from the completed job."

Route to: `postprocessing/odb-extraction` then `postprocessing/csv-export`.

## Key References

- **UMAT subroutine**: Fortran file (e.g., `Threestep.for`) with 4 state variables
- **Reference INP**: Contains mold geometry, contact, loads, steps (e.g., `Job-0_0_0_0.inp`)
- **Pre-built composite model**: For ply count changes (e.g., `P8_only_recipe_1.inp` for 8 plies)
- **Socket bridge**: TCP on `127.0.0.1:48152` inside Abaqus CAE

## Common Pitfalls

1. **Ply count vs ply angles**: Changing ply angles is a text edit; changing ply count
   requires mesh regeneration. Do not confuse the two.
2. **Pressure surface**: Pressure is applied on S2 (inner surface), NOT S1 (outer/contact
   surface). Routing to `setup/curing-load` must preserve this distinction.
3. **Tool node numbering**: Tool and composite parts both start from node 1. Parse nodes
   per-part, not globally.
4. **Set-2 node matching**: When merging models with different through-thickness meshes,
   match nodes by exact coordinate lookup, not by node ID.
5. **Unicode errors**: Use `consistencyChecking=OFF` in `submit()` when running via the
   socket bridge.
