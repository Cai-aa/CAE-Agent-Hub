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

"""Schema-probe domain tools — payload shape & error contract.

The four probes (``probe_path``, ``get_active_status``,
``get_allowed_values``, ``describe_named_object_template``) all
follow the same envelope:

* ``{"status": "ok", ...}`` on success
* ``{"status": "error", "error_code": "...", "message": "..."}`` on
  failure

Each test exercises one of those branches against a minimal stub
backend so the contract is locked down independently of the
underlying PyFluent / FluidsOne backend implementations.
"""

from __future__ import annotations

import asyncio
from typing import Any

from ansys.fluent.mcp.common.backend import Backend, BackendUnavailableError
from ansys.fluent.mcp.common.models import ConnectResult
from ansys.fluent.mcp.solve.lib.schema_probe_tools import (
    describe_named_object_template_impl,
    get_active_status_impl,
    get_allowed_values_impl,
    probe_path_impl,
)


class _StubBackend(Backend):
    """Tiny backend stub that records calls and returns canned data."""

    kind = "stub"
    label = "Stub"

    def __init__(
        self,
        *,
        connected: bool = True,
        probe_result: dict[str, dict[str, Any]] | None = None,
        active_result: dict[str, bool] | None = None,
        allowed_result: dict[str, list[Any]] | None = None,
        template_result: dict[str, Any] | None = None,
        raises: type[BaseException] | None = None,
    ) -> None:
        super().__init__()
        self._connected = connected
        self._probe_result = probe_result or {}
        self._active_result = active_result or {}
        self._allowed_result = allowed_result or {}
        self._template_result = template_result
        self._raises = raises
        self.probe_calls: list[list[str]] = []
        self.active_calls: list[list[str]] = []
        self.allowed_calls: list[list[str]] = []
        self.template_calls: list[str] = []

    async def connect(self, **_: Any) -> ConnectResult:
        return ConnectResult(status="ok", backend_kind="stub", endpoint="x")

    def is_connected(self) -> bool:
        return self._connected

    async def list_named_objects(self) -> dict[str, list[str]]:
        return {}

    async def get_state(self, paths: list[str] | None = None) -> dict[str, Any]:
        return {}

    async def probe_path(self, paths: list[str]) -> dict[str, dict[str, Any]]:
        self.probe_calls.append(list(paths))
        if self._raises is not None:
            raise self._raises("boom")
        return dict(self._probe_result)

    async def get_active_status(self, paths: list[str]) -> dict[str, bool]:
        self.active_calls.append(list(paths))
        if self._raises is not None:
            raise self._raises("boom")
        return dict(self._active_result)

    async def get_allowed_values(self, paths: list[str]) -> dict[str, list[Any]]:
        self.allowed_calls.append(list(paths))
        if self._raises is not None:
            raise self._raises("boom")
        return dict(self._allowed_result)

    async def describe_named_object_template(self, path: str) -> dict[str, Any] | None:
        self.template_calls.append(str(path))
        if self._raises is not None:
            raise self._raises("boom")
        return self._template_result


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------
# probe_path
# ---------------------------------------------------------------------


def test_probe_path_returns_results():
    backend = _StubBackend(
        probe_result={
            "setup.models.energy.enabled": {
                "exists": True,
                "is_active": True,
                "is_user_creatable": False,
                "kind": "leaf",
            }
        }
    )
    out = _run(probe_path_impl(backend, paths=["setup.models.energy.enabled"]))
    assert out["status"] == "ok"
    assert out["connected"] is True
    assert "setup.models.energy.enabled" in out["results"]
    assert backend.probe_calls == [["setup.models.energy.enabled"]]


def test_probe_path_rejects_empty_paths():
    backend = _StubBackend()
    out = _run(probe_path_impl(backend, paths=[]))
    assert out["status"] == "error"
    assert out["error_code"] == "invalid_arguments"


def test_probe_path_requires_live_session():
    backend = _StubBackend(connected=False)
    out = _run(probe_path_impl(backend, paths=["x"]))
    assert out["status"] == "error"
    assert out["error_code"] == "no_session"
    assert out["connected"] is False


