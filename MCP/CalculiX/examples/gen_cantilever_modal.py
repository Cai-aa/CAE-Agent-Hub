#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate a public textbook modal-analysis CalculiX deck (C3D8 cantilever).

Same clamped steel bar as ``cantilever.inp`` but the step is ``*FREQUENCY``
(free vibration, no load): 5 eigenpairs, eigenvectors printed to the ``.dat``
(``*NODE PRINT U``) so frequencies and mode shapes both parse from text. Pure
public benchmark (no proprietary data). Run::

    python3 gen_cantilever_modal.py   # writes cantilever_modal.inp next to this file

Hand-calc sanity targets (Euler-Bernoulli clamped-free, steel, mm-t-s-MPa):
f_n = (beta_n^2 / 2pi) * sqrt(E I / (rho A L^4)), beta_1 = 1.8751 ->
f1 ~ 464 Hz, f2 ~ 2908 Hz. Two honest ccx notes: the square 8x8 section is
doubly symmetric, so bending modes come in degenerate pairs (f1 = f2, f3 = f4);
and fully-integrated C3D8 hexes shear-lock in bending, so ccx runs ~5-10%
STIFFER than the Euler-Bernoulli hand calc (measured f1 ~ 502 Hz).
"""
from __future__ import annotations

from pathlib import Path

from gen_cantilever import E, NU, NX, NY, NZ, RHO, W, H, L, label

N_MODES = 5


def main(out: Path | None = None) -> Path:
    out = out or Path(__file__).with_name("cantilever_modal.inp")
    dx, dy, dz = L / NX, W / NY, H / NZ
    lines: list[str] = []
    lines.append("*HEADING")
    lines.append("Cantilever modal demo (public textbook benchmark, C3D8 solids), mm-t-s-MPa")
    lines.append("")

    lines.append("*NODE")
    for k in range(NZ + 1):
        for j in range(NY + 1):
            for i in range(NX + 1):
                x = i * dx
                y = j * dy - W / 2
                z = k * dz - H / 2
                lines.append(f"{label(i, j, k)}, {x:.3f}, {y:.3f}, {z:.3f}")

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

    emit_nset("ROOT", [label(0, j, k) for k in range(NZ + 1) for j in range(NY + 1)])
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
    lines.append(f"*FREQUENCY")
    lines.append(f"{N_MODES}")
    lines.append("*NODE PRINT, NSET=NALL")
    lines.append("U")
    lines.append("*NODE FILE")
    lines.append("U")
    lines.append("*END STEP")

    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {out}  ({NX*NY*NZ} C3D8, {n_all} nodes, {N_MODES} modes requested)")
    return out


if __name__ == "__main__":
    main()
