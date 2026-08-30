# Quality gates

Treat these as configurable screening defaults. Tighten or relax them only for documented analysis reasons.

## Topology gate

- Five continuous sweepable cells or logical blocks: one center and four outer sectors.
- No gaps, overlaps, duplicate nodes, sliver edges, or disconnected partitions.
- Matching counts on paired square/arc edges and on all four connector edges.
- Expected cross-section and hexahedron counts match the generated topology.

## Mesh gate

- Unmeshed regions: `0`.
- Requested brick-element percentage: `100%` unless an exception was approved.
- Negative or zero-volume elements: `0`.
- Target-preprocessor mesh-check failures: `0`.
- Aspect ratio: target `<= 5`; allow up to `10` only with explicit justification and local review.
- Adjacent edge-size ratio: target `<= 1.5`; avoid abrupt jumps above `2`.
- Shared internal interfaces: conformal nodes, not coincident duplicates.
- Four square-corner transition zones: no folded, concave, or visibly collapsed cells.

Record the worst element identifiers and their locations, not just global pass/fail. Use the target application's native quality definitions and record their names because metrics such as skew, warpage, and Jacobian may differ between preprocessors.

## Solver gate

Mesh quality does not prove physical validity. For a representative analysis, also inspect:

- Implicit analyses: convergence history, excessive-distortion warnings, contact diagnostics, equilibrium, and sensitivity to refinement.
- Explicit analyses: stable time increment, added mass or mass scaling, kinetic/internal/hourglass energy balance, negative volume, and contact penetration.
- Other physics: the solver-specific conservation, convergence, and refinement checks appropriate to the model.

A completed job or zero return code proves process completion only. Apply any stricter target-specific gates documented by the selected software adapter.

## Required evidence

Save:

- O-grid plan JSON and preview.
- Native model or checkpoint before and after meshing.
- Element counts by exact target type.
- Native mesh-quality output and any failed-element set or group.
- Cross-section image with element edges visible.
- Axial view proving sweep continuity.
- Solver audit when the mesh is accepted for analysis.
