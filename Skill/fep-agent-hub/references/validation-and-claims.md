# Validation and claim rules

## Universal acceptance stack

Accept a case only when every applicable layer passes:

1. **Protocol** — the required MCP tools/resources enumerate and return schema-valid statuses.
2. **Environment** — native executable versions and paths resolve from approved configuration.
3. **Geometry** — expected dimensions, areas/volumes, object validity, STEP, and manifest pass.
4. **Mesh** — dimensionality, SI bounds, physical groups, semantic mapping, and counts pass.
5. **Solver input** — structured model and SIF validation pass.
6. **Native run** — exit code, completion marker, diagnostic scan, timeout, and step/file counts pass.
7. **Fields** — required arrays exist, use the expected association, are finite, and are nontrivial where physics requires.
8. **Physics** — conservation, bounds, signs, analytical comparison, or reference relationship passes.
9. **Sensitivity** — perform mesh/time/load-linearity checks required by the profile.
10. **Postprocessing** — dataset/time inspection, ranges, pipeline, images/tables/state, and session shutdown pass.
11. **Provenance** — trace inputs, outputs, hashes, versions, and gate decisions.

One failed mandatory layer makes the case `FAILED`. A requested capability absent by design makes the operation `BLOCKED` with a next action. Neither may be counted as `SUCCEEDED`.

## Report percentages correctly

Use separate denominators:

- **Tool coverage** = unique declared tools invoked / declared tools.
- **Call success** = calls returning the expected contract status / calls made.
- **Case gate pass** = mandatory gates passed / mandatory gates evaluated.
- **Numerical error** = the named FE quantity compared with a named analytical, experimental, or refined reference.

Do not turn a contract pass rate into “calculation accuracy.” Do not claim 100% engineering correctness because all smoke gates passed. Include the reference, norm, sampling position, units, threshold, and reason the threshold is appropriate.

Historical public release evidence recorded 49/49 unique tool coverage and 52/52 contract calls. Treat those numbers as a dated baseline; rerun the current matrix and publish the newly observed count after changing tools.

## Case-specific minimum gates

| Case | Minimum gates |
|---|---|
| Steady heat | imposed bounds, finite temperature, midpoint consistency |
| Transient heat | native time count, bounds, monotonic midpoint, Fourier comparison |
| Harmonic transformer | finite complex A/B fields, flux concentration, turns relation, half-current linearity, mesh sensitivity |
| Static beam | support residuals, finite displacement/stress/strain, load scaling, theory comparisons at matching locations |
| Steady channel flow | convergence, no slip, flow consistency, Poiseuille profile, pressure drop |
| Transient Lenz | native time counts, finite `Az/Ez/Jeddy`, nonnegative loss, four ramp-increment opposition signs, reversal, time/mesh sensitivity |

Never weaken a failed threshold only to obtain PASS. Investigate geometry singularities, sampling definitions, discretization, material assumptions, time integration, and the physical meaning of the gate.

## Animation semantics

- **Transient heat:** animate the native BDF time values and may overlay a sampled temperature-history curve.
- **Harmonic transformer:** label phase reconstruction as harmonic visualization, not transient solution history.
- **Beam:** label independent load factors as a quasi-static load sequence, not structural dynamics.
- **Steady flow:** label particle/stream motion as a steady-field visualization, not a transient CFD solve.
- **Transient Lenz:** animate native `Az` time steps and derived adjacent-step fields; preserve the one-to-one time/frame relationship.

Media overlays, scan lines, particles, interpolation, transitions, and error-table animations are explanatory presentation. They cannot be solver evidence. Keep videos silent when requested and verify duration, frame rate, resolution, codec, frame count, and absence of an audio stream.

## Stability claim

Limit stability statements to the tested operating envelope: fixed profiles, validated software versions, workspace-contained paths, deterministic semantic mapping, serial runs, benchmark sizes, and the observed repeat count. Do not infer long-duration soak stability, high concurrency, very large models, MPI behavior, or arbitrary geometry robustness without dedicated evidence.

## Release hygiene

Before publishing:

1. Run the repository-prescribed tests and protocol smoke.
2. Run secret and author-machine-path scans over files that Git will include.
3. Review ignored native results and local configuration.
4. Check staged file sizes and licenses.
5. Record the commit SHA associated with the validation result.
6. Link reports to lightweight evidence while keeping heavy or proprietary results out of Git.
