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

import asyncio
from types import SimpleNamespace

from ansys.fluent.mcp.common.models import ConnectResult, RunCodeResult
from ansys.fluent.mcp.solve.lib import compare_tools
from ansys.fluent.mcp.solve.lib.compare_tools import (
    collect_compare_snapshot,
    compare_files_impl,
    diff_snapshots,
    format_compare_summary,
    shorten_value,
    split_diff_path,
)


class _SnapshotBackend:
    async def get_state(self):
        """Return the state.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        return {"models/energy": {"enabled": True}}

    async def list_named_objects(self):
        """List named objects entries.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        return {"boundary_conditions": ["outlet", "inlet"]}


class _FailingSnapshotBackend:
    async def get_state(self):
        """Return the state.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        raise RuntimeError("state failed")

    async def list_named_objects(self):
        """List named objects entries.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        raise RuntimeError("names failed")


def test_collect_compare_snapshot_sorts_named_objects_and_captures_errors():
    """Verify that collect compare snapshot sorts named objects and captures errors.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    snapshot = asyncio.run(collect_compare_snapshot(_SnapshotBackend()))
    failed = asyncio.run(collect_compare_snapshot(_FailingSnapshotBackend()))

    assert snapshot == {
        "global": {"models/energy": {"enabled": True}},
        "named": {"boundary_conditions": ["inlet", "outlet"]},
    }
    assert failed == {"global": {"_error": "state failed"}, "named": {"_error": "names failed"}}


def test_diff_snapshots_reports_nested_changes_and_list_membership():
    """Verify that diff snapshots reports nested changes and list membership.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    diffs = diff_snapshots(
        {"global": {"solver": {"type": "pressure"}}, "named": {"bc": ["inlet", "wall"]}},
        {"global": {"solver": {"type": "density"}}, "named": {"bc": ["inlet", "outlet"]}},
    )

    assert {
        "path": "global.solver.type",
        "change": "changed",
        "a": "pressure",
        "b": "density",
    } in diffs
    assert {"path": "named.bc['wall']", "change": "only_in_a", "a": "wall"} in diffs
    assert {"path": "named.bc['outlet']", "change": "only_in_b", "b": "outlet"} in diffs


def test_rendering_helpers_format_markdown_summary():
    """Verify that rendering helpers format markdown summary.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    assert shorten_value(["a", "b"]) == "a, b"
    assert shorten_value("a|b\nc") == "a\\|b c"
    assert shorten_value(None) == "—"
    assert split_diff_path("global.setup/models.energy.enabled") == (
        "setup/models.energy",
        "enabled",
    )
    assert split_diff_path("named.boundary_conditions['inlet']") == ("boundary_conditions", "inlet")

    summary = format_compare_summary(
        [
            {
                "path": "global.setup/models.energy.enabled",
                "change": "changed",
                "a": False,
                "b": True,
            }
        ],
        name_a="a.cas.h5",
        name_b="b.cas.h5",
    )

    assert "### Differences: **a.cas.h5** vs **b.cas.h5**" in summary
    assert "| `enabled` | False | True |" in summary


def test_format_compare_summary_handles_no_differences():
    """Verify that format compare summary handles no differences.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    assert (
        format_compare_summary([], name_a="a", name_b="b")
        == "No differences between **a** and **b**."
    )


class _CompareBackend:
    def __init__(self, label, *, connect_status="ok", run_error=False, disconnect_error=False):
        """Initialize the _CompareBackend instance.

        Parameters
        ----------
        label : Any
            Human-readable label attached to the operation or test double.
        connect_status : Any
            Connection status returned by the test double.
        run_error : Any
            Exception raised by the test double during code execution.
        disconnect_error : Any
            Exception raised by the test double during disconnect.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        self.label = label
        self.connect_status = connect_status
        self.run_error = run_error
        self.disconnect_error = disconnect_error
        self.connected_with = None
        self.snippets = []
        self.disconnected = False

    async def connect(self, **kwargs):
        """Connect to the configured backend or service.

        Parameters
        ----------
        kwargs : Any
            Keyword arguments forwarded to the callable.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        self.connected_with = kwargs
        if self.connect_status != "ok":
            return ConnectResult(
                status="error", error_code="launch_failed", message="cannot launch"
            )
        return ConnectResult(status="ok", backend_kind="pyfluent")

    async def run_code(self, snippet):
        """Execute Python code through the backend runtime.

        Parameters
        ----------
        snippet : Any
            Code snippet supplied to the operation under test.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        self.snippets.append(snippet)
        if self.run_error:
            return RunCodeResult(status="error", error_code="read_failed", message="cannot read")
        return RunCodeResult(status="ok")

    async def get_state(self):
        """Return the state.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        return {"setup": {"label": self.label}}

    async def list_named_objects(self):
        """List named objects entries.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        return {"bc": [self.label]}

    async def disconnect(self):
        """Close resources for the _CompareBackend object.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        self.disconnected = True
        if self.disconnect_error:
            raise RuntimeError("close failed")


