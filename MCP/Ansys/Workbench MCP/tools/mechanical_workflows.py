from __future__ import annotations

import json
import pprint
import re
import time
import uuid
from pathlib import Path
from typing import Any

from tools.workbench_bridge import WORKBENCH_JOBS_DIR, launch_workbench_journal
from tools.workbench_file_queue import (
    queue_execute_python,
    read_response,
)
from tools.workbench_socket_timer import (
    socket_timer_execute_python,
    socket_timer_state,
)


ROOT = Path(__file__).resolve().parents[1]
MECHANICAL_WORKFLOW_SCRIPT = ROOT / "workbench_plugin" / "mechanical_analysis_workflows.py"
WORKFLOW_JOB_DIR = WORKBENCH_JOBS_DIR / "workflow_inputs"
SUPPORTED_GEOMETRY_SUFFIXES = {
    ".step",
    ".stp",
    ".iges",
    ".igs",
    ".x_t",
    ".x_b",
    ".sat",
    ".scdoc",
    ".scdocx",
    ".pmdb",
}
SUPPORTED_TRANSPORTS = {"queue", "socket"}
SOCKET_READ_ONLY_OPERATIONS = {"probe_session", "geometry_inventory"}
SUPPORTED_OVERWRITE_POLICIES = {"error", "versioned", "replace"}
SAFE_NAME = re.compile(r"^[A-Za-z0-9_. -]{1,120}$")
WORKFLOW_MARKER = "ANSYS_WORKBENCH_WORKFLOW_JSON:"


def _error(message: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": False, "status": "error", "error": message}
    payload.update(extra)
    return payload


def _validate_name(value: str, field: str) -> str:
    text = str(value or "").strip()
    if not SAFE_NAME.fullmatch(text):
        raise ValueError(f"{field} must contain only letters, digits, spaces, '.', '_' or '-'")
    return text


def _positive_number(value: Any, field: str, *, allow_zero: bool = False) -> float:
    try:
        number = float(value)
    except Exception as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if allow_zero:
        if number < 0:
            raise ValueError(f"{field} must be >= 0")
    elif number <= 0:
        raise ValueError(f"{field} must be > 0")
    return number


def _resolve_existing_file(path: str, field: str) -> Path:
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"{field} does not exist: {resolved}")
    return resolved


def _resolve_output_path(path: str, overwrite_policy: str) -> Path:
    policy = str(overwrite_policy or "error").lower()
    if policy not in SUPPORTED_OVERWRITE_POLICIES:
        raise ValueError("overwrite_policy must be error, versioned, or replace")
    resolved = Path(path).expanduser().resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    if not resolved.exists():
        return resolved
    if policy == "error":
        raise FileExistsError(str(resolved))
    if policy == "replace":
        return resolved
    stamp = time.strftime("%Y%m%d_%H%M%S")
    candidate = resolved.with_name(f"{resolved.stem}.{stamp}{resolved.suffix}")
    counter = 1
    while candidate.exists():
        candidate = resolved.with_name(f"{resolved.stem}.{stamp}.{counter}{resolved.suffix}")
        counter += 1
    return candidate


