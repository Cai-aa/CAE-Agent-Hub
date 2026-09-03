from __future__ import annotations

import json
import os
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

JOBS_DIR = Path(os.environ.get("JOBS_DIR", ROOT / "jobs"))
WORKBENCH_JOBS_DIR = JOBS_DIR / "workbench"


def _safe_mkdir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _safe_mkdir(path.parent)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _process_running(pid: int) -> bool:
    try:
        import psutil

        return psutil.pid_exists(pid) and psutil.Process(pid).is_running()
    except Exception:
        # Fallback that works on Windows without relying on psutil internals.
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV"],
                text=True,
                capture_output=True,
                timeout=10,
            )
            return str(pid) in result.stdout
        except Exception:
            return False


def _find_under(base: Path, name: str) -> Path | None:
    if not base.exists():
        return None
    try:
        matches = sorted(base.rglob(name), key=lambda p: p.stat().st_mtime, reverse=True)
    except Exception:
        return None
    return matches[0] if matches else None


def find_workbench_exe() -> Path | None:
    """Find RunWB2.exe from env vars and common install locations."""
    explicit = os.environ.get("ANSYS_WB_EXE") or os.environ.get("RUNWB2_EXE")
    if explicit and Path(explicit).exists():
        return Path(explicit)

    candidates: list[Path] = []
    ansys_root = os.environ.get("ANSYS_ROOT")
    if ansys_root:
        root = Path(ansys_root)
        candidates.extend(
            [
                root / "Framework" / "bin" / "Win64" / "RunWB2.exe",
                root / "Framework" / "bin" / "Win64" / "runwb2.exe",
            ]
        )
    for key, value in os.environ.items():
        if key.upper().startswith("AWP_ROOT"):
            root = Path(value)
            candidates.extend(
                [
                    root / "Framework" / "bin" / "Win64" / "RunWB2.exe",
                    root / "Framework" / "bin" / "Win64" / "runwb2.exe",
                ]
            )

    candidates.extend([Path("C:/Program Files/ANSYS Inc"), Path("C:/Program Files/Ansys Inc")])

    for candidate in candidates:
        if candidate.is_file():
            return candidate
        if candidate.is_dir():
            found = _find_under(candidate, "RunWB2.exe") or _find_under(candidate, "runwb2.exe")
            if found:
                return found
    return None


def find_mechanical_cli() -> Path | None:
    """Find the PyMechanical CLI installed in this MCP virtual environment."""
    explicit = os.environ.get("ANSYS_MECHANICAL_CLI")
    if explicit and Path(explicit).exists():
        return Path(explicit)
    cli = ROOT / ".venv" / "Scripts" / "ansys-mechanical.exe"
    if cli.exists():
        return cli
    return None


def detect_workbench_environment() -> dict[str, Any]:
    wb = find_workbench_exe()
    mech_cli = find_mechanical_cli()
    ansys_root = os.environ.get("ANSYS_ROOT")
    return {
        "workbench_exe": str(wb) if wb else None,
        "workbench_available": wb is not None,
        "mechanical_cli": str(mech_cli) if mech_cli else None,
        "mechanical_cli_available": mech_cli is not None,
        "ansys_root": ansys_root,
        "jobs_dir": str(WORKBENCH_JOBS_DIR),
    }


def _job_dir(job_id: str) -> Path:
    return WORKBENCH_JOBS_DIR / job_id


def _meta_path(job_id: str) -> Path:
    return _job_dir(job_id) / "job.json"


def _normalize_path(path: str, must_exist: bool = True) -> Path:
    resolved = Path(path).expanduser().resolve()
    if must_exist and not resolved.exists():
        raise FileNotFoundError(str(resolved))
    return resolved


