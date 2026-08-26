# -*- coding: utf-8 -*-
"""mcp_server.py - CalculiX MCP server.

Exposes the open-source CalculiX FEM solver to MCP clients: parse an ``.inp``
deck, edit design variables in place, run ccx, read text results, and export the
field output to ``result_mesh.json`` for the CAE-Agent-Hub viewer.

CalculiX-only (no commercial-solver backends). Run with::

    python mcp_server.py            # stdio MCP transport

or register with an MCP client using the example config in ``examples/``.
"""
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    def load_dotenv(*args: object, **kwargs: object) -> bool:
        return False

from mcp.server.fastmcp import FastMCP

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))  # so `from tools.X import ...` works from any CWD

from tools.inp_parser import list_design_vars, modify_card, parse_model  # noqa: E402
from tools.optimizer import optimize_structure  # noqa: E402
from tools.result_exporter import export_result_mesh  # noqa: E402
from tools.solver import detect_ccx, read_results, run_solver  # noqa: E402

load_dotenv(ROOT / ".env")

INSTRUCTIONS = """You are driving CalculiX (open-source FEM) through MCP.

Typical workflow:
1. fea_health — confirm meshio is available and the ccx executable is detected.
2. parse_inp — inspect a .inp model (nodes, elements, sections, materials, loads).
3. list_design_vars — list tunable design variables, each with a var_id locator.
4. modify_card — edit a variable in place (text in-place; never rewrite via meshio).
5. run_solver — submit the deck to ccx (fire-and-forget; success ignores the exit
   code and checks stdout for *ERROR plus a data row in the .sta).
6. read_results — parse the .dat for max von Mises (self-computed), max |U|, mass.
7. export_results — turn the .dat results into a result_mesh.json the viewer
   can render.
8. optimize_structure (optional) — sizing optimization: minimize mass subject
   to stress/displacement bounds by tuning design variables (shell thickness,
   beam section, material, load). Each trial is a full solve, so set
   max_solves to bound wall time.
9. modal (*FREQUENCY) decks work with the same tools: read_results returns the
   frequency table (frequencies / n_modes); export_results with mode=N renders
   that mode shape in the viewer (stress-free displacement field).
10. avoid-resonance sizing: optimize_structure on a *FREQUENCY deck with a
   freq_<N>_hz constraint (e.g. freq_1_hz > 300) thins sections until mode N
   sits just above the floor - static metrics and frequency metrics come from
   static and modal decks respectively, so match the constraint set to the deck.

Units follow the .inp's working system (commonly mm-t-s-MPa). CalculiX has no
license; ccx returns 0 even on *ERROR, so never trust the exit code alone.
"""

mcp = FastMCP("CalculiX MCP", instructions=INSTRUCTIONS)


@mcp.tool()
def fea_health() -> dict:
    """Report meshio availability and the detected CalculiX executable."""
    try:
        import meshio  # noqa: F401

        meshio_ok = True
        meshio_err = None
    except Exception as e:  # pragma: no cover
        meshio_ok = False
        meshio_err = str(e)
    return {
        "status": "ok",
        "meshio_available": meshio_ok,
        "meshio_error": meshio_err,
        "ccx_exe": detect_ccx() or "(not found; set CCX_EXE or install ccx)",
    }


@mcp.tool()
def parse_inp(path: str) -> dict:
    """Parse a CalculiX/Abaqus ``.inp`` deck into a model overview.

    Returns nodes, element counts by type, shell/beam sections, materials, loads,
    and any unsupported cards. meshio is used opportunistically for bbox/set names
    but never blocks parsing.
    """
    return parse_model(path)


@mcp.tool()
def list_design_vars_tool(path: str) -> dict:
    """List tunable design variables (shell thickness, beam section, material E/nu/
    density, load magnitude), each carrying a ``var_id`` and a ``modify`` locator."""
    return list_design_vars(path)


