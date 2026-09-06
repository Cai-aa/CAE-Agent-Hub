from __future__ import annotations

import base64
import contextlib
import csv
import json
import math
import os
import re
import tempfile
from collections.abc import Callable, Mapping
from io import StringIO
from pathlib import Path
from typing import Any

from aedt_target import AedtTarget


class CapabilityError(ValueError):
    pass


APPLICATION_TYPES = (
    "Hfss",
    "Maxwell2d",
    "Maxwell3d",
    "Q3d",
    "Q2d",
    "Icepak",
    "Circuit",
    "TwinBuilder",
    "Mechanical",
    "Emit",
    "RMXprt",
    "Hfss3dLayout",
)

OFFICIAL_BACKEND_COMMANDS = {
    "connect_to_aedt",
    "disconnect_from_aedt",
    "get_pyaedt_logs",
    "run_python_script",
    "run_python_code",
    "list_designs",
    "list_projects",
    "open_project",
    "save_project",
    "create_design",
    "validate_design",
    "analyze_design",
    "export_results",
    "screenshot",
    "export_config",
    "clear_aedt",
    "get_model_info",
}


def _required_text(arguments: Mapping[str, Any], name: str) -> str:
    value = arguments.get(name)
    if not isinstance(value, str) or not value.strip():
        raise CapabilityError(f"{name} must be a non-empty string")
    return value.strip()


def _optional_text(arguments: Mapping[str, Any], name: str, default: str = "") -> str:
    value = arguments.get(name, default)
    if value is None:
        return default
    if not isinstance(value, str):
        raise CapabilityError(f"{name} must be a string or null")
    return value.strip()


def _boolean(arguments: Mapping[str, Any], name: str, default: bool) -> bool:
    value = arguments.get(name, default)
    if type(value) is not bool:
        raise CapabilityError(f"{name} must be a boolean")
    return value


def _positive_int(arguments: Mapping[str, Any], name: str) -> int | None:
    value = arguments.get(name)
    if value is None:
        return None
    if type(value) is not int or value <= 0:
        raise CapabilityError(f"{name} must be a positive integer or null")
    return value


def _name(value: Any) -> str | None:
    if value is None:
        return None
    getter = getattr(value, "GetName", None)
    if callable(getter):
        return str(getter())
    raw_name = getattr(value, "name", None)
    return str(raw_name) if raw_name is not None else None


def json_safe(value: Any) -> Any:
    if value is None or type(value) in {bool, int, str}:
        return value
    if type(value) is float:
        return value if math.isfinite(value) else str(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    return str(value)


def _is_icepak(app: Any) -> bool:
    return str(getattr(app, "design_type", "")).strip().lower() == "icepak"


def _icepak_result_directories(app: Any) -> list[Path]:
    raw_results = getattr(app, "results_directory", None)
    if not raw_results:
        return []
    root = Path(str(raw_results)).expanduser()
    design_name = str(getattr(app, "design_name", "")).strip()
    candidates = [root / f"{design_name}.results", root] if design_name else [root]
    return [candidate for candidate in candidates if candidate.is_dir()]


def _parse_icepak_residual_history(path: Path) -> list[dict[str, float | int]]:
    history: list[dict[str, float | int]] = []
    residual_markers = {
        "Continuity",
        "XVelocity",
        "YVelocity",
        "ZVelocity",
        "Energy",
    }
    number = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = re.match(rf"^\s*({number})\s+(.*)$", line)
        if not match:
            continue
        values = {
            name.strip().replace(" ", ""): float(value)
            for name, value in re.findall(rf"([A-Za-z][A-Za-z0-9 _-]*)\(({number})\)", match.group(2))
        }
        if not residual_markers.intersection(values):
            continue
        iteration_value = float(match.group(1))
        iteration: float | int = (
            int(iteration_value) if iteration_value.is_integer() else iteration_value
        )
        history.append({"Iteration": iteration, **values})
    return history


def _export_icepak_convergence(app: Any, output: Path) -> dict[str, Any]:
    candidates: list[tuple[int, float, Path, list[dict[str, float | int]]]] = []
    for root in _icepak_result_directories(app):
        for source in root.rglob("*.sd"):
            if not source.is_file():
                continue
            history = _parse_icepak_residual_history(source)
            if history:
                candidates.append((len(history), source.stat().st_mtime, source, history))
    if not candidates:
        raise CapabilityError(
            "Icepak residual monitor history was not found in the solved results directory"
        )
    _, _, source, history = max(candidates, key=lambda item: (item[0], item[1]))
    preferred = [
        "Continuity",
        "XVelocity",
        "YVelocity",
        "ZVelocity",
        "Energy",
    ]
    available = {key for row in history for key in row if key != "Iteration"}
    columns = [name for name in preferred if name in available]
    columns.extend(sorted(available - set(columns)))
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=["Iteration", *columns, "SourceFile"],
        )
        writer.writeheader()
        for row in history:
            writer.writerow({**row, "SourceFile": str(source)})
    return {
        "path": str(output),
        "format": "csv",
        "source": "icepak_monitor_history",
        "source_file": str(source),
        "row_count": len(history),
        "columns": ["Iteration", *columns],
    }


