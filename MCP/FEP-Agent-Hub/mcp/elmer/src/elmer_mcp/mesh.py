from __future__ import annotations

import math
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from open_cae_core.manifests import write_json


def gmsh_geo(
    step_path: Path,
    mesh_path: Path,
    global_size_mm: float,
    order: int = 1,
    coordinate_scale: float = 1.0,
) -> str:
    step = step_path.resolve().as_posix().replace('"', '\\"')
    mesh = mesh_path.resolve().as_posix().replace('"', '\\"')
    return f'''SetFactory("OpenCASCADE");
Merge "{step}";
Coherence;
Mesh.MeshSizeMin = {global_size_mm:.12g};
Mesh.MeshSizeMax = {global_size_mm:.12g};
Mesh.ElementOrder = {int(order)};
Mesh.MshFileVersion = 2.2;
Mesh.ScalingFactor = {coordinate_scale:.12g};
Mesh.SaveAll = 1;
Mesh 3;
Save "{mesh}";
'''


def _geo_name(value: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_]", "_", value)
    if not name or name[0].isdigit():
        name = f"region_{name}"
    return name


def gmsh_geo_2d(
    step_path: Path,
    mesh_path: Path,
    geometry_manifest: dict[str, Any],
    global_size_mm: float,
    order: int = 1,
    coordinate_scale: float = 0.001,
) -> tuple[str, dict[str, int], dict[str, int]]:
    """Build a conformal planar mesh from FreeCAD-validated rectangle fingerprints.

    The STEP remains a required, hashed handoff artifact.  The structured
    rectangle fingerprints avoid guessing OpenCASCADE entity order after STEP
    import and let Gmsh receive deterministic physical groups.
    """
    if not math.isclose(coordinate_scale, 0.001, rel_tol=0.0, abs_tol=1.0e-12):
        raise ValueError("The verified planar electromagnetic profile requires mm-to-m scale 0.001")
    objects = geometry_manifest.get("objects", [])
    by_semantic = {str(item.get("semantic_id")): item for item in objects}
    if "air" not in by_semantic:
        raise ValueError("Planar electromagnetic geometry requires semantic_id 'air'")
    required = {"core", "primary_pos", "primary_neg", "secondary_pos", "secondary_neg"}
    missing = sorted(required - set(by_semantic))
    if missing:
        raise ValueError(f"Planar electromagnetic geometry is missing regions: {missing}")

    body_order = ["air", "core", "primary_pos", "primary_neg", "secondary_pos", "secondary_neg"]
    body_ids = {name: index for index, name in enumerate(body_order, start=1)}
    boundary_ids = {"outer_boundary": 1001}
    lines = [
        'SetFactory("OpenCASCADE");',
        f'// Evidence STEP: {step_path.resolve().as_posix()}',
        f'Mesh.MeshSizeMin = {global_size_mm * coordinate_scale:.12g};',
        f'Mesh.MeshSizeMax = {global_size_mm * coordinate_scale:.12g};',
        f'Mesh.ElementOrder = {int(order)};',
        'Mesh.MshFileVersion = 2.2;',
        'Geometry.Tolerance = 1.0e-10;',
    ]

    region_arrays: dict[str, str] = {}
    for semantic in body_order[1:]:
        item = by_semantic[semantic]
        rectangles = item.get("source_rectangles_mm") or []
        if not rectangles:
            bbox = item.get("bbox_mm", [])
            if len(bbox) != 6:
                raise ValueError(f"Region {semantic} has no valid planar fingerprint")
            rectangles = [{"x_min": bbox[0], "x_max": bbox[1], "y_min": bbox[2], "y_max": bbox[3]}]
        tags = []
        safe = _geo_name(semantic)
        for index, rectangle in enumerate(rectangles, start=1):
            x0 = float(rectangle["x_min"]) * coordinate_scale
            x1 = float(rectangle["x_max"]) * coordinate_scale
            y0 = float(rectangle["y_min"]) * coordinate_scale
            y1 = float(rectangle["y_max"]) * coordinate_scale
            if x1 <= x0 or y1 <= y0:
                raise ValueError(f"Region {semantic} contains a non-positive rectangle")
            tag = f"{safe}_part_{index}"
            lines.append(f"{tag} = news; Rectangle({tag}) = {{{x0:.12g}, {y0:.12g}, 0, {x1-x0:.12g}, {y1-y0:.12g}}};")
            tags.append(tag)
        array_name = f"{safe}_surfaces"
        if len(tags) == 1:
            lines.append(f"{array_name}[] = {{{tags[0]}}};")
        else:
            tools = ", ".join(tags[1:])
            lines.append(
                f"{array_name}[] = BooleanUnion{{ Surface{{{tags[0]}}}; Delete; }}"
                f"{{ Surface{{{tools}}}; Delete; }};"
            )
        region_arrays[semantic] = array_name

    air_bbox = by_semantic["air"].get("bbox_mm", [])
    if len(air_bbox) != 6:
        raise ValueError("Air region has no valid bounding box")
    ax0, ax1, ay0, ay1 = [float(value) for value in (air_bbox[0], air_bbox[1], air_bbox[2], air_bbox[3])]
    ax0 *= coordinate_scale
    ax1 *= coordinate_scale
    ay0 *= coordinate_scale
    ay1 *= coordinate_scale
    lines.append(f"air_outer = news; Rectangle(air_outer) = {{{ax0:.12g}, {ay0:.12g}, 0, {ax1-ax0:.12g}, {ay1-ay0:.12g}}};")
    tools = ", ".join(f"{region_arrays[name]}[]" for name in body_order[1:])
    lines.append(f"air_surfaces[] = BooleanDifference{{ Surface{{air_outer}}; Delete; }}{{ Surface{{{tools}}}; }};")
    region_arrays["air"] = "air_surfaces"

    for semantic in body_order:
        lines.append(
            f'Physical Surface("{semantic}", {body_ids[semantic]}) = {{{region_arrays[semantic]}[]}};'
        )
    # OpenCASCADE curve bounding boxes include modelling tolerance.  A one
    # micrometre-scale query pad is still tiny compared with the 1 mm mesh but
    # reliably captures the four far-field edges.
    eps = max(max((ax1 - ax0), (ay1 - ay0)) * 1.0e-5, 1.0e-6)
    lines.extend(
        [
            f"outer_left[] = Curve In BoundingBox {{{ax0-eps:.12g}, {ay0-eps:.12g}, {-eps:.12g}, {ax0+eps:.12g}, {ay1+eps:.12g}, {eps:.12g}}};",
            f"outer_right[] = Curve In BoundingBox {{{ax1-eps:.12g}, {ay0-eps:.12g}, {-eps:.12g}, {ax1+eps:.12g}, {ay1+eps:.12g}, {eps:.12g}}};",
            f"outer_bottom[] = Curve In BoundingBox {{{ax0-eps:.12g}, {ay0-eps:.12g}, {-eps:.12g}, {ax1+eps:.12g}, {ay0+eps:.12g}, {eps:.12g}}};",
            f"outer_top[] = Curve In BoundingBox {{{ax0-eps:.12g}, {ay1-eps:.12g}, {-eps:.12g}, {ax1+eps:.12g}, {ay1+eps:.12g}, {eps:.12g}}};",
            'Physical Curve("outer_boundary", 1001) = {outer_left[], outer_right[], outer_bottom[], outer_top[]};',
        ]
    )
    return "\n".join(lines) + "\n", body_ids, boundary_ids


