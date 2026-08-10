# CalculiX MCP

An MCP server that exposes the open-source **CalculiX** FEM solver (`ccx`) to MCP
clients. CalculiX is GPLv2, needs no license, and runs as a fire-and-forget CLI —
so this server is fully self-contained, with no live-session bridge and no license
state machine.

The workflow is: parse a CalculiX/Abaqus `.inp` deck, inspect its tunable design
variables, edit a value in place, submit it to `ccx`, read the text results
(`.dat`), and export those `.dat` results to `result_mesh.json` so the
repo's [Text to CAE Viewer](../../viewer) can render the mesh and stress field.

This is the first open-source-solver FEM MCP in the hub (the existing FEA line
stopped at FEniCS references), filling the gap noted in Issue #14.

## Tools

| Tool | Purpose |
| --- | --- |
| `fea_health` | Report meshio availability and the detected `ccx` executable. |
| `parse_inp` | Parse a `.inp` deck: nodes, element counts, shell/beam sections, materials, loads. |
| `list_design_vars_tool` | List tunable design variables (shell thickness, beam section, material E/nu/density, load magnitude), each with a `var_id` locator. |
| `modify_card_tool` | Edit one design variable in place by `var_id`; pure-text replacement, writes a new `.inp`. |
| `run_solver_tool` | Run `ccx -i <jobname>` on a deck. Success ignores the exit code (see below). |
| `read_results_tool` | Parse the `.dat` for max von Mises (self-computed), max displacement, volume, mass. |
| `export_results_tool` | Export the run to `result_mesh.json` (viewer format). |
| `optimize_structure_tool` | Two-stage sizing optimization (LHS sweep + coordinate descent): minimize mass subject to stress/displacement bounds by tuning scalar design variables (shell thickness, beam section, material, load). Shell/beam models only — see [Optimization](#optimization). |

## Hard-won CalculiX contracts (encoded in the solver)

These are why this server is non-trivial — all from public CalculiX behaviour:

- **ccx exit code is untrusted** — `ccx` returns 0 even when it prints `*ERROR`.
  Success = no `*ERROR` in stdout **and** the `.sta` file has a data row **and**
  no timeout.
- **`.dat` has no von Mises** — only 6 stress components; σ_vm is self-computed.
- **`.dat` has no total volume/mass** — computed from the mesh geometry × `*DENSITY`.
- **Never `meshio.write`** — it drops every card and rewrites `B31`→`B31H`
  (corrupts the file). `modify_card` does pure-text in-place edits instead.

## Optimization

`optimize_structure_tool` runs two-stage **sizing** optimization: a Latin
Hypercube coarse sweep, then coordinate-descent refinement, minimizing mass
subject to stress and displacement constraints by editing scalar cards in place.

```python
optimize_structure_tool(
    path="examples/bracket.inp",
    variables={"shell.PLATE.thickness": [2.0, 8.0]},
    n_lhs=8, max_solves=18,
)
# -> best ~4.1 mm, ~-48% mass, stress < 250 MPa, displacement < 1.5 mm
```

Scope and honesty:

- **Shell/beam models only.** Solids (C3D8) expose no scalar geometry card, so
  there is no thickness to thin; use shape/topology optimization instead.
- This is **sizing/parameter optimization, not topology optimization** — it
  thins sections, it does not redistribute material in space.
- The best deck is written next to the input as `<stem>.optimized.inp`; pass it
  to `export_results_tool` to render the optimized design.

## Install

From this directory (Linux/macOS; adapt the venv activation on Windows):

```bash
uv venv .venv --python 3.11
uv pip install --python .venv/bin/python "mcp>=1.0,<1.8" meshio numpy "python-dotenv>=1,<2"
uv pip install --python .venv/bin/python pytest   # dev only
```

> `mcp` is pinned below 1.8: `mcp` 2.0 removed `mcp.server.fastmcp` (the FastMCP
> import used here and by the hub's other MCPs).

Install CalculiX separately (e.g. `ccx` or `ccx_preCICE` on your PATH, or set
`CCX_EXE`). `fea_health` will tell you whether the executable was detected.

## Run

```bash
.venv/bin/python mcp_server.py          # stdio MCP transport
```

Register it with an MCP client using `examples/mcp_config.example.json`.

## Example: cantilever benchmark

`examples/cantilever.inp` is a **public textbook cantilever** (steel C3D8 solid
bar, clamped at one end, transversely loaded at the other). Regenerate it with:

```bash
python3 examples/gen_cantilever.py
```

Hand-calc sanity targets (Euler-Bernoulli, mm-t-s-MPa, P = 100 N): tip deflection
≈ 0.8 mm, root stress ≈ 140 MPa. The viewer auto-magnifies the small elastic
deformation for display.

## Tests

```bash
.venv/bin/python -m pytest
```

Parser and exporter tests run without a solver. Solver tests are skipped
automatically when `ccx` is not detected, so the suite stays green before
CalculiX is installed.

## Contents

- `mcp_server.py` — FastMCP stdio server.
- `tools/inp_parser.py` — `.inp` card parsing + text in-place editing.
- `tools/solver.py` — `ccx` subprocess + `.dat` result parsing.
- `tools/result_exporter.py` — `.dat`/`.inp` → `result_mesh.json` (viewer format).
- `tools/optimizer.py` — two-stage sizing optimization (LHS + coordinate descent).
- `examples/` — public cantilever benchmark + generator + MCP config example.
- `tests/` — pytest suite.

## Repository rules

Commit only reusable source, examples (public benchmarks), tests, and docs. Do
not commit the virtual environment, `.env`, or any generated solver output
(`.frd`, `.dat`, `.sta`, `.cvg`, job directories). Input `.inp` decks are source
and are committed.
