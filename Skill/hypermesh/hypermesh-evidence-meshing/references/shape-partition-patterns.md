# Sphere and Flange Partition Patterns

Use this reference for spheres, spherical shells, domes, flange plates, hubs,
and other revolved parts whose mesh quality depends on measured construction
lines and repeatable block topology. The patterns are planning baselines, not a
substitute for solver-specific convergence and quality checks.

## Contents

- Measurement contract
- Construction-line rules
- Sphere and spherical-shell pattern
- Flange and bolt-circle pattern
- HyperMesh realization sequence
- Acceptance evidence
- Research basis

## Measurement Contract

Do not infer a partition from appearance alone. Record stable geometry IDs,
units, tolerance, and the method used to obtain each dimension.

For a sphere, spherical shell, or dome, measure:

- center and local orthogonal axes;
- outer and inner radius, shell thickness, and opening/cut-plane locations;
- included polar/azimuth angles for a partial sphere or dome;
- symmetry planes, seams, contacts, load patches, and support boundaries;
- smallest fillet, opening, ligament, and expected high-gradient region.

For a flange or hubbed plate, measure:

- center, axis, outer radius, bore radius, and every step/shoulder radius;
- pitch-circle diameter/radius (PCD), bolt-hole diameter, count, angular phase,
  and whether holes are through, blind, counterbored, or countersunk;
- flange, hub, neck, gasket, and washer/contact thicknesses;
- adjacent-hole center distance and clear ligament;
- radial clearance from each hole to the bore/hub and outer rim;
- fillet/chamfer radii, mating faces, gasket band, contact faces, load points,
  and constraints.

Use HyperMesh Measure for length, angle, radius, area, volume, center of gravity,
and bounding-box checks. Snap to end, middle, center, tangent, perpendicular, and
intersection locations where supported. Cross-check a recognized circle with
three non-collinear points or detected feature data; do not build a bolt pattern
from a visually estimated center.

For `N` equally spaced holes on pitch radius `R_p` with hole radius `r_h`,
calculate:

```text
pitch_angle       = 360deg / N
center_chord      = 2 * R_p * sin(pi / N)
tangent_ligament  = center_chord - 2 * r_h
inner_clearance   = (R_p - r_h) - R_bore
outer_clearance   = R_outer - (R_p + r_h)
```

Negative or near-zero clearance is a geometry/topology blocker, not a mesh-size
problem. Report the number of intended element rows across every critical
ligament and contact band.

## Construction-Line Rules

Construction lines are mesh-control topology. Keep only lines that establish a
required mapped corner, feature ring, transition band, source/target boundary,
symmetry seam, contact boundary, or load location.

1. Establish a verified local coordinate system at the measured center/axis.
2. Create points at measured centers, quadrant/extreme locations, tangent
   points, step radii, and sector boundaries.
3. Create circles/arcs, radial lines, meridians, or sectional planes from those
   points and dimensions.
4. Project lines onto the intended surface along an explicit vector or surface
   normal. Confirm the projected line remains on the correct face.
5. Preview extended trimmers and select only intended split sections.
6. Split in small groups, then re-check free/shared/non-manifold edges,
   shortest new edge, narrowest patch, patch sidedness, and solid mappability.
7. Suppress redundant hard points and construction edges after they have served
   their purpose, unless they must remain as a boundary or mesh-density anchor.

Prefer full planes/surfaces for complete solid sections and local projected
lines for surface-only flow control. An auxiliary line that stops in the middle
of a mapped patch usually creates a T-junction or residual sliver; terminate it
at a deliberate block boundary or remove it.

## Sphere and Spherical-Shell Pattern

### Choose the topology

- **Tet sphere:** retain a clean curvature-controlled boundary and avoid hex-
  style internal cuts unless material, contact, load, or refinement regions
  require them.
- **Quad-dominant spherical shell:** use symmetry patches or a six-patch
  cube-projected layout. A latitude/longitude grid concentrates nodes and poor
  aspect ratios at the poles; do not accept it merely because it looks regular
  away from the pole.
