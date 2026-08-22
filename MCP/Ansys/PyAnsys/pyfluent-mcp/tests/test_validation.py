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

import pytest

from ansys.fluent.mcp.common.validation import sanitize_python_code, validate_python_source


def test_validate_python_source_accepts_valid_code_and_caches_result():
    """Verify that validate python source accepts valid code and caches result.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    first = validate_python_source("x = 1\ny = x + 2")
    second = validate_python_source("x = 1\ny = x + 2")

    assert first.status == "ok"
    assert first.message == "parse_ok"
    assert first.return_value["node_count"] > 0
    assert second is first


@pytest.mark.parametrize(
    ("code", "error_code", "message"),
    [
        ("", "invalid_arguments", "non-empty"),
        ("for", "syntax_error", "SyntaxError"),
        ("eval('1')", "forbidden_call", "eval"),
        ("os.system('calc')", "forbidden_call", "os.system"),
        ("solver.tui.file.read_case()", "tui_not_allowed", "TUI escape hatch"),
        ("getattr(obj, '__subclasses__')", "forbidden_call", "__subclasses__"),
    ],
)
def test_validate_python_source_rejects_unsafe_or_invalid_code(code, error_code, message):
    """Verify that validate python source rejects unsafe or invalid code.

    Parameters
    ----------
    code : Any
        Python code or command text to execute or validate.
    error_code : Any
        Error code to supply to the function.
    message : Any
        Message text to format, log, or return.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    result = validate_python_source(code)

    assert result.status == "error"
    assert result.error_code == error_code
    assert message in result.message


def test_validate_python_source_allows_safe_dunder_reads():
    """Verify that validate python source allows safe dunder reads.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    result = validate_python_source("name = solver.__class__\nversion = solver.__version__")

    assert result.status == "ok"


def test_strict_validation_rejects_forbidden_imports_and_names():
    """Verify that strict validation rejects forbidden imports and names.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    import_result = validate_python_source("import os", strict=True)
    name_result = validate_python_source("answer = unknown_name + 1", strict=True)

    assert import_result.error_code == "forbidden_import"
    assert "os" in import_result.message
    assert name_result.error_code == "forbidden_name"
    assert "unknown_name" in name_result.message


def test_strict_validation_allows_bound_names_imports_and_extra_names():
    """Verify that strict validation allows bound names imports and extra names.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    code = """
import math

def scale(value, *rest, factor=2, **kwargs):
    total = 0
    for name, wall in data.items():
        total += len(name) + int(wall)
    with manager as handle:
        total += handle.value
    try:
        computed = math.sqrt(total) + value + factor + len(rest) + len(kwargs)
    except ValueError as exc:
        computed = 0
    return computed
"""

    result = validate_python_source(
        code,
        strict=True,
        extra_allowed_names={"data", "manager"},
    )

    assert result.status == "ok"


def test_sanitize_python_code_replaces_only_name_tokens():
    """Verify that sanitize python code replaces only name tokens.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    code = "x = true\ny = false\nz = null\ns = 'true false null'  # true"

    sanitized, fixes = sanitize_python_code(code)

    assert sanitized == "x = True\ny = False\nz = None\ns = 'true false null'  # true"
    assert fixes == [
        "line 1: true -> True",
        "line 2: false -> False",
        "line 3: null -> None",
    ]


def test_sanitize_python_code_leaves_empty_and_bad_tokens_unchanged():
    """Verify that sanitize python code leaves empty and bad tokens unchanged.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    assert sanitize_python_code("  ") == ("  ", [])
    assert sanitize_python_code("x = (true") == ("x = (true", [])
