"""Fixed FreeCAD-side runner.

This file is executed only by FreeCADCmd. It accepts no code snippets. The MCP
process passes a JSON job through OPEN_CAE_JOB and receives a JSON result at
OPEN_CAE_RESULT.
"""

from __future__ import annotations

import json
import os
import re
import traceback

import FreeCAD as App
import Part


def number(value):
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", str(value))
    if not match:
        raise ValueError("Expected a numeric quantity, got %r" % value)
    return float(match.group(0))


def vector(values):
    if not isinstance(values, list) or len(values) != 3:
        raise ValueError("Expected a three-component vector")
    return App.Vector(*[number(value) for value in values])


def close_document(doc):
    if doc:
        App.closeDocument(doc.Name)


def open_document(path):
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    return App.openDocument(path)


def placement_from(payload):
    placement = payload or {}
    position = vector(placement.get("position_mm", [0, 0, 0]))
    axis = vector(placement.get("rotation_axis", [0, 0, 1]))
    angle = number(placement.get("rotation_deg", 0))
    return App.Placement(position, App.Rotation(axis, angle))


def bbox(shape):
    box = shape.BoundBox
    return [box.XMin, box.XMax, box.YMin, box.YMax, box.ZMin, box.ZMax]


def shape_record(obj):
    record = {
        "name": obj.Name,
        "label": obj.Label,
        "type_id": obj.TypeId,
        "visibility": bool(getattr(obj.ViewObject, "Visibility", False))
        if hasattr(obj, "ViewObject")
        else False,
        "children": [child.Name for child in getattr(obj, "Group", [])],
    }
    if hasattr(obj, "Shape"):
        shape = obj.Shape
        record.update(
            {
                "shape_null": shape.isNull(),
                "valid": False if shape.isNull() else bool(shape.isValid()),
                "bbox_mm": [] if shape.isNull() else bbox(shape),
                "volume_mm3": 0.0 if shape.isNull() else float(shape.Volume),
                "area_mm2": 0.0 if shape.isNull() else float(shape.Area),
                "solids": len(shape.Solids),
                "shells": len(shape.Shells),
                "faces": len(shape.Faces),
                "edges": len(shape.Edges),
            }
        )
    return record