def gmsh_geo_eddy_2d(
    step_path: Path,
    mesh_path: Path,
    geometry_manifest: dict[str, Any],
    global_size_mm: float,
    order: int = 1,
    coordinate_scale: float = 0.001,
) -> tuple[str, dict[str, int], dict[str, int]]:
    """Build a conformal four-region planar transient-eddy-current mesh."""
    if not math.isclose(coordinate_scale, 0.001, rel_tol=0.0, abs_tol=1.0e-12):
        raise ValueError("The verified transient eddy-current profile requires mm-to-m scale 0.001")
    objects = geometry_manifest.get("objects", [])
    by_semantic = {str(item.get("semantic_id")): item for item in objects}
    body_order = ["air", "conductor", "coil_pos", "coil_neg"]
    missing = [semantic for semantic in body_order if semantic not in by_semantic]
    if missing:
        raise ValueError(f"Transient eddy-current geometry is missing regions: {missing}")
    body_ids = {name: index for index, name in enumerate(body_order, start=1)}
    boundary_ids = {"outer_boundary": 1001}
    lines = [
        'SetFactory("OpenCASCADE");',
        f'// Evidence STEP: {step_path.resolve().as_posix()}',
        f'Mesh.MeshSizeMin = {global_size_mm * coordinate_scale:.12g};',
        f'Mesh.MeshSizeMax = {global_size_mm * coordinate_scale:.12g};',
        f'Mesh.ElementOrder = {int(order)};',
        'Mesh.MshFileVersion = 2.2;',
        'Geometry.Tolerance = 1.0e-10;',
    ]
    region_arrays: dict[str, str] = {}
    for semantic in body_order[1:]:
        bbox = by_semantic[semantic].get("bbox_mm", [])
        if len(bbox) != 6:
            raise ValueError(f"Region {semantic} has no valid bounding box")
        x0, x1, y0, y1 = [float(value) * coordinate_scale for value in (bbox[0], bbox[1], bbox[2], bbox[3])]
        if x1 <= x0 or y1 <= y0:
            raise ValueError(f"Region {semantic} has non-positive dimensions")
        tag = _geo_name(semantic)
        lines.append(f'{tag} = news; Rectangle({tag}) = {{{x0:.12g}, {y0:.12g}, 0, {x1-x0:.12g}, {y1-y0:.12g}}};')
        lines.append(f'{tag}_surfaces[] = {{{tag}}};')
        region_arrays[semantic] = f"{tag}_surfaces"
    air_bbox = by_semantic["air"].get("bbox_mm", [])
    if len(air_bbox) != 6:
        raise ValueError("Air region has no valid bounding box")
    ax0, ax1, ay0, ay1 = [float(value) * coordinate_scale for value in (air_bbox[0], air_bbox[1], air_bbox[2], air_bbox[3])]
    lines.append(f'air_outer = news; Rectangle(air_outer) = {{{ax0:.12g}, {ay0:.12g}, 0, {ax1-ax0:.12g}, {ay1-ay0:.12g}}};')
    tools = ", ".join(f"{region_arrays[name]}[]" for name in body_order[1:])
    lines.append(f'air_surfaces[] = BooleanDifference{{ Surface{{air_outer}}; Delete; }}{{ Surface{{{tools}}}; }};')
    region_arrays["air"] = "air_surfaces"
    for semantic in body_order:
        lines.append(f'Physical Surface("{semantic}", {body_ids[semantic]}) = {{{region_arrays[semantic]}[]}};')
    eps = max(max(ax1 - ax0, ay1 - ay0) * 1.0e-5, 1.0e-6)
    lines.extend(
        [
            f'outer_left[] = Curve In BoundingBox {{{ax0-eps:.12g}, {ay0-eps:.12g}, {-eps:.12g}, {ax0+eps:.12g}, {ay1+eps:.12g}, {eps:.12g}}};',
            f'outer_right[] = Curve In BoundingBox {{{ax1-eps:.12g}, {ay0-eps:.12g}, {-eps:.12g}, {ax1+eps:.12g}, {ay1+eps:.12g}, {eps:.12g}}};',
            f'outer_bottom[] = Curve In BoundingBox {{{ax0-eps:.12g}, {ay0-eps:.12g}, {-eps:.12g}, {ax1+eps:.12g}, {ay0+eps:.12g}, {eps:.12g}}};',
            f'outer_top[] = Curve In BoundingBox {{{ax0-eps:.12g}, {ay1-eps:.12g}, {-eps:.12g}, {ax1+eps:.12g}, {ay1+eps:.12g}, {eps:.12g}}};',
            'Physical Curve("outer_boundary", 1001) = {outer_left[], outer_right[], outer_bottom[], outer_top[]};',
        ]
    )
    return "\n".join(lines) + "\n", body_ids, boundary_ids


