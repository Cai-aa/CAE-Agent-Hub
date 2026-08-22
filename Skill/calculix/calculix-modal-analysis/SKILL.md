---
name: calculix-modal-analysis
description: Workflow skill for CalculiX modal analysis (*FREQUENCY steps) — natural frequencies and mode shapes via the CalculiX MCP. read_results returns the frequency table; export_results with mode=N renders that mode shape in the browser viewer. Use when an agent must extract natural frequencies, check resonance margins, or visualize mode shapes on an open-source solver.
---

# CalculiX Modal Analysis

Free-vibration eigenanalysis on a CalculiX deck: a `*FREQUENCY` step requests N
eigenpairs; ccx prints the eigenvalue table and per-mode eigenvectors to the
`.dat`, so both frequencies and mode shapes parse from text (no `.frd` needed).

## When to Use

Use when an agent must extract natural frequencies, check resonance/vibration
margins, or visualize mode shapes on a CalculiX model. Driven by the same MCP
tools as static runs (`run_solver` → `read_results` → `export_results`).

Not for: static stress/deflection (use `calculix-fem`), transient/dynamic
response (not yet supported), or sizing optimization (`calculix-sizing-optimization`).

## Workflow

1. Confirm the deck has `*DENSITY` under its `*MATERIAL` — frequencies need
   mass; without density ccx fails the eigenvalue solve.
2. Confirm the step is `*FREQUENCY` with the wanted mode count on its data
   line, and `*NODE PRINT, NSET=<all>` / `U` so eigenvectors reach the `.dat`.
   No load is applied (free vibration); keep the `*BOUNDARY` clamp set.
3. `run_solver_tool` — submit the deck. Note: a `*FREQUENCY` run writes a
   **header-only `.sta`** (no increments in an eigenvalue solve); success
   accepts a non-empty `.dat` instead, so this is normal, not a failure.
4. `read_results_tool` — returns `frequencies` as
   `[{mode, eigenvalue, freq_rad_s, freq_hz}]` and `n_modes` (a doubly
   symmetric section gives degenerate pairs — f1 = f2 — which is expected).
5. `export_results_tool` with `mode=N` — writes `result_mesh.json` holding
   that mode's eigenvector as a stress-free displacement field; the viewer
   renders the mode shape with its usual auto-scaled deformation.

## Rules

- Units follow the `.inp` (commonly mm-t-s-MPa → frequencies in Hz).
- Eigenvectors are mass-normalized; their magnitude carries no physical
  displacement meaning — only the shape does. The viewer auto-scales.
- Fully-integrated C3D8 hexes shear-lock in bending: ccx frequencies run
  ~5-10% ABOVE the Euler-Bernoulli hand calc. For tight margins, refine the
  mesh through the thickness (or switch element type) and report the gap.
- Hand-calc check for a clamped-free bar: f_n = (beta_n^2 / 2pi) *
  sqrt(E I / (rho A L^4)), beta_1 = 1.8751.

## Example

`MCP/CalculiX/examples/cantilever_modal.inp` is the public cantilever benchmark
with a 5-mode `*FREQUENCY` step. ccx gives f1 = f2 ~ 502 Hz (degenerate bending
pair on the square section) vs the Euler-Bernoulli hand calc ~ 464 Hz (+8%,
C3D8 shear locking). Mode 1 exports straight into the viewer as the classic
half-sine bend.
