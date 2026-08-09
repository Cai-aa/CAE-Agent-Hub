# encoding: utf-8
"""Mechanical-side operations for repeatable structural workflows.

The MCP prepends a plain ``REQUEST`` dictionary and executes this file through
the Mechanical UI-thread file queue by default.  Keep this module compatible
with the IronPython runtime embedded in Mechanical.
"""

import os
import re
import time
import traceback


MARKER = "ANSYS_WORKBENCH_WORKFLOW_JSON:"
MANAGED_PREFIX = "WB_MCP_"


def _serializer():
    import clr
    clr.AddReference("System.Web.Extensions")
    from System.Web.Script.Serialization import JavaScriptSerializer
    return JavaScriptSerializer()


JSON = _serializer()


def _plain(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return dict((str(key), _plain(item)) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    try:
        return [_plain(item) for item in value]
    except Exception:
        return str(value)


def _quantity_payload(value):
    if value is None:
        return None
    payload = {"display": str(value)}
    try:
        payload["value"] = float(value.Value)
    except Exception:
        pass
    try:
        payload["unit"] = str(value.Unit)
    except Exception:
        pass
    return payload


def _children(obj):
    try:
        return list(obj.Children)
    except Exception:
        return []


def _walk(obj):
    values = []
    for child in _children(obj):
        values.append(child)
        values.extend(_walk(child))
    return values


def _objects_by_name(name):
    try:
        return list(DataModel.GetObjectsByName(name))
    except Exception:
        try:
            return list(ExtAPI.DataModel.GetObjectsByName(name))
        except Exception:
            return []


def _require_one(name):
    values = _objects_by_name(name)
    if len(values) != 1:
        raise ValueError("expected exactly one object named %s; found %d" % (name, len(values)))
    return values[0]


def _analysis(name):
    values = [item for item in list(Model.Analyses) if str(item.Name) == str(name)]
    if len(values) != 1:
        raise ValueError("expected exactly one analysis named %s; found %d" % (name, len(values)))
    return values[0]


def _delete_object(obj):
    try:
        obj.Delete()
        return
    except Exception:
        pass
    try:
        DataModel.Remove(obj)
        return
    except Exception:
        raise RuntimeError("cannot delete object: %s" % str(getattr(obj, "Name", obj)))


def _find_child(owner, name):
    return [item for item in _walk(owner) if str(getattr(item, "Name", "")) == str(name)]


def _ensure_result(solution, name, method_name):
    matches = _find_child(solution, name)
    if len(matches) > 1:
        raise ValueError("duplicate managed result name: %s" % name)
    if matches:
        return matches[0], False
    result = getattr(solution, method_name)()
    result.Name = name
    return result, True


def _session_state():
    state = {
        "project_available": False,
        "model_available": False,
        "analysis_collection_readable": False,
        "analysis_count": 0,
        "analyses": [],
    }
    try:
        project = ExtAPI.DataModel.Project
        state["project_available"] = project is not None
        if project is not None:
            state["project_directory"] = str(project.ProjectDirectory)
    except Exception as exc:
        state["project_error"] = str(exc)
    try:
        state["model_available"] = Model is not None
        analyses = list(Model.Analyses)
        state["analysis_collection_readable"] = True
        state["analysis_count"] = len(analyses)
        state["analyses"] = [str(item.Name) for item in analyses]
    except Exception as exc:
        state["model_error"] = str(exc)
    return state


def _require_ready():
    state = _session_state()
    if not state.get("project_available"):
        raise RuntimeError("Mechanical project is not available")
    if not state.get("model_available") or not state.get("analysis_collection_readable"):
        raise RuntimeError("Mechanical model or analysis collection is not available")
    return state


def _body_objects():
    bodies = []
    try:
        from Ansys.Mechanical.DataModel.Enums import DataModelObjectCategory
        bodies = list(DataModel.GetObjectsByType(DataModelObjectCategory.Body))
    except Exception:
        for obj in _walk(Model.Geometry):
            if obj.GetType().Name == "Body":
                bodies.append(obj)
    return bodies


def _contact_regions():
    regions = []
    for obj in _walk(Model.Connections):
        try:
            if obj.GetType().Name == "ContactRegion":
                regions.append(obj)
        except Exception:
            if "ContactRegion" in str(type(obj)):
                regions.append(obj)
    return regions


def _named_selections():
    try:
        return list(Model.NamedSelections.Children)
    except Exception:
        return []


def _geometry_inventory(payload):
    bodies = []
    for body in _body_objects():
        item = {
            "name": str(body.Name),
            "id": int(body.Id),
            "material": str(getattr(body, "Material", "")),
            "suppressed": bool(getattr(body, "Suppressed", False)),
        }
        try:
            geo = body.GetGeoBody()
            item["geometry_body_id"] = int(geo.Id)
            item["face_ids"] = [int(face.Id) for face in list(geo.Faces)]
            item["edge_ids"] = [int(edge.Id) for edge in list(geo.Edges)]
        except Exception as exc:
            item["geometry_entity_warning"] = str(exc)
        bodies.append(item)
    return {
        "bodies": bodies,
        "body_count": len(bodies),
        "named_selections": [str(item.Name) for item in _named_selections()],
        "contact_count": len(_contact_regions()),
        "analyses": [str(item.Name) for item in list(Model.Analyses)],
    }


def _import_geometry(payload):
    path = payload["geometry_path"]
    if not os.path.isfile(path):
        raise IOError("geometry file does not exist: %s" % path)
    name = payload["import_name"]
    existing = _objects_by_name(name)
    if existing and not payload.get("replace_existing"):
        raise ValueError("geometry import named %s already exists" % name)
    for obj in existing:
        _delete_object(obj)

    from Ansys.ACT.Mechanical.Utilities import GeometryImportPreferences
    from Ansys.Mechanical.DataModel.Enums.GeometryImportPreference import Format, AnalysisType

    before = len(_body_objects())
    preferences = GeometryImportPreferences()
    preferences.ProcessSolids = True
    preferences.ProcessSurfaces = False
    preferences.ProcessLines = False
    preferences.ProcessInstances = True
    preferences.ProcessNamedSelections = bool(payload.get("process_named_selections", True))
    preferences.ProcessCoordinateSystems = bool(payload.get("process_coordinate_systems", True))
    preferences.AnalysisType = AnalysisType.Type3D
    geometry_import = Model.GeometryImportGroup.AddGeometryImport()
    geometry_import.Name = name
    geometry_import.Import(path, Format.Automatic, preferences)
    after_bodies = _body_objects()
    return {
        "import_name": name,
        "geometry_path": path,
        "body_count_before": before,
        "body_count_after": len(after_bodies),
        "imported_body_count": len(after_bodies) - before,
        "body_names": [str(item.Name) for item in after_bodies],
    }


def _create_named_selection(payload):
    name = payload["name"]
    existing = _objects_by_name(name)
    if existing and not payload.get("replace_existing"):
        raise ValueError("named selection already exists: %s" % name)
    for obj in existing:
        _delete_object(obj)
    from Ansys.Mechanical.DataModel.Enums import SelectionTypeEnum
    selection = ExtAPI.SelectionManager.CreateSelectionInfo(SelectionTypeEnum.GeometryEntities)
    selection.Ids = [int(value) for value in payload["entity_ids"]]
    named = Model.AddNamedSelection()
    named.Name = name
    named.Location = selection
    return {"name": name, "entity_ids": list(payload["entity_ids"]), "entity_count": len(payload["entity_ids"])}


def _get_or_create_analysis(name, kind, replace_existing):
    matches = [item for item in list(Model.Analyses) if str(item.Name) == str(name)]
    if len(matches) > 1:
        raise ValueError("duplicate analysis name: %s" % name)
    if matches and replace_existing:
        _delete_object(matches[0])
        matches = []
    if matches:
        return matches[0], False
    if kind == "static":
        analysis = Model.AddStaticStructuralAnalysis()
    elif kind == "modal":
        analysis = Model.AddModalAnalysis()
    else:
        raise ValueError("unsupported analysis kind: %s" % kind)
    analysis.Name = name
    return analysis, True


def _configure_modal_results(analysis, mode_count):
    analysis.AnalysisSettings.MaximumModesToFind = int(mode_count)
    created = []
    for mode in range(1, int(mode_count) + 1):
        name = MANAGED_PREFIX + "Mode_%02d" % mode
        result, was_created = _ensure_result(analysis.Solution, name, "AddTotalDeformation")
        result.Mode = mode
        if was_created:
            created.append(name)
    return created


def _create_analysis_chain(payload):
    replace = bool(payload.get("replace_existing"))
    static, static_created = _get_or_create_analysis(payload["static_name"], "static", replace)
    baseline = None
    baseline_created = False
    if payload.get("include_baseline_modal"):
        baseline, baseline_created = _get_or_create_analysis(payload["baseline_modal_name"], "modal", replace)
        _configure_modal_results(baseline, payload["mode_count"])
    prestressed, prestressed_created = _get_or_create_analysis(payload["prestressed_modal_name"], "modal", replace)
    _configure_modal_results(prestressed, payload["mode_count"])

    initial_conditions = list(prestressed.InitialConditions)
    if not initial_conditions:
        raise RuntimeError("prestressed modal analysis has no InitialConditions object")
    initial_conditions[0].PreStressEnvironmentModalIC = static

    _ensure_result(static.Solution, MANAGED_PREFIX + "Total_Deformation", "AddTotalDeformation")
    _ensure_result(static.Solution, MANAGED_PREFIX + "Equivalent_Stress", "AddEquivalentStress")
    _ensure_result(static.Solution, MANAGED_PREFIX + "Maximum_Principal_Stress", "AddMaximumPrincipalStress")
    try:
        _ensure_result(static.Solution, MANAGED_PREFIX + "Contact_Tool", "AddContactTool")
    except Exception:
        pass

    return {
        "static": {"name": str(static.Name), "created": static_created},
        "baseline_modal": None if baseline is None else {"name": str(baseline.Name), "created": baseline_created},
        "prestressed_modal": {"name": str(prestressed.Name), "created": prestressed_created},
        "mode_count": int(payload["mode_count"]),
        "prestress_source": str(initial_conditions[0].PreStressEnvironmentModalIC.Name),
    }


def _selection_from_all_bodies():
    from Ansys.Mechanical.DataModel.Enums import SelectionTypeEnum
    selection = ExtAPI.SelectionManager.CreateSelectionInfo(SelectionTypeEnum.GeometryEntities)
    ids = []
    for body in _body_objects():
        if bool(getattr(body, "Suppressed", False)):
            continue
        try:
            ids.append(int(body.GetGeoBody().Id))
        except Exception:
            ids.append(int(body.Id))
    selection.Ids = ids
    return selection


def _set_component(field, value, unit):
    field.Output.SetDiscreteValue(0, Quantity("%s [%s]" % (value, unit)))


def _find_direct_child(owner, name):
    return [item for item in _children(owner) if str(getattr(item, "Name", "")) == str(name)]


def _configure_named_contacts(contact_pairs, replace_managed):
    from Ansys.Mechanical.DataModel.Enums import ContactType
    created = []
    updated = []
    for index, pair in enumerate(contact_pairs):
        name = MANAGED_PREFIX + "Bonded_%02d" % (index + 1)
        matches = _objects_by_name(name)
        if len(matches) > 1:
            raise ValueError("duplicate managed contact name: %s" % name)
        if matches and replace_managed:
            _delete_object(matches[0])
            matches = []
        if matches:
            contact = matches[0]
            updated.append(name)
        else:
            contact = Model.Connections.AddContactRegion()
            contact.Name = name
            created.append(name)
        contact.SourceLocation = _require_one(pair["source"]).Location
        contact.TargetLocation = _require_one(pair["target"]).Location
        contact.ContactType = ContactType.Bonded
    return created, updated


def _configure_rotor(payload):
    from Ansys.Mechanical.DataModel.Enums import ContactType, LoadDefineBy

    analysis = _analysis(payload["analysis_name"])
    bodies = _body_objects()
    if not bodies:
        raise RuntimeError("no geometry bodies are available")

    material_name = payload.get("material_name")
    material_updates = []
    if material_name:
        for body in bodies:
            body.Material = material_name
            material_updates.append(str(body.Name))

    contact_mode = payload.get("contact_mode", "existing")
    created_contacts = []
    updated_contacts = []
    if contact_mode == "automatic_bonded":
        before_ids = set(int(item.Id) for item in _contact_regions())
        Model.Connections.CreateAutomaticConnections()
        for contact in _contact_regions():
            if int(contact.Id) not in before_ids:
                contact.ContactType = ContactType.Bonded
                contact.Name = MANAGED_PREFIX + "Auto_Bonded_%02d" % (len(created_contacts) + 1)
                created_contacts.append(str(contact.Name))
    elif contact_mode == "named_pairs":
        created_contacts, updated_contacts = _configure_named_contacts(
            payload.get("contact_pairs", []), bool(payload.get("replace_managed_objects"))
        )

    contacts = _contact_regions()
    non_bonded = []
    for contact in contacts:
        try:
            contact_type = str(contact.ContactType)
            if not contact_type.endswith("Bonded"):
                non_bonded.append({"name": str(contact.Name), "contact_type": contact_type})
        except Exception as exc:
            non_bonded.append({"name": str(contact.Name), "contact_type_error": str(exc)})
    if not contacts:
        raise RuntimeError("no contact regions are available after contact configuration")
    if non_bonded:
        raise RuntimeError("rotor workflow requires bonded contacts; non-bonded=%s" % str(non_bonded))
    expected_contacts = payload.get("expected_contact_count")
    if expected_contacts is not None and len(contacts) != int(expected_contacts):
        raise RuntimeError(
            "contact count mismatch: expected %d, found %d" % (int(expected_contacts), len(contacts))
        )

    support_scope = _require_one(payload["fixed_support_named_selection"]).Location
    support_records = []
    support_analyses = [analysis]
    for modal_name in payload.get("modal_analysis_names", []):
        support_analyses.append(_analysis(modal_name))
    for support_analysis in support_analyses:
        support_name = MANAGED_PREFIX + "Fixed_Support"
        matches = _find_direct_child(support_analysis, support_name)
        if len(matches) > 1:
            raise ValueError("duplicate managed fixed support in %s" % str(support_analysis.Name))
        if matches:
            support = matches[0]
        else:
            support = support_analysis.AddFixedSupport()
            support.Name = support_name
        support.Location = support_scope
        support_records.append({"analysis_name": str(support_analysis.Name), "support_name": support_name})

    rotation_name = MANAGED_PREFIX + "Rotational_Velocity"
    matches = _find_direct_child(analysis, rotation_name)
    if len(matches) > 1:
        raise ValueError("duplicate managed rotational velocity")
    if matches:
        rotation = matches[0]
    else:
        rotation = analysis.AddRotationalVelocity()
        rotation.Name = rotation_name
    rotation.DefineBy = LoadDefineBy.Components
    coordinate_name = payload.get("coordinate_system_name")
    if coordinate_name:
        rotation.CoordinateSystem = _require_one(coordinate_name)
    scope_name = payload.get("rotation_scope_named_selection")
    rotation.Location = _require_one(scope_name).Location if scope_name else _selection_from_all_bodies()
    speed = float(payload["rotational_speed_rpm"])
    components = {"X": 0.0, "Y": 0.0, "Z": 0.0}
    components[payload["rotation_axis"]] = speed
    _set_component(rotation.XComponent, components["X"], "rpm")
    _set_component(rotation.YComponent, components["Y"], "rpm")
    _set_component(rotation.ZComponent, components["Z"], "rpm")
    try:
        analysis.AnalysisSettings.LargeDeflection = bool(payload.get("large_deflection", True))
    except Exception:
        pass

    return {
        "analysis_name": str(analysis.Name),
        "body_count": len(bodies),
        "material_updated_bodies": material_updates,
        "contact_mode": contact_mode,
        "contact_count": len(contacts),
        "created_contacts": created_contacts,
        "updated_contacts": updated_contacts,
        "fixed_supports": support_records,
        "rotational_velocity": rotation_name,
        "rotation_axis": payload["rotation_axis"],
        "rotational_speed_rpm": speed,
    }


def _mesh_counts():
    result = {"nodes": None, "elements": None, "unsupported": []}
    mesh_data = None
    try:
        mesh_data = ExtAPI.DataModel.Project.Model.MeshData
    except Exception:
        pass
    if mesh_data is not None:
        for key, candidates in (("nodes", ["NodeCount", "NodesCount"]), ("elements", ["ElementCount", "ElementsCount"])):
            for name in candidates:
                try:
                    result[key] = int(getattr(mesh_data, name))
                    break
                except Exception:
                    pass
            if result[key] is None:
                result["unsupported"].append(key)
    else:
        for key, name in (("nodes", "Nodes"), ("elements", "Elements")):
            try:
                result[key] = int(getattr(Model.Mesh, name))
            except Exception:
                result["unsupported"].append(key)
    return result


def _mesh_and_validate(payload):
    Model.Mesh.ElementSize = Quantity("%s [mm]" % float(payload["global_size_mm"]))
    sizing_records = []
    for item in payload.get("local_sizings", []):
        name = MANAGED_PREFIX + "Sizing_" + re.sub(r"[^A-Za-z0-9_]", "_", item["named_selection"])
        matches = _objects_by_name(name)
        if len(matches) > 1:
            raise ValueError("duplicate managed sizing name: %s" % name)
        if matches and payload.get("replace_managed_objects"):
            _delete_object(matches[0])
            matches = []
        if matches:
            sizing = matches[0]
        else:
            sizing = Model.Mesh.AddSizing()
            sizing.Name = name
        sizing.Location = _require_one(item["named_selection"]).Location
        sizing.ElementSize = Quantity("%s [mm]" % float(item["size_mm"]))
        sizing_records.append({"name": name, "size_mm": float(item["size_mm"])})
    if payload.get("clear_generated_data"):
        try:
            Model.Mesh.ClearGeneratedData()
        except Exception:
            pass
    if payload.get("generate_mesh"):
        Model.Mesh.GenerateMesh()
    counts = _mesh_counts()
    if payload.get("generate_mesh") and counts.get("elements") == 0:
        raise RuntimeError("mesh generation returned zero elements")
    return {
        "global_size_mm": float(payload["global_size_mm"]),
        "local_sizings": sizing_records,
        "generated": bool(payload.get("generate_mesh")),
        "mesh_counts": counts,
    }


def _solve(payload):
    records = []
    for name in payload["analysis_names"]:
        analysis = _analysis(name)
        started = time.time()
        try:
            analysis.Solve(True)
        except TypeError:
            analysis.Solution.Solve(True)
        records.append(
            {
                "analysis_name": name,
                "elapsed_seconds": round(time.time() - started, 3),
                "solution_status": str(getattr(analysis.Solution, "Status", "unknown")),
            }
        )
    if payload.get("save_after"):
        try:
            ExtAPI.DataModel.Project.Save()
        except Exception as exc:
            records.append({"save_warning": str(exc)})
    return {"solved": records, "solve_count": len(records)}


def _evaluate_solution(analysis):
    try:
        analysis.Solution.EvaluateAllResults()
    except Exception:
        pass


def _result_record(obj):
    record = {
        "name": str(obj.Name),
        "type": str(obj.GetType().Name),
        "status": str(getattr(obj, "Status", "unknown")),
    }
    for key, attr in (
        ("minimum", "Minimum"),
        ("maximum", "Maximum"),
        ("average", "Average"),
        ("frequency", "Frequency"),
        ("mode", "Mode"),
        ("maximum_occurs_on", "MaximumOccursOn"),
        ("minimum_occurs_on", "MinimumOccursOn"),
    ):
        try:
            value = getattr(obj, attr)
            if attr in ("Mode", "MaximumOccursOn", "MinimumOccursOn"):
                record[key] = _plain(value)
            else:
                record[key] = _quantity_payload(value)
        except Exception:
            pass
    return record


def _extract_structural(payload):
    analysis = _analysis(payload["analysis_name"])
    _evaluate_solution(analysis)
    records = []
    for obj in _walk(analysis.Solution):
        name = str(getattr(obj, "Name", ""))
        if name.startswith(MANAGED_PREFIX):
            records.append(_result_record(obj))
    return {
        "analysis_name": str(analysis.Name),
        "solution_status": str(getattr(analysis.Solution, "Status", "unknown")),
        "results": records,
    }


def _extract_modal(payload):
    analyses = []
    for name in payload["analysis_names"]:
        analysis = _analysis(name)
        _evaluate_solution(analysis)
        modes = []
        for obj in _walk(analysis.Solution):
            obj_name = str(getattr(obj, "Name", ""))
            if obj_name.startswith(MANAGED_PREFIX + "Mode_"):
                modes.append(_result_record(obj))
        modes.sort(key=lambda item: int(item.get("mode") or 0))
        analyses.append(
            {
                "analysis_name": name,
                "solution_status": str(getattr(analysis.Solution, "Status", "unknown")),
                "modes": modes[: int(payload["mode_count"])],
            }
        )
    comparison = []
    if len(analyses) == 2:
        left = analyses[0]["modes"]
        right = analyses[1]["modes"]
        for index in range(min(len(left), len(right))):
            first = left[index].get("frequency") or {}
            second = right[index].get("frequency") or {}
            if "value" in first and "value" in second and first["value"]:
                comparison.append(
                    {
                        "mode": index + 1,
                        "baseline": first,
                        "prestressed": second,
                        "change_percent": 100.0 * (second["value"] - first["value"]) / first["value"],
                    }
                )
    return {"analyses": analyses, "frequency_comparison": comparison}


def _safe_filename(value):
    return re.sub(r"[^A-Za-z0-9_.-]", "_", value)


def _versioned_path(path):
    stem, ext = os.path.splitext(path)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    candidate = stem + "." + stamp + ext
    counter = 1
    while os.path.exists(candidate):
        candidate = stem + "." + stamp + "." + str(counter) + ext
        counter += 1
    return candidate


def _output_path(directory, filename, policy):
    path = os.path.join(directory, filename)
    if not os.path.exists(path):
        return path
    if policy == "error":
        raise IOError("output already exists: %s" % path)
    if policy == "versioned":
        return _versioned_path(path)
    return path


def _export_evidence(payload):
    from Ansys.Mechanical.DataModel.Enums import GraphicsImageExportFormat
    from Ansys.Mechanical.Graphics import GraphicsImageExportSettings

    directory = payload["output_dir"]
    if not os.path.isdir(directory):
        os.makedirs(directory)
    policy = payload.get("overwrite_policy", "error")
    exported = []
    for name in payload["result_names"]:
        result = _require_one(name)
        result.Activate()
        image_path = _output_path(directory, _safe_filename(name) + ".png", policy)
        settings = GraphicsImageExportSettings()
        ExtAPI.Graphics.ExportImage(image_path, GraphicsImageExportFormat.PNG, settings)
        record = {"result_name": name, "image_path": image_path}
        try:
            text_path = _output_path(directory, _safe_filename(name) + ".txt", policy)
            result.ExportToTextFile(text_path)
            record["table_path"] = text_path
        except Exception as exc:
            record["table_warning"] = str(exc)
        exported.append(record)
    return {"output_dir": directory, "exported": exported, "count": len(exported)}


def _dispatch(request):
    operation = request.get("operation")
    payload = request.get("payload") or {}
    if operation == "probe_session":
        return _session_state()
    _require_ready()
    if operation == "geometry_inventory":
        return _geometry_inventory(payload)
    if operation == "import_geometry":
        return _import_geometry(payload)
    if operation == "create_named_selection":
        return _create_named_selection(payload)
    if operation == "create_analysis_chain":
        return _create_analysis_chain(payload)
    if operation == "configure_rotor":
        return _configure_rotor(payload)
    if operation == "mesh_and_validate":
        return _mesh_and_validate(payload)
    if operation == "solve":
        return _solve(payload)
    if operation == "extract_structural":
        return _extract_structural(payload)
    if operation == "extract_modal":
        return _extract_modal(payload)
    if operation == "export_evidence":
        return _export_evidence(payload)
    raise ValueError("unsupported operation: %s" % operation)


try:
    _operation = str(REQUEST.get("operation"))
    _payload = {
        "ok": True,
        "operation": _operation,
        "session": _session_state(),
        "data": _dispatch(REQUEST),
        "warnings": [],
        "errors": [],
    }
except Exception:
    _payload = {
        "ok": False,
        "operation": str(REQUEST.get("operation") if "REQUEST" in globals() else "missing_request"),
        "session": _session_state(),
        "data": {},
        "warnings": [],
        "errors": [traceback.format_exc()],
    }

_result = _plain(_payload)
print(MARKER + JSON.Serialize(_result))