def _profile_mesh_value(content: str, label: str) -> int | None:
    escaped_label = re.escape(label)
    for prefix in ("Total ", ""):
        patterns = (
            rf"\\?'(?:{prefix}){escaped_label}\\?',\s*(\d+)",
            rf"\b(?:{prefix}){escaped_label}\s*:\s*(\d+)",
        )
        for pattern in patterns:
            values = re.findall(pattern, content, flags=re.IGNORECASE)
            if values:
                return int(values[-1])
    return None


def _export_icepak_mesh_stats(app: Any, setup_name: str, output: Path) -> dict[str, Any]:
    output.parent.mkdir(parents=True, exist_ok=True)
    profile_path = output.with_name(f"{output.stem}_source_profile.prof")
    profile_result = app.export_profile(
        setup=setup_name,
        output_file=str(profile_path),
    )
    if isinstance(profile_result, (str, Path)) and Path(profile_result).is_file():
        profile_path = Path(profile_result)
    if not profile_path.is_file():
        raise CapabilityError("Icepak profile export did not create a readable file")
    content = profile_path.read_text(encoding="utf-8", errors="replace")
    statistics = {
        label.lower(): _profile_mesh_value(content, label)
        for label in ("Nodes", "Faces", "Cells")
    }
    if any(value is None for value in statistics.values()):
        raise CapabilityError(
            "Icepak profile did not contain total Nodes, Faces, and Cells"
        )
    with output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            ["Setup", "Nodes", "Faces", "Cells", "NormalCompletion", "SourceProfile"]
        )
        writer.writerow(
            [
                setup_name,
                statistics["nodes"],
                statistics["faces"],
                statistics["cells"],
                "Normal Completion" in content,
                str(profile_path),
            ]
        )
    return {
        "path": str(output),
        "format": "csv",
        "source": "icepak_solution_profile",
        "source_file": str(profile_path),
        "statistics": statistics,
        "normal_completion": "Normal Completion" in content,
    }


def _default_app_resolver(
    *, desktop: Any, project_name: str | None, design_name: str | None
) -> Any:
    from ansys.aedt.core import get_pyaedt_app

    return get_pyaedt_app(
        project_name=project_name,
        design_name=design_name,
        desktop=desktop,
    )


