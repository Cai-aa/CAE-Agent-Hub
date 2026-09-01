from __future__ import annotations

"""Session-aware Workbench and Mechanical control.

This module adds the missing Workbench Project Schematic layer on top of the
existing Mechanical queue/socket bridge.  It deliberately refuses to launch a
second Workbench while an unmanaged Workbench process is already running.

PyWorkbench and PyMechanical are imported lazily so the base MCP server can
still start and report a clear dependency error before the optional packages
are installed.
"""

from contextlib import contextmanager
from dataclasses import dataclass, field
import importlib.util
import json
import os
from pathlib import Path
import socket
import threading
import time
import uuid
from typing import Any

from tools.workbench_socket_timer import socket_timer_execute_python


_LOCK = threading.RLock()
_WORKBENCH_SESSIONS: dict[str, "WorkbenchSession"] = {}
_WORKBENCH_ENDPOINT_INDEX: dict[tuple[str, int, str], str] = {}
_MODEL_SESSIONS: dict[str, "ModelSession"] = {}
_MODEL_INDEX: dict[tuple[str, str], str] = {}
_MODEL_OPENING: set[tuple[str, str]] = set()
_MODEL_ENDPOINTS: dict[tuple[str, str], int] = {}


@dataclass
class WorkbenchSession:
    session_id: str
    client: Any
    port: int
    security: str
    owned: bool
    host: str = "localhost"
    launcher: Any | None = None
    process_id: int | None = None
    created_at: float = field(default_factory=time.time)


@dataclass
class ModelSession:
    model_session_id: str
    workbench_session_id: str
    system_name: str
    client: Any
    port: int
    transport_mode: str | None
    project_file: str | None = None
    created_at: float = field(default_factory=time.time)


def _reply(
    *,
    ok: bool,
    status: str,
    phase: str,
    data: dict[str, Any] | None = None,
    changed: bool = False,
    idempotent: bool = False,
    evidence: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "ok": ok,
        "status": status,
        "phase": phase,
        "changed": changed,
        "idempotent": idempotent,
        "data": data or {},
        "evidence": evidence or {},
        "warnings": warnings or [],
        "errors": errors or [],
    }


def _load_pyworkbench() -> tuple[Any, Any]:
    try:
        from ansys.workbench.core import connect_workbench
        from ansys.workbench.core.workbench_launcher import Launcher
    except Exception as exc:  # pragma: no cover - exact import error is environment specific
        raise RuntimeError(
            "ansys-workbench-core is required; install the MCP 'workbench' extra"
        ) from exc
    return connect_workbench, Launcher


def _load_pymechanical() -> Any:
    try:
        from ansys.mechanical.core import connect_to_mechanical
    except Exception as exc:  # pragma: no cover - exact import error is environment specific
        raise RuntimeError(
            "ansys-mechanical-core is required; install the MCP 'mechanical' extra"
        ) from exc
    return connect_to_mechanical


def _normalize_path(value: str | os.PathLike[str] | None) -> str | None:
    if not value:
        return None
    return os.path.normcase(os.path.abspath(os.path.normpath(os.fspath(value))))


def _process_inventory(strict: bool = False) -> list[dict[str, Any]]:
    try:
        import psutil
    except Exception as exc:
        if strict:
            raise RuntimeError(
                "Cannot enforce the single-Workbench gate because psutil is unavailable"
            ) from exc
        return []

    rows: list[dict[str, Any]] = []
    candidate_names = {"runwb2.exe", "ansysfww.exe", "ansyswbu.exe"}
    for proc in psutil.process_iter(["pid", "name"]):
        summary = proc.info
        name = str(summary.get("name") or "")
        if name.lower() not in candidate_names:
            continue
        try:
            info = proc.as_dict(
                attrs=["pid", "ppid", "name", "create_time", "cmdline"]
            )
            rows.append(
                {
                    "pid": int(info["pid"]),
                    "parent_pid": int(info.get("ppid") or 0),
                    "name": str(info.get("name") or name),
                    "created_at": float(info.get("create_time") or 0.0),
                    "command_line": [str(item) for item in (info.get("cmdline") or [])],
                }
            )
        except Exception as exc:
            if strict:
                raise RuntimeError(
                    f"Cannot inspect candidate ANSYS process {name} PID "
                    f"{summary.get('pid')}: {exc}"
                ) from exc
            continue
    rows.sort(key=lambda row: (row["created_at"], row["pid"]))
    return rows


def _workbench_processes(strict: bool = False) -> list[dict[str, Any]]:
    return [
        row
        for row in _process_inventory(strict=strict)
        if row["name"].lower() in {"runwb2.exe", "ansysfww.exe"}
    ]