def test_compare_files_impl_launches_ephemeral_sessions_and_diffs(monkeypatch, tmp_path):
    """Verify that compare files impl launches ephemeral sessions and diffs.

    Parameters
    ----------
    monkeypatch : Any
        Pytest fixture used to patch environment variables or dependencies.
    tmp_path : Any
        Path for the tmp.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    case_a = tmp_path / "a.cas.h5"
    case_b = tmp_path / "b.cas.h5"
    case_a.write_text("a")
    case_b.write_text("b")
    created = []

    def factory(label):
        """Create a test backend or handler instance.

        Parameters
        ----------
        label : Any
            Human-readable label attached to the operation or test double.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        backend = _CompareBackend(label)
        created.append(backend)
        return backend

    monkeypatch.setattr(compare_tools, "ephemeral_pyfluent_backend", factory)
    result = asyncio.run(
        compare_files_impl(SimpleNamespace(), path_a=str(case_a), path_b=str(case_b))
    )

    assert result["status"] == "ok"
    assert result["diff_count"] > 0
    assert result["path_a"] == str(case_a.resolve())
    assert result["launch"] == {
        "product": "pyfluent",
        "ui_mode": "gui",
        "precision": "double",
        "lightweight_setup": True,
    }
    assert len(created) == 2
    assert all(
        backend.connected_with == {"ui_mode": "gui", "precision": "double"} for backend in created
    )
    assert all("lightweight_setup=True" in backend.snippets[0] for backend in created)
    assert all(backend.disconnected for backend in created)


def test_compare_files_impl_validation_and_failure_paths(monkeypatch, tmp_path):
    """Verify that compare files impl validation and failure paths.

    Parameters
    ----------
    monkeypatch : Any
        Pytest fixture used to patch environment variables or dependencies.
    tmp_path : Any
        Path for the tmp.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    case_a = tmp_path / "a.cas.h5"
    case_b = tmp_path / "b.cas.h5"
    case_a.write_text("a")
    case_b.write_text("b")

    assert "path must be a non-empty" in compare_tools._validate_compare_path(" ")[1]
    assert (
        "file not found"
        in compare_tools._validate_compare_path(str(tmp_path / "missing.cas.h5"))[1]
    )
    unsupported = case_a.with_suffix(".txt")
    unsupported.write_text("x")
    assert "unsupported file type" in compare_tools._validate_compare_path(str(unsupported))[1]

    same = asyncio.run(
        compare_files_impl(SimpleNamespace(), path_a=str(case_a), path_b=str(case_a))
    )
    assert same == {"error": "path_a and path_b resolve to the same file"}

    monkeypatch.setattr(
        compare_tools,
        "ephemeral_pyfluent_backend",
        lambda label: _CompareBackend(label, connect_status="error"),
    )
    assert asyncio.run(
        compare_files_impl(SimpleNamespace(), path_a=str(case_a), path_b=str(case_b))
    )["error"] == ("failed to launch session A")

    backends = [_CompareBackend("a"), _CompareBackend("b", run_error=True, disconnect_error=True)]
    monkeypatch.setattr(compare_tools, "ephemeral_pyfluent_backend", lambda label: backends.pop(0))
    result = asyncio.run(
        compare_files_impl(SimpleNamespace(), path_a=str(case_a), path_b=str(case_b))
    )
    assert result == {"error": "failed to read b.cas.h5", "detail": "cannot read"}


def test_diff_and_format_helpers_handle_unhashable_and_root_paths():
    """Verify that diff and format helpers handle unhashable and root paths.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    diffs = diff_snapshots({"a": [["nested"]]}, {"a": [["other"]]})
    assert diffs == [{"path": "a", "change": "changed", "a": [["nested"]], "b": [["other"]]}]
    assert split_diff_path("plain") == ("", "plain")
    assert split_diff_path("a/b/c") == ("a/b", "c")
    assert shorten_value("x" * 90, limit=10) == "xxxxxxxxx…"
    summary = format_compare_summary(
        [
            {"path": "root", "change": "only_in_a", "a": {"x": 1}},
            {"path": "global.a.b", "change": "only_in_b", "b": "value"},
        ],
        name_a="a",
        name_b="b",
    )
    assert "#### (root)" in summary
    assert "| `root` | {'x': 1} | — |" in summary