def gmsh_geo_beam_2d(
    step_path: Path,
    mesh_path: Path,
    geometry_manifest: dict[str, Any],
    global_size_mm: float,
    order: int = 1,
    coordinate_scale: float = 0.001,
) -> tuple[str, dict[str, int], dict[str, int]]:
    """Build an SI-unit rectangle mesh with short support patches and a loaded top edge."""
    if not math.isclose(coordinate_scale, 0.001, rel_tol=0.0, abs_tol=1.0e-12):
        raise ValueError("The verified planar elasticity profile requires mm-to-m scale 0.001")
    objects = geometry_manifest.get("objects", [])
    beam = next((item for item in objects if str(item.get("semantic_id")) == "beam"), None)
    if not beam:
        raise ValueError("Planar elasticity geometry requires semantic_id 'beam'")
    bbox = beam.get("bbox_mm", [])
    if len(bbox) != 6:
        raise ValueError("Beam region has no valid bounding box")
    x0, x1, y0, y1 = [float(value) * coordinate_scale for value in (bbox[0], bbox[1], bbox[2], bbox[3])]
    if x1 <= x0 or y1 <= y0:
        raise ValueError("Beam rectangle must have positive length and height")
    body_ids = {"beam": 1}
    boundary_ids = {
        "left_pin": 1001,
        "right_roller": 1002,
        "top_load": 1003,
        "bottom_free": 1004,
        "left_end": 1005,
        "right_end": 1006,
    }
    support_width = min(global_size_mm * coordinate_scale, 0.02 * (x1 - x0), 0.25 * (x1 - x0))
    if support_width <= 0 or 2.0 * support_width >= x1 - x0:
        raise ValueError("Beam support patch width is invalid")
    lines = [
        'SetFactory("Built-in");',
        f'// Evidence STEP: {step_path.resolve().as_posix()}',
        f'Point(1) = {{{x0:.12g}, {y0:.12g}, 0}};',
        f'Point(2) = {{{x0+support_width:.12g}, {y0:.12g}, 0}};',
        f'Point(3) = {{{x1-support_width:.12g}, {y0:.12g}, 0}};',
        f'Point(4) = {{{x1:.12g}, {y0:.12g}, 0}};',
        f'Point(5) = {{{x1:.12g}, {y1:.12g}, 0}};',
        f'Point(6) = {{{x0:.12g}, {y1:.12g}, 0}};',
        'Line(1) = {1, 2};',
        'Line(2) = {2, 3};',
        'Line(3) = {3, 4};',
        'Line(4) = {4, 5};',
        'Line(5) = {5, 6};',
        'Line(6) = {6, 1};',
        'Curve Loop(1) = {1, 2, 3, 4, 5, 6};',
        'Plane Surface(1) = {1};',
        f'Mesh.MeshSizeMin = {global_size_mm * coordinate_scale:.12g};',
        f'Mesh.MeshSizeMax = {global_size_mm * coordinate_scale:.12g};',
        f'Mesh.ElementOrder = {int(order)};',
        'Mesh.MshFileVersion = 2.2;',
        'Physical Surface("beam", 1) = {1};',
        'Physical Curve("left_pin", 1001) = {1};',
        'Physical Curve("right_roller", 1002) = {3};',
        'Physical Curve("top_load", 1003) = {5};',
        'Physical Curve("bottom_free", 1004) = {2};',
        'Physical Curve("left_end", 1005) = {6};',
        'Physical Curve("right_end", 1006) = {4};',
    ]
    return "\n".join(lines) + "\n", body_ids, boundary_ids


