#!/usr/bin/env python3
"""Validate a coin-style cylinder O-grid plan and write JSON/SVG evidence."""

import argparse
import io
import json
import math
import os


def positive_int(value):
    value = int(value)
    if value <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return value


def make_plan(radius, length, square_half_width, circumferential, radial, axial):
    if radius <= 0.0 or length <= 0.0:
        raise ValueError("radius and length must be positive")
    if square_half_width <= 0.0:
        raise ValueError("square half-width must be positive")
    if square_half_width >= radius / math.sqrt(2.0):
        raise ValueError("square corners must remain inside the circle: a < R/sqrt(2)")
    if circumferential % 4:
        raise ValueError("circumferential divisions must be divisible by 4")

    n_side = circumferential // 4
    d_corner = radius - math.sqrt(2.0) * square_half_width
    d_side = radius - square_half_width
    sizes = {
        "square": 2.0 * square_half_width / n_side,
        "outer_arc": 0.5 * math.pi * radius / n_side,
        "corner_radial": d_corner / radial,
        "side_radial": d_side / radial,
        "axial": length / axial,
    }
    size_values = list(sizes.values())
    size_ratio = max(size_values) / min(size_values)
    n_quad = n_side * n_side + 4 * n_side * radial
    n_hex = n_quad * axial

    warnings = []
    ratio = square_half_width / radius
    if ratio < 0.30 or ratio > 0.45:
        warnings.append("a/R is outside the 0.30-0.45 starting search range; inspect corner cells closely")
    if size_ratio > 2.0:
        warnings.append("estimated largest-to-smallest characteristic size exceeds 2.0; rebalance counts or square size")

    return {
        "topology": "coin-style five-block O-grid",
        "radius": radius,
        "length": length,
        "square_half_width": square_half_width,
        "square_ratio": ratio,
        "corner_ligament": d_corner,
        "side_ligament": d_side,
        "circumferential_divisions": circumferential,
        "side_divisions": n_side,
        "radial_divisions": radial,
        "axial_divisions": axial,
        "expected_cross_section_quads": n_quad,
        "expected_hexahedra": n_hex,
        "characteristic_sizes": sizes,
        "estimated_size_ratio": size_ratio,
        "warnings": warnings,
    }


def _mapped_point(cx, cy, radius, half, sector, u, v):
    if sector == 0:
        sx, sy, angle = cx - half + 2 * half * u, cy - half, -135 + 90 * u
    elif sector == 1:
        sx, sy, angle = cx + half, cy - half + 2 * half * u, -45 + 90 * u
    elif sector == 2:
        sx, sy, angle = cx + half - 2 * half * u, cy + half, 45 + 90 * u
    else:
        sx, sy, angle = cx - half, cy + half - 2 * half * u, 135 + 90 * u
    angle = math.radians(angle)
    ox, oy = cx + radius * math.cos(angle), cy + radius * math.sin(angle)
    eased = v * (1.05 - 0.05 * v)
    return sx * (1.0 - eased) + ox * eased, sy * (1.0 - eased) + oy * eased


def _path(points):
    return " ".join(("M" if i == 0 else "L") + " %.2f %.2f" % point for i, point in enumerate(points))


def write_svg(plan, path):
    width, height = 900, 760
    cx, cy, draw_radius = 385.0, 390.0, 300.0
    half = draw_radius * plan["square_ratio"]
    n_side = plan["side_divisions"]
    n_radial = plan["radial_divisions"]
    mesh_paths = []

    for sector in range(4):
        for j in range(1, n_radial):
            points = [_mapped_point(cx, cy, draw_radius, half, sector, i / 48.0, j / float(n_radial)) for i in range(49)]
            mesh_paths.append('<path class="mesh" d="%s"/>' % _path(points))
        for i in range(1, n_side):
            points = [_mapped_point(cx, cy, draw_radius, half, sector, i / float(n_side), j / 30.0) for j in range(31)]
            mesh_paths.append('<path class="mesh" d="%s"/>' % _path(points))

    center_lines = []
    for i in range(1, n_side):
        offset = -half + 2.0 * half * i / float(n_side)
        center_lines.append('<line class="center" x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f"/>' % (cx + offset, cy - half, cx + offset, cy + half))
        center_lines.append('<line class="center" x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f"/>' % (cx - half, cy + offset, cx + half, cy + offset))

    partitions = []
    for sx, sy, angle in [(-half, -half, -135), (half, -half, -45), (half, half, 45), (-half, half, 135)]:
        theta = math.radians(angle)
        ex, ey = cx + draw_radius * math.cos(theta), cy + draw_radius * math.sin(theta)
        partitions.append('<line class="partition" x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f"/>' % (cx + sx, cy + sy, ex, ey))

    svg = """<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">
<rect width="100%%" height="100%%" fill="#ffffff"/>
<style>.mesh{fill:none;stroke:#aeb8c5;stroke-width:1}.center{stroke:#8090a0;stroke-width:1}.square{fill:#eaf5ff;stroke:#1476c8;stroke-width:4}.partition{stroke:#e05c26;stroke-width:4}.boundary{fill:none;stroke:#17212b;stroke-width:5}.title{font:700 28px sans-serif;fill:#17212b}.label{font:20px sans-serif;fill:#344250}</style>
<text class="title" x="55" y="48">Coin-style cylinder O-grid plan</text>
%s
%s
<rect class="square" x="%.2f" y="%.2f" width="%.2f" height="%.2f"/>
%s
<circle class="boundary" cx="%.2f" cy="%.2f" r="%.2f"/>
<text class="label" x="700" y="320">center square</text>
<text class="label" x="700" y="360">4 partition lines</text>
<text class="label" x="700" y="400">4 mapped sectors</text>
<text class="label" x="700" y="465">n_circ = %d</text>
<text class="label" x="700" y="500">n_radial = %d</text>
<text class="label" x="700" y="535">n_axial = %d</text>
<text class="label" x="700" y="590">N_hex = %d</text>
</svg>""" % (width, height, width, height, "\n".join(mesh_paths), "\n".join(center_lines), cx - half, cy - half, 2 * half, 2 * half, "\n".join(partitions), cx, cy, draw_radius, plan["circumferential_divisions"], plan["radial_divisions"], plan["axial_divisions"], plan["expected_hexahedra"])

    with io.open(path, "w", encoding="utf-8") as handle:
        handle.write(svg)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--radius", type=float, required=True)
    parser.add_argument("--length", type=float, required=True)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--square-half-width", type=float)
    group.add_argument("--square-ratio", type=float)
    parser.add_argument("--circumferential", type=positive_int, default=48)
    parser.add_argument("--radial", type=positive_int, default=6)
    parser.add_argument("--axial", type=positive_int, default=12)
    parser.add_argument("--output-dir", default="ogrid-plan")
    parser.add_argument("--no-svg", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    ratio = 0.40 if args.square_ratio is None and args.square_half_width is None else args.square_ratio
    half = args.square_half_width if args.square_half_width is not None else args.radius * ratio
    plan = make_plan(args.radius, args.length, half, args.circumferential, args.radial, args.axial)
    output_dir = os.path.abspath(args.output_dir)
    if not os.path.isdir(output_dir):
        os.makedirs(output_dir)
    json_path = os.path.join(output_dir, "ogrid_plan.json")
    with io.open(json_path, "w", encoding="utf-8") as handle:
        json.dump(plan, handle, indent=2, sort_keys=True)
        handle.write("\n")
    if not args.no_svg:
        write_svg(plan, os.path.join(output_dir, "ogrid_preview.svg"))
    print(json.dumps(plan, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