def _default_app_class_resolver(app_type: str) -> Any | None:
    import ansys.aedt.core as aedt

    app_map = {
        "Hfss": aedt.Hfss,
        "Maxwell2d": aedt.Maxwell2d,
        "Maxwell3d": aedt.Maxwell3d,
        "Q3d": aedt.Q3d,
        "Q2d": aedt.Q2d,
        "Icepak": aedt.Icepak,
        "Circuit": aedt.Circuit,
        "TwinBuilder": aedt.TwinBuilder,
        "Mechanical": aedt.Mechanical,
        "Emit": aedt.Emit,
        "RMXprt": getattr(aedt, "Rmxprt", None),
        "Hfss3dLayout": aedt.Hfss3dLayout,
    }
    return app_map.get(app_type)


def _default_log_file_resolver() -> str | None:
    try:
        from ansys.aedt.core.aedt_logger import pyaedt_logger

        raw_logger = getattr(pyaedt_logger, "logger", None)
        for handler in getattr(raw_logger, "handlers", []):
            candidate = getattr(handler, "baseFilename", None)
            if candidate and Path(candidate).is_file():
                return str(Path(candidate).resolve())
        candidate = getattr(pyaedt_logger, "filename", None)
        if candidate and Path(candidate).is_file():
            return str(Path(candidate).resolve())
    except Exception:  # noqa: BLE001,S110 - PyAEDT logger internals vary by release
        pass
    try:
        from ansys.aedt.core import settings

        configured = getattr(settings, "logger_file_path", None)
        if configured:
            candidate = Path(configured).expanduser()
            if candidate.is_file():
                return str(candidate.resolve())
            if candidate.is_dir():
                logs = sorted(
                    candidate.glob("pyaedt*.log"),
                    key=lambda item: item.stat().st_mtime,
                    reverse=True,
                )
                if logs:
                    return str(logs[0].resolve())
    except Exception:  # noqa: BLE001,S110 - settings fallback is optional
        pass
    return None


def _open_viewer(path: Path) -> str | None:
    try:
        if hasattr(os, "startfile"):
            os.startfile(path)  # type: ignore[attr-defined]
            return None
    except Exception as exc:  # noqa: BLE001 - report platform viewer failures
        return f"Viewer launch failed: {exc}"
    return "Viewer launch is not supported on this platform."


