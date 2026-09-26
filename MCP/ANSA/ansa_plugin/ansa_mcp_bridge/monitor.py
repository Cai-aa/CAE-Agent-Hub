"""Bounded, redacted observations. Monitoring never grants execution authority."""
from __future__ import annotations

import hashlib
import re
import time
from collections import deque

VERSION = "0.5.0"
HISTORY_LIMIT = 100
SENSITIVE = re.compile(r"token|secret|password|authorization|proof|nonce", re.I)
ASSIGNMENT = re.compile(r"(?i)(token|secret|password|authorization|api[_-]?key)([\"']?\s*[:=]\s*[\"']?)([^\s,\"'}]+)")


def timestamp():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


class Monitor:
    def __init__(self, secret=""):
        self.secret = secret
        self.started = time.monotonic()
        self.events = deque(maxlen=HISTORY_LIMIT)
        self.errors = deque(maxlen=20)
        self.sequence = 0
        self.last_request_at = None
        self.last_request_clock = None
        self.session = {}
        self.model = None
        self.last_change = None
        self.capture_changes = True
        self.revision = 0

    def safe(self, value, depth=0):
        if depth > 5:
            return "[depth limited]"
        if isinstance(value, dict):
            return {str(k)[:80]: "[redacted]" if SENSITIVE.search(str(k)) else
                    self.safe(v, depth + 1) for k, v in list(value.items())[:30]}
        if isinstance(value, (list, tuple)):
            return [self.safe(v, depth + 1) for v in value[:30]]
        if isinstance(value, str):
            text = value.replace(self.secret, "[redacted]") if self.secret else value
            return ASSIGNMENT.sub(r"\1\2[redacted]", text)[:1500]
        if value is None or isinstance(value, (bool, int, float)):
            return value
        return "[unsupported value]"

    def begin(self, method, params):
        self.sequence += 1
        self.last_request_at = timestamp()
        self.last_request_clock = time.monotonic()
        # Never retain arbitrary Python source or arbitrary result payloads.
        summary = dict(params)
        source = summary.pop("code", None)
        if isinstance(source, str):
            summary["code"] = {"bytes": len(source.encode("utf-8")),
                               "sha256": hashlib.sha256(source.encode("utf-8")).hexdigest()}
        event = {"sequence": self.sequence, "method": method,
                 "label": self.safe(params.get("step_name", params.get("operation", method))),
                 "started_at": self.last_request_at, "status": "running",
                 "parameters": self.safe(summary)}
        self.events.append(event)
        self.revision += 1
        return event

    def finish(self, event, start, result=None, error=None, before=None, after=None):
        event["elapsed_seconds"] = round(time.monotonic() - start, 3)
        event["finished_at"] = timestamp()
        event["status"] = "completed" if error is None else (
            "outcome_unknown" if "OUTCOME_UNKNOWN:" in str(error) else "failed")
        if error is not None:
            event["error"] = self.safe(f"{type(error).__name__}: {error}")
            self.add_error(event["method"], event["error"])
        if isinstance(result, dict):
            event["result"] = self.safe({k: v for k, v in result.items() if k in {
                "execution_returned", "model_effect_verified", "idempotent_replay",
                "database", "database_before", "database_after", "deck", "deck_after",
                "refreshed", "return_code", "live_step", "entity_id", "entity_type",
                "saved", "path", "counts", "errors"}})
            if result.get("idempotent_replay"):
                event["status"] = "replayed"
        if before is not None or after is not None:
            change = compare_snapshots(before, after)
            event["model_change"] = self.safe(change)
            self.last_change = event["model_change"]
        if after is not None:
            self.model = self.safe(after)
        self.revision += 1

    def add_error(self, source, message):
        self.errors.append({"at": timestamp(), "source": source, "message": self.safe(message)})
        self.revision += 1

    def export(self):
        return self.safe({"dashboard_version": VERSION, "exported_at": timestamp(),
                          "last_authenticated_request": self.last_request_at,
                          "session": self.session, "model_snapshot": self.model,
                          "last_change": self.last_change, "events": list(self.events),
                          "diagnostics": list(self.errors)}) | {
            # Lists above are bounded by their own limits, not the per-value limit.
            "events": [self.safe(e) for e in self.events],
            "notice": "Counts are not mesh quality or engineering validation. Review paths and parameters before sharing. Python source/results and credentials are excluded."}


def compare_snapshots(before, after):
    if not before or not after or before.get("error") or after.get("error"):
        return {"status": "unavailable", "before": before, "after": after}
    if (before.get("database"), before.get("deck")) != (after.get("database"), after.get("deck")):
        return {"status": "context_changed", "before": before, "after": after}
    counts = {}
    for key in before.get("counts", {}).keys() & after.get("counts", {}).keys():
        a, b = before["counts"][key], after["counts"][key]
        counts[key] = {"before": a, "after": b, "delta": b - a}
    return {"status": "partial" if before.get("errors") or after.get("errors") else "sampled",
            "counts": counts, "errors_before": before.get("errors", {}),
            "errors_after": after.get("errors", {}),
            "note": "Zero count delta does not prove unchanged properties or geometry."}
