from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:
    pass

JOBS_DIR = Path(os.environ.get("ATOMISTIC_MCP_JOBS_DIR", ROOT / "jobs"))


def _resolve(candidates: list[str | None]) -> Path | None:
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate).expanduser()
        if path.is_file():
            return path.resolve()
        found = shutil.which(candidate)
        if found:
            return Path(found).resolve()
    return None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _job_path(job_id: str) -> Path:
    return JOBS_DIR / job_id / "job.json"


def _tail(path: Path, size: int) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")[-max(1, int(size)) :]


def _probe_import(command: Path | None) -> dict[str, Any] | None:
    if command is None:
        return None
    try:
        result = subprocess.run(
            [str(command), "-c", "import ovito; print(getattr(ovito, '__version__', 'available'))"],
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return {"ok": result.returncode == 0, "stdout": result.stdout.strip(), "stderr": result.stderr.strip()}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def find_lammps(executable: str | None = None) -> Path | None:
    return _resolve([executable, os.environ.get("LAMMPS_EXE"), "lmp", "lmp_serial", "lmp_mpi"])


def find_ovito_gui(executable: str | None = None) -> Path | None:
    return _resolve([executable, os.environ.get("OVITO_EXE"), "ovito"])


def find_ovito_script(command: str | None = None) -> Path | None:
    return _resolve([command, os.environ.get("OVITOS_EXE"), "ovitos", os.environ.get("OVITO_PYTHON")])


def detect_lammps(executable: str | None = None) -> dict[str, Any]:
    path = find_lammps(executable)
    return {
        "status": "ok" if path else "missing",
        "lammps_exe": str(path) if path else None,
        "message": "Potential files are user-supplied inputs and need separate provenance and redistribution review.",
    }


def detect_ovito(ovito_exe: str | None = None, script_command: str | None = None) -> dict[str, Any]:
    gui = find_ovito_gui(ovito_exe)
    script = find_ovito_script(script_command)
    probe = _probe_import(script)
    batch_ok = bool(probe and probe.get("ok"))
    return {
        "status": "ok" if batch_ok else "partial" if gui else "missing",
        "ovito_gui": str(gui) if gui else None,
        "ovito_script_command": str(script) if script else None,
        "batch_python_available": batch_ok,
        "import_probe": probe,
        "message": "OVITO GUI availability does not imply ovitos or Python batch support.",
    }


def _run(kind: str, command: list[str], cwd: Path, run_dir: Path, timeout_sec: int) -> dict[str, Any]:
    if timeout_sec <= 0:
        return {"status": "error", "error": "timeout_sec must be positive"}
    job_id = f"{kind}_{uuid.uuid4().hex[:12]}"
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    stdout_path, stderr_path = job_dir / "stdout.log", job_dir / "stderr.log"
    payload: dict[str, Any] = {
        "job_id": job_id,
        "kind": kind,
        "command": command,
        "cwd": str(cwd),
        "run_dir": str(run_dir),
        "stdout": str(stdout_path),
        "stderr": str(stderr_path),
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    try:
        with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
            result = subprocess.run(
                command, cwd=str(cwd), stdout=stdout, stderr=stderr, timeout=timeout_sec,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=False,
            )
        payload.update({"status": "completed" if result.returncode == 0 else "failed", "returncode": result.returncode})
    except subprocess.TimeoutExpired:
        payload.update({"status": "timed_out", "returncode": None})
    except Exception as exc:
        payload.update({"status": "error", "error": str(exc), "returncode": None})
    payload["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    _write_json(_job_path(job_id), payload)
    return payload


def run_lammps_input(input_path: str, run_dir: str, executable: str | None, extra_args: list[str] | None, timeout_sec: int) -> dict[str, Any]:
    exe, input_file = find_lammps(executable), Path(input_path).expanduser().resolve()
    if exe is None:
        return {"status": "missing", "error": "LAMMPS executable not found. Set LAMMPS_EXE."}
    if not input_file.is_file():
        return {"status": "missing", "error": f"LAMMPS input not found: {input_file}"}
    output = Path(run_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    return _run("lammps", [str(exe), *(extra_args or []), "-in", input_file.name], input_file.parent, output, timeout_sec)


def run_ovito_script(script_path: str, run_dir: str, command: str | None, timeout_sec: int) -> dict[str, Any]:
    exe, script = find_ovito_script(command), Path(script_path).expanduser().resolve()
    if exe is None:
        return {"status": "missing", "error": "ovitos or an OVITO Python interpreter not found."}
    if not script.is_file():
        return {"status": "missing", "error": f"OVITO script not found: {script}"}
    output = Path(run_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    return _run("ovito", [str(exe), str(script)], script.parent, output, timeout_sec)


def get_job_status(job_id: str) -> dict[str, Any]:
    path = _job_path(job_id)
    if not path.exists():
        return {"status": "not_found", "job_id": job_id}
    return json.loads(path.read_text(encoding="utf-8"))


def read_job_log(job_id: str, stream: str = "stdout", tail_chars: int = 12000) -> dict[str, Any]:
    job = get_job_status(job_id)
    if job.get("status") == "not_found":
        return job
    key = "stderr" if stream.lower() == "stderr" else "stdout"
    return {"job_id": job_id, "stream": key, "status": job.get("status"), "tail": _tail(Path(job[key]), tail_chars)}


def list_jobs(limit: int = 20) -> dict[str, Any]:
    if not JOBS_DIR.exists():
        return {"jobs": [], "count": 0}
    paths = sorted(JOBS_DIR.glob("*/job.json"), key=lambda path: path.stat().st_mtime, reverse=True)[: max(1, int(limit))]
    return {"jobs": [json.loads(path.read_text(encoding="utf-8")) for path in paths], "count": len(paths)}
