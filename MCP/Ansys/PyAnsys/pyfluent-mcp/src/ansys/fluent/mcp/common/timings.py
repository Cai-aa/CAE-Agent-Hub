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

"""Lightweight in-process latency collector for the gateway.

The attribute "the system feels slow" must be attributed to the right layer:
HTTP endpoint, tool dispatch, or live Fluent backend call. Doing that
with logs alone is hard because the user has to scroll a noisy file.
This module keeps a fixed-size counter table per scope and exposes
it through ``GET /v1/diagnostics/timings``.

Design constraints
------------------

* **Always-on, near-zero overhead.** A timed block does one
  ``time.perf_counter()`` pair plus three dictionary updates under a single
  ``threading.Lock``. No allocations per call are made beyond the key string
  the caller already has.
* **Bounded memory.** Each scope (``http``/``tool``/ ``backend``)
  keeps at most ``_MAX_KEYS`` distinct keys (1024). When the table is
  full, new keys are silently dropped. Stale-but-bounded is preferred over
  unbounded growth.
* **No external deps.** Stdlib only. The collector is importable from
  any module without pulling in FastAPI, PyFluent, or asyncio.
* **Reset on demand.** ``GET /v1/diagnostics/timings?reset=true``
  clears the counters automatically so the user can take a fresh sample
  around a specific user action.

Records kept per (scope, key)
-----------------------------

* ``count``: Number of completed calls.
* ``total_ms``: Cumulative wall time.
* ``min_ms`` / ``max_ms``: Extremes.
* ``last_ms``: Most recent sample (helps catch cold-start outliers).
* ``errors``: Number of calls that left the timed block via an
  exception. The elapsed time is still recorded so a slow failure
  doesn't disappear from the table.
"""

from __future__ import annotations

from contextlib import contextmanager
import threading
import time
from typing import Iterator

# Hard cap on distinct keys per scope. Trips only on pathological
# usage (e.g. a tool that mints a fresh key per call).
_MAX_KEYS = 1024


class _Bucket:
    __slots__ = ("count", "total_ms", "min_ms", "max_ms", "last_ms", "errors")

    def __init__(self) -> None:
        """Initialize the _Bucket instance.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        self.count = 0
        self.total_ms = 0.0
        self.min_ms = float("inf")
        self.max_ms = 0.0
        self.last_ms = 0.0
        self.errors = 0

    def record(self, elapsed_ms: float, *, errored: bool) -> None:
        """Record timing information for an operation.

        Parameters
        ----------
        elapsed_ms : float
            Elapsed ms to supply to the function.
        errored : bool
            Whether to enable or apply errored.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        self.count += 1
        self.total_ms += elapsed_ms
        if elapsed_ms < self.min_ms:
            self.min_ms = elapsed_ms
        if elapsed_ms > self.max_ms:
            self.max_ms = elapsed_ms
        self.last_ms = elapsed_ms
        if errored:
            self.errors += 1

    def to_dict(self) -> dict[str, float | int]:
        """Convert the object to a dictionary representation.

        Returns
        -------
        dict[str, float | int]
            Mapping containing the operation result.
        """
        avg = (self.total_ms / self.count) if self.count else 0.0
        return {
            "count": self.count,
            "errors": self.errors,
            "total_ms": round(self.total_ms, 2),
            "avg_ms": round(avg, 2),
            "min_ms": round(self.min_ms, 2) if self.count else 0.0,
            "max_ms": round(self.max_ms, 2),
            "last_ms": round(self.last_ms, 2),
        }


class TimingsCollector:
    """Process-wide singleton. Thread-safe. No async is required."""

    def __init__(self) -> None:
        """Initialize the ``TimingsCollector`` instance.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        self._lock = threading.Lock()
        self._scopes: dict[str, dict[str, _Bucket]] = {}
        self._started_at = time.time()

    # -- recording ----------------------------------------------------

    def record(self, scope: str, key: str, elapsed_ms: float, *, errored: bool = False) -> None:
        """Record timing information for an operation.

        Parameters
        ----------
        scope : str
            Scope to supply to the function.
        key : str
            Key for looking up or storing the associated value.
        elapsed_ms : float
            Elapsed milliseconds to supply to the function.
        errored : bool
            Whether to enable or apply errored.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        with self._lock:
            table = self._scopes.get(scope)
            if table is None:
                table = {}
                self._scopes[scope] = table
            bucket = table.get(key)
            if bucket is None:
                if len(table) >= _MAX_KEYS:
                    # Bounded memory: drop new key, but still update an
                    # ``__overflow__`` counter so the user sees that
                    # something is being dropped.
                    overflow = table.get("__overflow__")
                    if overflow is None:
                        overflow = _Bucket()
                        table["__overflow__"] = overflow
                    overflow.record(elapsed_ms, errored=errored)
                    return
                bucket = _Bucket()
                table[key] = bucket
            bucket.record(elapsed_ms, errored=errored)

    @contextmanager
    def time(self, scope: str, key: str) -> Iterator[None]:
        """Context manager: ``with timings.time('tool', name): ...``.

        Parameters
        ----------
        scope : str
            Scope to limit the field or API lookup.
        key : str
            Key to supply to the function.

        Returns
        -------
        Iterator[None]
            Result produced by the function.
        """
        t0 = time.perf_counter()
        errored = False
        try:
            yield
        except BaseException:
            errored = True
            raise
        finally:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            self.record(scope, key, elapsed_ms, errored=errored)

    # -- inspection ---------------------------------------------------

    def snapshot(self) -> dict[str, list[dict[str, float | int | str]]]:
        """Return a JSON-friendly view, sorted by the ``total_ms`` description per scope.

        This approach ensures the slow paths sit at the top.

        Returns
        -------
        dict[str, list[dict[str, float | int | str]]]
            Mapping containing the operation result.
        """
        out: dict[str, list[dict[str, float | int | str]]] = {}
        with self._lock:
            for scope, table in self._scopes.items():
                rows = []
                for key, bucket in table.items():
                    row = {"key": key, **bucket.to_dict()}
                    rows.append(row)
                rows.sort(key=lambda r: r["total_ms"], reverse=True)
                out[scope] = rows
        return out

    def summary(self) -> dict[str, dict[str, float | int]]:
        """One row per scope with totals, providing a cheap top-line metric.

        Returns
        -------
        dict[str, dict[str, float | int]]
            Mapping containing the operation result.
        """
        out: dict[str, dict[str, float | int]] = {}
        with self._lock:
            for scope, table in self._scopes.items():
                count = sum(b.count for b in table.values())
                total = sum(b.total_ms for b in table.values())
                errors = sum(b.errors for b in table.values())
                out[scope] = {
                    "count": count,
                    "errors": errors,
                    "total_ms": round(total, 2),
                    "avg_ms": round(total / count, 2) if count else 0.0,
                }
        return out

    def uptime_s(self) -> float:
        """Return process uptime in seconds.

        Returns
        -------
        float
            Floating-point result produced by the operation.
        """
        return round(time.time() - self._started_at, 2)

    def reset(self) -> None:
        """Reset collected timing information.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        with self._lock:
            self._scopes.clear()
            self._started_at = time.time()


# Module-level singleton used by every recorder.
_COLLECTOR: TimingsCollector | None = None


def get_collector() -> TimingsCollector:
    """Return the collector.

    Returns
    -------
    TimingsCollector
        TimingsCollector produced by the operation.
    """
    global _COLLECTOR
    if _COLLECTOR is None:
        _COLLECTOR = TimingsCollector()
    return _COLLECTOR


__all__ = ["TimingsCollector", "get_collector"]