@contextmanager
def _exclusive_launch_guard(timeout: float = 30.0):
    """Serialize launch preflight across MCP processes.

    The OS releases the byte-range lock if the MCP process dies.  The lock file
    contains no session data and lives outside the source checkout.
    """

    state_root = Path(
        os.environ.get("LOCALAPPDATA") or os.environ.get("TEMP") or os.getcwd()
    ) / "ansys-workbench-mcp"
    state_root.mkdir(parents=True, exist_ok=True)
    lock_path = state_root / "workbench-launch.lock"
    stream = lock_path.open("a+b")
    acquired = False
    deadline = time.time() + max(0.0, float(timeout))
    try:
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b"\0")
            stream.flush()
        while not acquired:
            try:
                stream.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:  # pragma: no cover - this MCP is deployed on Windows
                    import fcntl

                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except (OSError, BlockingIOError):
                if time.time() >= deadline:
                    raise RuntimeError("Timed out waiting for the global Workbench launch lock")
                time.sleep(0.1)
        yield
    finally:
        if acquired:
            try:
                stream.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:  # pragma: no cover - this MCP is deployed on Windows
                    import fcntl

                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass
        stream.close()


def _port_is_open(port: int, host: str = "127.0.0.1", timeout: float = 0.4) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def _run_workbench_json(client: Any, body: str) -> dict[str, Any]:
    script = "import json\n" + body.rstrip() + "\nwb_script_result=json.dumps(report)"
    result = client.run_script_string(script)
    if isinstance(result, dict):
        return result
    if not isinstance(result, str):
        raise RuntimeError(f"Unexpected Workbench result type: {type(result).__name__}")
    decoded = json.loads(result)
    if not isinstance(decoded, dict):
        raise RuntimeError("Workbench JSON result must be an object")
    return decoded


def _workbench_inventory(client: Any) -> dict[str, Any]:
    return _run_workbench_json(
        client,
        r'''
def _safe_attr(obj, name):
    try:
        value = getattr(obj, name)
        return None if value is None else str(value)
    except Exception:
        return None

def _has_component(system, component_name):
    try:
        return system.GetComponent(Name=component_name) is not None
    except Exception:
        return False

project_file = None
try:
    project_file = str(GetProjectFile())
except Exception:
    project_file = None

systems = []
for system in GetAllSystems():
    systems.append({
        "name": str(system.Name),
        "display_text": _safe_attr(system, "DisplayText"),
        "template_name": _safe_attr(system, "TemplateName"),
        "has_engineering_data": _has_component(system, "Engineering Data"),
        "has_geometry": _has_component(system, "Geometry"),
        "has_model": _has_component(system, "Model"),
        "has_setup": _has_component(system, "Setup"),
        "has_solution": _has_component(system, "Solution"),
    })

report = {
    "framework_version": str(GetFrameworkVersion()),
    "project_file": project_file,
    "systems": systems,
    "system_count": len(systems),
}
''',
    )


def _get_workbench_session(session_id: str) -> WorkbenchSession:
    try:
        return _WORKBENCH_SESSIONS[session_id]
    except KeyError as exc:
        raise KeyError(f"Unknown Workbench session: {session_id}") from exc


def _get_model_session(model_session_id: str) -> ModelSession:
    try:
        return _MODEL_SESSIONS[model_session_id]
    except KeyError as exc:
        raise KeyError(f"Unknown Mechanical model session: {model_session_id}") from exc


def workbench_session_status() -> dict[str, Any]:
    inventory = _process_inventory()
    workbench_processes = [
        row for row in inventory if row["name"].lower() in {"runwb2.exe", "ansysfww.exe"}
    ]
    sessions = [
        {
            "session_id": session.session_id,
            "port": session.port,
            "security": session.security,
            "owned": session.owned,
            "process_id": session.process_id,
            "port_open": _port_is_open(session.port),
        }
        for session in _WORKBENCH_SESSIONS.values()
    ]
    model_sessions = [
        {
            "model_session_id": session.model_session_id,
            "workbench_session_id": session.workbench_session_id,
            "system_name": session.system_name,
            "port": session.port,
            "port_open": _port_is_open(session.port),
        }
        for session in _MODEL_SESSIONS.values()
    ]
    pyworkbench_available = importlib.util.find_spec("ansys.workbench.core") is not None
    pymechanical_available = importlib.util.find_spec("ansys.mechanical.core") is not None
    unmanaged = bool(workbench_processes) and not bool(sessions)
    return _reply(
        ok=True,
        status="ready" if not unmanaged else "blocked_existing_workbench",
        phase="SESSION_STATUS",
        data={
            "process_inventory": inventory,
            "workbench_sessions": sessions,
            "model_sessions": model_sessions,
            "dependencies": {
                "ansys_workbench_core": pyworkbench_available,
                "ansys_mechanical_core": pymechanical_available,
            },
            "can_launch_without_duplicate": not bool(workbench_processes),
            "requires_attach_port": unmanaged,
        },
        warnings=(
            [
                "A Workbench process already exists but is not managed by this MCP. "
                "Attach to its StartServer port; launching another instance is refused."
            ]
            if unmanaged
            else []
        ),
    )


_BOOTSTRAP_MARKER = "WB_BOOTSTRAP_JSON:"


