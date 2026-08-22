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

import asyncio
import json

from ansys.fluent.mcp.solve.catalog import index as catalog_index, retriever as catalog_retriever
from ansys.fluent.mcp.solve.catalog.index import ApiIndex, _normalise_path, _parse_line, _tokenise
from ansys.fluent.mcp.solve.catalog.retriever import (
    ApiHit,
    LexicalApiRetriever,
    get_api_retriever_for_session,
)


def _api_objects_file(tmp_path):
    """Create a temporary API objects file for the test.

    Parameters
    ----------
    tmp_path : Any
        Path for the tmp.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    path = tmp_path / "api_objects.json"
    path.write_text(
        json.dumps(
            {
                "api_objects": [
                    "<solver_session>.setup.boundary_conditions.velocity_inlet (Object)",
                    "<solver_session>.setup.boundary_conditions.velocity_inlet.thermal (Group)",
                    "<solver_session>.setup.boundary_conditions.velocity_inlet.thermal.t (Parameter)",  # noqa: E501
                    "<solver_session>.solution.run_calculation.iterate (Command)",
                    "<meshing_session>.workflow.task (Object)",
                    "<solver_session>.tui.file.read_case (Command)",
                    "bad line",
                ]
            }
        ),
        encoding="utf-8",
    )
    return path


def test_api_index_loads_filters_and_searches_with_help_tokens(tmp_path):
    """Verify that api index loads filters and searches with help tokens.

    Parameters
    ----------
    tmp_path : Any
        Path for the tmp.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    index = ApiIndex(
        custom_path=str(_api_objects_file(tmp_path)),
        help_map={
            "velocity_inlet": "incoming gas inlet boundary",
            "thermal": "thermal temperature settings",
            "t": "Static temperature value",
        },
    )

    hits = index.search("incoming gas temperature", kinds=["Parameter"], top_k=3)
    under_hits = index.search("iterate", under="solution")
    children = index.children_of("setup.boundary_conditions", max_results=10)

    assert index.available is True
    assert (
        index.lookup('setup.boundary_conditions.velocity_inlet["inlet-1"].thermal.t').kind
        == "Parameter"
    )
    assert hits[0].entry.path == "setup.boundary_conditions.velocity_inlet.thermal.t"
    assert under_hits[0].entry.path == "solution.run_calculation.iterate"
    assert [child.path for child in children] == ["setup.boundary_conditions.velocity_inlet"]
    assert index.lookup("tui.file.read_case") is None


def test_api_index_handles_bad_or_missing_files(tmp_path):
    """Verify that api index handles bad or missing files.

    Parameters
    ----------
    tmp_path : Any
        Path for the tmp.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    bad_shape = tmp_path / "bad_shape.json"
    bad_json = tmp_path / "bad_json.json"
    bad_shape.write_text(json.dumps({"api_objects": "nope"}), encoding="utf-8")
    bad_json.write_text("not json", encoding="utf-8")

    assert ApiIndex(custom_path=str(tmp_path / "missing.json")).available is False
    assert ApiIndex(custom_path=str(bad_shape)).available is False
    assert ApiIndex(custom_path=str(bad_json)).available is False


def test_parse_line_and_path_helpers():
    """Verify that parse line and path helpers.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    entry = _parse_line(
        "<solver_session>.results.scene['scene-1'].graphics_objects (Object)",
        help_map={"scene": "view scene", "graphics_objects": "graphics object collection"},
    )

    assert entry.path == "results.scene.graphics_objects"
    assert entry.tokens[:4] == ["results", "scene", "graphics", "objects"]
    assert "view scene" in entry.doc
    assert _parse_line("<solver_session>.solver.tui.file (Command)") is None
    assert _parse_line(123) is None
    assert _normalise_path('.a["name"].b..') == "a.b"
    assert _tokenise("Velocity-Inlet.T") == ["velocity", "inlet", "t"]


def test_lexical_retriever_and_api_hit_tool_dict(tmp_path):
    """Verify that lexical retriever and api hit tool dict.

    Parameters
    ----------
    tmp_path : Any
        Path for the tmp.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    index = ApiIndex(custom_path=str(_api_objects_file(tmp_path)), help_map={})
    retriever = LexicalApiRetriever(index)

    hits = asyncio.run(retriever.retrieve("iterate", top_k=1, kinds=["Command"]))
    schema_only = ApiHit(
        "mesh.check_mesh", "Command", 0.123456, raw="raw", payload={"source": "schema"}
    )
    plain = ApiHit("setup.models.energy", "Parameter", 1.23456)

    assert hits[0].path == "solution.run_calculation.iterate"
    assert schema_only.to_tool_dict() == {
        "path": "mesh.check_mesh",
        "kind": "Command",
        "score": 0.1235,
        "raw": "raw",
        "payload": {"source": "schema"},
        "note": "Does not exist. Use solver.settings.mesh.check() instead.",
    }
    assert plain.to_tool_dict() == {
        "path": "setup.models.energy",
        "kind": "Parameter",
        "score": 1.2346,
    }


def test_api_index_can_scope_meshing_session(tmp_path):
    """Verify that meshing API paths can be indexed independently."""
    path = _api_objects_file(tmp_path)
    solver_index = ApiIndex(custom_path=str(path), help_map={})
    meshing_index = ApiIndex(custom_path=str(path), sessions=("meshing_session",), help_map={})

    assert solver_index.lookup("workflow.task") is None
    assert meshing_index.lookup("workflow.task").session == "meshing_session"
    assert [hit.entry.path for hit in meshing_index.search("workflow", top_k=3)] == [
        "workflow.task"
    ]


def test_session_scoped_retriever_uses_meshing_index(monkeypatch, tmp_path):
    """Verify that meshing retrievers search ``meshing_session`` entries."""
    path = _api_objects_file(tmp_path)

    def fake_index_for_session(session):
        return ApiIndex(custom_path=str(path), sessions=(session,), help_map={})

    monkeypatch.setattr(catalog_retriever, "get_api_index_for_session", fake_index_for_session)

    hits = asyncio.run(get_api_retriever_for_session("meshing_session").retrieve("workflow"))

    assert [hit.path for hit in hits] == ["workflow.task"]


def test_default_api_index_singleton_can_be_reset(monkeypatch):
    """Verify that default api index singleton can be reset.

    Parameters
    ----------
    monkeypatch : Any
        Pytest fixture used to patch environment variables or dependencies.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    custom = ApiIndex(custom_path="missing.json")
    monkeypatch.setattr(catalog_index, "_default_index", custom)

    assert catalog_index.get_default_api_index() is custom
    catalog_index.reset_default_api_index()
    assert catalog_index._default_index is None


def test_default_retriever_factory_and_override(monkeypatch):
    """Verify that default retriever factory and override.

    Parameters
    ----------
    monkeypatch : Any
        Pytest fixture used to patch environment variables or dependencies.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    catalog_retriever.set_default_api_retriever(None)
    lexical = catalog_retriever._build_default()
    assert isinstance(lexical, LexicalApiRetriever)

    catalog_retriever.set_default_api_retriever(lexical)
    assert catalog_retriever.get_default_api_retriever() is lexical
    catalog_retriever.set_default_api_retriever(None)
