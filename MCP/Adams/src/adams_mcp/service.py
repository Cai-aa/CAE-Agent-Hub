from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import socket
import subprocess
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import Settings


NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
FATAL_RE = re.compile(
    r"(?im)^\s*!?\s*(?:ERROR:|FATAL:)|command (?:was )?not executed|license (?:failure|error)|integration failure|invalid keyword"
)
SAFE_LIVE_PREFIXES = (
    "model ", "part ", "marker ", "geometry ", "constraint ", "force ",
    "measure ", "simulation ", "numeric_results ", "file spread_sheet ",
    "executive_control ", "defaults ", "view ", "graphic ", "interface ",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ok(summary: str, data: Any = None, *, artifacts: list[str] | None = None, warnings: list[str] | None = None, evidence: list[str] | None = None) -> dict[str, Any]:
    return {
        "ok": True,
        "status": "SUCCEEDED",
        "summary": summary,
        "data": data if data is not None else {},
        "artifacts": artifacts or [],
        "warnings": warnings or [],
        "evidence": evidence or [],
        "next_recommended_action": None,
    }


def _fail(code: str, message: str, *, retryable: bool = False, recommended_action: str | None = None, log: str | None = None, status: str = "FAILED") -> dict[str, Any]:
    return {
        "ok": False,
        "status": status,
        "error": {
            "code": code,
            "message": message,
            "log": log,
            "retryable": retryable,
            "recommended_action": recommended_action,
        },
    }


class AdamsService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.projects = settings.workspace / "projects"
        self.runs = settings.workspace / "runs"

    def environment_probe(self) -> dict[str, Any]:
        s = self.settings
        launcher = s.launcher
        root = s.adams_root
        aview = root / "aview" / "win64" / "aview.exe"
        solver = root / "solver" / "win64" / "solver.exe"
        adams_python = root / "python" / "win64" / "Lib" / "site-packages"
        command_server = adams_python / "mdi" / "command_server" / "ViewCommandListener.py"
        probes = {
            "launcher": {"path": str(launcher), "available": launcher.is_file()},
            "adams_view": {"path": str(aview), "available": aview.is_file()},
            "adams_solver": {"path": str(solver), "available": solver.is_file()},
            "adams_python": {"path": str(adams_python), "available": adams_python.is_dir()},
            "command_server_module": {"path": str(command_server), "available": command_server.is_file()},
            "workspace": {"path": str(s.workspace), "available": s.workspace.is_dir()},
        }
        ready = all(probes[key]["available"] for key in ("launcher", "adams_view", "workspace"))
        data = {
            "release": s.release,
            "release_source": "configured_and_executable_metadata",
            "adams_root": str(root),
            "platform": "windows",
            "batch_ready": ready,
            "live_endpoint": f"127.0.0.1:{s.live_port}",
            "live_listening": self._port_open(),
            "raw_commands_enabled": s.raw_commands_enabled,
            "probes": probes,
            "checked_at": _now(),
        }
        return _ok("Adams environment is ready for batch execution" if ready else "Adams environment is incomplete", data, warnings=[] if ready else ["Launcher or Adams/View was not found"])

    def capabilities(self) -> dict[str, Any]:
        env = self.environment_probe()["data"]
        live = bool(env["live_listening"])
        batch = bool(env["batch_ready"])
        capabilities = [
            self._cap("environment.probe", True, ["local"]),
            self._cap("batch.cmd", batch, ["view_batch"], "runtime-verified" if batch else "unavailable"),
            self._cap("live.query", live, ["live_cmd"], "runtime-verified" if live else "available_when_server_listens"),
            self._cap("live.structured_cmd", live, ["live_cmd"], "available_when_server_listens"),
            self._cap("model.create", batch, ["batch_cmd", "live_cmd"], "template-verified-adams-2024.1"),
            self._cap("part.create.box", batch, ["batch_cmd", "live_cmd"], "template-verified-adams-2024.1"),
            self._cap("joint.create.revolute", batch, ["batch_cmd", "live_cmd"], "template-verified-adams-2024.1"),
            self._cap("gravity.set", batch, ["batch_cmd", "live_cmd"], "template-verified-adams-2024.1"),
            self._cap("motion.create.rotational", batch, ["batch_cmd", "live_cmd"], "template-verified-adams-2024.1"),
            self._cap("simulation.transient", batch, ["batch_cmd", "live_cmd"], "native-smoke-required"),
            self._cap("result.extract", batch, ["batch_cmd"], "component-path-must-be-discovered"),
            self._cap("plot.create", False, ["view_postprocessor"], "unverified"),
            self._cap("animation.export", False, ["view_postprocessor"], "unverified"),
            self._cap("solver.direct", False, ["solver"], "planned-v0.2"),
        ]
        return _ok("Capability registry generated from configuration and runtime probes", {"release": self.settings.release, "capabilities": capabilities})

    @staticmethod
    def _cap(cap_id: str, supported: bool, backend: list[str], verification: str = "runtime-probed") -> dict[str, Any]:
        return {"id": cap_id, "supported": supported, "backend": backend, "verification": verification}

    def project_create(self, project_id: str, model_name: str, length_unit: str = "mm", mass_unit: str = "kg", force_unit: str = "newton", time_unit: str = "sec", angle_unit: str = "deg") -> dict[str, Any]:
        try:
            project_id = self._name(project_id, "project_id")
            model_name = self._name(model_name, "model_name")
        except ValueError as exc:
            return _fail("ADM-MODEL-204", str(exc))
        units = {"length": length_unit, "mass": mass_unit, "force": force_unit, "time": time_unit, "angle": angle_unit}
        allowed = {"length": {"mm", "cm", "meter", "inch", "foot"}, "mass": {"kg", "gram", "pound_mass"}, "force": {"newton", "kilonewton", "pound_force"}, "time": {"sec"}, "angle": {"deg", "rad"}}
        if any(value not in allowed[key] for key, value in units.items()):
            return _fail("ADM-MODEL-204", f"Unsupported unit selection: {units}")
        path = self.projects / project_id
        if path.exists():
            return _fail("ADM-MODEL-201", f"Project already exists: {project_id}")
        path.mkdir(parents=True)
        manifest = {"schema_version": 1, "project_id": project_id, "model_name": model_name, "units": units, "parts": [], "connections": [], "loads": [], "motions": [], "measures": [], "analyses": [], "created_at": _now(), "updated_at": _now()}
        self._write_json(path / "model_manifest.json", manifest)
        preamble = (
            f"defaults units length={length_unit} angle={angle_unit} force={force_unit} mass={mass_unit} time={time_unit}\n"
            f"model create model_name={model_name}\n"
            f"model display model_name={model_name}\n"
        )
        (path / "model.cmd").write_text(preamble, encoding="utf-8")
        return _ok(f"Created isolated Adams project {project_id}", {"project_id": project_id, "model_name": model_name, "manifest": str(path / "model_manifest.json")}, artifacts=[str(path / "model.cmd"), str(path / "model_manifest.json")])

    def project_inspect(self, project_id: str) -> dict[str, Any]:
        try:
            path, manifest = self._project(project_id)
        except (ValueError, FileNotFoundError) as exc:
            return _fail("ADM-MODEL-201", str(exc))
        return _ok(f"Inspected Adams project {project_id}", {"manifest": manifest, "model_cmd": str(path / "model.cmd")}, artifacts=[str(path / "model_manifest.json"), str(path / "model.cmd")])

    def rigid_body_create(self, project_id: str, semantic_id: str, corner: list[float], size: list[float], mass: float, inertia: list[float]) -> dict[str, Any]:
        try:
            semantic_id = self._name(semantic_id, "semantic_id")
            path, manifest = self._project(project_id)
            self._vec(corner, 3, "corner")
            self._vec(size, 3, "size", positive=True)
            self._vec(inertia, 3, "inertia", positive=True)
            if not math.isfinite(mass) or mass <= 0:
                raise ValueError("mass must be a positive finite number")
        except (ValueError, FileNotFoundError) as exc:
            return _fail("ADM-MODEL-204", str(exc))
        if any(item["semantic_id"] == semantic_id for item in manifest["parts"]):
            return _fail("ADM-MODEL-204", f"semantic_id already exists: {semantic_id}")
        model = manifest["model_name"]
        part = f".{model}.{semantic_id}"
        cm = f"{part}.cm"
        marker = f"{part}.corner"
        diag = [corner[i] + size[i] for i in range(3)]
        cmd = f"""
part create rigid_body name_and_position part_name={part} location=0,0,0 orientation=0d,0d,0d
marker create marker_name={cm} location={corner[0] + size[0]/2},{corner[1] + size[1]/2},{corner[2] + size[2]/2} orientation=0d,0d,0d
marker create marker_name={marker} location={corner[0]},{corner[1]},{corner[2]} orientation=0d,0d,0d
part create rigid_body mass_properties part_name={part} mass={mass} center_of_mass_marker={cm} ixx={inertia[0]} iyy={inertia[1]} izz={inertia[2]} ixy=0 izx=0 iyz=0
geometry create shape block block_name={part}.geometry corner_marker={marker} diag_corner_coords={diag[0]},{diag[1]},{diag[2]}
"""
        self._append(path / "model.cmd", cmd)
        manifest["parts"].append({"semantic_id": semantic_id, "adams_path": part, "entity_type": "part", "geometry": "box", "corner": corner, "size": size, "mass": mass, "inertia": inertia})
        self._save_manifest(path, manifest)
        return _ok(f"Added rigid body {semantic_id}", {"semantic_id": semantic_id, "adams_path": part}, artifacts=[str(path / "model.cmd")])

    def connection_create_revolute(self, project_id: str, semantic_id: str, i_part: str, j_part: str, location: list[float], orientation: list[float] | None = None) -> dict[str, Any]:
        try:
            semantic_id = self._name(semantic_id, "semantic_id")
            i_part = self._name(i_part, "i_part")
            j_part = self._name(j_part, "j_part")
            path, manifest = self._project(project_id)
            self._vec(location, 3, "location")
            orientation = orientation or [0.0, 0.0, 0.0]
            self._vec(orientation, 3, "orientation")
        except (ValueError, FileNotFoundError) as exc:
            return _fail("ADM-MODEL-206", str(exc))
        model = manifest["model_name"]
        known = {item["semantic_id"] for item in manifest["parts"]} | {"ground"}
        if i_part not in known or j_part not in known:
            return _fail("ADM-MODEL-202", f"Parts must exist in manifest (known: {sorted(known)})")
        i_path = f".{model}.{i_part}"
        j_path = f".{model}.{j_part}"
        im = f"{i_path}.{semantic_id}_i"
        jm = f"{j_path}.{semantic_id}_j"
        joint = f".{model}.{semantic_id}"
        loc = ",".join(map(str, location)); ori = ",".join(f"{v}d" for v in orientation)
        cmd = f"""
marker create marker_name={im} location={loc} orientation={ori}
marker create marker_name={jm} location={loc} orientation={ori}
constraint create joint revolute joint_name={joint} i_marker_name={im} j_marker_name={jm}
"""
        self._append(path / "model.cmd", cmd)
        manifest["connections"].append({"semantic_id": semantic_id, "adams_path": joint, "type": "revolute", "i_part": i_part, "j_part": j_part, "location": location, "orientation": orientation})
        self._save_manifest(path, manifest)
        return _ok(f"Added revolute joint {semantic_id}", {"semantic_id": semantic_id, "adams_path": joint})

    def gravity_set(self, project_id: str, vector: list[float]) -> dict[str, Any]:
        try:
            path, manifest = self._project(project_id)
            self._vec(vector, 3, "vector")
        except (ValueError, FileNotFoundError) as exc:
            return _fail("ADM-MODEL-204", str(exc))
        cmd = f"force create body gravitational gravity_field_name=gravity x_component_gravity={vector[0]} y_component_gravity={vector[1]} z_component_gravity={vector[2]}\n"
        self._append(path / "model.cmd", cmd)
        manifest["loads"] = [item for item in manifest["loads"] if item.get("type") != "gravity"]
        manifest["loads"].append({"semantic_id": "gravity", "type": "gravity", "vector": vector})
        self._save_manifest(path, manifest)
        return _ok("Gravity command added", {"vector": vector})

    def motion_create_rotational(self, project_id: str, semantic_id: str, joint_id: str, function: str) -> dict[str, Any]:
        try:
            semantic_id = self._name(semantic_id, "semantic_id")
            joint_id = self._name(joint_id, "joint_id")
            path, manifest = self._project(project_id)
            if not re.fullmatch(r"[0-9A-Za-z_+\-*/(). dD]+", function) or len(function) > 200:
                raise ValueError("function contains unsupported characters or is too long")
        except (ValueError, FileNotFoundError) as exc:
            return _fail("ADM-MODEL-204", str(exc))
        if joint_id not in {item["semantic_id"] for item in manifest["connections"]}:
            return _fail("ADM-MODEL-202", f"Joint not found: {joint_id}")
        model = manifest["model_name"]
        motion = f".{model}.{semantic_id}"
        cmd = f'constraint create motion_generator motion_name={motion} type_of_freedom=rotational joint_name=.{model}.{joint_id} function="{function}"\n'
        self._append(path / "model.cmd", cmd)
        manifest["motions"].append({"semantic_id": semantic_id, "adams_path": motion, "type": "rotational", "joint": joint_id, "function": function})
        self._save_manifest(path, manifest)
        return _ok(f"Added rotational motion {semantic_id}", {"semantic_id": semantic_id, "function": function})

    def simulation_run(self, project_id: str, analysis_name: str, end_time: float, steps: int, timeout_sec: float | None = None) -> dict[str, Any]:
        try:
            analysis_name = self._name(analysis_name, "analysis_name")
            path, manifest = self._project(project_id)
            if not math.isfinite(end_time) or end_time <= 0 or not 2 <= steps <= 1_000_000:
                raise ValueError("end_time must be positive and steps must be between 2 and 1,000,000")
        except (ValueError, FileNotFoundError) as exc:
            return _fail("ADM-SOLVE-301", str(exc))
        source = (path / "model.cmd").read_text(encoding="utf-8")
        source += f"\nsimulation single_run transient type=auto_select end_time={end_time} number_of_steps={steps} model_name=.{manifest['model_name']} initial_static=no\n"
        numeric_component = None
        if manifest["connections"]:
            joint_id = manifest["connections"][0]["semantic_id"]
            numeric_component = f".{manifest['model_name']}.Last_Run.{joint_id}.FY"
            source += f'numeric_results write result_set_component_name={numeric_component} sort_by=by_time order=ascending write_to_terminal=off file_name="results/{analysis_name}_{joint_id}_fy.txt"\n'
        result = self._run_batch_text(source, {"kind": "project_simulation", "project_id": project_id, "analysis_name": analysis_name, "end_time": end_time, "steps": steps, "numeric_component": numeric_component, "require_numeric": numeric_component is not None}, timeout_sec)
        if result["ok"]:
            manifest["analyses"].append({"name": analysis_name, "run_id": result["data"]["run_id"], "end_time": end_time, "steps": steps, "status": "VERIFIED"})
            self._save_manifest(path, manifest)
        return result

    def batch_run_cmd(self, cmd_path: str, timeout_sec: float | None = None) -> dict[str, Any]:
        try:
            source = self._inside_workspace(Path(cmd_path), must_exist=True)
        except (ValueError, FileNotFoundError) as exc:
            return _fail("ADM-MCP-004", str(exc))
        if source.suffix.lower() != ".cmd":
            return _fail("ADM-MCP-004", "Only .cmd files inside the configured workspace may be executed")
        return self._run_batch_text(source.read_text(encoding="utf-8", errors="replace"), {"kind": "workspace_cmd", "source": str(source)}, timeout_sec)

    def smoke_test(self, timeout_sec: float = 180.0) -> dict[str, Any]:
        fixture = self.settings.adams_root / "aview" / "examples" / "parametric" / "para_4bar.cmd"
        if not fixture.is_file():
            return _fail("ADM-MCP-001", f"Adams-native smoke fixture not found: {fixture}")
        text = fixture.read_text(encoding="latin-1")
        text = re.sub(r"(?im)^\s*graphic\s+animate\s*$", "! graphic animate omitted by headless smoke test", text)
        text += '\nnumeric_results write result_set_component_name=.para_4bar.Last_Run.JOINT_1.FY sort_by=by_time order=ascending write_to_terminal=off file_name="results/joint1_fy.txt"\n'
        result = self._run_batch_text(text, {"kind": "native_smoke", "fixture": str(fixture), "expected_model": "para_4bar", "expected_end_time": 5.0}, timeout_sec)
        if result["ok"]:
            result["summary"] = "Adams 2024.1 native four-bar model built and transient simulation completed through MCP batch adapter"
        return result

    def result_summary(self, result_path: str) -> dict[str, Any]:
        try:
            path = self._inside_workspace(Path(result_path), must_exist=True)
        except (ValueError, FileNotFoundError) as exc:
            return _fail("ADM-POST-401", str(exc))
        if path.suffix.lower() not in {".txt", ".csv", ".sps"}:
            return _fail("ADM-POST-401", "Only text/CSV/spreadsheet numeric exports can be summarized")
        values = self._numeric_values(path)
        if len(values) < 2:
            return _fail("ADM-POST-401", f"Fewer than two finite numeric data points found in {path}")
        mean = sum(values) / len(values)
        rms = math.sqrt(sum(value * value for value in values) / len(values))
        data = {"path": str(path), "points": len(values), "min": min(values), "max": max(values), "mean": mean, "rms": rms, "first": values[0], "final": values[-1], "sha256": self._sha256(path)}
        return _ok(f"Summarized {len(values)} Adams numeric result points", data, artifacts=[str(path)])

    def live_status(self, port: int | None = None) -> dict[str, Any]:
        port = port or self.settings.live_port
        listening = self._port_open(port)
        return _ok("Adams Command Server is listening" if listening else "Adams Command Server is not listening", {"host": "127.0.0.1", "port": port, "connected": listening}, warnings=[] if listening else ["In Adams/View run: command_server start, then start the listener on this port"])

    def live_query(self, expression: str, port: int | None = None) -> dict[str, Any]:
        if not expression or len(expression) > 1000 or any(char in expression for char in "\r\n\x00"):
            return _fail("ADM-LIVE-102", "Invalid query expression")
        try:
            data = self._socket_exchange("query" + expression, query=True, port=port)
            return _ok("Live Adams query completed", {"expression": expression, "result": data})
        except (OSError, TimeoutError, ValueError) as exc:
            return _fail("ADM-LIVE-102", str(exc), retryable=True, recommended_action="Start Command Server in Adams/View and confirm the configured localhost port")

    def live_command(self, command: str, port: int | None = None) -> dict[str, Any]:
        normalized = command.strip().lower()
        if not self.settings.raw_commands_enabled and not normalized.startswith(SAFE_LIVE_PREFIXES):
            return _fail("ADM-MCP-004", "Command prefix is not allowlisted; arbitrary Adams CMD is disabled")
        if len(command) > 4000 or any(char in command for char in "\r\n\x00"):
            return _fail("ADM-MCP-004", "Command must be one line and no longer than 4000 characters")
        try:
            data = self._socket_exchange("cmd " + command, query=False, port=port)
            return _ok("Live Adams command completed", {"command": command, "response": data})
        except (OSError, TimeoutError, ValueError) as exc:
            return _fail("ADM-LIVE-102", str(exc), retryable=True)

    def evidence_latest(self) -> dict[str, Any]:
        candidates = sorted((item for item in self.runs.iterdir() if item.is_dir()), key=lambda p: p.stat().st_mtime, reverse=True)
        if not candidates:
            return _fail("ADM-POST-401", "No Adams MCP runs exist yet")
        run = candidates[0]
        validation = self._read_json(run / "validation.json") if (run / "validation.json").is_file() else {}
        artifacts = [str(item) for item in run.rglob("*") if item.is_file()]
        return _ok(f"Latest evidence is {run.name}", {"run_id": run.name, "validation": validation}, artifacts=artifacts, evidence=[str(run / "final_report.md")])

    def _run_batch_text(self, source_text: str, request: dict[str, Any], timeout_sec: float | None) -> dict[str, Any]:
        if not self.settings.launcher.is_file():
            return _fail("ADM-MCP-001", f"Adams launcher not found: {self.settings.launcher}")
        run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
        run = self.runs / run_id
        (run / "logs").mkdir(parents=True)
        (run / "model").mkdir()
        (run / "results").mkdir()
        cmd_path = run / "aview.cmd"
        clean = source_text.rstrip() + "\nquit conf=no\n"
        cmd_path.write_text(clean, encoding="latin-1", errors="replace")
        self._write_json(run / "request.json", {**request, "run_id": run_id, "created_at": _now()})
        self._write_json(run / "environment.json", self.environment_probe()["data"])
        self._write_json(run / "capabilities.json", self.capabilities()["data"])
        start = time.monotonic()
        timeout = min(float(timeout_sec or self.settings.batch_timeout_sec), 3600.0)
        comspec = os.environ.get("COMSPEC", "C:/Windows/System32/cmd.exe")
        args = [comspec, "/d", "/s", "/c", "call", str(self.settings.launcher), "aview", "ru-s", "b", cmd_path.name]
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
        stdout_path = run / "logs" / "stdout.log"
        stderr_path = run / "logs" / "stderr.log"
        # Desktop MCP hosts may provide a PATH without Windows utilities.
        # Adams' nested batch scripts need them even when cmd.exe is absolute.
        child_env = os.environ.copy()
        system_root = Path(os.environ.get("SystemRoot", "C:/Windows"))
        child_env["PATH"] = os.pathsep.join([
            str(system_root / "System32"), str(system_root),
            str(system_root / "System32" / "Wbem"), child_env.get("PATH", ""),
        ])
        with stdout_path.open("w", encoding="utf-8") as stdout_stream, stderr_path.open(
            "w", encoding="utf-8"
        ) as stderr_stream:
            process = subprocess.Popen(
                args,
                cwd=run,
                stdin=subprocess.DEVNULL,
                env=child_env,
                stdout=stdout_stream,
                stderr=stderr_stream,
                text=True,
                encoding="utf-8",
                errors="replace",
                shell=False,
                creationflags=creationflags,
            )
            try:
                process.wait(timeout=timeout)
                completed = process
                timed_out = False
            except subprocess.TimeoutExpired:
                # Adams' launcher creates cmd/python grandchildren.  Killing only
                # the immediate cmd.exe can leave a grandchild alive, so terminate
                # the full Windows process tree while its parent still exists.
                timed_out = True
                taskkill = Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32" / "taskkill.exe"
                if taskkill.is_file():
                    subprocess.run(
                        [str(taskkill), "/PID", str(process.pid), "/T", "/F"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=15,
                        check=False,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                elif process.poll() is None:
                    process.kill()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                completed = None
        stdout = stdout_path.read_text(encoding="utf-8", errors="replace")
        stderr = stderr_path.read_text(encoding="utf-8", errors="replace")
        log_text = stdout + "\n" + stderr
        for log_file in run.glob("*.log"):
            log_text += "\n" + log_file.read_text(encoding="utf-8", errors="replace")
        fatal_matches = sorted(set(match.group(0).strip() for match in FATAL_RE.finditer(log_text)))
        artifacts = [item for item in run.rglob("*") if item.is_file()]
        result_files = [item for item in artifacts if item.suffix.lower() in {".res", ".req", ".gra", ".adm", ".msg", ".bin"} or (item.is_relative_to(run / "results") and item.suffix.lower() in {".txt", ".csv", ".sps"})]
        numeric_outputs = []
        for item in result_files:
            if item.suffix.lower() in {".txt", ".csv", ".sps"}:
                values = self._numeric_values(item)
                numeric_outputs.append({"path": str(item), "points": len(values), "finite": all(math.isfinite(value) for value in values), "min": min(values) if values else None, "max": max(values) if values else None})
        return_code = None if timed_out else completed.returncode
        model_verified = bool(re.search(r"Model verified successfully", log_text, re.I))
        simulation_seen = bool(re.search(r"simulation\s+single(?:_run)?\s+trans", log_text, re.I))
        numeric_gate = any(item["points"] > 1 and item["finite"] for item in numeric_outputs)
        required_numeric = request.get("kind") == "native_smoke" or bool(request.get("require_numeric"))
        required_simulation = request.get("kind") in {"native_smoke", "project_simulation"}
        passed = not timed_out and return_code == 0 and not fatal_matches and (not required_simulation or (model_verified and simulation_seen)) and (not required_numeric or numeric_gate)
        validation = {
            "run_id": run_id,
            "status": "VERIFIED" if passed else ("TIMEOUT" if timed_out else "FAILED"),
            "process_exit_zero": return_code == 0,
            "fatal_error_count": len(fatal_matches),
            "fatal_signals": fatal_matches[:20],
            "model_verified": model_verified,
            "simulation_command_seen": simulation_seen,
            "result_artifact_count": len(result_files),
            "result_artifacts": [str(item) for item in result_files],
            "numeric_outputs": numeric_outputs,
            "numeric_gate_passed": numeric_gate,
            "elapsed_seconds": round(time.monotonic() - start, 3),
            "completed_at": _now(),
        }
        self._write_json(run / "validation.json", validation)
        report = f"# Adams MCP run {run_id}\n\nStatus: {validation['status']}\n\nExit code: {return_code}\n\nFatal signals: {len(fatal_matches)}\n\nResult artifacts: {len(result_files)}\n\nElapsed: {validation['elapsed_seconds']} s\n"
        (run / "final_report.md").write_text(report, encoding="utf-8")
        hash_targets = [item for item in run.rglob("*") if item.is_file() and item.name != "hashes.json"]
        hashes = {str(item.relative_to(run)): self._sha256(item) for item in hash_targets}
        self._write_json(run / "hashes.json", hashes)
        all_artifacts = [str(item) for item in run.rglob("*") if item.is_file()]
        if timed_out:
            return _fail("ADM-SOLVE-304", f"Adams batch timed out after {timeout} seconds", retryable=True, log=str(run / "logs" / "stdout.log"), recommended_action="Check license availability and inspect the batch log", status="TIMEOUT")
        if not passed:
            code = "ADM-MCP-003" if re.search(r"license", log_text, re.I) else "ADM-SOLVE-303"
            return _fail(code, f"Adams batch failed (exit={return_code}, fatal_signals={len(fatal_matches)})", log=str(run / "logs" / "stdout.log"), recommended_action="Inspect validation.json and the captured Adams logs")
        return _ok("Adams batch completed and passed process/error gates", {"run_id": run_id, "validation": validation}, artifacts=all_artifacts, evidence=[str(run / "validation.json"), str(run / "hashes.json"), str(run / "final_report.md")], warnings=[] if result_files else ["No disk result artifact was detected; validation currently proves Adams command/batch completion but not a numeric result series"])

    def _socket_exchange(self, payload: str, *, query: bool, port: int | None) -> str:
        use_port = int(port or self.settings.live_port)
        with socket.create_connection(("127.0.0.1", use_port), timeout=self.settings.connect_timeout_sec) as client:
            client.settimeout(self.settings.command_timeout_sec)
            client.sendall(payload.encode("utf-8"))
            first = client.recv(1024).decode("utf-8", "replace")
            if not query:
                return first
            if first == "SERVER_ERROR":
                raise ValueError("Adams Command Server rejected the query")
            if not first.startswith("query:"):
                raise ValueError(f"Unexpected Command Server response: {first}")
            client.sendall(b"OK")
            chunks: list[bytes] = []
            while True:
                try:
                    chunk = client.recv(65536)
                except socket.timeout:
                    break
                if not chunk:
                    break
                chunks.append(chunk)
            return b"".join(chunks).decode("utf-8", "replace")

    def _port_open(self, port: int | None = None) -> bool:
        try:
            with socket.create_connection(("127.0.0.1", int(port or self.settings.live_port)), timeout=0.25):
                return True
        except OSError:
            return False

    def _project(self, project_id: str) -> tuple[Path, dict[str, Any]]:
        project_id = self._name(project_id, "project_id")
        path = self.projects / project_id
        if not path.is_dir():
            raise FileNotFoundError(f"Project not found: {project_id}")
        return path, self._read_json(path / "model_manifest.json")

    def _inside_workspace(self, path: Path, *, must_exist: bool = False) -> Path:
        resolved = path.expanduser().resolve(strict=must_exist)
        if not resolved.is_relative_to(self.settings.workspace):
            raise ValueError(f"Path is outside configured workspace: {resolved}")
        return resolved

    @staticmethod
    def _name(value: str, field: str) -> str:
        if not NAME_RE.fullmatch(value):
            raise ValueError(f"{field} must match {NAME_RE.pattern}")
        return value

    @staticmethod
    def _vec(value: list[float], size: int, field: str, positive: bool = False) -> None:
        if len(value) != size or any(not math.isfinite(float(item)) for item in value):
            raise ValueError(f"{field} must contain {size} finite numbers")
        if positive and any(float(item) <= 0 for item in value):
            raise ValueError(f"{field} values must be positive")

    @staticmethod
    def _append(path: Path, text: str) -> None:
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(text.strip() + "\n")

    def _save_manifest(self, path: Path, manifest: dict[str, Any]) -> None:
        manifest["updated_at"] = _now()
        self._write_json(path / "model_manifest.json", manifest)

    @staticmethod
    def _write_json(path: Path, data: Any) -> None:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    @staticmethod
    def _numeric_values(path: Path) -> list[float]:
        values: list[float] = []
        number_line = re.compile(r"^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?)\s*$")
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            match = number_line.match(line)
            if match:
                value = float(match.group(1))
                if math.isfinite(value):
                    values.append(value)
        return values