def _bootstrap_bridge_report(timeout: float) -> dict[str, Any]:
    code = r'''
import json
import os

report = {"ok": False, "phase": "SERVER_REUSE_OR_START_ONCE"}
try:
    try:
        server_port = int(GetServerPort())
    except Exception:
        server_port = 0
    start_called = False
    if server_port <= 0:
        StartServer()
        start_called = True
        server_port = int(GetServerPort())
    report.update({
        "ok": server_port > 0,
        "pid": int(os.getpid()),
        "server_port": server_port,
        "project_file": str(GetProjectFile()),
        "systems": [str(system.Name) for system in GetAllSystems()],
        "start_called": start_called,
    })
except Exception as exc:
    report["error"] = str(exc)
print("WB_BOOTSTRAP_JSON:" + json.dumps(report, ensure_ascii=True, sort_keys=True))
'''
    outer = socket_timer_execute_python(code, timeout=float(timeout))
    if not outer.get("ok"):
        raise RuntimeError(f"Workbench bridge request failed: {outer.get('error')}")
    response = outer.get("response") or {}
    if not response.get("ok"):
        raise RuntimeError(f"Workbench bridge rejected request: {response}")
    execution = response.get("execution") or {}
    if not execution.get("ok"):
        raise RuntimeError(f"Workbench bridge execution failed: {execution}")
    stdout = str(execution.get("stdout") or "")
    marker_lines = [
        line[len(_BOOTSTRAP_MARKER) :]
        for line in stdout.splitlines()
        if line.startswith(_BOOTSTRAP_MARKER)
    ]
    if len(marker_lines) != 1:
        raise RuntimeError("Workbench bootstrap did not return exactly one JSON marker")
    report = json.loads(marker_lines[0])
    if not isinstance(report, dict) or not report.get("ok"):
        raise RuntimeError(f"Workbench bootstrap report failed: {report}")
    return report


def workbench_bootstrap_current(
    expected_project_path: str | None = None,
    expected_system_name: str | None = None,
    security: str = "wnua",
    host: str = "localhost",
    bridge_timeout: float = 10.0,
) -> dict[str, Any]:
    """Attach to the one existing Workbench without launching another instance."""

    phase = "WORKBENCH_BOOTSTRAP"
    try:
        with _exclusive_launch_guard(timeout=float(bridge_timeout)):
            processes = _process_inventory(strict=True)
            runwb = [row for row in processes if row["name"].lower() == "runwb2.exe"]
            framework = [
                row for row in processes if row["name"].lower() == "ansysfww.exe"
            ]
            mechanical = [
                row for row in processes if row["name"].lower() == "ansyswbu.exe"
            ]
            if len(runwb) != 1 or len(framework) != 1:
                raise RuntimeError(
                    "Expected exactly one RunWB2.exe and one AnsysFWW.exe; "
                    f"observed {len(runwb)} and {len(framework)}"
                )
            if int(framework[0]["parent_pid"]) != int(runwb[0]["pid"]):
                raise RuntimeError("AnsysFWW.exe is not a child of the unique RunWB2.exe")
            if any(
                int(row["parent_pid"]) != int(framework[0]["pid"])
                for row in mechanical
            ):
                raise RuntimeError("AnsysWBU.exe exists outside the unique Workbench tree")

            bridge = _bootstrap_bridge_report(timeout=float(bridge_timeout))
            if int(bridge.get("pid") or 0) != int(framework[0]["pid"]):
                raise RuntimeError(
                    "Port 9885 bridge PID does not match the unique AnsysFWW.exe"
                )
            port = int(bridge.get("server_port") or 0)
            if port <= 0:
                raise RuntimeError("Workbench bootstrap returned an invalid server port")

            observed_project = _normalize_path(bridge.get("project_file"))
            expected_project = _normalize_path(expected_project_path)
            if expected_project is not None and observed_project != expected_project:
                raise RuntimeError(
                    f"Expected project {expected_project}, observed {observed_project}"
                )
            observed_systems = [str(item) for item in (bridge.get("systems") or [])]
            if expected_system_name is not None and observed_systems.count(
                str(expected_system_name)
            ) != 1:
                raise RuntimeError(
                    f"Expected one internal System {expected_system_name}, "
                    f"observed {observed_systems}"
                )

        attached = workbench_attach_current(port=port, security=security, host=host)
        if not attached.get("ok"):
            return attached
        session_id = str(attached["data"]["session_id"])
        inventory = attached["data"]["inventory"]
        inventory_project = _normalize_path(inventory.get("project_file"))
        inventory_systems = [
            str(item.get("name")) for item in (inventory.get("systems") or [])
        ]
        gate_errors: list[str] = []
        if expected_project is not None and inventory_project != expected_project:
            gate_errors.append(
                f"Attached project {inventory_project} does not equal {expected_project}"
            )
        if expected_system_name is not None and inventory_systems.count(
            str(expected_system_name)
        ) != 1:
            gate_errors.append(
                f"Attached systems {inventory_systems} do not uniquely contain "
                f"{expected_system_name}"
            )
        if gate_errors:
            workbench_session_disconnect(session_id)
            return _reply(
                ok=False,
                status="identity_gate_failed",
                phase=phase,
                data={"bridge": bridge, "inventory": inventory},
                evidence={"processes": processes},
                errors=gate_errors,
            )
        return _reply(
            ok=True,
            status=(
                "already_bootstrapped"
                if attached.get("status") == "already_attached"
                else "bootstrapped"
            ),
            phase=phase,
            changed=bool(bridge.get("start_called")),
            idempotent=attached.get("status") == "already_attached",
            data={
                "session_id": session_id,
                "bridge": bridge,
                "inventory": inventory,
            },
            evidence={"processes": processes, "security": security, "host": host},
        )
    except Exception as exc:
        return _reply(
            ok=False,
            status="bootstrap_failed",
            phase=phase,
            errors=[str(exc)],
        )


