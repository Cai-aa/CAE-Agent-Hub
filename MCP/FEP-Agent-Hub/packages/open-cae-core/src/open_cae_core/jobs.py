from __future__ import annotations

import json
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class Job:
    id: str
    kind: str
    status: str = "PENDING"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    data: dict[str, Any] = field(default_factory=dict)


class JobStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def create(self, kind: str, **data: Any) -> Job:
        job = Job(uuid.uuid4().hex[:12], kind, data=data)
        self.save(job)
        return job

    def save(self, job: Job) -> None:
        job.updated_at = datetime.now(timezone.utc).isoformat()
        with self._lock:
            records = self._read()
            records[job.id] = asdict(job)
            self.path.write_text(json.dumps(records, indent=2), encoding="utf-8")

    def get(self, job_id: str) -> Job | None:
        record = self._read().get(job_id)
        return Job(**record) if record else None

    def _read(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