- **All-quad spherical shell:** prefer six four-sided projected patches with
  matching counts. If eight spherical octants are used, explicitly design the
  extraordinary-node/transition topology instead of treating each triangular
  octant as a mapped four-sided face.
- **Mapped-hex solid sphere:** create a finite cube-like core and six surrounding
  curved blocks, or an equivalent non-collapsing multiblock layout. Do not drag
  an entire spherical surface to one center node; the collapsed center produces
  degenerate/low-Jacobian cells.
- **Spherical shell solid:** partition outer and inner faces identically, match
  their loops and counts, then map/sweep through thickness.

### Create measured auxiliary topology

1. Create three orthogonal planes through the measured center and verify one
   eighth of the geometry when symmetry of geometry and analysis permits.
2. Create great-circle/equator and meridian curves from those planes. Use them
   as symmetry or patch boundaries, not as an automatic latitude/longitude
   mesh generator.
3. For a six-patch shell, project a centered cube's six face boundaries onto
   the sphere and verify four-sided patch loops and equal shared-edge counts.
4. For a solid sphere, define a nonzero core radius and create the core before
   connecting its faces to the spherical boundary. Keep core edges comparable
   to the first outer radial layer.
5. Add local rings only around openings, contacts, loads, or refinement zones.
   Stop the ring through a transition patch before it reaches a pole or a
   conflicting seam.
6. Mesh one verified patch/octant first. Replicate only if geometry, material,
   contacts, loads, and constraints preserve the same symmetry.

For radius `R`, target surface size `h`, maximum angular increment `alpha`, and
required count multiple `m`, use:

```text
n_size       = ceil(2*pi*R / h)
n_angle      = ceil(360deg / alpha)
n_great      = round_up(max(n_size, n_angle, minimum_count), m)
n_quarter    = n_great / 4
n_semicircle = n_great / 2
```

Make `m` compatible with four quadrant directions and every modeled symmetry or
periodic sector. This is a count baseline; increase it for contact, local
curvature, bending, wave propagation, or convergence requirements.

### Sphere rejection checks

Reject or revise the plan when:

- radial lines converge to a single center or polar node;
- a cube-like core is so small that the first outer block has a severe size
  jump, or so large that its projected outer cells become highly skewed;
- shared cube/sphere patch edges have incompatible counts or seam starts;
- a pole, extraordinary node, or block seam lies inside peak contact/load/stress
  regions without a documented reason;
- shell thickness has too few layers for the selected formulation and physics;
- replication is used although openings, loads, constraints, or contact break
  symmetry.

## Flange and Bolt-Circle Pattern

### Partition by functional radial zones

Use only zones that exist and matter in the model:

1. bore/shaft interface;
2. hub or neck and its fillet/shoulder transition;
3. inner ligament from hub/bore to the bolt-hole band;
4. bolt-hole washer/contact band;
5. outer ligament and rim;
6. gasket/contact/load bands on the flange face;
7. axial flange, hub, neck, and step layers for a solid model.

Create concentric circles at the bore, hub shoulder, physical gasket/contact
limits, washer limits, transition limits, and outer rim. Do not create every
possible ring: overlapping rings or a ring closer than the allowed minimum size
produce sliver annuli.

Create radial auxiliary lines through every bolt-hole center and at every
mid-pitch plane. Add quadrant/tangent connections from each retained hole to
its washer boundary so each hole patch has compatible principal directions.
Where the hub or outer boundary interrupts this flow, end the lines at a
purpose-built transition circle and redesign the far-field patch counts.

### Sector and 3D mapping logic

- A one-pitch sector spans `360/N` degrees. Use it as an analysis sector only
  when geometry, material, gasket/contact, bolt pretension, loads, and
  constraints are cyclically identical.
- Even without cyclic analysis, a verified sector may be patterned as mesh
  topology. Equivalence and re-check every sector seam.
- Mesh hole/washer patches first, radial transition zones second, regular rim
  and bore/hub zones third.
