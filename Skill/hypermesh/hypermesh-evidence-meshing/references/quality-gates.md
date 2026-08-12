# HyperMesh Quality Gates

- CAD import returns success and creates nonzero expected entities.
- No unresolved duplicate surfaces, intersections, or unintended free edges remain.
- The chosen shell/quad, hex/sweep, or tet route is justified against geometry,
  solver formulation, analysis physics, and decomposition cost.
- Every partition has a stated purpose and does not create unresolved sliver
  surfaces, short edges, acute wedges, or residual unmappable blocks.
- Mapped/swept blocks record source, target, path, shared-face dependencies,
  sweep direction, and verified mappability before volume meshing.
- Surface and volume element counts are nonzero.
- Element type and solver profile match the downstream analysis.
- Retained cylinders, holes, circular edges, contacts, interfaces, and
  load/constraint boundaries have explicit local controls rather than only a
  global size.
- Mating or shared edges use compatible division counts; intentional
  nonconformal interfaces name their coupling/contact method.
- Washer, radial, axial, and biased transition layers record counts, direction,
  minimum/maximum spacing, and growth ratio where applicable.
- Quality metrics use named criteria: aspect ratio, skew, Jacobian, warpage,
  minimum/maximum angle, tet collapse, or solver-specific checks.
- Failed element counts and percentages are exported, not hidden.
- Every metric also exports its exact worst value, element ID, centroid or
  location, and ranked worst set; a failure threshold is not a worst value.
- Tetra reports cross-correlate minimum-height, collapse, aspect, and volume-
  skew sets and distinguish severe failures from marginal misses.
- Tetra hotspot evidence reports node-to-geometry associations, boundary-node
  count distribution, geometry IDs, cluster sizes, and local mesh-edge versus
  associated geometry-edge lengths before choosing refinement.
- Blind local refinement is blocked when an absolute minimum-height failure is
  dominant and the hotspot is boundary constrained; boundary sampling and
  surface-tria topology must be regularized or reviewed first.
- Individual solver-specific metrics remain available when an aggregate QI is
  reported; a better compound QI does not override a severe metric failure.
- Quality remediation records the diagnosed cause, operation, affected patch,
  and before/after counts and worst values.
- Topology-changing local repair is checkpointed per hotspot, globally
  rechecked, rolled back on an active-metric regression, and reclustered before
  another element-ID-based operation.
- A hard zero-failure tetra deliverable has zero failures for tet collapse,
  aspect ratio, volumetric skew, minimum height, and any additionally active
  Jacobian gate; it also contains no unintended non-tetra elements.
- Zero-failure status is independently reproduced after solver-deck export and
  reload. Record exact worst values and their safety margins, not only zeros.
- Numerical quality acceptance and CAD-adherence acceptance are separate.
  Record moved-node count, maximum boundary displacement, a user/engineering-
  approved tolerance, and current/initial geometry-association changes.
- Do not reproject nodes to stale initial point/line/surface IDs unless those
  entities exist in the current model and a checkpointed trial preserves all
  topology, feature, and quality gates.
- A tetra volume is not repaired until its closed boundary-tria mesh has passed
  topology and active 2D quality checks or its exceptions are documented.
- Any quality exception is localized and justified.
- Solver-deck export completes and the deck is nonempty.

Block downstream solve claims when logs contain translator failure, nonzero
`*geomimport` error code, BatchMesher nonzero return value, zero elements, or
unresolved severe quality failures.
