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

import math

import pytest

from ansys.fluent.mcp.solve.lib.units import (
    Quantity,
    iter_quantities,
    parse_quantities,
    quantity_hints,
)


def test_parse_quantities_preserves_order_and_classifies_units():
    """Verify that parse quantities preserves order and classifies units.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    found = parse_quantities("Inlet at 50 C, 10 psi, 3 m/s, 2 kg/s, and 4 ft.")

    assert [(q.value, q.unit, q.quantity, q.raw) for q in found] == [
        (50.0, "C", "temperature", "50 C"),
        (10.0, "psi", "pressure", "10 psi"),
        (3.0, "m/s", "velocity", "3 m/s"),
        (2.0, "kg/s", "mass_flow", "2 kg/s"),
        (4.0, "ft", "length", "4 ft"),
    ]


@pytest.mark.parametrize(
    ("text", "unit", "quantity"),
    [
        ("300 kelvin", "K", "temperature"),
        ("20 degC", "C", "temperature"),
        ("12 meters", "m", "length"),
        ("3 feet", "ft", "length"),
        ("120 rpms", "rpm", "angular_velocity"),
        ("1.2 g/cm^3", "g/cm^3", "density"),
        ("18 kW/m^2", "kW/m^2", "heat_flux"),
        ("7 cP", "cP", "viscosity"),
        ("9 MW", "MW", "power"),
    ],
)
def test_parse_quantities_resolves_aliases_and_special_units(text, unit, quantity):
    """Verify that parse quantities resolves aliases and special units.

    Parameters
    ----------
    text : Any
        Text value to parse, normalize, or write.
    unit : Any
        Unit to supply to the function.
    quantity : Any
        Quantity to supply to the function.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    [quantity_found] = parse_quantities(text)

    assert quantity_found.unit == unit
    assert quantity_found.quantity == quantity


@pytest.mark.parametrize(
    ("quantity", "expected_value", "expected_unit"),
    [
        (Quantity(50, "C", "temperature", "50 C"), 323.15, "K"),
        (Quantity(32, "F", "temperature", "32 F"), 273.15, "K"),
        (Quantity(10, "psi", "pressure", "10 psi"), 68947.57, "Pa"),
        (Quantity(60, "rpm", "angular_velocity", "60 rpm"), 2 * math.pi, "rad/s"),
        (Quantity(12, "in", "length", "12 in"), 0.3048, "m"),
    ],
)
def test_quantity_to_default_converts_to_fluent_si(quantity, expected_value, expected_unit):
    """Verify that quantity to default converts to fluent si.

    Parameters
    ----------
    quantity : Any
        Quantity to supply to the function.
    expected_value : Any
        Expected value to supply to the function.
    expected_unit : Any
        Expected unit to supply to the function.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    converted = quantity.to_default()

    assert converted.value == pytest.approx(expected_value)
    assert converted.unit == expected_unit
    assert converted.quantity == quantity.quantity
    assert converted.raw == quantity.raw


def test_quantity_to_dict_and_unknown_default_unit():
    """Verify that quantity to dict and unknown default unit.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    quantity = Quantity(5, "widget", "unknown", "5 widget")

    assert quantity.to_default() is quantity
    assert quantity.to_dict() == {
        "value": 5,
        "unit": "widget",
        "quantity": "unknown",
        "raw": "5 widget",
    }


def test_quantity_hints_include_normalized_fluent_defaults():
    """Verify that quantity hints include normalized fluent defaults.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    hints = quantity_hints("heat at 2 kW and speed 60 rpm")

    assert hints == [
        {
            "raw": "2 kW",
            "value": 2.0,
            "unit": "kW",
            "quantity": "power",
            "fluent_default": {"value": 2000.0, "unit": "W"},
        },
        {
            "raw": "60 rpm",
            "value": 60.0,
            "unit": "rpm",
            "quantity": "angular_velocity",
            "fluent_default": {"value": 2 * math.pi, "unit": "rad/s"},
        },
    ]


def test_iter_quantities_matches_parser_and_empty_text_returns_empty():
    """Verify that iter quantities matches parser and empty text returns empty.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    assert list(iter_quantities("1 cm and 2 mm")) == parse_quantities("1 cm and 2 mm")
    assert parse_quantities("") == []