def validate_rotor_job_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize the rotor structural-analysis input."""
    errors: list[str] = []
    warnings: list[str] = []
    normalized: dict[str, Any] = {}

    try:
        normalized["analysis_name"] = _validate_name(
            spec.get("analysis_name", "Rotating_Static"), "analysis_name"
        )
    except Exception as exc:
        errors.append(str(exc))

    try:
        normalized["rotational_speed_rpm"] = _positive_number(
            spec.get("rotational_speed_rpm"), "rotational_speed_rpm"
        )
    except Exception as exc:
        errors.append(str(exc))

    axis = str(spec.get("rotation_axis", "X")).strip().upper()
    if axis not in {"X", "Y", "Z"}:
        errors.append("rotation_axis must be X, Y, or Z")
    normalized["rotation_axis"] = axis

    fixed_name = str(spec.get("fixed_support_named_selection", "")).strip()
    if not fixed_name:
        errors.append("fixed_support_named_selection is required")
    else:
        try:
            normalized["fixed_support_named_selection"] = _validate_name(
                fixed_name, "fixed_support_named_selection"
            )
        except Exception as exc:
            errors.append(str(exc))

    rotation_scope = str(spec.get("rotation_scope_named_selection", "")).strip()
    if rotation_scope:
        try:
            normalized["rotation_scope_named_selection"] = _validate_name(
                rotation_scope, "rotation_scope_named_selection"
            )
        except Exception as exc:
            errors.append(str(exc))
    else:
        normalized["rotation_scope_named_selection"] = ""

    coordinate_system = str(spec.get("coordinate_system_name", "")).strip()
    if coordinate_system:
        try:
            normalized["coordinate_system_name"] = _validate_name(
                coordinate_system, "coordinate_system_name"
            )
        except Exception as exc:
            errors.append(str(exc))
    else:
        normalized["coordinate_system_name"] = ""

    contact_mode = str(spec.get("contact_mode", "existing")).strip().lower()
    if contact_mode not in {"existing", "automatic_bonded", "named_pairs"}:
        errors.append("contact_mode must be existing, automatic_bonded, or named_pairs")
    normalized["contact_mode"] = contact_mode

    contact_pairs: list[dict[str, str]] = []
    seen_pairs: set[tuple[str, str]] = set()
    for index, pair in enumerate(spec.get("contact_pairs", []) or []):
        if not isinstance(pair, dict):
            errors.append(f"contact_pairs[{index}] must be an object")
            continue
        try:
            source = _validate_name(pair.get("source", ""), f"contact_pairs[{index}].source")
            target = _validate_name(pair.get("target", ""), f"contact_pairs[{index}].target")
        except Exception as exc:
            errors.append(str(exc))
            continue
        key = (source, target)
        if key in seen_pairs:
            errors.append(f"duplicate contact pair: {source} -> {target}")
            continue
        seen_pairs.add(key)
        contact_pairs.append({"source": source, "target": target})
    normalized["contact_pairs"] = contact_pairs
    if contact_mode == "named_pairs" and not contact_pairs:
        errors.append("contact_pairs is required when contact_mode=named_pairs")

    expected_contacts = spec.get("expected_contact_count")
    if expected_contacts is not None:
        try:
            expected_contacts = int(expected_contacts)
            if expected_contacts <= 0:
                raise ValueError
            normalized["expected_contact_count"] = expected_contacts
        except Exception:
            errors.append("expected_contact_count must be a positive integer")
    else:
        normalized["expected_contact_count"] = None

    material_name = str(spec.get("material_name", "")).strip()
    normalized["material_name"] = material_name
    if not material_name:
        warnings.append("material_name is empty; existing body materials will be preserved")

    normalized["large_deflection"] = bool(spec.get("large_deflection", True))
    normalized["replace_managed_objects"] = bool(spec.get("replace_managed_objects", False))
    modal_names: list[str] = []
    for index, value in enumerate(
        spec.get("modal_analysis_names", ["Modal_Zero_RPM", "Modal_Prestressed"]) or []
    ):
        try:
            modal_names.append(_validate_name(value, f"modal_analysis_names[{index}]"))
        except Exception as exc:
            errors.append(str(exc))
    if len(set(modal_names)) != len(modal_names):
        errors.append("modal_analysis_names must be unique")
    normalized["modal_analysis_names"] = modal_names

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "normalized": normalized,
    }


def validate_mesh_spec(spec: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    normalized: dict[str, Any] = {}
    try:
        normalized["global_size_mm"] = _positive_number(spec.get("global_size_mm"), "global_size_mm")
    except Exception as exc:
        errors.append(str(exc))
    local_sizings: list[dict[str, Any]] = []
    for index, item in enumerate(spec.get("local_sizings", []) or []):
        if not isinstance(item, dict):
            errors.append(f"local_sizings[{index}] must be an object")
            continue
        try:
            name = _validate_name(item.get("named_selection", ""), f"local_sizings[{index}].named_selection")
            size = _positive_number(item.get("size_mm"), f"local_sizings[{index}].size_mm")
            local_sizings.append({"named_selection": name, "size_mm": size})
        except Exception as exc:
            errors.append(str(exc))
    normalized["local_sizings"] = local_sizings
    normalized["generate_mesh"] = bool(spec.get("generate_mesh", True))
    normalized["clear_generated_data"] = bool(spec.get("clear_generated_data", True))
    normalized["replace_managed_objects"] = bool(spec.get("replace_managed_objects", False))
    return {"ok": not errors, "errors": errors, "normalized": normalized}


def _mechanical_script(operation: str, payload: dict[str, Any]) -> str:
    if not MECHANICAL_WORKFLOW_SCRIPT.is_file():
        raise FileNotFoundError(str(MECHANICAL_WORKFLOW_SCRIPT))
    request = {"operation": operation, "payload": payload}
    request_literal = pprint.pformat(request, width=100, sort_dicts=True)
    body = MECHANICAL_WORKFLOW_SCRIPT.read_text(encoding="utf-8")
    return f"REQUEST = {request_literal}\n\n{body}"


def _find_workflow_marker(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        for item in value.values():
            found = _find_workflow_marker(item)
            if found is not None:
                return found
        return None
    if isinstance(value, (list, tuple)):
        for item in value:
            found = _find_workflow_marker(item)
            if found is not None:
                return found
        return None
    if not isinstance(value, str) or WORKFLOW_MARKER not in value:
        return None
    text = value.split(WORKFLOW_MARKER, 1)[1].splitlines()[0].strip()
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    except Exception:
        return None


def _dispatch(operation: str, payload: dict[str, Any], transport: str, wait_timeout: float) -> dict[str, Any]:
    selected = str(transport or "queue").lower()
    if selected not in SUPPORTED_TRANSPORTS:
        return _error("transport must be queue or socket")
    if selected == "socket" and operation not in SOCKET_READ_ONLY_OPERATIONS:
        return _error(
            "socket transport is blocked for this operation; use transport=queue so Mechanical executes it on the UI thread"
        )
    try:
        code = _mechanical_script(operation, payload)
    except Exception as exc:
        return _error(str(exc))

    if selected == "socket":
        result = socket_timer_execute_python(code=code, timeout=max(1.0, float(wait_timeout)))
        result["transport"] = "socket_background_thread"
        result["warning"] = (
            "Socket execution is intended for diagnostics or explicitly supported operations. "
            "Use transport=queue for Mechanical data-model mutations."
        )
        parsed = _find_workflow_marker(result)
        if parsed is not None:
            result["workflow_result"] = parsed
        return result

    result = queue_execute_python(code=code, wait_timeout=max(0.0, float(wait_timeout)))
    result["transport"] = "file_queue_ui_thread"
    response = result.get("response", {})
    if response.get("timed_out"):
        result["status"] = "submitted"
        result["next_step"] = "Poll mechanical_workflow_status_tool with the returned request_id; do not resubmit."
    parsed = _find_workflow_marker(result)
    if parsed is not None:
        result["workflow_result"] = parsed
    return result


def mechanical_readiness(timeout: float = 5.0) -> dict[str, Any]:
    socket_state = socket_timer_state(timeout=max(1.0, float(timeout)))
    if not socket_state.get("ok"):
        return {
            "ok": False,
            "ready_for_model_mutation": False,
            "bridge_connected": False,
            "socket": socket_state,
            "required_state": {
                "project_available": True,
                "model_available": True,
                "analysis_collection_readable": True,
            },
        }
    probe = _dispatch("probe_session", {}, "queue", max(0.0, float(timeout)))
    workflow = probe.get("workflow_result") or {}
    state = workflow.get("data") or workflow.get("session") or {}
    ready = all(
        bool(state.get(key))
        for key in ("project_available", "model_available", "analysis_collection_readable")
    )
    return {
        "ok": ready,
        "ready_for_model_mutation": ready,
        "bridge_connected": True,
        "socket": socket_state,
        "ui_queue_probe": probe,
        "mechanical_state": state,
        "required_state": {
            "project_available": True,
            "model_available": True,
            "analysis_collection_readable": True,
        },
        "note": (
            "Ready only when the UI-thread probe proves Project, Model, and Model.Analyses. "
            "A reachable socket or has_model_symbol flag alone is insufficient."
        ),
    }


def mechanical_probe_session(transport: str = "queue", wait_timeout: float = 5.0) -> dict[str, Any]:
    return _dispatch("probe_session", {}, transport, wait_timeout)


def mechanical_geometry_inventory(transport: str = "queue", wait_timeout: float = 10.0) -> dict[str, Any]:
    return _dispatch("geometry_inventory", {}, transport, wait_timeout)


def mechanical_import_geometry(
    geometry_path: str,
    import_name: str = "WB_MCP_Geometry_Import",
    process_named_selections: bool = True,
    process_coordinate_systems: bool = True,
    replace_existing: bool = False,
    transport: str = "queue",
    wait_timeout: float = 30.0,
) -> dict[str, Any]:
    try:
        path = _resolve_existing_file(geometry_path, "geometry_path")
        if path.suffix.lower() not in SUPPORTED_GEOMETRY_SUFFIXES:
            raise ValueError(f"unsupported geometry suffix: {path.suffix}")
        name = _validate_name(import_name, "import_name")
    except Exception as exc:
        return _error(str(exc))
    payload = {
        "geometry_path": str(path),
        "import_name": name,
        "process_named_selections": bool(process_named_selections),
        "process_coordinate_systems": bool(process_coordinate_systems),
        "replace_existing": bool(replace_existing),
    }
    return _dispatch("import_geometry", payload, transport, wait_timeout)


def mechanical_create_named_selection(
    name: str,
    entity_ids: list[int],
    replace_existing: bool = False,
    transport: str = "queue",
    wait_timeout: float = 10.0,
) -> dict[str, Any]:
    try:
        clean_name = _validate_name(name, "name")
        ids = sorted(set(int(value) for value in entity_ids))
        if not ids or any(value <= 0 for value in ids):
            raise ValueError("entity_ids must contain positive geometry entity ids")
    except Exception as exc:
        return _error(str(exc))
    return _dispatch(
        "create_named_selection",
        {"name": clean_name, "entity_ids": ids, "replace_existing": bool(replace_existing)},
        transport,
        wait_timeout,
    )


def mechanical_create_analysis_chain(
    static_name: str = "Rotating_Static",
    baseline_modal_name: str = "Modal_Zero_RPM",
    prestressed_modal_name: str = "Modal_Prestressed",
    mode_count: int = 6,
    include_baseline_modal: bool = True,
    replace_existing: bool = False,
    transport: str = "queue",
    wait_timeout: float = 15.0,
) -> dict[str, Any]:
    try:
        payload = {
            "static_name": _validate_name(static_name, "static_name"),
            "baseline_modal_name": _validate_name(baseline_modal_name, "baseline_modal_name"),
            "prestressed_modal_name": _validate_name(prestressed_modal_name, "prestressed_modal_name"),
            "mode_count": int(mode_count),
            "include_baseline_modal": bool(include_baseline_modal),
            "replace_existing": bool(replace_existing),
        }
        if payload["mode_count"] < 1 or payload["mode_count"] > 100:
            raise ValueError("mode_count must be between 1 and 100")
        names = [payload["static_name"], payload["prestressed_modal_name"]]
        if payload["include_baseline_modal"]:
            names.append(payload["baseline_modal_name"])
        if len(set(names)) != len(names):
            raise ValueError("analysis names must be unique")
    except Exception as exc:
        return _error(str(exc))
    return _dispatch("create_analysis_chain", payload, transport, wait_timeout)


def mechanical_configure_rotor_model(
    spec: dict[str, Any], transport: str = "queue", wait_timeout: float = 20.0
) -> dict[str, Any]:
    validation = validate_rotor_job_spec(spec)
    if not validation["ok"]:
        return _error("rotor job spec validation failed", validation=validation)
    return _dispatch("configure_rotor", validation["normalized"], transport, wait_timeout)


def mechanical_mesh_and_validate(
    spec: dict[str, Any], transport: str = "queue", wait_timeout: float = 60.0
) -> dict[str, Any]:
    validation = validate_mesh_spec(spec)
    if not validation["ok"]:
        return _error("mesh spec validation failed", validation=validation)
    return _dispatch("mesh_and_validate", validation["normalized"], transport, wait_timeout)


def mechanical_solve_analysis(
    analysis_names: list[str],
    save_after: bool = True,
    transport: str = "queue",
    wait_timeout: float = 2.0,
) -> dict[str, Any]:
    try:
        names = [_validate_name(value, "analysis_names") for value in analysis_names]
        if not names:
            raise ValueError("analysis_names must not be empty")
        if len(set(names)) != len(names):
            raise ValueError("analysis_names must be unique")
    except Exception as exc:
        return _error(str(exc))
    return _dispatch("solve", {"analysis_names": names, "save_after": bool(save_after)}, transport, wait_timeout)


def mechanical_extract_structural_results(
    analysis_name: str = "Rotating_Static",
    transport: str = "queue",
    wait_timeout: float = 15.0,
) -> dict[str, Any]:
    try:
        name = _validate_name(analysis_name, "analysis_name")
    except Exception as exc:
        return _error(str(exc))
    return _dispatch("extract_structural", {"analysis_name": name}, transport, wait_timeout)


def mechanical_extract_modal_results(
    analysis_names: list[str] | None = None,
    mode_count: int = 6,
    transport: str = "queue",
    wait_timeout: float = 15.0,
) -> dict[str, Any]:
    selected = analysis_names or ["Modal_Zero_RPM", "Modal_Prestressed"]
    try:
        names = [_validate_name(value, "analysis_names") for value in selected]
        count = int(mode_count)
        if count < 1 or count > 100:
            raise ValueError("mode_count must be between 1 and 100")
    except Exception as exc:
        return _error(str(exc))
    return _dispatch("extract_modal", {"analysis_names": names, "mode_count": count}, transport, wait_timeout)


def mechanical_export_evidence(
    output_dir: str,
    result_names: list[str],
    overwrite_policy: str = "error",
    transport: str = "queue",
    wait_timeout: float = 30.0,
) -> dict[str, Any]:
    try:
        policy = str(overwrite_policy or "error").lower()
        if policy not in SUPPORTED_OVERWRITE_POLICIES:
            raise ValueError("overwrite_policy must be error, versioned, or replace")
        directory = Path(output_dir).expanduser().resolve()
        directory.mkdir(parents=True, exist_ok=True)
        names = [_validate_name(value, "result_names") for value in result_names]
        if not names:
            raise ValueError("result_names must not be empty")
    except Exception as exc:
        return _error(str(exc))
    return _dispatch(
        "export_evidence",
        {"output_dir": str(directory), "result_names": names, "overwrite_policy": policy},
        transport,
        wait_timeout,
    )


def mechanical_workflow_status(request_id: str | None = None, timeout: float = 5.0) -> dict[str, Any]:
    if request_id:
        if not re.fullmatch(r"[0-9a-fA-F]{32}", request_id):
            return _error("request_id must be a 32-character hexadecimal queue id")
        response = read_response(request_id)
        parsed = _find_workflow_marker(response)
        if parsed is not None:
            response["workflow_result"] = parsed
        return response
    return mechanical_readiness(timeout=timeout)


def build_prestressed_modal_journal(
    project_path: str,
    geometry_path: str | None = None,
    include_baseline_modal: bool = True,
    overwrite_policy: str = "error",
) -> dict[str, Any]:
    """Create, but do not run, a Workbench journal for the analysis-system chain."""
    try:
        project = _resolve_output_path(project_path, overwrite_policy)
        geometry = _resolve_existing_file(geometry_path, "geometry_path") if geometry_path else None
    except Exception as exc:
        return _error(str(exc))

    WORKFLOW_JOB_DIR.mkdir(parents=True, exist_ok=True)
    journal_path = WORKFLOW_JOB_DIR / (
        f"prestressed_modal_chain_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.wbjn"
    )
    project_literal = repr(str(project))
    geometry_literal = repr(str(geometry)) if geometry else None
    lines = [
        'SetScriptVersion(Version="26.1.39")',
        'static_template = GetTemplate(TemplateName="Static Structural", Solver="ANSYS")',
        'static_system = static_template.CreateSystem()',
        'static_system.DisplayText = "Rotating Static"',
    ]
    if geometry_literal:
        lines.extend(
            [
                'static_geometry = static_system.GetContainer(ComponentName="Geometry")',
                f"static_geometry.SetFile(FilePath={geometry_literal})",
            ]
        )
    if include_baseline_modal:
        lines.extend(
            [
                'modal_template = GetTemplate(TemplateName="Modal", Solver="ANSYS")',
                'baseline_system = modal_template.CreateSystem(Position="Right", RelativeTo=static_system)',
                'baseline_system.DisplayText = "Modal Zero RPM"',
            ]
        )
        if geometry_literal:
            lines.extend(
                [
                    'baseline_geometry = baseline_system.GetContainer(ComponentName="Geometry")',
                    f"baseline_geometry.SetFile(FilePath={geometry_literal})",
                ]
            )
    lines.extend(
        [
            'prestress_template = GetTemplate(TemplateName="Modal", Solver="ANSYS")',
            'prestress_system = prestress_template.CreateSystem(Position="Right", RelativeTo=static_system)',
            'prestress_system.DisplayText = "Modal Prestressed"',
            'static_solution = static_system.GetComponent(Name="Solution")',
            'prestress_setup = prestress_system.GetComponent(Name="Setup")',
            'static_solution.TransferData(TargetComponent=prestress_setup)',
            f"Save(FilePath={project_literal}, Overwrite=True)",
        ]
    )
    journal_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "ok": True,
        "status": "created",
        "journal_path": str(journal_path),
        "project_path": str(project),
        "geometry_path": str(geometry) if geometry else None,
        "overwrite_policy": overwrite_policy,
    }


def workbench_create_prestressed_modal_chain(
    project_path: str,
    geometry_path: str | None = None,
    include_baseline_modal: bool = True,
    overwrite_policy: str = "error",
    launch: bool = True,
) -> dict[str, Any]:
    built = build_prestressed_modal_journal(
        project_path=project_path,
        geometry_path=geometry_path,
        include_baseline_modal=include_baseline_modal,
        overwrite_policy=overwrite_policy,
    )
    if not built.get("ok") or not launch:
        return built
    launched = launch_workbench_journal(built["journal_path"], cwd=str(Path(built["project_path"]).parent), batch=True)
    return {"ok": launched.get("status") != "error", "journal": built, "job": launched}
