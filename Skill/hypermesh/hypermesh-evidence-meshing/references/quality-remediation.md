# Mesh Quality Diagnosis and Remediation

Treat quality repair as a cause-driven loop. A visually smooth mesh is not
proof of solver suitability, and a lower aggregate QI must not hide a severe
solver-specific failure.

## Contents

- Establish criteria and localize failures
- Diagnose the cause
- Choose the least destructive remedy
- Metric-specific remedies
- Surface and solid checks
- Verify and report

## Establish Criteria and Localize Failures

1. Load or define the downstream solver's 2D and 3D criteria before meshing.
2. Align target size in meshing parameters with the target/min/max values in the
   criteria file.
3. Export failed count and percentage per metric, plus Worst/Fail/Warn/Good/Ideal
   distributions when QI is used.
4. Review failures as localized patches with one or more neighboring layers;
   do not edit isolated elements without seeing their topology context.
5. For tetra meshes, read [tetra-quality-optimization.md](tetra-quality-optimization.md),
   export exact values with `hm_getelemcheckvalues`, and intersect the minimum-
   height, collapse, aspect, and volumetric-skew failure sets.
6. Count CAD-associated nodes in each failed tetra and classify connected
   hotspots as geometry-edge, surface-boundary, interior, or mixed before
   selecting refinement, edge swap, boundary remesh, or fixed-topology repair.

QI is a weighted compound indicator. Retain the individual metric values and
solver calculation method because different solvers and element types do not
use one universal quality definition.

## Diagnose the Cause

Classify each failed patch before editing:

- **geometry cause:** short edge, sliver face, duplicate/overlap, excessive
  curvature, narrow gap, poor midsurface, or missing topology;
- **partition cause:** wrong patch sidedness, incompatible counts, abrupt size
  transition, singularity at a critical feature, or conflicting sweep paths;
- **mesh connectivity cause:** poor diagonal, unnecessary trias, duplicate
  elements, disconnected/equivalent nodes, or wrong local pattern;
- **node-position cause:** otherwise valid topology with locally suboptimal node
  locations;
- **formulation/criteria cause:** inappropriate element type/order, impossible
  minimum length, or criteria inconsistent with target size.

Repair the highest-level cause first. Repeated node motion cannot cure a sliver
surface or an invalid hex block.

## Choose the Least Destructive Remedy

Apply remedies in this order unless evidence justifies another sequence:

1. correct duplicate, overlap, free-edge, normal, or topology errors;
2. suppress/protect/split geometry and revise local density or transition;
3. remesh the localized patch/block while preserving valid interfaces;
4. change connectivity with split, swap, or combine operations;
5. smooth/move nodes with geometry association and anchor constraints;
6. accept an exception only with solver evidence and localized justification.

When smoothing, anchor critical feature, interface, connector, and boundary
nodes. Review whether selected nodes are fixed by geometry, 1D elements, or
unselected neighbors; an unchanged mesh may mean the intended nodes cannot move.

## Metric-Specific Remedies

| Failure | Likely cause | Preferred remedy |
| --- | --- | --- |
| Minimum length | short geometric edge, over-refinement, collapsed transition | suppress/repartition the feature, change density/transition, then local remesh |
| Maximum length | insufficient local density | refine the patch or edge and transition outward |
| Aspect ratio | narrow patch, mismatched opposite counts, one-row transition | repartition, align flow, add rows, or revise edge counts |
| Skew | diagonal/connectivity or distorted flow around a feature | swap edge, revise washer/transition, split surface, local remesh |
| Warpage | coarse curved surface, poor midsurface, nonplanar quad | improve geometry/midsurface, curvature refinement, split or local remesh |
| Jacobian/scaled Jacobian | distorted mapped source, twisted sweep, collapsed solid | repair source mesh/block decomposition and remesh; do not rely on smoothing alone |
| Min/max angle | acute patch corner, bad tria/quad diagonal | revise partition, split/swap/combine, then smooth locally |
| Tet collapse | poor boundary triangles, narrow volume, proximity conflict | repair surface mesh/geometry, adjust volume controls, regenerate the affected volume |
| Excess trias/pentas | unsuitable quad/hex topology or transition | move singularity, repartition, combine compatible trias; keep allowed transitions if quality improves |
| Duplicate elements/nodes | repeated generation or unsafe equivalence | identify duplicates, delete the intended copy, equivalence only within justified tolerance |

Do not chase one metric while degrading another. Re-run all active checks after
each local patch repair.

## Surface and Solid Checks

For shell/surface mesh, verify topology/free edges, normals, geometry
association, duplicate elements, edge flow, size grading, and feature capture.

For mapped hex/penta mesh, verify source surface quality before extrusion,
source-target correspondence, shared-face continuity, sweep-layer bias, element
orientation, scaled Jacobian/Jacobian, aspect, warpage, and any solver-specific
solid checks. A mappable color/status proves topology eligibility, not final
quality.

For tet mesh, verify a closed, intersection-free surface mesh before volume
generation. Recheck boundary triangles and local proximity after failed tet
collapse or volume meshing.

For second-order elements, project/check midside nodes as required and repeat
quality checks using the final order; first-order quality alone is insufficient.

## Verify and Report

After each remediation iteration, export:

- operation, selected patch/block and neighboring layers;
- before/after element and node counts;
- before/after failed count, percentage, worst value, and location per metric;
- any moved boundary/feature nodes and maximum displacement;
- newly created trias/pentas or changed connectivity;
- remaining exception sets and engineering justification.

Stop automatic cleanup when improvements plateau, failures migrate into more
critical regions, or an operation violates feature/interface constraints. Block
acceptance when severe solver-specific failures remain unresolved.

Apply local topology changes as checkpointed transactions. Process one hotspot,
re-run all active metrics globally, and reload the checkpoint if any protected
feature, failure count, or exact worst value regresses. Recompute the failure
clusters after every accepted topology change rather than reusing stale element
IDs.

Treat less than one-percent improvement in the dominant failure count as a
plateau unless the exact worst value or critical-region location improves
materially. Do not repeat a node-only optimizer after this point; revisit the
geometry, boundary trias, local controls, and remesh freedom.

For a boundary-dominated tetra plateau, add a controlled shape-preserving
escalation before destructive surface reconstruction: checkpoint the best mesh,
test feature-aware `*morphsmoothmorphbased` candidates over one and two
neighboring layers, and rank them by all active failures, exact margins,
protected-feature integrity, and boundary displacement. After this broad
regularization, repair only the remaining typed residuals: a one-layer local
free-morph candidate for minimum-height clusters and fixed-boundary local
tetra remeshing for interior skew/connectivity clusters. Independently reload
the exported deck before accepting zero failures.

The least failed mesh is not automatically the least distorted geometry.
Always compare node coordinates against the accepted baseline, distinguish
boundary and interior motion, set a documented displacement tolerance, and
audit both current and initial CAD associations. Reject forced projection when
the referenced current geometry entity is unavailable or when the trial
creates degenerate elements.
