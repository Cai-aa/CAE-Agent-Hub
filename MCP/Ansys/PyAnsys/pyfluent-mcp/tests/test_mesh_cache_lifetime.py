# Copyright (C) 2026 Synopsys, Inc. and ANSYS, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for the mesh-probe cache lifetime contract.

Mesh probes (``mesh_quality`` / ``mesh_check`` / ``mesh_counts``) live
in a separate ``_mesh_cache`` bucket that MUST survive across
``invalidate_live_caches`` calls — physics/settings ``run_code``
snippets do not change the mesh, so re-probing on every Apply is
wasted work.

Only the following operations drop the mesh cache:

* :meth:`Backend.invalidate_mesh_cache` (explicit).
* :meth:`Backend.invalidate_cache` (full reset — used by connect /
  disconnect flows).
* :meth:`Backend.maybe_invalidate_mesh_cache` when the ``run_code``
  snippet contains a mesh-mutation marker
  (``file.read_case``, ``mesh.replace``, ``mesh.adapt.``, ...).

The failure mode this guards against: after every ``finalize``/Apply
the runner's post-apply followup fires
``probe_session_insights(backend)``, which internally calls
``backend.mesh_quality()`` and ``backend.mesh_check()``. Before this
contract, ``invalidate_live_caches`` dropped the mesh cache on every
``run_code``, so the mesh probes re-ran ``session.settings.mesh.quality()``
and ``session.settings.mesh.check()`` after every physics write — the
exact noise the user reported ("I still see post finalize, every time
it checks mesh quality and mesh size").
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from ansys.fluent.mcp.common.backend import Backend
from ansys.fluent.mcp.common.errors import BackendUnavailableError
from ansys.fluent.mcp.common.models import RunCodeResult
from ansys.fluent.mcp.solve.backends import pyfluent as pyfluent_backend_module


class _StubBackend(Backend):
    """Minimal Backend subclass — exercises the base-class cache contract."""

    kind = "stub"
    label = "Stub backend"

    async def connect(self, **kwargs):  # pragma: no cover - unused
        raise BackendUnavailableError("stub")

    async def disconnect(self) -> None:  # pragma: no cover - unused
        return None

    def is_connected(self) -> bool:  # pragma: no cover - unused
        return False

    async def status(self):  # pragma: no cover - unused
        raise BackendUnavailableError("stub")


# ----------------------------------------------------------------------
# Base contract — mesh cache split from generic cache
# ----------------------------------------------------------------------


def test_mesh_cache_is_separate_from_generic_cache():
    """``_mesh_cache`` MUST be a distinct bucket, not aliased to ``_cache``."""
    backend = _StubBackend()
    assert backend._mesh_cache is not backend._cache
    backend._cache_put("k", "v")
    assert backend._mesh_cache_get("k") is None
    backend._mesh_cache_put("k", "mv")
    assert backend._mesh_cache_get("k") == "mv"
    assert backend._cache_get("k", ttl=60.0) == "v"


def test_invalidate_live_caches_preserves_mesh_cache():
    """``invalidate_live_caches`` runs on every ``run_code``; must NOT drop mesh."""
    backend = _StubBackend()
    backend._mesh_cache_put("mesh_quality", {"min_orthogonal_quality": 0.5})
    backend._cache_put("named_objects", ["a", "b"])
    backend.invalidate_live_caches()
    assert backend._cache_get("named_objects", ttl=60.0) is None
    assert backend._mesh_cache_get("mesh_quality") == {"min_orthogonal_quality": 0.5}


def test_invalidate_mesh_cache_drops_only_mesh_cache():
    backend = _StubBackend()
    backend._mesh_cache_put("mesh_quality", {"x": 1})
    backend._cache_put("named_objects", ["a"])
    backend.invalidate_mesh_cache()
    assert backend._mesh_cache_get("mesh_quality") is None
    assert backend._cache_get("named_objects", ttl=60.0) == ["a"]


def test_invalidate_cache_clears_both_buckets():
    """``invalidate_cache`` is a full reset (used by disconnect flows)."""
    backend = _StubBackend()
    backend._mesh_cache_put("mesh_quality", {"x": 1})
    backend._cache_put("named_objects", ["a"])
    backend.invalidate_cache()
    assert backend._mesh_cache_get("mesh_quality") is None
    assert backend._cache_get("named_objects", ttl=60.0) is None


# ----------------------------------------------------------------------
# Mesh-mutation marker detection
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "code",
    [
        "session.settings.file.read_case('case.cas.h5')",
        "session.settings.file.read_mesh('mesh.msh.h5')",
        "session.settings.file.read_case_data('case.cas.h5')",
        "session.settings.file.replace_mesh('new.msh.h5')",
        "session.settings.mesh.replace('foo')",
        "session.settings.mesh.modify_zones.append_mesh(...)",
        "session.settings.mesh.modify_zones.remesh(...)",
        "session.settings.mesh.adapt.refine_mesh()",
        "session.settings.mesh.repair_improve.improve_quality()",
        "session.settings.solution.run_calculation.mesh_motion(...)",
    ],
)
def test_maybe_invalidate_mesh_cache_matches_mutation_markers(code: str):
    backend = _StubBackend()
    backend._mesh_cache_put("mesh_quality", {"x": 1})
    assert backend.maybe_invalidate_mesh_cache(code) is True
    assert backend._mesh_cache_get("mesh_quality") is None