def workbench_attach_current(
    port: int,
    security: str = "mtls",
    host: str = "localhost",
) -> dict[str, Any]:
    phase = "WORKBENCH_ATTACH"
    if int(port) <= 0:
        return _reply(ok=False, status="invalid_port", phase=phase, errors=["port must be > 0"])
    endpoint_key = (str(host).lower(), int(port), str(security).lower())
    with _LOCK:
        existing_id = _WORKBENCH_ENDPOINT_INDEX.get(endpoint_key)
        existing = _WORKBENCH_SESSIONS.get(existing_id or "")
    if existing is not None:
        try:
            inventory = _workbench_inventory(existing.client)
            return _reply(
                ok=True,
                status="already_attached",
                phase=phase,
                idempotent=True,
                data={"session_id": existing.session_id, "inventory": inventory},
                evidence={"port": int(port), "host": host, "security": security},
            )
        except Exception:
            with _LOCK:
                _WORKBENCH_ENDPOINT_INDEX.pop(endpoint_key, None)
    try:
        connect_workbench, _ = _load_pyworkbench()
        client = connect_workbench(port=int(port), host=host, security=security)
        inventory = _workbench_inventory(client)
        session_id = "wb_" + uuid.uuid4().hex[:12]
        session = WorkbenchSession(
            session_id=session_id,
            client=client,
            port=int(port),
            security=security,
            owned=False,
            host=host,
        )
        with _LOCK:
            _WORKBENCH_SESSIONS[session_id] = session
            _WORKBENCH_ENDPOINT_INDEX[endpoint_key] = session_id
        return _reply(
            ok=True,
            status="attached",
            phase=phase,
            changed=False,
            data={"session_id": session_id, "inventory": inventory},
            evidence={"port": int(port), "host": host, "security": security},
        )
    except Exception as exc:
        return _reply(ok=False, status="attach_failed", phase=phase, errors=[str(exc)])


def workbench_launch_managed(
    version: str = "252",
    show_gui: bool = True,
    server_workdir: str | None = None,
    use_insecure_connection: bool = False,
) -> dict[str, Any]:
    phase = "WORKBENCH_LAUNCH"
    with _LOCK:
        try:
            with _exclusive_launch_guard():
                # Fail closed if process discovery is unavailable.  Checking
                # again while holding the cross-process lock closes the race
                # between two MCP servers launching simultaneously.
                processes = _workbench_processes(strict=True)
                if processes:
                    return _reply(
                        ok=False,
                        status="blocked_existing_workbench",
                        phase=phase,
                        data={"workbench_processes": processes},
                        errors=["Refusing to launch a second Workbench instance"],
                    )
                connect_workbench, launcher_class = _load_pyworkbench()
                launcher = launcher_class()
                port, security = launcher.launch(
                    version=version,
                    show_gui=bool(show_gui),
                    server_workdir=server_workdir,
                    port_to_use=-1,
                    use_insecure_connection=bool(use_insecure_connection),
                )
                if not port or int(port) <= 0:
                    raise RuntimeError("PyWorkbench did not return a valid server port")
                client = connect_workbench(port=int(port), host="localhost", security=security)
                inventory = _workbench_inventory(client)
                session_id = "wb_" + uuid.uuid4().hex[:12]
                process_id = getattr(launcher, "_process_id", None)
                session = WorkbenchSession(
                    session_id=session_id,
                    client=client,
                    port=int(port),
                    security=str(security),
                    owned=True,
                    launcher=launcher,
                    process_id=int(process_id) if process_id and int(process_id) > 0 else None,
                )
                _WORKBENCH_SESSIONS[session_id] = session
            return _reply(
                ok=True,
                status="launched",
                phase=phase,
                changed=True,
                data={"session_id": session_id, "inventory": inventory},
                evidence={
                    "port": int(port),
                    "security": str(security),
                    "process_id": session.process_id,
                    "version": version,
                },
            )
        except Exception as exc:
            return _reply(ok=False, status="launch_failed", phase=phase, errors=[str(exc)])


