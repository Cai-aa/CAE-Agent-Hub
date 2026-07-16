from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any


MAX_REQUEST_BYTES = 1_048_576


@dataclass
class PendingCall:
    request_id: str
    method: str
    params: dict[str, Any]
    completed: threading.Event = field(default_factory=threading.Event)
    response: dict[str, Any] | None = None
    cancelled: bool = False


def success(request_id: str, result: Any) -> dict[str, Any]:
    return {"id": request_id, "ok": True, "result": result}


def failure(request_id: str, code: str, message: str) -> dict[str, Any]:
    return {
        "id": request_id,
        "ok": False,
        "error": {"code": code, "message": message},
    }
