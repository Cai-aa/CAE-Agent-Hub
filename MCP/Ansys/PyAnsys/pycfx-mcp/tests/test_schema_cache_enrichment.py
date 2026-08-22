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

"""CFX schema-cache enrichment: ``has_allowed_values`` + command args.

Phase 12 extends :class:`CFXSchemaCache` with:

* an ``enums`` lookup populated from the top-level ``enums`` block of
  each loaded config file,
* a ``CommandArgument`` schema attached to every ``Command`` /
  ``Query`` node — extracted from the JSON ``args`` list,
* the public accessors ``has_allowed_values``, ``get_allowed_values``,
  ``get_command_arguments``.

The tests below pin those behaviours by writing a tiny config-file
fixture instead of relying on the bundled CFX JSON whose schema
shape we don't control.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import ansys.cfx.mcp.cfx.schema_cache as sc_mod
from ansys.cfx.mcp.cfx.schema_cache import (
    CFXSchemaCache,
    CommandArgument,
    SchemaNode,
)


@pytest.fixture
def synthetic_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """Write a tiny schema JSON into a temporary location and
    point the cache loader at it via ``resources.files`` monkey
    patching."""
    payload = {
        "type": "group",
        "help": "root",
        "enums": {
            "TurbModel": {
                "type": "enum",
                "help": "Turbulence model option",
                "values": ["k epsilon", "k omega", "SST", "laminar"],
            },
        },
        "children": {
            "solver_control": {
                "type": "group",
                "help": "Solver control branch",
                "children": {
                    "timescale_factor": {
                        "type": "real",
                        "help": "Timescale multiplier",
                    },
                    "turbulence_option": {
                        "type": "TurbModel",
                        "help": "Active turbulence model",
                    },
                    "convergence_target": {
                        "type": "string",
                        "values": ["Low", "Medium", "High"],
                        "help": "Convergence stringency",
                    },
                },
                "commands": {
                    "start_run": {
                        "type": "command",
                        "help": "Start the solver run.",
                        "args": [
                            {
                                "name": "case_file",
                                "type": "str",
                                "default": "None",
                            },
                            {
                                "name": "parallel",
                                "type": "bool",
                                "default": "False",
                                "help": "Run in parallel",
                            },
                            "not-a-dict-entry-should-be-skipped",
                            {"type": "missing-name-skipped"},
                        ],
                    },
                },
                "queries": {
                    "is_converged": {
                        "type": "query",
                        "help": "Has the run converged?",
                        "args": [],
                    },
                },
            },
        },
    }
    cfg_file = tmp_path / "synthetic.json"
    cfg_file.write_text(json.dumps(payload), encoding="utf-8")

    # Patch ``importlib.resources.files`` so the cache loads our
    # tiny payload instead of the bundled CFX JSON.
    class _FakeResource:
        def __init__(self, path: Path) -> None:
            self._path = path

        def joinpath(self, name: str) -> "_FakeResource":
            return _FakeResource(self._path / name)

        def read_text(self, encoding: str = "utf-8") -> str:
            return self._path.read_text(encoding=encoding)

    def _fake_files(_pkg: str) -> _FakeResource:
        return _FakeResource(tmp_path)

    monkeypatch.setattr(sc_mod.resources, "files", _fake_files)
    return cfg_file.name


# ---------------------------------------------------------------------
# allowed_values — enum + inline values
# ---------------------------------------------------------------------


def test_enum_reference_attaches_allowed_values(synthetic_config: str):
    cache = CFXSchemaCache(config_files=[synthetic_config])
    node = cache.get("solver_control.turbulence_option")
    assert node is not None
    assert node.has_allowed_values
    assert node.allowed_values == ("k epsilon", "k omega", "SST", "laminar")


def test_inline_values_list_attaches_allowed_values(synthetic_config: str):
    cache = CFXSchemaCache(config_files=[synthetic_config])
    node = cache.get("solver_control.convergence_target")
    assert node is not None
    assert node.has_allowed_values
    assert node.allowed_values == ("Low", "Medium", "High")


def test_primitive_leaf_has_no_allowed_values(synthetic_config: str):
    cache = CFXSchemaCache(config_files=[synthetic_config])
    node = cache.get("solver_control.timescale_factor")
    assert node is not None
    assert not node.has_allowed_values
    assert node.allowed_values is None


def test_has_allowed_values_accessor(synthetic_config: str):
    cache = CFXSchemaCache(config_files=[synthetic_config])
    assert cache.has_allowed_values("solver_control.turbulence_option")
    assert not cache.has_allowed_values("solver_control.timescale_factor")
    assert not cache.has_allowed_values("solver_control.nonexistent")


def test_get_allowed_values_accessor(synthetic_config: str):
    cache = CFXSchemaCache(config_files=[synthetic_config])
    assert cache.get_allowed_values("solver_control.turbulence_option") == (
        "k epsilon",
        "k omega",
        "SST",
        "laminar",
    )
    assert cache.get_allowed_values("solver_control.timescale_factor") is None
    assert cache.get_allowed_values("solver_control.missing") is None


# ---------------------------------------------------------------------
# command arguments — schema indexing
# ---------------------------------------------------------------------


def test_command_arguments_indexed(synthetic_config: str):
    cache = CFXSchemaCache(config_files=[synthetic_config])
    args = cache.get_command_arguments("solver_control.start_run")
    assert len(args) == 2  # malformed entries skipped
    case_arg, parallel_arg = args
    assert case_arg == CommandArgument(name="case_file", type_hint="str", default="None", help="")
    assert parallel_arg == CommandArgument(
        name="parallel",
        type_hint="bool",
        default="False",
        help="Run in parallel",
    )


def test_command_args_empty_for_non_command(synthetic_config: str):
    cache = CFXSchemaCache(config_files=[synthetic_config])
    assert cache.get_command_arguments("solver_control.timescale_factor") == ()
    assert cache.get_command_arguments("solver_control") == ()


def test_query_arguments_indexed(synthetic_config: str):
    cache = CFXSchemaCache(config_files=[synthetic_config])
    args = cache.get_command_arguments("solver_control.is_converged")
    # Empty args list → empty tuple.
    assert args == ()
    # But the node itself exists as a Query.
    node = cache.get("solver_control.is_converged")
    assert node is not None
    assert node.kind == "Query"


def test_unknown_path_returns_empty_arguments(synthetic_config: str):
    cache = CFXSchemaCache(config_files=[synthetic_config])
    assert cache.get_command_arguments("does.not.exist") == ()


# ---------------------------------------------------------------------
# SchemaNode.is_command / .has_allowed_values invariants
# ---------------------------------------------------------------------


def test_schema_node_is_command_flag(synthetic_config: str):
    cache = CFXSchemaCache(config_files=[synthetic_config])
    cmd = cache.get("solver_control.start_run")
    assert cmd is not None
    assert cmd.is_command is True
    leaf = cache.get("solver_control.timescale_factor")
    assert leaf is not None
    assert leaf.is_command is False


def test_schema_node_has_allowed_values_empty_tuple():
    node = SchemaNode(
        path="x",
        kind="Parameter",
        cfx_type="real",
        allowed_values=(),
    )
    # Empty enumeration is treated as "no constraint" — explicit
    # length check.
    assert not node.has_allowed_values
