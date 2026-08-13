# FEP Agent Hub Release Validation

- Release: 0.1.0
- Validation date: 2026-08-13
- Status: **PASS**

## Tool contract coverage

| Server | Exposed | Unique invoked | Coverage |
|---|---:|---:|---:|
| FreeCAD MCP | 15 | 15 | 100% |
| Elmer MCP | 17 | 17 | 100% |
| ParaView MCP | 17 | 17 | 100% |
| Total | 49 | 49 | 100% |

The full matrix made 52 calls and all 52 matched their declared contract. Three tool calls returned the required `BLOCKED` response for their tested context:

- `freecad_capture_view`: headless FreeCAD screenshot is not claimed in v0.1.
- `elmer_excitation_set`: electromagnetic excitation is rejected under the heat profile.
- `paraview_export_animation`: the tested steady dataset has only one time step. The same tool succeeds for verified multi-step data.

These are explicit capability boundaries, not hidden failures.

## Native benchmarks

The validation created a real 10 mm FreeCAD cube, exported STEP, generated and converted a Gmsh mesh, solved steady heat conduction with Elmer, and post-processed the VTU with a persistent ParaView worker.

| Gate | Result |
|---|---:|
| Tmin | 299.99999999999994 K |
| Tmax | 400.00000000000006 K |
| Tmid | 350.26994261005336 K |
| Nodes | 235 |
| Volume elements | 734 |
| Boundary elements | 396 |
| Physics acceptance | PASS |

The electromagnetic extension also completed a real 2D harmonic transformer-effect
workflow with baseline, half-current, and refined-mesh solves. The registered MCP
entrypoint recorded 111/111 `SUCCEEDED` calls; field, flux, open-circuit voltage,
linearity, mesh sensitivity, and ParaView output gates passed. See
[`transformer-induction-validation-report.zh-CN.md`](transformer-induction-validation-report.zh-CN.md).

The plane-stress structural extension completed ten real quasi-static beam load
levels. All ten passed finite-field, support-residual, and analytical comparison
gates, and ParaView exported ten verified time-step frames. See
[`simply-supported-beam-validation-report.zh-CN.md`](simply-supported-beam-validation-report.zh-CN.md).

The transient thermal extension completed 20 real BDF1 time steps and matched
the 20 s Fourier-series midpoint temperature within 0.318 K. The steady flow
extension passed a Re=100 Poiseuille benchmark, including 1.76% velocity-profile
L2 error and 1.04% pressure-drop error. See
[`transient-heat-and-flow-validation-report.zh-CN.md`](transient-heat-and-flow-validation-report.zh-CN.md).

## Automated checks

- Routine Python tests: 17/17 executed tests passed.
- Native pytest wrapper: opt-in; the same native chain was executed by the full MCP validation.
- MCP inventory: tools plus static resources and resource templates listed successfully for all three servers.
- Native commands: FreeCADCmd, Gmsh, ElmerGrid, and ElmerSolver exited successfully without timeout.
- ParaView worker: requests completed and the MCP-owned process stopped normally.

## Claim boundary

This report establishes full declared-tool contract coverage plus steady and transient thermal, linear electromagnetic, linear plane-stress structural, and steady laminar-flow benchmarks. It does not establish universal accuracy for arbitrary CAD, nonlinear materials, contact, structural dynamics, turbulence, free surfaces, multiphysics, MPI, very large models, concurrency, or long-duration soak operation.
