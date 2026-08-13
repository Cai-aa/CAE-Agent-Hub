from __future__ import annotations

from pathlib import Path

import pytest

from open_cae_core import SafeProcessRunner, ToolResponse, WorkspaceGuard
from open_cae_core.errors import ExecutableNotAllowed, WorkspaceViolation


def test_workspace_guard_rejects_escape(tmp_path: Path) -> None:
    guard = WorkspaceGuard(tmp_path / "workspace")
    with pytest.raises(WorkspaceViolation):
        guard.resolve("../outside.step")
    with pytest.raises(WorkspaceViolation):
        guard.resolve("\\\\server\\share\\model.step")


def test_workspace_guard_extensions_and_project(tmp_path: Path) -> None:
    guard = WorkspaceGuard(tmp_path / "workspace")
    project = guard.ensure_project("cube_heat")
    assert (project / "evidence").is_dir()
    with pytest.raises(WorkspaceViolation):
        guard.resolve(project / "model.exe", allowed_extensions={".step"})


def test_process_runner_rejects_unlisted_executable(tmp_path: Path) -> None:
    runner = SafeProcessRunner()
    with pytest.raises(ExecutableNotAllowed):
        runner.run(
            "python.exe",
            [],
            cwd=tmp_path,
            stdout_log=tmp_path / "out.log",
            stderr_log=tmp_path / "err.log",
        )


def test_tool_response_schema() -> None:
    payload = ToolResponse.success("done", data={"value": 1}).to_dict()
    assert payload == {
        "ok": True,
        "status": "SUCCEEDED",
        "summary": "done",
        "data": {"value": 1},
        "artifacts": [],
        "evidence": [],
        "warnings": [],
        "next_recommended_action": None,
    }

