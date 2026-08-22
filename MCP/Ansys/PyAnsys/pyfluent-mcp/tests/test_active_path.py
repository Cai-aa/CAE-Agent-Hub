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

"""Unit table for the deterministic active-path resolver.

Locks the forward resolution (logical setting -> active path) and the
reverse routing (proposed path + mode -> active? + correct sibling) for
every mode-dependent setting class the resolver knows.
"""

from __future__ import annotations

import pytest

from ansys.fluent.mcp.solve.lib.active_path import (
    MULTI_PATH_CLASSES,
    SolverMode,
    UrfFamily,
    active_urf_family,
    bc_path,
    classify_methods_gate,
    classify_path,
    cz_root,
    describe_mode,
    format_mode_summary,
    interface_root,
    is_coupled_scheme,
    multiphase_bc_phase_path,
    multiphase_volume_fraction_path,
    reroute,
    resolve_write_target,
    run_calculation_path,
    urf_path,
    write_target_hints,
)

SEG = SolverMode()  # default: standard, steady, segregated
COUPLED = SolverMode(flow_scheme="Coupled")
COUPLED_PT = SolverMode(flow_scheme="Coupled", pseudo_transient=True)
UTL = SolverMode(utl=True)
TRANSIENT = SolverMode(transient=True)


# ---------------------------------------------------------------------------
# SolverMode construction
# ---------------------------------------------------------------------------


def test_solver_mode_from_state_reads_canonical_paths():
    state = {
        "setup.general.solver.time": "unsteady-1st-order",
        "setup.general.solver.type": "density-based",
        "solution.methods.p_v_coupling.flow_scheme": "Coupled",
        "solution.methods.pseudo_time_method.formulation.coupled_solver": True,
        "setup.models.multiphase.model": "vof",
        "setup.models.viscous.model": "k-omega",
        "setup.models.energy.enabled": True,
    }
    mode = SolverMode.from_state(state, utl=True, phases=("phase-1", "phase-2"))
    assert mode.transient is True
    assert mode.density_based is True
    assert mode.coupled is True
    assert mode.pseudo_transient is True
    assert mode.multiphase_model == "vof"
    assert mode.multiphase is True
    assert mode.turbulence_model == "k-omega"
    assert mode.energy is True
    assert mode.utl is True
    assert mode.phases == ("phase-1", "phase-2")


def test_solver_mode_defaults_are_simplest():
    m = SolverMode()
    assert (m.utl, m.transient, m.coupled, m.pseudo_transient, m.multiphase) == (
        False,
        False,
        False,
        False,
        False,
    )


def test_solver_mode_from_backend_state_nested_shape():
    # PyFluent backend.get_state() returns nested dicts keyed by
    # slash-separated node paths — the adapter must flatten them.
    raw = {
        "setup/general/solver": {"time": "unsteady-1st-order", "type": "density-based"},
        "solution/methods/p-v-coupling": {"flow_scheme": "Coupled"},
        "solution/methods/pseudo-time-method/formulation": {"coupled_solver": True},
        "setup/models/multiphase": {"model": "vof"},
        "setup/models/viscous": {"model": "k-omega"},
        "setup/models/energy": {"enabled": True},
    }
    mode = SolverMode.from_backend_state(
        raw,
        utl=True,
        phases=("water", "air"),
    )
    assert mode.transient is True
    assert mode.density_based is True
    assert mode.coupled is True
    assert mode.pseudo_transient is True
    assert mode.multiphase_model == "vof"
    assert mode.turbulence_model == "k-omega"
    assert mode.energy is True
    assert mode.utl is True
    assert mode.phases == ("water", "air")


def test_solver_mode_from_backend_state_tolerates_inactive_and_missing():
    raw = {
        "setup/general/solver": {"time": "steady", "type": "pressure-based"},
        "setup/models/viscous": {"inactive": True},
        "setup/models/energy": {"error": "unreachable"},
        "setup/models/multiphase": {"model": None},
    }
    mode = SolverMode.from_backend_state(raw)
    assert mode.transient is False
    assert mode.density_based is False
    assert mode.turbulence_model is None
    assert mode.energy is False
    assert mode.multiphase_model is None


