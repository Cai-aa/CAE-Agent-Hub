# Feature-Aware Meshing

Use this guide after choosing the mesh route and partition topology. Treat all
counts as planning baselines; solver formulation, element order, contact,
loading, curvature tolerance, and expected gradients govern final density.

## Contents

- Preserve, seed, washer, or remove
- Circular edges and cylindrical surfaces
- Holes, washers, and slots
- Fillets, steps, ribs, and narrow faces
- Intersections, spokes, and periodic geometry
- Size transitions and biased edges
- Feature evidence

## Preserve, Seed, Washer, or Remove

Classify every recognized feature by analysis role, not size alone:

- **Preserve** holes/edges that define load transfer, bolts, pins, bearings,
  contact, flow, materials, thickness, symmetry, loads, or constraints.
- **Seed** a geometrically important feature when its boundary must be retained
  but no dedicated ring or structured block is needed.
- **Washer/O-grid** retained openings that need regular radial flow, connector
  coupling, bearing/contact pressure, or controlled transition.
- **Remove/suppress** cosmetic holes, logos, threads, short edges, chamfers, and
  fillets only after documenting that their physics is negligible.

Protect critical entities with explicit feature/preserved-entity selections.
Do not let automatic cleanup collapse them merely because minimum element size
is larger than the feature.

## Circular Edges and Cylindrical Surfaces

For radius `R`, target circumferential size `h_theta`, and maximum allowed angle
per element `alpha_max`, calculate both baselines:

```text
n_size  = ceil(2*pi*R / h_theta)
n_angle = ceil(360deg / alpha_max)
n_theta = max(n_size, n_angle, minimum_count)
```

Round `n_theta` upward to satisfy periodic sectors, symmetry, opposing edges,
and connector directions. A multiple of four is useful when quarter points or
orthogonal directions must carry nodes, but it is not a universal quality rule.
Give mating circles compatible counts and seam/start locations.

For axial length `L`, use `n_z = ceil(L/h_z)` as a baseline. Bias axial layers
toward shoulders, ends, contact boundaries, fillets, load introduction regions,
or thickness changes. Record direction, minimum/maximum spacing, and growth.

For annuli or thick cylinders, define radial layers from through-thickness
physics. Split large curved sectors when the selected sweep direction forces a
curved side to behave as a source/path combination that would otherwise produce
distorted elements. Treat the community rule of splitting a 90-degree arc into
two regions as a diagnostic heuristic, then verify scaled Jacobian and warpage.

## Holes, Washers, and Slots

For each retained hole, measure shape, radius/diameter, depth, axis, edge
distance, neighboring-hole distance, and associated analysis feature.

Choose the washer pattern deliberately:

- **Radial washer** for circular flow and regular ring layers.
- **Corner-quad washer** when the surrounding quad topology should connect to
  four principal directions.
- **No washer** when nearby boundaries, holes, or narrow ligaments make the ring
  more distorted than a controlled local remesh.

Define exact or minimum elements around critical holes; do not use `auto` when
repeatable connector alignment or washer layers require a fixed count. Define
one to three washer widths as absolute values, radius-based expressions, or
quality-derived values. An automatic width may legitimately omit the washer
when good elements cannot be produced, so verify actual creation.

Prioritize bolt/bearing holes when washers overlap. For close holes or a hole
near a free edge, build a shared partition/transition or relax the lower-priority
washer. Report the minimum elements across the remaining ligament.

For slots, keep the rounded or rectangular end treatment explicit. Seed both
ends compatibly, match opposite straight-edge counts, and inspect skew at the
arc/straight tangency. For blind or countersunk holes, independently inspect the
wall, cap, cone/bottom transition, and sweep compatibility.

## Fillets, Steps, Ribs, and Narrow Faces

Read [fillet-chamfer-meshing.md](fillet-chamfer-meshing.md) for the complete
measurement, preserve/suppress decision, fillet/chamfer calculation, Tcl
realization, route-specific topology, and evidence workflow.

Choose among four retained/simplified fillet treatments:

- remove it when it is non-physical relative to target/minimum size;
- preserve it with curvature control when stress or contact needs the radius;
- split it along its midline to stabilize rows and mesh flow;
- enforce a minimum row count across its arc length.

Treat chamfers as measured narrow planar bands, not zero-radius fillets. Retain
at least two controlled rows as a planning baseline when stress, contact,
sealing, load transfer, or manufacturing intent matters; otherwise document and
verify any suppression.

Use chordal deviation/maximum angle and minimum element size together. Avoid
capturing a radius with tiny elements that violate the solver minimum length.

Suppress construction lines and narrow faces that create slivers, but preserve
real steps and component boundaries. Do not preserve adjacent component
boundaries that have no structural meaning if they force poor elements; do not
remove meaningful interfaces merely to improve QI.

At thickness changes, split a transition band instead of collapsing the entire
change into one row. Keep step corners and contact edges as hard topology when
they drive results.

## Intersections, Spokes, and Periodic Geometry

- At T/Y/pipe intersections, separate branch blocks from the main run and
  establish a shared transition/core block before sweeping.
- Around spokes, gear teeth, blades, or repeated sectors, mesh one verified
  sector and replicate only when geometry, loading, contact, and periodic counts
  are truly identical.
- Align block seams with symmetry or low-gradient regions when possible; avoid
  placing singular nodes in peak contact/stress zones.
- Use a small three-direction mappable connector block where sweep directions
  must change, rather than forcing conflicting one-direction blocks to meet.

## Size Transitions and Biased Edges

For fine size `h_f`, coarse size `h_c`, and maximum adjacent growth `g_max`, use:

```text
n_transition >= ceil(log(h_c / h_f) / log(g_max))
g_actual = (h_c / h_f) ** (1 / n_transition)
```

Create an explicit transition band with enough distance/layers. Put topology
singularities and unavoidable trias/pentas away from holes, contacts, sharp
gradients, and shared sweep sources. Prefer symmetric bias when both ends need
refinement and one-way bias when only one end is critical.

Do not refine every boundary. Separate geometry-driven curvature refinement,
physics-driven local refinement, and numerical transition requirements.

For tetra routes, keep the regular model-level minimum size distinct from a
smaller protected-feature minimum. A very small global curvature/proximity
floor can capture every cosmetic short edge and sliver, creating many flattened
tets. Use the finer value only on measured protected feature sets and verify the
closed surface-tria mesh before volume meshing.

## Feature Evidence

Export, per feature:

- stable ID or geometric descriptor and analysis role;
- measured dimensions and units;
- preserve/seed/washer/remove decision and reason;
- local size, circumference count, washer type/width/layers, axial/radial
  layers, bias/growth, and periodic/symmetry constraints;
- selected entity count before the operation and created entity/element count;
- localized quality failures before and after remediation.

In Tcl, block execution when an expected feature selection is empty. Resolve
actual commands and marks against the installed HyperMesh version; ribbon and
Classic UI names differ and must not be used as proof that a Tcl command exists.
