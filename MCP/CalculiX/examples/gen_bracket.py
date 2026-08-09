#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate a public textbook shell-bracket CalculiX input deck (S4 shells).

A flat rectangular steel plate clamped along one short edge and transversely
loaded along the other - a bending shell whose ``*SHELL SECTION`` thickness is
the sizing design variable. Pure public benchmark (no proprietary data). Run::

    python3 gen_bracket.py            # writes bracket.inp next to this file

The thickness (ELSET=PLATE) is what the sizing optimizer thins to minimize mass
subject to stress/deflection constraints. Geometry/mesh/load are in mm-t-s-MPa.
"""
from __future__ import annotations

from pathlib import Path

L = 120.0            # length (x)
W = 40.0             # width  (y)
T = 5.0              # shell thickness (z) - the sizing design variable
NX, NY = 24, 8       # S4 elements along x, y (192 shells; 225 nodes)
E, NU = 210000.0, 0.3
RHO = 7.85e-9        # t/mm^3 (steel, 7850 kg/m^3)
P_PER_NODE = 10.0    # -Z load per tip-edge node; (NY+1)=9 nodes -> P=90 N total


def label(i: int, j: int) -> int:
    """Row-major node label (1-based) over the (NX+1) x (NY+1) grid."""
    return j * (NX + 1) + i + 1


def main(out: Path | None = None) -> Path:
    out = out or Path(__file__).with_name("bracket.inp")
    dx, dy = L / NX, W / NY
    lines: list[str] = []
    lines.append("*HEADING")
    lines.append("Shell bracket demo (public textbook benchmark, S4 shells), mm-t-s-MPa")
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

    # Node sets: ROOT (clamped x=0 edge), TIP (loaded x=L edge), NALL (all).
    lines.append("*NSET, NSET=ROOT")
    lines.append(", ".join(str(label(0, j)) for j in range(NY + 1)))
    lines.append("*NSET, NSET=TIP")
    lines.append(", ".join(str(label(NX, j)) for j in range(NY + 1)))
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

    lines.append("*STEP")
    lines.append("*STATIC")
    lines.append("*CLOAD")
    lines.append(f"TIP, 3, {-P_PER_NODE}")
    lines.append("*NODE PRINT, NSET=NALL")
    lines.append("U")
    lines.append("*EL PRINT, ELSET=PLATE")
    lines.append("S")
    lines.append("*NODE FILE")
    lines.append("U")
    lines.append("*EL FILE")
    lines.append("S")
    lines.append("*END STEP")

    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {out}  ({NX * NY} S4, {n_all} nodes, thickness={T} mm)")
    return out


if __name__ == "__main__":
    main()
