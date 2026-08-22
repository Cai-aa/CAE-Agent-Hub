# Copyright (C) 2026 Synopsys, Inc. and ANSYS, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""PathDescriptor + describe_path domain tool — envelope contract.

The descriptor is the single unified shape every discovery tool and
every validator guard reasons about. These tests pin:

* The frozen field set and their ``None`` defaults.
* The predicate helpers (``is_parameter`` / ``is_named_object`` /
  ``is_command`` / ``is_bounded_enum`` / ``value_is_allowed`` /
  ``value_is_in_range``).
* ``from_probe`` composition — every one of the four upstream probes
  (``probe_path``, ``get_allowed_values``, template, command args)
  is optional and missing sources leave descriptor fields as ``None``.
* The ``describe_path`` domain tool — batch call, fail-soft on the
  optional probes, hard-fail only when ``probe_path`` itself errors.
"""

from __future__ import annotations

import asyncio
from typing import Any

from ansys.fluent.mcp.common.backend import Backend, BackendUnavailableError
from ansys.fluent.mcp.common.models import ConnectResult
from ansys.fluent.mcp.common.path_descriptor import (
    CommandArgument,
    PathDescriptor,
)
from ansys.fluent.mcp.solve.lib.schema_probe_tools import describe_path_impl

# ---------------------------------------------------------------------
# Stub backend
# ---------------------------------------------------------------------


class _StubBackend(Backend):
    """Backend stub that returns canned data per probe."""

    kind = "stub"
    label = "Stub"

    def __init__(
        self,
        *,
        connected: bool = True,
        probes: dict[str, dict[str, Any]] | None = None,
        allowed: dict[str, list[Any]] | None = None,
        templates: dict[str, dict[str, Any] | None] | None = None,
        command_args: dict[str, dict[str, Any] | None] | None = None,
        probe_raises: type[BaseException] | None = None,
        allowed_raises: type[BaseException] | None = None,
    ) -> None:
        super().__init__()
        self._connected = connected
        self._probes = probes or {}
        self._allowed = allowed or {}
        self._templates = templates or {}
        self._command_args = command_args or {}
        self._probe_raises = probe_raises
        self._allowed_raises = allowed_raises
        self.probe_calls: list[list[str]] = []
        self.allowed_calls: list[list[str]] = []
        self.template_calls: list[str] = []
        self.command_calls: list[str] = []

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
        if self._probe_raises is not None:
            raise self._probe_raises("boom")
        return {p: dict(self._probes.get(p, {})) for p in paths}

    async def get_allowed_values(self, paths: list[str]) -> dict[str, list[Any]]:
        self.allowed_calls.append(list(paths))
        if self._allowed_raises is not None:
            raise self._allowed_raises("boom")
        return {p: list(self._allowed.get(p, [])) for p in paths if p in self._allowed}

    async def describe_named_object_template(self, path: str) -> dict[str, Any] | None:
        self.template_calls.append(str(path))
        return self._templates.get(path)

    async def get_command_arguments(self, path: str) -> dict[str, Any] | None:
        self.command_calls.append(str(path))
        return self._command_args.get(path)


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------
# PathDescriptor dataclass shape
# ---------------------------------------------------------------------


def test_descriptor_defaults_to_none_everywhere():
    desc = PathDescriptor(path="setup.models.energy.enabled")
    assert desc.path == "setup.models.energy.enabled"
    assert desc.kind is None
    assert desc.exists is None
    assert desc.is_active is None
    assert desc.is_user_creatable is None
    assert desc.is_read_only is None
    assert desc.child_class is None
    assert desc.child_fields is None
    assert desc.allowed_values is None
    assert desc.min_value is None
    assert desc.max_value is None
    assert desc.command_arguments is None
    assert desc.utl_alternate_path is None
    assert desc.multiphase_alternate_path is None
    assert desc.notes == ()


def test_descriptor_is_frozen():
    desc = PathDescriptor(path="setup.models.energy.enabled")
    try:
        desc.kind = "Parameter"  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("PathDescriptor must be frozen")


def test_descriptor_unknown_helper():
    desc = PathDescriptor.unknown("setup.foo.bar")
    assert desc.path == "setup.foo.bar"
    assert desc.kind is None
    assert desc.exists is None


def test_descriptor_predicates_parameter():
    desc = PathDescriptor(path="x", kind="Parameter")
    assert desc.is_parameter is True
    assert desc.is_group is False
    assert desc.is_named_object is False
    assert desc.is_command is False


def test_descriptor_predicates_group():
    desc = PathDescriptor(path="x", kind="Group")
    assert desc.is_group is True
    assert desc.is_parameter is False


def test_descriptor_predicates_named_object():
    desc = PathDescriptor(path="x", kind="NamedObject")
    assert desc.is_named_object is True
    desc2 = PathDescriptor(path="x", kind="NamedObjectContainer")
    assert desc2.is_named_object is True
    desc3 = PathDescriptor(path="x", kind="ListObject")
    assert desc3.is_named_object is True


def test_descriptor_predicates_command():
    desc = PathDescriptor(path="x", kind="Command")
    assert desc.is_command is True
    desc2 = PathDescriptor(path="x", kind="Action")
    assert desc2.is_command is True


def test_descriptor_bounded_enum_flag():
    empty = PathDescriptor(path="x", kind="Parameter", allowed_values=None)
    assert empty.is_bounded_enum is False
    # Empty tuple != None; still not bounded because there is nothing to constrain against
    zeroed = PathDescriptor(path="x", kind="Parameter", allowed_values=())
    assert zeroed.is_bounded_enum is False
    full = PathDescriptor(path="x", kind="Parameter", allowed_values=("a", "b", "c"))
    assert full.is_bounded_enum is True


def test_descriptor_value_is_allowed_exact_string():
    desc = PathDescriptor(
        path="setup.models.viscous.model",
        kind="Parameter",
        allowed_values=("k-omega", "k-epsilon", "laminar"),
    )
    assert desc.value_is_allowed("k-omega") is True
    assert desc.value_is_allowed("k-epsilon") is True
    assert desc.value_is_allowed("nonsense") is False


def test_descriptor_value_is_allowed_case_insensitive_strip():
    desc = PathDescriptor(
        path="setup.models.viscous.model",
        kind="Parameter",
        allowed_values=("k-omega", "k-epsilon", "laminar"),
    )
    assert desc.value_is_allowed("  K-Omega  ") is True
    assert desc.value_is_allowed("K-EPSILON") is True


def test_descriptor_value_is_allowed_returns_none_when_unbounded():
    desc = PathDescriptor(path="x", kind="Parameter", allowed_values=None)
    assert desc.value_is_allowed("anything") is None


def test_descriptor_value_is_in_range_bidirectional():
    desc = PathDescriptor(
        path="solution.controls.under_relaxation['pressure']",
        kind="Parameter",
        min_value=0.0,
        max_value=1.0,
    )
    assert desc.value_is_in_range(0.5) is True
    assert desc.value_is_in_range(0.0) is True
    assert desc.value_is_in_range(1.0) is True
    assert desc.value_is_in_range(-0.1) is False
    assert desc.value_is_in_range(1.1) is False


def test_descriptor_value_is_in_range_open_intervals():
    desc = PathDescriptor(path="x", kind="Parameter", min_value=1.0)
    assert desc.value_is_in_range(5.0) is True
    assert desc.value_is_in_range(0.5) is False

    desc = PathDescriptor(path="x", kind="Parameter", max_value=100.0)
    assert desc.value_is_in_range(50) is True
    assert desc.value_is_in_range(200) is False


def test_descriptor_value_is_in_range_returns_none_when_unbounded():
    desc = PathDescriptor(path="x", kind="Parameter")
    assert desc.value_is_in_range(42.0) is None


def test_descriptor_value_is_in_range_returns_none_for_non_numeric():
    desc = PathDescriptor(path="x", kind="Parameter", min_value=0.0, max_value=1.0)
    assert desc.value_is_in_range("not a number") is None
    assert desc.value_is_in_range(None) is None


def test_descriptor_to_dict_round_trip_shape():
    desc = PathDescriptor(
        path="setup.models.viscous.model",
        kind="Parameter",
        exists=True,
        is_active=True,
        allowed_values=("k-omega", "k-epsilon"),
        notes=("only writable when energy=on",),
    )
    d = desc.to_dict()
    assert d["path"] == "setup.models.viscous.model"
    assert d["kind"] == "Parameter"
    assert d["exists"] is True
    assert d["allowed_values"] == ["k-omega", "k-epsilon"]
    assert d["min_value"] is None
    assert d["notes"] == ["only writable when energy=on"]
    assert d["command_arguments"] is None


# ---------------------------------------------------------------------
# from_probe composition
# ---------------------------------------------------------------------


def test_from_probe_composes_probe_only():
    desc = PathDescriptor.from_probe(
        "setup.models.energy.enabled",
        {"exists": True, "is_active": True, "kind": "Parameter"},
    )
    assert desc.exists is True
    assert desc.is_active is True
    assert desc.kind == "Parameter"
    assert desc.allowed_values is None
    assert desc.command_arguments is None


def test_from_probe_folds_allowed_values():
    desc = PathDescriptor.from_probe(
        "setup.models.viscous.model",
        {"exists": True, "is_active": True, "kind": "Parameter"},
        allowed_values=["laminar", "k-omega"],
    )
    assert desc.allowed_values == ("laminar", "k-omega")


def test_from_probe_folds_named_object_template():
    template = {
        "child_class": "VelocityInletChild",
        "fields": {"vmag": {}, "temperature": {}},
        "is_user_creatable": True,
        "is_active": True,
    }
    desc = PathDescriptor.from_probe(
        "setup.boundary_conditions.velocity_inlet",
        {"exists": True, "kind": "NamedObject"},
        template=template,
    )
    assert desc.child_class == "VelocityInletChild"
    assert desc.child_fields == ("vmag", "temperature")
    assert desc.is_user_creatable is True
    assert desc.is_active is True


def test_from_probe_folds_command_arguments():
    desc = PathDescriptor.from_probe(
        "solution.run_calculation.iterate",
        {"exists": True, "kind": "Command"},
        command_arguments={
            "argument_names": ["iter_count"],
            "arguments": {
                "iter_count": {
                    "kind": "Integer",
                    "required": True,
                    "default": 1,
                    "docstring": "Number of iterations to run.",
                }
            },
        },
    )
    assert desc.is_command
    assert desc.command_arguments is not None
    assert len(desc.command_arguments) == 1
    arg = desc.command_arguments[0]
    assert isinstance(arg, CommandArgument)
    assert arg.name == "iter_count"
    assert arg.required is True
    assert arg.default == 1


def test_from_probe_missing_sources_leaves_none():
    # Only path — every downstream field must be None (not [], not "")
    desc = PathDescriptor.from_probe("setup.foo", None)
    assert desc.kind is None
    assert desc.exists is None
    assert desc.is_active is None
    assert desc.allowed_values is None
    assert desc.command_arguments is None
    assert desc.child_class is None
    assert desc.child_fields is None


def test_from_probe_folds_utl_and_multiphase_alternates():
    desc = PathDescriptor.from_probe(
        "setup.boundary_conditions.wall['w']",
        {"exists": True, "is_active": True, "kind": "NamedObject"},
        utl_alternate_path="setup.physics.boundaries.wall['w']",
        multiphase_alternate_path=(
            "setup.boundary_conditions.wall['w'].phase['air'].multiphase.volume_fraction.value"
        ),
    )
    assert desc.utl_alternate_path == "setup.physics.boundaries.wall['w']"
    assert (
        desc.multiphase_alternate_path == "setup.boundary_conditions.wall['w'].phase['air']"
        ".multiphase.volume_fraction.value"
    )


# ---------------------------------------------------------------------
# describe_path domain tool
# ---------------------------------------------------------------------


def test_describe_path_composes_batch():
    backend = _StubBackend(
        probes={
            "setup.models.viscous.model": {
                "exists": True,
                "is_active": True,
                "is_user_creatable": False,
                "kind": "Parameter",
            },
            "setup.boundary_conditions.velocity_inlet": {
                "exists": True,
                "is_active": True,
                "is_user_creatable": True,
                "kind": "NamedObject",
            },
            "solution.run_calculation.iterate": {
                "exists": True,
                "is_active": True,
                "kind": "Command",
            },
        },
        allowed={
            "setup.models.viscous.model": [
                "laminar",
                "k-omega",
                "k-epsilon",
            ]
        },
        templates={
            "setup.boundary_conditions.velocity_inlet": {
                "child_class": "VelocityInletChild",
                "fields": {"vmag": {}, "temperature": {}},
                "is_user_creatable": True,
                "is_active": True,
            }
        },
        command_args={
            "solution.run_calculation.iterate": {
                "argument_names": ["iter_count"],
                "arguments": {
                    "iter_count": {
                        "kind": "Integer",
                        "required": True,
                        "default": 1,
                    }
                },
            }
        },
    )
    out = _run(
        describe_path_impl(
            backend,
            paths=[
                "setup.models.viscous.model",
                "setup.boundary_conditions.velocity_inlet",
                "solution.run_calculation.iterate",
            ],
        )
    )
    assert out["status"] == "ok"
    assert out["connected"] is True
    results = out["results"]

    # Parameter path — allowed values folded in
    param = results["setup.models.viscous.model"]
    assert param["kind"] == "Parameter"
    assert param["is_active"] is True
    assert param["allowed_values"] == ["laminar", "k-omega", "k-epsilon"]
    assert param["command_arguments"] is None
    assert param["child_class"] is None

    # NamedObject path — template folded in
    named = results["setup.boundary_conditions.velocity_inlet"]
    assert named["kind"] == "NamedObject"
    assert named["is_user_creatable"] is True
    assert named["child_class"] == "VelocityInletChild"
    assert set(named["child_fields"]) == {"vmag", "temperature"}
    assert named["command_arguments"] is None

    # Command path — arguments folded in
    cmd = results["solution.run_calculation.iterate"]
    assert cmd["kind"] == "Command"
    assert cmd["command_arguments"] is not None
    assert len(cmd["command_arguments"]) == 1
    assert cmd["command_arguments"][0]["name"] == "iter_count"


def test_describe_path_rejects_empty_paths():
    backend = _StubBackend()
    out = _run(describe_path_impl(backend, paths=[]))
    assert out["status"] == "error"
    assert out["error_code"] == "invalid_arguments"


def test_describe_path_requires_live_session():
    backend = _StubBackend(connected=False)
    out = _run(describe_path_impl(backend, paths=["x"]))
    assert out["status"] == "error"
    assert out["error_code"] == "no_session"
    assert out["connected"] is False


def test_describe_path_hard_fails_when_probe_path_fails():
    backend = _StubBackend(probe_raises=BackendUnavailableError)
    out = _run(describe_path_impl(backend, paths=["x"]))
    assert out["status"] == "error"
    assert out["error_code"] == "backend_unavailable"


def test_describe_path_hard_fails_when_probe_path_raises_generic():
    backend = _StubBackend(probe_raises=RuntimeError)
    out = _run(describe_path_impl(backend, paths=["x"]))
    assert out["status"] == "error"
    assert out["error_code"] == "probe_failed"


def test_describe_path_fails_soft_on_allowed_values_error():
    # allowed_values probe raises — descriptor for that path still
    # composes, allowed_values just stays None.
    backend = _StubBackend(
        probes={
            "setup.models.viscous.model": {
                "exists": True,
                "is_active": True,
                "kind": "Parameter",
            }
        },
        allowed_raises=RuntimeError,
    )
    out = _run(describe_path_impl(backend, paths=["setup.models.viscous.model"]))
    assert out["status"] == "ok"
    assert out["results"]["setup.models.viscous.model"]["allowed_values"] is None


def test_describe_path_skips_template_for_non_named_objects():
    backend = _StubBackend(
        probes={
            "setup.models.viscous.model": {
                "exists": True,
                "is_active": True,
                "kind": "Parameter",
            }
        }
    )
    _run(describe_path_impl(backend, paths=["setup.models.viscous.model"]))
    # No template call for a Parameter kind
    assert backend.template_calls == []
    # And no command-args call
    assert backend.command_calls == []


def test_describe_path_skips_command_args_when_disabled():
    backend = _StubBackend(
        probes={
            "solution.run_calculation.iterate": {
                "exists": True,
                "is_active": True,
                "kind": "Command",
            }
        },
        command_args={
            "solution.run_calculation.iterate": {
                "argument_names": ["iter_count"],
                "arguments": {"iter_count": {}},
            }
        },
    )
    out = _run(
        describe_path_impl(
            backend,
            paths=["solution.run_calculation.iterate"],
            include_command_arguments=False,
        )
    )
    assert backend.command_calls == []
    assert out["results"]["solution.run_calculation.iterate"]["command_arguments"] is None


def test_describe_path_registered_in_domain_tool_catalogue():
    """The tool must be in the canonical catalogue with the expected description."""
    from ansys.fluent.mcp.solve.lib.domain_tools import get_solve_domain_tools

    names = {tool.spec.name for tool in get_solve_domain_tools()}
    assert "describe_path" in names
