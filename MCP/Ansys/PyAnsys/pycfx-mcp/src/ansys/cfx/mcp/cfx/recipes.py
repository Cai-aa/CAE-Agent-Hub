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

"""Canonical PyCFX code recipes.

These recipes are distilled from the `examples <https://cfx.docs.pyansys.com/version/stable/examples/index.html>`_
in PyCFX documentation and act as the authoritative pattern library for
custom Python authoring. Anchoring callers to these snippets keeps code idiomatic
(correct creation idiom and real attribute names) and *minimal*. When a user asks
to "create an outlet," the author should emit only the required lines and avoid
extra boundary-condition values that were never requested.

"""

from __future__ import annotations

from dataclasses import dataclass
import re

__all__ = ["Recipe", "RECIPES", "match_recipes", "recipes_prompt_block"]


@dataclass(frozen=True)
class Recipe:
    """A single canonical PyCFX pattern.

    Parameters
    ----------
    name : str
        Short identifier such as ``"create_outlet"``.
    summary : str
        One-line description to show to the model.
    keywords : tuple[str, ...]
        Lower-case trigger tokens to match against the user prompt.
    minimal : str
        Smallest correct snippet that satisfies the bare request. This is
        what the model should emit unless the user explicitly asks for more.
    optional : str, default: ``""``
        Extra lines the model may add *only* when the user explicitly requests
        the corresponding setting (documented, never auto-applied).
    notes : str, default: ``""``
        Free-form text describing the recipe, its idioms, and any gotchas. This
        is guidance the model must respect.
    """

    name: str
    summary: str
    keywords: tuple[str, ...]
    minimal: str
    optional: str = ""
    notes: str = ""

    def render(self) -> str:
        """Render this CFX recipe as a prompt-ready canonical code example.

        Returns
        -------
        str
            String value produced for the requested CFX or provider operation.
        """
        parts = [
            f"### Recipe: {self.name}",
            self.summary,
            "",
            "Minimal (emit only this unless more is asked):",
            "```python",
            self.minimal.strip(),
            "```",
        ]
        if self.optional.strip():
            parts += [
                "",
                "Optional (add ONLY if the user explicitly asks):",
                "```python",
                self.optional.strip(),
                "```",
            ]
        if self.notes.strip():
            parts += ["", f"Notes: {self.notes.strip()}"]
        return "\n".join(parts)


# A small canonical domain handle the snippets assume already exists. The
# grounding/runtime layer can rebind ``domain`` to the live default domain.
_DOMAIN = 'domain = pre.setup.flow["Flow Analysis 1"].domain["Default Domain"]'

