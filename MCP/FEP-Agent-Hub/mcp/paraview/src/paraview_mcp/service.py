from __future__ import annotations

import atexit
import json
import math
import os
import queue
import struct
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from open_cae_core import EvidenceRecorder, ToolResponse, WorkspaceGuard
from open_cae_core.config import OpenCAEConfig
from open_cae_core.manifests import read_json

from .environment import probe_paraview


class WorkerSession:
    def __init__(self, project_root: Path, executable: Path, worker_script: Path) -> None:
        if executable.name.lower() != "pvpython.exe" or not executable.is_file():
            raise ValueError("Only a configured pvpython.exe may start the ParaView worker")
        self.project_root = project_root
        self.executable = executable
        self.worker_script = worker_script
        self.session_id = uuid.uuid4().hex[:12]
        self._lock = threading.Lock()
        self._responses: queue.Queue[str | None] = queue.Queue()
        log_dir = project_root / "evidence" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        self.stderr_path = log_dir / f"pvpython-{self.session_id}.stderr.log"
        self._stderr = self.stderr_path.open("w", encoding="utf-8", newline="\n")
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        appdata = project_root / "evidence" / "paraview-appdata"
        appdata.mkdir(parents=True, exist_ok=True)
        environment = os.environ.copy()
        environment["APPDATA"] = str(appdata)
        environment["LOCALAPPDATA"] = str(appdata)
        self.process = subprocess.Popen(
            [str(executable), str(worker_script)],
            cwd=str(project_root),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self._stderr,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            shell=False,
            creationflags=flags,
            env=environment,
        )
        self._reader = threading.Thread(target=self._read_stdout, daemon=True)
        self._reader.start()
        EvidenceRecorder(project_root).command(
            {
                "exe": str(executable),
                "args": [str(worker_script)],
                "cwd": str(project_root),
                "pid": self.process.pid,
                "persistent": True,
                "session_id": self.session_id,
            }
        )
        response = self.call("ping", {}, timeout=60)
        if not response.get("ok"):
            self.close(force=True)
            raise RuntimeError(response.get("error", "pvpython worker did not become ready"))

    def _read_stdout(self) -> None:
        assert self.process.stdout is not None
        for line in self.process.stdout:
            self._responses.put(line)
        self._responses.put(None)

    def call(self, method: str, params: dict[str, Any], *, timeout: float = 60) -> dict[str, Any]:
        if self.process.poll() is not None:
            return {"ok": False, "error": "SESSION_LOST", "exit_code": self.process.returncode}
        request_id = uuid.uuid4().hex
        request = {"id": request_id, "method": method, "params": params}
        deadline = time.monotonic() + timeout
        with self._lock:
            assert self.process.stdin is not None
            self.process.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
            self.process.stdin.flush()
            while time.monotonic() < deadline:
                try:
                    line = self._responses.get(timeout=max(0.1, deadline - time.monotonic()))
                except queue.Empty:
                    break
                if line is None:
                    return {"ok": False, "error": "SESSION_LOST", "exit_code": self.process.poll()}
                try:
                    response = json.loads(line)
                except json.JSONDecodeError:
                    EvidenceRecorder(self.project_root).append("worker_protocol.jsonl", {"non_json_stdout": line.rstrip()})
                    continue
                if response.get("id") == request_id:
                    EvidenceRecorder(self.project_root).append(
                        "worker_protocol.jsonl",
                        {"method": method, "request_id": request_id, "ok": response.get("ok")},
                    )
                    return response
        return {"ok": False, "error": f"Worker timeout after {timeout} seconds"}

    def close(self, *, force: bool = False) -> None:
        if self.process.poll() is None and not force:
            try:
                self.call("stop", {}, timeout=10)
            except Exception:
                pass
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        if self.process.stdin:
            self.process.stdin.close()
        if self.process.stdout:
            self.process.stdout.close()
        self._stderr.close()


