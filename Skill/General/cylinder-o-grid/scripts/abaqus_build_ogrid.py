#!/usr/bin/env python
"""Build and quality-check a five-block cylinder O-grid in Abaqus/CAE.

Run a normal-Python parameter check with --dry-run. Run geometry and mesh
creation only with the Abaqus Python interpreter.
"""

from __future__ import print_function

import argparse
import json
import math
import os
import sys


def positive_int(value):
    value = int(value)
    if value <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return value


def parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--radius", type=float, required=True)
    parser.add_argument("--length", type=float, required=True)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--square-half-width", type=float)
    group.add_argument("--square-ratio", type=float)
    parser.add_argument("--circumferential", type=positive_int, default=48)
    parser.add_argument("--radial", type=positive_int, default=6)
    parser.add_argument("--axial", type=positive_int, default=12)
    parser.add_argument("--model-name", default="OGridCylinderModel")
    parser.add_argument("--part-name", default="OGridCylinder")
    parser.add_argument("--analysis", choices=("standard", "explicit"), default="standard")
    parser.add_argument("--element-code", choices=("C3D8R", "C3D8", "C3D8I"), default="C3D8R")
    parser.add_argument("--max-aspect-ratio", type=float, default=5.0)
    parser.add_argument("--cae-out", default="cylinder_ogrid.cae")
    parser.add_argument("--replace-model", action="store_true")
    parser.add_argument("--allow-quality-api-failure", action="store_true")
    return parser.parse_args(argv)


def make_plan(args):
    ratio = 0.40 if args.square_ratio is None and args.square_half_width is None else args.square_ratio
    half = args.square_half_width if args.square_half_width is not None else args.radius * ratio
    if args.radius <= 0.0 or args.length <= 0.0:
        raise ValueError("radius and length must be positive")
    if half <= 0.0 or half >= args.radius / math.sqrt(2.0):
        raise ValueError("require 0 < square half-width < R/sqrt(2)")
    if args.circumferential % 4:
        raise ValueError("circumferential divisions must be divisible by 4")
    if args.analysis == "explicit" and args.element_code == "C3D8I":
        raise ValueError("C3D8I is not permitted for this Explicit template")
    n_side = args.circumferential // 4
    n_quad = n_side * n_side + 4 * n_side * args.radial
    return {
        "radius": args.radius,
        "length": args.length,
        "square_half_width": half,
        "square_ratio": half / args.radius,
        "circumferential": args.circumferential,
        "side_divisions": n_side,
        "radial_divisions": args.radial,
        "axial_divisions": args.axial,
        "expected_cross_section_quads": n_quad,
        "expected_hexahedra": n_quad * args.axial,
        "analysis": args.analysis,
        "element_code": args.element_code,
        "max_aspect_ratio": args.max_aspect_ratio,
    }


def _normalize_edge(edge_or_array):
    if hasattr(edge_or_array, "index") and not callable(edge_or_array.index):
        return edge_or_array
    if len(edge_or_array) == 1:
        return edge_or_array[0]
    raise RuntimeError("edge lookup did not return exactly one edge")


def _edge_at(part, point):
    return _normalize_edge(part.edges.findAt(tuple(point)))


def _top_face(part):
    candidates = []
    for face in part.faces:
        normal = face.getNormal()
        if abs(normal[0]) < 1.0e-9 and abs(normal[1]) < 1.0e-9 and normal[2] > 0.999999:
            candidates.append(face)
    if len(candidates) != 1:
        raise RuntimeError("expected one planar +Z end face, found %d" % len(candidates))
    return candidates[0]


def _unique_edges(edges):
    found = {}
    for edge in edges:
        found[edge.index] = edge
    return tuple(found[index] for index in sorted(found))


