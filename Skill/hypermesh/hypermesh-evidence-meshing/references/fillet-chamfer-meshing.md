# Fillet and Chamfer Meshing

Use this reference whenever a model contains interior fillets, exterior rounds,
edge blends, chamfers, or bevels. Decide from analysis relevance and measured
representability; never delete a feature only because it is small or keep it
only because it exists in CAD.

## Contents

- Inventory and decision contract
- Fillet calculations and topology
- Chamfer calculations and topology
- HyperMesh realization
- Route-specific rules
- Quality and evidence gates
- Research basis

## Inventory and Decision Contract

Record, for every candidate feature:

- stable surface/edge IDs, component, units, CAD or FE-geometry status, and
  convex/concave classification;
- analysis role: fatigue/stress concentration, contact, sealing, bearing/load
  transfer, boundary condition, material/thickness interface, manufacturing,
  or cosmetic;
- minimum/maximum radius, profile width, included angle, longitudinal length,
  tangency edges, adjacent-face widths, nearby holes/steps, and continuity;
- global target size, solver minimum size, curvature angle, chordal-deviation
  limit, cleanup tolerance, element order, and intended shell/hex/tet route.

Use this decision order:

1. **Preserve and control** a feature that affects contact, sealing, fatigue,
   stress flow, load/constraint application, material/thickness boundaries, or
   the source/target topology of a mapped block.
2. **Preserve and test** a manufacturing feature when its result sensitivity is
   unknown. Compare a locally converged retained model with any simplified
   model before accepting suppression.
3. **Suppress candidate** only when the feature is physically negligible and
   its required rows would violate minimum size or create slivers. Suppression
   is a reviewed decision, never an automatic result of this classification.
4. **Manual review** a variable-radius blend, interrupted chain, blend running
   into a hole/step/contact edge, or a feature whose adjacent faces cannot be
   extended cleanly.

Protect retained feature sets before BatchMesher or global cleanup. Confirm
that loads, constraints, contacts, connectors, and property boundaries still
reference valid entities after any geometry change.

## Fillet Calculations and Topology

For radius `R`, included/sweep angle `theta` in radians, target profile size
`h`, maximum turn angle `alpha`, maximum chordal deviation `d`, and minimum
profile rows `n_min`, calculate:

```text
arc_width = R * theta
n_size    = ceil(arc_width / h)
n_angle   = ceil(theta_deg / alpha_deg)
n_dev     = ceil(theta / (2 * acos(1 - d/R)))       when 0 < d < R
n_rows    = max(n_min, n_size, n_angle, n_dev)
chord     = 2 * R * sin(theta / (2*n_rows))
deviation = R * (1 - cos(theta / (2*n_rows)))
```

Treat two rows across a retained low-order fillet as a planning floor, not an
acceptance rule. Use three or more rows, local convergence, or higher-order
curvature representation when bending, fatigue, contact pressure, or a stress
gradient drives the analysis. The actual angle need not be 90 degrees.

For a structured shell mesh, connect both tangency edges and any longitudinal
centerline to deliberate patch boundaries. Match counts along the fillet chain
and adjacent patches. Put transitions outside the peak-gradient part of the
fillet, and do not end a split line inside a mapped patch.

A longitudinal centerline can stabilize row flow or split a narrow fillet into
two controlled strips. It does not by itself guarantee quality: reject the
split if it creates short end edges, distorted rows at hard points, or
incompatible counts at an interrupted/variable-width chain.

## Chamfer Calculations and Topology

Treat a chamfer as a narrow planar feature band, not as a zero-radius fillet.
Measure the shortest distance `s` across the chamfer face. If only the two leg
setbacks `a` and `b` are known, derive:

```text
s        = sqrt(a*a + b*b)
angle    = atan2(b, a)
n_rows   = max(n_min, ceil(s / h))
h_actual = s / n_rows
```

Use at least two rows across a retained structural/contact chamfer as a
planning floor. Increase the count when contact traction, a weld preparation,
sealing land, high stress gradient, or quadratic geometry representation needs
it. A single row is acceptable only with explicit formulation and convergence
evidence; it must not be a silent consequence of global size.

For quads, extend the two chamfer endpoints/tangency-equivalent corners into
the neighboring topology and match both long-edge counts. For mapped hex,
isolate the chamfer and adjacent shoulder as a staged source-target block; do
not force one axial sweep through a changing cross-section. Acute chamfers that
leave wedge/sliver residual blocks require a revised cut or a tet/hybrid route.

Suppress a cosmetic chamfer by merging/suppressing its bounding topology only
after verifying that adjacent faces reconstruct cleanly. There is no assumption
that every HyperMesh release exposes chamfers as a dedicated detected feature;
manual narrow-face inventory may be required.

## Size Transition

When local profile size `h_f` must return to far-field size `h_c` with maximum
adjacent growth `g_max`, create an explicit transition band:

```text
n_transition = ceil(log(h_c / h_f) / log(g_max))
g_actual      = (h_c / h_f) ** (1 / n_transition)
```