def gmsh_geo_channel_2d(
    step_path: Path,
    mesh_path: Path,
    geometry_manifest: dict[str, Any],
    global_size_mm: float,
    order: int = 1,
    coordinate_scale: float = 0.001,
) -> tuple[str, dict[str, int], dict[str, int]]:
    """Build an SI-unit rectangular channel with deterministic CFD boundaries."""
    if not math.isclose(coordinate_scale, 0.001, rel_tol=0.0, abs_tol=1.0e-12):
        raise ValueError("The verified planar flow profile requires mm-to-m scale 0.001")
    objects = geometry_manifest.get("objects", [])
    fluid = next((item for item in objects if str(item.get("semantic_id")) == "fluid"), None)
    if not fluid:
        raise ValueError("Planar flow geometry requires semantic_id 'fluid'")
    bbox = fluid.get("bbox_mm", [])
    if len(bbox) != 6:
        raise ValueError("Fluid region has no valid bounding box")
    x0, x1, y0, y1 = [float(value) * coordinate_scale for value in (bbox[0], bbox[1], bbox[2], bbox[3])]
    if x1 <= x0 or y1 <= y0:
        raise ValueError("Channel rectangle must have positive length and height")
    body_ids = {"fluid": 1}
    boundary_ids = {"inlet": 1001, "outlet": 1002, "walls": 1003}
    lines = [
        'SetFactory("Built-in");',
        f'// Evidence STEP: {step_path.resolve().as_posix()}',
        f'Point(1) = {{{x0:.12g}, {y0:.12g}, 0}};',
        f'Point(2) = {{{x1:.12g}, {y0:.12g}, 0}};',
        f'Point(3) = {{{x1:.12g}, {y1:.12g}, 0}};',
        f'Point(4) = {{{x0:.12g}, {y1:.12g}, 0}};',
        'Line(1) = {1, 2};',
        'Line(2) = {2, 3};',
        'Line(3) = {3, 4};',
        'Line(4) = {4, 1};',
        'Curve Loop(1) = {1, 2, 3, 4};',
        'Plane Surface(1) = {1};',
        f'Mesh.MeshSizeMin = {global_size_mm * coordinate_scale:.12g};',
        f'Mesh.MeshSizeMax = {global_size_mm * coordinate_scale:.12g};',
        f'Mesh.ElementOrder = {int(order)};',
        'Mesh.MshFileVersion = 2.2;',
        'Physical Surface("fluid", 1) = {1};',
        'Physical Curve("inlet", 1001) = {4};',
        'Physical Curve("outlet", 1002) = {2};',
        'Physical Curve("walls", 1003) = {1, 3};',
    ]
    return "\n".join(lines) + "\n", body_ids, boundary_ids


