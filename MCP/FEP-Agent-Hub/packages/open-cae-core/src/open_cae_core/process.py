from __future__ import annotations

import os
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

from .errors import ExecutableNotAllowed
from .evidence import EvidenceRecorder


ALLOWED_EXECUTABLES = {
    "freecadcmd.exe",
    "freecad.exe",
    "elmergrid.exe",
    "elmersolver.exe",
    "elmersolver_mpi.exe",
    "elmergui.exe",
    "mpiexec.exe",
    "gmsh.exe",
    "pvpython.exe",
    "pvbatch.exe",
    "paraview.exe",
}


@dataclass(slots=True)
class ProcessResult:
    exe: str
    args: list[str]
    cwd: str
    start: str
    end: str
    exit_code: int
    stdout_log: str
    stderr_log: str
    timed_out: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class SafeProcessRunner:
    def __init__(self, allowed: set[str] | None = None) -> None:
        self.allowed = {name.lower() for name in (allowed or ALLOWED_EXECUTABLES)}

    def run(
        self,
        exe: str | Path,
        args: Sequence[str],
        *,
        cwd: str | Path,
        stdout_log: str | Path,
        stderr_log: str | Path,
        timeout: float = 300,
        environment: Mapping[str, str] | None = None,
        evidence: EvidenceRecorder | None = None,
    ) -> ProcessResult:
        executable = Path(exe).resolve()
        if executable.name.lower() not in self.allowed:
            raise ExecutableNotAllowed(f"Executable is not whitelisted: {executable.name}")
        if not executable.is_file():
            raise FileNotFoundError(executable)

        workdir = Path(cwd).resolve()
        out_path = Path(stdout_log).resolve()
        err_path = Path(stderr_log).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        err_path.parent.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        if environment:
            env.update({str(key): str(value) for key, value in environment.items()})
        started = datetime.now(timezone.utc).isoformat()
        timed_out = False
        exit_code = -1
        try:
            with out_path.open("wb") as stdout, err_path.open("wb") as stderr:
                completed = subprocess.run(
                    [str(executable), *map(str, args)],
                    cwd=str(workdir),
                    stdin=subprocess.DEVNULL,
                    stdout=stdout,
                    stderr=stderr,
                    env=env,
                    shell=False,
                    timeout=timeout,
                    check=False,
                )
                exit_code = completed.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
            exit_code = -9
        ended = datetime.now(timezone.utc).isoformat()
        result = ProcessResult(
            exe=str(executable),
            args=[str(value) for value in args],
            cwd=str(workdir),
            start=started,
            end=ended,
            exit_code=exit_code,
            stdout_log=str(out_path),
            stderr_log=str(err_path),
            timed_out=timed_out,
        )
        if evidence:
            evidence.command(result.to_dict())
        return result
