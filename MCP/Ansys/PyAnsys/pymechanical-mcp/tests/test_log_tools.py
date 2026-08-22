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

"""Unit tests for Mechanical log retrieval utilities."""

import json

from ansys.mechanical.mcp import tools


def test_get_mechanical_logs_no_connection(mock_context_no_mechanical):
    result = tools.get_mechanical_logs(mock_context_no_mechanical)
    assert "No Mechanical connection is available" in result


def test_get_mechanical_logs_invalid_params(mock_context):
    assert "tail_lines must be greater than 0" in tools.get_mechanical_logs(
        mock_context, tail_lines=0
    )
    assert "max_chars must be greater than 0" in tools.get_mechanical_logs(
        mock_context, max_chars=0
    )


def test_get_mechanical_logs_unknown_source(mock_context):
    result = tools.get_mechanical_logs(mock_context, source="unknown")
    data = json.loads(result)
    assert "Unknown source" in data["error"]


def test_get_mechanical_messages_json_and_filter(mock_mechanical):
    mock_mechanical.run_python_script.return_value = json.dumps(
        [
            {"severity": "Info", "source": "A", "summary": "startup"},
            {"severity": "Error", "source": "Solver", "summary": "failed"},
        ]
    )

    result = tools._get_mechanical_messages(
        mock_mechanical, tail_lines=10, contains="error", max_chars=40000
    )
    data = json.loads(result)

    assert data["source"] == "messages"
    assert data["total_messages"] == 1
    assert "failed" in data["logs"]


def test_get_mechanical_messages_raw_fallback(mock_mechanical):
    mock_mechanical.run_python_script.return_value = "line1\nline2\nline3"

    result = tools._get_mechanical_messages(
        mock_mechanical, tail_lines=2, contains=None, max_chars=40000
    )
    data = json.loads(result)

    assert data["returned_lines"] == 2
    assert "line2" in data["logs"]
    assert "line3" in data["logs"]


def test_get_mechanical_solve_log_not_found(tmp_path, mock_mechanical):
    mock_mechanical.project_directory = str(tmp_path)

    result = tools._get_mechanical_solve_log(
        mock_mechanical, tail_lines=5, contains=None, max_chars=10000
    )
    data = json.loads(result)

    assert data["source"] == "solve_log"
    assert "solve.out not found" in data["error"]


def test_get_mechanical_solve_log_rglob_and_truncation(tmp_path, mock_mechanical):
    nested = tmp_path / "nested"
    nested.mkdir(parents=True, exist_ok=True)
    solve_log = nested / "solve.out"
    solve_log.write_text("INFO start\nERROR bad\nINFO end\n", encoding="utf-8")

    mock_mechanical.project_directory = str(tmp_path)

    result = tools._get_mechanical_solve_log(
        mock_mechanical,
        tail_lines=10,
        contains="info",
        max_chars=8,
    )
    data = json.loads(result)

    assert data["source"] == "solve_log"
    assert data["matched_lines"] == 2
    assert data["truncated"] is True


def test_get_mechanical_logs_source_routes(mock_context, monkeypatch):
    monkeypatch.setattr(tools, "_get_mechanical_messages", lambda *args, **kwargs: "MSG")
    monkeypatch.setattr(tools, "_get_mechanical_solve_log", lambda *args, **kwargs: "SOLVE")

    assert tools.get_mechanical_logs(mock_context, source="messages") == "MSG"
    assert tools.get_mechanical_logs(mock_context, source="solve_log") == "SOLVE"
