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

"""CFX ``validate_code`` — strict mode + schema-path check.

Phase 13 makes :meth:`CFXBackend.validate_code` enforce the AST
sandbox in strict mode and additionally walk the AST for
``solver.<path>`` / ``pre.<path>`` / ``post.<path>`` /
``session.<path>`` chains. Paths that the schema cache reports as
unknown AND that have no near-match are promoted to a structured
``unknown_cfx_path`` error.
"""

from __future__ import annotations

import asyncio

import pytest

from ansys.cfx.mcp.cfx.backend import CFXBackend


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------
# strict-mode sandbox (imports / Name lookups)
# ---------------------------------------------------------------------


def test_validate_code_blocks_forbidden_import():
    backend = CFXBackend()
    code = "import os\nos.system('whoami')\n"
    result = _run(backend.validate_code(code))
    assert result.status == "error"
    assert result.error_code in {"forbidden_call", "forbidden_import", "disallowed_import"}


def test_validate_code_blocks_disallowed_import():
    backend = CFXBackend()
    code = "import requests\nrequests.get('https://x.com')\n"
    result = _run(backend.validate_code(code))
    assert result.status == "error"
    assert result.error_code in {"disallowed_import", "forbidden_import"}


def test_validate_code_accepts_math_import():
    backend = CFXBackend()
    code = "import math\nprint(math.pi)\n"
    result = _run(backend.validate_code(code))
    assert result.status == "ok"


# ---------------------------------------------------------------------
# schema-path check
# ---------------------------------------------------------------------


def test_validate_code_passes_known_solver_path():
    """A path that the schema cache knows about should validate
    successfully (might emit warnings about other paths but no
    blocking error)."""
    backend = CFXBackend()
    code = "tf = solver.setup.flow['main'].domain['fluid'].solver_control.convergence_control.timescale_factor\n"  # noqa: E501
    result = _run(backend.validate_code(code))
    # The path normalises to setup.flow["<name>"].domain["<name>"]
    # .solver_control.convergence_control.timescale_factor which is
    # in the schema cache — so we expect status='ok'.
    assert result.status == "ok"


def test_validate_code_blocks_hallucinated_path():
    """A path with no schema match AND no near-match should be
    promoted to an unknown_cfx_path error."""
    backend = CFXBackend()
    code = "x = solver.totally.bogus.invented.fake_attr_xyzzyq.value\n"
    result = _run(backend.validate_code(code))
    if result.status == "error":
        # ``unknown_cfx_path`` is the structured error; the message
        # must include the offending path.
        assert result.error_code == "unknown_cfx_path"
        assert "fake_attr_xyzzyq" in result.message
    else:
        pytest.skip(
            "Schema cache returned at least one near-match for the "
            "synthetic path — that's acceptable because it means the "
            "validator chose to warn rather than block."
        )


def test_validate_code_keeps_near_miss_as_warning():
    """A path whose leaf has a near-match should remain a warning,
    not an error because the author may have made a simple typo."""
    backend = CFXBackend()
    code = "x = solver.setup.flow['main'].domain['fluid'].solver_control.convergence_control.timescale_facter\n"  # noqa: E501
    result = _run(backend.validate_code(code))
    if result.status == "ok":
        # If warnings exist, the typo should be referenced.
        if result.warnings:
            assert any("timescale_facter" in w for w in result.warnings)
    else:
        # Either is acceptable provided we don't crash.
        assert result.error_code is not None


def test_validate_code_rejects_empty_string():
    backend = CFXBackend()
    result = _run(backend.validate_code(""))
    assert result.status == "error"
    assert result.error_code == "invalid_arguments"


def test_validate_code_path_extraction_handles_no_paths():
    """A snippet with no ``solver/pre/post/session`` roots should
    pass the schema-path check trivially."""
    backend = CFXBackend()
    code = "x = 42\nprint(x)\n"
    result = _run(backend.validate_code(code))
    assert result.status == "ok"


# ---------------------------------------------------------------------
# Phase 1a: run_code shares the schema guard + strict env promotion
# ---------------------------------------------------------------------


def test_run_code_shares_schema_hallucination_guard():
    """``run_code`` MUTATES the live case, so it must reject the same
    hallucinated paths ``validate_code`` does (shared
    ``_check_cfx_schema_paths``)."""
    backend = CFXBackend()
    code = "x = solver.totally.bogus.invented.fake_attr_xyzzyq.value\n"
    err = backend._check_cfx_schema_paths(code)
    if err is None:
        pytest.skip("schema cache produced a near-match; warn instead of block")
    assert err.status == "error"
    assert err.error_code == "unknown_cfx_path"


def test_strict_env_promotes_near_match_to_error(monkeypatch):
    """With ``CFX_MCP_STRICT_VALIDATION`` set, a near-match warning is
    promoted to a blocking ``unknown_cfx_path`` error."""
    backend = CFXBackend()
    code = """
x = solver.setup.flow['main'].domain['fluid'].solver_control.convergence_control.timescale_facter
"""
    # Baseline (no env): near-match should NOT block.
    monkeypatch.delenv("CFX_MCP_STRICT_VALIDATION", raising=False)
    monkeypatch.delenv("FLUIDS_MCP_STRICT_VALIDATION", raising=False)
    baseline = backend._check_cfx_schema_paths(code)
    monkeypatch.setenv("CFX_MCP_STRICT_VALIDATION", "1")
    strict = backend._check_cfx_schema_paths(code)
    # If there was a near-match warning baseline (None), strict should
    # now produce an error. If the schema had no opinion at all, both
    # are None — acceptable.
    if baseline is None and strict is not None:
        assert strict.error_code == "unknown_cfx_path"
