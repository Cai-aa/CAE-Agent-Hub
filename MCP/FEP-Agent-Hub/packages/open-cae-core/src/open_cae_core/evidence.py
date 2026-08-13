from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class EvidenceRecorder:
    def __init__(self, project_root: str | Path) -> None:
        self.project_root = Path(project_root).resolve()
        self.root = self.project_root / "evidence"
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def append(self, filename: str, record: dict[str, Any]) -> Path:
        path = self.root / filename
        payload = {"timestamp": utc_now(), **record}
        line = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        with self._lock, path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(line + "\n")
        return path

    def tool_call(
        self,
        tool: str,
        inputs: dict[str, Any],
        result: dict[str, Any],
    ) -> Path:
        return self.append(
            "tool_calls.jsonl", {"tool": tool, "inputs": inputs, "result": result}
        )

    def command(self, record: dict[str, Any]) -> Path:
        return self.append("commands.jsonl", record)

    def hash_file(self, path: str | Path) -> dict[str, Any]:
        artifact = Path(path).resolve()
        digest = hashlib.sha256()
        with artifact.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return {
            "path": artifact.relative_to(self.project_root).as_posix(),
            "sha256": digest.hexdigest(),
            "size": artifact.stat().st_size,
        }

    def record_artifacts(self, paths: Iterable[str | Path]) -> Path:
        existing_path = self.root / "artifacts.json"
        existing: dict[str, dict[str, Any]] = {}
        if existing_path.is_file():
            try:
                payload = json.loads(existing_path.read_text(encoding="utf-8"))
                existing = {record["path"]: record for record in payload.get("artifacts", [])}
            except (json.JSONDecodeError, KeyError, TypeError):
                existing = {}
        for path in paths:
            if Path(path).is_file():
                record = self.hash_file(path)
                existing[record["path"]] = record
        records = [existing[key] for key in sorted(existing)]
        payload = {"generated_at": utc_now(), "artifacts": records}
        path = existing_path
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        hashes = self.root / "hashes.json"
        hashes.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
        return path