def _edge_families(part, radius, half, length):
    z_faces = (0.0, length)
    square_points = []
    arc_points = []
    connector_points = []
    b = radius / math.sqrt(2.0)

    for z_value in z_faces:
        square_points.extend(((0.0, -half, z_value), (half, 0.0, z_value), (0.0, half, z_value), (-half, 0.0, z_value)))
        arc_points.extend(((0.0, -radius, z_value), (radius, 0.0, z_value), (0.0, radius, z_value), (-radius, 0.0, z_value)))
        for sx, sy in ((-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0)):
            connector_points.append((sx * (half + b) / 2.0, sy * (half + b) / 2.0, z_value))

    axial_points = []
    z_mid = length / 2.0
    for value in (half, b):
        axial_points.extend(((-value, -value, z_mid), (value, -value, z_mid), (value, value, z_mid), (-value, value, z_mid)))

    return {
        "side": _unique_edges([_edge_at(part, point) for point in square_points + arc_points]),
        "radial": _unique_edges([_edge_at(part, point) for point in connector_points]),
        "axial": _unique_edges([_edge_at(part, point) for point in axial_points]),
    }


def _failed_count(result):
    if isinstance(result, dict):
        return len(result.get("failedElements", ()))
    return 0


def build_in_abaqus(args, plan):
    from abaqus import mdb
    import abaqusConstants as ac
    import mesh

    if args.model_name in mdb.models:
        if not args.replace_model:
            raise RuntimeError("model already exists; choose another name or pass --replace-model explicitly")
        del mdb.models[args.model_name]

    model = mdb.Model(name=args.model_name)
    sheet_size = 4.0 * max(args.radius, args.length)
    b = args.radius / math.sqrt(2.0)
    base_sketch = model.ConstrainedSketch(name="__cylinder_profile__", sheetSize=sheet_size)
    # Place the circle seam at a connector endpoint so the perimeter has four
    # logical 90-degree arcs instead of an extra split edge at angle zero.
    base_sketch.CircleByCenterPerimeter(center=(0.0, 0.0), point1=(b, b))
    part = model.Part(name=args.part_name, dimensionality=ac.THREE_D, type=ac.DEFORMABLE_BODY)
    part.BaseSolidExtrude(sketch=base_sketch, depth=args.length)
    del model.sketches[base_sketch.name]

    half = plan["square_half_width"]
    top = _top_face(part)
    transform = part.MakeSketchTransform(
        sketchPlane=top,
        sketchPlaneSide=ac.SIDE1,
        origin=(0.0, 0.0, args.length),
    )
    partition_sketch = model.ConstrainedSketch(
        name="__coin_ogrid_partition__",
        sheetSize=sheet_size,
        transform=transform,
    )
    partition_sketch.rectangle(point1=(-half, -half), point2=(half, half))
    connector_pairs = [
        ((-half, -half), (-b, -b)),
        ((half, -half), (b, -b)),
        ((half, half), (b, b)),
        ((-half, half), (-b, b)),
    ]
    for point1, point2 in connector_pairs:
        partition_sketch.Line(point1=point1, point2=point2)
    part.PartitionFaceBySketch(faces=(top,), sketch=partition_sketch)
    del model.sketches[partition_sketch.name]

    axis_feature = part.DatumAxisByPrincipalAxis(principalAxis=ac.ZAXIS)
    axis = part.datums[axis_feature.id]
    square_top_points = [
        (0.0, -half, args.length),
        (half, 0.0, args.length),
        (0.0, half, args.length),
        (-half, 0.0, args.length),
    ]
    square_edges = tuple(_edge_at(part, point) for point in square_top_points)
    part.PartitionCellByExtrudeEdge(
        cells=part.cells[:],
        edges=square_edges,
        line=axis,
        sense=ac.REVERSE,
    )

    connector_top_points = []
    for point1, point2 in connector_pairs:
        connector_top_points.append(
            ((point1[0] + point2[0]) / 2.0, (point1[1] + point2[1]) / 2.0, args.length)
        )
    connector_edges = tuple(_edge_at(part, point) for point in connector_top_points)
    outer_cell = part.cells.findAt((0.0, (half + args.radius) / 2.0, args.length / 2.0))
    part.PartitionCellByExtrudeEdge(
        cells=(outer_cell,),
        edges=connector_edges,
        line=axis,
        sense=ac.REVERSE,
    )

    if len(part.cells) != 5:
        raise RuntimeError("expected five sweepable cells after extrusion, found %d; stop and repair the partition topology" % len(part.cells))

    families = _edge_families(part, args.radius, half, args.length)
    part.seedEdgeByNumber(edges=families["side"], number=plan["side_divisions"], constraint=ac.FIXED)
    part.seedEdgeByNumber(edges=families["radial"], number=args.radial, constraint=ac.FIXED)
    part.seedEdgeByNumber(edges=families["axial"], number=args.axial, constraint=ac.FIXED)
    part.setMeshControls(regions=part.cells, elemShape=ac.HEX, technique=ac.STRUCTURED)

    element_constant = getattr(ac, args.element_code)
    library = ac.STANDARD if args.analysis == "standard" else ac.EXPLICIT
    element_type = mesh.ElemType(elemCode=element_constant, elemLibrary=library)
    part.setElementType(regions=(part.cells,), elemTypes=(element_type,))
    part.generateMesh()

    actual_elements = len(part.elements)
    if actual_elements != plan["expected_hexahedra"]:
        raise RuntimeError("expected %d hexahedra, Abaqus generated %d; do not accept this mesh" % (plan["expected_hexahedra"], actual_elements))

    type_counts = {}
    for element in part.elements:
        element_name = str(getattr(element, "type", "UNKNOWN"))
        type_counts[element_name] = type_counts.get(element_name, 0) + 1
    unexpected = [name for name in type_counts if name not in (args.element_code, "UNKNOWN")]
    if unexpected:
        raise RuntimeError("unexpected element types: %s" % ", ".join(sorted(unexpected)))

    quality = {"status": "verified"}
    try:
        analysis_result = part.verifyMeshQuality(criterion=ac.ANALYSIS_CHECKS, elemShape=ac.HEX, regions=part.elements)
        aspect_result = part.verifyMeshQuality(criterion=ac.ASPECT_RATIO, threshold=args.max_aspect_ratio, elemShape=ac.HEX, regions=part.elements)
        quality["analysis_check_failures"] = _failed_count(analysis_result)
        quality["analysis_check_warnings"] = len(analysis_result.get("warningElements", ()))
        quality["aspect_ratio_failures"] = _failed_count(aspect_result)
        quality["aspect_ratio_average"] = float(aspect_result.get("average", 0.0))
        quality["aspect_ratio_worst"] = float(aspect_result.get("worst", 0.0))
        worst_element = aspect_result.get("worstElement")
        if hasattr(worst_element, "label"):
            quality["aspect_ratio_worst_element"] = worst_element.label
        elif worst_element:
            quality["aspect_ratio_worst_element"] = worst_element[0].label
        else:
            quality["aspect_ratio_worst_element"] = None
    except Exception as exc:
        quality = {"status": "unverified", "error": str(exc)}
        if not args.allow_quality_api_failure:
            raise RuntimeError("Abaqus mesh-quality API did not complete: %s" % exc)

    if quality.get("analysis_check_failures", 0) or quality.get("aspect_ratio_failures", 0):
        raise RuntimeError("mesh failed quality gates: %s" % json.dumps(quality, sort_keys=True))

    cae_path = os.path.abspath(args.cae_out)
    parent = os.path.dirname(cae_path)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    mdb.saveAs(pathName=cae_path)

    summary = dict(plan)
    summary.update({
        "model_name": args.model_name,
        "part_name": args.part_name,
        "cell_count": len(part.cells),
        "node_count": len(part.nodes),
        "element_count": actual_elements,
        "element_type_counts": type_counts,
        "quality": quality,
        "cae_path": cae_path,
    })
    return summary


def main():
    raw = sys.argv[1:]
    if "--" in raw:
        raw = raw[raw.index("--") + 1:]
    args = parse_args(raw)
    plan = make_plan(args)
    if args.dry_run:
        print(json.dumps(plan, indent=2, sort_keys=True))
        return
    summary = build_in_abaqus(args, plan)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