def test_solver_mode_from_backend_state_accepts_dotted_flat_shape_too():
    flat = {
        "setup.general.solver.time": "steady",
        "setup.general.solver.type": "pressure-based",
        "solution.methods.p_v_coupling.flow_scheme": "SIMPLE",
        "setup.models.energy.enabled": False,
    }
    mode = SolverMode.from_backend_state(flat)
    assert mode.transient is False
    assert mode.coupled is False
    assert mode.energy is False


def test_solver_mode_from_backend_state_empty_returns_simplest_defaults():
    assert SolverMode.from_backend_state(None) == SolverMode()
    assert SolverMode.from_backend_state({}) == SolverMode()


@pytest.mark.parametrize(
    "scheme,coupled",
    [
        ("SIMPLE", False),
        ("SIMPLEC", False),
        ("PISO", False),
        ("Fractional Step", False),
        ("Coupled", True),
        ("coupled", True),
        ("Phase Coupled SIMPLE", True),
        ("phase-coupled-simple", True),
        (None, False),
    ],
)
def test_is_coupled_scheme(scheme, coupled):
    assert is_coupled_scheme(scheme) is coupled


# ---------------------------------------------------------------------------
# URF forward resolution
# ---------------------------------------------------------------------------


def test_active_urf_family_by_mode():
    assert active_urf_family(SEG) is UrfFamily.SEGREGATED
    assert active_urf_family(COUPLED) is UrfFamily.COUPLED_EXPLICIT
    assert active_urf_family(COUPLED_PT) is UrfFamily.PSEUDO_TIME


@pytest.mark.parametrize(
    "mode,eq,expected",
    [
        (SEG, "pressure", "solution.controls.under_relaxation['pressure']"),
        (SEG, "momentum", "solution.controls.under_relaxation['mom']"),
        (SEG, "vof", "solution.controls.under_relaxation['mp']"),
        (SEG, "energy", "solution.controls.under_relaxation['temperature']"),
        (
            COUPLED,
            "pressure",
            "solution.controls.p_v_controls.explicit_pressure_under_relaxation",
        ),
        (
            COUPLED,
            "momentum",
            "solution.controls.p_v_controls.explicit_momentum_under_relaxation",
        ),
        (COUPLED, "k", "solution.controls.relaxation_factor['k']"),
        (
            COUPLED_PT,
            "k",
            "solution.controls.pseudo_time_explicit_relaxation_factor.global_dt_pseudo_relax['k']",
        ),
        (
            COUPLED_PT,
            "temperature",
            "solution.controls.pseudo_time_explicit_relaxation_factor"
            ".global_dt_pseudo_relax['temperature']",
        ),
    ],
)
def test_urf_path_forward(mode, eq, expected):
    assert urf_path(mode, eq) == expected


# ---------------------------------------------------------------------------
# URF reverse routing — the validator's deterministic core
# ---------------------------------------------------------------------------


def test_segregated_urf_under_coupled_is_rerouted():
    res = reroute("solution.controls.under_relaxation['pressure']", COUPLED)
    assert res.active is False
    assert res.correct_path == ("solution.controls.p_v_controls.explicit_pressure_under_relaxation")
    assert res.group == "urf"
    assert res.active_family == "coupled_explicit"


def test_segregated_urf_under_coupled_pseudo_time_is_rerouted():
    res = reroute("solution.controls.under_relaxation['k']", COUPLED_PT)
    assert res.active is False
    assert res.correct_path == (
        "solution.controls.pseudo_time_explicit_relaxation_factor.global_dt_pseudo_relax['k']"
    )


def test_coupled_explicit_urf_under_segregated_is_rerouted():
    res = reroute("solution.controls.p_v_controls.explicit_momentum_under_relaxation", SEG)
    assert res.active is False
    assert res.correct_path == "solution.controls.under_relaxation['mom']"


