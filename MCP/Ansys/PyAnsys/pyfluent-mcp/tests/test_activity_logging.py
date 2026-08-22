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

from ansys.fluent.mcp.common.activity_logging import (
    format_iterable_inline,
    sanitize_args,
    summarise_result,
    truncate_text,
)


def test_sanitize_args_redacts_and_truncates_nested_values():
    """Verify that sanitize args redacts and truncates nested values.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    sanitized = sanitize_args(
        {
            "api_key": "secret-value",
            "path": "C:/very/long/path/that/stays/whole",
            "payload": "abcdef",
            "nested": [{"authToken": "abcd"}, ("long-value",)],
        },
        limit=4,
    )

    assert sanitized["api_key"] == "<redacted len=12>"
    assert sanitized["path"] == "C:/very/long/path/that/stays/whole"
    assert sanitized["payload"] == "abcd... <+2 chars>"
    assert sanitized["nested"] == [{"authToken": "<redacted len=4>"}, ["long... <+6 chars>"]]


def test_summarise_result_compacts_large_collections():
    """Verify that summarize result compacts large collections.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    result = summarise_result(
        {
            "items": list(range(20)),
            "mapping": {f"key_{idx}": idx for idx in range(15)},
            "message": "abcdefghij",
        },
        limit=5,
    )

    assert result["items"] == {"_kind": "list", "_head": [0, 1, 2, 3, 4, 5], "_size": 20}
    assert result["mapping"]["_kind"] == "dict"
    assert result["mapping"]["_size"] == 15
    assert result["message"] == "abcde... <+5 chars>"


def test_format_iterable_inline_stops_at_limit():
    """Verify that format iterable inline stops at limit.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    assert format_iterable_inline(["alpha", "beta", "gamma"], limit=14) == "alpha, beta, \u2026"


def test_truncate_text_handles_empty_and_long_text():
    """Verify that truncate text handles empty and long text.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    assert truncate_text("") == ""
    assert truncate_text("abcdef", limit=3) == "abc... <+3 chars>"
