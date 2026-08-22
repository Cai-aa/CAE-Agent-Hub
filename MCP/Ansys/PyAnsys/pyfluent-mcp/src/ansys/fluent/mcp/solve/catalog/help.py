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

r"""Docstring extractor for PyFluent's generated ``settings_<version>.py``.

The bundled ``api_objects.json`` carries only ``(path, kind)`` tuples,
which is fine for exact-path lookup but useless for free-text
queries such as *"temperature of incoming gas"*. The relevant leaf is
spelled ``velocity_inlet.thermal.t``, and the token ``t`` does not match
any English word.

PyFluent does, however, ship a one-paragraph class docstring with every
generated settings class. Indexing those docstrings into the lexical
fallback closes most of the recall gap to an embedding-based retriever
without adding a vector store.

This module extracts ``leaf_python_name -> docstring`` from the
generated module **by regex**. Importing the 3.4 MB module is slow and
has side effects unwanted at retrieval time. The parsed map is
cached to disk so the regex is paid once per (PyFluent version,
ansys-fluent-mcp version) combination.

Multiple classes can share a leaf name. For example, ``temperature`` appears as
a child of ``wall``, ``mass_flow_inlet``, ``radiator``, and more. The map
stores the deduplicated union of all docstrings for a given leaf,
joined by ``\\n\\n``. The lexical scorer then tokenizes that blob and
uses it as additional bag-of-words evidence for any path whose leaf
matches.

This is approximate. A query that hits via the ``wall``-specific
docstring may also boost ``radiator``-rooted paths sharing the leaf.
That's an acceptable trade for the cost (~50 LOC, no extra dependency)
because the eventual ranker still prefers paths whose path tokens
overlap the query. The docstring evidence is additive, not decisive.
"""

from __future__ import annotations

import hashlib
from importlib import metadata
import json
import logging
import os
from pathlib import Path
import re
import threading
from typing import Optional

logger = logging.getLogger("ansys.fluent.mcp.api_help")


_CLASS_DOC_RE = re.compile(
    # Class header, then a triple-quoted docstring on the next line(s),
    # then any of the marker lines we expect in the generated file
    # (``_version = ...`` / ``fluent_name = ...`` / ``_python_name = ...``).
    # ``[\s\S]*?`` is used in the doc body so the match can cross
    # newlines without enabling re.DOTALL globally (which would let
    # ``.*?`` in the class header span past its own line).
    r"^class\s+(?P<cls>[A-Za-z_][\w]*).*?:\s*\n"
    r'\s+"""(?P<doc>[\s\S]*?)"""\s*\n'
    r"(?:[\s\S]*?_python_name\s*=\s*[\"'](?P<pn>[^\"']+)[\"'])?",
    re.MULTILINE,
)


def _cache_dir() -> Path:
    """Return ``~/.ansys-fluent-mcp/cache`` (created on demand).

    A single shared user-cache directory keeps the lexical help map,
    the learned-aliases SQLite store and any future cached artefacts
    co-located. Overridable via ``FLUIDS_MCP_CACHE_DIR`` for tests and
    sandboxes that should not write to ``$HOME``.

    Returns
    -------
    Path
        Result produced by the function.
    """
    override = os.environ.get("FLUIDS_MCP_CACHE_DIR")
    if override:
        base = Path(override)
    else:
        base = Path.home() / ".ansys-fluent-mcp" / "cache"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _resolve_settings_file() -> Path:
    """Locate PyFluent's most-recent generated ``settings_<vers>.py``.

    Picks the highest version present so that, if a newer Fluent is
    installed alongside, we index its catalog. ``ansys-fluent-core`` is
    a required dependency, so a missing distribution is allowed to fail
    fast via ``importlib.metadata``.

    Returns
    -------
    Path
        Result produced by the function.
    """
    package_files = metadata.files("ansys-fluent-core") or ()
    candidates = sorted(
        Path(path.locate())
        for path in package_files
        if re.search(r"(?:^|[\\/])settings_\d+\.py$", str(path))
        and "generated" in path.parts
        and "solver" in path.parts
    )
    if not candidates:
        raise FileNotFoundError(
            "ansys-fluent-core must include generated solver settings_*.py files."
        )
    return candidates[-1]


def _extract(text: str) -> dict[str, str]:
    r"""Pull ``(python_name -> docstring)`` from the generated module text.

    When the same leaf name appears in multiple classes the docstrings
    are joined by ``\\n\\n`` so the resulting blob carries all known
    evidence about that leaf.

    Parameters
    ----------
    text : str
        Text value to parse, normalize, or write.

    Returns
    -------
    dict[str, str]
        Mapping containing the operation result.
    """
    out: dict[str, list[str]] = {}
    for m in _CLASS_DOC_RE.finditer(text):
        pn = (m.group("pn") or m.group("cls") or "").strip()
        doc = (m.group("doc") or "").strip()
        if not pn or not doc:
            continue
        bucket = out.setdefault(pn, [])
        if doc not in bucket:
            bucket.append(doc)
    return {k: "\n\n".join(v) for k, v in out.items()}


def build_help_map(
    *,
    settings_path: Optional[Path] = None,
    use_cache: bool = True,
) -> dict[str, str]:
    """Return ``{leaf_python_name: docstring}`` for the active PyFluent.

    The parsed map is memoized to ``$CACHE_DIR/api_help_<hash>.json``
    keyed on the absolute path of the settings file plus its mtime, so
    a PyFluent upgrade transparently rebuilds the cache while normal
    process starts read it back in less than 10 ms.

    Parameters
    ----------
    settings_path : Optional[Path]
        Settings path to supply to the function.
    use_cache : bool
        Use cache to supply to the function.

    Returns
    -------
    dict[str, str]
        Mapping containing the operation result.
    """
    path = settings_path or _resolve_settings_file()
    if not path.is_file():
        return {}
    try:
        stat = path.stat()
    except OSError:
        return {}
    cache_key = hashlib.sha1(
        f"{path}|{int(stat.st_mtime)}|{stat.st_size}".encode("utf-8"),
        usedforsecurity=False,
    ).hexdigest()[:16]
    cache_file = _cache_dir() / f"api_help_{cache_key}.json"
    if use_cache and cache_file.is_file():
        try:
            with cache_file.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items()}
        except (OSError, ValueError) as exc:
            logger.warning("api_help cache unreadable (%s); rebuilding", exc)
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        logger.warning("Failed to read %s: %s", path, exc)
        return {}
    parsed = _extract(text)
    if use_cache:
        try:
            with cache_file.open("w", encoding="utf-8") as fh:
                json.dump(parsed, fh)
        except OSError as exc:  # cache is best-effort
            logger.warning("Failed to write api_help cache %s: %s", cache_file, exc)
    logger.info("api_help: extracted %d leaf docstrings from %s", len(parsed), path.name)
    return parsed


_default_map: Optional[dict[str, str]] = None
_default_lock = threading.Lock()


def get_default_help_map() -> dict[str, str]:
    """Process-wide cached help map, which falls back to an empty dictionary.

    Returns
    -------
    dict[str, str]
        Mapping containing the operation result.
    """
    global _default_map
    if _default_map is None:
        with _default_lock:
            if _default_map is None:
                _default_map = build_help_map()
    return _default_map


def reset_default_help_map() -> None:
    """Test hook for clearing the in-process help map cache.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    global _default_map
    with _default_lock:
        _default_map = None


__all__ = [
    "build_help_map",
    "get_default_help_map",
    "reset_default_help_map",
]
