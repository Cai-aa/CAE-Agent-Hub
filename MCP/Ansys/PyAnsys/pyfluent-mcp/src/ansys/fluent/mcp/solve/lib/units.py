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

"""Unit- and quantity-aware parsing for free-text Fluent values.

PyFluent settings parameters generally accept either a bare numeric in
the Fluent active unit-system or a ``(value, unit)`` tuple. Host-generated
code that ignores units is a major source of silently-wrong
boundary conditions ("set inlet to 50 C" landing as 50 K because the
solver is in SI). This module extracts ``{value, unit, quantity}``
hints from a free-form prompt so the orchestrator can pass them to the
authoring host as structured context. The grounding pass can then rewrite plain
numeric literals into ``(value, unit)`` tuples when the target API
supports it.

This module is intentionally lightweight with no `pint` dependency. It only handle the
units that actually show up in CFD prompts. Anything ambiguous returns
``None``, and the caller must fall back to asking the user.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterator, Optional

# ---------------------------------------------------------------------------
# Unit catalog
# ---------------------------------------------------------------------------

# Map of canonical unit -> physical quantity. Aliases collapse to the
# canonical form via :data:`_UNIT_ALIASES`.
_UNITS: dict[str, str] = {
    "K": "temperature",
    "C": "temperature",
    "F": "temperature",
    "Pa": "pressure",
    "kPa": "pressure",
    "MPa": "pressure",
    "bar": "pressure",
    "atm": "pressure",
    "psi": "pressure",
    "m/s": "velocity",
    "cm/s": "velocity",
    "mm/s": "velocity",
    "ft/s": "velocity",
    "in/s": "velocity",
    "kg/s": "mass_flow",
    "g/s": "mass_flow",
    "lb/s": "mass_flow",
    "kg/m^3": "density",
    "g/cm^3": "density",
    "W": "power",
    "kW": "power",
    "MW": "power",
    "W/m^2": "heat_flux",
    "kW/m^2": "heat_flux",
    "Pa.s": "viscosity",
    "cP": "viscosity",
    "rad/s": "angular_velocity",
    "rpm": "angular_velocity",
    "m": "length",
    "cm": "length",
    "mm": "length",
    "in": "length",
    "ft": "length",
}

_UNIT_ALIASES: dict[str, str] = {
    "kelvin": "K",
    "k": "K",
    "celsius": "C",
    "degc": "C",
    "degC": "C",
    "°c": "C",
    "fahrenheit": "F",
    "degf": "F",
    "degF": "F",
    "°f": "F",
    "pascal": "Pa",
    "pa": "Pa",
    "kpa": "kPa",
    "mpa": "MPa",
    "bars": "bar",
    "atmosphere": "atm",
    "atms": "atm",
    "ms": "m/s",  # tricky; only matched as suffix to a number
    "kgs": "kg/s",
    "rpms": "rpm",
    "metres": "m",
    "meters": "m",
    "centimetres": "cm",
    "millimetres": "mm",
    "inches": "in",
    "feet": "ft",
    "watt": "W",
    "watts": "W",
    "kilowatt": "kW",
    "megawatt": "MW",
}

# Default Fluent unit-system per quantity (SI).
_FLUENT_DEFAULT_UNIT: dict[str, str] = {
    "temperature": "K",
    "pressure": "Pa",
    "velocity": "m/s",
    "mass_flow": "kg/s",
    "density": "kg/m^3",
    "power": "W",
    "heat_flux": "W/m^2",
    "viscosity": "Pa.s",
    "angular_velocity": "rad/s",
    "length": "m",
}

# Conversion to Fluent default unit. value_in_default = factor * value + offset.
_TO_DEFAULT: dict[str, tuple[float, float]] = {
    # temperature
    "K": (1.0, 0.0),
    "C": (1.0, 273.15),
    "F": (5 / 9, 459.67 * 5 / 9),
    # pressure
    "Pa": (1.0, 0.0),
    "kPa": (1e3, 0.0),
    "MPa": (1e6, 0.0),
    "bar": (1e5, 0.0),
    "atm": (101325.0, 0.0),
    "psi": (6894.757, 0.0),
    # velocity
    "m/s": (1.0, 0.0),
    "cm/s": (1e-2, 0.0),
    "mm/s": (1e-3, 0.0),
    "ft/s": (0.3048, 0.0),
    "in/s": (0.0254, 0.0),
    # mass_flow
    "kg/s": (1.0, 0.0),
    "g/s": (1e-3, 0.0),
    "lb/s": (0.45359237, 0.0),
    # density
    "kg/m^3": (1.0, 0.0),
    "g/cm^3": (1e3, 0.0),
    # power
    "W": (1.0, 0.0),
    "kW": (1e3, 0.0),
    "MW": (1e6, 0.0),
    # heat_flux
    "W/m^2": (1.0, 0.0),
    "kW/m^2": (1e3, 0.0),
    # viscosity
    "Pa.s": (1.0, 0.0),
    "cP": (1e-3, 0.0),
    # angular_velocity
    "rad/s": (1.0, 0.0),
    "rpm": (2 * 3.141592653589793 / 60.0, 0.0),
    # length
    "m": (1.0, 0.0),
    "cm": (1e-2, 0.0),
    "mm": (1e-3, 0.0),
    "in": (0.0254, 0.0),
    "ft": (0.3048, 0.0),
}


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Quantity:
    """A parsed numeric value with its unit and CFD quantity classification."""

    value: float
    unit: str  # canonical unit symbol
    quantity: str  # temperature | pressure | velocity | ...
    raw: str  # original substring as it appeared in the prompt

    def to_default(self) -> "Quantity":
        """Convert this quantity into the Fluent default unit for its quantity.

        Returns
        -------
        'Quantity'
            Result produced by the function.
        """
        target = _FLUENT_DEFAULT_UNIT.get(self.quantity)
        if target is None or target == self.unit:
            return self
        factor, offset = _TO_DEFAULT.get(self.unit, (1.0, 0.0))
        si_value = factor * self.value + offset
        # Now si_value is in the SI default; convert from SI to target if different
        # (in our table SI == Fluent default, so just return).
        return Quantity(value=si_value, unit=target, quantity=self.quantity, raw=self.raw)

    def to_dict(self) -> dict[str, object]:
        """Convert the object to a dictionary representation.

        Returns
        -------
        dict[str, object]
            Mapping containing the operation result.
        """
        return {
            "value": self.value,
            "unit": self.unit,
            "quantity": self.quantity,
            "raw": self.raw,
        }


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


_NUM = r"[-+]?(?:\d+\.\d+|\.\d+|\d+)(?:[eE][-+]?\d+)?"
# Build alternation of all known unit tokens (canonical + aliases), longest first.
_ALL_UNITS = sorted(
    set(_UNITS) | set(_UNIT_ALIASES),
    key=lambda u: -len(u),
)
# Escape and protect the slash so it matches as a literal.
_UNIT_PATTERN = "|".join(re.escape(u) for u in _ALL_UNITS)
_QTY_RE = re.compile(
    rf"({_NUM})\s*({_UNIT_PATTERN})\b",
    re.IGNORECASE,
)


def _resolve_unit(token: str) -> Optional[str]:
    """Resolve unit.

    Parameters
    ----------
    token : str
        Token to supply to the function.

    Returns
    -------
    Optional[str]
        Optional value produced by the operation.
    """
    if token in _UNITS:
        return token
    canon = _UNIT_ALIASES.get(token)
    if canon and canon in _UNITS:
        return canon
    canon = _UNIT_ALIASES.get(token.lower())
    if canon and canon in _UNITS:
        return canon
    # Case-insensitive lookup against the canonical table.
    lower = {k.lower(): k for k in _UNITS}
    return lower.get(token.lower())


def parse_quantities(text: str) -> list[Quantity]:
    """Extract every ``<number><unit>`` pair from ``text``.

    Order is preserved. Overlapping matches are not produced. (Regex
    consumes left to right). The returned list may be empty.

    Parameters
    ----------
    text : str
        Text value to parse, normalize, or write.

    Returns
    -------
    list[Quantity]
        Collection containing the operation results.
    """
    if not text:
        return []
    out: list[Quantity] = []
    for match in _QTY_RE.finditer(text):
        try:
            value = float(match.group(1))
        except ValueError:
            continue
        unit_token = match.group(2)
        canonical = _resolve_unit(unit_token)
        if canonical is None:
            continue
        quantity = _UNITS.get(canonical)
        if quantity is None:
            continue
        out.append(Quantity(value=value, unit=canonical, quantity=quantity, raw=match.group(0)))
    return out


def quantity_hints(text: str) -> list[dict[str, object]]:
    """Client-friendly serialization of every quantity in ``text``.

    Each hint contains the original literal, canonical unit,
    quantity classification, and value converted to Fluent's
    default SI unit so callers can plug it straight into PyFluent.

    Parameters
    ----------
    text : str
        Text value to parse, normalize, or write.

    Returns
    -------
    list[dict[str, object]]
        Mapping containing the operation result.
    """
    hints: list[dict[str, object]] = []
    for q in parse_quantities(text):
        normalised = q.to_default()
        hints.append(
            {
                "raw": q.raw,
                "value": q.value,
                "unit": q.unit,
                "quantity": q.quantity,
                "fluent_default": {
                    "value": normalised.value,
                    "unit": normalised.unit,
                },
            }
        )
    return hints


def iter_quantities(text: str) -> Iterator[Quantity]:
    """Return a generator of every ``<number><unit>`` pair from ``text``.

    Generator equivalent of :func:`parse_quantities`.

    Parameters
    ----------
    text : str
        Text value to parse, normalize, or write.

    Returns
    -------
    Iterator[Quantity]
        Result produced by the function.
    """
    yield from parse_quantities(text)


__all__ = [
    "Quantity",
    "parse_quantities",
    "quantity_hints",
    "iter_quantities",
]
