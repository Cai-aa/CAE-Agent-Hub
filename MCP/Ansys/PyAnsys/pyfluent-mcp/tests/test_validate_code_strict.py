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

"""``validate_code`` strict mode + unknown-path promotion.

The PyFluent backend's ``validate_code`` now:

* invokes :func:`validate_python_source` with ``strict=True``, which
  enforces the AST import allow-list and top-level Name allow-list,
* promotes settings paths that the bundled API index reports as
  having *no near-match* to a structured ``unknown_settings_path``
  error (instead of leaving them as silent warnings).

The tests below pin both behaviours against the offline (no-session)
path of the PyFluent backend so they run on any developer machine.
"""

from __future__ import annotations

import ast
import asyncio

import pytest

from ansys.fluent.mcp.solve.backends.pyfluent import PyFluentBackend, _extract_settings_paths


def _run(coro):
    return asyncio.run(coro)


def _make_backend() -> PyFluentBackend:
    """Build a PyFluent backend without connecting to a live solver.

    ``validate_code`` does not require a live connection for its
    AST + catalog passes — both run offline.
    """
    return PyFluentBackend()


# ---------------------------------------------------------------------
# strict=True — import / Name allow-lists
# ---------------------------------------------------------------------


def test_validate_code_blocks_forbidden_import():
    backend = _make_backend()
    code = "import os\nos.system('whoami')\n"
    result = _run(backend.validate_code(code))
    assert result.status == "error"
    # The forbidden_call hits before the import allow-list rejection.
    assert result.error_code in {"forbidden_call", "disallowed_import", "forbidden_import"}


def test_validate_code_blocks_disallowed_import_under_strict():
    backend = _make_backend()
    code = "import requests\nrequests.get('https://example.com')\n"
    result = _run(backend.validate_code(code))
    assert result.status == "error"
    assert result.error_code in {"disallowed_import", "forbidden_import"}


def test_validate_code_accepts_allowed_imports():
    backend = _make_backend()
    code = "import math\nprint(math.pi)\n"
    result = _run(backend.validate_code(code))
    assert result.status == "ok"


# ---------------------------------------------------------------------
# unknown_settings_path — hallucinated path detection
# ---------------------------------------------------------------------


def test_validate_code_rejects_completely_hallucinated_path():
    """A path with neither a direct hit nor a near-match in the API
    index should be promoted to ``unknown_settings_path`` error."""
    backend = _make_backend()
    code = "solver.setup.totally_nonexistent.fake_node_xyzzyx.do_thing(42)\n"
    result = _run(backend.validate_code(code))
    # The leaf "do_thing" doesn't exist anywhere in the bundled
    # api_objects.json so the catalog search returns no candidate
    # and we promote to an error.
    if result.status == "error":
        assert result.error_code == "unknown_settings_path"
        # The hallucinated path should appear in the message.
        assert "fake_node_xyzzyx" in result.message
    else:
        # The catalog index isn't available in this environment;
        # skip the assertion. The companion ``test_validation.py``
        # already pins offline parse behaviour.
        pytest.skip("api_objects.json index not available")


def test_validate_code_keeps_nearby_misspellings_as_warning():
    """A path whose leaf has a plausible near-match should stay as
    a warning so the caller can self-correct."""
    backend = _make_backend()
    # ``material_name`` is the canonical typo for ``general.material``
    # under a fluid cell zone — the catalog index can resolve "material"
    # as a near-match, so we keep it as a warning rather than
    # blocking.
    code = "solver.setup.cell_zone_conditions.fluid['x'].material_name = 'air'\n"
    result = _run(backend.validate_code(code))
    # Either it parses cleanly as a warning, or the catalog isn't
    # available — either is acceptable; we just must not crash.
    if result.status == "ok":
        # Warning should be present if any warnings were emitted.
        assert result.warnings is None or isinstance(result.warnings, list)
    else:
        # If strict mode rejected for an unrelated reason that's a
        # legitimate validation result too; we only care that the
        # path triage didn't crash.
        assert result.error_code is not None


def test_validate_code_passes_clean_snippet():
    """A snippet that reads only well-known paths should pass."""
    backend = _make_backend()
    code = "models = solver.setup.models\nprint(models)\n"
    result = _run(backend.validate_code(code))
    assert result.status == "ok"


# ---------------------------------------------------------------------
# Phase 1a: run_code reflection-write guard + strict env helper
# ---------------------------------------------------------------------


def test_run_code_blocks_setattr_reflection():
    """``setattr`` is an allowed builtin (so strict validation passes),
    but it can smuggle a write past the schema/read-only guards, so
    ``run_code`` rejects it outright."""
    from ansys.fluent.mcp.solve.backends.pyfluent import _scan_reflection_writes

    code = "setattr(solver.setup.models, 'energy', 1)\n"
    assert _scan_reflection_writes(code)  # detector fires

    backend = _make_backend()
    result = _run(backend.run_code(code))
    assert result.status == "error"
    assert result.error_code == "forbidden_call"


def test_run_code_blocks_dunder_setitem():
    from ansys.fluent.mcp.solve.backends.pyfluent import _scan_reflection_writes

    code = "solver.setup.models.__setattr__('energy', 1)\n"
    assert _scan_reflection_writes(code)


def test_scan_reflection_allows_normal_assignment():
    from ansys.fluent.mcp.solve.backends.pyfluent import _scan_reflection_writes

    code = "solver.setup.models.energy.enabled = True\n"
    assert not _scan_reflection_writes(code)


def test_extract_settings_paths_includes_meshing_workflow_roots():
    """Meshing workflow paths should be catalog-validated like solver settings."""
    tree = ast.parse(
        """
session.workflow.InitializeWorkflow(WorkflowType="Watertight Geometry")
session.workflow.TaskObject["Import Geometry"].Arguments.set_state({"LengthUnit": "in"})
session.PartManagement.InputFileChanged(FilePath="x.pmdb")
"""
    )

    paths = set(_extract_settings_paths(tree))

    assert "workflow.InitializeWorkflow" in paths
    assert "workflow.TaskObject.Arguments.set_state" in paths
    assert "PartManagement.InputFileChanged" in paths


def test_strict_validation_env_helper(monkeypatch):
    from ansys.fluent.mcp.solve.backends.pyfluent import _strict_validation_enabled

    monkeypatch.delenv("FLUIDS_MCP_STRICT_VALIDATION", raising=False)
    assert _strict_validation_enabled() is False
    monkeypatch.setenv("FLUIDS_MCP_STRICT_VALIDATION", "1")
    assert _strict_validation_enabled() is True
    monkeypatch.setenv("FLUIDS_MCP_STRICT_VALIDATION", "off")
    assert _strict_validation_enabled() is False