Keep the transition out of tangency endpoints, contacts, load application
zones, mapped source faces, and maximum stress-gradient regions. Re-run all
quality metrics after changing density; do not repair a minimum-length failure
by introducing skew, warpage, or a poor solid Jacobian.

## HyperMesh Realization

Use the installed-version UI or a command verified against its local help.

1. Detect and review fillets with the Features tool, then validate the feature
   data after geometry edits. Current feature data includes radius, width, and
   angle ranges. Inventory chamfer faces separately when they are not detected.
2. Measure the actual profile and classify preserve/suppress/manual-review
   before changing geometry.
3. For a retained fillet, use curvature-aware edge seeding and, when helpful,
   split its longitudinal centerline. The documented Tcl operation is
   `*createfilletmidlines`; its radius/width ranges and tangent-edge suppression
   flag must be derived from measured values, not copied from an example.
4. For a justified fillet removal, preview the selected chain. The documented
   `*removeedgefillets` command filters surface edge fillets by radius and
   angle; wrap it in `catch`, use explicit marks, and verify the post-operation
   entity and topology counts.
5. If automatic defeaturing fails, delete/reconstruct or extend/intersect the
   adjacent CAD surfaces only in a copied run model. Check free/shared/non-
   manifold edges and nearby topology immediately.
6. For retained chamfers, create endpoint/section cuts and exact edge densities
   before meshing the surrounding patch or block.
7. Prefer the session command file or installed API documentation when mapping
   a ribbon action to automation. UI labels and command signatures vary by
   release.

Do not apply CAD fillet/defeature commands to FE geometry without checking
version support. Altair documents important FE-geometry limitations for
Fillets, Defeature, Solid Map, tetra, and hex workflows in current releases.

## Route-Specific Rules

- **Shell/midsurface:** decide whether the physical 3D edge treatment belongs
  in the midsurface idealization. Preserve a radius/chamfer when it changes the
  midsurface path, thickness transition, joint, contact, or load definition.
  Anchor feature and boundary nodes during smoothing.
- **Mapped/swept hex:** isolate shoulder, fillet, and chamfer transitions into
  compatible blocks. Check source mesh first, match shared-face counts, use
  more than one layer through a retained profile, and verify scaled Jacobian,
  aspect, warpage, and orientation after every staged sweep.
- **Tet:** avoid hex-style over-partitioning. Retain a closed, intersection-free
  boundary mesh with curvature/proximity controls; check boundary triangle
  quality and tet collapse near small blends.
- **Second order:** project/check midside nodes on retained curvature and repeat
  the final-order quality checks. First-order chordal evidence is insufficient.

## Quality and Evidence Gates

Export before/after evidence containing:

- feature IDs, measurements, role, decision, reason, and protected entities;
- derived row count, actual chord/profile size, chordal deviation, local
  transition layers/growth, and matching edge counts;
- executed selection marks, detected/selected/changed entity counts, and any
  command errors;
- free/shared/non-manifold edges, shortest edge, narrowest face, surface/solid
  counts, area/volume change, and bounding-box change after defeaturing;
- failed count and worst value for minimum length, aspect, skew, warpage,
  angle, Jacobian/scaled Jacobian, chordal deviation, and solver-specific checks;
- local before/after images or element sets at tangency endpoints, fillet
  centerlines, chamfer ends, block interfaces, and transition bands;
- retained-vs-suppressed sensitivity evidence when the feature can affect peak
  stress, contact pressure, sealing, stiffness, or fatigue.

Block automatic acceptance if an operation loses a protected boundary,
creates a free/non-manifold edge, produces required spacing below the solver
minimum, leaves an unmappable residual block, or merely moves a severe failure
into a more critical region.

## Research Basis

Community material supplied practical workflows; exact capabilities and Tcl
signatures were cross-checked against Altair documentation:

- [Bilibili double-fillet meshing example](https://www.bilibili.com/video/BV1HW4y1273B/)
- [Bilibili HyperMesh geometry-cleanup and partition notes](https://www.bilibili.com/opus/1035259234909945926)
- [Jishulink BatchMesher fillet controls and formulas](https://www.jishulink.com/post/421562)
- [Altair Features: fillet detection, measurement, validation, and defeaturing](https://help.altair.com/hwdesktop/hwx/topics/pre_processing/model_setup/features_r.htm)
- [Altair curved-surface mesh and chordal-deviation tutorial](https://2022.help.altair.com/2022.2/hwdesktop/hm/topics/tutorials/hm/hm_3120_2d_mesh_in_curved_surfaces_c.htm)
- [Altair `*createfilletmidlines`](https://help.altair.com/hwdesktop/hwd/topics/reference/hm/_createfilletmidlines.htm)
- [Altair `*removeedgefillets`](https://2022.help.altair.com/2022.3/hwdesktop/hwd/topics/reference/hm/_removeedgefillets.htm)
- [Altair Quick Edit split, suppress, and trim operations](https://help.altair.com/2024/hwdesktop/hwx/topics/pre_processing/geometry/quick_edit_t.htm)
- [Altair FE-geometry support limitations](https://help.altair.com/hwdesktop/hwx/topics/chapter_heads/fegeometry_r.htm)