def test_segregated_urf_under_segregated_is_active():
    res = reroute("solution.controls.under_relaxation['pressure']", SEG)
    assert res.active is True
    assert res.correct_path is None


def test_coupled_explicit_urf_under_coupled_is_active():
    res = reroute("solution.controls.p_v_controls.explicit_pressure_under_relaxation", COUPLED)
    assert res.active is True


# ---------------------------------------------------------------------------
# UTL BC / CZ / interface reverse routing
# ---------------------------------------------------------------------------


def test_standard_bc_under_utl_is_rerouted():
    res = reroute("setup.boundary_conditions.wall['hw'].thermal.temperature.value", UTL)
    assert res.active is False
    assert res.correct_path == ("setup.physics.boundaries.wall['hw'].thermal.temperature.value")
    assert res.group == "bc"


def test_utl_bc_under_standard_is_rerouted():
    res = reroute("setup.physics.boundaries.wall['hw'].thermal.temperature.value", SEG)
    assert res.active is False
    assert res.correct_path == ("setup.boundary_conditions.wall['hw'].thermal.temperature.value")


def test_standard_bc_under_standard_is_active():
    res = reroute("setup.boundary_conditions.velocity_inlet['in']", SEG)
    assert res.active is True


def test_cell_zone_namespace_reroute():
    res = reroute("setup.cell_zone_conditions.fluid['f1']", UTL)
    assert res.active is False
    assert res.correct_path == "setup.physics.volumes.fluid['f1']"


# ---------------------------------------------------------------------------
# Run command reverse routing
# ---------------------------------------------------------------------------


def test_iterate_under_transient_is_rerouted():
    res = reroute("solution.run_calculation.iterate", TRANSIENT)
    assert res.active is False
    assert res.correct_path == "solution.run_calculation.dual_time_iterate"


def test_dual_time_iterate_under_steady_is_rerouted():
    res = reroute("solution.run_calculation.dual_time_iterate", SEG)
    assert res.active is False
    assert res.correct_path == "solution.run_calculation.iterate"


def test_iterate_under_steady_is_active():
    assert reroute("solution.run_calculation.iterate", SEG).active is True


# ---------------------------------------------------------------------------
# Unknown / non-multipath paths are never blocked
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "setup.models.energy.enabled",
        "setup.models.viscous.model",
        "solution.methods.p_v_coupling.flow_scheme",
        "results.surfaces.plane_surface['p1']",
        "",
    ],
)
def test_unknown_paths_are_active(path):
    res = reroute(path, COUPLED_PT)
    assert res.active is True
    assert res.correct_path is None
    assert classify_path(path) is None


# ---------------------------------------------------------------------------
# Forward namespace helpers
# ---------------------------------------------------------------------------


def test_namespace_helpers_track_utl():
    assert bc_path(SEG, "wall", "hw") == "setup.boundary_conditions.wall['hw']"
    assert bc_path(UTL, "wall", "hw") == "setup.physics.boundaries.wall['hw']"
    assert cz_root(SEG) == "setup.cell_zone_conditions"
    assert cz_root(UTL) == "setup.physics.volumes"
    assert interface_root(SEG) == "setup.mesh_interfaces"
    assert interface_root(UTL) == "setup.physics.interfaces"


def test_run_calculation_path_by_mode():
    assert run_calculation_path(SEG) == "solution.run_calculation.iterate"
    assert run_calculation_path(TRANSIENT) == "solution.run_calculation.dual_time_iterate"


def test_multiphase_volume_fraction_path():
    p = multiphase_volume_fraction_path(SEG, "velocity_inlet", "in", "phase-2")
    assert p == (
        "setup.boundary_conditions.velocity_inlet['in']"
        ".phase['phase-2'].multiphase.volume_fraction.value"
    )
    p_utl = multiphase_volume_fraction_path(UTL, "velocity_inlet", "in", "phase-2")
    assert p_utl.startswith("setup.physics.boundaries.velocity_inlet['in'].phase['phase-2']")


# ---------------------------------------------------------------------------
# Registry invariants
# ---------------------------------------------------------------------------


