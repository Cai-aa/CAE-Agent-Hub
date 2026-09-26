"""Generate and validate a demonstrative involute-profile hexahedral gear mesh.

This is a pre-processing example, not a certified gear design or a solved case.
The tooth flanks follow an involute above the base circle; the short root
transition is deliberately simplified rather than a cutter-generated fillet.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path


TEETH = 20
MODULE_MM = 2.0
PRESSURE_ANGLE_DEG = 20.0
THICKNESS_MM = 8.0
BORE_RADIUS_MM = 5.0
SECTORS_PER_TOOTH = 24
Z_LAYERS = 2
RADIAL_RINGS_MM = (5.0, 8.0, 11.0, 14.0, 16.5)


def tooth_radius(angle: float) -> float:
    """Outside radius at a polar angle; involute flanks, simplified root."""
    pitch = MODULE_MM * TEETH / 2.0
    base = pitch * math.cos(math.radians(PRESSURE_ANGLE_DEG))
    tip = pitch + MODULE_MM
    root = pitch - 1.25 * MODULE_MM
    tooth_pitch_angle = 2.0 * math.pi / TEETH
    distance = abs((angle + tooth_pitch_angle / 2) % tooth_pitch_angle
                   - tooth_pitch_angle / 2)

    def involute(radius: float) -> float:
        parameter = math.sqrt((radius / base) ** 2 - 1.0)
        return parameter - math.atan(parameter)

    half_at_base = math.pi / (2.0 * TEETH) + involute(pitch)
    half_at_tip = half_at_base - involute(tip)
    transition = math.radians(0.75)
    if distance <= half_at_tip:
        return tip
    if distance < half_at_base:
        lo, hi = base, tip
        for _ in range(45):
            mid = (lo + hi) / 2.0
            if half_at_base - involute(mid) > distance:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2.0
    if distance < half_at_base + transition:
        fraction = (distance - half_at_base) / transition
        return base + (root - base) * fraction
    return root


def determinant(a, b, c) -> float:
    return (a[0] * (b[1] * c[2] - b[2] * c[1])
            - a[1] * (b[0] * c[2] - b[2] * c[0])
            + a[2] * (b[0] * c[1] - b[1] * c[0]))


def element_jacobian(points, xi: float, eta: float, zeta: float) -> float:
    """C3D8 isoparametric Jacobian at a reference position, in mm cubed."""
    signs = ((-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
             (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1))
    tangents = []
    for component in range(3):
        tangents.append(tuple(sum(
            sign[component]
            * (1.0 + sign[(component + 1) % 3] * (xi, eta, zeta)[(component + 1) % 3])
            * (1.0 + sign[(component + 2) % 3] * (xi, eta, zeta)[(component + 2) % 3])
            * point[axis] / 8.0 for sign, point in zip(signs, points)
        ) for axis in range(3)))
    return determinant(*tangents)


def generate(output: Path) -> dict:
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    sectors = TEETH * SECTORS_PER_TOOTH
    rings = len(RADIAL_RINGS_MM) + 1

    def node_id(k: int, j: int, i: int) -> int:
        return 1 + i + sectors * (j + rings * k)

    coordinates = {}
    lines = [
        "*Heading",
        "ANSA MCP educational spur gear mesh; mm, N, MPa",
        "** 20 teeth; module 2 mm; pressure angle 20 deg; thickness 8 mm; bore 10 mm",
        "** Involute flanks; simplified root transition; not manufacturing-certified",
        "*Node",
    ]
    for k in range(Z_LAYERS + 1):
        z = k * THICKNESS_MM / Z_LAYERS
        for j in range(rings):
            for i in range(sectors):
                angle = 2.0 * math.pi * i / sectors
                radius = (RADIAL_RINGS_MM[j] if j < rings - 1
                          else tooth_radius(angle))
                x, y = radius * math.cos(angle), radius * math.sin(angle)
                identifier = node_id(k, j, i)
                coordinates[identifier] = (x, y, z)
                lines.append(f"{identifier}, {x:.10f}, {y:.10f}, {z:.10f}")

    lines.append("*Element, type=C3D8, elset=GEAR_SOLID")
    element_count = 0
    min_jacobian = math.inf
    gauss = 1.0 / math.sqrt(3.0)
    faces = Counter()
    for k in range(Z_LAYERS):
        for j in range(rings - 1):
            for i in range(sectors):
                next_i = (i + 1) % sectors
                bottom = (node_id(k, j, i), node_id(k, j + 1, i),
                          node_id(k, j + 1, next_i), node_id(k, j, next_i))
                top = tuple(node_id(k + 1, jj, ii) for jj, ii in
                            ((j, i), (j + 1, i), (j + 1, next_i), (j, next_i)))
                nodes = bottom + top
                points = [coordinates[n] for n in nodes]
                for xi in (-gauss, gauss):
                    for eta in (-gauss, gauss):
                        for zeta in (-gauss, gauss):
                            jacobian = element_jacobian(points, xi, eta, zeta)
                            min_jacobian = min(min_jacobian, jacobian)
                            if jacobian <= 0.0:
                                raise ValueError(
                                    f"Element {element_count + 1}: nonpositive Jacobian"
                                )
                for face in ((0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4),
                             (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
                    faces[tuple(sorted(nodes[index] for index in face))] += 1
                element_count += 1
                lines.append(f"{element_count}, " + ", ".join(map(str, nodes)))
    if any(count not in (1, 2) for count in faces.values()):
        raise ValueError("Nonmanifold element face found")
    expected_boundary_faces = 2 * sectors * ((rings - 1) + Z_LAYERS)
    boundary_faces = sum(count == 1 for count in faces.values())
    if boundary_faces != expected_boundary_faces:
        raise ValueError(f"Boundary face mismatch: {boundary_faces}")

    bore_ids = [node_id(k, 0, i) for k in range(Z_LAYERS + 1)
                for i in range(sectors)]
    lines.append("*Nset, nset=BORE_NODES")
    for start in range(0, len(bore_ids), 16):
        lines.append(", ".join(map(str, bore_ids[start:start + 16])))
    lines.extend(("*Material, name=DEMO_STEEL", "*Elastic", "210000., 0.3",
                  "*Solid Section, elset=GEAR_SOLID, material=DEMO_STEEL", ",", ""))
    data = "\n".join(lines).encode("ascii")
    output.write_bytes(data)
    report = {
        "source_deck": str(output.resolve()),
        "sha256": hashlib.sha256(data).hexdigest(),
        "nodes": len(coordinates),
        "hexahedra": element_count,
        "boundary_faces": boundary_faces,
        "minimum_gauss_jacobian_mm3": min_jacobian,
        "teeth": TEETH,
        "module_mm": MODULE_MM,
        "pressure_angle_deg": PRESSURE_ANGLE_DEG,
        "tip_diameter_mm": 2 * (MODULE_MM * TEETH / 2 + MODULE_MM),
        "root_diameter_mm": 2 * (MODULE_MM * TEETH / 2 - 1.25 * MODULE_MM),
        "bore_diameter_mm": 2 * BORE_RADIUS_MM,
        "thickness_mm": THICKNESS_MM,
        "scope": "FE mesh only; no boundary conditions, loads, solver run, or result",
    }
    output.with_suffix(".json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    print(json.dumps(generate(parser.parse_args().output), indent=2))
