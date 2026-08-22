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

import gzip
import json

from ansys.fluent.mcp.solve.catalog import schema
from ansys.fluent.mcp.solve.catalog.schema import SettingsSchema, load_settings_schema


def _raw_schema():
    """Return a raw schema fixture for the test.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    return {
        "type": "group",
        "children": {
            "setup": {
                "type": "group",
                "children": {
                    "boundary-conditions": {
                        "type": "group",
                        "children": {
                            "wall": {
                                "type": "named-object",
                                "user-creatable?": True,
                                "object-type": {
                                    "type": "group",
                                    "children": {
                                        "thermal": {
                                            "type": "group",
                                            "children": {
                                                "enable?": {
                                                    "type": "boolean",
                                                    "help": "Enable heat transfer",
                                                    "has-allowed-values": True,
                                                }
                                            },
                                        }
                                    },
                                    "commands": {
                                        "set-temperature": {
                                            "help": "Set wall temperature",
                                            "arguments": {
                                                "wall-name": {
                                                    "type": "string",
                                                    "help": "Wall name",
                                                },
                                                "file-name": {
                                                    "type": "file",
                                                    "help": "Input profile",
                                                    "file-purpose": "input",
                                                },
                                            },
                                        }
                                    },
                                    "queries": {
                                        "get-temperature": {
                                            "help": "Read wall temperature",
                                            "arguments": {},
                                        }
                                    },
                                },
                            }
                        },
                    }
                },
            },
            "solution": {
                "type": "group",
                "child-aliases": {"run-calculation": "run_calculation"},
                "children": {},
            },
        },
    }


def test_settings_schema_resolves_paths_members_and_commands():
    """Verify that settings schema resolves paths members and commands.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    settings = SettingsSchema(_raw_schema(), source="fixture")

    container = settings.resolve("solver.settings.setup.boundary-conditions.wall")
    member = settings.resolve('setup.boundary_conditions.wall["wall-1"].thermal.enable')
    dotted_member = settings.resolve("setup.boundary_conditions.wall.wall_1.thermal")
    command = settings.lookup_command("setup.boundary_conditions.wall.wall_1.set_temperature")
    query = settings.lookup_command("setup.boundary_conditions.wall.wall_1.get_temperature")

    assert settings.source == "fixture"
    assert settings.node_count > 1
    assert container.kind == "named-object"
    assert container.user_creatable is True
    assert member.kind == "boolean"
    assert member.has_allowed_values is True
    assert dotted_member.kind == "group"
    assert command.py_name == "set_temperature"
    assert command.arg_names() == ["wall_name", "wall-name", "file_name", "file-name"]
    assert command.arguments[1].file_purpose == "input"
    assert query.is_query is True
    assert settings.resolve("missing.path") is None
    assert settings.lookup_command("setup.boundary_conditions.wall.missing") is None


def test_load_settings_schema_reads_json_and_gzip_overrides(tmp_path, monkeypatch):
    """Verify that load settings schema reads json and gzip overrides.

    Parameters
    ----------
    tmp_path : Any
        Path for the tmp.
    monkeypatch : Any
        Pytest fixture used to patch environment variables or dependencies.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    json_path = tmp_path / "settings.json"
    gzip_path = tmp_path / "settings.json.gz"
    json_path.write_text(json.dumps(_raw_schema()), encoding="utf-8")
    with gzip.open(gzip_path, "wt", encoding="utf-8") as handle:
        json.dump(_raw_schema(), handle)

    load_settings_schema.cache_clear()
    monkeypatch.setenv(schema._OVERRIDE_ENV, str(json_path))
    loaded_json = load_settings_schema("test")

    load_settings_schema.cache_clear()
    monkeypatch.setenv(schema._OVERRIDE_ENV, str(gzip_path))
    loaded_gzip = load_settings_schema("test")

    assert loaded_json.resolve("setup.boundary_conditions.wall") is not None
    assert loaded_json.source == str(json_path)
    assert loaded_gzip.resolve("setup.boundary_conditions.wall") is not None
    assert loaded_gzip.source == str(gzip_path)


def test_load_settings_schema_returns_none_for_missing_or_bad_override(tmp_path, monkeypatch):
    """Verify that load settings schema returns none for missing or bad override.

    Parameters
    ----------
    tmp_path : Any
        Path for the tmp.
    monkeypatch : Any
        Pytest fixture used to patch environment variables or dependencies.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    load_settings_schema.cache_clear()
    monkeypatch.setenv(schema._OVERRIDE_ENV, str(tmp_path / "missing.json"))
    monkeypatch.setattr(schema, "_locate_default_data", lambda: None)
    assert load_settings_schema("test") is None

    bad_path = tmp_path / "bad.json"
    bad_path.write_text("not json", encoding="utf-8")
    load_settings_schema.cache_clear()
    monkeypatch.setenv(schema._OVERRIDE_ENV, str(bad_path))
    assert load_settings_schema("test") is None
