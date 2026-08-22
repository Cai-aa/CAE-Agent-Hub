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

"""Schema grounding for CFX Python.

This pass validates the attribute chains that appear in PyCFX snippets against
:class:`~ansys.cfx.mcp.cfx.schema_cache.CFXSchemaCache` and snaps unknown
attribute leaves to the nearest valid name.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import get_close_matches
import logging
import re

from ansys.cfx.mcp.cfx.schema_cache import CFXSchemaCache, get_schema_cache

logger = logging.getLogger("ansys.cfx.mcp.grounding")

# Roots from which a CFX setup attribute chain can begin in generated code,
# e.g. ``pre.raw.setup...`` or a bare ``setup...``.
_CHAIN_RE = re.compile(
    r"""
    (?P<root>(?:[A-Za-z_][\w]*\.)*?)?      # optional leading object chain (pre.raw.)
    (?P<body>setup(?:\.[A-Za-z_]\w*|\[[^\]]*\])+)  # setup followed by .attr or ["name"]
    """,
    re.VERBOSE,
)

# A single ``.attribute`` or ``["instance"]`` segment.
_SEGMENT_RE = re.compile(r"\.([A-Za-z_]\w*)|(\[[^\]]*\])")


@dataclass
class GroundingReport:
    """Summary of changes made by the :func:`ground_code` function."""

    replacements: list[tuple[str, str]] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        """Whether schema grounding changed the original code.

        Returns
        -------
        bool
            Whether the grounded code differs from the original code.
        """
        return bool(self.replacements)


def _split_segments(body: str) -> list[str]:
    """Split a CFX path into schema-relevant name segments.

    Parameters
    ----------
    body : str
        HTTP request body sent to the provider.

    Returns
    -------
    list[str]
        Value computed by the helper for the requested CFX workflow.
    """
    segments = ["setup"]
    rest = body[len("setup") :]
    for match in _SEGMENT_RE.finditer(rest):
        attr, bracket = match.groups()
        segments.append(attr if attr is not None else bracket)
    return segments


def _normalize_path(segments: list[str]) -> str:
    """Normalize CFX path segments into the schema-cache lookup form.

    Parameters
    ----------
    segments : list[str]
        CFX path segments to normalize or join.

    Returns
    -------
    str
        String value produced for the requested CFX or provider operation.
    """
    out = []
    for seg in segments:
        if seg.startswith("["):
            out.append('["<name>"]')
        else:
            out.append(("." if out else "") + seg)
    return "".join(out)


def _ground_chain(body: str, cache: CFXSchemaCache, report: GroundingReport) -> str:
    """Ground one CFX attribute chain against the schema cache.

    Parameters
    ----------
    body : str
        HTTP request body sent to the provider.
    cache : CFXSchemaCache
        Schema, validation, or backend cache used by the helper.
    report : GroundingReport
        Grounding report that records schema corrections.

    Returns
    -------
    str
        String value produced for the requested CFX or provider operation.
    """
    segments = _split_segments(body)
    if cache.exists(_normalize_path(segments)):
        return body

    # Walk left-to-right. The prefix is known to be valid. Repair the first
    # attribute segment that breaks the chain.
    changed = False
    for i in range(1, len(segments)):
        seg = segments[i]
        if seg.startswith("["):
            continue  # instance keys are user data, never rewritten
        prefix_path = _normalize_path(segments[: i + 1])
        if cache.exists(prefix_path):
            continue

        valid_children = cache.children(_normalize_path(segments[:i]))
        # Drop placeholder-only entries. Keep only plain attribute names.
        plain = [c for c in valid_children if not c.endswith('["<name>"]')]
        match = get_close_matches(seg, plain, n=1, cutoff=0.6)
        if match:
            report.replacements.append((seg, match[0]))
            segments[i] = match[0]
            changed = True
        else:
            report.unresolved.append(prefix_path)
            break  # cannot validate deeper without a valid prefix

    if not changed:
        return body

    # Reassemble the body preserving bracket segments verbatim.
    rebuilt = segments[0]
    for seg in segments[1:]:
        rebuilt += seg if seg.startswith("[") else f".{seg}"
    return rebuilt


def ground_code(code: str, cache: CFXSchemaCache | None = None) -> tuple[str, GroundingReport]:
    """Ground generated CFX code by correcting schema-known path segments.

    Parameters
    ----------
    code : str
        Python source code submitted for validation, grounding, or execution.
    cache : CFXSchemaCache | None, default: None
        Schema, validation, or backend cache used by the helper.

    Returns
    -------
    tuple[str, GroundingReport]
        Value computed by the helper for the requested CFX workflow.
    """
    report = GroundingReport()
    if not code:
        return code, report
    cache = cache or get_schema_cache()

    def _replace(match: re.Match[str]) -> str:
        """Replace a matched CFX path with its grounded schema path.

        Parameters
        ----------
        match : re.Match[str]
            Regular-expression match describing the text to replace.

        Returns
        -------
        str
            String value produced for the requested CFX or provider operation.
        """
        root = match.group("root") or ""
        body = match.group("body")
        grounded = _ground_chain(body, cache, report)
        return root + grounded

    grounded_code = _CHAIN_RE.sub(_replace, code)
    if report.changed:
        logger.debug(
            "CFX schema grounding applied %d fix(es): %s",
            len(report.replacements),
            report.replacements,
        )
    return grounded_code, report