@pytest.mark.parametrize(
    "code",
    [
        "session.settings.setup.models.multiphase.model = 'mixture'",
        "session.settings.setup.boundary_conditions.velocity_inlet['inlet1']"
        ".phase['phase-2'].set_state(...)",
        "session.settings.solution.methods.p_v_coupling.flow_scheme = 'SIMPLE'",
        "session.settings.setup.materials.fluid['air'].density.value = 1.2",
        "session.settings.mesh.quality()",  # READ, not a mutation
        "session.settings.mesh.check()",  # READ, not a mutation
        "session.settings.results.graphics.contour['c1'].display()",
    ],
)
def test_maybe_invalidate_mesh_cache_leaves_non_mutating_code_alone(code: str):
    """Physics writes / graphics / mesh READS must NOT drop the mesh cache."""
    backend = _StubBackend()
    backend._mesh_cache_put("mesh_quality", {"x": 1})
    assert backend.maybe_invalidate_mesh_cache(code) is False
    assert backend._mesh_cache_get("mesh_quality") == {"x": 1}


def test_maybe_invalidate_mesh_cache_handles_empty_code():
    backend = _StubBackend()
    backend._mesh_cache_put("k", "v")
    assert backend.maybe_invalidate_mesh_cache("") is False
    assert backend.maybe_invalidate_mesh_cache(None) is False  # type: ignore[arg-type]
    assert backend._mesh_cache_get("k") == "v"


# ----------------------------------------------------------------------
# PyFluent backend — mesh probes hit ``_mesh_cache`` and survive
# a physics ``run_code``.
# ----------------------------------------------------------------------


def _make_pyfluent_backend() -> pyfluent_backend_module.PyFluentBackend:
    backend = pyfluent_backend_module.PyFluentBackend()
    backend._solver = SimpleNamespace(settings=SimpleNamespace())
    return backend


