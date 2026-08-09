---
name: calculix-fem
description: Workflow skill for driving the CalculiX MCP server over .inp decks — model inspection, in-place design-variable edits, ccx solve, .dat result reading, and result_mesh.json export for the viewer. Use when an agent must run an open-source linear-static FEM analysis on CalculiX, tune section/material/load parameters, or produce a viewer-renderable result.
---

# CalculiX FEM

CalculiX (`ccx`) is an open-source FEM solver (GPLv2, no license). It reads
Abaqus-style `.inp` decks and writes text `.dat` results plus `.frd` field output.
`ccx` returns exit code 0 even on `*ERROR`, so never judge success by the exit
code — the solver layer checks stdout for `*ERROR` and requires a data row in the
`.sta`.

## When to Use

Use this skill when an agent must run an open-source linear-static FEA analysis on
CalculiX: parse/inspect a `.inp` deck, tune section/material/load parameters, solve
with `ccx`, read `.dat` results, or export a viewer-renderable result. For commercial
solvers (Abaqus/Ansys), use those solvers' own skills instead.

## Workflow

1. `fea_health` — confirm meshio is available and `ccx` is detected.
2. `parse_inp` — inspect the `.inp` (nodes, elements, sections, materials, loads).
3. `list_design_vars_tool` — list tunable variables; each carries a `var_id`.
4. `modify_card_tool` — change a variable by `var_id` (pure-text, in place).
5. `run_solver_tool` — submit the deck to `ccx`.
6. `read_results_tool` — read max von Mises (self-computed), max |U|, volume, mass.
7. `export_results_tool` — write `result_mesh.json` for the viewer.

## Rules

- Units follow the `.inp` working system (commonly mm-t-s-MPa). Report them.
- `.dat` has no von Mises column and no total volume/mass — these are derived.
- Never rewrite a deck with `meshio.write` (it drops cards and corrupts element
  types). Use `modify_card_tool`.
- For the deck to produce both text results and the field output the viewer needs,
  include `*NODE PRINT`/`*EL PRINT` (for `.dat`) and `*NODE FILE`/`*EL FILE`
  (for `.frd`).

## Example

`MCP/CalculiX/examples/cantilever.inp` is a public cantilever benchmark (steel
C3D8 solid bar, clamped end, transverse tip load). Hand-calc targets at P = 100 N:
tip deflection ≈ 0.8 mm, root stress ≈ 140 MPa.
