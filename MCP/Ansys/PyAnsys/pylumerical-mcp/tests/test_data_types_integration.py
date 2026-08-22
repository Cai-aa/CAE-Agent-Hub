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

"""Integration tests for the lumapi Lumerical -> Python conversion contract.

For every entry in the PyLumerical `passing_data` table
(https://lumerical.docs.pyansys.com/version/stable/user_guide/passing_data.html)
plus the dataset/struct flavours from the Lumerical knowledge base, a value is
created in the Lumerical workspace via the lumapi ``.eval()`` bridge and then
pulled back into Python through the MCP tool chain
(``execute_python_code`` -> ``_lum_print_json`` -> envelope) and asserted
against the documented Python shape/keys.

The pure ``_lum_print_json`` recursion logic is unit-tested in
``tests/test_startup_helpers.py`` against synthetic numpy/complex/dict
inputs; this file's marginal value is exercising the helper against real
``lumapi`` outputs and the full MCP envelope path.

A single hidden FDTD session is shared by every test in the module via a
module-scoped ``fdtd_session`` fixture; the autouse ``clear_workspace``
fixture issues ``switchtolayout; deleteall; clear;`` between tests to wipe
both the simulation tree and the script-workspace variable namespace.

Out of scope (intentionally):

- Python -> Lumerical (``putv``) round-trip.
- Unstructured datasets (require a DEVICE/CHARGE session).
- Tensor attributes on rectilinear datasets (trailing dim 9): the public
  ``addattribute`` API only documents 1-arg scalar and 3-arg vector forms;
  tensor attributes are produced by solvers, not constructed by users.
- Running an actual FDTD simulation; datasets are constructed with
  ``matrixdataset`` / ``rectilineardataset`` script commands instead so each
  test stays well under a few seconds.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
import pytest_asyncio

from ansys.lumerical.mcp import tools
from ansys.lumerical.mcp.server import PyLumericalMCP

pytestmark = [
    pytest.mark.requires_lumerical,
    pytest.mark.integration,
    # Share a single event loop across every test in this module so the
    # module-scoped subprocess + FDTD handle survives between tests.
    pytest.mark.asyncio(loop_scope="module"),
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(loop_scope="module", scope="module")
async def fdtd_session(make_tool_context):
    """Single hidden FDTD session shared by every test in this module."""
    server = PyLumericalMCP(name="test-server")
    async with server.product_lifespan(server) as app_ctx:
        ctx = make_tool_context(app_ctx)
        opened = await tools.open_session(ctx, name="fdtd_data", product="fdtd", hide=True)
        assert opened["success"], opened
        try:
            yield ctx, "fdtd_data"
        finally:
            try:
                await tools.close_session(ctx, name="fdtd_data")
            except Exception:
                # Lifespan teardown will _lum_close_all() in any case.
                pass


@pytest_asyncio.fixture(loop_scope="module", autouse=True)
async def clear_workspace(fdtd_session):
    """Reset the Lumerical workspace before each test.

    ``switchtolayout`` returns to layout mode (datasets / sim runs put the
    app in analysis mode where ``deleteall`` is a no-op); ``deleteall``
    removes any geometry / monitors created by an earlier test;
    ``clear`` wipes script workspace variables.
    """
    ctx, name = fdtd_session
    env = await tools.execute_python_code(
        ctx,
        code=(
            f"_lum_get({name!r}).eval('switchtolayout; deleteall; clear;'); "
            "_lum_print_json({'cleared': True})"
        ),
    )
    assert env["success"], env
    yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _roundtrip(ctx, name: str, *, lsf: str, var: str) -> Any:
    """Create ``var`` in LSF via ``.eval()``, then retrieve via ``_lum_print_json``.

    Returns the parsed JSON payload (i.e. the value seen by the LLM).
    """
    env = await tools.execute_python_code(
        ctx,
        code=(f"_lum_get({name!r}).eval({lsf!r}); _lum_print_json({{'evaluated': True}})"),
    )
    assert env["success"], env

    env = await tools.execute_python_code(
        ctx,
        code=f"_lum_print_json(_lum_get({name!r}).getv({var!r}))",
    )
    assert env["success"], env
    return json.loads(env["stdout"].strip())


def _find_complex_dict(obj: Any) -> dict[str, float] | None:
    """Descend through nested lists to find a single ``{real, imag}`` dict.

    Lumerical complex scalars come back as 1-element ndarrays whose nesting
    depth is documented as "1x1" but in practice can be ``(1,)`` or
    ``(1,1)``. Tests use this to decouple from the specific shape.
    """
    if isinstance(obj, dict) and set(obj) == {"real", "imag"}:
        return obj
    if isinstance(obj, list):
        for item in obj:
            found = _find_complex_dict(item)
            if found is not None:
                return found
    return None


def _nested_list_shape(obj: Any) -> list[int]:
    """Return the leading dimensions of a (rectangular) nested list."""
    dims: list[int] = []
    cur = obj
    while isinstance(cur, list) and cur:
        dims.append(len(cur))
        cur = cur[0]
    return dims


# ---------------------------------------------------------------------------
# Scalar types
# ---------------------------------------------------------------------------


async def test_string(fdtd_session):
    """Lumerical String -> Python ``str``."""
    ctx, name = fdtd_session
    payload = await _roundtrip(ctx, name, lsf='s = "hello world";', var="s")
    assert payload == "hello world"


async def test_real_float(fdtd_session):
    """Lumerical Real (float literal) -> Python ``float``."""
    ctx, name = fdtd_session
    payload = await _roundtrip(ctx, name, lsf="x = 1.25;", var="x")
    assert payload == 1.25


async def test_real_from_integer_literal(fdtd_session):
    """Integer literals get coerced to float in Lumerical (no int type).

    Per https://lumerical.docs.pyansys.com/version/stable/user_guide/passing_data.html#real-number
    """
    ctx, name = fdtd_session
    payload = await _roundtrip(ctx, name, lsf="n = 42;", var="n")
    # JSON serialises 42.0 as `42` (no fractional part), so a numeric
    # equality is sufficient here without pinning float vs int.
    assert payload == 42


async def test_complex_scalar(fdtd_session):
    """Lumerical Complex -> 1-element complex ndarray -> ``{real, imag}`` dict.

    The variable is named ``cz`` (not ``c``) because ``c`` is the reserved
    speed-of-light constant in Lumerical script - assigning to it silently
    fails and ``getv("c")`` then raises ``Failed to get variable``.
    """
    ctx, name = fdtd_session
    payload = await _roundtrip(ctx, name, lsf="cz = 1+2i;", var="cz")
    found = _find_complex_dict(payload)
    assert found is not None, payload
    assert found == {"real": 1.0, "imag": 2.0}


# ---------------------------------------------------------------------------
# Matrix types
# ---------------------------------------------------------------------------


async def test_matrix_real(fdtd_session):
    """Real Lumerical matrix -> nested list of floats."""
    ctx, name = fdtd_session
    payload = await _roundtrip(ctx, name, lsf="M = [1,2,3;4,5,6];", var="M")
    assert payload == [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]


async def test_matrix_complex(fdtd_session):
    """Complex matrix -> nested list with ``{real, imag}`` entries.

    Regression net for the complex-ndarray fix in ``_lum_print_json`` (the
    pre-fix code stringified each complex via ``json.dumps(default=str)``).
    """
    ctx, name = fdtd_session
    payload = await _roundtrip(ctx, name, lsf="M = [1+1i, 2-2i];", var="M")

    flat: list[Any] = []

    def _flatten(x: Any) -> None:
        if isinstance(x, list):
            for item in x:
                _flatten(item)
        else:
            flat.append(x)

    _flatten(payload)
    assert {"real": 1.0, "imag": 1.0} in flat
    assert {"real": 2.0, "imag": -2.0} in flat


# ---------------------------------------------------------------------------
# Container types
# ---------------------------------------------------------------------------


async def test_cell_array(fdtd_session):
    """Cell array -> Python ``list`` of mixed types.

    Mirrors the example from the PyLumerical docs:
    https://lumerical.docs.pyansys.com/version/stable/user_guide/passing_data.html#cell-array
    """
    ctx, name = fdtd_session
    lsf = (
        "mycell = cell(3); "
        'mycell{1} = "Hello World"; '
        "mycell{2} = matrix(2,2); "
        'mycell{3} = {"name":"Lumerical", "value":cell(3)};'
    )
    payload = await _roundtrip(ctx, name, lsf=lsf, var="mycell")

    assert isinstance(payload, list)
    assert len(payload) == 3
    assert payload[0] == "Hello World"
    # Element 2: 2x2 matrix as nested list of zeros.
    assert isinstance(payload[1], list)
    assert _nested_list_shape(payload[1]) == [2, 2]
    # Element 3: nested struct with `name` and `value` (a 3-cell list).
    assert isinstance(payload[2], dict)
    assert payload[2]["name"] == "Lumerical"
    assert isinstance(payload[2]["value"], list)
    assert len(payload[2]["value"]) == 3


async def test_struct(fdtd_session):
    """Lumerical Struct -> Python ``dict`` (ordering not preserved)."""
    ctx, name = fdtd_session
    lsf = 's = {"name":"foo","real":1.5,"complex":1+1i,"mat":matrix(2,2)};'
    payload = await _roundtrip(ctx, name, lsf=lsf, var="s")

    assert isinstance(payload, dict)
    assert set(payload.keys()) == {"name", "real", "complex", "mat"}
    assert payload["name"] == "foo"
    assert payload["real"] == 1.5
    found = _find_complex_dict(payload["complex"])
    assert found == {"real": 1.0, "imag": 1.0}
    assert _nested_list_shape(payload["mat"]) == [2, 2]


# ---------------------------------------------------------------------------
# Datasets
# ---------------------------------------------------------------------------


async def test_matrix_dataset(fdtd_session):
    """``matrixdataset`` -> dict with parameters, attributes, and metadata."""
    ctx, name = fdtd_session
    lsf = (
        "radius = [0,1,2]; height = [1.0,2.0]; "
        'R = matrixdataset("R"); '
        'R.addparameter("radius", radius); '
        'R.addparameter("height", height); '
        'R.addattribute("R", matrix(3,2));'
    )
    payload = await _roundtrip(ctx, name, lsf=lsf, var="R")

    assert isinstance(payload, dict)
    # The `Lumerical_dataset` metadata key is what distinguishes a dataset
    # dict from a generic struct dict on the Python side.
    assert "Lumerical_dataset" in payload
    keys = set(payload.keys())
    for required in ("radius", "height", "R"):
        assert required in keys, f"missing dataset key {required!r}: {keys}"
    # The R attribute is a Np1 x Np2 = 3 x 2 matrix.
    assert _nested_list_shape(payload["R"])[:2] == [3, 2]


async def test_rectilinear_dataset_full(fdtd_session):
    """``rectilineardataset`` with scalar + vector attributes and an interdependent parameter.

    Per https://optics.ansys.com/hc/en-us/articles/360034409554-Introduction-to-Lumerical-datasets
    a rectilinear dataset's attribute trailing dimensions are:

    - scalar: ``[Nx, Ny, Nz, Np1, ..., Npn]``
    - vector: ``[Nx, Ny, Nz, Np1, ..., Npn, 3]``
    - tensor: ``[Nx, Ny, Nz, Np1, ..., Npn, 9]``

    The user-facing
    `addattribute <https://optics.ansys.com/hc/en-us/articles/360034929873-addattribute-Script-command>`_
    only documents 1-arg (scalar) and 3-arg (vector) forms for rectilinear
    datasets; tensor attributes (trailing dim 9) arise from solver outputs
    (e.g. Multiphysics permittivity) and cannot be constructed via
    ``addattribute`` alone, so they are out of scope here.

    The interdependent ``addparameter("lambda", c/f, "f", f)`` form (from the
    ``matrixdataset`` / ``rectilineardataset`` docs) lets a single parameter
    appear under two names (frequency and wavelength).
    """
    ctx, name = fdtd_session
    lsf = (
        "x = [0,1]; y = [0,1,2]; z = [0]; f = [1e14,2e14]; "
        'D = rectilineardataset("D", x, y, z); '
        'D.addparameter("lambda", c/f, "f", f); '
        'D.addattribute("Pabs", matrix(2,3,1,2)); '
        'D.addattribute("E", matrix(2,3,1,2), matrix(2,3,1,2), matrix(2,3,1,2));'
    )
    payload = await _roundtrip(ctx, name, lsf=lsf, var="D")

    assert isinstance(payload, dict)
    assert "Lumerical_dataset" in payload
    keys = set(payload.keys())
    for required in ("x", "y", "z", "f", "lambda", "Pabs", "E"):
        assert required in keys, f"missing dataset key {required!r}: {keys}"

    # Pabs: scalar attribute -> [Nx, Ny, Nz, Nf] = [2, 3, 1, 2].
    assert _nested_list_shape(payload["Pabs"]) == [2, 3, 1, 2]
    # E: vector attribute -> trailing dim 3 -> [2, 3, 1, 2, 3].
    assert _nested_list_shape(payload["E"]) == [2, 3, 1, 2, 3]
    # Interdependent parameter: `lambda` mirrors `f` length (2 entries).
    assert _nested_list_shape(payload["lambda"])[0] == 2
    assert _nested_list_shape(payload["f"])[0] == 2


# ---------------------------------------------------------------------------
# Truncation guard in _lum_print_json
# ---------------------------------------------------------------------------


async def test_large_array_truncation(fdtd_session):
    """Force the ``max_array_size`` truncation branch in ``_lum_print_json``.

    A 1000x1000 zero matrix (1e6 elements) is well above any reasonable
    inline serialisation budget, so we lower ``max_array_size`` to 10 to
    drive the ``{__truncated__, shape, dtype, preview}`` envelope.
    """
    ctx, name = fdtd_session
    env = await tools.execute_python_code(
        ctx,
        code=(
            f"_lum_get({name!r}).eval('big = matrix(1000,1000);'); "
            "_lum_print_json({'created': 'big'})"
        ),
    )
    assert env["success"], env

    # This test bypasses the shared `_roundtrip` helper because it needs to
    # thread a `max_array_size=10` kwarg into `_lum_print_json`.
    env = await tools.execute_python_code(
        ctx,
        code=(f"_lum_print_json(_lum_get({name!r}).getv('big'), max_array_size=10)"),
    )
    assert env["success"], env

    payload = json.loads(env["stdout"].strip())
    assert payload["__truncated__"] is True
    assert payload["shape"] == [1000, 1000]
    assert "dtype" in payload
    assert isinstance(payload["preview"], list)
    # _lum_print_json caps the preview at the first 50 elements of `flatten()`.
    assert 0 < len(payload["preview"]) <= 50