@mcp.tool()
def modify_card_tool(
    path: str,
    var_id: str,
    new_value: float,
    out_path: str | None = None,
) -> dict:
    """Edit one design variable (located by ``var_id`` from list_design_vars) in
    place via pure-text replacement and write a new ``.inp``. ``out_path`` defaults
    to overwriting the input.
    """
    return modify_card(path, var_id, new_value, out_path)


@mcp.tool()
def run_solver_tool(path: str, timeout: int = 1800) -> dict:
    """Run CalculiX (``ccx -i <jobname>``) on an ``.inp`` deck. Success is judged by
    stdout having no ``*ERROR`` and the ``.sta`` holding a data row (the ccx exit
    code is untrusted). Returns status plus ``.dat``/``.sta`` paths."""
    return run_solver(path, timeout=timeout)


@mcp.tool()
def read_results_tool(result_path: str) -> dict:
    """Parse a CalculiX ``.dat`` (or the job dir containing it) for max von Mises
    (self-computed from 6 components), max displacement magnitude, volume and mass."""
    return read_results(result_path)


@mcp.tool()
def export_results_tool(
    inp_path: str,
    dat_path: str | None = None,
    out_path: str | None = None,
    deformation_scale: float | None = None,
    mode: int | None = None,
) -> dict:
    """Export a CalculiX run to ``result_mesh.json`` (the CAE-Agent-Hub viewer
    format). Mesh topology comes from the ``.inp`` and displacement/stress fields
    from the ``.dat`` (same original node/element labels); when ``dat_path`` is
    omitted a sibling ``<stem>.dat`` is used, and if that is missing a mesh-only
    file is produced. ``deformation_scale`` is auto-chosen when None. For modal
    (``*FREQUENCY``) runs, pass ``mode=N`` to export that mode's eigenvector as
    the displacement field (stress-free); the frequencies themselves come from
    ``read_results``."""
    res = export_result_mesh(
        inp_path,
        dat_path=dat_path,
        out_path=out_path,
        deformation_scale=deformation_scale,
        mode=mode,
    )
    out = res.pop("_out_path", None)
    return {"out_path": out, "nodes": len(res["nodes"]), "elements": len(res["elements"]),
            "fieldRanges": res["fieldRanges"], "elementType": res["elementType"]}


@mcp.tool()
def optimize_structure_tool(
    path: str,
    variables: dict,
    objective: dict | None = None,
    constraints: list | None = None,
    n_lhs: int = 5,
    max_solves: int = 10,
    max_iters: int = 6,
    seed: int = 42,
    timeout: int = 1800,
) -> dict:
    """Run two-stage sizing optimization on a CalculiX ``.inp`` deck: minimize mass
    subject to stress/displacement/natural-frequency constraints by tuning scalar
    design variables (shell thickness, beam section, material, load).
    ``variables`` maps each ``var_id`` (from ``list_design_vars``) to
    ``[lower, upper]``. Defaults: objective = minimize mass; constraints = max
    von Mises < 250 MPa and max displacement < 1.5 mm (needs a ``*STATIC``
    deck). A frequency constraint such as ``{"metric": "freq_1_hz", "op": ">",
    "value": 300.0}`` (avoid resonance) instead needs a ``*FREQUENCY`` deck and
    is evaluated from the ``.dat`` eigenvalue table. Returns the best feasible
    design found, its mass reduction vs the baseline, the full evaluation
    history, and the convergence reason. The best deck is written next to the
    input as ``<stem>.optimized.inp``. Each evaluation is a real ccx solve, so
    wall time ~= (1 + n_lhs + coord-descent probes) x per-solve time, bounded
    by ``max_solves``."""
    return optimize_structure(
        path,
        variables,
        objective=objective,
        constraints=constraints,
        n_lhs=n_lhs,
        max_solves=max_solves,
        max_iters=max_iters,
        seed=seed,
        timeout=timeout,
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
