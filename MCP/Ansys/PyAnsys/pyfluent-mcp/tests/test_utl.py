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

import pytest

from ansys.fluent.mcp.solve.lib import utl


class FakeBackend:
    def __init__(self, *, connected=True, state=None, solver=None, raises=False):
        """Initialize the FakeBackend instance.

        Parameters
        ----------
        connected : Any
            Whether the fake or test backend should report an active connection.
        state : Any
            State to supply to the function.
        solver : Any
            Solver to supply to the function.
        raises : Any
            Raises to supply to the function.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        self.connected = connected
        self.state = state or {}
        self._solver = solver
        self.raises = raises
        self.invalidated = False

    def is_connected(self):
        """Return whether connected.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        return self.connected

    async def get_state(self, paths):
        """Return the state.

        Parameters
        ----------
        paths : Any
            Fluent object paths supplied to the operation.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        if self.raises:
            raise RuntimeError("probe failed")
        return self.state

    def invalidate_live_caches(self):
        """Clear cached live backend state.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        self.invalidated = True


def test_detect_utl_mode_handles_connected_states_and_failures():
    """Verify that detect utl mode handles connected states and failures.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    assert asyncio.run(utl.detect_utl_mode(None)) is None
    assert asyncio.run(utl.detect_utl_mode(FakeBackend(connected=False))) is None
    assert asyncio.run(utl.detect_utl_mode(FakeBackend(raises=True))) is None
    assert (
        asyncio.run(
            utl.detect_utl_mode(FakeBackend(state={utl.UTL_PROBE_PATH: {"inactive": True}}))
        )
        is False
    )
    assert (
        asyncio.run(
            utl.detect_utl_mode(FakeBackend(state={utl.UTL_PROBE_PATH: {"error": "missing"}}))
        )
        is None
    )
    assert (
        asyncio.run(utl.detect_utl_mode(FakeBackend(state={utl.UTL_PROBE_PATH: {"active": True}})))
        is True
    )


def test_enable_disable_utl_toggle_solver_and_invalidate_cache():
    """Verify that enable disable utl toggle solver and invalidate cache.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    calls = []
    solver = SimpleNamespace(execute_tui=lambda scheme: calls.append(scheme))
    backend = FakeBackend(solver=solver)

    assert asyncio.run(utl.enable_utl(backend)) is True
    assert asyncio.run(utl.disable_utl(backend)) is True

    assert calls == ["(enable-feature 'utl)", "(disable-feature 'utl)"]
    assert backend.invalidated is True


def test_toggle_feature_returns_false_for_unavailable_surfaces():
    """Verify that toggle feature returns false for unavailable surfaces.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    assert asyncio.run(utl.enable_utl(FakeBackend(connected=False))) is False
    assert asyncio.run(utl.enable_utl(FakeBackend(solver=None))) is False
    assert asyncio.run(utl.enable_utl(FakeBackend(solver=SimpleNamespace()))) is False

    def fail(_scheme):
        """Exercise the fail test helper.

        Parameters
        ----------
        _scheme : Any
            Scheme to supply to the function.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        raise RuntimeError("boom")

    assert (
        asyncio.run(utl.enable_utl(FakeBackend(solver=SimpleNamespace(execute_tui=fail)))) is False
    )


