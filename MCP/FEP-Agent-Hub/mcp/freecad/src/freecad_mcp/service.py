from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Any

from open_cae_core import (
    EvidenceRecorder,
    SafeProcessRunner,
    ToolResponse,
    WorkspaceGuard,
)
from open_cae_core.config import OpenCAEConfig
from open_cae_core.manifests import read_json, write_json

from .environment import probe_freecad


class FreeCADService:
    def __init__(self, config: OpenCAEConfig) -> None:
        self.config = config
        self.guard = WorkspaceGuard(config.workspace_root)
        self.runner = SafeProcessRunner()
        self.runner_script = Path(__file__).parent / "runner" / "freecad_runner.FCMacro"

    def environment_probe(self) -> ToolResponse:
        data = probe_freecad(self.config)
        if data["headless_ok"]:
            return ToolResponse.success("FreeCAD headless capability is available", data=data)
        return ToolResponse.blocked(
            "FreeCADCmd.exe was not found",
            data=data,
            next_recommended_action="Set [freecad].cmd in OPEN_CAE_CONFIG",
        )

    def session_status(self) -> ToolResponse:
        environment = probe_freecad(self.config)
        status = "HEADLESS_AVAILABLE" if environment["headless_ok"] else "UNAVAILABLE"
        return ToolResponse.success(
            f"FreeCAD session status: {status}", data={"session_status": status, **environment}
        )

    def _document(self, project: str, value: str = "geometry/model.FCStd", *, must_exist: bool = True) -> Path:
        project_root = self.guard.ensure_project(project)
        path = self.guard.resolve(project_root / value, allowed_extensions={".fcstd"}, must_exist=must_exist)
        try:
            path.relative_to(project_root)
        except ValueError as exc:
            raise ValueError("Document must stay inside the selected project") from exc
        return path

    def _execute(
        self,
        project: str,
        operation: str,
        *,
        document: str = "geometry/model.FCStd",
        payload: dict[str, Any] | None = None,
        document_must_exist: bool = True,
        expected_artifacts: list[Path] | None = None,
        timeout: float = 180,
    ) -> ToolResponse:
        project_root = self.guard.ensure_project(project)
        evidence = EvidenceRecorder(project_root)
        executable = probe_freecad(self.config).get("freecadcmd_exe")
        if not executable:
            return ToolResponse.blocked(
                "FreeCADCmd.exe is unavailable",
                next_recommended_action="Run freecad_environment_probe and configure FreeCAD",
            )
        document_path = self._document(project, document, must_exist=document_must_exist)
        job_id = uuid.uuid4().hex[:12]
        job_path = project_root / "evidence" / "jobs" / f"freecad-{job_id}.json"
        result_path = project_root / "evidence" / "jobs" / f"freecad-{job_id}.result.json"
        logs = project_root / "evidence" / "logs"
        payload = dict(payload or {})
        write_json(
            job_path,
            {"operation": operation, "document": str(document_path), "payload": payload},
        )
        staged_runner_dir = project_root / "evidence" / "freecad-runner"
        staged_runner_dir.mkdir(parents=True, exist_ok=True)
        staged_runner = staged_runner_dir / self.runner_script.name
        staged_python = staged_runner_dir / "freecad_runner.py"
        shutil.copy2(self.runner_script, staged_runner)
        shutil.copy2(self.runner_script.with_name("freecad_runner.py"), staged_python)
        process = self.runner.run(
            executable,
            [
                "-u",
                str(project_root / "evidence" / "freecad-user.cfg"),
                "-s",
                str(project_root / "evidence" / "freecad-system.cfg"),
                str(staged_runner),
            ],
            cwd=project_root,
            stdout_log=logs / f"freecad-{job_id}.stdout.log",
            stderr_log=logs / f"freecad-{job_id}.stderr.log",
            timeout=timeout,
            environment={
                "OPEN_CAE_JOB": str(job_path),
                "OPEN_CAE_RESULT": str(result_path),
            },
            evidence=evidence,
        )
        raw = read_json(result_path) if result_path.is_file() else {
            "ok": False,
            "error": "FreeCAD runner did not produce a result file",
        }
        inputs = {"project": project, "document": document, **payload}
        if process.exit_code != 0 or not raw.get("ok"):
            response = ToolResponse.failure(
                raw.get("error", "FreeCAD operation failed"),
                data={
                    "operation": operation,
                    "error_type": raw.get("error_type"),
                    "process": process.to_dict(),
                },
                evidence=[self.guard.relative(result_path), self.guard.relative(Path(process.stderr_log))],
            )
            evidence.tool_call(f"freecad_{operation}", inputs, response.to_dict())
            return response

        artifacts = [path for path in (expected_artifacts or []) if path.is_file() and path.stat().st_size > 0]
        if expected_artifacts and len(artifacts) != len(expected_artifacts):
            missing = [str(path) for path in expected_artifacts if path not in artifacts]
            response = ToolResponse.failure(
                "FreeCAD returned success but required artifacts are missing",
                data={"missing": missing, "process": process.to_dict()},
            )
            evidence.tool_call(f"freecad_{operation}", inputs, response.to_dict())
            return response
        if artifacts:
            evidence.record_artifacts(artifacts)
        response = ToolResponse.success(
            f"FreeCAD operation {operation} completed",
            data=raw.get("data", {}),
            artifacts=[self.guard.relative(path) for path in artifacts],
            evidence=[self.guard.relative(result_path)],
        )
        evidence.tool_call(f"freecad_{operation}", inputs, response.to_dict())
        return response

    def document_create(
        self,
        project: str,
        path: str = "geometry/model.FCStd",
        label: str = "OpenCAE",
        overwrite: bool = False,
    ) -> ToolResponse:
        document = self._document(project, path, must_exist=False)
        return self._execute(
            project,
            "document_create",
            document=path,
            payload={"name": "OpenCAE", "label": label, "overwrite": overwrite},
            document_must_exist=False,
            expected_artifacts=[document],
        )

    def document_inspect(self, project: str, path: str = "geometry/model.FCStd") -> ToolResponse:
        return self._execute(project, "document_inspect", document=path)

    def object_inspect(self, project: str, name: str, path: str = "geometry/model.FCStd") -> ToolResponse:
        return self._execute(project, "object_inspect", document=path, payload={"name": name})

    def feature_create(
        self,
        project: str,
        feature_type: str,
        name: str,
        parameters: dict[str, Any],
        placement: dict[str, Any] | None = None,
        path: str = "geometry/model.FCStd",
    ) -> ToolResponse:
        return self._execute(
            project,
            "feature_create",
            document=path,
            payload={
                "feature_type": feature_type,
                "name": name,
                "parameters": parameters,
                "placement": placement or {},
            },
            expected_artifacts=[self._document(project, path)],
        )

    def feature_update(
        self,
        project: str,
        name: str,
        patch: dict[str, Any],
        placement: dict[str, Any] | None = None,
        path: str = "geometry/model.FCStd",
    ) -> ToolResponse:
        payload: dict[str, Any] = {"name": name, "patch": patch}
        if placement is not None:
            payload["placement"] = placement
        return self._execute(
            project,
            "feature_update",
            document=path,
            payload=payload,
            expected_artifacts=[self._document(project, path)],
        )

    def feature_delete(
        self,
        project: str,
        name: str,
        force: bool = False,
        path: str = "geometry/model.FCStd",
    ) -> ToolResponse:
        return self._execute(
            project,
            "feature_delete",
            document=path,
            payload={"name": name, "force": force},
            expected_artifacts=[self._document(project, path)],
        )

    def boolean(
        self,
        project: str,
        operation: str,
        base: str,
        tools: list[str],
        result: str,
        path: str = "geometry/model.FCStd",
    ) -> ToolResponse:
        return self._execute(
            project,
            "boolean",
            document=path,
            payload={"operation": operation, "base": base, "tools": tools, "result": result},
            expected_artifacts=[self._document(project, path)],
        )

    def transform(
        self,
        project: str,
        name: str,
        placement: dict[str, Any],
        path: str = "geometry/model.FCStd",
    ) -> ToolResponse:
        return self._execute(
            project,
            "transform",
            document=path,
            payload={"name": name, "placement": placement},
            expected_artifacts=[self._document(project, path)],
        )

    def geometry_validate(
        self,
        project: str,
        objects: list[str] | None = None,
        path: str = "geometry/model.FCStd",
    ) -> ToolResponse:
        response = self._execute(
            project, "geometry_validate", document=path, payload={"objects": objects or []}
        )
        if response.ok and not response.data.get("valid"):
            response.ok = False
            response.status = "FAILED"
            response.summary = "FreeCAD geometry validation failed"
        return response

    def document_save(
        self,
        project: str,
        path: str = "geometry/model.FCStd",
        output: str | None = None,
        overwrite: bool = False,
    ) -> ToolResponse:
        output_path = self._document(project, output or path, must_exist=False)
        if output_path.exists() and output and output != path and not overwrite:
            return ToolResponse.blocked("Output exists; set overwrite=true to replace it")
        return self._execute(
            project,
            "document_save",
            document=path,
            payload={"output": str(output_path)},
            expected_artifacts=[output_path],
        )

    def export_step(
        self,
        project: str,
        objects: list[str] | None = None,
        output: str = "geometry/model.step",
        also_export_parts: bool = False,
        semantic_ids: dict[str, str] | None = None,
        path: str = "geometry/model.FCStd",
    ) -> ToolResponse:
        project_root = self.guard.ensure_project(project)
        step = self.guard.resolve(project_root / output, allowed_extensions={".step", ".stp"})
        manifest = project_root / "geometry" / "geometry_manifest.json"
        return self._execute(
            project,
            "export_step",
            document=path,
            payload={
                "objects": objects or [],
                "output": str(step),
                "manifest": str(manifest),
                "step_file": self.guard.relative(step).split(f"{project}/", 1)[-1],
                "also_export_parts": also_export_parts,
                "semantic_ids": semantic_ids or {},
                "model_name": project,
            },
            expected_artifacts=[step, manifest],
        )

    def capture_view(self, project: str) -> ToolResponse:
        self.guard.ensure_project(project)
        return ToolResponse.blocked(
            "Headless FreeCAD view capture is not guaranteed and is disabled in v0.1",
            data={"capability": "UNSUPPORTED_IN_HEADLESS"},
            next_recommended_action="Use ParaView MCP after solving or add the FreeCAD Live Bridge",
        )