def save(doc, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    doc.recompute()
    doc.saveAs(path)


def create_feature(doc, payload):
    feature_type = payload["feature_type"].lower()
    name = payload["name"]
    parameters = payload.get("parameters", {})
    if feature_type == "rectangle_face":
        width = number(parameters.get("width"))
        height = number(parameters.get("height"))
        if width <= 0 or height <= 0:
            raise ValueError("rectangle_face width and height must be positive")
        obj = doc.addObject("Part::Feature", name)
        obj.Label = payload.get("label", name)
        obj.Shape = Part.makePlane(width, height)
        obj.addProperty("App::PropertyString", "OpenCAEFeatureType", "OpenCAE")
        obj.OpenCAEFeatureType = "rectangle_face"
        obj.addProperty("App::PropertyString", "OpenCAEParameters", "OpenCAE")
        obj.OpenCAEParameters = json.dumps(
            {"width": width, "height": height}, ensure_ascii=True, sort_keys=True
        )
        obj.Placement = placement_from(payload.get("placement"))
        doc.recompute()
        return shape_record(obj)

    constructors = {
        "box": ("Part::Box", {"Length": "length", "Width": "width", "Height": "height"}),
        "cylinder": ("Part::Cylinder", {"Radius": "radius", "Height": "height", "Angle": "angle"}),
        "sphere": ("Part::Sphere", {"Radius": "radius", "Angle1": "angle1", "Angle2": "angle2", "Angle3": "angle3"}),
        "cone": ("Part::Cone", {"Radius1": "radius1", "Radius2": "radius2", "Height": "height", "Angle": "angle"}),
    }
    if feature_type not in constructors:
        raise ValueError("Unsupported feature type: %s" % feature_type)
    type_id, mapping = constructors[feature_type]
    obj = doc.addObject(type_id, name)
    obj.Label = payload.get("label", name)
    for property_name, input_name in mapping.items():
        if input_name in parameters:
            setattr(obj, property_name, number(parameters[input_name]))
    obj.Placement = placement_from(payload.get("placement"))
    doc.recompute()
    return shape_record(obj)


def update_feature(doc, payload):
    obj = doc.getObject(payload["name"])
    if obj is None:
        raise KeyError(payload["name"])
    allowed = {
        "length": "Length",
        "width": "Width",
        "height": "Height",
        "radius": "Radius",
        "radius1": "Radius1",
        "radius2": "Radius2",
        "angle": "Angle",
        "label": "Label",
    }
    for key, value in payload.get("patch", {}).items():
        if key.lower() not in allowed:
            raise ValueError("Property is not editable: %s" % key)
        property_name = allowed[key.lower()]
        setattr(obj, property_name, value if property_name == "Label" else number(value))
    if "placement" in payload:
        obj.Placement = placement_from(payload["placement"])
    doc.recompute()
    return shape_record(obj)


def boolean_feature(doc, payload):
    operation = payload["operation"].lower()
    base = doc.getObject(payload["base"])
    tools = [doc.getObject(name) for name in payload.get("tools", [])]
    if base is None or not tools or any(tool is None for tool in tools):
        raise ValueError("Boolean inputs do not exist")
    result_name = payload.get("result", operation.title())
    current = base
    for index, tool in enumerate(tools):
        final_name = result_name if index == len(tools) - 1 else "%s_stage_%d" % (result_name, index)
        type_id = {"cut": "Part::Cut", "fuse": "Part::Fuse", "common": "Part::Common"}.get(operation)
        if not type_id:
            raise ValueError("Unsupported boolean: %s" % operation)
        result = doc.addObject(type_id, final_name)
        result.Base = current
        result.Tool = tool
        current = result
    doc.recompute()
    return shape_record(current)


def validate(doc, names=None):
    selected = [doc.getObject(name) for name in names] if names else list(doc.Objects)
    records = [shape_record(obj) for obj in selected if obj is not None and hasattr(obj, "Shape")]
    failures = []
    for record in records:
        dimensional_measure = (
            record.get("volume_mm3", 0)
            if record.get("solids", 0)
            else record.get("area_mm2", 0)
        )
        if record.get("shape_null") or not record.get("valid") or dimensional_measure <= 0:
            failures.append(record["name"])
    return {"valid": not failures and bool(records), "failures": failures, "objects": records}


def rectangle_sources(obj, seen=None):
    """Return fixed rectangle leaves used to build a planar Boolean result."""
    seen = seen or set()
    if obj is None or obj.Name in seen:
        return []
    seen.add(obj.Name)
    if getattr(obj, "OpenCAEFeatureType", "") == "rectangle_face" and hasattr(obj, "Shape"):
        box = bbox(obj.Shape)
        return [
            {
                "freecad_name": obj.Name,
                "x_min": float(box[0]),
                "x_max": float(box[1]),
                "y_min": float(box[2]),
                "y_max": float(box[3]),
            }
        ]
    leaves = []
    for property_name in ("Base", "Tool"):
        child = getattr(obj, property_name, None)
        if child is not None:
            leaves.extend(rectangle_sources(child, seen))
    return leaves


def export_step(doc, payload):
    names = payload.get("objects") or [obj.Name for obj in doc.Objects if hasattr(obj, "Shape")]
    objects = [doc.getObject(name) for name in names]
    objects = [obj for obj in objects if obj is not None and hasattr(obj, "Shape")]
    if not objects:
        raise ValueError("No exportable objects selected")
    output = payload["output"]
    os.makedirs(os.path.dirname(output), exist_ok=True)
    Part.export(objects, output)
    manifest_objects = []
    parts = []
    for obj in objects:
        shape = obj.Shape
        if hasattr(shape, "CenterOfMass"):
            center = shape.CenterOfMass
        else:
            box = shape.BoundBox
            center = App.Vector(
                0.5 * (box.XMin + box.XMax),
                0.5 * (box.YMin + box.YMax),
                0.5 * (box.ZMin + box.ZMax),
            )
        record = {
            "semantic_id": payload.get("semantic_ids", {}).get(obj.Name, obj.Name.lower()),
            "freecad_name": obj.Name,
            "label": obj.Label,
            "role": "solid" if len(shape.Solids) else "planar_face",
            "bbox_mm": bbox(shape),
            "centroid_mm": [center.x, center.y, center.z],
            "volume_mm3": float(shape.Volume),
            "area_mm2": float(shape.Area),
        }
        sources = rectangle_sources(obj)
        if sources:
            record["source_rectangles_mm"] = sources
        manifest_objects.append(record)
        if payload.get("also_export_parts"):
            part_path = os.path.join(os.path.dirname(output), "parts", record["semantic_id"] + ".step")
            os.makedirs(os.path.dirname(part_path), exist_ok=True)
            Part.export([obj], part_path)
            parts.append(part_path)
    manifest = {
        "schema_version": "1.0",
        "units": "mm",
        "coordinate_system": "global",
        "model_name": payload.get("model_name", doc.Label),
        "step_file": payload.get("step_file", "geometry/model.step"),
        "objects": manifest_objects,
    }
    manifest_path = payload["manifest"]
    with open(manifest_path, "w", encoding="utf-8") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
    return {"step": output, "manifest": manifest_path, "parts": parts, "objects": manifest_objects}


def dispatch(job):
    operation = job["operation"]
    payload = job.get("payload", {})
    document = job.get("document")
    doc = None
    try:
        if operation == "document_create":
            if os.path.exists(document) and not payload.get("overwrite"):
                raise FileExistsError(document)
            doc = App.newDocument(payload.get("name", "OpenCAE"), payload.get("label", "OpenCAE"))
            save(doc, document)
            return {"document": document, "label": doc.Label}

        doc = open_document(document)
        if operation == "document_inspect":
            return {"document": document, "label": doc.Label, "objects": [shape_record(obj) for obj in doc.Objects]}
        if operation == "object_inspect":
            obj = doc.getObject(payload["name"])
            if obj is None:
                raise KeyError(payload["name"])
            return shape_record(obj)
        if operation == "feature_create":
            result = create_feature(doc, payload)
            save(doc, document)
            return result
        if operation == "feature_update":
            result = update_feature(doc, payload)
            save(doc, document)
            return result
        if operation == "feature_delete":
            obj = doc.getObject(payload["name"])
            if obj is None:
                raise KeyError(payload["name"])
            dependents = [item.Name for item in obj.InList]
            if dependents and not payload.get("force"):
                raise ValueError("Object has dependents: %s" % dependents)
            doc.removeObject(obj.Name)
            save(doc, document)
            return {"deleted": payload["name"], "dependents": dependents}
        if operation == "boolean":
            result = boolean_feature(doc, payload)
            save(doc, document)
            return result
        if operation == "transform":
            obj = doc.getObject(payload["name"])
            if obj is None:
                raise KeyError(payload["name"])
            obj.Placement = placement_from(payload.get("placement"))
            doc.recompute()
            save(doc, document)
            return shape_record(obj)
        if operation == "geometry_validate":
            return validate(doc, payload.get("objects"))
        if operation == "document_save":
            output = payload.get("output", document)
            save(doc, output)
            return {"document": output}
        if operation == "export_step":
            result = export_step(doc, payload)
            return result
        raise ValueError("Unsupported operation: %s" % operation)
    finally:
        close_document(doc)


def main():
    job_path = os.environ["OPEN_CAE_JOB"]
    result_path = os.environ["OPEN_CAE_RESULT"]
    try:
        with open(job_path, "r", encoding="utf-8") as stream:
            job = json.load(stream)
        data = dispatch(job)
        result = {"ok": True, "data": data}
    except Exception as exc:
        result = {
            "ok": False,
            "error": str(exc),
            "error_type": type(exc).__name__,
            "traceback": traceback.format_exc(),
        }
    os.makedirs(os.path.dirname(result_path), exist_ok=True)
    with open(result_path, "w", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    if not result["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
