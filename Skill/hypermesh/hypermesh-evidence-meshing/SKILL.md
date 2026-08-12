---
name: hypermesh-evidence-meshing
description: Evidence-first Altair HyperMesh geometry cleanup, measured construction-line partitioning, shell/solid meshing, and mesh-quality remediation through Tcl and hmbatch. Use when Codex must plan or automate 2D quad flow, mapped/swept hexa blocks, tetra fallback, spheres, spherical shells, domes, flange plates, hubs, bolt circles/PCD, cylinders, holes, washers, slots, fillets, rounds, edge blends, chamfers, bevels, intersections, size transitions, biased edges, symmetry, contact or boundary regions, BatchMesher, solver-deck export, or repair of skew, Jacobian, warpage, aspect, angle, duplicate, and free-edge failures without reporting an empty or low-quality mesh as success.
---

# HyperMesh Evidence Meshing

Use explicit Tcl through `hmbatch -tcl` as the reproducible baseline. Do not
assume an undocumented Python API and do not modify vendor installation files.

## Start

Read `MCP/HyperWorks/README.md`, then call `get_environment`,
`get_live_bridge_status`, and `get_live_capabilities`. Create a project with
`create_project`, import only workspace-scoped inputs, and use one of two
auditable routes:

- write screened Tcl with `write_tcl_script`, then execute it with
  `run_hmbatch`; or
- use typed live operations such as `import_live_cad`,
  `automesh_live_surfaces`, `solid_map_live_solids`,
  `tetra_mesh_live_solids`, and `get_live_mesh_quality`.

Use `create_live_checkpoint` before a local repair and
`rollback_live_checkpoint` when any protected feature or active quality metric
regresses. Inspect the installed release before using Tcl commands that are not
covered by typed MCP tools. Never expose arbitrary Python, shell, or unscreened
Tcl through the live bridge.

## Choose the Meshing Route

- For shells or midsurfaces, design quad flow and local transitions before
  `automesh`; allow trias only where the solver and physics permit them.
- For hex-dominant solids, prove each planned block is sweep/mapping-compatible
  and define source, target, path, shared-face dependencies, and mesh order.
- For tet-dominant solids, clean and protect the boundary surface mesh first;
  do not over-partition merely to imitate a hex workflow.
- Prefer a simpler, verifiable topology over a fragile pure-hex target when
  decomposition cost or distorted transition blocks outweighs its benefit.

## Gate the Workflow

1. Copy source CAD into the run input area; never overwrite the original.
2. Confirm the CAD reader/import completed and count imported surfaces/solids.
3. Define solver-specific size and quality criteria, then audit free edges,
   duplicate/overlapping surfaces, intersections, normals, and topology.
4. Classify mesh-driving features and preserve intentional circular edges,
   holes, contacts, loads, constraints, interfaces, and symmetry boundaries.
5. Write a partition plan before cutting geometry. For each patch/block, record
   why it exists, source/target/path topology, shared interfaces, and dependent
   blocks. A large number of cuts is not evidence of a valid decomposition.
6. Apply cuts incrementally. Re-check topology and mappability after each group
   and reject sliver surfaces, short edges, acute wedges, and conflicting sweep
   directions introduced by the cut.
7. Define edge densities, local size, bias, washer rings, transition bands, and
   sweep layers before generating dependent surface or volume mesh.
8. Mesh difficult terminal/source regions first, then propagate compatible
   shared-face meshes through dependent blocks. Generate verified surface mesh
   before volume mesh when the route requires it.
9. Diagnose failed elements by cause and node-to-geometry association. Cluster
   failures, rank one hotspot at a time, and distinguish geometry-edge,
   boundary-surface, and interior failures. Prefer topology repair or local
   remesh before connectivity edits, and use node smoothing only when geometry
   and topology are already suitable. Do not treat an absolute minimum-height
   failure as an automatic request for a smaller local element size.
10. When ordinary hotspot repair reaches a plateau, invoke the zero-failure
    escalation route: checkpoint, test feature-aware shape-preserving morphing
    on one/two neighboring layers, then route residual minimum-height and
    interior-skew failures to separate local operations. Rank every candidate
    globally and roll back regressions.
11. Export `.hm`, solver deck, quality report, partition/feature summaries, and
    command/log evidence.

Read [references/quality-gates.md](references/quality-gates.md) before accepting
the mesh. A return code of zero without entities and quality statistics is not a
successful mesh.

Read [references/partition-strategy.md](references/partition-strategy.md) before
cutting 2D surfaces or decomposing a solid for mapped/swept hex meshing.

Read [references/feature-meshing.md](references/feature-meshing.md) whenever the
geometry includes cylinders, holes, circular/curved edges, slots, thin annuli,
sweepable solids, fillets, steps, intersections, contacts, interfaces, or
boundary-condition regions.

Read [references/fillet-chamfer-meshing.md](references/fillet-chamfer-meshing.md)
whenever the geometry contains interior fillets, exterior rounds, edge blends,
chamfers, or bevels. Measure the profile, classify its physics role, derive
curvature/row/transition controls, and verify protected boundaries and topology
before accepting either preservation or defeaturing.

Read [references/shape-partition-patterns.md](references/shape-partition-patterns.md)
for spheres, spherical shells, domes, flange plates, hubs, bolt circles, or any
revolved part that needs measured centers/axes, construction lines, concentric
rings, meridians, symmetry planes, a non-collapsing core, or periodic sectors.

Read [references/quality-remediation.md](references/quality-remediation.md) when
QI or solver checks fail. Record the selected feature IDs, patch/block IDs,
derived division counts, failed element sets, and before/after statistics; do
not rely on a global element size or a final screenshot alone.

Read [references/tetra-quality-optimization.md](references/tetra-quality-optimization.md)
for any tetra route or tetra-quality failure. Export exact values with
`hm_getelemcheckvalues`, localize overlapping failures, prove feature-to-gate
feasibility, quality-check the boundary-tria mesh first, and reject node-only
optimization when it plateaus or only renumbers failed elements.

For a localized tetra repair, checkpoint the accepted mesh and process one
hotspot as a transaction. Re-run every active metric globally after fixed-
topology, edge-swap, or boundary-remesh candidates. Commit only a Pareto-safe
candidate; otherwise reload the checkpoint. Recompute hotspot IDs after every
accepted topology-changing operation because remeshing can invalidate element
IDs and adjacency.

For a hard zero-failure deliverable, all active failure counts must be zero in
both the working model and an independently reloaded solver deck. Then audit
pure element type, exact worst-value margins, moved boundary nodes, maximum
displacement, and current/initial CAD associations. Numerical quality approval
does not automatically approve geometry adherence; define and report an
engineering displacement tolerance. Never force-project stale initial geometry
IDs unless the referenced current entity exists and a checkpointed trial passes
all quality and topology gates.

## Finish

Report source geometry type, import translator, entity counts, element counts,
element types, global and local size controls, edge densities and bias, feature
division counts, block dependency and meshing order, failed-quality counts,
remediation, and exported solver profile. Preserve failed BatchMesher logs
because they identify translator, criteria, parameter-file, or topology
problems. For a zero-failure run, also report the independent-reload result,
exact quality margins, maximum boundary displacement, the applicable geometry
tolerance, and association changes.
