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

"""UTL (Unified Topology Layer) detection, toggling, and path translation.

UTL is a Fluent beta feature that exposes a *physics-grouped* settings
namespace (``setup.physics.boundaries``,``setup.physics.volumes``,
or ``setup.physics.interfaces``) and disables the per-zone namespace
(``setup.boundary_conditions``, or ``setup.cell_zone_conditions``,
``setup.mesh_interfaces``). It is toggled at runtime via the Scheme
feature flag::

    (enable-feature 'utl)

There is **no PyFluent settings-API equivalent** for this toggle as of
Fluent 27.1 and PyFluent 0.38.1he Ansys-authored UTL regression
scripts themselves use ``solver.execute_tui("(enable-feature 'utl)")``.
This module isolates that one Scheme call in
:func:`enable_utl`/:func:`disable_utl` and documents the exception.
Every other UTL interaction goes through the PyFluent settings API.

The following empirical mapping was extracted from a live probe against
Fluent 2027 R1. See ``_probe_utl.py`` in the repository root for the raw
data.

* Canonical detection signal:
  ``solver.settings.setup.physics.is_active()``.
* When UTL is enabled, the standard families raise
  ``InactiveObjectError`` on write, which is a clean, typed failure
  the executor surfaces as a validation diagnostic rather than a
  crash.
* Several surfaces are *mode-agnostic* (active in both modes):
  ``solution.cell_registers``, ``results.surfaces.*``,
  ``solution.controls.equations``, ``setup.models.*``, and the
  scalar leaves of ``solution.report_definitions.*`` (``field``,
  ``report_type``, ``create_report_file``, ...). Recipes that touch
  only these surfaces work unchanged in both modes.
* The mode-divergent surfaces collapse to four shapes:

  * Namespace prefix
  * BC-value nesting (``.thermal.value`` versus ``.value``)
  * Value enum casing (``'temperature'`` versus ``'Temperature'``)
  * Selector form on a handful of command   arguments (``surface_names=[…]``
    versus ``locations={'physics':[…]}``)

:class:`PathFamily` encapsulates all four shapes so a single recipe template
can target both modes by calling family helpers rather than hard-coding paths.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import logging
from typing import Any

logger = logging.getLogger("ansys.fluent.mcp.common.utl")


# ---------------------------------------------------------------------------
# Canonical paths / probes
# ---------------------------------------------------------------------------

#: Path whose ``is_active()`` distinguishes UTL from standard mode.
UTL_PROBE_PATH = "setup.physics"

#: Standard-mode roots that go inactive when UTL is enabled.
STANDARD_ONLY_ROOTS: tuple[str, ...] = (
    "setup.boundary_conditions",
    "setup.cell_zone_conditions",
    "setup.mesh_interfaces",
)

#: UTL-mode roots that go inactive when UTL is disabled.
UTL_ONLY_ROOTS: tuple[str, ...] = (
    "setup.physics.boundaries",
    "setup.physics.volumes",
    "setup.physics.interfaces",
)


# ---------------------------------------------------------------------------
# Detection / toggling
# ---------------------------------------------------------------------------


async def detect_utl_mode(backend: Any) -> bool | None:
    """Return True if UTL is currently enabled on ``backend``.

    Returns ``None`` if the backend is not connected or the probe
    fails (such as against a non-PyFluent backend). Callers should
    treat ``None`` as "unknown — assume standard".

    Parameters
    ----------
    backend : Any
        Backend to supply to the function.

    Returns
    -------
    bool | None
        Boolean result produced by the function.
    """
    if backend is None or not getattr(backend, "is_connected", lambda: False)():
        return None
    try:
        state = await backend.get_state([UTL_PROBE_PATH])
    except Exception:  # probes are advisory
        return None
    val = (state or {}).get(UTL_PROBE_PATH)
    if isinstance(val, dict) and val.get("inactive") is True:
        return False
    if isinstance(val, dict) and "error" in val:
        return None
    # Anything that resolves as not-inactive means physics namespace
    # is live, which is the UTL signal.
    return val is not None


async def enable_utl(backend: Any) -> bool:
    """Enable UTL on the live session. Returns True on success.

    Uses the one sanctioned ``execute_tui`` call for the Scheme
    feature toggle. There is no settings-API equivalent in 27.1.

    Parameters
    ----------
    backend : Any
        Backend to supply to the function.

    Returns
    -------
    bool
        Boolean result produced by the function.
    """
    return await _toggle_feature(backend, "(enable-feature 'utl)")


async def disable_utl(backend: Any) -> bool:
    """Disable UTL on the live session. Returns ``True`` on success.

    Parameters
    ----------
    backend : Any
        Backend to supply to the function.

    Returns
    -------
    bool
        Boolean result produced by the function.
    """
    return await _toggle_feature(backend, "(disable-feature 'utl)")


async def _toggle_feature(backend: Any, scheme: str) -> bool:
    """Enable or disable a Fluent feature flag.

    Parameters
    ----------
    backend : Any
        Backend instance for performing the operation.
    scheme : str
        Scheme to supply to the function.

    Returns
    -------
    bool
        Boolean result of the operation.
    """
    if backend is None or not getattr(backend, "is_connected", lambda: False)():
        return False
    solver = getattr(backend, "_solver", None)
    if solver is None:
        logger.warning("utl toggle: backend has no live solver handle")
        return False
    execute_tui = getattr(solver, "execute_tui", None)
    if not callable(execute_tui):
        logger.warning("utl toggle: solver has no execute_tui")
        return False
    import asyncio

    try:
        await asyncio.to_thread(execute_tui, scheme)
    except Exception as exc:
        logger.warning("utl toggle %r failed: %s", scheme, exc)
        return False
    # Invalidate any cached named-object / state info — the active
    # namespace just flipped under us.
    try:
        backend.invalidate_live_caches()
    except Exception as exc:
        logger.warning("Failed to invalidate backend caches after UTL toggle: %s", exc)
    return True


# ---------------------------------------------------------------------------
# PathFamily — the recipe-facing translator
# ---------------------------------------------------------------------------


class FamilyKind(str, Enum):
    """Which path family is active in the target session."""

    STANDARD = "standard"
    UTL = "utl"


@dataclass(frozen=True)
class PathFamily:
    """Translate semantic operations into mode-appropriate Fluent paths.

    Recipes that want to be mode-agnostic build paths through this
    helper rather than hard-coding ``setup.boundary_conditions.…``.
    The :meth:`from_active` classmethod picks the correct family
    given a live UTL flag::

        family = PathFamily.from_active(ctx.utl_enabled)
        for path, value in family.wall_thermal_temperature("hw", 423):
            cx.set(path, value)

    All helpers return a *list of (path, value)* tuples — even single-
    write operations — because the UTL form for some BC attributes
    requires two writes (condition + value) where the standard form
    needs only one.
    """

    kind: FamilyKind

    # ---- factory ---------------------------------------------------

    @classmethod
    def from_active(cls, utl_enabled: bool | None) -> "PathFamily":
        """Create the wrapper from the active solver session.

        Parameters
        ----------
        utl_enabled : bool | None
            Utl enabled to supply to the function.

        Returns
        -------
        'PathFamily'
            'PathFamily' produced by the operation.
        """
        return cls(kind=FamilyKind.UTL if utl_enabled else FamilyKind.STANDARD)

    @property
    def is_utl(self) -> bool:
        """Return whether utl.

        Returns
        -------
        bool
            Boolean result of the operation.
        """
        return self.kind is FamilyKind.UTL

    # ---- namespace roots -------------------------------------------

    def boundaries_root(self) -> str:
        """Root path for boundary-condition families (wall, inlet, ...).

        Returns
        -------
        str
            String result produced by the function.
        """
        return "setup.physics.boundaries" if self.is_utl else "setup.boundary_conditions"

    def volumes_root(self) -> str:
        """Root path for cell-zone families (fluid, solid).

        Returns
        -------
        str
            String result produced by the function.
        """
        return "setup.physics.volumes" if self.is_utl else "setup.cell_zone_conditions"

    def interfaces_root(self) -> str:
        """Root path for mesh interfaces.

        Note: the two forms are not structurally equivalent — the
        standard form is a NamedObject collection
        (``setup.mesh_interfaces.interface[name]``) while UTL exposes
        a command collection (``setup.physics.interfaces.create``,
        ``.auto_create``). Callers that need to *create* an interface
        should use :meth:`interface_create_call` instead.

        Returns
        -------
        str
            String result produced by the function.
        """
        return "setup.physics.interfaces" if self.is_utl else "setup.mesh_interfaces"

    # ---- BC accessor paths -----------------------------------------

    def bc_path(self, family: str, name: str) -> str:
        """Return the indexed BC node path.

        Parameters
        ----------
        family : str
            Family to supply to the function.
        name : str
            Name of the object, module, or setting being processed.

        Returns
        -------
        str
            String result produced by the function.

        Examples
        --------
        **UTL mode**

        >>> family = PathFamily.from_active(utl_enabled=True)
        >>> output = family.bc_path("wall", "hw")
        >>> print(output)

        setup.physics.boundaries.wall['hw']

        **Standard mode**

        >>> family = PathFamily.from_active(utl_enabled=False)
        >>> output = family.bc_path("wall", "hw")
        >>> print(output)

        setup.boundary_conditions.wall['hw']
        """
        return f"{self.boundaries_root()}.{family}['{name}']"

    def cz_path(self, family: str, name: str) -> str:
        """Resolve the child zone path for the requested zone.

        Parameters
        ----------
        family : str
            Family to supply to the function.
        name : str
            Name of the object, module, or setting being processed.

        Returns
        -------
        str
            String value produced by the helper.
        """
        return f"{self.volumes_root()}.{family}['{name}']"

    # ---- BC writes (semantic ops) ----------------------------------

    #: Wall ``thermal.thermal_condition`` enum value casing differs
    #: between modes (lowercase / hyphenated in standard,
    #: Title-Case-with-spaces in UTL). The sub-path itself
    #: (``.thermal.thermal_condition``) is identical in both modes
    #: under PyFluent v27.1.
    _WALL_THERMAL_VALUE_MAP = {
        "temperature": "Temperature",
        "heat-flux": "Heat Flux",
        "convection": "Convection",
        "radiation": "Radiation",
        "mixed": "Mixed",
        "coupled": "via System Coupling",  # rare; see UG §13.2.4
    }

    def _wall_thermal_enum(self, std_value: str) -> str:
        """Return the mode-correct ``thermal_condition`` enum value.

        Parameters
        ----------
        std_value : str
            Std value to supply to the function.

        Returns
        -------
        str
            String result produced by the function.
        """
        if self.is_utl:
            return self._WALL_THERMAL_VALUE_MAP.get(std_value, std_value)
        return std_value

    def wall_thermal_temperature(
        self,
        name: str,
        value: float,
    ) -> list[tuple[str, Any]]:
        """Set a wall to fixed-temperature BC and assign the value.

        Returns paired (path, value) writes. Both modes use the same
        v27.1 canonical sub-paths (``.thermal.thermal_condition`` and
        ``.thermal.temperature.value``); only the root prefix and the
        enum casing differ between standard and UTL.

        Parameters
        ----------
        name : str
            Name of the object, module, or setting being processed.
        value : float
            Value to supply to the function.

        Returns
        -------
        list[tuple[str, Any]]
            Collection containing the operation results.
        """
        base = self.bc_path("wall", name)
        return [
            (f"{base}.thermal.thermal_condition", self._wall_thermal_enum("temperature")),
            (f"{base}.thermal.temperature.value", value),
        ]

    def wall_thermal_mixed(
        self,
        name: str,
        *,
        htc: float,
        ext_temp: float,
    ) -> list[tuple[str, Any]]:
        """Set a wall to Mixed convection+radiation.

        Parameters
        ----------
        name : str
            Name of the object, module, or setting being processed.
        htc : float
            Htc to supply to the function.
        ext_temp : float
            Ext temp to supply to the function.

        Returns
        -------
        list[tuple[str, Any]]
            Collection containing the operation results.
        """
        base = self.bc_path("wall", name)
        return [
            (f"{base}.thermal.thermal_condition", self._wall_thermal_enum("mixed")),
            (f"{base}.thermal.heat_transfer_coeff.value", htc),
            (f"{base}.thermal.ext_rad_temperature.value", ext_temp),
        ]

    def wall_thermal_convection(
        self,
        name: str,
        *,
        htc: float,
    ) -> list[tuple[str, Any]]:
        """Configure wall thermal convection settings.

        Parameters
        ----------
        name : str
            Name of the object, module, or setting being processed.
        htc : float
            Htc to supply to the function.

        Returns
        -------
        list[tuple[str, Any]]
            List of results produced by the operation.
        """
        base = self.bc_path("wall", name)
        return [
            (f"{base}.thermal.thermal_condition", self._wall_thermal_enum("convection")),
            (f"{base}.thermal.heat_transfer_coeff.value", htc),
        ]

    def velocity_inlet_speed(
        self,
        name: str,
        value: float,
    ) -> list[tuple[str, Any]]:
        """Configure velocity-inlet speed settings.

        Parameters
        ----------
        name : str
            Name of the object, module, or setting being processed.
        value : float
            Value to inspect, convert, or store.

        Returns
        -------
        list[tuple[str, Any]]
            List of results produced by the operation.
        """
        base = self.bc_path("velocity_inlet", name)
        return [(f"{base}.momentum.velocity_magnitude.value", value)]

    def velocity_inlet_temperature(
        self,
        name: str,
        value: float,
    ) -> list[tuple[str, Any]]:
        """Configure velocity-inlet temperature settings.

        Parameters
        ----------
        name : str
            Name of the object, module, or setting being processed.
        value : float
            Value to inspect, convert, or store.

        Returns
        -------
        list[tuple[str, Any]]
            List of results produced by the operation.
        """
        base = self.bc_path("velocity_inlet", name)
        return [(f"{base}.thermal.temperature.value", value)]

    # ---- Report-definition selectors -------------------------------

    def report_volume_selector(
        self,
        report_name: str,
        zones_or_groups: list[str],
    ) -> list[tuple[str, Any]]:
        """Bind a volume report-definition to its zones / physics groups.

        Standard: writes to ``…[r].cell_zones``.
        UTL: writes to ``…[r].locations.physics``.

        Parameters
        ----------
        report_name : str
            Report name to supply to the function.
        zones_or_groups : list[str]
            Zones or groups to supply to the function.

        Returns
        -------
        list[tuple[str, Any]]
            Collection containing the operation results.
        """
        base = f"solution.report_definitions.volume['{report_name}']"
        if self.is_utl:
            return [(f"{base}.locations.physics", list(zones_or_groups))]
        return [(f"{base}.cell_zones", list(zones_or_groups))]

    # ---- Surface-integral command call ------------------------------

    def surface_integral_args(
        self,
        zones_or_groups: list[str],
        *,
        report_of: str | None = None,
        write_to_file: bool = False,
        file_name: str | None = None,
        append_data: bool = False,
    ) -> dict[str, Any]:
        """Build the kwargs dict for ``surface_integrals.<method>(…)``.

        Standard: ``surface_names=[…]``.
        UTL: ``locations={'surfaces': [], 'physics': [...]}``.

        Parameters
        ----------
        zones_or_groups : list[str]
            Zones or groups to supply to the function.
        report_of : str | None
            Report of to supply to the function.
        write_to_file : bool
            Write to file to supply to the function.
        file_name : str | None
            File name to supply to the function.
        append_data : bool
            Append data to supply to the function.

        Returns
        -------
        dict[str, Any]
            Mapping containing the operation result.
        """
        args: dict[str, Any] = {}
        if self.is_utl:
            args["locations"] = {"surfaces": [], "physics": list(zones_or_groups)}
        else:
            args["surface_names"] = list(zones_or_groups)
        if report_of is not None:
            args["report_of"] = report_of
        args["write_to_file"] = bool(write_to_file)
        if file_name is not None:
            args["file_name"] = file_name
        if append_data:
            args["append_data"] = True
        return args

    # ---- UTL-only operations (no standard counterpart) -------------

    def utl_volume_set_location(
        self,
        family: str,
        name: str,
        locations: list[str],
    ) -> tuple[str, dict[str, Any]]:
        """Group multiple cell zones into a single UTL physics volume.

        Returns ``(method_path, args)`` for a ``call`` step. UTL only.
        Raises ``ValueError`` in standard mode — callers should check
        :attr:`is_utl` or mark their recipe ``requires_utl=True``.

        Parameters
        ----------
        family : str
            Family to supply to the function.
        name : str
            Name of the object, module, or setting being processed.
        locations : list[str]
            Locations to supply to the function.

        Returns
        -------
        tuple[str, dict[str, Any]]
            Mapping containing the operation result.
        """
        if not self.is_utl:
            raise ValueError(
                "volume.set_location is UTL-only; standard mode addresses "
                "cell zones individually via setup.cell_zone_conditions"
            )
        return (
            f"setup.physics.volumes.{family}['{name}'].set_location",
            {"locations": list(locations)},
        )

    def utl_volume_split(
        self,
        family: str,
        src_name: str,
        *,
        into: list[str],
        new_name: str,
    ) -> tuple[str, dict[str, Any]]:
        """Split a UTL physics volume by extracting some zones into a new physics volume.

        Only available in UTL mode.

        Parameters
        ----------
        family : str
            Family to supply to the function.
        src_name : str
            Src name to supply to the function.
        into : list[str]
            Into to supply to the function.
        new_name : str
            New name to supply to the function.

        Returns
        -------
        tuple[str, dict[str, Any]]
            Mapping containing the operation result.
        """
        if not self.is_utl:
            raise ValueError("volume.split is UTL-only")
        return (
            f"setup.physics.volumes.{family}['{src_name}'].split",
            {"locations": list(into), "name": new_name},
        )

    def utl_interface_create_call(
        self,
        *,
        name: str,
        boundary_1: str,
        boundary_2: str,
        intf_type: str = "wall",
        mesh_connectivity: str = "non-conformal",
        periodicity: str = "none",
    ) -> tuple[str, dict[str, Any]]:
        """Create a mesh interface via the UTL command form. UTL only.

        Parameters
        ----------
        name : str
            Name of the object, module, or setting being processed.
        boundary_1 : str
            Boundary 1 to supply to the function.
        boundary_2 : str
            Boundary 2 to supply to the function.
        intf_type : str
            Intf type to supply to the function.
        mesh_connectivity : str
            Mesh connectivity to supply to the function.
        periodicity : str
            Periodicity to supply to the function.

        Returns
        -------
        tuple[str, dict[str, Any]]
            Mapping containing the operation result.
        """
        if not self.is_utl:
            raise ValueError(
                "physics.interfaces.create is UTL-only; standard mode uses "
                "setup.mesh_interfaces.interface[name] (NamedObject create)"
            )
        return (
            "setup.physics.interfaces.create",
            {
                "name": name,
                "boundary_1": boundary_1,
                "boundary_2": boundary_2,
                "intf_type": intf_type,
                "mesh_connectivity": mesh_connectivity,
                "periodicity": periodicity,
            },
        )

    def utl_interface_auto_create(self) -> tuple[str, dict[str, Any]]:
        """Auto-create interfaces from coincident boundary pairs. UTL only.

        Returns
        -------
        tuple[str, dict[str, Any]]
            Mapping containing the operation result.
        """
        if not self.is_utl:
            raise ValueError("physics.interfaces.auto_create is UTL-only")
        return ("setup.physics.interfaces.auto_create", {})


# ---------------------------------------------------------------------------
# Translation table (for static analysis / documentation surfaces)
# ---------------------------------------------------------------------------

#: Prefix-level rewrites between the two families. The translator
#: takes the LONGEST matching prefix to avoid ambiguity (e.g.
#: ``setup.physics.boundaries.wall`` matches before the shorter
#: ``setup.physics``).
UTL_PREFIX_MAP_TO_UTL: dict[str, str] = {
    "setup.boundary_conditions": "setup.physics.boundaries",
    "setup.cell_zone_conditions": "setup.physics.volumes",
    "setup.mesh_interfaces": "setup.physics.interfaces",
}

UTL_PREFIX_MAP_TO_STANDARD: dict[str, str] = {v: k for k, v in UTL_PREFIX_MAP_TO_UTL.items()}


def translate_prefix(path: str, *, to_utl: bool) -> str:
    """Rewrite ``path``'s family prefix if it matches a known mapping.

    Returns the path unchanged when no mapping applies (such as for paths
    under ``solution.*``/``results.*``, which are mode-agnostic, or
    leaf attribute names that differ in nesting depth and so can't
    be rewritten by a simple prefix swap. For those, use :class:`PathFamily`
    helpers).

    Parameters
    ----------
    path : str
        Fluent object path or file-system path to inspect.
    to_utl : bool
        Whether to translate the path to UTL.

    Returns
    -------
    str
        String result produced by the function.
    """
    table = UTL_PREFIX_MAP_TO_UTL if to_utl else UTL_PREFIX_MAP_TO_STANDARD
    # Longest-prefix match.
    for src in sorted(table, key=len, reverse=True):
        if path == src or path.startswith(src + "."):
            return table[src] + path[len(src) :]
    return path
