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

"""Active-path resolver — one deterministic primitive for mode-dependent paths.

Fluent exposes the *same logical setting* at MULTIPLE physical paths whose
ACTIVE one depends on the live solver mode. Writing the wrong sibling is
silently rejected (``InactiveObjectError`` / "the object cannot be edited").
The canonical example is under-relaxation factors (URFs), whose family
depends on the pressure-velocity coupling scheme:

* segregated (SIMPLE / SIMPLEC / PISO / Fractional Step) ->
  ``solution.controls.under_relaxation['<eq>']`` (a NamedObject family)
* coupled, no pseudo-transient ->
  ``solution.controls.p_v_controls.explicit_*_under_relaxation`` (scalars)
  + ``solution.controls.relaxation_factor['<eq>']``
* coupled + pseudo-transient ->
  ``solution.controls.pseudo_time_explicit_relaxation_factor
  .global_dt_pseudo_relax['<eq>']``

Historically this knowledge was scattered across recipe URF stagers
(``stage_under_relaxation_auto``), the agent ``resolve_active_path`` tool,
the validator's ``inactive_path`` diagnostic, and per-recipe ``is_utl``
branches. This module is the SINGLE source of truth, shared by the OSS
leaf and the agent monorepo.

Two cooperating capabilities:

1. **Forward resolution** -- given a :class:`SolverMode` + a logical
   setting (e.g. a URF equation, a BC family/name, the run command),
   return the concrete *active* path. See :func:`urf_path`,
   :func:`bc_path`, :func:`run_calculation_path`, ...

2. **Reverse routing** -- given ANY proposed path + a :class:`SolverMode`,
   say whether it is active and, if not, what the correct active sibling
   is. See :func:`reroute`. This is what lets the validator hard-block a
   wrong-path write *before* Apply and hand clients a deterministic fix
   instead of letting the executor silently skip the step.

The module has NO dependency on the agent loop or live backend; it is pure,
deterministic Fluent-path knowledge. Build the :class:`SolverMode` from a
live state snapshot (:meth:`SolverMode.from_state`) and pass it in.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from typing import Any, Mapping

from ansys.fluent.mcp.solve.lib.utl import (
    PathFamily,
    translate_prefix,
)

# ---------------------------------------------------------------------------
# Solver mode
# ---------------------------------------------------------------------------

#: Pressure-velocity coupling schemes that use the COUPLED URF family
#: (everything else is segregated). Case- and separator-insensitive.
_COUPLED_FLOW_SCHEMES: frozenset[str] = frozenset({"coupled", "phase coupled simple"})


def is_coupled_scheme(flow_scheme: str | None) -> bool:
    """Return True for coupled-family pressure-velocity schemes (hyphen-tolerant)."""
    if not flow_scheme:
        return False
    norm = str(flow_scheme).strip().lower().replace("_", " ").replace("-", " ")
    return norm in _COUPLED_FLOW_SCHEMES


def _norm_multiphase(value: Any) -> str | None:
    """Normalize a multiphase model value to None|'vof'|'mixture'|'eulerian'."""
    if value is None:
        return None
    s = str(value).strip().lower()
    if s in ("", "off", "none", "no", "false", "single phase", "single-phase"):
        return None
    if "vof" in s or "volume of fluid" in s:
        return "vof"
    if "mixture" in s:
        return "mixture"
    if "euler" in s:
        return "eulerian"
    if "wet steam" in s or "wetsteam" in s:
        return "wetsteam"
    return s


def _norm_radiation(value: Any) -> str | None:
    """Normalize a radiation model value to None|'p1'|'do'|'s2s'|'mc'|'rosseland'|'solar'.

    ``None`` means radiation is off — the "simplest" default. Mirrors the
    off-value handling in :func:`_norm_multiphase` so a live ``none``/``off``
    reads as no radiation model, matching ``_apply_step_to_mode`` on the
    fluids-mcp side.
    """
    if value is None:
        return None
    s = str(value).strip().lower()
    if s in ("", "off", "none", "no", "false"):
        return None
    # Separator-robust matching: fold ``_``/``-`` to spaces so the raw model
    # string the plan simulator stores (``"discrete-ordinates"``) reads the
    # same as the live-state value (``"discrete ordinates"``/``"do"``).
    t = s.replace("_", " ").replace("-", " ")
    if "rosseland" in t:
        return "rosseland"
    if "solar" in t:
        return "solar"
    if "monte" in t or t == "mc":
        return "mc"
    if "discrete ordinates" in t or t == "do":
        return "do"
    if "s2s" in t or "surface to surface" in t:
        return "s2s"
    if t in ("p1", "p 1"):
        return "p1"
    return s


def _flag_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "on", "enabled")
    return False


def _norm_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return None
    s = str(value).strip()
    return s or None


@dataclass(frozen=True)
class SolverMode:
    """A snapshot of the live solver mode facets that gate path selection.

    Every field defaults to the "simplest" value (standard namespace,
    steady, pressure-based, segregated, single-phase, energy off) so a
    partially-known mode still resolves deterministically.
    """

    utl: bool = False
    transient: bool = False
    density_based: bool = False
    flow_scheme: str | None = None
    pseudo_transient: bool = False
    multiphase_model: str | None = None
    phases: tuple[str, ...] = ()
    turbulence_model: str | None = None
    energy: bool = False
    nita: bool = False
    radiation_model: str | None = None

    @property
    def coupled(self) -> bool:
        """True when the pressure-velocity scheme is a coupled-family one."""
        return is_coupled_scheme(self.flow_scheme)

    @property
    def pressure_based(self) -> bool:
        """True when the solver type is pressure-based (opposite of density-based)."""
        return not self.density_based

    @property
    def multiphase(self) -> bool:
        """True when any multiphase model is active."""
        return self.multiphase_model is not None

    @classmethod
    def from_state(
        cls,
        state: Mapping[str, Any] | None,
        *,
        utl: bool | None = None,
        phases: tuple[str, ...] = (),
    ) -> "SolverMode":
        """Build a :class:`SolverMode` from a live state snapshot dict.

        ``state`` is a flat ``{path: value}`` mapping as returned by
        ``backend.get_state([...])``. ``utl`` is passed separately because
        UTL detection is a dedicated probe (``detect_utl_mode``), not a
        plain settings read. ``phases`` (ordered phase keys) is likewise
        supplied by the caller when known (it comes from
        ``list_named_objects`` on ``setup.models.multiphase.phases``).
        """
        st: Mapping[str, Any] = state or {}

        time_mode = _norm_str(st.get("setup.general.solver.time"))
        transient = bool(isinstance(time_mode, str) and time_mode not in ("steady", ""))

        solver_type = _norm_str(st.get("setup.general.solver.type")) or ""
        density_based = "density" in solver_type.lower()

        flow_scheme = _norm_str(st.get("solution.methods.p_v_coupling.flow_scheme"))

        pseudo_transient = (
            _flag_truthy(st.get("solution.methods.pseudo_time_method.formulation.coupled_solver"))
            or _flag_truthy(
                st.get("solution.methods.pseudo_time_method.formulation.segregated_solver")
            )
            or _flag_truthy(
                st.get("solution.methods.pseudo_time_method.formulation.density_based_solver")
            )
        )

        # Multiphase model lives at the singular ``.model`` leaf in the
        # live tree; some recipes write the plural ``.models`` enum. Read
        # whichever is present.
        mp = _norm_multiphase(
            st.get("setup.models.multiphase.model")
            if st.get("setup.models.multiphase.model") is not None
            else st.get("setup.models.multiphase.models")
        )

        nita = _flag_truthy(
            st.get("solution.methods.nita.nita_settings.set_velocity_and_vof_cutoffs")
        ) or _flag_truthy(st.get("solution.methods.nita"))

        return cls(
            utl=bool(utl),
            transient=transient,
            density_based=density_based,
            flow_scheme=flow_scheme,
            pseudo_transient=pseudo_transient,
            multiphase_model=mp,
            phases=tuple(phases),
            turbulence_model=_norm_str(st.get("setup.models.viscous.model")),
            energy=_flag_truthy(st.get("setup.models.energy.enabled")),
            nita=nita,
            radiation_model=_norm_radiation(
                st.get("setup.models.radiation.model")
                if st.get("setup.models.radiation.model") is not None
                else st.get("setup.models.radiation.rad_model")
            ),
        )

    @classmethod
    def from_backend_state(
        cls,
        state: Mapping[str, Any] | None,
        *,
        utl: bool | None = None,
        phases: tuple[str, ...] = (),
    ) -> "SolverMode":
        """Build a :class:`SolverMode` from the raw ``backend.get_state()`` output.

        The Fluent PyFluent backend returns a **nested dict of dicts**
        keyed by slash-separated node paths (e.g. ``"setup/general/
        solver"`` -> ``{"time": "steady", "type": "pressure-based",
        ...}``), NOT the flat dotted mapping :meth:`from_state`
        expects. This adapter flattens the shape the backend uses onto
        the flat dotted mapping :meth:`from_state` consumes so callers
        don't have to reimplement the translation.

        Silently tolerant of missing keys — a partial or empty state
        still produces a valid :class:`SolverMode` populated with the
        "simplest" defaults. Only the specific facets :meth:`from_state`
        cares about are extracted; other backend-state keys are
        ignored.
        """
        raw: Mapping[str, Any] = state or {}

        def _pluck(root_slash: str, sub_dot: str) -> Any:
            root_dot = root_slash.replace("/", ".")
            # Prefer the nested "setup/general/solver" -> dict lookup
            # first, since that's what backend.get_state() returns.
            node = raw.get(root_slash)
            if node is None:
                node = raw.get(root_dot)
            if isinstance(node, dict):
                # Walk sub-dot inside the nested dict, tolerating
                # inactive / error / skipped markers gracefully.
                if node.get("inactive") or node.get("error") or node.get("skipped"):
                    return None
                cur: Any = node
                for part in sub_dot.split("."):
                    if not isinstance(cur, dict):
                        return None
                    cur = cur.get(part) if part in cur else cur.get(part.replace("-", "_"))
                return cur
            # Fall back to the flat dotted layout used by :meth:`from_state`.
            return raw.get(f"{root_dot}.{sub_dot}")

        flat: dict[str, Any] = {}
        for root, sub in (
            ("setup/general/solver", "time"),
            ("setup/general/solver", "type"),
            ("solution/methods/p-v-coupling", "flow_scheme"),
            (
                "solution/methods/pseudo-time-method/formulation",
                "coupled_solver",
            ),
            (
                "solution/methods/pseudo-time-method/formulation",
                "segregated_solver",
            ),
            (
                "solution/methods/pseudo-time-method/formulation",
                "density_based_solver",
            ),
            ("setup/models/multiphase", "model"),
            ("setup/models/multiphase", "models"),
            ("setup/models/viscous", "model"),
            ("setup/models/energy", "enabled"),
            ("setup/models/radiation", "model"),
            ("setup/models/radiation", "rad_model"),
            (
                "solution/methods/nita/nita-settings",
                "set_velocity_and_vof_cutoffs",
            ),
            ("solution/methods", "nita"),
        ):
            val = _pluck(root, sub)
            if val is None:
                continue
            # ``from_state`` uses dotted paths with UNDERSCORES
            # (`p_v_coupling`, `pseudo_time_method`, ...) while the
            # backend's slash keys use HYPHENS (`p-v-coupling`,
            # `pseudo-time-method`, ...). Normalize before emitting so
            # ``from_state``'s lookups hit.
            key = f"{root.replace('/', '.').replace('-', '_')}.{sub}"
            flat[key] = val
        return cls.from_state(flat, utl=utl, phases=phases)


# ---------------------------------------------------------------------------
# Under-relaxation families
# ---------------------------------------------------------------------------


class UrfFamily(str, Enum):
    """The active under-relaxation family for a given solver mode."""

    SEGREGATED = "segregated"
    COUPLED_EXPLICIT = "coupled_explicit"
    PSEUDO_TIME = "pseudo_time"


def active_urf_family(mode: SolverMode) -> UrfFamily:
    """Return the URF family that is ACTIVE under ``mode``.

    * coupled + pseudo-transient -> per-equation pseudo-time family
    * coupled (no pseudo)        -> explicit scalar + relaxation_factor
    * segregated                 -> under_relaxation NamedObject family
    """
    if mode.coupled:
        return UrfFamily.PSEUDO_TIME if mode.pseudo_transient else UrfFamily.COUPLED_EXPLICIT
    return UrfFamily.SEGREGATED


# Canonical equation tokens used internally. Free-text /
# per-family spellings normalize onto these.
_EQ_CANON: dict[str, str] = {
    "p": "pressure",
    "pressure": "pressure",
    "mom": "mom",
    "momentum": "mom",
    "vof": "vof",
    "mp": "vof",
    "volume-fraction": "vof",
    "volume_fraction": "vof",
    "k": "k",
    "tke": "k",
    "omega": "omega",
    "sdr": "omega",
    "epsilon": "epsilon",
    "temperature": "temperature",
    "energy": "temperature",
    "enthalpy": "temperature",
    "density": "density",
    "body-force": "body-force",
    "body_force": "body-force",
}


def _canon_eq(eq: str) -> str:
    return _EQ_CANON.get(str(eq).strip().strip("'\"").lower(), str(eq).strip().strip("'\"").lower())


#: Segregated NamedObject key for a canonical equation token. VOF is
#: keyed ``mp`` (mass-phase) in the segregated under_relaxation family.
_SEG_KEY: dict[str, str] = {
    "pressure": "pressure",
    "mom": "mom",
    "vof": "mp",
    "k": "k",
    "omega": "omega",
    "epsilon": "epsilon",
    "temperature": "temperature",
    "density": "density",
    "body-force": "body-force",
}

_UR = "solution.controls.under_relaxation"
_PVC = "solution.controls.p_v_controls"
_RF = "solution.controls.relaxation_factor"
_PT = "solution.controls.pseudo_time_explicit_relaxation_factor.global_dt_pseudo_relax"

#: Coupled-explicit scalar leaves keyed by canonical equation.
_COUPLED_EXPLICIT_SCALAR: dict[str, str] = {
    "pressure": f"{_PVC}.explicit_pressure_under_relaxation",
    "mom": f"{_PVC}.explicit_momentum_under_relaxation",
    "vof": f"{_PVC}.explicit_volume_fraction_under_relaxation",
}


def urf_path(mode: SolverMode, equation: str) -> str:
    """Return the ACTIVE concrete URF path for ``equation`` under ``mode``.

    Examples
    --------
    >>> urf_path(SolverMode(), "pressure")
    "solution.controls.under_relaxation['pressure']"
    >>> urf_path(SolverMode(flow_scheme="Coupled"), "momentum")
    'solution.controls.p_v_controls.explicit_momentum_under_relaxation'
    >>> urf_path(SolverMode(flow_scheme="Coupled", pseudo_transient=True), "k")
    "solution.controls.pseudo_time_explicit_relaxation_factor.global_dt_pseudo_relax['k']"
    """
    eq = _canon_eq(equation)
    fam = active_urf_family(mode)
    if fam is UrfFamily.SEGREGATED:
        return f"{_UR}['{_SEG_KEY.get(eq, eq)}']"
    if fam is UrfFamily.COUPLED_EXPLICIT:
        scalar = _COUPLED_EXPLICIT_SCALAR.get(eq)
        if scalar is not None:
            return scalar
        return f"{_RF}['{eq}']"
    # PSEUDO_TIME
    return f"{_PT}['{eq}']"


# ---------------------------------------------------------------------------
# Path classification (reverse map)
# ---------------------------------------------------------------------------


class PathGroup(str, Enum):
    """The multi-path class a concrete path belongs to."""

    URF = "urf"
    BC = "bc"
    CZ = "cz"
    INTERFACE = "interface"
    RUN = "run"


@dataclass(frozen=True)
class PathInfo:
    """Classification of a concrete path within a multi-path group."""

    group: PathGroup
    # For URF: a :class:`UrfFamily` value. For BC/CZ/INTERFACE: "utl" or
    # "standard". For RUN: "iterate" or "dual_time_iterate".
    family: str
    # The equation token (URF) or named-object key, when extractable.
    key: str | None = None


_BRACKET_RE = re.compile(r"\[\s*['\"]?([^'\"\]]+)['\"]?\s*\]")


def _bracket_key(path: str) -> str | None:
    m = _BRACKET_RE.search(path)
    return m.group(1).strip() if m else None


def classify_path(path: str) -> PathInfo | None:
    """Classify ``path`` into a known multi-path group, or ``None``.

    ``None`` means the path is not a known mode-dependent setting, so
    callers should treat it as "we can't reason about activation here"
    and NOT block it.
    """
    if not path:
        return None
    p = str(path)

    # --- URF families -------------------------------------------------
    if p.startswith(f"{_UR}["):
        return PathInfo(PathGroup.URF, UrfFamily.SEGREGATED.value, _bracket_key(p))
    if p.startswith(_PT) and "[" in p:
        return PathInfo(PathGroup.URF, UrfFamily.PSEUDO_TIME.value, _bracket_key(p))
    if p == f"{_PVC}.explicit_pressure_under_relaxation":
        return PathInfo(PathGroup.URF, UrfFamily.COUPLED_EXPLICIT.value, "pressure")
    if p == f"{_PVC}.explicit_momentum_under_relaxation":
        return PathInfo(PathGroup.URF, UrfFamily.COUPLED_EXPLICIT.value, "mom")
    if p == f"{_PVC}.explicit_volume_fraction_under_relaxation":
        return PathInfo(PathGroup.URF, UrfFamily.COUPLED_EXPLICIT.value, "vof")
    if p.startswith(f"{_RF}["):
        return PathInfo(PathGroup.URF, UrfFamily.COUPLED_EXPLICIT.value, _bracket_key(p))

    # --- BC / CZ / interface namespaces ------------------------------
    if p.startswith("setup.physics.boundaries"):
        return PathInfo(PathGroup.BC, "utl", _bracket_key(p))
    if p.startswith("setup.boundary_conditions"):
        return PathInfo(PathGroup.BC, "standard", _bracket_key(p))
    if p.startswith("setup.physics.volumes"):
        return PathInfo(PathGroup.CZ, "utl", _bracket_key(p))
    if p.startswith("setup.cell_zone_conditions"):
        return PathInfo(PathGroup.CZ, "standard", _bracket_key(p))
    if p.startswith("setup.physics.interfaces"):
        return PathInfo(PathGroup.INTERFACE, "utl", _bracket_key(p))
    if p.startswith("setup.mesh_interfaces"):
        return PathInfo(PathGroup.INTERFACE, "standard", _bracket_key(p))

    # --- run calculation command -------------------------------------
    if p.startswith("solution.run_calculation.dual_time_iterate"):
        return PathInfo(PathGroup.RUN, "dual_time_iterate", None)
    if p.startswith("solution.run_calculation.iterate"):
        return PathInfo(PathGroup.RUN, "iterate", None)

    return None


# ---------------------------------------------------------------------------
# Reverse routing
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RerouteResult:
    """Result of checking a proposed path against the live mode.

    ``active=True`` means the path is fine to write as-is. ``active=False``
    means the path is in a known multi-path class and is INACTIVE under the
    current mode; ``correct_path`` carries the active sibling when it can be
    derived deterministically (else ``None``), and ``reason`` is a short
    human-readable explanation suitable for a validator diagnostic.
    """

    active: bool
    correct_path: str | None
    reason: str
    group: str | None
    # The active family/selector under the current mode (for messaging).
    active_family: str | None = None


_ACTIVE = RerouteResult(active=True, correct_path=None, reason="", group=None)


def reroute(path: str, mode: SolverMode) -> RerouteResult:
    """Check ``path`` against ``mode`` and, if inactive, point to the fix.

    Deterministic and conservative: returns ``active=True`` for any path
    that is not a recognized multi-path setting, so it never false-blocks
    an ordinary write.
    """
    info = classify_path(path)
    if info is None:
        return _ACTIVE

    if info.group is PathGroup.URF:
        want = active_urf_family(mode)
        if info.family == want.value:
            return _ACTIVE
        correct = urf_path(mode, info.key) if info.key else None
        return RerouteResult(
            active=False,
            correct_path=correct,
            reason=(
                f"under-relaxation family '{info.family}' is inactive under "
                f"the live pressure-velocity scheme "
                f"({'coupled' if mode.coupled else 'segregated'}"
                f"{', pseudo-transient' if (mode.coupled and mode.pseudo_transient) else ''})"
                f"; the active family is '{want.value}'"
            ),
            group=info.group.value,
            active_family=want.value,
        )

    if info.group in (PathGroup.BC, PathGroup.CZ, PathGroup.INTERFACE):
        path_is_utl = info.family == "utl"
        if path_is_utl == mode.utl:
            return _ACTIVE
        correct = translate_prefix(path, to_utl=mode.utl)
        # Interfaces are not a clean prefix swap (NamedObject vs command),
        # so only offer the rewritten root as guidance.
        return RerouteResult(
            active=False,
            correct_path=correct if correct != path else None,
            reason=(
                f"{info.group.value} path uses the "
                f"{'UTL' if path_is_utl else 'standard'} namespace but the "
                f"live session is in {'UTL' if mode.utl else 'standard'} mode"
            ),
            group=info.group.value,
            active_family="utl" if mode.utl else "standard",
        )

    if info.group is PathGroup.RUN:
        want_cmd = "dual_time_iterate" if mode.transient else "iterate"
        if info.family == want_cmd:
            return _ACTIVE
        return RerouteResult(
            active=False,
            correct_path=f"solution.run_calculation.{want_cmd}",
            reason=(
                f"'{info.family}' is the {'steady' if info.family == 'iterate' else 'transient'} "
                f"run command but the live session is "
                f"{'transient' if mode.transient else 'steady'}"
            ),
            group=info.group.value,
            active_family=want_cmd,
        )

    return _ACTIVE


# ---------------------------------------------------------------------------
# Forward namespace helpers (UTL-aware) — thin, deterministic wrappers
# ---------------------------------------------------------------------------


def path_family(mode: SolverMode) -> PathFamily:
    """Return the :class:`PathFamily` translator for ``mode``."""
    return PathFamily.from_active(mode.utl)


def bc_root(mode: SolverMode) -> str:
    """Active boundary-condition namespace root."""
    return path_family(mode).boundaries_root()


def cz_root(mode: SolverMode) -> str:
    """Active cell-zone namespace root."""
    return path_family(mode).volumes_root()


def interface_root(mode: SolverMode) -> str:
    """Active mesh-interface namespace root."""
    return path_family(mode).interfaces_root()


def bc_path(mode: SolverMode, family: str, name: str) -> str:
    """Active indexed BC node path (e.g. ``...wall['hw']``)."""
    return path_family(mode).bc_path(family, name)


def cz_path(mode: SolverMode, family: str, name: str) -> str:
    """Active indexed cell-zone node path."""
    return path_family(mode).cz_path(family, name)


def run_calculation_path(mode: SolverMode) -> str:
    """Active run-calculation command path (steady vs transient)."""
    return (
        "solution.run_calculation.dual_time_iterate"
        if mode.transient
        else "solution.run_calculation.iterate"
    )


def multiphase_volume_fraction_path(
    mode: SolverMode,
    bc_family: str,
    bc_name: str,
    phase_key: str,
    *,
    leaf: str = "volume_fraction",
) -> str:
    """Per-phase BC volume-fraction path under the active namespace.

    ``leaf`` defaults to the inlet ``volume_fraction`` value leaf; pass a
    different scoped leaf (e.g. ``backflow_volume_fraction``) as needed.
    Kept for backward compatibility; new callers should prefer the more
    general :func:`multiphase_bc_phase_path`.
    """
    return multiphase_bc_phase_path(
        mode,
        bc_family,
        bc_name,
        phase_key,
        leaf=leaf,
    )


def multiphase_bc_phase_path(
    mode: SolverMode,
    bc_family: str,
    bc_name: str,
    phase_key: str,
    *,
    leaf: str,
    scope: str = "multiphase",
    value_suffix: bool = True,
) -> str:
    """Return the per-phase BC leaf path under the active namespace.

    On multiphase cases Fluent splits BC leaves into two tiers:

    * **Mixture-level** leaves (``momentum.*``, ``turbulence.*``,
      ``dpm.*``, ...) live directly on the BC's top namespace and are
      set once per BC — call :func:`bc_path` for those.
    * **Per-phase** leaves (``volume_fraction``, ``granular_temperature``,
      per-phase turbulence / DPM / species knobs, ...) live under
      ``phase['<phase-key>'].<scope>.<leaf>`` on the BC. Writing them
      under a NON-matching phase key is silently rejected.

    This helper composes the per-phase path for ANY leaf (not just
    ``volume_fraction`` as the legacy helper did) so multiphase-aware
    callers do not need to string-format the path themselves. It also
    handles the ``.value`` suffix that Fluent applies to numeric leaves
    (``volume_fraction.value``) while allowing structural leaves that
    do NOT carry the suffix (``turbulence.turb_intensity``) via
    ``value_suffix=False``.

    Parameters
    ----------
    mode
        Live solver mode (drives UTL vs standard root selection).
    bc_family
        BC family (e.g. ``"velocity_inlet"``, ``"pressure_outlet"``,
        ``"mass_flow_inlet"``, ``"wall"``).
    bc_name
        Named-object key on the BC family (e.g. ``"inlet1"``).
    phase_key
        Phase-name key as stored on ``setup.models.multiphase.phases``
        (typically a user-visible string like ``"water-liquid"`` or
        Fluent's default ``"phase-1"``).
    leaf
        The per-phase leaf name relative to ``<scope>`` (e.g.
        ``"volume_fraction"``, ``"granular_temperature"``,
        ``"turb_intensity"``, ``"backflow_volume_fraction"``).
    scope
        Container under which the leaf lives on the phase branch;
        Fluent uses ``"multiphase"`` for VOF / mixture / eulerian
        volume-fraction / granular knobs (the default). Turbulence
        per-phase leaves live under ``"turbulence"``; DPM per-phase
        under ``"dpm"``.
    value_suffix
        Append ``.value`` to the path. True for numeric quantities
        (the common case), False for structural / enum leaves.

    Returns
    -------
    str
        The concrete active per-phase BC path.

    Examples
    --------
    >>> multiphase_bc_phase_path(
    ...     SolverMode(),
    ...     "velocity_inlet",
    ...     "inlet1",
    ...     "water-liquid",
    ...     leaf="volume_fraction",
    ... )
    "setup.boundary_conditions.velocity_inlet['inlet1'].phase['water-liquid'].multiphase.volume_fraction.value"

    >>> multiphase_bc_phase_path(
    ...     SolverMode(utl=True),
    ...     "wall",
    ...     "hw",
    ...     "primary",
    ...     leaf="turb_intensity",
    ...     scope="turbulence",
    ...     value_suffix=False,
    ... )
    "setup.physics.boundaries.wall['hw'].phase['primary'].turbulence.turb_intensity"
    """
    base = bc_path(mode, bc_family, bc_name)
    tail = f".phase['{phase_key}'].{scope}.{leaf}"
    return f"{base}{tail}.value" if value_suffix else f"{base}{tail}"


# ---------------------------------------------------------------------------
# solution.methods.* mode-gated leaf classification (extends URF coverage)
# ---------------------------------------------------------------------------

#: Prefixes on ``solution.methods.*`` whose availability is gated by
#: solver mode (density-based vs pressure-based, pseudo-transient
#: on/off, transient on/off). Writing to an inactive prefix is silently
#: rejected by Fluent. The value tuple is
#: ``(selector_facet, expected_value_or_predicate, human_description)``.
#: A ``None`` in expected means "the facet must be truthy". The
#: predicate form ``("!", value)`` means "the facet must NOT equal
#: value".
_METHODS_MODE_GATES: tuple[tuple[str, str, Any, str], ...] = (
    # Pseudo-time formulation flags live under the branch itself and
    # are self-gating (writing them TURNS the mode on), but their
    # per-scheme scaling knobs are inactive unless the matching solver
    # branch is on.
    (
        "solution.methods.pseudo_time_method.local_dt_pseudo_relaxation_factor",
        "coupled_scheme",
        None,
        (
            "local Δτ pseudo-relaxation factors are only active with a "
            "coupled + pseudo-transient formulation"
        ),
    ),
    (
        "solution.methods.pseudo_time_method.global_dt_pseudo_time_step",
        "coupled_pseudo",
        None,
        (
            "global Δτ pseudo-time-step scaling is only active with a "
            "coupled + pseudo-transient formulation"
        ),
    ),
    # Density-based-only methods (AUSM, Roe, Weiss-Smith preconditioning, ...) live here.
    (
        "solution.methods.flux_type",
        "density_based",
        None,
        (
            "flux_type (AUSM / Roe / ...) is a density-based-solver knob; "
            "pressure-based cases have no active flux_type"
        ),
    ),
    (
        "solution.methods.warped_face_gradient_correction",
        "density_based",
        None,
        "warped_face_gradient_correction is a density-based-solver knob",
    ),
    # Transient-only method knobs
    (
        "solution.methods.transient_controls",
        "transient",
        None,
        "transient_controls is only active in unsteady runs",
    ),
    (
        "solution.methods.high_speed_numerics",
        "density_based",
        None,
        "high_speed_numerics is a density-based-solver knob (compressible / high-speed physics)",
    ),
    # Pressure-based-only stabilizer. Density-based cases have no active
    # high_order_term_relaxation (HOTR).
    (
        "solution.methods.high_order_term_relaxation",
        "pressure_based",
        None,
        (
            "high_order_term_relaxation (HOTR) is a pressure-based-solver "
            "stabilizer; density-based cases have no active "
            "high_order_term_relaxation"
        ),
    ),
    # Model sub-selectors that live under ``setup.models.*`` rather than
    # ``solution.methods.*`` but share the "active or the mode is wrong"
    # semantics (no correct sibling — the leaf only exists under the
    # matching parent model). Turbulence family sub-selectors:
    (
        "setup.models.viscous.k_omega_model",
        "viscous_k_omega",
        None,
        (
            "the k_omega_model sub-selector is only active when "
            "setup.models.viscous.model is a k-omega variant"
        ),
    ),
    (
        "setup.models.viscous.k_epsilon_model",
        "viscous_k_epsilon",
        None,
        (
            "the k_epsilon_model sub-selector is only active when "
            "setup.models.viscous.model is a k-epsilon variant"
        ),
    ),
    # Radiation sub-branch controls are only active under the matching
    # radiation model (e.g. discrete-ordinates energy iterations).
    (
        "setup.models.radiation.discrete_ordinates",
        "radiation_do",
        None,
        (
            "discrete_ordinates.* controls are only active when "
            "setup.models.radiation.model is discrete-ordinates (DO)"
        ),
    ),
)


def _methods_facet_active(mode: SolverMode, facet: str) -> bool:
    """Return True when ``facet`` is satisfied under ``mode``."""
    if facet == "coupled_pseudo":
        return mode.coupled and mode.pseudo_transient
    if facet == "coupled_scheme":
        return mode.coupled
    if facet == "density_based":
        return mode.density_based
    if facet == "pressure_based":
        return not mode.density_based
    if facet == "transient":
        return mode.transient
    if facet == "viscous_k_omega":
        return "omega" in (mode.turbulence_model or "").lower()
    if facet == "viscous_k_epsilon":
        return "epsilon" in (mode.turbulence_model or "").lower()
    if facet.startswith("radiation_"):
        # ``radiation_do`` -> "do", ``radiation_p1`` -> "p1", etc. Normalize
        # the mode value so this tolerates both the raw model string the plan
        # simulator stores (``"discrete-ordinates"``) and the already-
        # normalized live-state value (``"do"``).
        want = facet.split("_", 1)[1]
        return _norm_radiation(mode.radiation_model) == want
    # Unknown facet — never false-block.
    return True


def classify_methods_gate(path: str) -> tuple[str, str] | None:
    """Return ``(facet_name, human_description)`` for a mode-gated methods prefix.

    If ``path`` starts with a known ``solution.methods.*`` mode-gated
    prefix, return the facet + description tuple; otherwise return
    ``None``.

    Consumers should call :func:`_methods_facet_active` (or replicate
    its logic) to decide whether the gate is currently satisfied. This
    is complementary to :func:`classify_path` — the latter handles
    URF / BC / CZ / interface / run families and returns a
    :class:`PathInfo`; this helper covers ``solution.methods.*`` where
    the "correct sibling" concept does not apply (the path is either
    active or the mode is wrong).
    """
    if not path:
        return None
    for prefix, facet, _expected, description in _METHODS_MODE_GATES:
        if path == prefix or path.startswith(prefix + "."):
            return facet, description
    return None


# ---------------------------------------------------------------------------
# Declarative registry (introspection / documentation / drift tests)
# ---------------------------------------------------------------------------

#: One row per multi-path setting class. The ``resolver`` field names the
#: function that returns the active path; ``selectors`` lists the
#: :class:`SolverMode` facets that gate the choice. This table is the
#: single inventory the test-suite asserts against, so adding a new
#: multi-path class is one row here + the matching resolver branch.
MULTI_PATH_CLASSES: tuple[dict[str, Any], ...] = (
    {
        "id": "urf",
        "description": "per-equation under-relaxation / pseudo-time relaxation",
        "selectors": ("flow_scheme", "pseudo_transient"),
        "resolver": "urf_path",
        "families": tuple(f.value for f in UrfFamily),
    },
    {
        "id": "bc",
        "description": "boundary-condition namespace (UTL vs standard)",
        "selectors": ("utl",),
        "resolver": "bc_path",
        "families": ("standard", "utl"),
    },
    {
        "id": "cz",
        "description": "cell-zone namespace (UTL vs standard)",
        "selectors": ("utl",),
        "resolver": "cz_path",
        "families": ("standard", "utl"),
    },
    {
        "id": "interface",
        "description": "mesh-interface namespace (UTL command vs standard NamedObject)",
        "selectors": ("utl",),
        "resolver": "interface_root",
        "families": ("standard", "utl"),
    },
    {
        "id": "run",
        "description": "run-calculation command (steady iterate vs transient dual_time_iterate)",
        "selectors": ("transient",),
        "resolver": "run_calculation_path",
        "families": ("iterate", "dual_time_iterate"),
    },
    {
        "id": "multiphase_vf",
        "description": "per-phase BC volume-fraction (UTL namespace + phase key)",
        "selectors": ("utl", "phases"),
        "resolver": "multiphase_volume_fraction_path",
        "families": ("standard", "utl"),
    },
    {
        "id": "multiphase_bc_phase",
        "description": "generic per-phase BC leaf (UTL namespace + phase key + arbitrary leaf)",
        "selectors": ("utl", "phases"),
        "resolver": "multiphase_bc_phase_path",
        "families": ("standard", "utl"),
    },
    {
        "id": "methods_gate",
        "description": (
            "solution.methods.* mode-gated leaves "
            "(density-based-only, pseudo-transient-only, transient-only)"
        ),
        "selectors": ("density_based", "coupled", "pseudo_transient", "transient"),
        "resolver": "classify_methods_gate",
        "families": (
            "pressure_based",
            "density_based",
            "coupled_scheme",
            "coupled_pseudo",
            "transient",
        ),
    },
)


# ---------------------------------------------------------------------------
# Canonical write-target resolver
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WriteTarget:
    """Canonical resolution of "where should a write to ``requested_path`` land".

    The three consumers of active-path knowledge (the validator's
    ``inactive_path`` diagnostic, the ``resolve_active_path`` tool
    surfaced to clients, and the recipe URF stagers) historically
    each maintained their OWN version of the classify → reroute →
    fetch-alternate-path pipeline. That triplication is the reason
    the same live case could produce three DIFFERENT answers for
    "where does this URF write actually go" — the validator said
    ``inactive_path``, the tool said "no reroute needed", and the
    recipe went ahead and wrote the wrong family.

    :func:`resolve_write_target` is the single deterministic
    resolver they all consult. The result carries:

    * ``requested_path`` — the input, verbatim.
    * ``active_path`` — the correct path to write under ``mode``,
      which equals ``requested_path`` when the input is already
      active (``needs_reroute=False``).
    * ``needs_reroute`` — True iff ``active_path != requested_path``.
    * ``group`` / ``active_family`` — for messaging and telemetry.
    * ``reason`` — short human-readable explanation suitable for a
            validator diagnostic and the client-facing tool response.
    * ``classified`` — True iff the requested path was recognized
      as belonging to a known multi-path class. When False, the
      resolver is conservative: it returns ``needs_reroute=False``
      and ``active_path=requested_path`` so an ordinary write is
      never false-blocked.
    """

    requested_path: str
    active_path: str
    needs_reroute: bool
    group: str | None = None
    active_family: str | None = None
    reason: str = ""
    classified: bool = False


def resolve_write_target(mode: SolverMode, path: str) -> WriteTarget:
    """Return the canonical :class:`WriteTarget` for a proposed write.

    Combines :func:`classify_path` + :func:`reroute` (multi-path
    families) with :func:`classify_methods_gate` (``solution.methods.*``
    mode-gated leaves) behind one call so every consumer produces the
    same answer. When the path is not a recognized multi-path or
    mode-gated setting, returns a "pass-through" :class:`WriteTarget`
    with ``needs_reroute=False`` and ``classified=False`` — that is
    the signal to fall back to the default schema-only check.

    Parameters
    ----------
    mode
        Live solver mode facets (build via :meth:`SolverMode.from_state`).
    path
        Proposed write path (bracket-indexed forms accepted).

    Returns
    -------
    WriteTarget
        Canonical resolution. When ``needs_reroute`` is True,
        ``active_path`` carries the sibling to write instead (or,
        if a deterministic active path cannot be derived, equals
        ``requested_path`` and the caller should surface the
        ``reason`` verbatim rather than silently proceeding).
    """
    info = classify_path(path)
    if info is None:
        # Second chance: ``solution.methods.*`` mode-gated leaves have
        # no "correct sibling" (the path is either active or the mode
        # is wrong), so surface an inactive gate as a classified
        # write-target with ``active_path=requested_path`` and
        # ``needs_reroute=False`` but a ``reason`` string the caller
        # can promote into a warning.
        gate = classify_methods_gate(path)
        if gate is not None:
            facet, description = gate
            if _methods_facet_active(mode, facet):
                return WriteTarget(
                    requested_path=path,
                    active_path=path,
                    needs_reroute=False,
                    group="methods_gate",
                    active_family=facet,
                    classified=True,
                )
            return WriteTarget(
                requested_path=path,
                active_path=path,
                needs_reroute=False,
                group="methods_gate",
                active_family=facet,
                reason=description,
                classified=True,
            )
        return WriteTarget(
            requested_path=path,
            active_path=path,
            needs_reroute=False,
            classified=False,
        )
    r = reroute(path, mode)
    if r.active:
        return WriteTarget(
            requested_path=path,
            active_path=path,
            needs_reroute=False,
            group=info.group.value,
            active_family=r.active_family or info.family,
            classified=True,
        )
    correct = r.correct_path or path
    return WriteTarget(
        requested_path=path,
        active_path=correct,
        needs_reroute=correct != path,
        group=info.group.value,
        active_family=r.active_family,
        reason=r.reason,
        classified=True,
    )


# ---------------------------------------------------------------------------
# Mode summary + write-target hints (shared by authoring hosts and the
# agent loop, so callers see one deterministic answer for "what should
# a write to X look like under the current live mode".
# ---------------------------------------------------------------------------


def describe_mode(mode: SolverMode) -> dict[str, Any]:
    """Return a compact JSON-safe summary of ``mode``.

    Suitable for embedding in a system prompt or a debug payload.
    Fields:

    * ``time`` — ``"steady"`` or ``"transient"``.
    * ``solver_type`` — ``"pressure-based"`` or ``"density-based"``.
    * ``flow_scheme`` — the raw p-v coupling string (may be None).
    * ``coupled`` — bool.
    * ``pseudo_transient`` — bool.
    * ``urf_family`` — active URF family enum value.
    * ``bc_namespace`` / ``cz_namespace`` / ``interface_namespace``
      — ``"utl"`` or ``"standard"``.
    * ``multiphase`` — ``None`` for single-phase, else
      ``{model, phases}``.
    * ``turbulence_model`` / ``energy`` — passthrough.
    * ``nita`` — bool.
    """
    urf_fam = active_urf_family(mode)
    mp: dict[str, Any] | None
    if mode.multiphase:
        mp = {"model": mode.multiphase_model, "phases": list(mode.phases)}
    else:
        mp = None
    return {
        "time": "transient" if mode.transient else "steady",
        "solver_type": "density-based" if mode.density_based else "pressure-based",
        "flow_scheme": mode.flow_scheme,
        "coupled": mode.coupled,
        "pseudo_transient": mode.pseudo_transient,
        "urf_family": urf_fam.value,
        "bc_namespace": "utl" if mode.utl else "standard",
        "cz_namespace": "utl" if mode.utl else "standard",
        "interface_namespace": "utl" if mode.utl else "standard",
        "multiphase": mp,
        "turbulence_model": mode.turbulence_model,
        "energy": mode.energy,
        "nita": mode.nita,
    }


def write_target_hints(mode: SolverMode) -> dict[str, Any]:
    """Return canonical write-target answers for the CURRENT ``mode``.

    Emits a small dict that any authoring surface (agent-loop system prompt,
    `describe_path` fallback, external host preflight) can turn into
    a short "when you write X, use path Y" guide. Contains ONLY facts
    derivable from ``mode`` — no live tool calls, no schema probes.

    Keys:

    * ``urf_family`` — active URF family enum value.
    * ``urf_root`` — the container path (segregated NamedObject root,
      coupled scalar prefix, or pseudo-time NamedObject root).
    * ``urf_key_template`` — how to index into that root
      (``"['<equation>']"`` for NamedObject families, ``""`` for
      scalar leaves under the coupled-explicit family).
    * ``run_calculation_path`` — active iterate command.
    * ``bc_root`` / ``cz_root`` / ``interface_root`` — active namespace
      roots.
    * ``multiphase`` — ``None`` for single-phase, else a per-phase
      write-guidance dict:

      * ``model`` — VOF / Mixture / Eulerian.
      * ``phases`` — ordered list.
      * ``mixture_level_bc_template`` —
        ``"<bc_root>.<family>['<name>'].<leaf>"``.
      * ``per_phase_bc_template`` —
        ``"<bc_root>.<family>['<name>'].phase['<phase>'].multiphase.<leaf>"``.
      * ``per_phase_bc_note`` — "which BC leaves are per-phase vs mixture-level
        varies by model — call describe_path to confirm".
    """
    urf_fam = active_urf_family(mode)
    if urf_fam is UrfFamily.SEGREGATED:
        urf_root = _UR
        urf_key_template = "['<equation>']  # e.g. 'pressure', 'mom', 'k', 'omega', 'temperature'"
    elif urf_fam is UrfFamily.COUPLED_EXPLICIT:
        urf_root = _PVC
        urf_key_template = (
            ".explicit_<equation>_under_relaxation"
            "  # e.g. 'pressure', 'momentum', 'volume_fraction'"
            f" — OR {_RF}['<equation>'] for turbulence / energy"
        )
    else:  # PSEUDO_TIME
        urf_root = _PT
        urf_key_template = "['<equation>']  # e.g. 'pressure', 'mom', 'k', 'omega', 'temperature'"

    mp_block: dict[str, Any] | None = None
    if mode.multiphase:
        mp_block = {
            "model": mode.multiphase_model,
            "phases": list(mode.phases),
            "mixture_level_bc_template": (f"{bc_root(mode)}.<family>['<name>'].<mixture_leaf>"),
            "per_phase_bc_template": (
                f"{bc_root(mode)}.<family>['<name>'].phase['<phase>'].multiphase.<leaf>"
            ),
            "per_phase_bc_note": (
                "which BC leaves are per-phase vs mixture-level varies by "
                "model (VOF vs Mixture vs Eulerian) and by BC family — "
                "call describe_path on the specific leaf to confirm."
            ),
        }
    return {
        "urf_family": urf_fam.value,
        "urf_root": urf_root,
        "urf_key_template": urf_key_template,
        "run_calculation_path": run_calculation_path(mode),
        "bc_root": bc_root(mode),
        "cz_root": cz_root(mode),
        "interface_root": interface_root(mode),
        "multiphase": mp_block,
    }


def format_mode_summary(mode: SolverMode) -> str:
    """Return a short human-readable summary of ``mode`` for prompts.

    Two lines: one for the mode identity, one for the write-target
    hints (URF family, BC namespace, run command, multiphase state).
    Deliberately compact — the full JSON summary is available via
    :func:`describe_mode` and :func:`write_target_hints` when a caller
    needs to inspect it.
    """
    desc = describe_mode(mode)
    hints = write_target_hints(mode)
    parts = [
        f"time={desc['time']}",
        f"solver={desc['solver_type']}",
        f"flow_scheme={desc['flow_scheme'] or 'default'}",
        f"pseudo_transient={desc['pseudo_transient']}",
        f"bc_namespace={desc['bc_namespace']}",
        f"turbulence={desc['turbulence_model'] or 'none'}",
        f"energy={desc['energy']}",
    ]
    if desc["multiphase"]:
        parts.append(
            f"multiphase={desc['multiphase']['model']}("
            f"{','.join(desc['multiphase']['phases']) or '?'})"
        )
    line1 = "SOLVER MODE: " + " | ".join(parts)
    line2 = (
        f"URF root: {hints['urf_root']}{hints['urf_key_template']} | "
        f"run command: {hints['run_calculation_path']} | "
        f"BC root: {hints['bc_root']}"
    )
    if hints["multiphase"]:
        line2 += (
            f" | mixture BC leaves: {hints['multiphase']['mixture_level_bc_template']}"
            f" | per-phase BC leaves: {hints['multiphase']['per_phase_bc_template']}"
        )
    return line1 + "\n" + line2


__all__ = [
    "SolverMode",
    "UrfFamily",
    "PathGroup",
    "PathInfo",
    "RerouteResult",
    "WriteTarget",
    "is_coupled_scheme",
    "active_urf_family",
    "urf_path",
    "classify_path",
    "classify_methods_gate",
    "reroute",
    "resolve_write_target",
    "path_family",
    "bc_root",
    "cz_root",
    "interface_root",
    "bc_path",
    "cz_path",
    "run_calculation_path",
    "multiphase_volume_fraction_path",
    "multiphase_bc_phase_path",
    "describe_mode",
    "write_target_hints",
    "format_mode_summary",
    "MULTI_PATH_CLASSES",
]