def test_multi_path_registry_covers_all_groups():
    ids = {row["id"] for row in MULTI_PATH_CLASSES}
    assert {
        "urf",
        "bc",
        "cz",
        "interface",
        "run",
        "multiphase_vf",
        "multiphase_bc_phase",
        "methods_gate",
    } <= ids
    for row in MULTI_PATH_CLASSES:
        assert row["selectors"], row
        assert row["resolver"], row
        assert row["families"], row


# ---------------------------------------------------------------------------
# Generic per-phase BC path (mixture-vs-per-phase leaf routing)
# ---------------------------------------------------------------------------


def test_multiphase_bc_phase_path_default_volume_fraction():
    p = multiphase_bc_phase_path(
        SEG,
        "velocity_inlet",
        "in",
        "water-liquid",
        leaf="volume_fraction",
    )
    assert p == (
        "setup.boundary_conditions.velocity_inlet['in']"
        ".phase['water-liquid'].multiphase.volume_fraction.value"
    )


def test_multiphase_bc_phase_path_backflow_variant():
    p = multiphase_bc_phase_path(
        SEG,
        "pressure_outlet",
        "out",
        "air",
        leaf="backflow_volume_fraction",
    )
    assert p.endswith(".phase['air'].multiphase.backflow_volume_fraction.value")


def test_multiphase_bc_phase_path_utl_namespace():
    p = multiphase_bc_phase_path(
        UTL,
        "velocity_inlet",
        "in",
        "phase-2",
        leaf="volume_fraction",
    )
    assert p.startswith("setup.physics.boundaries.velocity_inlet['in']")


def test_multiphase_bc_phase_path_non_multiphase_scope_no_value_suffix():
    # Turbulence per-phase leaves live under a different scope and are
    # structural (no .value suffix).
    p = multiphase_bc_phase_path(
        SEG,
        "velocity_inlet",
        "in",
        "primary",
        leaf="turb_intensity",
        scope="turbulence",
        value_suffix=False,
    )
    assert p == (
        "setup.boundary_conditions.velocity_inlet['in'].phase['primary'].turbulence.turb_intensity"
    )


def test_multiphase_volume_fraction_path_delegates_to_generic():
    a = multiphase_volume_fraction_path(SEG, "velocity_inlet", "in", "ph1")
    b = multiphase_bc_phase_path(
        SEG,
        "velocity_inlet",
        "in",
        "ph1",
        leaf="volume_fraction",
    )
    assert a == b


# ---------------------------------------------------------------------------
# solution.methods.* mode-gated leaves
# ---------------------------------------------------------------------------


DBNS = SolverMode(density_based=True)


def test_classify_methods_gate_hits_density_based_only_leaves():
    hit = classify_methods_gate("solution.methods.flux_type")
    assert hit is not None
    assert hit[0] == "density_based"


def test_classify_methods_gate_hits_pseudo_time_only_leaves():
    hit = classify_methods_gate(
        "solution.methods.pseudo_time_method.local_dt_pseudo_relaxation_factor.pressure",
    )
    assert hit is not None
    assert hit[0] in ("coupled_scheme", "coupled_pseudo")


def test_classify_methods_gate_returns_none_for_untracked_paths():
    assert classify_methods_gate("solution.methods.p_v_coupling.flow_scheme") is None
    assert classify_methods_gate("setup.models.energy.enabled") is None


def test_resolve_write_target_surfaces_methods_gate_reason_when_inactive():
    # flux_type is a density-based-only knob; on a pressure-based case
    # the resolver must flag it as classified + inactive-with-reason,
    # NOT hard-block (no correct sibling exists).
    t = resolve_write_target(SEG, "solution.methods.flux_type")
    assert t.classified is True
    assert t.group == "methods_gate"
    assert t.active_family == "density_based"
    assert t.reason  # human-readable
    assert t.needs_reroute is False
    assert t.active_path == "solution.methods.flux_type"


def test_resolve_write_target_no_reason_when_methods_gate_active():
    t = resolve_write_target(DBNS, "solution.methods.flux_type")
    assert t.classified is True
    assert t.reason == ""