def test_path_family_standard_and_utl_translations():
    """Verify that path family standard and utl translations.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    standard = utl.PathFamily.from_active(False)
    active = utl.PathFamily.from_active(True)

    assert standard.kind is utl.FamilyKind.STANDARD
    assert active.kind is utl.FamilyKind.UTL
    assert standard.boundaries_root() == "setup.boundary_conditions"
    assert active.boundaries_root() == "setup.physics.boundaries"
    assert standard.volumes_root() == "setup.cell_zone_conditions"
    assert active.interfaces_root() == "setup.physics.interfaces"
    assert standard.bc_path("wall", "hot-wall") == "setup.boundary_conditions.wall['hot-wall']"
    assert active.cz_path("fluid", "fluid-1") == "setup.physics.volumes.fluid['fluid-1']"

    assert standard.wall_thermal_temperature("wall", 350) == [
        ("setup.boundary_conditions.wall['wall'].thermal.thermal_condition", "temperature"),
        ("setup.boundary_conditions.wall['wall'].thermal.temperature.value", 350),
    ]
    assert active.wall_thermal_mixed("wall", htc=12, ext_temp=300)[0] == (
        "setup.physics.boundaries.wall['wall'].thermal.thermal_condition",
        "Mixed",
    )
    assert active.wall_thermal_convection("wall", htc=8)[0][1] == "Convection"
    assert standard.velocity_inlet_speed("in", 4.5) == [
        ("setup.boundary_conditions.velocity_inlet['in'].momentum.velocity_magnitude.value", 4.5)
    ]
    assert active.velocity_inlet_temperature("in", 295) == [
        ("setup.physics.boundaries.velocity_inlet['in'].thermal.temperature.value", 295)
    ]


def test_path_family_selectors_and_utl_only_calls():
    """Verify that path family selectors and utl only calls.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    standard = utl.PathFamily.from_active(False)
    active = utl.PathFamily.from_active(True)

    assert standard.report_volume_selector("r", ["fluid"]) == [
        ("solution.report_definitions.volume['r'].cell_zones", ["fluid"])
    ]
    assert active.report_volume_selector("r", ["fluid"]) == [
        ("solution.report_definitions.volume['r'].locations.physics", ["fluid"])
    ]
    assert standard.surface_integral_args(
        ["wall"], report_of="area", file_name="out.txt", append_data=True
    ) == {
        "surface_names": ["wall"],
        "report_of": "area",
        "write_to_file": False,
        "file_name": "out.txt",
        "append_data": True,
    }
    assert active.surface_integral_args(["fluid"], write_to_file=True) == {
        "locations": {"surfaces": [], "physics": ["fluid"]},
        "write_to_file": True,
    }
    assert active.utl_volume_set_location("fluid", "fluid-group", ["fluid-1"]) == (
        "setup.physics.volumes.fluid['fluid-group'].set_location",
        {"locations": ["fluid-1"]},
    )
    assert active.utl_volume_split(
        "solid", "solid-all", into=["solid-1"], new_name="solid-part"
    ) == (
        "setup.physics.volumes.solid['solid-all'].split",
        {"locations": ["solid-1"], "name": "solid-part"},
    )
    assert active.utl_interface_create_call(name="i", boundary_1="a", boundary_2="b") == (
        "setup.physics.interfaces.create",
        {
            "name": "i",
            "boundary_1": "a",
            "boundary_2": "b",
            "intf_type": "wall",
            "mesh_connectivity": "non-conformal",
            "periodicity": "none",
        },
    )
    assert active.utl_interface_auto_create() == ("setup.physics.interfaces.auto_create", {})

    with pytest.raises(ValueError):
        standard.utl_volume_set_location("fluid", "x", [])
    with pytest.raises(ValueError):
        standard.utl_volume_split("fluid", "x", into=[], new_name="y")
    with pytest.raises(ValueError):
        standard.utl_interface_create_call(name="i", boundary_1="a", boundary_2="b")
    with pytest.raises(ValueError):
        standard.utl_interface_auto_create()


def test_translate_prefix_uses_longest_match_and_leaves_other_paths():
    """Verify that translate prefix uses longest match and leaves other paths.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    assert utl.translate_prefix("setup.boundary_conditions.wall['w']", to_utl=True) == (
        "setup.physics.boundaries.wall['w']"
    )
    assert utl.translate_prefix("setup.physics.volumes.fluid['f']", to_utl=False) == (
        "setup.cell_zone_conditions.fluid['f']"
    )
    assert utl.translate_prefix("solution.methods", to_utl=True) == "solution.methods"
