---
name: run-fluent-autoclave
description: Run, diagnose, reproduce, and validate ANSYS Fluent CFD simulations of forced-convection autoclaves using Fluent MCP or PyFluent. Use for autoclave or hot-air vessel projects involving SCDOC/STEP geometry, annular velocity inlets, pressure outlets, Spalart-Allmaras turbulence, energy transport, calorimeter temperature boundaries, automatic meshing, longitudinal velocity contours, streamlines, mass-balance checks, or the Bohne paper boundary-condition case.
---

# Run Fluent Autoclave

Reproduce the validated open autoclave workflow while preserving geometry-specific judgment and numerical evidence.

## Workflow

1. Detect Fluent before launching it. Confirm `fluent.exe`, PyFluent, version, and job directory.
2. Inspect the geometry and existing project files. Reuse a valid STEP/fluid domain instead of rebuilding geometry.
3. Read [references/paper-case.md](references/paper-case.md) before applying the Bohne-style boundary conditions.
4. Read [references/mcp-workflow.md](references/mcp-workflow.md) before controlling Fluent MCP or handling a Chinese path.
5. Copy the bundled scripts into the job directory and adjust only the geometry-dependent constants.
6. Generate and check the mesh. Reject unmatched boundary faces, non-manifold faces, invalid volumes, or a misidentified full-face inlet.
7. Configure Fluent in small validated chunks. Print each model, material, and boundary state after setting it.
8. Run one time step first. Continue only if the mesh is valid and residuals remain finite.
9. Run the remaining steps asynchronously when possible, monitor stdout/stderr, and save case/data before post-processing.
10. Extract mass flow, inlet/outlet average and maximum speeds, global maximum speed and location, pressure drop, temperature range, and the final residuals.
11. Generate the vertical longitudinal mid-plane velocity contour and streamlines with outlet left and inlet/head right.
12. Run `scripts/validate_results.py` on the final JSON. Do not call the result complete if conservation or provenance checks fail.

## Required physical setup

- Use the annular clearance at the ellipsoidal head as the velocity inlet; never use the whole end face without verifying the geometry.
- Use a pressure outlet at the opposite duct.
- Keep vessel walls adiabatic and no-slip.
- Split exposed calorimeter faces into a separate fixed-temperature wall zone.
- Use the material properties and boundary values in `references/paper-case.md` when reproducing that case.
- Treat the reference image peak velocity as an outcome, not a prescribed outlet value.

## Reliability rules

- Preserve prior cases and results; write the new run under distinct names.
- Prefer named zones over raw zone IDs after the mesh is loaded.
- Verify the global maximum location. A maximum at the outlet is suspicious unless the geometry physically contracts there.
- Report local outlet reverse-flow area separately from net mass conservation.
- State geometry-scale differences before comparing peak speeds to a paper.
- Do not report wall heat-transfer coefficients as design values without a near-wall mesh and y-plus assessment.
- Keep the final Fluent MCP session loaded when the user is likely to continue interactively.

## Bundled scripts

- `scripts/mesh_autoclave_paper_case.py`: Boolean fluid-domain construction, boundary splitting, and refined tetrahedral mesh.
- `scripts/prepare_fluent_paper_mesh.py`: Deterministic Gmsh-to-Fluent ASCII mesh conversion with named zones.
- `scripts/plot_fluent_paper_results.py`: Main-view velocity, streamline, temperature, and pressure figures from extracted plane data.
- `scripts/validate_results.py`: Acceptance checks for the final result JSON.

The three simulation scripts are validated against the supplied autoclave topology. Inspect and adapt their STEP volume ordering, coordinate tests, and output paths for a different geometry.
