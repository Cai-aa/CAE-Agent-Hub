#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate a public textbook shell-cantilever modal CalculiX deck (S4 shells).

A flat rectangular steel plate clamped along one short edge, free everywhere
else, with a 5-mode ``*FREQUENCY`` step - the frequency-constrained sizing
demo: the ``*SHELL SECTION`` thickness is the design variable, and the
optimizer thins it until mode 1 approaches a resonance floor. Pure public
benchmark (no proprietary data). Run::

    python3 gen_plate_modal.py           # writes plate_modal.inp next to this file

Hand-calc sanity (Euler-Bernoulli cantilever, mm-t-s-MPa): the first bending
frequency of a wide plate reduces to

    f1 = (beta1^2 / 2 pi) * (t / L^2) * sqrt(E / (12 rho)),
    beta1 = 1.8751

For L = 300 mm steel this is f1 ~= 9.29 * t[mm] Hz, so t = 4 mm gives
f1 ~= 37.1 Hz. The canonical optimization run ("avoid resonance":
minimize mass subject to freq_1_hz >= 30) therefore lands near
t* = 30 / 9.29 ~= 3.23 mm - a number to verify the optimizer against.
S4 shells are Mindlin-Reissner, so ccx runs a few percent off the
Kirchhoff hand calc; treat it as a sanity band, not an exact target.

Geometry/mesh are in mm-t-s-MPa. Mode 1 is the first out-of-plane bending
mode; a wide plate also has torsion and in-plane modes higher up.
"""
from __future__ import annotations

from pathlib import Path

L = 300.0            # length (x)
W = 60.0             # width  (y)
T = 4.0              # shell thickness - the sizing design variable
NX, NY = 30, 6       # S4 elements along x, y (180 shells; 217 nodes)
E, NU = 210000.0, 0.3
RHO = 7.85e-9        # t/mm^3 (steel, 7850 kg/m^3)
N_MODES = 5


def label(i: int, j: int) -> int:
    """Row-major node label (1-based) over the (NX+1) x (NY+1) grid."""
    return j * (NX + 1) + i + 1


def main(out: Path | None = None) -> Path:
    out = out or Path(__file__).with_name("plate_modal.inp")
    dx, dy = L / NX, W / NY
    lines: list[str] = []
    lines.append("*HEADING")
    lines.append("Shell cantilever modal demo (public textbook benchmark, S4 shells), mm-t-s-MPa")
    lines.append("")

    # Nodes: flat plate in the x-y plane (z=0 mid-surface), centred on the y axis.
    lines.append("*NODE")
    for j in range(NY + 1):
        for i in range(NX + 1):
            x = i * dx
            y = j * dy - W / 2
            lines.append(f"{label(i, j)}, {x:.3f}, {y:.3f}, 0.0")

    # S4 quads, CCW: lower-left, lower-right, upper-right, upper-left.
    lines.append("*ELEMENT, TYPE=S4, ELSET=PLATE")
    el = 0
    for j in range(NY):
        for i in range(NX):
            el += 1
            n = [label(i, j), label(i + 1, j), label(i + 1, j + 1), label(i, j + 1)]
            lines.append(f"{el}, " + ", ".join(str(v) for v in n))

    # Node sets: ROOT (clamped x=0 edge) and NALL (all nodes).
    lines.append("*NSET, NSET=ROOT")
    lines.append(", ".join(str(label(0, j)) for j in range(NY + 1)))
    n_all = label(NX, NY)
    lines.append("*NSET, NSET=NALL, GENERATE")
    lines.append(f"1, {n_all}, 1")

    lines.append("*MATERIAL, NAME=STEEL")
    lines.append("*ELASTIC")
    lines.append(f"{E:.1f}, {NU}")
    lines.append("*DENSITY")
    lines.append(f"{RHO},")

    # Shell section: thickness on the data line (the design variable).
    lines.append("*SHELL SECTION, ELSET=PLATE, MATERIAL=STEEL")
    lines.append(f"{T:.3f},")

    lines.append("*BOUNDARY")
    lines.append("ROOT, 1, 6")

    # Eigen solve; *NODE PRINT puts the eigenvectors in the .dat next to the
    # eigenvalue table (a *FREQUENCY step writes a header-only .sta - normal).
    lines.append("*STEP")
    lines.append("*FREQUENCY")
    lines.append(f"{N_MODES}")
    lines.append("*NODE PRINT, NSET=NALL")
    lines.append("U")
    lines.append("*NODE FILE")
    lines.append("U")
    lines.append("*END STEP")

    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {out}  ({NX * NY} S4, {n_all} nodes, thickness={T} mm, {N_MODES} modes)")
    return out


if __name__ == "__main__":
    main()