def workbench_project_inventory(session_id: str) -> dict[str, Any]:
    phase = "PROJECT_INVENTORY"
    try:
        session = _get_workbench_session(session_id)
        inventory = _workbench_inventory(session.client)
        return _reply(ok=True, status="inspected", phase=phase, data=inventory)
    except Exception as exc:
        return _reply(ok=False, status="inspection_failed", phase=phase, errors=[str(exc)])


def workbench_project_open(session_id: str, project_path: str) -> dict[str, Any]:
    phase = "PROJECT_OPEN"
    path = Path(project_path).expanduser().resolve()
    if path.suffix.lower() != ".wbpj" or not path.is_file():
        return _reply(
            ok=False,
            status="invalid_project",
            phase=phase,
            errors=[f"Workbench project does not exist: {path}"],
        )
    try:
        session = _get_workbench_session(session_id)
        before = _workbench_inventory(session.client)
        before_path = _normalize_path(before.get("project_file"))
        target_path = _normalize_path(str(path))
        if before_path == target_path:
            return _reply(
                ok=True,
                status="already_open",
                phase=phase,
                idempotent=True,
                data=before,
            )
        if int(before.get("system_count") or 0) > 0:
            return _reply(
                ok=False,
                status="blocked_active_project",
                phase=phase,
                data={"current": before, "requested_project": str(path)},
                errors=["A different non-empty Workbench project is already active"],
            )
        literal = json.dumps(str(path))
        session.client.run_script_string(f"Open(FilePath={literal})")
        after = _workbench_inventory(session.client)
        if _normalize_path(after.get("project_file")) != target_path:
            raise RuntimeError("Workbench opened a project whose identity does not match the target")
        return _reply(
            ok=True,
            status="opened",
            phase=phase,
            changed=True,
            data=after,
            evidence={"project_path": str(path)},
        )
    except Exception as exc:
        return _reply(ok=False, status="open_failed", phase=phase, errors=[str(exc)])


