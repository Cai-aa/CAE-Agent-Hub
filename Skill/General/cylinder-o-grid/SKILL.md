---
name: cylinder-o-grid
description: "Plan, create, adapt, and quality-audit coin-style five-block O-grid hexahedral meshes for cylindrical CAE models. Use for software-independent O-grid planning or implementation in a selected preprocessor, including requests mentioning 钱币原理、圆柱网格、中心正方形、顶点切到圆周、结构化六面体网格, mapped square-to-circle partitions, or HEX8 meshes. Includes a generic planner and an Abaqus/CAE execution adapter; do not claim automated support in another CAE application without a matching adapter or proved live native-tool path."
---

# Cylinder O-Grid

Create a reviewable coin-style O-grid and accept it only after topology, mesh, and analysis checks pass in the selected CAE workflow.

## Establish the task

Collect or infer only low-risk inputs:

- Identify the target preprocessor, solver, analysis type, and whether the task is plan-only or a live implementation.
- Distinguish a new cylinder from an existing production part.
- Record radius `R`, length `L`, cylinder axis, units, and any interfaces or local refinement zones.
- Record the requested brick family and the exact solver-specific formulation when known.
- Record either target element size or counts for one square side/90-degree arc, radial layers, and axial layers.
- Ask before changing geometry, deleting an existing mesh, replacing a model, or relaxing a quality gate.

If live access to the target CAE application is unavailable, generate a plan and preview, label them as unexecuted in that application, and do not claim that the mesh was created or validated there.

## Enforce the topology

Use a circular cross-section with one centered, axis-aligned square. Connect each square vertex to the circle along the same 45-degree radial direction. Preserve these invariants:

- Keep `0 < a < R/sqrt(2)`, where `a` is the square half-width.
- Create five sweepable cross-section regions: one center block and four outer sectors.
- Use the same count `n_side` on every square side and corresponding 90-degree outer arc.
- Use the same `n_radial` on all four vertex-to-circle connector edges.
- Use the same `n_axial` on all edges parallel to the cylinder axis.
- Keep partitions continuous through the full cylinder length and share nodes at every internal boundary.
- Reject free tetrahedral fallback unless the user explicitly changes the objective.

Read [references/topology.md](references/topology.md) before selecting the square size or element counts.

## Route to the target software

- For every target, first produce and review the software-independent plan with `scripts/plan_ogrid.py`.
- For Abaqus/CAE, read [references/abaqus.md](references/abaqus.md). Use `scripts/abaqus_build_ogrid.py` only for a clean, straight cylinder aligned with global Z; adapt the workflow for existing or differently oriented parts.
- For another CAE preprocessor, translate the five logical blocks, edge roles, mapped quadrilateral controls, axial sweep, and quality gates into its native operations. Use only available registered tools or documented native APIs. No non-Abaqus automated builder is bundled, so deliver plan-only evidence if live construction and readback cannot be proved.

Do not infer solver element codes from the generic `HEX8` label. Report both the generic brick family and the exact target formulation actually assigned.

## Execute the workflow

1. Inspect the current model and preserve a checkpoint before mutation.
2. Produce an O-grid plan and preview with `scripts/plan_ogrid.py`.
3. Select the applicable software route and confirm that its required operations are available.
4. Partition the cross-section into five logical blocks and propagate them continuously through the cylinder length.
5. Apply mapped quadrilateral controls on the cross-section and structured or swept hexahedral controls through the axis.
6. Seed by topological role, not by fragile edge indices.
7. Generate the mesh and run every gate in [references/quality-gates.md](references/quality-gates.md), plus target-specific diagnostics.
8. Save the native model, preview, mesh statistics, quality results, warnings, and any solver audit together.

For live automation, prove the real application session with harmless inspection calls before mutation, save a checkpoint, and preserve raw tool output. A bridge response, generated file, or process return code alone is not mesh-quality or solver-validity evidence.

## Use the bundled scripts

Create the software-independent plan:

```powershell
python scripts/plan_ogrid.py --radius 10 --length 30 --square-ratio 0.40 --circumferential 48 --radial 6 --axial 24 --output-dir ogrid-plan
```

Dry-run the Abaqus adapter without importing Abaqus modules:

```powershell
python scripts/abaqus_build_ogrid.py --dry-run --radius 10 --length 30 --square-ratio 0.40 --circumferential 48 --radial 6 --axial 24
```

Run the adapter inside Abaqus/CAE after reviewing the plan:

```powershell
abaqus cae noGUI=scripts/abaqus_build_ogrid.py -- --radius 10 --length 30 --square-ratio 0.40 --circumferential 48 --radial 6 --axial 24 --cae-out cylinder_ogrid.cae
```

Treat the Abaqus builder as a starting point for a clean cylinder. Do not run it against a production model without adapting names, orientation, interfaces, and save path.

## Report acceptance evidence

Return:

- Target application, solver, and execution mode: generic plan, live native workflow, or bundled adapter.
- Geometry parameters and `a/R`.
- `n_side`, total circumferential count, `n_radial`, and `n_axial`.
- Expected and actual node/element counts.
- Generic brick family, exact assigned formulation, and verified HEX percentage.
- Mesh-control technique and axial layering direction.
- Failed mesh diagnostics, worst aspect-ratio result, negative/zero-volume count, and unmeshed regions.
- A cross-section image with element edges and an axial/swept view.
- Any unverified item, unavailable target-specific check, or relaxed threshold.

Never state “high quality” without attached measurements and a visual check of the four square-corner transition zones.

Use `assets/coin-ogrid-topology.svg` as the software-independent topology reference. Use `assets/abaqus-live-smoke.png` only as an Abaqus appearance example. Never infer quality metrics from images alone.