- For a constant-thickness flange solid, quality-check one face mesh and sweep
  it axially. Isolate hub/neck steps and fillets into separate source-target
  blocks before the sweep.
- A varying-thickness or necked flange usually needs staged blocks; do not force
  a single axial drag across a shoulder or fillet.
- Use shells/midsurfaces only when the chosen formulation represents flange
  bending, contact, bolt load introduction, and thickness offsets adequately.

For each hole, derive an explicit circumferential count from size and curvature
and round it to a multiple of four when quadrant connections are required. Make
the pitch-circle and sector-boundary counts multiples of the hole count so
patterned seams remain compatible.

### Flange rejection checks

Reject or revise the plan when:

- a hole washer overlaps the bore, hub shoulder, adjacent washer, gasket limit,
  or outer rim without a shared transition plan;
- fewer than the solver/physics-required rows fit across an inner, outer, or
  adjacent-hole ligament;
- the hole-center and mid-pitch lines produce different edge counts on opposite
  sector boundaries;
- a mesh seam crosses a bolt bearing patch, gasket discontinuity, contact edge,
  or concentrated load unnecessarily;
- an axial sweep crosses a step/fillet with incompatible source-target loops;
- a cyclic sector is replicated despite nonperiodic pretension, loading,
  contact, material, or geometry.

## HyperMesh Realization Sequence

Use the installed-version ribbon or verified Tcl equivalents:

1. Detect/review holes and flanges and store their dimensions/descriptors.
2. Measure and record radii, angles, thicknesses, centers, clearances, area/
   volume, and bounding box as applicable.
3. Create points/nodes and local systems at verified centers, extrema, tangent
   locations, sector boundaries, and axial stations.
4. Create lines/arcs/circles and sectional planes/surfaces.
5. Use Split with Lines for projected or offset surface splits, including
   washer anchors, and Split with Planes/Surfaces for complete solid blocks.
6. Review split sections and apply only the intended trims.
7. Verify topology/mappability and count new entities before meshing.
8. Set exact shared-edge densities, bias, local size, curvature angle, washer
   layers, and through-thickness/sweep divisions.
9. Mesh one patch/block/sector, check all active metrics, then propagate.

Do not translate UI labels directly into Tcl. Resolve commands against the
installed HyperMesh help and capture the executed commands, marks, and entity
counts in the run evidence.

## Acceptance Evidence

Add these items to the normal partition and quality reports:

- measured center/axis/radii/PCD/thickness table with units and tolerance;
- construction entity table with point, line, plane, and target IDs;
- before/after split entity counts and minimum new edge/patch width;
- sphere patch/core layout or flange radial-zone/sector layout;
- ordered counts at every shared patch/block/sector edge;
- minimum elements across shell thickness and flange/hole ligaments;
- source-target-path, mesh order, symmetry/periodicity justification, and seam
  equivalence result;
- local Jacobian, warpage, aspect, skew, angle, and solver-specific failures at
  poles, core interfaces, holes, washers, fillets, seams, and transitions.

## Research Basis

Community examples were used to identify practical patterns, then topology and
operations were cross-checked against Altair documentation:

- Bilibili sphere structured-mesh and multi-scale circular examples show the
  recurring sphere/circular training patterns.
- A HyperMesh sphere example on Jishulink explicitly uses one-eighth symmetry.
- Altair China block-decomposition teaching and the “partition art” notes cover
  mappability, terminal-block backtracking, symmetry, and curved-sector splits.
- Community HyperMesh notes describe constructing points/nodes and projected
  lines before using shared edges to split geometry.
- Altair Measure documents length, angle, radius, area, volume, center-of-
  gravity, bounding-box, and snap-based measurement.
- Altair Features documents detection and management of 2D/3D holes, flanges,
  fillets, and associated geometry/mesh.
- Altair Split with Lines supports lines, bounding lines, offset/washer splits,
  graphical lines, projection, and section preview; Split with Planes supports
  complete surface/solid sections.
- Altair Solid Map requires complex solids to be partitioned into simpler
  mappable sections and still requires staged meshing and quality checks.