def workbench_project_save_as(
    session_id: str,
    target_path: str,
    overwrite: bool = False,
) -> dict[str, Any]:
    phase = "PROJECT_SAVE_AS"
    target = Path(target_path).expanduser().resolve()
    if target.suffix.lower() != ".wbpj":
        return _reply(
            ok=False,
            status="invalid_target",
            phase=phase,
            errors=["Save target must use the .wbpj extension"],
        )
    if target.exists() and not overwrite:
        return _reply(
            ok=False,
            status="target_exists",
            phase=phase,
            errors=[f"Refusing to overwrite existing project: {target}"],
        )
    try:
        session = _get_workbench_session(session_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        literal = json.dumps(str(target))
        flag = "True" if overwrite else "False"
        session.client.run_script_string(f"Save(FilePath={literal}, Overwrite={flag})")
        inventory = _workbench_inventory(session.client)
        if _normalize_path(inventory.get("project_file")) != _normalize_path(str(target)):
            raise RuntimeError("Workbench Save As identity check failed")
        return _reply(
            ok=True,
            status="saved",
            phase=phase,
            changed=True,
            data=inventory,
            evidence={"target_path": str(target), "overwrite": bool(overwrite)},
        )
    except Exception as exc:
        return _reply(ok=False, status="save_failed", phase=phase, errors=[str(exc)])


def _select_mechanical_system(inventory: dict[str, Any], system_name: str | None) -> dict[str, Any]:
    candidates = [
        item
        for item in inventory.get("systems", [])
        if item.get("has_model") and item.get("has_solution")
    ]
    if system_name:
        matches = [item for item in candidates if item.get("name") == system_name]
        if len(matches) != 1:
            raise RuntimeError(
                f"Mechanical system selector matched {len(matches)} systems; expected exactly one"
            )
        return matches[0]
    if len(candidates) != 1:
        names = [str(item.get("name")) for item in candidates]
        raise RuntimeError(
            f"Found {len(candidates)} Mechanical systems {names}; provide the exact internal system_name"
        )
    return candidates[0]


def _mechanical_state(client: Any) -> dict[str, Any]:
    code = r'''
import json
report = {"ok": False}
try:
    from Ansys.Mechanical.DataModel.Enums import DataModelObjectCategory

    try:
        _text_type = unicode
    except NameError:
        _text_type = str

    def _safe_text(value):
        if value is None:
            return None
        try:
            text = _text_type(value)
        except Exception:
            try:
                text = _text_type(repr(value))
            except Exception:
                return "<unprintable>"
        try:
            return text.encode("unicode_escape").decode("ascii")
        except Exception:
            try:
                return str(text)
            except Exception:
                return "<unprintable>"

    project = ExtAPI.DataModel.Project
    model = project.Model if project is not None else None
    bodies = []
    active_bodies = []
    analyses = []
    named_selections = []
    if model is not None:
        bodies = list(ExtAPI.DataModel.GetObjectsByType(DataModelObjectCategory.Body))
        for body in bodies:
            try:
                if not bool(body.Suppressed):
                    active_bodies.append(body)
            except Exception:
                active_bodies.append(body)
        analyses = list(model.Analyses)
        try:
            named_selection_group = getattr(model, "NamedSelections", None)
            if named_selection_group is not None:
                named_selections = list(getattr(named_selection_group, "Children", []) or [])
        except Exception:
            named_selections = []
        if not named_selections:
            try:
                named_selections = list(
                    ExtAPI.DataModel.GetObjectsByType(DataModelObjectCategory.NamedSelection)
                )
            except Exception:
                named_selections = []
    application_version = None
    try:
        application_version = _safe_text(ExtAPI.Application.ApplicationVersion)
    except Exception:
        pass
    report = {
        "ok": (
            project is not None
            and model is not None
            and len(active_bodies) > 0
            and len(analyses) > 0
        ),
        "application_version": application_version,
        "project_directory": _safe_text(getattr(project, "ProjectDirectory", "")) if project is not None else None,
        "model_present": model is not None,
        "body_count": len(bodies),
        "body_names": [_safe_text(getattr(body, "Name", "")) for body in bodies],
        "active_body_count": len(active_bodies),
        "active_body_names": [_safe_text(getattr(body, "Name", "")) for body in active_bodies],
        "analysis_count": len(analyses),
        "analyses": [{
            "name": _safe_text(getattr(analysis, "Name", "")),
            "analysis_type": _safe_text(getattr(analysis, "AnalysisType", "")),
            "working_directory": _safe_text(getattr(analysis, "WorkingDir", "")),
        } for analysis in analyses],
        "named_selection_count": len(named_selections),
        "named_selection_names": [
            _safe_text(getattr(named_selection, "Name", ""))
            for named_selection in named_selections
        ],
    }
except Exception as exc:
    try:
        error_text = _safe_text(exc)
    except Exception:
        error_text = "Mechanical state inspection failed"
    report = {"ok": False, "error": error_text}
json.dumps(report, ensure_ascii=True)
'''
    raw = client.run_python_script(code)
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        raise RuntimeError(f"Unexpected Mechanical result type: {type(raw).__name__}")
    decoded = json.loads(raw)
    if not isinstance(decoded, dict):
        raise RuntimeError("Mechanical state result must be an object")
    for key in ("body_names", "active_body_names", "named_selection_names"):
        decoded[key] = [_decode_mechanical_text(item) for item in decoded.get(key, [])]
    for key in ("application_version", "project_directory", "error"):
        if key in decoded:
            decoded[key] = _decode_mechanical_text(decoded.get(key))
    for analysis in decoded.get("analyses", []):
        if isinstance(analysis, dict):
            for key in ("name", "analysis_type", "working_directory"):
                analysis[key] = _decode_mechanical_text(analysis.get(key))
    return decoded


def _decode_mechanical_text(value: Any) -> str:
    """Decode ``unicode_escape`` text returned by Mechanical's IronPython layer."""

    if value is None:
        return ""
    text = str(value)
    if not any(marker in text for marker in ("\\\\", "\\u", "\\U", "\\x")):
        return text
    try:
        return bytes(text, "ascii").decode("unicode_escape")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


def _working_directory_matches_system(value: Any, system_name: str) -> bool:
    if not value:
        return False
    parts = [os.path.normcase(part) for part in Path(str(value)).parts]
    expected = os.path.normcase(system_name)
    mech = os.path.normcase("MECH")
    return any(
        parts[index] == expected and parts[index + 1] == mech
        for index in range(max(0, len(parts) - 1))
    )


def _exact_name_gate(observed: list[Any], expected: list[str] | None, label: str) -> list[str]:
    if expected is None:
        return []
    observed_names = sorted(str(item) for item in observed)
    expected_names = sorted(str(item) for item in expected)
    if observed_names == expected_names:
        return []
    return [f"Expected exact {label} {expected_names}, observed {observed_names}"]


def workbench_model_open(
    session_id: str,
    system_name: str | None = None,
    transport_mode: str | None = None,
    connect_timeout: float = 120.0,
    mechanical_port: int | None = None,
) -> dict[str, Any]:
    phase = "MODEL_OPEN"
    try:
        workbench_session = _get_workbench_session(session_id)
        inventory = _workbench_inventory(workbench_session.client)
        project_file = _normalize_path(inventory.get("project_file"))
        if not project_file:
            raise RuntimeError("Workbench has no saved project identity; refusing to open Model")
        system = _select_mechanical_system(inventory, system_name)
        exact_name = str(system["name"])
        index_key = (session_id, exact_name)
        with _LOCK:
            existing_id = _MODEL_INDEX.get(index_key)
            if existing_id and existing_id in _MODEL_SESSIONS:
                existing = _MODEL_SESSIONS[existing_id]
                state = _mechanical_state(existing.client)
                return _reply(
                    ok=bool(state.get("ok")),
                    status="already_open" if state.get("ok") else "stale_model_session",
                    phase=phase,
                    idempotent=True,
                    data={"model_session_id": existing_id, "system": system, "state": state},
                    evidence={"mechanical_port": existing.port},
                )
            if index_key in _MODEL_OPENING:
                return _reply(
                    ok=False,
                    status="model_open_in_progress",
                    phase=phase,
                    idempotent=True,
                    data={"system": system},
                    errors=["Another request is already opening this exact Workbench Model"],
                )
            _MODEL_OPENING.add(index_key)

        try:
            # PyWorkbench 0.14 has a known risky path when a non-zero port is
            # passed.  Let Workbench allocate a dynamic port and use the
            # returned value as the authoritative endpoint.
            endpoint_key = (project_file, exact_name)
            with _LOCK:
                cached_port = _MODEL_ENDPOINTS.get(endpoint_key)
                if mechanical_port is not None:
                    requested_port = int(mechanical_port)
                    if requested_port <= 0:
                        raise RuntimeError("mechanical_port must be > 0")
                    if cached_port is not None and int(cached_port) != requested_port:
                        raise RuntimeError(
                            f"Mechanical endpoint conflict: cached {cached_port}, "
                            f"requested {requested_port}"
                        )
                    _MODEL_ENDPOINTS[endpoint_key] = requested_port
                    cached_port = requested_port
            if cached_port is None:
                port = int(
                    workbench_session.client.start_mechanical_server(
                        system_name=exact_name, port=0
                    )
                )
                if port <= 0:
                    raise RuntimeError(
                        "Workbench did not return a valid Mechanical server port"
                    )
                with _LOCK:
                    _MODEL_ENDPOINTS[endpoint_key] = port
            else:
                port = int(cached_port)
            if port <= 0:
                raise RuntimeError("Workbench did not return a valid Mechanical server port")
            connect_to_mechanical = _load_pymechanical()
            mechanical = connect_to_mechanical(
                ip="127.0.0.1",
                port=port,
                connect_timeout=float(connect_timeout),
                clear_on_connect=False,
                cleanup_on_exit=False,
                keep_connection_alive=True,
                transport_mode=transport_mode,
            )
            state = _mechanical_state(mechanical)
            if not state.get("ok"):
                raise RuntimeError(f"Mechanical Model gate failed: {state}")
            model_session_id = "model_" + uuid.uuid4().hex[:12]
            model_session = ModelSession(
                model_session_id=model_session_id,
                workbench_session_id=session_id,
                system_name=exact_name,
                client=mechanical,
                port=port,
                transport_mode=transport_mode,
                project_file=project_file,
            )
            with _LOCK:
                _MODEL_SESSIONS[model_session_id] = model_session
                _MODEL_INDEX[index_key] = model_session_id
        finally:
            with _LOCK:
                _MODEL_OPENING.discard(index_key)
        return _reply(
            ok=True,
            status="model_ready",
            phase=phase,
            changed=True,
            data={"model_session_id": model_session_id, "system": system, "state": state},
            evidence={"mechanical_port": port, "transport_mode": transport_mode},
        )
    except Exception as exc:
        return _reply(ok=False, status="model_open_failed", phase=phase, errors=[str(exc)])


def workbench_model_state(
    model_session_id: str,
    expected_body_count: int | None = None,
    expected_analysis_count: int | None = None,
    expected_project_path: str | None = None,
    expected_system_name: str | None = None,
    expected_body_names: list[str] | None = None,
    expected_analysis_names: list[str] | None = None,
    expected_analysis_types: list[str] | None = None,
) -> dict[str, Any]:
    phase = "MODEL_STATE"
    try:
        session = _get_model_session(model_session_id)
        state = _mechanical_state(session.client)
        gate_errors: list[str] = []
        parent = _get_workbench_session(session.workbench_session_id)
        workbench_inventory = _workbench_inventory(parent.client)
        current_project = _normalize_path(workbench_inventory.get("project_file"))
        recorded_project = _normalize_path(session.project_file)
        requested_project = _normalize_path(expected_project_path)
        if not current_project or current_project != recorded_project:
            gate_errors.append(
                f"Workbench project identity changed: expected {recorded_project}, observed {current_project}"
            )
        if requested_project is not None and current_project != requested_project:
            gate_errors.append(
                f"Expected project {requested_project}, observed {current_project}"
            )

        exact_systems = [
            item
            for item in workbench_inventory.get("systems", [])
            if str(item.get("name")) == session.system_name and item.get("has_model")
        ]
        if len(exact_systems) != 1:
            gate_errors.append(
                f"Expected exact Workbench system {session.system_name}, matched {len(exact_systems)}"
            )
        if expected_system_name is not None and expected_system_name != session.system_name:
            gate_errors.append(
                f"Expected system {expected_system_name}, model session is {session.system_name}"
            )

        working_directories = [
            analysis.get("working_directory") for analysis in state.get("analyses", [])
        ]
        if not any(
            _working_directory_matches_system(path, session.system_name)
            for path in working_directories
        ):
            gate_errors.append(
                f"No Mechanical analysis WorkingDir maps to exact Workbench system {session.system_name}"
            )

        active_body_count = int(state.get("active_body_count", state.get("body_count", -1)))
        active_body_names = state.get("active_body_names", state.get("body_names", []))
        if expected_body_count is not None and active_body_count != int(
            expected_body_count
        ):
            gate_errors.append(
                f"Expected {expected_body_count} active bodies, observed {active_body_count}"
            )
        if expected_analysis_count is not None and int(state.get("analysis_count", -1)) != int(
            expected_analysis_count
        ):
            gate_errors.append(
                f"Expected {expected_analysis_count} analyses, observed {state.get('analysis_count')}"
            )
        gate_errors.extend(_exact_name_gate(active_body_names, expected_body_names, "active bodies"))
        gate_errors.extend(
            _exact_name_gate(
                [item.get("name") for item in state.get("analyses", [])],
                expected_analysis_names,
                "analyses",
            )
        )
        gate_errors.extend(
            _exact_name_gate(
                [item.get("analysis_type") for item in state.get("analyses", [])],
                expected_analysis_types,
                "analysis types",
            )
        )
        ok = bool(state.get("ok")) and not gate_errors
        return _reply(
            ok=ok,
            status="model_ready" if ok else "model_gate_failed",
            phase=phase,
            data={
                "model_session_id": model_session_id,
                "state": state,
                "workbench_inventory": workbench_inventory,
            },
            evidence={
                "mechanical_port": session.port,
                "system_name": session.system_name,
                "project_file": current_project,
            },
            errors=gate_errors,
        )
    except Exception as exc:
        return _reply(ok=False, status="state_failed", phase=phase, errors=[str(exc)])


def workbench_model_execute_python(model_session_id: str, code: str) -> dict[str, Any]:
    phase = "MODEL_EXECUTE_PYTHON"
    if not code or not code.strip():
        return _reply(ok=False, status="empty_code", phase=phase, errors=["code is empty"])
    try:
        session = _get_model_session(model_session_id)
        gate = workbench_model_state(
            model_session_id=model_session_id,
            expected_project_path=session.project_file,
            expected_system_name=session.system_name,
        )
        if not gate.get("ok"):
            return _reply(
                ok=False,
                status="identity_gate_failed",
                phase=phase,
                data={"model_session_id": model_session_id, "gate": gate},
                evidence={"mechanical_port": session.port},
                errors=list(gate.get("errors") or ["Model identity gate failed"]),
            )
        result = session.client.run_python_script(code)
        return _reply(
            ok=True,
            status="executed",
            phase=phase,
            changed=True,
            data={"model_session_id": model_session_id, "result": result},
            evidence={"mechanical_port": session.port, "system_name": session.system_name},
        )
    except Exception as exc:
        return _reply(ok=False, status="execution_failed", phase=phase, errors=[str(exc)])


def _close_client_channel_only(client: Any, *, workbench: bool) -> str:
    """Close only the client transport, never an ANSYS application process."""

    attribute_names = ("channel",) if workbench else ("_channel", "channel")
    for attribute_name in attribute_names:
        channel = getattr(client, attribute_name, None)
        close = getattr(channel, "close", None)
        if callable(close):
            close()
            try:
                setattr(client, attribute_name, None)
            except Exception:
                pass
            if workbench:
                for name in ("stub", "_stub"):
                    if hasattr(client, name):
                        try:
                            setattr(client, name, None)
                        except Exception:
                            pass
            return f"closed_{attribute_name}"
    return "registry_only_no_channel_api"


def workbench_session_disconnect(session_id: str) -> dict[str, Any]:
    """Disconnect the PyWorkbench client without resetting or closing Workbench.

    Mechanical model clients are intentionally not ``exit()``-ed because
    PyMechanical's exit operation can terminate the Workbench-managed
    Mechanical process.  The caller must explicitly own any later termination.
    """

    phase = "SESSION_DISCONNECT"
    model_detach_modes: dict[str, str] = {}
    try:
        with _LOCK:
            session = _get_workbench_session(session_id)
            child_ids = [
                model_id
                for model_id, model_session in _MODEL_SESSIONS.items()
                if model_session.workbench_session_id == session_id
            ]
            for model_id in child_ids:
                model_session = _MODEL_SESSIONS.pop(model_id)
                _MODEL_INDEX.pop((session_id, model_session.system_name), None)
                model_detach_modes[model_id] = _close_client_channel_only(
                    model_session.client, workbench=False
                )
            _WORKBENCH_SESSIONS.pop(session_id, None)
            _WORKBENCH_ENDPOINT_INDEX.pop(
                (str(session.host).lower(), int(session.port), str(session.security).lower()),
                None,
            )
        workbench_detach_mode = _close_client_channel_only(session.client, workbench=True)
        return _reply(
            ok=True,
            status="disconnected",
            phase=phase,
            changed=True,
            data={
                "session_id": session_id,
                "detached_model_sessions": child_ids,
                "workbench_detach_mode": workbench_detach_mode,
                "model_detach_modes": model_detach_modes,
            },
            warnings=[
                "Only MCP client channels were detached; Workbench and Mechanical processes were left running"
            ],
        )
    except Exception as exc:
        return _reply(ok=False, status="disconnect_failed", phase=phase, errors=[str(exc)])
