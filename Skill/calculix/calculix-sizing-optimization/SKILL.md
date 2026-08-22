---
name: calculix-sizing-optimization
description: Workflow skill for two-stage sizing/parameter optimization on a CalculiX shell or beam deck via the optimize_structure tool — Latin Hypercube sweep plus coordinate descent to minimize mass subject to stress/displacement or natural-frequency constraints by tuning scalar section/material/load cards. Use when an agent must lighten a CalculiX shell or beam model while keeping stress and deflection within limits, or must thin a deck until its first modes clear a resonance floor (freq_1_hz constraint on a *FREQUENCY deck).
---

# CalculiX Sizing Optimization

Two-stage **sizing/parameter** optimization: minimize mass subject to stress,
displacement, or natural-frequency constraints by editing scalar design
variables in place (shell thickness, beam section, material E/nu/density, load
magnitude). The mesh and geometry never change — only scalar cards.

This is **sizing optimization, not topology optimization**. It thins sections;
it does not redistribute material in space.

## When to Use

Use when an agent must lighten a CalculiX **shell or beam** model while keeping
von Mises stress and displacement within limits (static deck), or must lighten
it while keeping a natural frequency above a resonance floor (modal deck).
Driven by the `optimize_structure_tool` MCP tool.

Do NOT use for:

- **Solid (C3D8 / C3D8R) models.** Solids expose no scalar geometry card — their
  mass is set by node-defined volume x density, so there is no thickness to
  thin. Material/load variables on a solid are degenerate for mass minimization
  (density changes mass but not stiffness; E changes stiffness but not mass).
  Solid lightweighting needs shape or topology optimization, which is a
  different problem and is not covered here.
- Topology optimization (material distribution over a fixed mesh) — separate,
  future work.

## Workflow

1. `parse_inp` / `list_design_vars_tool` — confirm the deck and find the
   `shell.<elset>.thickness` (or beam section) `var_id` and its current value.
2. Choose bounds `{var_id: [lower, upper]}` to bracket the search. Mass falls
   monotonically with shell/beam thickness.
3. `optimize_structure_tool` — run the two-stage loop (LHS sweep, then
   coordinate descent). Each evaluation is a real ccx solve, so set `max_solves`
   to bound wall time.
4. Inspect the result: `best` (vars, mass_kg, stress_vm, disp, feasible,
   `mass_reduction_pct`), `converged` / `termination_reason`, and `history`.
5. Optional: `export_results_tool` on the persisted `<stem>.optimized.inp` to
   render the optimized design in the viewer.

## Rules

- Frame results as **sizing/parameter optimization** (section sizing), never
  topology.
- Defaults: minimize mass s.t. max von Mises < 250 MPa and max displacement <
  1.5 mm; pass `objective` / `constraints` to override.
- **Match the constraint set to the deck**: a `*STATIC` deck reports
  `max_stress_vm` / `max_disp`; a `*FREQUENCY` deck reports `freq_<N>_hz`
  (mode N in Hz, from the `.dat` eigenvalue table) and nothing else. Mixing a
  stress constraint into a modal optimization makes every point infeasible —
  the run warns about missing metrics rather than failing opaquely.
- **Avoid-resonance runs**: on a modal deck pass e.g.
  `constraints=[{"metric": "freq_1_hz", "op": ">", "value": 300.0}]`; thinning
  stops where mode 1 sits just above the floor. Constraint metric names are
  validated (`mass`, `max_stress_vm`, `max_disp`, `freq_<N>_hz`).
- The acceptance rule assumes shell/beam thickness (mass-monotone). Material E
  and load magnitude are exposed as variables but are not validated for
  mass-minimization — prefer section thickness.
- Units follow the `.inp` (commonly mm-t-s-MPa); `mass_kg` is reported in kg.
- A `converged=False` result is not a failure: `best` is the lightest feasible
  point found, and `bound_limited` tells whether it already sits at the box
  optimum (widen the bounds to do better).

## Example

`MCP/CalculiX/examples/bracket.inp` is a public S4 shell bracket (steel plate,
clamped edge, transverse tip load). Starting from thickness 8 mm with bounds
`{"shell.PLATE.thickness": [2.0, 8.0]}` and `n_lhs=8`, the optimizer converges
to ~4.1 mm — about **-48% mass** — while keeping stress < 250 MPa and
displacement < 1.5 mm.

`MCP/CalculiX/examples/plate_modal.inp` is the avoid-resonance counterpart: a
public S4 shell cantilever plate with a 5-mode `*FREQUENCY` step. With
`constraints=[{"metric": "freq_1_hz", "op": ">", "value": 30.0}]` the
optimizer thins from 4 mm to ~3.23 mm — **-19% mass**, f1 = 30.4 Hz — matching
the Euler-Bernoulli hand calc t* = 30 / 9.29 ≈ 3.23 mm for L = 300 steel
(f1 ≈ (1.8751²/2π)(t/L²)√(E/12ρ)).
