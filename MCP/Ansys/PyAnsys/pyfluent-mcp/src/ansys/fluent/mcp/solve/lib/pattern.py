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

"""Wildcard/pattern helpers for named-object selection.

PyFluent accepts glob-style patterns on string indexers and string-list
properties (such as ``cell_zone_conditions.copy(from_="cell_1", to="cell_*")``
and ``zone_assignment.passive_zone = "*bar*|*tabzone*"``). The solver itself
expands these patterns at runtime. This module mirrors that contract on
the *client* side to do the following:

* Recognize a pattern in user- or host-supplied identifiers.
* Validate a pattern by checking that it matches at least one live name.
* Enumerate matching names for batched (multi-edit) plan steps.

The pattern grammar is a subset of PyFluent's:

* ``*``: Match any run of characters (``fnmatch`` semantics).
* ``?``: Match a single character.
* ``[abc]``: Character class.
* ``|``: Alternation between sub-patterns. For example,
  ``"wall-*|inlet-?"`` matches either branch.

Plain identifiers (no wildcard metacharacters) are returned by
:func:`expand_pattern` unchanged when they appear in ``candidates``,
so a literal name behaves as a direct lookup.
"""

from __future__ import annotations

import fnmatch
from typing import Iterable

_WILDCARD_CHARS = frozenset("*?[|")


def is_pattern(name: str | None) -> bool:
    """Return ``True`` when ``name`` contains any wildcard metacharacter.

    Parameters
    ----------
    name : str | None
        Name of the object, module, or setting being processed.

    Returns
    -------
    bool
        Boolean result produced by the function.
    """
    if not name:
        return False
    return any(ch in _WILDCARD_CHARS for ch in name)


def expand_pattern(pattern: str, candidates: Iterable[str]) -> list[str]:
    """Return every entry in ``candidates`` matching ``pattern``.

    The result preserves the order in which candidates first match, so
    callers get a stable enumeration that mirrors the underlying live
    name list. Duplicate matches (possible across alternation branches)
    are collapsed.

    Plain (non-pattern) ``pattern`` values fall through to a literal
    membership check, returning ``[pattern]`` if present and ``[]``
    otherwise.

    Parameters
    ----------
    pattern : str
        Selection pattern for matching object names.
    candidates : Iterable[str]
        Candidates to supply to the function.

    Returns
    -------
    list[str]
        Collection containing the operation results.
    """
    cands = [str(c) for c in candidates]
    if not is_pattern(pattern):
        return [pattern] if pattern in cands else []

    seen: set[str] = set()
    out: list[str] = []
    branches = [b for b in pattern.split("|") if b]
    for branch in branches:
        for c in cands:
            if c in seen:
                continue
            if fnmatch.fnmatchcase(c, branch):
                seen.add(c)
                out.append(c)
    return out