def parse_elmer_mesh(mesh_dir: str | Path) -> dict[str, Any]:
    root = Path(mesh_dir)
    header = root / "mesh.header"
    nodes_file = root / "mesh.nodes"
    elements_file = root / "mesh.elements"
    boundary_file = root / "mesh.boundary"
    names_file = root / "mesh.names"
    required = [header, nodes_file, elements_file, boundary_file]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Incomplete Elmer mesh: {missing}")

    header_lines = [line.strip() for line in header.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()]
    counts = [int(value) for value in header_lines[0].split()[:3]]
    nodes: dict[int, tuple[float, float, float]] = {}
    for line in nodes_file.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split()
        if len(parts) >= 5:
            nodes[int(parts[0])] = (float(parts[-3]), float(parts[-2]), float(parts[-1]))
    body_ids: set[int] = set()
    element_types: set[int] = set()
    element_count = 0
    for line in elements_file.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split()
        if len(parts) >= 4:
            body_ids.add(int(parts[1]))
            element_types.add(int(parts[2]))
            element_count += 1

    boundary_nodes: dict[int, set[int]] = defaultdict(set)
    boundary_element_counts: dict[int, int] = defaultdict(int)
    for line in boundary_file.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split()
        if len(parts) < 6:
            continue
        boundary_id = int(parts[1])
        boundary_element_counts[boundary_id] += 1
        for value in parts[5:]:
            node_id = int(value)
            if node_id in nodes:
                boundary_nodes[boundary_id].add(node_id)

    coordinates = list(nodes.values())
    bounds = [
        min(point[0] for point in coordinates),
        max(point[0] for point in coordinates),
        min(point[1] for point in coordinates),
        max(point[1] for point in coordinates),
        min(point[2] for point in coordinates),
        max(point[2] for point in coordinates),
    ]
    span = max(bounds[1] - bounds[0], bounds[3] - bounds[2], bounds[5] - bounds[4], 1.0)
    tolerance = max(span * 1e-7, 1e-9)
    dimension = 2 if math.isclose(bounds[4], bounds[5], abs_tol=1.0e-12) and all(value < 500 for value in element_types) else 3
    semantics: dict[str, list[int]] = {"x_min": [], "x_max": [], "y_min": [], "y_max": []}
    if dimension == 3:
        semantics.update({"z_min": [], "z_max": []})
    boundary_records = []
    axes = [(0, "x_min", "x_max", bounds[0], bounds[1]), (1, "y_min", "y_max", bounds[2], bounds[3])]
    if dimension == 3:
        axes.append((2, "z_min", "z_max", bounds[4], bounds[5]))
    for boundary_id, node_ids in sorted(boundary_nodes.items()):
        points = [nodes[node_id] for node_id in node_ids]
        record = {
            "id": boundary_id,
            "elements": boundary_element_counts[boundary_id],
            "nodes": len(node_ids),
            "bbox": [
                min(point[0] for point in points), max(point[0] for point in points),
                min(point[1] for point in points), max(point[1] for point in points),
                min(point[2] for point in points), max(point[2] for point in points),
            ],
        }
        for axis, low_name, high_name, low, high in axes:
            values = [point[axis] for point in points]
            if values and all(math.isclose(value, low, abs_tol=tolerance) for value in values):
                semantics[low_name].append(boundary_id)
            if values and all(math.isclose(value, high, abs_tol=tolerance) for value in values):
                semantics[high_name].append(boundary_id)
        if dimension == 2 and points and all(
            math.isclose(point[0], bounds[0], abs_tol=tolerance)
            or math.isclose(point[0], bounds[1], abs_tol=tolerance)
            or math.isclose(point[1], bounds[2], abs_tol=tolerance)
            or math.isclose(point[1], bounds[3], abs_tol=tolerance)
            for point in points
        ):
            semantics.setdefault("outer_boundary", []).append(boundary_id)
        boundary_records.append(record)
    if dimension == 2:
        semantics["outer_boundary"] = sorted(
            set(
                semantics.get("outer_boundary", [])
                + semantics["x_min"]
                + semantics["x_max"]
                + semantics["y_min"]
                + semantics["y_max"]
            )
        )
    named_bodies: dict[str, int] = {}
    named_boundaries: dict[str, int] = {}
    if names_file.is_file():
        section = None
        for line in names_file.read_text(encoding="utf-8", errors="replace").splitlines():
            lowered = line.lower()
            if "names for bodies" in lowered:
                section = "bodies"
                continue
            if "names for boundaries" in lowered:
                section = "boundaries"
                continue
            match = re.match(r"\s*\$\s+([A-Za-z0-9_]+)\s*=\s*(\d+)\s*$", line)
            if not match:
                continue
            name, value = match.group(1), int(match.group(2))
            if section == "bodies":
                named_bodies[name] = value
            elif section == "boundaries":
                named_boundaries[name] = value
    return {
        "dimension": dimension,
        "nodes": len(nodes),
        "elements": element_count,
        "boundary_elements": sum(boundary_element_counts.values()),
        "header_counts": {"nodes": counts[0], "elements": counts[1], "boundary_elements": counts[2]},
        "bodies": sorted(body_ids),
        "element_types": sorted(element_types),
        "boundaries": boundary_records,
        "bounds": bounds,
        "semantic_boundaries": semantics,
        "named_bodies": named_bodies,
        "named_boundaries": named_boundaries,
        "quality": {"checked": False, "reason": "v0.1 records topology; Jacobian quality is delegated to Gmsh logs"},
    }