def test_pyfluent_mesh_quality_survives_physics_run_code(monkeypatch):
    """Physics ``run_code`` MUST NOT re-fire ``session.settings.mesh.quality()``."""
    backend = _make_pyfluent_backend()

    quality_text = (
        "Minimum Orthogonal Quality = 2.5e-01\n"
        "Maximum Ortho skew = 7.5e-01\n"
        "Maximum Aspect Ratio = 1.2e+01"
    )
    run_code_calls: list[str] = []

    async def _fake_run_code(code: str) -> RunCodeResult:
        run_code_calls.append(code)
        if "mesh.quality" in code:
            return RunCodeResult(status="ok", stdout=quality_text)
        return RunCodeResult(status="ok", stdout="")

    monkeypatch.setattr(backend, "run_code", _fake_run_code)

    first = asyncio.run(backend.mesh_quality())
    assert first["min_orthogonal_quality"] == pytest.approx(0.25)
    assert run_code_calls == ["session.settings.mesh.quality()"]

    # Simulate a physics write on the same session — this drops the
    # generic ``_cache`` via ``invalidate_live_caches`` but MUST NOT
    # drop the mesh cache.
    backend.invalidate_live_caches()

    second = asyncio.run(backend.mesh_quality())
    assert second == first
    # No new call — the mesh probe was served from cache.
    assert run_code_calls == ["session.settings.mesh.quality()"]


def test_pyfluent_mesh_check_survives_physics_run_code(monkeypatch):
    backend = _make_pyfluent_backend()

    check_text = "Mesh check succeeded.\nDone."
    run_code_calls: list[str] = []

    async def _fake_run_code(code: str) -> RunCodeResult:
        run_code_calls.append(code)
        return RunCodeResult(status="ok", stdout=check_text)

    monkeypatch.setattr(backend, "run_code", _fake_run_code)

    first = asyncio.run(backend.mesh_check())
    assert first["raw"] == check_text
    assert run_code_calls == ["session.settings.mesh.check()"]

    backend.invalidate_live_caches()

    second = asyncio.run(backend.mesh_check())
    assert second == first
    assert run_code_calls == ["session.settings.mesh.check()"]


def test_pyfluent_mesh_cache_drops_on_case_read(monkeypatch):
    """A new case load DOES change the mesh — the cache must invalidate."""
    backend = _make_pyfluent_backend()

    quality_text = (
        "Minimum Orthogonal Quality = 2.5e-01\n"
        "Maximum Ortho skew = 7.5e-01\n"
        "Maximum Aspect Ratio = 1.2e+01"
    )
    run_code_calls: list[str] = []

    async def _fake_run_code(code: str) -> RunCodeResult:
        run_code_calls.append(code)
        return RunCodeResult(status="ok", stdout=quality_text)

    monkeypatch.setattr(backend, "run_code", _fake_run_code)

    asyncio.run(backend.mesh_quality())
    assert len(run_code_calls) == 1

    # Simulate the mesh-mutation trigger: a fresh case load.
    backend.maybe_invalidate_mesh_cache("session.settings.file.read_case('new_case.cas.h5')")
    assert backend._mesh_cache_get("mesh_quality") is None

    asyncio.run(backend.mesh_quality())
    assert len(run_code_calls) == 2  # re-probed after mesh mutation


def test_pyfluent_mesh_counts_uses_mesh_cache():
    backend = _make_pyfluent_backend()

    call_counter = {"n": 0}

    class _CountingScheme:
        def eval(self, _expr):
            call_counter["n"] += 1
            return [1000, 3000, 500]

    backend._solver = SimpleNamespace(scheme=_CountingScheme())

    first = asyncio.run(backend.mesh_counts())
    assert first == {"cell_count": 1000, "face_count": 3000, "node_count": 500}
    assert call_counter["n"] == 1

    # Physics write path — invalidate live caches; mesh_counts survives.
    backend.invalidate_live_caches()

    second = asyncio.run(backend.mesh_counts())
    assert second == first
    assert call_counter["n"] == 1


def test_pyfluent_mesh_counts_all_none_is_not_cached():
    """An all-``None`` payload = "no mesh loaded"; don't pin it."""
    backend = _make_pyfluent_backend()

    class _EmptyScheme:
        def eval(self, _expr):
            return []

    backend._solver = SimpleNamespace(scheme=_EmptyScheme())
    result = asyncio.run(backend.mesh_counts())
    assert result == {"cell_count": None, "face_count": None, "node_count": None}
    assert backend._mesh_cache_get("mesh_counts") is None
