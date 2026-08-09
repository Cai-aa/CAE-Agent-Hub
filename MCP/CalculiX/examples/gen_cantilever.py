#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate a public textbook cantilever-beam CalculiX input deck (C3D8 solids).

A 3D square steel bar clamped at one end and transversely loaded at the other —
a recognizable bending beam for the viewer. Pure public benchmark (no proprietary
data). Run with::

    python3 gen_cantilever.py            # writes cantilever.inp next to this file

Sanity targets (Euler-Bernoulli, steel, mm-t-s-MPa, P = 100 N tip):
  - tip deflection  delta = P L^3 / (3 E I) ~ 0.8 mm   (I = W H^3 / 12)
  - root stress     sigma = P L (H/2) / I     ~ 140 MPa
The viewer auto-magnifies the (small, elastic) deformation for display.
"""
from __future__ import annotations
from pathlib import Path

# Geometry / mesh / load (mm-t-s-MPa)
L = 120.0            # length (x)
W = 8.0              # cross-section width  (y)
H = 8.0              # cross-section height (z)
NX, NY, NZ = 24, 4, 4   # elements along x, y, z (384 hex; 625 nodes)
E, NU = 210000.0, 0.3
RHO = 7.85e-9        # t/mm^3 (7850 kg/m^3 steel)
P_PER_NODE = 4.0     # -Z load per tip-face node; (NY+1)(NZ+1)=25 nodes -> P=100 N total


def label(i: int, j: int, k: int) -> int:
    """Row-major node label (1-based), producing a contiguous 1..N sequence."""
    return k * (NX + 1) * (NY + 1) + j * (NX + 1) + i + 1


def main(out: Path | None = None) -> Path:
    out = out or Path(__file__).with_name("cantilever.inp")
    dx, dy, dz = L / NX, W / NY, H / NZ
    lines: list[str] = []
    lines.append("*HEADING")
    lines.append("Cantilever beam demo (public textbook benchmark, C3D8 solids), mm-t-s-MPa")
    lines.append("")

    # Nodes (cross-section centred on the y-z origin)
    lines.append("*NODE")
    for k in range(NZ + 1):
        for j in range(NY + 1):
            for i in range(NX + 1):
                x = i * dx
                y = j * dy - W / 2
                z = k * dz - H / 2
                lines.append(f"{label(i, j, k)}, {x:.3f}, {y:.3f}, {z:.3f}")

    # C3D8 hexahedra (local order: 1-2-3-4 bottom CCW, 5-6-7-8 top CCW)
    lines.append("*ELEMENT, TYPE=C3D8, ELSET=BEAM")
    el = 0
    for k in range(NZ):
        for j in range(NY):
            for i in range(NX):
                el += 1
                n = [
                    label(i, j, k), label(i + 1, j, k), label(i + 1, j + 1, k), label(i, j + 1, k),
                    label(i, j, k + 1), label(i + 1, j, k + 1), label(i + 1, j + 1, k + 1), label(i, j + 1, k + 1),
                ]
                lines.append(f"{el}, " + ", ".join(str(v) for v in n))

    def emit_nset(name: str, labels: list[int]) -> None:
        lines.append(f"*NSET, NSET={name}")
        for c in range(0, len(labels), 8):
            lines.append(", ".join(str(x) for x in labels[c:c + 8]))

    emit_nset("ROOT", [label(0, j, k) for k in range(NZ + 1) for j in range(NY + 1)])      # x = 0 face
    emit_nset("TIP", [label(NX, j, k) for k in range(NZ + 1) for j in range(NY + 1)])       # x = L face

    n_all = label(NX, NY, NZ)
    lines.append("*NSET, NSET=NALL, GENERATE")
    lines.append(f"1, {n_all}, 1")

    lines.append("*MATERIAL, NAME=STEEL")
    lines.append("*ELASTIC")
    lines.append(f"{E:.1f}, {NU}")
    lines.append("*DENSITY")
    lines.append(f"{RHO},")

    lines.append("*SOLID SECTION, ELSET=BEAM, MATERIAL=STEEL,")
    lines.append("*BOUNDARY")
    lines.append("ROOT, 1, 6")

    lines.append("*STEP")
    lines.append("*STATIC")
    lines.append("*CLOAD")
    lines.append(f"TIP, 3, {-P_PER_NODE}")
    lines.append("*NODE PRINT, NSET=NALL")
    lines.append("U")
    lines.append("*EL PRINT, ELSET=BEAM")
    lines.append("S")
    lines.append("*NODE FILE")
    lines.append("U")
    lines.append("*EL FILE")
    lines.append("S")
    lines.append("*END STEP")

    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {out}  ({NX*NY*NZ} C3D8, {n_all} nodes)")
    return out


if __name__ == "__main__":
    main()