def test_probe_path_handles_backend_unavailable():
    backend = _StubBackend(raises=BackendUnavailableError)
    out = _run(probe_path_impl(backend, paths=["x"]))
    assert out["status"] == "error"
    assert out["error_code"] == "backend_unavailable"


def test_probe_path_handles_generic_failure():
    backend = _StubBackend(raises=RuntimeError)
    out = _run(probe_path_impl(backend, paths=["x"]))
    assert out["status"] == "error"
    assert out["error_code"] == "probe_failed"


# ---------------------------------------------------------------------
# get_active_status
# ---------------------------------------------------------------------


def test_active_status_returns_bool_map():
    backend = _StubBackend(active_result={"a": True, "b": False, "c": 1})
    out = _run(get_active_status_impl(backend, paths=["a", "b", "c"]))
    assert out["status"] == "ok"
    assert out["results"] == {"a": True, "b": False, "c": True}


def test_active_status_rejects_empty_paths():
    backend = _StubBackend()
    out = _run(get_active_status_impl(backend, paths=[]))
    assert out["error_code"] == "invalid_arguments"


def test_active_status_requires_live_session():
    backend = _StubBackend(connected=False)
    out = _run(get_active_status_impl(backend, paths=["x"]))
    assert out["error_code"] == "no_session"


# ---------------------------------------------------------------------
# get_allowed_values
# ---------------------------------------------------------------------


def test_allowed_values_returns_list_map():
    backend = _StubBackend(
        allowed_result={
            "setup.models.viscous.model": ["laminar", "k-epsilon", "k-omega"],
            "setup.cell_zone_conditions.fluid[x].material": [],
        }
    )
    out = _run(
        get_allowed_values_impl(
            backend,
            paths=[
                "setup.models.viscous.model",
                "setup.cell_zone_conditions.fluid[x].material",
            ],
        )
    )
    assert out["status"] == "ok"
    assert out["results"]["setup.models.viscous.model"] == [
        "laminar",
        "k-epsilon",
        "k-omega",
    ]
    assert out["results"]["setup.cell_zone_conditions.fluid[x].material"] == []


def test_allowed_values_coerces_non_list_to_empty():
    backend = _StubBackend(allowed_result={"x": None})  # type: ignore[arg-type]
    out = _run(get_allowed_values_impl(backend, paths=["x"]))
    assert out["status"] == "ok"
    assert out["results"]["x"] == []


def test_allowed_values_handles_backend_unavailable():
    backend = _StubBackend(raises=BackendUnavailableError)
    out = _run(get_allowed_values_impl(backend, paths=["x"]))
    assert out["error_code"] == "backend_unavailable"


# ---------------------------------------------------------------------
# describe_named_object_template
# ---------------------------------------------------------------------


def test_template_returns_dict():
    template = {
        "child_class": "VelocityInletChild",
        "is_active": True,
        "is_user_creatable": True,
        "fields": {
            "vmag": {
                "type_hint": "Real",
                "is_active": True,
                "is_read_only": False,
                "allowed_values": [],
            }
        },
    }
    backend = _StubBackend(template_result=template)
    out = _run(
        describe_named_object_template_impl(
            backend,
            path="setup.boundary_conditions.velocity_inlet",
        )
    )
    assert out["status"] == "ok"
    assert out["template"] == template
    assert backend.template_calls == ["setup.boundary_conditions.velocity_inlet"]


def test_template_rejects_empty_path():
    backend = _StubBackend()
    out = _run(describe_named_object_template_impl(backend, path=""))
    assert out["error_code"] == "invalid_arguments"


def test_template_returns_none_when_backend_returns_non_dict():
    backend = _StubBackend(template_result=None)  # type: ignore[arg-type]
    out = _run(describe_named_object_template_impl(backend, path="x"))
    assert out["status"] == "ok"
    assert out["template"] is None


def test_template_handles_generic_failure():
    backend = _StubBackend(raises=RuntimeError)
    out = _run(describe_named_object_template_impl(backend, path="x"))
    assert out["error_code"] == "probe_failed"
