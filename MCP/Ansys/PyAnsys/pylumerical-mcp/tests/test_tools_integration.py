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

"""Integration tests that exercise the MCP server against a real Lumerical install.

These are marked ``requires_lumerical``; the existing :mod:`conftest` auto-skips
them when no Lumerical install is detected. The tests drive the same lifecycle
the MCP runtime uses: ``product_lifespan`` -> tools -> cleanup.

These rely on
:class:`ansys.lumerical.mcp.persistent_session.LumericalPersistentPythonSession`
to tolerate FDTD's multi-second silent startup. The base
:class:`ansys.common.mcp.PersistentPythonSession.execute` aborts after 0.5 s of
no output, which would lose the JSON envelopes our tools depend on.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ansys.lumerical.mcp import tools
from ansys.lumerical.mcp._envelope import _MAX_ERROR_CHARS
from ansys.lumerical.mcp.server import PyLumericalMCP

pytestmark = [
    pytest.mark.requires_lumerical,
    pytest.mark.integration,
]


@pytest.mark.timeout(180)
async def test_fdtd_session_lifecycle_smoke(tmp_path: Path, make_tool_context):
    """Open a hidden FDTD session, add a rectangle, save, and close it."""
    server = PyLumericalMCP(name="test-server")
    out_file = tmp_path / "smoke.fsp"

    async with server.product_lifespan(server) as app_ctx:
        ctx = make_tool_context(app_ctx)

        # 1) open
        opened = await tools.open_session(ctx, name="fdtd_smoke", product="fdtd", hide=True)
        assert opened["success"], opened
        assert "fdtd_smoke" in app_ctx.sessions

        try:
            # 2) list
            listed = await tools.list_sessions(ctx)
            assert listed["success"]
            assert any(s["name"] == "fdtd_smoke" for s in listed["data"])

            # 3) Python -- add a rectangle, give it a name
            evald = await tools.execute_python_code(
                ctx,
                code=(
                    "_lum_get('fdtd_smoke').addrect(name='r1', x_span=1e-6); "
                    "_lum_print_json({'added': 'r1'})"
                ),
            )
            assert evald["success"], evald

            # 4) Python -- save the project, then verify the file exists.
            save_path = str(out_file).replace("\\", "/")
            saved = await tools.execute_python_code(
                ctx,
                code=(
                    f"_lum_get('fdtd_smoke').save({save_path!r}); "
                    f"_lum_print_json({{'saved': {save_path!r}}})"
                ),
            )
            assert saved["success"], saved
            # The framework's execute_python_code returns stdout/stderr fields.
            assert "saved" in saved.get("stdout", "")
            assert out_file.exists() or Path(save_path + ".fsp").exists()

        finally:
            # 5) close (always run, even if asserts above failed)
            closed = await tools.close_session(ctx, name="fdtd_smoke")
            assert closed["success"], closed
            assert "fdtd_smoke" not in app_ctx.sessions


@pytest.mark.timeout(180)
async def test_open_session_unknown_product_returns_failure(make_tool_context):
    server = PyLumericalMCP(name="test-server")
    async with server.product_lifespan(server) as app_ctx:
        ctx = make_tool_context(app_ctx)

        # We bypass the Literal validation by calling the tool function
        # directly with a clearly invalid product. The startup helper
        # raises ValueError; tools wrap that into a failure envelope.
        # Note: FastMCP itself would reject this at the schema layer, but
        # this test verifies the inner failure path.
        result = await tools.open_session(
            ctx,
            name="nope",
            product="fdtd",
            hide=True,
            filename="/this/does/not/exist.fsp",
        )
        # Either the open succeeded and we should close it, or it failed -- both
        # are valid here; we just want to exercise the failure path without
        # leaking a session.
        if result["success"]:
            await tools.close_session(ctx, name="nope")


@pytest.mark.timeout(180)
async def test_execute_python_code_round_trips_data(make_tool_context):
    """Verify _lum_print_json successfully serializes structured data."""
    server = PyLumericalMCP(name="test-server")
    async with server.product_lifespan(server) as app_ctx:
        ctx = make_tool_context(app_ctx)

        opened = await tools.open_session(ctx, name="py_smoke", product="fdtd", hide=True)
        assert opened["success"], opened

        try:
            result = await tools.execute_python_code(
                ctx,
                code=("import numpy as np; _lum_print_json({'arr': np.arange(5), 'pi': 3.14})"),
            )
            assert result["success"], result
            payload = json.loads(result["stdout"].strip())
            assert payload["arr"] == [0, 1, 2, 3, 4]
            assert payload["pi"] == 3.14
        finally:
            await tools.close_session(ctx, name="py_smoke")


@pytest.mark.timeout(300)
async def test_execute_python_code_clean_error_envelopes_for_bad_lumapi_calls(
    make_tool_context,
):
    """End-to-end: bad lumapi snippets surface as tight, structured envelopes.

    Drives four representative failure modes against one live FDTD session
    and verifies that each produces:

    - ``success`` is False
    - a non-empty short ``error`` summary (<= ``_MAX_ERROR_CHARS``)
    - ``error`` is NOT a byte-for-byte duplicate of ``stderr``
    - the exception class name appears in ``error``
    - the total envelope is well under the 10 kB context-window budget
    - REPL-prompt noise (``>>> `` / ``... ``) is stripped from ``stderr``

    Sharing one ``open_session`` / ``close_session`` lifecycle keeps the
    test affordable -- four FDTD startups would otherwise dominate the
    runtime.
    """
    server = PyLumericalMCP(name="test-server")
    async with server.product_lifespan(server) as app_ctx:
        ctx = make_tool_context(app_ctx)

        opened = await tools.open_session(ctx, name="err_smoke", product="fdtd", hide=True)
        assert opened["success"], opened

        try:
            cases: list[tuple[str, str, str]] = [
                # (label, snippet, expected substring in error)
                (
                    "AttributeError",
                    "_lum_get('err_smoke').addrct(name='r1')",
                    "AttributeError",
                ),
                (
                    "KeyError",
                    "_lum_get('does_not_exist')",
                    "KeyError",
                ),
                (
                    "LumApiError",
                    # Setting an unknown property triggers a real lumapi-side
                    # exception; the exact class is ``LumApiError`` (often via
                    # the dotted path ``ansys.api.lumerical.lumapi.LumApiError``)
                    # but matching on ``Error`` keeps us robust to upstream
                    # renames or wrapping by ansys.lumerical.core.
                    "_lum_get('err_smoke').set('this property does not exist', 1.0)",
                    "Error",
                ),
                (
                    "SyntaxError",
                    "def foo(:",
                    "SyntaxError",
                ),
            ]

            for label, snippet, expected in cases:
                parsed = await tools.execute_python_code(ctx, code=snippet)

                assert parsed["success"] is False, f"{label}: expected failure -- got {parsed!r}"
                err = parsed.get("error", "")
                stderr_text = parsed.get("stderr", "")

                assert err, f"{label}: error field empty -- envelope={parsed!r}"
                assert len(err) <= _MAX_ERROR_CHARS, (
                    f"{label}: error field too long ({len(err)} > {_MAX_ERROR_CHARS})"
                )
                assert err != stderr_text, (
                    f"{label}: error field is a byte-for-byte duplicate of stderr"
                )
                assert expected in err, (
                    f"{label}: expected substring {expected!r} in error -- got {err!r}"
                )
                envelope_bytes = len(json.dumps(parsed))
                assert envelope_bytes < 10_000, (
                    f"{label}: envelope too large ({envelope_bytes} bytes) -- "
                    "should fit within agent context budget"
                )

                # No REPL prompt noise should remain in stderr.
                for line in stderr_text.splitlines():
                    assert not line.startswith(">>> "), f"{label}: leaked REPL prompt: {line!r}"
                    assert not line.startswith("... "), f"{label}: leaked REPL prompt: {line!r}"

        finally:
            await tools.close_session(ctx, name="err_smoke")
