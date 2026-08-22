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

from ansys.fluent.mcp.common.text_match import (
    edit_distance_le_one,
    fuzzy_normalize,
    sanitize_named_object_key,
)


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("water", "water"),
        ("water", "waver"),
        ("water", "waters"),
        ("water", "wate"),
    ],
)
def test_edit_distance_le_one_true_cases(left, right):
    """Verify that edit distance le one true cases.

    Parameters
    ----------
    left : Any
        Left to supply to the function.
    right : Any
        Right to supply to the function.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    assert edit_distance_le_one(left, right) is True


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("water", "steam"),
        ("water", "wateryy"),
        ("ab", "ba"),
    ],
)
def test_edit_distance_le_one_false_cases(left, right):
    """Verify that edit distance le one false cases.

    Parameters
    ----------
    left : Any
        Left to supply to the function.
    right : Any
        Right to supply to the function.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    assert edit_distance_le_one(left, right) is False


def test_fuzzy_normalize_returns_unique_canonical_match_only():
    """Verify that fuzzy normalize returns unique canonical match only.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    assert fuzzy_normalize("water-vapour", ["water-vapor", "air"]) == "water-vapor"
    assert fuzzy_normalize("water-vapor", ["water-vapor", "air"]) is None
    assert fuzzy_normalize("cat", ["bat", "car"]) is None
    assert fuzzy_normalize(123, ["123"]) is None


def test_sanitize_named_object_key_rewrites_whitespace_only():
    """Verify that sanitize named object key rewrites whitespace only.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    sanitized, notice = sanitize_named_object_key("  oil   inlet  ")

    assert sanitized == "oil-inlet"
    assert "contained whitespace" in notice
    assert sanitize_named_object_key("phase-1") == ("phase-1", None)
    assert sanitize_named_object_key("phase/1") == ("phase/1", None)
    assert sanitize_named_object_key(123) == (123, None)
