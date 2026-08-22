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

"""Unit tests for the helpers exec'd into the persistent subprocess.

The helpers normally live inside the framework's persistent Python subprocess,
fed in (base64-wrapped) by :mod:`ansys.lumerical.mcp.startup_code`. They are
written as a regular Python module
(:mod:`ansys.lumerical.mcp._subprocess_helpers`) precisely so we can import
them directly here and unit-test them without spawning a subprocess. The
``ansys.lumerical.core`` import inside the helper module is guarded with a
try/except so the import succeeds even on machines without Lumerical.
"""

from __future__ import annotations

import contextlib
import io
import json

import pytest

from ansys.lumerical.mcp import _subprocess_helpers as helpers


def _capture_json(obj) -> object:
    """Call ``_lum_print_json(obj)`` and return the parsed JSON result."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        helpers._lum_print_json(obj)
    return json.loads(buf.getvalue())


def test_lum_print_json_handles_plain_dict():
    assert _capture_json({"a": 1, "b": "two"}) == {"a": 1, "b": "two"}


def test_lum_print_json_handles_top_level_complex():
    assert _capture_json(1 + 2j) == {"real": 1.0, "imag": 2.0}


def test_lum_print_json_handles_complex_ndarray():
    """The previous implementation lost structure for complex arrays.

    ``ndarray.tolist()`` returns nested Python ``complex`` objects, which are
    not JSON-serialisable. The old code returned the list directly and let
    ``json.dumps(default=str)`` stringify each complex (``"(1+2j)"``). The
    fix recurses ``_conv`` into the ``tolist()`` output so complex values
    become ``{"real": ..., "imag": ...}`` and round-trip cleanly.
    """
    np = pytest.importorskip("numpy")
    arr = np.array([1 + 2j, 3 - 4j], dtype=np.complex128)

    assert _capture_json(arr) == [
        {"real": 1.0, "imag": 2.0},
        {"real": 3.0, "imag": -4.0},
    ]


def test_lum_print_json_handles_numpy_scalars():
    """numpy scalar types (np.float64, np.complex128, ...) round-trip as numbers."""
    np = pytest.importorskip("numpy")

    assert _capture_json(np.float64(1.5)) == 1.5
    assert _capture_json(np.int64(7)) == 7
    assert _capture_json(np.complex128(1 + 2j)) == {"real": 1.0, "imag": 2.0}


def test_lum_print_json_truncates_large_arrays():
    np = pytest.importorskip("numpy")
    arr = np.arange(1000)
    parsed = _capture_json(arr)
    if isinstance(parsed, list):
        # max_array_size default (200_000) is huge; 1000 elements should not truncate.
        assert parsed == list(range(1000))
    else:
        pytest.fail(f"expected list payload, got {parsed!r}")


def test_lum_print_json_truncates_when_over_limit():
    np = pytest.importorskip("numpy")
    arr = np.arange(10)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        # Force truncation by setting max_array_size below the array size.
        helpers._lum_print_json(arr, max_array_size=5)
    parsed = json.loads(buf.getvalue())
    assert parsed["__truncated__"] is True
    assert parsed["shape"] == [10]
    assert parsed["preview"] == list(range(10))


def test_startup_code_string_embeds_helpers_source():
    """``LUMERICAL_STARTUP_CODE`` should base64-decode to the helpers source."""
    import base64

    from ansys.lumerical.mcp.startup_code import (
        _INNER_STARTUP_SOURCE,
        LUMERICAL_STARTUP_CODE,
    )

    # The startup code is two lines: an `import base64 as _lum_b64` and an
    # `exec(compile(_lum_b64.b64decode('...')...))`. Pull the b64 payload back
    # out and verify it round-trips to the same source the helpers module ships.
    start = LUMERICAL_STARTUP_CODE.index("b64decode('") + len("b64decode('")
    end = LUMERICAL_STARTUP_CODE.index("')", start)
    decoded = base64.b64decode(LUMERICAL_STARTUP_CODE[start:end]).decode("utf-8")
    assert decoded == _INNER_STARTUP_SOURCE
    assert "_lum_open" in decoded
    assert "_lum_print_json" in decoded
