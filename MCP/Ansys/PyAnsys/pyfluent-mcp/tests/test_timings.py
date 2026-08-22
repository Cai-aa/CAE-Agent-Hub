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

import pytest

from ansys.fluent.mcp.common import timings
from ansys.fluent.mcp.common.timings import TimingsCollector


def test_timings_collector_records_rounded_snapshot_and_summary():
    """Verify that timings collector records rounded snapshot and summary.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    collector = TimingsCollector()

    collector.record("tool", "fast", 10.123)
    collector.record("tool", "slow", 25.555, errored=True)
    collector.record("tool", "slow", 4.0)

    snapshot = collector.snapshot()["tool"]
    summary = collector.summary()["tool"]

    assert [row["key"] for row in snapshot] == ["slow", "fast"]
    assert snapshot[0] == {
        "key": "slow",
        "count": 2,
        "errors": 1,
        "total_ms": 29.55,
        "avg_ms": 14.78,
        "min_ms": 4.0,
        "max_ms": 25.55,
        "last_ms": 4.0,
    }
    assert summary == {"count": 3, "errors": 1, "total_ms": 39.68, "avg_ms": 13.23}


def test_timings_context_manager_records_success_and_error():
    """Verify that timings context manager records success and error.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    collector = TimingsCollector()

    with collector.time("backend", "get_state"):
        pass
    with pytest.raises(RuntimeError):
        with collector.time("backend", "run_code"):
            raise RuntimeError("boom")

    summary = collector.summary()["backend"]
    rows = {row["key"]: row for row in collector.snapshot()["backend"]}

    assert summary["count"] == 2
    assert summary["errors"] == 1
    assert rows["get_state"]["errors"] == 0
    assert rows["run_code"]["errors"] == 1


def test_timings_reset_clears_scopes_and_restarts_uptime():
    """Verify that timings reset clears scopes and restarts uptime.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    collector = TimingsCollector()
    collector.record("http", "GET /health", 1.0)

    assert collector.snapshot()
    collector.reset()

    assert collector.snapshot() == {}
    assert collector.summary() == {}
    assert collector.uptime_s() >= 0.0


def test_get_collector_returns_singleton(monkeypatch):
    """Verify that get collector returns singleton.

    Parameters
    ----------
    monkeypatch : Any
        Pytest fixture used to patch environment variables or dependencies.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    monkeypatch.setattr(timings, "_COLLECTOR", None)

    assert timings.get_collector() is timings.get_collector()
