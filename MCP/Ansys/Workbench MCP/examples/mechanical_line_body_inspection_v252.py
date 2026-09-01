import json
import traceback

from Ansys.Mechanical.DataModel.Enums import DataModelObjectCategory

SOURCE_STEP = "UNSET_REQUIRED_BY_CALLER"
UNITS = "mm"


def text(value):
    try:
        return unicode(value)
    except Exception:
        return str(value)


def safe(obj, name):
    try:
        return text(getattr(obj, name))
    except Exception as error:
        return "<unavailable: %s>" % text(error)


report = {
    "schema_version": 1,
    "workflow": "fusion_step_to_beam_smoke",
    "phase": "MECHANICAL_LINE_BODY_IMPORT",
    "status": "FAIL",
    "ok": False,
    "source_step": SOURCE_STEP,
    "units": UNITS,
    "gates": {
        "step_file_check": None,
        "workbench_step_import": None,
        "spaceclaim_beam_idealization": None,
        "mechanical_line_body_import": None,
    },
    "bodies": [],
    "counts": {"all": 0, "active_line": 0, "active_solid": 0, "active_surface": 0},
    "orientation_objects": [],
    "warnings": [],
    "errors": [],
    "evidence": {},
}

try:
    if SOURCE_STEP == "UNSET_REQUIRED_BY_CALLER":
        report["warnings"].append("Set SOURCE_STEP and UNITS from the conversion manifest before final evidence validation.")
    model = ExtAPI.DataModel.Project.Model
    bodies = list(ExtAPI.DataModel.GetObjectsByType(DataModelObjectCategory.Body))
    report["counts"]["all"] = len(bodies)
    for body in bodies:
        geometry_type = safe(body, "GeometryType")
        suppressed = safe(body, "Suppressed").lower() == "true"
        item = {
            "name": safe(body, "Name"),
            "geometry_type": geometry_type,
            "model_type": safe(body, "ModelType"),
            "suppressed": suppressed,
            "material": safe(body, "Material"),
            "cross_section": safe(body, "CrossSection"),
        }
        try:
            geo_body = body.GetGeoBody()
            item["geometry_id"] = int(geo_body.Id)
            item["vertex_count"] = len(list(geo_body.Vertices))
        except Exception as error:
            item["geometry_probe_error"] = text(error)
        report["bodies"].append(item)
        if not suppressed:
            lower = geometry_type.lower()
            if "line" in lower:
                report["counts"]["active_line"] += 1
            elif "solid" in lower:
                report["counts"]["active_solid"] += 1
            elif "surface" in lower:
                report["counts"]["active_surface"] += 1

    for child in model.Geometry.Children:
        type_name = safe(child.GetType(), "FullName")
        if "Orientation" in type_name:
            report["orientation_objects"].append({
                "name": safe(child, "Name"),
                "type": type_name,
                "state": safe(child, "ObjectState"),
            })

    report["evidence"]["model_available"] = True
    report["status"] = "BLOCKED"
    report["warnings"].append(
        "Inventory completed. Compare member names, section read-back, orientation coverage, and connectivity against the conversion manifest before setting PASS."
    )
except Exception as error:
    report["errors"].append(text(error))
    report["traceback"] = traceback.format_exc()

print("ANSYS_STRUCTURAL_JSON:" + json.dumps(report, sort_keys=True))
