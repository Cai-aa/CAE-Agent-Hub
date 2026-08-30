# Coin-style O-grid topology

## Geometry

Assume a circular section of radius `R`, a cylinder length `L`, and a centered square with half-width `a`.

- Enforce `R > 0`, `L > 0`, and `0 < a < R/sqrt(2)`.
- Use `a/R = 0.30-0.45` only as a starting search range, not as a universal optimum.
- Measure the corner ligament as `d_corner = R - sqrt(2)*a`.
- Measure the side ligament as `d_side = R - a`.
- Reduce `a` if corner cells become compressed; increase `a` if the center block is excessively fine relative to the outer ring.

Create four connector lines from `(±a, ±a)` to `(±R/sqrt(2), ±R/sqrt(2))` with matching signs. The cross-section must contain exactly five logical blocks: one square and four outer sectors.

## Compatible counts

Let:

- `n_side` be the divisions on each square side and each 90-degree outer arc.
- `n_radial` be the divisions on each connector edge.
- `n_axial` be the divisions through the length.

Then:

- Total outer circumference divisions: `n_circ = 4*n_side`.
- Cross-section quadrilaterals: `N_quad = n_side^2 + 4*n_side*n_radial`.
- Expected hexahedra: `N_hex = N_quad*n_axial`.

Use these identities as topology checks. A mismatch usually means an edge was seeded inconsistently, a block was not mapped, or the target preprocessor generated a different element topology.

## Sizing checks

Estimate characteristic sizes before meshing:

- Square-side spacing: `h_square = 2*a/n_side`.
- Outer-arc spacing: `h_arc = (pi*R/2)/n_side`.
- Corner radial spacing: `h_corner = d_corner/n_radial`.
- Side radial spacing: `h_side = d_side/n_radial`.
- Axial spacing: `h_axial = L/n_axial`.

Keep neighboring characteristic sizes comparable. Start by keeping the largest-to-smallest estimate below about 2, then inspect actual corner cells and adapt. Use biased seeding only when the transition remains smooth and symmetric.

Prefer circumferential counts divisible by 4. Increase counts in whole-block-compatible increments; never change only one sector.
