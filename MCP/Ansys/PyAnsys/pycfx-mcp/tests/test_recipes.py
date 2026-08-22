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

from __future__ import annotations

import pytest

from ansys.cfx.mcp.cfx.recipes import (
    RECIPES,
    Recipe,
    match_recipes,
    recipes_prompt_block,
)


# -- recipe library --------------------------------------------------------
def test_recipes_are_unique() -> None:
    names = [r.name for r in RECIPES]
    assert len(names) == len(set(names))


def test_outlet_recipe_is_minimal_and_idiomatic() -> None:
    outlet = next(r for r in RECIPES if r.name == "create_outlet")
    # Correct creation idiom and direct boundary_type assignment.
    assert 'domain.boundary["outlet"] = {}' in outlet.minimal
    assert 'outlet.boundary_type = "OUTLET"' in outlet.minimal
    # Minimal snippet must NOT contain guessed pressure / mass_and_momentum.
    assert "relative_pressure" not in outlet.minimal
    assert "mass_and_momentum" not in outlet.minimal
    # Those live in the optional block instead.
    assert "relative_pressure" in outlet.optional


def test_boundary_type_is_not_dot_option() -> None:
    for name in ("create_outlet", "create_inlet", "create_wall"):
        recipe = next(r for r in RECIPES if r.name == name)
        assert "boundary_type.option" not in recipe.minimal


# -- matching --------------------------------------------------------------
@pytest.mark.parametrize(
    ("prompt", "expected"),
    [
        ("create outlet", "create_outlet"),
        ("add an inlet", "create_inlet"),
        ("make a wall boundary", "create_wall"),
        ("set the turbulence model to SST", "set_turbulence_model"),
        ("use water as the fluid material", "set_fluid_material"),
    ],
)
def test_match_recipes_top_hit(prompt: str, expected: str) -> None:
    matches = match_recipes(prompt)
    assert matches
    assert matches[0].name == expected


def test_match_recipes_empty_prompt() -> None:
    assert match_recipes("") == []


def test_match_recipes_no_match() -> None:
    assert match_recipes("export the mesh to a parasolid file") == []


def test_match_recipes_respects_limit() -> None:
    matches = match_recipes("create outlet inlet wall turbulence material", limit=2)
    assert len(matches) <= 2


# -- prompt block ----------------------------------------------------------
def test_recipes_prompt_block_empty() -> None:
    assert recipes_prompt_block([]) == ""


def test_recipes_prompt_block_contains_minimal_directive() -> None:
    block = recipes_prompt_block(match_recipes("create outlet"))
    assert "MINIMAL" in block
    assert "create_outlet" in block
    assert 'boundary["outlet"] = {}' in block


def test_recipe_render_includes_optional_and_notes() -> None:
    recipe = Recipe(
        name="x",
        summary="s",
        keywords=("x",),
        minimal="a = 1",
        optional="b = 2",
        notes="be careful",
    )
    text = recipe.render()
    assert "Minimal" in text
    assert "Optional" in text
    assert "be careful" in text