def write_semantic_map(
    path: Path,
    mesh_summary: dict[str, Any],
    geometry_manifest: dict[str, Any],
    expected_body_ids: dict[str, int] | None = None,
    expected_boundary_ids: dict[str, int] | None = None,
) -> Path:
    objects = geometry_manifest.get("objects", [])
    bodies = mesh_summary.get("bodies", [])
    ambiguous = len(objects) != len(bodies)
    body_map = {}
    if expected_body_ids:
        named_bodies = mesh_summary.get("named_bodies", {})
        resolved_body_ids = {
            semantic: int(named_bodies.get(semantic, body_id))
            for semantic, body_id in expected_body_ids.items()
        }
        missing_ids = sorted(set(resolved_body_ids.values()) - set(bodies))
        ambiguous = bool(missing_ids)
        if not ambiguous:
            body_map = resolved_body_ids
    elif not ambiguous:
        body_map = {
            obj.get("semantic_id", f"body_{body}"): body
            for obj, body in zip(objects, bodies, strict=True)
        }
    boundary_map = mesh_summary.get("semantic_boundaries", {})
    if expected_boundary_ids:
        actual_boundary_ids = {item["id"] for item in mesh_summary.get("boundaries", [])}
        named_boundaries = mesh_summary.get("named_boundaries", {})
        for semantic, boundary_id in expected_boundary_ids.items():
            resolved_id = int(named_boundaries.get(semantic, boundary_id))
            if resolved_id in actual_boundary_ids:
                boundary_map[semantic] = [resolved_id]
    payload = {
        "schema_version": "1.0",
        "status": "SEMANTIC_MAPPING_AMBIGUOUS" if ambiguous else "MAPPED",
        "body_ids": body_map,
        "boundary_ids": boundary_map,
        "method": "verified Gmsh physical groups + Elmer mesh coordinate fingerprint" if expected_body_ids else "manifest cardinality + Elmer mesh coordinate fingerprint",
        "bounds": mesh_summary.get("bounds"),
        "dimension": mesh_summary.get("dimension"),
    }
    return write_json(path, payload)