class ParaViewService:
    def __init__(self, config: OpenCAEConfig) -> None:
        self.config = config
        self.guard = WorkspaceGuard(config.workspace_root)
        self.worker_script = Path(__file__).parent / "worker" / "bridge_worker.py"
        self.sessions: dict[str, WorkerSession] = {}
        atexit.register(self.close_all)

    def environment_probe(self) -> ToolResponse:
        data = probe_paraview(self.config)
        if data["headless_available"]:
            return ToolResponse.success("ParaView pvpython headless capability is available", data=data)
        return ToolResponse.blocked(
            "pvpython.exe was not found",
            data=data,
            next_recommended_action="Set [paraview].pvpython in OPEN_CAE_CONFIG",
        )

    def session_start(self, project: str, mode: str = "headless") -> ToolResponse:
        if mode != "headless":
            return ToolResponse.blocked("ParaView Live GUI Bridge is a later milestone; v0.1 is headless")
        project_root = self.guard.ensure_project(project)
        existing = self.sessions.get(project)
        if existing and existing.process.poll() is None:
            return ToolResponse.success(
                "ParaView worker is already running",
                data={"session_id": existing.session_id, "pid": existing.process.pid, "status": "READY"},
            )
        executable = probe_paraview(self.config).get("pvpython_exe")
        if not executable:
            return ToolResponse.blocked("pvpython.exe is unavailable")
        try:
            session = WorkerSession(project_root, Path(executable), self.worker_script)
        except Exception as exc:
            return ToolResponse.failure(
                f"Failed to start pvpython worker: {exc}",
                evidence=[self.guard.relative(project_root / "evidence" / "logs")],
            )
        self.sessions[project] = session
        return ToolResponse.success(
            "Persistent pvpython worker started",
            data={"session_id": session.session_id, "pid": session.process.pid, "status": "READY"},
            evidence=[self.guard.relative(session.stderr_path)],
        )

    def session_status(self, project: str) -> ToolResponse:
        session = self.sessions.get(project)
        if not session:
            return ToolResponse.success("No ParaView session", data={"status": "STOPPED"})
        status = "READY" if session.process.poll() is None else "SESSION_LOST"
        return ToolResponse.success(
            f"ParaView session status: {status}",
            data={"status": status, "session_id": session.session_id, "pid": session.process.pid, "exit_code": session.process.poll()},
        )

    def session_stop(self, project: str) -> ToolResponse:
        session = self.sessions.pop(project, None)
        if not session:
            return ToolResponse.success("No MCP-owned ParaView worker was running", data={"status": "STOPPED"})
        session.close()
        return ToolResponse.success(
            "MCP-owned ParaView worker stopped",
            data={"status": "STOPPED", "session_id": session.session_id},
        )

    def close_all(self) -> None:
        for project in list(self.sessions):
            try:
                self.session_stop(project)
            except Exception:
                pass

    def _call(self, project: str, method: str, params: dict[str, Any], *, timeout: float = 60) -> ToolResponse:
        session = self.sessions.get(project)
        if not session or session.process.poll() is not None:
            return ToolResponse.blocked(
                "ParaView session is not ready",
                next_recommended_action="Call paraview_session_start first",
            )
        response = session.call(method, params, timeout=timeout)
        evidence = EvidenceRecorder(self.guard.ensure_project(project))
        if not response.get("ok"):
            result = ToolResponse.failure(
                response.get("error", "ParaView worker operation failed"),
                data={"method": method, "error_type": response.get("error_type")},
                evidence=[self.guard.relative(session.stderr_path)],
            )
            evidence.tool_call(f"paraview_{method}", params, result.to_dict())
            return result
        result = ToolResponse.success(f"ParaView operation {method} completed", data=response.get("data", {}))
        evidence.tool_call(f"paraview_{method}", params, result.to_dict())
        return result

    def _resolve_dataset_path(self, project: str, value: str) -> Path:
        project_root = self.guard.ensure_project(project)
        path = self.guard.resolve(project_root / value, allowed_extensions={".vtu", ".pvtu", ".vtk", ".pvd"})
        if path.is_file():
            return path
        if value == "results/case.vtu":
            manifest = project_root / "results" / "result_manifest.json"
            if manifest.is_file():
                files = read_json(manifest).get("files", [])
                if files:
                    candidate = self.guard.resolve(project_root / files[0], allowed_extensions={".vtu", ".pvtu", ".vtk", ".pvd"}, must_exist=True)
                    return candidate
        raise FileNotFoundError(path)

    def dataset_open(self, project: str, path: str = "results/case.vtu", alias: str = "result") -> ToolResponse:
        try:
            dataset = self._resolve_dataset_path(project, path)
        except FileNotFoundError as exc:
            return ToolResponse.failure(f"Dataset does not exist: {exc}")
        response = self._call(project, "dataset_open", {"path": str(dataset), "alias": alias}, timeout=120)
        if response.ok:
            response.artifacts = [self.guard.relative(dataset)]
        return response

    def dataset_inspect(self, project: str, proxy: str = "result") -> ToolResponse:
        return self._call(project, "dataset_inspect", {"proxy": proxy})

    def pipeline_inspect(self, project: str) -> ToolResponse:
        return self._call(project, "pipeline_inspect", {})

    def filter_create(self, project: str, input_proxy: str, filter_type: str, parameters: dict[str, Any], alias: str | None = None) -> ToolResponse:
        if filter_type not in {"slice", "clip", "contour", "glyph", "stream_tracer", "warp", "threshold", "calculator", "plot_over_line"}:
            return ToolResponse.blocked("Filter type is not in the v0.1 whitelist")
        if filter_type == "plot_over_line":
            point1 = parameters.get("point1")
            point2 = parameters.get("point2")
            resolution = parameters.get("resolution", 200)
            if (
                not isinstance(point1, list)
                or not isinstance(point2, list)
                or len(point1) != 3
                or len(point2) != 3
                or not all(isinstance(value, (int, float)) and math.isfinite(float(value)) for value in point1 + point2)
                or not isinstance(resolution, int)
                or not 1 <= resolution <= 10000
            ):
                return ToolResponse.failure("plot_over_line requires finite point1/point2 vectors and resolution in 1..10000")
            parameters = {
                "point1": [float(value) for value in point1],
                "point2": [float(value) for value in point2],
                "resolution": resolution,
            }
        return self._call(
            project,
            "filter_create",
            {"input": input_proxy, "filter_type": filter_type, "parameters": parameters, "alias": alias},
            timeout=120,
        )

    def color_by(self, project: str, proxy: str, array: str, association: str = "POINTS", preset: str | None = None) -> ToolResponse:
        return self._call(project, "color_by", {"proxy": proxy, "array": array, "association": association, "preset": preset})

    def scalar_range(self, project: str, proxy: str, array: str, association: str = "POINTS", mode: str = "data") -> ToolResponse:
        if mode != "data":
            return ToolResponse.blocked("v0.1 scalar range mode is data; percentile is a later capability")
        return self._call(project, "scalar_range", {"proxy": proxy, "array": array, "association": association})

    def camera_set(self, project: str, camera: dict[str, Any]) -> ToolResponse:
        return self._call(project, "camera_set", camera)

    def camera_fit(self, project: str) -> ToolResponse:
        return self._call(project, "camera_fit", {})

    def render(self, project: str) -> ToolResponse:
        return self._call(project, "render", {}, timeout=120)

    def export_image(
        self,
        project: str,
        output: str = "post/field.png",
        resolution: list[int] | None = None,
        background: list[float] | None = None,
    ) -> ToolResponse:
        project_root = self.guard.ensure_project(project)
        target = self.guard.resolve(project_root / output, allowed_extensions={".png"})
        resolution = resolution or [1920, 1080]
        if len(resolution) != 2 or any(int(value) <= 0 or int(value) > 8192 for value in resolution):
            return ToolResponse.failure("Resolution must contain two values in 1..8192")
        response = self._call(
            project,
            "export_image",
            {"output": str(target), "resolution": [int(value) for value in resolution], "background": background or [1.0, 1.0, 1.0]},
            timeout=180,
        )
        if not response.ok:
            return response
        actual = self._png_size(target)
        if not target.is_file() or target.stat().st_size == 0 or list(actual or ()) != [int(value) for value in resolution]:
            return ToolResponse.failure(
                "ParaView returned success but PNG artifact validation failed",
                data={"expected_resolution": resolution, "actual_resolution": actual},
            )
        EvidenceRecorder(project_root).record_artifacts([target])
        response.artifacts = [self.guard.relative(target)]
        response.data["validated_resolution"] = list(actual)
        return response

    @staticmethod
    def _png_size(path: Path) -> tuple[int, int] | None:
        if not path.is_file():
            return None
        data = path.read_bytes()[:24]
        if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
            return None
        return struct.unpack(">II", data[16:24])

    def export_csv(self, project: str, proxy: str = "result", output: str = "post/result.csv") -> ToolResponse:
        project_root = self.guard.ensure_project(project)
        target = self.guard.resolve(project_root / output, allowed_extensions={".csv"})
        response = self._call(project, "export_csv", {"proxy": proxy, "output": str(target)}, timeout=180)
        if response.ok and target.is_file() and target.stat().st_size > 0:
            EvidenceRecorder(project_root).record_artifacts([target])
            response.artifacts = [self.guard.relative(target)]
            return response
        if response.ok:
            return ToolResponse.failure("ParaView returned success but CSV is missing or empty")
        return response

    def export_animation(
        self,
        project: str,
        proxy: str = "result",
        output: str = "post/animation/frame.png",
        resolution: list[int] | None = None,
        frame_rate: int = 10,
        background: list[float] | None = None,
    ) -> ToolResponse:
        inspection = self.dataset_inspect(project, proxy)
        if not inspection.ok:
            return inspection
        time_steps = inspection.data.get("time_steps", [])
        if len(time_steps) < 2:
            return ToolResponse.blocked(
                "Animation export requires at least two verified dataset time steps",
                data={"time_steps": time_steps},
            )
        if len(time_steps) > 240:
            return ToolResponse.blocked("Animation export is limited to 240 verified time steps")
        project_root = self.guard.ensure_project(project)
        target = self.guard.resolve(project_root / output, allowed_extensions={".png"})
        resolution = resolution or [1920, 1080]
        if len(resolution) != 2 or any(int(value) <= 0 or int(value) > 8192 for value in resolution):
            return ToolResponse.failure("Resolution must contain two values in 1..8192")
        if not isinstance(frame_rate, int) or not 1 <= frame_rate <= 120:
            return ToolResponse.failure("frame_rate must be an integer in 1..120")
        response = self._call(
            project,
            "export_animation",
            {
                "proxy": proxy,
                "output": str(target),
                "resolution": [int(value) for value in resolution],
                "frame_rate": frame_rate,
                "background": background or [0.015, 0.025, 0.06],
            },
            timeout=600,
        )
        if not response.ok:
            return response
        files = []
        for value in response.data.get("files", []):
            try:
                frame = self.guard.resolve(value, allowed_extensions={".png"}, must_exist=True)
            except (FileNotFoundError, ValueError):
                return ToolResponse.failure("ParaView animation reported an unsafe or missing frame")
            if self._png_size(frame) != (int(resolution[0]), int(resolution[1])):
                return ToolResponse.failure("ParaView animation frame resolution validation failed")
            files.append(frame)
        if len(files) != len(time_steps):
            return ToolResponse.failure(
                "ParaView animation frame count does not match verified time steps",
                data={"expected": len(time_steps), "actual": len(files)},
            )
        EvidenceRecorder(project_root).record_artifacts(files)
        response.artifacts = [self.guard.relative(path) for path in files]
        response.data["validated_frame_count"] = len(files)
        return response

    def state_save(self, project: str, output: str = "post/state.pvsm") -> ToolResponse:
        project_root = self.guard.ensure_project(project)
        target = self.guard.resolve(project_root / output, allowed_extensions={".pvsm"})
        response = self._call(project, "state_save", {"output": str(target)}, timeout=120)
        if response.ok and target.is_file() and target.stat().st_size > 0:
            response.artifacts = [self.guard.relative(target)]
        return response