def test_resolve_write_target_passthrough_for_non_classified():
    t = resolve_write_target(SEG, "setup.models.energy.enabled")
    assert t.classified is False
    assert t.needs_reroute is False


# ---------------------------------------------------------------------------
# describe_mode / write_target_hints / format_mode_summary
# ---------------------------------------------------------------------------


def test_describe_mode_captures_full_facet_set():
    m = SolverMode(
        transient=True,
        density_based=True,
        flow_scheme="Coupled",
        pseudo_transient=True,
        multiphase_model="vof",
        phases=("water", "air"),
        turbulence_model="k-omega",
        energy=True,
        utl=True,
    )
    d = describe_mode(m)
    assert d["time"] == "transient"
    assert d["solver_type"] == "density-based"
    assert d["coupled"] is True
    assert d["pseudo_transient"] is True
    assert d["urf_family"] == "pseudo_time"
    assert d["bc_namespace"] == "utl"
    assert d["multiphase"] == {"model": "vof", "phases": ["water", "air"]}
    assert d["turbulence_model"] == "k-omega"
    assert d["energy"] is True


def test_describe_mode_single_phase_returns_none_multiphase():
    d = describe_mode(SEG)
    assert d["multiphase"] is None
    assert d["solver_type"] == "pressure-based"


def test_pressure_based_property_is_opposite_of_density_based():
    assert SEG.pressure_based is True
    assert DBNS.pressure_based is False


def test_write_target_hints_segregated_uses_under_relaxation_root():
    h = write_target_hints(SEG)
    assert h["urf_family"] == "segregated"
    assert h["urf_root"] == "solution.controls.under_relaxation"
    assert h["run_calculation_path"] == "solution.run_calculation.iterate"
    assert h["bc_root"] == "setup.boundary_conditions"
    assert h["multiphase"] is None


def test_write_target_hints_coupled_pseudo_uses_global_dt_root():
    h = write_target_hints(COUPLED_PT)
    assert h["urf_family"] == "pseudo_time"
    assert h["urf_root"].startswith("solution.controls.pseudo_time_explicit_relaxation_factor")


def test_write_target_hints_multiphase_emits_per_phase_template():
    m = SolverMode(
        multiphase_model="vof",
        phases=("water", "air"),
        utl=False,
    )
    h = write_target_hints(m)
    assert h["multiphase"]["model"] == "vof"
    assert h["multiphase"]["phases"] == ["water", "air"]
    assert "phase['<phase>']" in h["multiphase"]["per_phase_bc_template"]
    assert "multiphase.<leaf>" in h["multiphase"]["per_phase_bc_template"]
    # Mixture-level template does NOT include the phase indexer.
    assert "phase[" not in h["multiphase"]["mixture_level_bc_template"]


def test_write_target_hints_multiphase_utl_uses_physics_root():
    m = SolverMode(
        multiphase_model="vof",
        phases=("water", "air"),
        utl=True,
    )
    h = write_target_hints(m)
    assert h["multiphase"]["per_phase_bc_template"].startswith(
        "setup.physics.boundaries.",
    )


def test_format_mode_summary_is_two_lines_and_covers_essentials():
    m = SolverMode(
        multiphase_model="vof",
        phases=("water", "air"),
        flow_scheme="Coupled",
        pseudo_transient=True,
        turbulence_model="k-omega",
        energy=True,
    )
    text = format_mode_summary(m)
    lines = text.split("\n")
    assert len(lines) == 2
    assert "SOLVER MODE:" in lines[0]
    assert "multiphase=vof" in lines[0]
    assert "turbulence=k-omega" in lines[0]
    assert "URF root:" in lines[1]
    assert "run command:" in lines[1]
    assert "per-phase BC leaves:" in lines[1]


def test_format_mode_summary_single_phase_omits_multiphase_block():
    text = format_mode_summary(SEG)
    assert "multiphase=" not in text
    assert "per-phase BC leaves:" not in text
