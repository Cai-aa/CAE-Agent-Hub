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

"""Tests for snippet builders and result parsing in ``session_helpers``."""

from __future__ import annotations

import json

from ansys.lumerical.mcp.session_helpers import (
    build_close_session_snippet,
    build_eval_snippet,
    build_open_session_snippet,
    envelope_failure,
    envelope_success,
    extract_json_payload,
    render_envelope_from_execute,
)

# ---------------------------------------------------------------------------
# Snippet builders -- these are pure functions, so we just spot-check that
# they emit valid Python that uses repr() to embed user-supplied strings.
# ---------------------------------------------------------------------------


def test_build_open_session_snippet_basic():
    snippet = build_open_session_snippet("s1", "fdtd", None, True)
    assert "_lum_open(" in snippet
    assert "'s1'" in snippet
    assert "'fdtd'" in snippet
    assert "filename=None" in snippet
    assert "hide=True" in snippet
    assert "_lum_print_json" in snippet
    compile(snippet, "<snippet>", "exec")


def test_build_open_session_snippet_with_filename():
    snippet = build_open_session_snippet("s1", "fdtd", "/tmp/foo.fsp", False)
    assert "'/tmp/foo.fsp'" in snippet
    assert "hide=False" in snippet
    compile(snippet, "<snippet>", "exec")


def test_build_open_session_snippet_escapes_awkward_names():
    snippet = build_open_session_snippet("name with 'quotes'", "mode", None, True)
    compile(snippet, "<snippet>", "exec")
    assert "'name with \\'quotes\\''" in snippet or "\"name with 'quotes'\"" in snippet


def test_build_close_session_snippet():
    snippet = build_close_session_snippet("s1")
    assert snippet == "_lum_print_json(_lum_close('s1'))"
    compile(snippet, "<snippet>", "exec")


def test_build_eval_snippet_simple():
    snippet = build_eval_snippet("s1", "addrect;")
    assert "_lum_get('s1').eval('addrect;')" in snippet
    assert "evaluated" in snippet
    compile(snippet, "<snippet>", "exec")


def test_build_eval_snippet_multiline_with_quotes():
    script = 'addrect;\nset("name","r1");\nset("x",0);'
    snippet = build_eval_snippet("s1", script)
    compile(snippet, "<snippet>", "exec")
    # The original script must be embedded as a Python string literal that
    # round-trips: i.e. evaluating the literal must yield the original.
    assert repr(script) in snippet


# ---------------------------------------------------------------------------
# extract_json_payload
# ---------------------------------------------------------------------------


def test_extract_json_payload_single_line():
    out = '{"name": "s1", "product": "fdtd"}'
    payload = extract_json_payload(out)
    assert payload == {"name": "s1", "product": "fdtd"}


def test_extract_json_payload_with_preamble():
    out = '[pylumerical-mcp] startup helpers loaded; import_error=None\n{"closed": "s1"}'
    payload = extract_json_payload(out)
    assert payload == {"closed": "s1"}


def test_extract_json_payload_pretty_printed():
    out = 'some preamble text\n{\n  "session": "s1",\n  "evaluated": true\n}'
    payload = extract_json_payload(out)
    assert payload == {"session": "s1", "evaluated": True}


def test_extract_json_payload_missing():
    assert extract_json_payload("") is None
    assert extract_json_payload("just text, no json") is None


def test_extract_json_payload_picks_last_valid_line():
    out = 'first\n{"old": 1}\n{"new": 2}'
    assert extract_json_payload(out) == {"new": 2}


# ---------------------------------------------------------------------------
# Envelopes
# ---------------------------------------------------------------------------


def test_envelope_success_with_dict_payload():
    parsed = envelope_success({"a": 1})
    assert isinstance(parsed, dict)
    assert parsed == {"success": True, "data": {"a": 1}}


def test_envelope_success_with_list_payload():
    parsed = envelope_success([1, 2, 3])
    assert parsed["success"] is True
    assert parsed["data"] == [1, 2, 3]


def test_envelope_success_with_extras():
    parsed = envelope_success({"a": 1}, message="ok")
    assert parsed["message"] == "ok"


def test_envelope_success_coerces_non_json_safe_payload():
    """A non-JSON-safe leaf must be coerced to ``str`` (mirror of ``default=str``).

    Before the structured-content refactor the helper called ``json.dumps``
    with ``default=str`` to handle e.g. ``Path`` / ``datetime``. Now the
    helper returns a live dict, so the equivalent coercion happens in
    :func:`_jsonable` and is verified here so FastMCP never sees a value
    its own serializer might refuse.
    """
    from pathlib import Path

    parsed = envelope_success({"where": Path("/tmp/foo.fsp")})
    assert isinstance(parsed["data"]["where"], str)
    assert parsed["data"]["where"].endswith("foo.fsp")
    # And the whole envelope still serializes cleanly.
    assert isinstance(json.dumps(parsed), str)


def test_envelope_failure_basic():
    parsed = envelope_failure("boom")
    assert isinstance(parsed, dict)
    assert parsed["success"] is False
    assert parsed["error"] == "boom"
    assert "stdout" not in parsed
    assert "stderr" not in parsed


def test_envelope_failure_with_streams():
    parsed = envelope_failure("boom", stdout="hi", stderr="ouch")
    assert parsed["stdout"] == "hi"
    assert parsed["stderr"] == "ouch"


def test_render_envelope_from_execute_success():
    result = {
        "success": True,
        "stdout": '{"name": "s1"}',
        "stderr": "",
    }
    parsed = render_envelope_from_execute(result)
    assert parsed["success"] is True
    assert parsed["data"] == {"name": "s1"}


def test_render_envelope_from_execute_failure():
    result = {
        "success": False,
        "stdout": "partial",
        "stderr": "Traceback...",
        "error": "ValueError: bad",
    }
    parsed = render_envelope_from_execute(result)
    assert parsed["success"] is False
    assert parsed["error"] == "ValueError: bad"
    assert parsed["stderr"] == "Traceback..."
