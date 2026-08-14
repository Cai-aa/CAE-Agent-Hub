from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class ToolResponse:
    ok: bool
    status: str
    summary: str
    data: dict[str, Any] = field(default_factory=dict)
    artifacts: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    next_recommended_action: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def success(cls, summary: str, **kwargs: Any) -> "ToolResponse":
        return cls(True, "SUCCEEDED", summary, **kwargs)

    @classmethod
    def blocked(cls, summary: str, **kwargs: Any) -> "ToolResponse":
        return cls(False, "BLOCKED", summary, **kwargs)

    @classmethod
    def failure(cls, summary: str, **kwargs: Any) -> "ToolResponse":
        return cls(False, "FAILED", summary, **kwargs)