def launch_workbench_journal(
    journal_path: str,
    cwd: str | None = None,
    batch: bool = True,
    extra_args: list[str] | None = None,
) -> dict[str, Any]:
    """Launch a Workbench journal asynchronously and return a job id."""
    try:
        wb = find_workbench_exe()
        if not wb:
            return {
                "status": "error",
                "error": "RunWB2.exe not found. Set ANSYS_WB_EXE or ANSYS_ROOT in .env.",
            }

        journal = _normalize_path(journal_path)
        run_cwd = _normalize_path(cwd, must_exist=True) if cwd else journal.parent
    except Exception as exc:
        return {"status": "error", "error": str(exc)}

    job_id = "wb_" + uuid.uuid4().hex[:12]
    job_dir = _job_dir(job_id)
    _safe_mkdir(job_dir)
    stdout_path = job_dir / "stdout.log"
    stderr_path = job_dir / "stderr.log"

    cmd = [str(wb)]
    if batch:
        cmd.append("-B")
    cmd.extend(["-R", str(journal)])
    if extra_args:
        cmd.extend(extra_args)

    stdout_path.touch()
    stderr_path.touch()
    if os.name == "nt":
        launch_exe = cmd[0]
        launch_args = cmd[1:]
        if Path(launch_exe).suffix.lower() in {".bat", ".cmd"}:
            launch_args = [
                "/d",
                "/s",
                "/c",
                "call",
                '"' + launch_exe + '"',
                *launch_args,
            ]
            launch_exe = os.environ.get("ComSpec", "cmd.exe")
        launch_env = os.environ.copy()
        launch_env["WORKBENCH_MCP_LAUNCH_EXE"] = launch_exe
        launch_env["WORKBENCH_MCP_LAUNCH_ARGS"] = json.dumps(launch_args)
        launch_env["WORKBENCH_MCP_LAUNCH_CWD"] = str(run_cwd)
        launcher = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "$a = ConvertFrom-Json $env:WORKBENCH_MCP_LAUNCH_ARGS; "
                "$p = Start-Process -FilePath $env:WORKBENCH_MCP_LAUNCH_EXE "
                "-ArgumentList $a -WorkingDirectory $env:WORKBENCH_MCP_LAUNCH_CWD "
                "-PassThru; $p.Id",
            ],
            text=True,
            capture_output=True,
            env=launch_env,
            timeout=30,
        )
        if launcher.returncode != 0:
            raise RuntimeError(launcher.stderr.strip() or "Start-Process failed")
        pid = int(launcher.stdout.strip().splitlines()[-1])
    else:
        proc = subprocess.Popen(cmd, cwd=str(run_cwd))
        pid = proc.pid

    payload = {
        "job_id": job_id,
        "kind": "workbench_journal",
        "status": "running",
        "pid": pid,
        "command": cmd,
        "cwd": str(run_cwd),
        "journal_path": str(journal),
        "stdout": str(stdout_path),
        "stderr": str(stderr_path),
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    _write_json(_meta_path(job_id), payload)
    return payload


def launch_mechanical_script(
    script_path: str,
    revision: int = 261,
    graphical: bool = False,
    project_file: str | None = None,
    script_args: str | None = None,
) -> dict[str, Any]:
    """Launch ansys-mechanical CLI asynchronously for a Mechanical Python script."""
    try:
        cli = find_mechanical_cli()
        if not cli:
            return {
                "status": "error",
                "error": "ansys-mechanical.exe not found. Install ansys-mechanical-core in this MCP .venv.",
            }
        script = _normalize_path(script_path)
        resolved_project = str(_normalize_path(project_file)) if project_file else None
    except Exception as exc:
        return {"status": "error", "error": str(exc)}
    job_id = "mech_" + uuid.uuid4().hex[:12]
    job_dir = _job_dir(job_id)
    _safe_mkdir(job_dir)
    stdout_path = job_dir / "stdout.log"
    stderr_path = job_dir / "stderr.log"

    cmd = [str(cli), "-r", str(revision), "-i", str(script)]
    if graphical:
        cmd.append("-g")
    else:
        cmd.append("--exit")
    if project_file:
        cmd.extend(["--project-file", resolved_project])
    if script_args:
        cmd.extend(["--script-args", script_args])

    stdout_path.touch()
    stderr_path.touch()
    if os.name == "nt":
        launch_env = os.environ.copy()
        launch_env["WORKBENCH_MCP_LAUNCH_EXE"] = cmd[0]
        launch_env["WORKBENCH_MCP_LAUNCH_ARGS"] = json.dumps(cmd[1:])
        launch_env["WORKBENCH_MCP_LAUNCH_CWD"] = str(script.parent)
        launcher = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "$a = ConvertFrom-Json $env:WORKBENCH_MCP_LAUNCH_ARGS; "
                "$p = Start-Process -FilePath $env:WORKBENCH_MCP_LAUNCH_EXE "
                "-ArgumentList $a -WorkingDirectory $env:WORKBENCH_MCP_LAUNCH_CWD "
                "-PassThru; $p.Id",
            ],
            text=True,
            capture_output=True,
            env=launch_env,
            timeout=30,
        )
        if launcher.returncode != 0:
            raise RuntimeError(launcher.stderr.strip() or "Start-Process failed")
        pid = int(launcher.stdout.strip().splitlines()[-1])
    else:
        proc = subprocess.Popen(cmd, cwd=str(script.parent))
        pid = proc.pid

    payload = {
        "job_id": job_id,
        "kind": "mechanical_script",
        "status": "running",
        "pid": pid,
        "command": cmd,
        "cwd": str(script.parent),
        "script_path": str(script),
        "stdout": str(stdout_path),
        "stderr": str(stderr_path),
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    _write_json(_meta_path(job_id), payload)
    return payload


def get_workbench_job_status(job_id: str) -> dict[str, Any]:
    meta = _meta_path(job_id)
    if not meta.exists():
        return {"status": "not_found", "job_id": job_id}
    payload = _read_json(meta)
    if payload.get("status") == "running":
        pid = int(payload.get("pid", 0))
        if pid and _process_running(pid):
            return payload
        payload["status"] = "completed_or_exited"
        payload["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        _write_json(meta, payload)
    return payload


def read_workbench_job_log(job_id: str, stream: str = "stdout", tail_chars: int = 12000) -> dict[str, Any]:
    status = get_workbench_job_status(job_id)
    if status.get("status") == "not_found":
        return status
    key = "stderr" if stream.lower() == "stderr" else "stdout"
    path = Path(status.get(key, ""))
    if not path.exists():
        return {"job_id": job_id, "stream": key, "error": f"log file missing: {path}"}
    text = path.read_text(encoding="utf-8", errors="replace")
    return {
        "job_id": job_id,
        "stream": key,
        "path": str(path),
        "tail": text[-int(tail_chars):],
        "status": status.get("status"),
    }


def list_workbench_jobs(limit: int = 20) -> dict[str, Any]:
    if not WORKBENCH_JOBS_DIR.exists():
        return {"jobs": [], "count": 0}
    jobs: list[dict[str, Any]] = []
    for meta in sorted(WORKBENCH_JOBS_DIR.glob("*/job.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            jobs.append(get_workbench_job_status(meta.parent.name))
        except Exception as exc:
            jobs.append({"job_id": meta.parent.name, "status": "error", "error": str(exc)})
        if len(jobs) >= limit:
            break
    return {"jobs": jobs, "count": len(jobs)}
