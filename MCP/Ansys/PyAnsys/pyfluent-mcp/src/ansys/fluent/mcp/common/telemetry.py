# Copyright (C) 2026 Synopsys, Inc. and ANSYS, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Telemetry hook.

Centralized place to emit per-step events from MCP host interactions:

* ``tool_call``: Every tool invocation
* ``host_turn``: Every host round-trip, when the caller reports one
* ``validation_end``: Final outcome of a validation request

Default implementation logs at INFO via :mod:`logging` in a structured
JSON line so consumers (such as Application Insights and OpenTelemetry collectors)
can scrape without installing extra dependencies. Replace via
:func:`set_default_telemetry` to forward elsewhere.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import json
import logging
import time
from typing import Any, Optional

logger = logging.getLogger("ansys.fluent.mcp.telemetry")


class Telemetry(ABC):
    """Pluggable telemetry sink."""

    @abstractmethod
    def emit(self, event: str, fields: dict[str, Any]) -> None:
        """Emit a telemetry event.

        Parameters
        ----------
        event : str
            Telemetry or logging event name to record.
        fields : dict[str, Any]
            Structured fields attached to the telemetry event.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        ...


class LoggingTelemetry(Telemetry):
    """Default sink that writes one JSON line per event at the INFO level."""

    def __init__(self, *, level: int = logging.INFO) -> None:
        """Initialize the LoggingTelemetry instance.

        Parameters
        ----------
        level : int
            Logging level or severity to apply.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        self._level = level

    def emit(self, event: str, fields: dict[str, Any]) -> None:
        """Emit a telemetry event.

        Parameters
        ----------
        event : str
            Telemetry or logging event name to record.
        fields : dict[str, Any]
            Structured fields attached to the telemetry event.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        logger.disabled = False
        if not logger.isEnabledFor(self._level):
            return
        payload = {"event": event, "ts": time.time(), **_safe_fields(fields)}
        try:
            line = json.dumps(payload, default=str, ensure_ascii=False)
        except (TypeError, ValueError):
            line = repr(payload)
        logger.log(self._level, "telemetry %s", line)


class NullTelemetry(Telemetry):
    """Discard everything (used in tests where logging is noise)."""

    def emit(self, event: str, fields: dict[str, Any]) -> None:  # noqa: D401
        """Emit a telemetry event.

        Parameters
        ----------
        event : str
            Telemetry or logging event name to record.
        fields : dict[str, Any]
            Structured fields attached to the telemetry event.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        return None


def _safe_fields(fields: dict[str, Any]) -> dict[str, Any]:
    """Truncate any oversized strings so a single tool result blob does not blow up log lines.

    Parameters
    ----------
    fields : dict[str, Any]
        Fields to supply to the function.

    Returns
    -------
    dict[str, Any]
        Mapping containing the operation result.
    """
    out: dict[str, Any] = {}
    for k, v in fields.items():
        if isinstance(v, str) and len(v) > 1024:
            out[k] = v[:1024] + f"…[+{len(v) - 1024} chars]"
        else:
            out[k] = v
    return out


# ---------------------------------------------------------------------------
# Singleton helper
# ---------------------------------------------------------------------------


_default: Optional[Telemetry] = None


def get_default_telemetry() -> Telemetry:
    """Return the default telemetry.

    Returns
    -------
    Telemetry
        Telemetry produced by the operation.
    """
    global _default
    if _default is None:
        _default = LoggingTelemetry()
    return _default


def set_default_telemetry(sink: Optional[Telemetry]) -> None:
    """Override the default sink. Pass ``None`` to reset to logging.

    Parameters
    ----------
    sink : Optional[Telemetry]
        Sink to supply to the function.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    global _default
    _default = sink


__all__ = [
    "Telemetry",
    "LoggingTelemetry",
    "NullTelemetry",
    "get_default_telemetry",
    "set_default_telemetry",
]
