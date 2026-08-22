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

from ansys.cfx.mcp.cfx.grounding import ground_code
from ansys.cfx.mcp.cfx.schema_cache import (
    CFXSchemaCache,
    get_schema_cache,
    to_python_name,
)

_FLUID_MODELS = 'setup.flow["F"].domain["D"].fluid_models'
_TURB_OPTION = f"{_FLUID_MODELS}.turbulence_model.option"
_MATERIAL = 'setup.flow["F"].domain["D"].fluid_definition["Water"].material'


@pytest.fixture(scope="module")
def cache() -> CFXSchemaCache:
    return get_schema_cache()


# -- to_python_name --------------------------------------------------------
@pytest.mark.parametrize(
    ("cfx_name", "expected"),
    [
        ("FLOW", "flow"),
        ("SOLVER CONTROL", "solver_control"),
        ("Default Domain", "default_domain"),
        ("Drag Coefficient", "drag_coefficient"),
        ("", ""),
    ],
)
def test_to_python_name(cfx_name: str, expected: str) -> None:
    assert to_python_name(cfx_name) == expected


def test_to_python_name_keyword_collision() -> None:
    # "class" is a Python keyword and must be suffixed.
    assert to_python_name("class") == "class_"


# -- CFXSchemaCache --------------------------------------------------------
def test_cache_loads_many_nodes(cache: CFXSchemaCache) -> None:
    assert len(cache) > 5000


def test_exists_known_parameter(cache: CFXSchemaCache) -> None:
    assert cache.exists(_TURB_OPTION)
    assert cache.exists(_MATERIAL)


def test_exists_unknown_parameter(cache: CFXSchemaCache) -> None:
    assert not cache.exists(f"{_FLUID_MODELS}.turbulance_model.option")


def test_get_returns_node_metadata(cache: CFXSchemaCache) -> None:
    node = cache.get(_TURB_OPTION)
    assert node is not None
    assert node.kind == "Parameter"
    assert node.path  # normalised path is populated


def test_children_lists_attributes(cache: CFXSchemaCache) -> None:
    kids = cache.children(_FLUID_MODELS)
    assert "turbulence_model" in kids


def test_children_unknown_path_is_empty(cache: CFXSchemaCache) -> None:
    assert cache.children(f"{_FLUID_MODELS}.does_not_exist") == []


def test_suggest_fixes_typo(cache: CFXSchemaCache) -> None:
    suggestions = cache.suggest(f"{_FLUID_MODELS}.turbulance_model")
    assert any(s.endswith("turbulence_model") for s in suggestions)


def test_suggest_known_path_returns_itself(cache: CFXSchemaCache) -> None:
    assert cache.suggest(f"{_FLUID_MODELS}.turbulence_model")


# -- grounding -------------------------------------------------------------
def test_ground_code_fixes_leaf_typo() -> None:
    src = f'{_FLUID_MODELS}.turbulance_model.option = "k epsilon"'
    out, report = ground_code(src)
    assert ".turbulence_model.option" in out
    assert ("turbulance_model", "turbulence_model") in report.replacements
    assert report.changed


def test_ground_code_fixes_material_typo() -> None:
    src = 'setup.flow["F"].domain["D"].fluid_definition["Water"].materail = "Water"'
    out, report = ground_code(src)
    assert out.endswith('.material = "Water"')
    assert report.changed


def test_ground_code_leaves_valid_chain_untouched() -> None:
    src = f"x = {_TURB_OPTION}"
    out, report = ground_code(src)
    assert out == src
    assert not report.changed


def test_ground_code_preserves_instance_keys() -> None:
    src = f"{_FLUID_MODELS}.turbulance_model.option = 1"
    out, _ = ground_code(src)
    assert 'flow["F"]' in out
    assert 'domain["D"]' in out


def test_ground_code_unresolved_leaf_left_as_is() -> None:
    src = 'setup.flow["F"].domain["D"].zzz_nonexistent.foo = 1'
    out, report = ground_code(src)
    assert out == src
    assert not report.changed
    assert report.unresolved


def test_ground_code_empty_input() -> None:
    out, report = ground_code("")
    assert out == ""
    assert not report.changed


def test_ground_code_with_explicit_cache(cache: CFXSchemaCache) -> None:
    src = f"{_FLUID_MODELS}.turbulance_model.option = 1"
    out, report = ground_code(src, cache=cache)
    assert ".turbulence_model.option" in out