RECIPES: tuple[Recipe, ...] = (
    Recipe(
        name="create_outlet",
        summary="Create an OUTLET boundary on the default domain.",
        keywords=("outlet", "out boundary", "create outlet", "add outlet"),
        minimal=(
            f"{_DOMAIN}\n"
            'domain.boundary["outlet"] = {}\n'
            'outlet = domain.boundary["outlet"]\n'
            'outlet.boundary_type = "OUTLET"\n'
            'outlet.location = "out"'
        ),
        optional=(
            'outlet.boundary_conditions.mass_and_momentum.option = "Average Static Pressure"\n'
            'outlet.boundary_conditions.mass_and_momentum.relative_pressure = "0 [Pa]"'
        ),
        notes=(
            "Create with `domain.boundary[name] = {}` first, then bind the handle. "
            '`boundary_type` is a direct string assignment ("OUTLET"), NOT `.option`. '
            "`location` is MANDATORY (CFX rejects an undefined region). It defaults "
            'to "out" for an outlet unless the user names a mesh region. '
            "Do not set pressure or mass_and_momentum unless asked."
        ),
    ),
    Recipe(
        name="create_inlet",
        summary="Create an INLET boundary on the default domain.",
        keywords=("inlet", "in boundary", "create inlet", "add inlet"),
        minimal=(
            f"{_DOMAIN}\n"
            'domain.boundary["in1"] = {}\n'
            'in1 = domain.boundary["in1"]\n'
            'in1.boundary_type = "INLET"\n'
            'in1.location = "in1"'
        ),
        optional=(
            'in1.boundary_conditions.mass_and_momentum.option = "Normal Speed"\n'
            'in1.boundary_conditions.mass_and_momentum.normal_speed = "2 [m s^-1]"\n'
            'in1.boundary_conditions.heat_transfer.static_temperature = "300 [K]"'
        ),
        notes=(
            'Create with `domain.boundary[name] = {}` first. `boundary_type = "INLET"` '
            "is a direct string assignment. `location` is MANDATORY (CFX rejects an "
            "undefined region). Inlets are NUMBERED: the first inlet is named/located "
            '"in1", the second "in2", etc. (name matches location). Add '
            "speed/temperature only when requested."
        ),
    ),
    Recipe(
        name="create_wall",
        summary="Create a WALL boundary on the default domain.",
        keywords=("wall", "create wall", "add wall"),
        minimal=(
            f"{_DOMAIN}\n"
            'domain.boundary["wall"] = {}\n'
            'wall = domain.boundary["wall"]\n'
            'wall.boundary_type = "WALL"\n'
            'wall.location = "wall"'
        ),
        optional="",
        notes=(
            '`boundary_type = "WALL"` is a direct string assignment. `location` is '
            'MANDATORY (CFX rejects an undefined region). It defaults to "wall".'
        ),
    ),
    Recipe(
        name="set_fluid_material",
        summary="Assign a fluid material on the default domain.",
        keywords=("material", "fluid", "set water", "set air", "fluid definition"),
        minimal=(f'{_DOMAIN}\ndomain.fluid_definition["Fluid 1"].material = "Water"'),
        notes='Use the instance key `fluid_definition["Fluid 1"]`. Assign `.material` directly.',
    ),
    Recipe(
        name="set_turbulence_model",
        summary="Set the turbulence model on the default domain.",
        keywords=("turbulence", "k epsilon", "k omega", "sst", "laminar"),
        minimal=(f'{_DOMAIN}\ndomain.fluid_models.turbulence_model.option = "k epsilon"'),
        notes=(
            '`turbulence_model.option` takes a string such as "k epsilon", "SST", or "None" '
            "for laminar."
        ),
    ),
    Recipe(
        name="set_heat_transfer_model",
        summary="Set the heat transfer model on the default domain.",
        keywords=("heat transfer", "thermal energy", "total energy", "isothermal"),
        minimal=(f'{_DOMAIN}\ndomain.fluid_models.heat_transfer_model.option = "Thermal Energy"'),
        notes='Options include "Thermal Energy", "Total Energy", "Isothermal", "None".',
    ),
    Recipe(
        name="set_solver_control",
        summary="Configure basic solver control (advection scheme + timescale).",
        keywords=("solver control", "advection", "timescale", "physical timescale"),
        minimal=(
            'solver_control = pre.setup.flow["Flow Analysis 1"].solver_control\n'
            'solver_control.advection_scheme.option = "Upwind"\n'
            'solver_control.convergence_control.timescale_control = "Physical Timescale"\n'
            'solver_control.convergence_control.physical_timescale = "2 [s]"'
        ),
        notes=(
            "Only emit the lines the user asks . Do not add convergence criteria unless requested."
        ),
    ),
)


def _tokenize(text: str) -> set[str]:
    """Tokenize user prompt text for deterministic CFX recipe matching.

    Parameters
    ----------
    text : str
        Text content to inspect, tokenize, or render.

    Returns
    -------
    set[str]
        Value computed by the helper for the requested CFX workflow.
    """
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def match_recipes(prompt: str, *, limit: int = 3) -> list[Recipe]:
    """Return CFX recipes whose trigger words match the user prompt.

    Parameters
    ----------
    prompt : str
        Natural-language user request to process.
    limit : int, default: 3
        Maximum number of records to return.

    Returns
    -------
    list[Recipe]
        Value computed by the helper for the requested CFX workflow.
    """
    if not prompt:
        return []
    prompt_tokens = _tokenize(prompt)
    prompt_lower = prompt.lower()
    scored: list[tuple[int, Recipe]] = []
    for recipe in RECIPES:
        score = 0
        for kw in recipe.keywords:
            if " " in kw:
                if kw in prompt_lower:
                    score += 2  # multi-word phrase match is strong
            elif kw in prompt_tokens:
                score += 1
        if score:
            scored.append((score, recipe))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [recipe for _score, recipe in scored[:limit]]


def recipes_prompt_block(recipes: list[Recipe]) -> str:
    """Render matching CFX recipes as a compact prompt context block.

    Parameters
    ----------
    recipes : list[Recipe]
        Recipe definitions to render into the code-generation prompt.

    Returns
    -------
    str
        String value produced for the requested CFX or provider operation.
    """
    if not recipes:
        return ""
    rendered = "\n\n".join(recipe.render() for recipe in recipes)
    return (
        "Use the following canonical PyCFX recipes as the authoritative pattern. "
        "Emit the MINIMAL snippet that satisfies the request. Do NOT add optional "
        "settings, locations, or numeric values unless the user explicitly asked "
        "for them.\n\n" + rendered
    )
