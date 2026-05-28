from __future__ import annotations

import json
import os
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

JOBS_DIR = Path(os.environ.get("FLUENT_MCP_JOBS_DIR", os.environ.get("JOBS_DIR", ROOT / "jobs")))
FLUENT_JOBS_DIR = JOBS_DIR / "fluent"


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


def find_fluent_exe() -> Path | None:
    """Find fluent.exe from env vars and common ANSYS install locations."""
    explicit = os.environ.get("FLUENT_EXE") or os.environ.get("ANSYS_FLUENT_EXE")
    if explicit and Path(explicit).exists():
        return Path(explicit)

    candidates: list[Path] = []
    ansys_root = os.environ.get("ANSYS_ROOT")
    if ansys_root:
        root = Path(ansys_root)
        candidates.extend(
            [
                root / "fluent" / "ntbin" / "win64" / "fluent.exe",
                root / "Fluent" / "ntbin" / "win64" / "fluent.exe",
            ]
        )

    for key, value in os.environ.items():
        if key.upper().startswith("AWP_ROOT"):
            root = Path(value)
            candidates.extend(
                [
                    root / "fluent" / "ntbin" / "win64" / "fluent.exe",
                    root / "Fluent" / "ntbin" / "win64" / "fluent.exe",
                ]
            )

    candidates.extend([Path("C:/Program Files/ANSYS Inc"), Path("C:/Program Files/Ansys Inc")])

    for candidate in candidates:
        if candidate.is_file():
            return candidate
        if candidate.is_dir():
            found = _find_under(candidate, "fluent.exe")
            if found:
                return found
    return None


def _pyfluent_available() -> dict[str, Any]:
    try:
        import ansys.fluent.core as pyfluent

        return {
            "available": True,
            "module": "ansys.fluent.core",
            "version": getattr(pyfluent, "__version__", None),
        }
    except Exception as exc:
        return {"available": False, "module": "ansys.fluent.core", "error": str(exc)}


def detect_fluent_environment() -> dict[str, Any]:
    fluent_exe = find_fluent_exe()
    return {
        "fluent_exe": str(fluent_exe) if fluent_exe else None,
        "fluent_available": fluent_exe is not None,
        "ansys_root": os.environ.get("ANSYS_ROOT"),
        "fluent_version": os.environ.get("FLUENT_VERSION"),
        "jobs_dir": str(FLUENT_JOBS_DIR),
        "pyfluent": _pyfluent_available(),
    }


def _normalize_dimension_precision(dimension: str | int = "3", precision: str = "double") -> str:
    value = str(dimension).strip().lower()
    if value in {"2", "2d", "2-dimensional", "2d2d"}:
        base = "2d"
    elif value in {"3", "3d", "3-dimensional", "3d3d"}:
        base = "3d"
    elif value in {"2ddp", "3ddp", "2d", "3d"}:
        return value
    else:
        raise ValueError("dimension must be 2, 2d, 3, 3d, 2ddp, or 3ddp")

    if str(precision).strip().lower() in {"double", "dp", "double-precision", "double_precision"}:
        return base + "dp"
    return base


def _normalize_path(path: str | Path, must_exist: bool = True) -> Path:
    resolved = Path(path).expanduser().resolve()
    if must_exist and not resolved.exists():
        raise FileNotFoundError(str(resolved))
    return resolved


def build_fluent_batch_command(
    fluent_exe: str | Path,
    journal_path: str | Path,
    dimension: str | int = "3",
    precision: str = "double",
    processor_count: int = 2,
    extra_args: list[str] | None = None,
) -> list[str]:
    exe = _normalize_path(fluent_exe)
    journal = _normalize_path(journal_path)
    processors = max(1, int(processor_count))
    command = [
        str(exe),
        _normalize_dimension_precision(dimension, precision),
        "-g",
        f"-t{processors}",
        "-i",
        str(journal),
    ]
    if extra_args:
        command.extend(str(arg) for arg in extra_args)
    return command


def _job_dir(job_id: str, jobs_dir: str | Path | None = None) -> Path:
    root = Path(jobs_dir) if jobs_dir is not None else FLUENT_JOBS_DIR
    return root / job_id


def _meta_path(job_id: str, jobs_dir: str | Path | None = None) -> Path:
    return _job_dir(job_id, jobs_dir) / "job.json"


def launch_fluent_journal(
    journal_path: str,
    cwd: str | None = None,
    fluent_exe: str | None = None,
    dimension: str | int = "3",
    precision: str = "double",
    processor_count: int = 2,
    extra_args: list[str] | None = None,
    jobs_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Launch a Fluent journal asynchronously and return a job id."""
    try:
        exe = Path(fluent_exe).expanduser().resolve() if fluent_exe else find_fluent_exe()
        if not exe or not exe.exists():
            return {
                "status": "error",
                "error": "fluent.exe not found. Set FLUENT_EXE or ANSYS_ROOT in .env.",
            }
        journal = _normalize_path(journal_path)
        run_cwd = _normalize_path(cwd, must_exist=True) if cwd else journal.parent
        command = build_fluent_batch_command(exe, journal, dimension, precision, processor_count, extra_args)
    except Exception as exc:
        return {"status": "error", "error": str(exc)}

    job_id = "fluent_" + uuid.uuid4().hex[:12]
    job_dir = _job_dir(job_id, jobs_dir)
    _safe_mkdir(job_dir)
    stdout_path = job_dir / "stdout.log"
    stderr_path = job_dir / "stderr.log"

    stdout = stdout_path.open("w", encoding="utf-8", errors="replace")
    stderr = stderr_path.open("w", encoding="utf-8", errors="replace")
    proc = subprocess.Popen(
        command,
        cwd=str(run_cwd),
        stdout=stdout,
        stderr=stderr,
        stdin=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    stdout.close()
    stderr.close()

    payload = {
        "job_id": job_id,
        "kind": "fluent_journal",
        "status": "running",
        "pid": proc.pid,
        "command": command,
        "cwd": str(run_cwd),
        "journal_path": str(journal),
        "stdout": str(stdout_path),
        "stderr": str(stderr_path),
        "metadata_path": str(_meta_path(job_id, jobs_dir)),
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    _write_json(_meta_path(job_id, jobs_dir), payload)
    return payload


def get_fluent_job_status(job_id: str, jobs_dir: str | Path | None = None) -> dict[str, Any]:
    meta = _meta_path(job_id, jobs_dir)
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


def read_fluent_job_log(job_id: str, stream: str = "stdout", tail_chars: int = 12000) -> dict[str, Any]:
    status = get_fluent_job_status(job_id)
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


def list_fluent_jobs(limit: int = 20) -> dict[str, Any]:
    if not FLUENT_JOBS_DIR.exists():
        return {"jobs": [], "count": 0}
    jobs: list[dict[str, Any]] = []
    for meta in sorted(FLUENT_JOBS_DIR.glob("*/job.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            jobs.append(get_fluent_job_status(meta.parent.name))
        except Exception as exc:
            jobs.append({"job_id": meta.parent.name, "status": "error", "error": str(exc)})
        if len(jobs) >= limit:
            break
    return {"jobs": jobs, "count": len(jobs)}
