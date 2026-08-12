# Partition and Block Strategy

Use partitioning to create meshable topology, not to maximize the number of
geometric pieces. Every new edge/face must support mesh flow, feature capture,
size transition, symmetry, or a valid source-target sweep relation.

## Contents

- Decide whether to partition
- Plan 2D quad topology
- Plan mapped/swept solid blocks
- Decompose complex solids
- Select and sequence cuts
- Reject harmful partitions
- Partition evidence

## Decide Whether to Partition

1. Fix the solver profile, element formulation/order, target/min/max size, and
   quality criteria.
2. Protect physics-driving features and identify candidates for suppression.
3. Choose shell/quad, hex/sweep, or tet/boundary-surface route.
4. Partition only if it improves one of these: patch sidedness, source-target
   compatibility, edge-count compatibility, curvature capture, local transition,
   feature isolation, symmetry, or mesh quality.
5. Predict new short edges, sliver faces, acute corners, and interface conflicts
   before applying the cut.

For tet meshing, excessive decomposition usually adds boundary constraints and
poor surface triangles. Prefer curvature/proximity controls unless partitioning
is required for materials, contacts, boundary conditions, or local refinement.

## Plan 2D Quad Topology

Aim for four-sided or otherwise map-friendly patches with compatible opposing
edge counts. Treat a geometric surface containing many trimmed edges as a
topology problem even when it looks rectangular.

Use these patterns:

- Split around holes into washer/O-grid patches and connect their principal
  directions to the outer boundary.
- Extend important corners, tangent points, hole centers/quarter points, and
  thickness transitions into deliberate partition lines.
- Divide long irregular surfaces into a difficult feature patch, a transition
  patch, and a regular far-field patch.
- Suppress meaningless internal lines to merge tiny patches; add hard points or
  split lines only when they control a needed node/flow location.
- Keep unavoidable trias or extraordinary nodes in low-gradient, low-contact
  regions and away from source faces used for hex mapping.

Before meshing a patch, record its boundary loop, corner nodes, ordered edge
counts, target flow direction, and neighboring patches. A quad-dominant surface
is not acceptable if the flow twists abruptly or concentrates singularities at
critical features.

For a fine-to-coarse transition, cut a band with enough length for the permitted
growth. Mesh the fine feature patch first, transition next, and regular coarse
patch last. Do not ask smoothing to create a transition that the topology does
not contain.

## Plan Mapped/Swept Solid Blocks

For every proposed block define:

- source topology;
- target topology;
- path/along faces and sweep direction;
- source and target boundary-loop correspondence;
- divisions along the sweep;
- shared faces and whether their mesh already exists;
- one-direction or three-direction mappability expectation.

Complex solids must be decomposed into simpler sweepable blocks before Solid
Map. A three-direction mappable block is valuable where different sweep
directions meet because it can accept multiple source-target choices. Do not
assume all individually mappable solids can be meshed in a single multi-solid
operation; incompatible constraints on a shared face can still require staged
meshing.

Use an existing, quality-checked 2D source mesh to control the resulting hex/
penta topology. Maintain shared faces between adjacent blocks rather than
detaching them unless a nonconformal interface is intentional.

## Decompose Complex Solids

Apply these heuristics in order:

1. **Symmetry simplification:** partition and verify the smallest valid sector;
   replicate only when geometry and analysis conditions share the symmetry.
2. **Terminal-block backtracking:** identify a block that could be meshed last
   even if its incoming interface mesh were already fixed. Remove it mentally,
   repeat toward the core, then mesh in reverse dependency order.
3. **Source-first difficulty:** mesh circular, highly constrained, or contact
   source faces before simple rectangular neighbors; propagate their shared-face
   topology outward.
4. **Direction-change connector:** insert a compact three-direction mappable
   block where one-direction sweep paths turn or branch.
5. **Curved-sector split:** if a curved sector cannot sweep along its natural
   arc and produces distorted path elements, split the sector into smaller
   source/path roles and verify quality. The 90-degree bisection rule is a useful
   community heuristic, not an unconditional geometric law.
6. **Fallback:** use linear solid, drag/line-drag, ends-only, or a tet/hybrid
   route when Solid Map topology is unsuitable. Record why the fallback is more
   credible than additional fragile cuts.

At T-, Y-, cross-pipe, spoke, gear, and branched structures, isolate branches,
then solve the central junction topology. Do not sweep every branch independently
into an unresolved core.

## Select and Sequence Cuts

Choose the least destructive cutter that creates the planned topology:

- use an existing or constructed surface/plane for a complete sectional block;
- use lines/edges for local surface partitions or to extend key directions;
- use nodes/points to anchor a local cut or mapped corner;
- preview extended trimmers and deselect unwanted split sections;
- retain shared partition faces for conformal block interfaces.

Apply cuts in small groups. After each group:

1. verify topology colors/free/shared/non-manifold edges;
2. recount solids/surfaces and expected shared faces;
3. re-check mappability and source-target correspondence;
4. measure the shortest new edge and narrowest new surface;
5. undo/rework the group if it creates an unmeshable remainder.

## Reject Harmful Partitions

Reject or revise a plan when it:

- creates a sliver smaller than solver minimum size;
- turns a smooth transition into an acute wedge;
- leaves a final residual block with no compatible source and target;
- creates mismatched counts on a conformal shared face;
- forces a washer, contact, or load boundary through a poor transition;
- produces contradictory sweep directions at a shared face;
- preserves cosmetic boundaries that destroy mesh flow;
- removes component/material/contact boundaries solely to improve QI;
- depends on global smoothing to repair invalid topology.

## Partition Evidence

Export a block/patch table containing:

- block ID, purpose, bounding feature IDs, and parent solid/surface;
- source, target, path, mappability expectation, and sweep direction;
- ordered edge counts, bias, local size, and shared interface IDs;
- predecessor/successor blocks and planned mesh order;
- cutter type and selection counts;
- post-cut entity counts, minimum new feature size, topology status, and actual
  mappability;
- accepted fallback or rejected-plan reason.
