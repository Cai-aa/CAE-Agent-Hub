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

"""Tests for the ``toolsets://definition`` MCP resource."""

import asyncio

import pytest

# Importing tools, contexts, and toolsets ensures everything is registered on `app`.
from ansys.aedt.mcp import (
    contexts,  # noqa: F401
    tools,  # noqa: F401
    toolsets as toolsets_module,  # noqa: F401
)
from ansys.aedt.mcp.server import app
from ansys.aedt.mcp.toolsets import _TOOLSET_CATALOGUE, _build_toolsets

REQUIRED_KEYS = {"name", "description", "skill", "tools"}


def _list_tool_names() -> set[str]:
    async def _list():
        return await app._local_provider._list_tools()

    return {t.name for t in asyncio.run(_list())}


class TestToolsetsResource:
    def test_build_returns_list(self):
        result = _build_toolsets()
        assert isinstance(result, list)
        assert len(result) > 0

    def test_items_have_required_keys(self):
        for entry in _build_toolsets():
            assert REQUIRED_KEYS <= entry.keys(), (
                f"toolset {entry.get('name')} missing keys: {REQUIRED_KEYS - entry.keys()}"
            )

    def test_string_fields_are_non_empty(self):
        for entry in _build_toolsets():
            for key in ("name", "description", "skill"):
                assert isinstance(entry[key], str) and entry[key].strip(), (
                    f"toolset {entry['name']!r} field {key!r} is empty"
                )

    def test_tools_field_is_list_of_strings(self):
        for entry in _build_toolsets():
            assert isinstance(entry["tools"], list)
            assert all(isinstance(t, str) and t for t in entry["tools"])

    def test_toolset_names_unique(self):
        names = [e["name"] for e in _build_toolsets()]
        assert len(names) == len(set(names))

    def test_each_listed_tool_is_a_real_registered_tool(self):
        registered = _list_tool_names()
        missing: list[tuple[str, str]] = []
        for entry in _build_toolsets():
            for tool in entry["tools"]:
                if tool not in registered:
                    missing.append((entry["name"], tool))
        assert not missing, (
            "Toolset catalogue references unregistered tools:\n  - "
            + "\n  - ".join(f"{ts}: {t}" for ts, t in missing)
        )

    def test_every_registered_tool_appears_in_some_toolset(self):
        registered = _list_tool_names()
        listed = {t for e in _build_toolsets() for t in e["tools"]}
        orphans = registered - listed
        assert not orphans, (
            "The following registered tools are not listed in any toolset "
            "in toolsets.py:\n  - "
            + "\n  - ".join(sorted(orphans))
            + "\n\nAdd each to the appropriate toolset in "
            "ansys/aedt/mcp/toolsets.py::_TOOLSET_CATALOGUE."
        )

    def test_no_tool_listed_in_multiple_toolsets(self):
        seen: dict[str, str] = {}
        duplicates: list[tuple[str, str, str]] = []
        for entry in _build_toolsets():
            for tool in entry["tools"]:
                if tool in seen:
                    duplicates.append((tool, seen[tool], entry["name"]))
                else:
                    seen[tool] = entry["name"]
        assert not duplicates, "Tools appearing in multiple toolsets:\n  - " + "\n  - ".join(
            f"{t} in {a!r} and {b!r}" for t, a, b in duplicates
        )

    def test_resource_is_registered(self):
        async def _list():
            return await app._list_resources()

        resources = asyncio.run(_list())
        uris = {str(r.uri) for r in resources}
        assert "toolsets://definition" in uris, (
            f"toolsets://definition not registered. Found: {sorted(uris)}"
        )

    def test_catalogue_is_module_constant(self):
        # Stability anchor: ensure module exposes the catalogue dict.
        assert isinstance(_TOOLSET_CATALOGUE, dict)
        assert _TOOLSET_CATALOGUE  # non-empty

    def test_lifecycle_skill_prefers_existing_sessions(self):
        lifecycle_skill = _TOOLSET_CATALOGUE["lifecycle"]["skill"]

        assert "First call check_aedt_status before every workflow" in lifecycle_skill
        assert "include the option to open a new session instead" in lifecycle_skill
        assert "launch_aedt(confirm_new_session=True)" in lifecycle_skill
        assert "connected session has no open projects" in lifecycle_skill
        assert "call create_design with the matching app_type" in lifecycle_skill


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
