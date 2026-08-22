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

"""Shared string-matching utilities for fuzzy/typo-tolerant lookup.

These helpers are used everywhere callers need to reconcile a supplied
identifier against a finite, authoritative set of known strings — material
names, allowed values of an enum-typed setting, NamedObject keys, dict-key
schemas, command kwargs, etc.

Keeping the implementation in one place avoids the trap we hit historically:
``_check_value`` learned to tolerate the ``"least-squares-cell-based"`` ->
``"least-square-cell-based"`` typo while ``copy_material`` could not even
resolve ``"water-vapour"`` -> ``"water-vapor"``. Both are the same
single-edit problem; both should share the same solution.

Public API:
    * :func:`edit_distance_le_one` — fast ``≤ 1`` Levenshtein verdict.
    * :func:`fuzzy_normalize` — return the canonical spelling if and
      only if exactly one entry in ``allowed`` is within edit distance
      1 (case-insensitive), else ``None``.
    * :func:`sanitize_named_object_key` — collapse whitespace in a
            NamedObject key to the idiomatic hyphen separator.
"""

from __future__ import annotations

from collections.abc import Iterable
import re


def edit_distance_le_one(a: str, b: str) -> bool:
    """Return True iff Levenshtein distance between ``a`` and ``b`` is at most 1.

    Faster than computing the full distance because we only need the
    ``≤ 1`` verdict.

    Parameters
    ----------
    a : str
        A supplied to the function.
    b : str
        B supplied to the function.

    Returns
    -------
    bool
        Boolean result produced by the function.
    """
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la == lb:
        diffs = 0
        for ca, cb in zip(a, b):
            if ca != cb:
                diffs += 1
                if diffs > 1:
                    return False
        return diffs == 1
    if la > lb:
        a, b = b, a
        la, lb = lb, la
    i = j = 0
    skipped = False
    while i < la and j < lb:
        if a[i] == b[j]:
            i += 1
            j += 1
        elif skipped:
            return False
        else:
            j += 1
            skipped = True
    return True


def fuzzy_normalize(value: str, allowed: Iterable[str]) -> str | None:
    """Normalize ``value`` to a canonical spelling from ``allowed``.

    It returns the canonical spelling for ``value`` if exactly one entry
    in ``allowed`` is within edit distance 1 (case-insensitive), else
    ``None``.

    Uniqueness is required so a near-spelling never silently overwrites
    a value when two candidates are equally plausible — surface the
    ambiguity to the caller instead.

    Parameters
    ----------
    value : str
        Value supplied to the function.
    allowed : Iterable[str]
        Allowed supplied to the function.

    Returns
    -------
    str | None
        String result produced by the function.
    """
    if not isinstance(value, str):
        return None
    low = value.lower()
    matches = [a for a in allowed if isinstance(a, str) and edit_distance_le_one(low, a.lower())]
    if len(matches) == 1 and matches[0] != value:
        return matches[0]
    return None


# Whitespace inside a NamedObject key is the most common naming
# violation we see from natural-language intent. Other illegal
# characters (``/``, ``\``, ``:``),
# brackets, ...) appear far more rarely and conflating them into the
# same auto-fix risks corrupting names the user intentionally typed,
# so we intentionally scope the helper to whitespace only and let
# the backend surface the apply-time error for the rest.
_WHITESPACE_RE = re.compile(r"\s+")


def sanitize_named_object_key(
    name: str,
    *,
    replacement: str = "-",
) -> tuple[str, str | None]:
    r"""Return ``(sanitized_name, notice_or_None)`` for a NamedObject key.

    Some backends reject whitespace in NamedObject instance keys (BC names,
    cell-zone names, material names, named-expression keys, ...).
    Internal whitespace runs are collapsed to ``replacement`` (hyphen
    by default — the idiomatic separator, e.g.
    ``pressure-outlet-1``, ``phase-1``, ``cold-inlet``) and leading
    or trailing whitespace is stripped.

    The function is conservative — it ONLY rewrites whitespace.
    Other illegal characters (``/``, ``\\``, ``:``, brackets, ...) are
    rare in natural-language intent and are deliberately left alone
    so a deterministic rewrite never corrupts a name the user
    intentionally typed; the backend surfaces those at apply time.

    Returns a 2-tuple:

    * ``sanitized_name``  — the cleaned name (equal to ``name`` when
      no rewrite was needed).
    * ``notice``          — a one-line human-readable explanation of
      the rewrite, or ``None`` when the input was already clean.

    Non-string inputs are returned unchanged with ``notice=None`` so
    callers can pipe values through this helper unconditionally.

    Example::

        >>> sanitize_named_object_key("oil inlet")
        ('oil-inlet', "name 'oil inlet' contained whitespace; ...")
        >>> sanitize_named_object_key("phase-1")
        ('phase-1', None)

    Parameters
    ----------
    name : str
        Name of the object, module, or setting being processed.
    replacement : str
        Replacement supplied to the function.

    Returns
    -------
    tuple[str, str | None]
        Collection containing the operation results.
    """
    if not isinstance(name, str):
        return name, None
    stripped = name.strip()
    sanitized = _WHITESPACE_RE.sub(replacement, stripped)
    if sanitized == name:
        return name, None
    notice = (
        f"name {name!r} contained whitespace; auto-corrected to "
        f"{sanitized!r} (spaces are not valid in NamedObject keys; "
        f"hyphens are the idiomatic separator, e.g. 'pressure-outlet-1')."
    )
    return sanitized, notice
