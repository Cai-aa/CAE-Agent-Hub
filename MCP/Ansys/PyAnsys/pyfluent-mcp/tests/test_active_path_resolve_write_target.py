# Copyright (C) 2026 Synopsys, Inc. and ANSYS, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""`resolve_write_target` — canonical write-target resolver contract.

The resolver replaces the three-way disagreement between the
validator, the ``resolve_active_path`` tool, and the recipe URF
stagers on "where should this write actually land under the current
mode?". These tests pin the invariants:

* Pass-through for unclassified paths — the resolver NEVER
  false-blocks an ordinary write.
* URF family routing under segregated / coupled-explicit /
  pseudo-time modes.
* BC / cell-zone / interface UTL-vs-standard rerouting.
* Run-calculation steady vs transient rerouting.
* WriteTarget dataclass shape stability.
"""

from __future__ import annotations

import pytest

from ansys.fluent.mcp.solve.lib.active_path import (
    SolverMode,
    UrfFamily,
    WriteTarget,
    active_urf_family,
    is_coupled_scheme,
    resolve_write_target,
    urf_path,
)

# ---------------------------------------------------------------------
# Dataclass shape
# ---------------------------------------------------------------------


def test_write_target_defaults():
    t = WriteTarget(
        requested_path="setup.foo",
        active_path="setup.foo",
        needs_reroute=False,
    )
    assert t.requested_path == "setup.foo"
    assert t.active_path == "setup.foo"
    assert t.needs_reroute is False
    assert t.group is None
    assert t.active_family is None
    assert t.reason == ""
    assert t.classified is False


def test_write_target_is_frozen():
    t = WriteTarget(
        requested_path="x",
        active_path="x",
        needs_reroute=False,
    )
    with pytest.raises(Exception):
        t.needs_reroute = True  # type: ignore[misc]


# ---------------------------------------------------------------------
# Unclassified paths — pass-through
# ---------------------------------------------------------------------


def test_resolve_unclassified_path_passes_through():
    mode = SolverMode()
    t = resolve_write_target(mode, "setup.models.energy.enabled")
    assert t.needs_reroute is False
    assert t.active_path == "setup.models.energy.enabled"
    assert t.classified is False
    assert t.reason == ""


def test_resolve_empty_path_passes_through():
    mode = SolverMode()
    t = resolve_write_target(mode, "")
    assert t.needs_reroute is False
    assert t.classified is False


def test_resolve_random_scalar_leaf_passes_through():
    """Ordinary settings leaves must NOT be blocked by the resolver."""
    mode = SolverMode()
    for path in (
        "setup.models.viscous.model",
        "setup.materials.fluid['air'].density.value",
        "solution.methods.spatial_discretization.discretization_scheme['mom']",
    ):
        t = resolve_write_target(mode, path)
        assert t.needs_reroute is False, path
        assert t.classified is False, path


# ---------------------------------------------------------------------
# URF routing
# ---------------------------------------------------------------------


def test_resolve_segregated_urf_active_under_segregated_mode():
    mode = SolverMode()  # segregated (flow_scheme None → segregated default)
    t = resolve_write_target(
        mode,
        "solution.controls.under_relaxation['pressure']",
    )
    assert t.needs_reroute is False
    assert t.classified is True
    assert t.group == "urf"
    assert t.active_family == UrfFamily.SEGREGATED.value


def test_resolve_segregated_urf_reroutes_under_coupled():
    mode = SolverMode(flow_scheme="Coupled")
    t = resolve_write_target(
        mode,
        "solution.controls.under_relaxation['pressure']",
    )
    assert t.needs_reroute is True
    assert t.classified is True
    assert t.group == "urf"
    assert t.active_path == "solution.controls.p_v_controls.explicit_pressure_under_relaxation"
    assert t.active_family == UrfFamily.COUPLED_EXPLICIT.value
    assert "inactive" in t.reason


def test_resolve_coupled_scalar_urf_reroutes_under_segregated():
    mode = SolverMode()  # segregated
    t = resolve_write_target(
        mode,
        "solution.controls.p_v_controls.explicit_pressure_under_relaxation",
    )
    assert t.needs_reroute is True
    assert t.active_path == "solution.controls.under_relaxation['pressure']"


def test_resolve_pseudo_time_urf_active_under_coupled_pseudo():
    mode = SolverMode(flow_scheme="Coupled", pseudo_transient=True)
    t = resolve_write_target(
        mode,
        ("solution.controls.pseudo_time_explicit_relaxation_factor.global_dt_pseudo_relax['k']"),
    )
    assert t.needs_reroute is False
    assert t.classified is True
    assert t.active_family == UrfFamily.PSEUDO_TIME.value


def test_resolve_pseudo_time_urf_reroutes_under_coupled_no_pseudo():
    mode = SolverMode(flow_scheme="Coupled", pseudo_transient=False)
    t = resolve_write_target(
        mode,
        ("solution.controls.pseudo_time_explicit_relaxation_factor.global_dt_pseudo_relax['k']"),
    )
    assert t.needs_reroute is True
    # For k on coupled-explicit-scalar the resolver produces the
    # relaxation_factor NamedObject variant (no dedicated scalar leaf).
    assert t.active_path == "solution.controls.relaxation_factor['k']"


# ---------------------------------------------------------------------
# BC / CZ / interface UTL routing
# ---------------------------------------------------------------------


def test_resolve_standard_bc_active_under_standard():
    mode = SolverMode(utl=False)
    t = resolve_write_target(
        mode,
        "setup.boundary_conditions.wall['w']",
    )
    assert t.needs_reroute is False


def test_resolve_standard_bc_reroutes_under_utl():
    mode = SolverMode(utl=True)
    t = resolve_write_target(
        mode,
        "setup.boundary_conditions.wall['w']",
    )
    assert t.needs_reroute is True
    assert t.classified is True
    assert t.group == "bc"
    assert t.active_family == "utl"
    assert t.active_path.startswith("setup.physics.boundaries.")


def test_resolve_utl_bc_reroutes_under_standard():
    mode = SolverMode(utl=False)
    t = resolve_write_target(
        mode,
        "setup.physics.boundaries.wall['w']",
    )
    assert t.needs_reroute is True
    assert t.active_family == "standard"
    assert t.active_path.startswith("setup.boundary_conditions.")


def test_resolve_standard_cz_reroutes_under_utl():
    mode = SolverMode(utl=True)
    t = resolve_write_target(
        mode,
        "setup.cell_zone_conditions.fluid['fluid_1']",
    )
    assert t.needs_reroute is True
    assert t.group == "cz"


def test_resolve_interface_family_reroutes_across_modes():
    utl_mode = SolverMode(utl=True)
    t = resolve_write_target(
        utl_mode,
        "setup.mesh_interfaces.one_to_one['int-1']",
    )
    assert t.needs_reroute is True
    assert t.group == "interface"


# ---------------------------------------------------------------------
# Run-calculation routing
# ---------------------------------------------------------------------


def test_resolve_iterate_active_under_steady():
    mode = SolverMode()  # steady
    t = resolve_write_target(mode, "solution.run_calculation.iterate")
    assert t.needs_reroute is False
    assert t.classified is True


def test_resolve_iterate_reroutes_under_transient():
    mode = SolverMode(transient=True)
    t = resolve_write_target(mode, "solution.run_calculation.iterate")
    assert t.needs_reroute is True
    assert t.active_path == "solution.run_calculation.dual_time_iterate"


def test_resolve_dual_time_iterate_reroutes_under_steady():
    mode = SolverMode(transient=False)
    t = resolve_write_target(
        mode,
        "solution.run_calculation.dual_time_iterate",
    )
    assert t.needs_reroute is True
    assert t.active_path == "solution.run_calculation.iterate"


# ---------------------------------------------------------------------
# is_coupled_scheme cross-check (recipe helper delegates here)
# ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [
        ("Coupled", True),
        ("coupled", True),
        ("COUPLED", True),
        ("Phase Coupled SIMPLE", True),
        ("phase_coupled_simple", True),
        ("phase-coupled-simple", True),
        ("SIMPLE", False),
        ("SIMPLEC", False),
        ("PISO", False),
        ("Fractional Step", False),
        ("", False),
        (None, False),
    ],
)
def test_is_coupled_scheme_variants(value, expected):
    assert is_coupled_scheme(value) is expected


def test_urf_path_matches_write_target_active_path():
    """Every URF write-target's active_path must equal what urf_path emits directly."""
    mode = SolverMode(flow_scheme="Coupled", pseudo_transient=True)
    for eq in ("pressure", "mom", "k", "omega"):
        forward = urf_path(mode, eq)
        # A pseudo-time write to the SAME family should be pass-through
        t = resolve_write_target(mode, forward)
        assert t.needs_reroute is False, (eq, forward, t)


def test_urf_family_helper_matches_resolver():
    mode = SolverMode(flow_scheme="Coupled")
    fam = active_urf_family(mode)
    t = resolve_write_target(
        mode,
        "solution.controls.under_relaxation['pressure']",
    )
    assert t.active_family == fam.value