class OfficialCapabilities:
    def __init__(
        self,
        *,
        app_resolver: Callable[..., Any] | None = None,
        app_class_resolver: Callable[[str], Any | None] | None = None,
        log_file_resolver: Callable[[], str | None] | None = None,
    ) -> None:
        self._app_resolver = app_resolver or _default_app_resolver
        self._app_class_resolver = app_class_resolver or _default_app_class_resolver
        self._log_file_resolver = log_file_resolver or _default_log_file_resolver
        self._exec_globals: dict[str, Any] = {}
        self._apps: list[Any] = []

    def clear_local_state(self) -> None:
        self._exec_globals.clear()
        self._apps.clear()

    def execute(
        self,
        command: str,
        *,
        desktop: Any,
        target: AedtTarget,
        arguments: Mapping[str, Any],
        connection_kwargs: Mapping[str, Any],
    ) -> dict[str, Any]:
        if command not in OFFICIAL_BACKEND_COMMANDS:
            raise CapabilityError(f"unsupported official command: {command}")
        handler = getattr(self, f"_{command}")
        result = handler(desktop, target, arguments, connection_kwargs)
        safe = json_safe(result)
        if not isinstance(safe, dict):
            raise TypeError(f"AEDT command {command} returned a non-object result")
        return safe

    def _resolve_app(
        self, desktop: Any, project_name: str | None, design_name: str | None
    ) -> Any:
        app = self._app_resolver(
            desktop=desktop,
            project_name=project_name,
            design_name=design_name,
        )
        if app is None:
            raise CapabilityError("AEDT has no active design for this operation")
        return app

    @staticmethod
    def _target(target: AedtTarget) -> dict[str, Any]:
        return {"kind": target.kind, "value": target.value}

    def _connect_to_aedt(self, desktop, target, arguments, connection_kwargs):
        project_name = _optional_text(arguments, "project_name") or None
        design_name = _optional_text(arguments, "design_name") or None
        project = desktop.active_project()
        design = None
        try:
            design = desktop.active_design(project)
        except (IndexError, TypeError):
            pass
        result = {
            "target": self._target(target),
            "connected": True,
            "aedt_version": getattr(desktop, "aedt_version_id", None),
            "pid": getattr(desktop, "aedt_process_id", None),
            "port": getattr(desktop, "port", None),
            "grpc": bool(getattr(desktop, "is_grpc_api", target.kind == "port")),
            "active_project": _name(project),
            "active_design": _name(design),
        }
        if design_name:
            app = self._resolve_app(desktop, project_name, design_name)
            result.update(
                active_project=getattr(app, "project_name", project_name),
                active_design=getattr(app, "design_name", design_name),
                design_type=getattr(app, "design_type", None),
            )
        return result

    def _disconnect_from_aedt(self, desktop, target, arguments, connection_kwargs):
        close_projects = _boolean(arguments, "close_projects", False)
        close_desktop = _boolean(arguments, "close_desktop", False)
        released = bool(
            desktop.release_desktop(
                close_projects=close_projects,
                close_on_exit=close_desktop,
            )
        )
        self.clear_local_state()
        return {
            "target": self._target(target),
            "disconnected": True,
            "release_result": released,
            "closed_projects": close_projects,
            "closed_desktop": close_desktop,
        }

    def _list_projects(self, desktop, target, arguments, connection_kwargs):
        projects = [str(item) for item in desktop.project_list]
        return {
            "target": self._target(target),
            "open_projects": projects,
            "count": len(projects),
        }

    def _list_designs(self, desktop, target, arguments, connection_kwargs):
        requested = _optional_text(arguments, "project_name") or None
        projects = (
            [requested] if requested else [str(item) for item in desktop.project_list]
        )
        entries = []
        for project in projects:
            designs = [str(item) for item in desktop.design_list(project)]
            entries.append(
                {"project": project, "designs": designs, "count": len(designs)}
            )
        result = {
            "target": self._target(target),
            "projects": entries,
            "project_count": len(entries),
            "design_count": sum(item["count"] for item in entries),
        }
        if requested and entries:
            result.update(entries[0])
        return result

    def _open_project(self, desktop, target, arguments, connection_kwargs):
        path = Path(_required_text(arguments, "project_path")).expanduser().resolve()
        if not path.is_file():
            raise CapabilityError(f"project file not found: {path}")
        design_name = _optional_text(arguments, "design_name") or None
        loaded = desktop.load_project(str(path), design_name=design_name)
        return {
            "target": self._target(target),
            "opened": bool(loaded) if loaded is not None else True,
            "project_path": str(path),
            "active_design": design_name,
        }

    def _save_project(self, desktop, target, arguments, connection_kwargs):
        project_name = _optional_text(arguments, "project_name") or None
        if project_name is None:
            project_name = _name(desktop.active_project())
        if not project_name:
            raise CapabilityError("AEDT has no active project to save")
        save_as = (
            _optional_text(arguments, "save_as")
            or _optional_text(arguments, "path")
            or None
        )
        saved = bool(desktop.save_project(project_name, save_as))
        return {
            "target": self._target(target),
            "project_name": project_name,
            "path": save_as,
            "saved": saved,
        }

    def _clear_aedt(self, desktop, target, arguments, connection_kwargs):
        close_projects = _boolean(arguments, "close_projects", True)
        projects = [str(item) for item in desktop.project_list]
        closed = []
        if close_projects:
            for project in projects:
                desktop.odesktop.CloseProject(project)
                closed.append(project)
            self._apps.clear()
        clear_messages = getattr(desktop, "clear_messages", None)
        if callable(clear_messages):
            clear_messages()
        return {
            "target": self._target(target),
            "cleared": True,
            "closed_projects": closed,
            "project_count": len(closed),
        }

    def _get_model_info(self, desktop, target, arguments, connection_kwargs):
        requested_design = _optional_text(arguments, "design_name") or None
        project = desktop.active_project()
        design = None
        try:
            design = desktop.active_design(project)
        except (IndexError, TypeError):
            pass
        project_name = _name(project)
        design_name = requested_design or _name(design)
        design_type = None
        if design_name:
            try:
                design_type = desktop.design_type(design_name=design_name)
            except TypeError:
                design_type = desktop.design_type(project_name, design_name)
        project_path = None
        try:
            value = desktop.project_path
            project_path = value() if callable(value) else value
        except (AttributeError, TypeError):
            pass
        return {
            "target": self._target(target),
            "project_name": project_name,
            "design_name": design_name,
            "design_type": design_type,
            "project_path": project_path,
        }

    def _get_pyaedt_logs(self, desktop, target, arguments, connection_kwargs):
        tail_lines = arguments.get("tail_lines", 200)
        max_chars = arguments.get("max_chars", 40000)
        contains = _optional_text(arguments, "contains") or None
        if type(tail_lines) is not int or tail_lines <= 0:
            raise CapabilityError("tail_lines must be a positive integer")
        if type(max_chars) is not int or max_chars <= 0:
            raise CapabilityError("max_chars must be a positive integer")
        safe_tail = min(tail_lines, 5000)
        safe_chars = min(max_chars, 200000)
        log_file = self._log_file_resolver()
        payload = {
            "target": self._target(target),
            "log_file": log_file,
            "contains": contains,
            "total_lines": 0,
            "matched_lines": 0,
            "returned_lines": 0,
            "truncated": False,
            "logs": "",
        }
        if log_file and Path(log_file).is_file():
            all_lines = (
                Path(log_file)
                .read_text(encoding="utf-8", errors="replace")
                .splitlines(keepends=True)
            )
            filtered = all_lines
            if contains:
                token = contains.lower()
                filtered = [line for line in all_lines if token in line.lower()]
            selected = filtered[-safe_tail:]
            log_text = "".join(selected)
            if len(log_text) > safe_chars:
                log_text = log_text[-safe_chars:]
                payload["truncated"] = True
            payload.update(
                total_lines=len(all_lines),
                matched_lines=len(filtered),
                returned_lines=len(selected),
                logs=log_text,
            )
        else:
            payload["file_log_error"] = "PyAEDT log file could not be resolved."

        try:
            project = desktop.active_project()
            design = desktop.active_design(project)
            project_name = _name(project) or ""
            design_name = _name(design) or ""
            payload["native_messages"] = {
                "project": project_name or None,
                "design": design_name or None,
                "info_messages": list(
                    desktop.odesktop.GetMessages(project_name, design_name, 0)
                ),
                "error_messages": list(
                    desktop.odesktop.GetMessages(project_name, design_name, 2)
                ),
            }
        except Exception as exc:  # noqa: BLE001 - AEDT native message APIs vary
            payload["native_messages_error"] = str(exc)
        return payload

    def _run_python_script(self, desktop, target, arguments, connection_kwargs):
        script = Path(_required_text(arguments, "script_path")).expanduser().resolve()
        if not script.is_file():
            raise CapabilityError(f"script file not found: {script}")
        result = desktop.odesktop.RunScript(str(script))
        return {
            "target": self._target(target),
            "executed": True,
            "script_path": str(script),
            "result": result,
        }

    def _run_python_code(self, desktop, target, arguments, connection_kwargs):
        code = _required_text(arguments, "code")
        self._exec_globals.update(
            {
                "desktop": desktop,
                "odesktop": desktop.odesktop,
                "aedt_port": getattr(desktop, "port", None),
            }
        )
        self._exec_globals.pop("result", None)
        stdout = StringIO()
        stderr = StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exec(code, self._exec_globals)  # noqa: S102  # nosec B102 - explicit tool contract
        return {
            "target": self._target(target),
            "executed": True,
            "result": self._exec_globals.get("result"),
            "stdout": stdout.getvalue(),
            "stderr": stderr.getvalue(),
        }

    def _create_design(self, desktop, target, arguments, connection_kwargs):
        app_type = _required_text(arguments, "app_type")
        if app_type not in APPLICATION_TYPES:
            raise CapabilityError(
                f"unsupported application type: {app_type}; supported: "
                + ", ".join(APPLICATION_TYPES)
            )
        app_class = self._app_class_resolver(app_type)
        if app_class is None:
            raise CapabilityError(f"PyAEDT class is unavailable for {app_type}")
        design_name = _optional_text(arguments, "design_name") or None
        project_name = _optional_text(arguments, "project_name") or None
        solution_type = _optional_text(arguments, "solution_type") or None
        kwargs = dict(connection_kwargs)
        if design_name:
            kwargs["design"] = design_name
        if project_name:
            kwargs["project"] = project_name
        if solution_type:
            hfss_map = {
                "DrivenModal": "Modal",
                "DrivenTerminal": "Terminal",
            }
            kwargs["solution_type"] = (
                hfss_map.get(solution_type, solution_type)
                if app_type == "Hfss"
                else solution_type
            )
        app = app_class(**kwargs)
        self._apps.append(app)
        return {
            "target": self._target(target),
            "created": True,
            "app_type": app_type,
            "project_name": getattr(app, "project_name", project_name),
            "design_name": getattr(app, "design_name", design_name),
            "solution_type": getattr(app, "solution_type", solution_type),
        }

    @staticmethod
    def _validate_app(app):
        with tempfile.TemporaryDirectory() as temporary_directory:
            log_file = Path(temporary_directory) / "validation.log"
            valid = bool(app.validate_simple(log_file=log_file))
            details = None
            if not valid:
                details = (
                    log_file.read_text(encoding="utf-8", errors="replace")
                    if log_file.is_file()
                    else "Design validation failed."
                )
            return valid, details

    def _validate_design(self, desktop, target, arguments, connection_kwargs):
        project_name = _optional_text(arguments, "project_name") or None
        design_name = _optional_text(arguments, "design_name") or None
        app = self._resolve_app(desktop, project_name, design_name)
        valid, details = self._validate_app(app)
        return {
            "target": self._target(target),
            "valid": valid,
            "project_name": getattr(app, "project_name", project_name),
            "design_name": getattr(app, "design_name", design_name),
            "details": details,
        }

    def _analyze_design(self, desktop, target, arguments, connection_kwargs):
        setup_name = _optional_text(arguments, "setup_name") or None
        project_name = _optional_text(arguments, "project_name") or None
        design_name = _optional_text(arguments, "design_name") or None
        analyze_all = _boolean(arguments, "analyze_all_designs", False)
        if analyze_all:
            if setup_name:
                raise CapabilityError(
                    "setup_name cannot be used when analyze_all_designs is true"
                )
            completed = bool(
                desktop.analyze_all(project=project_name, design=design_name)
            )
            return {
                "target": self._target(target),
                "mode": "analyze_all",
                "project_name": project_name,
                "design_name": design_name,
                "completed": completed,
                "solver_completion_confirmed": completed,
            }

        app = self._resolve_app(desktop, project_name, design_name)
        valid, details = self._validate_app(app)
        if not valid:
            return {
                "target": self._target(target),
                "started": False,
                "validation_passed": False,
                "validation_details": details,
                "project_name": getattr(app, "project_name", project_name),
                "design_name": getattr(app, "design_name", design_name),
            }
        solve_in_batch = _boolean(arguments, "solve_in_batch", False)
        requested_cores = _positive_int(arguments, "num_cores")
        requested_tasks = _positive_int(arguments, "num_tasks")
        requested_gpus = _positive_int(arguments, "num_gpus")
        requested_auto_settings = _boolean(arguments, "use_auto_settings", True)
        acf_file = _optional_text(arguments, "acf_file") or None
        icepak_safe_mode = _boolean(arguments, "icepak_safe_mode", True)
        safe_mode_applied = bool(_is_icepak(app) and icepak_safe_mode and not acf_file)
        effective_cores = 1 if safe_mode_applied else requested_cores
        effective_tasks = 1 if safe_mode_applied and requested_tasks else requested_tasks
        effective_gpus = None if safe_mode_applied else requested_gpus
        effective_auto_settings = (
            False if safe_mode_applied else requested_auto_settings
        )
        adjustments = []
        if safe_mode_applied and requested_cores not in (None, 1):
            adjustments.append(
                f"Icepak safe mode changed num_cores from {requested_cores} to 1"
            )
        if safe_mode_applied and requested_tasks not in (None, 1):
            adjustments.append(
                f"Icepak safe mode changed num_tasks from {requested_tasks} to 1"
            )
        if safe_mode_applied and requested_gpus is not None:
            adjustments.append("Icepak safe mode disabled GPU allocation")
        if safe_mode_applied and requested_auto_settings:
            adjustments.append("Icepak safe mode disabled automatic DSO settings")
        started = bool(
            app.analyze(
                setup=setup_name,
                cores=effective_cores,
                tasks=effective_tasks,
                gpus=effective_gpus,
                acf_file=acf_file,
                use_auto_settings=effective_auto_settings,
                solve_in_batch=solve_in_batch,
                machine=_optional_text(arguments, "machine", "localhost")
                or "localhost",
                run_in_thread=_boolean(arguments, "run_in_thread", False),
                revert_to_initial_mesh=_boolean(
                    arguments, "revert_to_initial_mesh", False
                ),
                blocking=False,
            )
        )
        return {
            "target": self._target(target),
            "started": started,
            "validation_passed": True,
            "project_name": getattr(app, "project_name", project_name),
            "design_name": getattr(app, "design_name", design_name),
            "setup_name": setup_name,
            "mode": "batch" if solve_in_batch else "interactive",
            "solver_completion_confirmed": False,
            "icepak_safe_mode_applied": safe_mode_applied,
            "requested_resources": {
                "num_cores": requested_cores,
                "num_tasks": requested_tasks,
                "num_gpus": requested_gpus,
                "use_auto_settings": requested_auto_settings,
            },
            "effective_resources": {
                "num_cores": effective_cores,
                "num_tasks": effective_tasks,
                "num_gpus": effective_gpus,
                "use_auto_settings": effective_auto_settings,
            },
            "resource_adjustments": adjustments,
        }

    def _export_results(self, desktop, target, arguments, connection_kwargs):
        output = str(
            Path(_required_text(arguments, "output_path")).expanduser().resolve()
        )
        export_type = _optional_text(arguments, "export_type", "touchstone").lower()
        setup_name = _optional_text(arguments, "setup_name") or None
        methods = {
            "touchstone": "export_touchstone",
            "profile": "export_profile",
            "convergence": "export_convergence",
            "mesh": "export_mesh_stats",
        }
        if export_type not in methods:
            raise CapabilityError(
                "export_type must be touchstone, profile, convergence, or mesh"
            )
        app = self._resolve_app(desktop, None, None)
        if export_type != "touchstone" and not setup_name:
            get_setups = getattr(app, "get_setups", None)
            setups = list(get_setups()) if callable(get_setups) else []
            if len(setups) == 1:
                setup_name = str(setups[0])
            elif not setups:
                raise CapabilityError(
                    f"{export_type} export requires a solved setup, but none exists"
                )
            else:
                raise CapabilityError(
                    f"{export_type} export requires setup_name because multiple "
                    f"setups exist: {', '.join(map(str, setups))}"
                )
        output_path = Path(output)
        details = None
        if _is_icepak(app) and export_type == "convergence":
            details = _export_icepak_convergence(app, output_path)
            result = details["path"]
            export_method = details["source"]
        elif _is_icepak(app) and export_type == "mesh":
            details = _export_icepak_mesh_stats(app, str(setup_name), output_path)
            result = details["path"]
            export_method = details["source"]
        else:
            method = getattr(app, methods[export_type], None)
            if not callable(method):
                raise CapabilityError(
                    f"{export_type} export is unavailable for {type(app).__name__} designs"
                )
            kwargs = {"output_file": output}
            if setup_name:
                kwargs["setup"] = setup_name
            result = method(**kwargs)
            export_method = methods[export_type]
        return {
            "target": self._target(target),
            "export_type": export_type,
            "setup_name": setup_name,
            "output_path": output,
            "result": result,
            "file_exists": output_path.exists(),
            "export_method": export_method,
            "details": details,
        }

    def _screenshot(self, desktop, target, arguments, connection_kwargs):
        raw_path = (
            _optional_text(arguments, "path", "screenshot.jpg") or "screenshot.jpg"
        )
        output = Path(raw_path).expanduser().resolve()
        if output.suffix.lower() not in {".jpg", ".jpeg"}:
            output = output.with_suffix(".jpg")
        resolution = _optional_text(arguments, "resolution", "1080p") or "1080p"
        if resolution not in {"1080p", "4k"}:
            raise CapabilityError("resolution must be 1080p or 4k")
        plot_type = _optional_text(arguments, "plot_type", "model") or "model"
        if plot_type not in {"model", "field", "mesh"}:
            raise CapabilityError("plot_type must be model, field, or mesh")
        project = _optional_text(arguments, "project") or None
        design = _optional_text(arguments, "design") or None
        open_viewer = _boolean(arguments, "open_viewer", True)
        app = self._resolve_app(desktop, project, design)
        width, height = (3840, 2160) if resolution == "4k" else (1920, 1080)
        output.parent.mkdir(parents=True, exist_ok=True)
        app.post.export_model_picture(
            full_name=str(output),
            width=width,
            height=height,
        )
        if not output.is_file():
            raise RuntimeError(f"screenshot file was not created: {output}")
        viewer_error = _open_viewer(output) if open_viewer else None
        return {
            "target": self._target(target),
            "path": str(output),
            "project": getattr(app, "project_name", project),
            "design": getattr(app, "design_name", design),
            "plot_type": plot_type,
            "resolution": resolution,
            "mime_type": "image/jpeg",
            "data_base64": base64.b64encode(output.read_bytes()).decode("ascii"),
            "viewer_opened": bool(open_viewer and viewer_error is None),
            "viewer_error": viewer_error,
        }

    def _export_config(self, desktop, target, arguments, connection_kwargs):
        output = _optional_text(arguments, "output") or None
        project = _optional_text(arguments, "project") or None
        design = _optional_text(arguments, "design") or None
        overwrite = _boolean(arguments, "overwrite", False)
        app = self._resolve_app(desktop, project, design)
        temporary = False
        if output:
            target_path = Path(output).expanduser().resolve()
            if target_path.suffix.lower() != ".json":
                target_path = target_path.with_suffix(".json")
        else:
            descriptor, temporary_name = tempfile.mkstemp(suffix=".json")
            os.close(descriptor)
            target_path = Path(temporary_name)
            target_path.unlink(missing_ok=True)
            temporary = True
        try:
            config_file = app.configurations.export_config(
                config_file=str(target_path),
                overwrite=overwrite,
            )
            if not config_file:
                raise RuntimeError("PyAEDT did not export a configuration file")
            config_path = Path(config_file)
            config = json.loads(config_path.read_text(encoding="utf-8"))
            result = {
                "target": self._target(target),
                "config": config,
                "design": getattr(app, "design_name", design),
                "project": getattr(app, "project_name", project),
            }
            if output:
                result["config_file"] = str(config_path.resolve())
            return result
        finally:
            if temporary:
                target_path.unlink(missing_ok=True)
