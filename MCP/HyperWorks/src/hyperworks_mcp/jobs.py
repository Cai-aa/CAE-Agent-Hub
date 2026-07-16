from __future__ import annotations

import ctypes
import json
import os
import shutil
import signal
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

from .settings import Settings, within


SUCCESS_MARKER = "__HYPERWORKS_MCP_DONE__"


def _write_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def _pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    if os.name == "nt":
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _tail(path: Path, max_chars: int = 2_000_000) -> str:
    if not path.is_file():
        return ""
    with path.open("rb") as stream:
        stream.seek(0, os.SEEK_END)
        size = stream.tell()
        stream.seek(max(0, size - max_chars))
        return stream.read().decode("utf-8", errors="replace")


class JobService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.processes: dict[str, subprocess.Popen[bytes]] = {}

    def _job_dir(self, job_id: str) -> Path:
        if not job_id.startswith("job_") or any(
            char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"
            for char in job_id
        ):
            raise ValueError("Invalid job_id")
        path = within(
            self.settings.workspace / "jobs" / job_id,
            self.settings.workspace / "jobs",
        )
        if not (path / "job.json").is_file():
            raise ValueError(f"Job not found: {job_id}")
        return path

    def _record(self, job_id: str) -> dict[str, Any]:
        directory = self._job_dir(job_id)
        return json.loads((directory / "job.json").read_text(encoding="utf-8"))

    def start(
        self,
        kind: str,
        project_id: str,
        command: list[str],
        run_dir: Path,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        job_id = "job_" + time.strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
        job_dir = within(self.settings.workspace / "jobs" / job_id, self.settings.workspace)
        job_dir.mkdir(parents=True)
        log_path = job_dir / "stdout.log"
        stdout = log_path.open("wb")
        flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        try:
            process = subprocess.Popen(
                command,
                cwd=run_dir,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=subprocess.STDOUT,
                shell=False,
                creationflags=flags,
            )
        finally:
            stdout.close()
        now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        record = {
            "job_id": job_id,
            "project_id": project_id,
            "kind": kind,
            "state": "RUNNING",
            "pid": process.pid,
            "return_code": None,
            "created_at": now,
            "updated_at": now,
            "run_directory": str(run_dir),
            "log_file": str(log_path),
            "command": [Path(command[0]).name, *command[1:]],
            "metadata": metadata or {},
        }
        _write_json(job_dir / "job.json", record)
        self.processes[job_id] = process
        return record

    def status(self, job_id: str) -> dict[str, Any]:
        record = self._record(job_id)
        process = self.processes.get(job_id)
        return_code = process.poll() if process else record.get("return_code")
        alive = process.poll() is None if process else _pid_alive(record.get("pid"))
        state = record["state"]
        log_text = _tail(Path(record["log_file"]))
        if state not in {"COMPLETED", "FAILED", "CANCELLED", "UNKNOWN"}:
            if alive:
                state = "RUNNING"
            elif return_code is not None:
                state = "COMPLETED" if return_code == 0 else "FAILED"
            elif record["kind"] == "HMBATCH" and SUCCESS_MARKER in log_text:
                state = "COMPLETED"
            else:
                state = "UNKNOWN"
        if state != record["state"] or return_code != record.get("return_code"):
            record.update(
                {
                    "state": state,
                    "return_code": return_code,
                    "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                }
            )
            _write_json(self._job_dir(job_id) / "job.json", record)
        return {
            **record,
            "state": state,
            "process_alive": alive,
            "success_marker_detected": SUCCESS_MARKER in log_text,
            "estimated_progress": None,
        }

    def log(self, job_id: str, lines: int = 100) -> dict[str, Any]:
        record = self._record(job_id)
        path = Path(record["log_file"])
        content = _tail(path).splitlines()
        count = max(1, min(int(lines), 5000))
        return {
            "job_id": job_id,
            "path": str(path),
            "exists": path.is_file(),
            "lines": content[-count:],
        }

    def cancel(self, job_id: str) -> dict[str, Any]:
        record = self.status(job_id)
        if record["state"] != "RUNNING":
            return {**record, "message": "Job is not active; nothing was terminated."}
        process = self.processes.get(job_id)
        pid = record.get("pid")
        if os.name == "nt" and pid:
            if process:
                try:
                    process.send_signal(signal.CTRL_BREAK_EVENT)
                    process.wait(timeout=5)
                except (OSError, subprocess.TimeoutExpired):
                    pass
            if _pid_alive(pid):
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    capture_output=True,
                    check=False,
                    timeout=20,
                    shell=False,
                )
        elif process:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        if pid and _pid_alive(pid):
            raise RuntimeError(f"Process tree is still alive: {pid}")
        record.update(
            {
                "state": "CANCELLED",
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            }
        )
        _write_json(self._job_dir(job_id) / "job.json", record)
        return record

    def list(self, project_id: str | None = None, limit: int = 50) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        for path in sorted(
            (self.settings.workspace / "jobs").glob("job_*/job.json"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        ):
            record = json.loads(path.read_text(encoding="utf-8"))
            if project_id is None or record.get("project_id") == project_id:
                items.append(self.status(record["job_id"]))
            if len(items) >= max(1, min(int(limit), 200)):
                break
        return {"jobs": items, "count": len(items)}

    def artifacts(self, job_id: str) -> dict[str, Any]:
        record = self._record(job_id)
        roots = [Path(record["run_directory"]), self._job_dir(job_id)]
        items: list[dict[str, Any]] = []
        seen: set[str] = set()
        for root in roots:
            if not root.is_dir():
                continue
            for path in root.rglob("*"):
                if not path.is_file() or path.name == "job.json":
                    continue
                key = os.path.normcase(str(path.resolve()))
                if key in seen:
                    continue
                seen.add(key)
                items.append(
                    {
                        "path": str(path),
                        "size_bytes": path.stat().st_size,
                        "modified_epoch": path.stat().st_mtime,
                    }
                )
        return {"job_id": job_id, "artifacts": items, "count": len(items)}


def stage_solver_input(project_root: Path, deck_file: Path, destination: Path) -> Path:
    source_root = within(project_root / "input", project_root)
    shutil.copytree(source_root, destination, dirs_exist_ok=False)
    relative = deck_file.resolve().relative_to(source_root.resolve())
    return destination / relative
