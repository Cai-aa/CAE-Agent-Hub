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

"""Lexical fallback over the PyFluent API catalog (the default in practice).

This module is the SOLE actively-running retriever for every default install.

It reads ``ansys/fluent/core/generated/api_tree/api_objects.json``
(shipped with ``ansys-fluent-core``) and offers three operations used
by orchestration:

* :meth:`ApiIndex.search`: **BM25** ranking over the union of path
  tokens and PyFluent class docstring tokens. (See
  :mod:`ansys.fluent.mcp.common.api_help`). Cheap, dependency free, and
  much stronger than the previous token-overlap scorer for
  free-text queries. For example, "temperature of incoming gas" →
  ``velocity_inlet.thermal.t`` now works because the leaf class's
  docstring contains the word *temperature*.
* :meth:`ApiIndex.lookup`: Exact dotted-path resolution.
* :meth:`ApiIndex.children_of`: Immediate API children of a path
  For example, used to walk a boundary condition kind to enumerate
  its property leaves.

The scoring formula follows. Also see :func:`_score_entry`)::

    bm25(query_tokens, entry_tokens)
      + 0.25 * (#query_token substring matches in path)
      - 0.05 * (path depth in dots)

The substring bonus preserves the historic behavior where exact
segment matches (``energy`` → ``setup.models.energy``) outrank deeper
family matches. The depth penalty discourages picking generic
ancestors over leaf parameters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import resources
import json
import logging
import math
import os
from pathlib import Path
import re
import threading
from typing import Iterable, Optional

logger = logging.getLogger("ansys.fluent.mcp.api_index")


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


@dataclass
class ApiEntry:
    """One row of ``api_objects.json``.

    ``tokens`` is the union of path tokens and docstring tokens for
    the leaf class (when a PyFluent docstring is available). ``doc``
    is the raw docstring blob for diagnostics; the scorer only ever
    looks at ``tokens``.
    """

    raw: str  # original line, e.g. ``<solver_session>.foo (Parameter)``
    path: str  # normalised dotted path without the session prefix
    kind: str  # Object | Parameter | Command | Group | ...
    session: str  # solver_session | meshing_session | ...
    tokens: list[str] = field(default_factory=list)
    doc: str = ""


@dataclass
class ApiSearchHit:
    """One search hit from the index."""

    entry: ApiEntry
    score: float


# ---------------------------------------------------------------------------
# Index
# ---------------------------------------------------------------------------


_LINE_RE = re.compile(r"^<(?P<session>[^>]+)>\.?(?P<path>.*?)\s*\((?P<kind>[^)]+)\)\s*$")
_TOKEN_RE = re.compile(r"[a-z0-9]+")


class ApiIndex:
    """Lightweight searchable index over PyFluent's ``api_objects.json``.

    Thread-safe lazy load. Subclass / replace via ``custom_path`` for tests.
    """

    def __init__(
        self,
        *,
        custom_path: Optional[str] = None,
        sessions: Iterable[str] = ("solver_session",),
        help_map: Optional[dict[str, str]] = None,
        extra_entries: Optional[list["ApiEntry"]] = None,
    ) -> None:
        """Initialize the ApiIndex instance.

        Parameters
        ----------
        custom_path : Optional[str]
            Path for the custom.
        sessions : Iterable[str]
            Sessions to supply to the function.
        help_map : Optional[dict[str, str]]
            Help map to supply to the function.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        self._custom_path = custom_path
        self._sessions = set(sessions)
        self._help_map_override = help_map  # None → lazy default; {} → explicitly empty
        self._extra_entries: list[ApiEntry] = list(extra_entries) if extra_entries else []
        self._lock = threading.Lock()
        self._loaded = False
        self._entries: list[ApiEntry] = []
        self._by_path: dict[str, ApiEntry] = {}
        # BM25 corpus statistics, populated alongside _entries.
        self._doc_freq: dict[str, int] = {}
        self._avgdl: float = 0.0
        self._n_docs: int = 0

    # ---- loading ------------------------------------------------------

    @property
    def available(self) -> bool:
        """Return whether the catalog index is available.

        Returns
        -------
        bool
            Boolean result of the operation.
        """
        self._ensure_loaded()
        return bool(self._entries)

    def _ensure_loaded(self) -> None:
        """Load the catalog index if it has not been loaded yet.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            self._loaded = True
            path = self._resolve_path()
            if path is None:
                logger.info("api_objects.json not found; ApiIndex disabled")
                return
            try:
                with Path(path).open("r", encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, ValueError) as exc:
                logger.warning("Failed to load %s: %s", path, exc)
                return
            raw_entries = data.get("api_objects") if isinstance(data, dict) else None
            if not isinstance(raw_entries, list):
                logger.warning("Unexpected api_objects.json shape at %s", path)
                return
            help_map: dict[str, str]
            if self._help_map_override is not None:
                help_map = self._help_map_override
            else:
                try:
                    from ansys.fluent.mcp.solve.catalog.help import get_default_help_map

                    help_map = get_default_help_map()
                except Exception as exc:  # help layer is optional
                    logger.warning("api_help unavailable (%s); proceeding path-only", exc)
                    help_map = {}
            for line in raw_entries:
                entry = _parse_line(line, help_map=help_map)
                if entry is None or entry.session not in self._sessions:
                    continue
                self._entries.append(entry)
                self._by_path[entry.path] = entry
            # Inject caller-supplied synthetic entries (e.g. meshing workflow tasks)
            # before building BM25 stats so they participate fully in ranking.
            for _extra in self._extra_entries:
                self._entries.append(_extra)
                self._by_path.setdefault(_extra.path, _extra)
            # Build BM25 stats over the (path + doc) token bag.
            total_len = 0
            for entry in self._entries:
                total_len += len(entry.tokens)
                for term in set(entry.tokens):
                    self._doc_freq[term] = self._doc_freq.get(term, 0) + 1
            self._n_docs = len(self._entries)
            self._avgdl = (total_len / self._n_docs) if self._n_docs else 0.0
            logger.info(
                "Loaded %d API entries from %s (help docs: %d, avgdl=%.1f)",
                self._n_docs,
                path,
                sum(1 for e in self._entries if e.doc),
                self._avgdl,
            )

    def _resolve_path(self) -> Optional[Path]:
        """Resolve path.

        Returns
        -------
        Optional[Path]
            Optional value produced by the operation.
        """
        if self._custom_path:
            return Path(self._custom_path)
        env_path = os.getenv("FLUIDS_MCP_API_OBJECTS_PATH")
        if env_path and Path(env_path).is_file():
            return Path(env_path)
        # Preferred path: importlib.resources over the generated api_tree
        # package. Handles zipped wheels and editable installs.
        try:
            files = resources.files("ansys.fluent.core.generated.api_tree")
            candidate_ref = files.joinpath("api_objects.json")
            with resources.as_file(candidate_ref) as candidate:
                if candidate.is_file():
                    return Path(candidate)
        except (ModuleNotFoundError, FileNotFoundError, KeyError):
            pass
        # Fallback for environments where package resources are not
        # discoverable (namespace-package edge cases).
        try:
            import ansys.fluent.core as fluent_pkg  # type: ignore

            pkg_file = getattr(fluent_pkg, "__file__", None)
            if isinstance(pkg_file, str) and pkg_file:
                candidate = Path(pkg_file).parent / "generated" / "api_tree" / "api_objects.json"
                if candidate.is_file():
                    return candidate
        except (ImportError, AttributeError, TypeError, KeyError):
            pass
        # Final fallback: direct site-packages probe to survive broken
        # namespace metadata on certain Python/installer combinations.
        try:
            import site

            candidates = [
                Path(p)
                / "ansys"
                / "fluent"
                / "core"
                / "generated"
                / "api_tree"
                / "api_objects.json"
                for p in (site.getsitepackages() + [site.getusersitepackages()])
            ]
            for candidate in candidates:
                if candidate.is_file():
                    return candidate
        except Exception as exc:
            logger.debug("Site-packages probe for api_objects.json failed: %s", exc)
        return None

    # ---- lookup -------------------------------------------------------

    def lookup(self, path: str) -> Optional[ApiEntry]:
        """Return the exact lookup.

        ``path`` is the dotted path **without** the session prefix and
        without ``["<name>"]`` instance keys.

        Parameters
        ----------
        path : str
            Fluent object path or file-system path to inspect.

        Returns
        -------
        Optional[ApiEntry]
            Result produced by the function.
        """
        self._ensure_loaded()
        if not path:
            return None
        return self._by_path.get(_normalise_path(path))

    def children_of(self, path: str, *, max_results: int = 50) -> list[ApiEntry]:
        """Return immediate children of ``path``.

        This refers to entries whose path begins with ``path.`` and has no further dots.

        Parameters
        ----------
        path : str
            Fluent object path or file-system path to inspect.
        max_results : int
            Max results to supply to the function.

        Returns
        -------
        list[ApiEntry]
            Collection containing the operation results.
        """
        self._ensure_loaded()
        prefix = _normalise_path(path)
        if not prefix:
            return []
        prefix_dot = prefix + "."
        plen = len(prefix_dot)
        out: list[ApiEntry] = []
        for entry in self._entries:
            if not entry.path.startswith(prefix_dot):
                continue
            tail = entry.path[plen:]
            # Skip indexed sub-paths and grandchildren.
            if "." in tail.split("[", 1)[0] and not tail.startswith('"'):
                continue
            out.append(entry)
            if len(out) >= max_results:
                break
        return out

    # ---- search -------------------------------------------------------

    def search(
        self,
        query: str,
        *,
        top_k: int = 10,
        kinds: Optional[Iterable[str]] = None,
        under: Optional[str] = None,
    ) -> list[ApiSearchHit]:
        """Token-overlap scoring against the API path tokens.

        Parameters
        ----------
        query
            User question or property hint (e.g. ``"temperature inlet"``).
        top_k
            Maximum number of hits to return.
        kinds
            Optional set of kinds to keep (``"Parameter"``, ``"Command"`` ...).
        under
            Optional path prefix; restricts the search to entries below it.

        Returns
        -------
        list[ApiSearchHit]
            Collection containing the operation results.
        """
        self._ensure_loaded()
        if not query or not self._entries:
            return []
        q_tokens = _tokenise(query)
        if not q_tokens:
            return []
        kinds_set = {k for k in kinds} if kinds else None
        prefix = _normalise_path(under) + "." if under else None

        hits: list[ApiSearchHit] = []
        for entry in self._entries:
            if kinds_set and entry.kind not in kinds_set:
                continue
            if prefix and not entry.path.startswith(prefix):
                continue
            score = self._score_entry(q_tokens, entry)
            if score > 0:
                hits.append(ApiSearchHit(entry=entry, score=score))

        hits.sort(key=lambda h: (-h.score, len(h.entry.path)))
        return hits[:top_k]

    # ------------------------------------------------------------------
    # BM25
    # ------------------------------------------------------------------

    # Classic BM25 parameters; the corpus is short technical text so
    # the defaults from the original paper work fine.
    _BM25_K1 = 1.5
    _BM25_B = 0.75

    def _score_entry(self, query_tokens: list[str], entry: ApiEntry) -> float:
        """BM25 over (path ∪ doc) tokens + path substring bonus − depth penalty.

        Returns ``0.0`` when no query token is present in the entry's
        token bag (matches the strict ``overlap==0 → drop`` filter the
        old scorer used; prevents irrelevant entries leaking into
        results just because BM25 assigns them a tiny positive score).

        Parameters
        ----------
        query_tokens : list[str]
            Query tokens to supply to the function.
        entry : ApiEntry
            Entry to supply to the function.

        Returns
        -------
        float
            Floating-point result produced by the function.
        """
        if not entry.tokens or self._n_docs == 0:
            return 0.0
        # Frequency lookup over the entry token bag (with duplicates).
        tf: dict[str, int] = {}
        for tok in entry.tokens:
            tf[tok] = tf.get(tok, 0) + 1
        doc_len = len(entry.tokens)
        score = 0.0
        any_match = False
        k1 = self._BM25_K1
        b = self._BM25_B
        for q in query_tokens:
            if q not in tf:
                continue
            any_match = True
            df = self._doc_freq.get(q, 0)
            # IDF with the BM25+ smoothing — never goes negative even
            # for very common terms.
            idf = math.log(1.0 + (self._n_docs - df + 0.5) / (df + 0.5))
            f = tf[q]
            denom = f + k1 * (1.0 - b + b * (doc_len / self._avgdl if self._avgdl else 1.0))
            score += idf * ((f * (k1 + 1.0)) / denom)
        if not any_match:
            return 0.0
        # Substring bonus and depth penalty preserve the prior ordering
        # bias: exact path-segment matches beat scattered docstring
        # evidence, and shorter paths beat ancestor-only matches.
        lc = entry.path.lower()
        bonus = sum(0.25 for t in query_tokens if t and t in lc)
        depth_penalty = 0.05 * entry.path.count(".")
        return score + bonus - depth_penalty


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_line(line: str, *, help_map: Optional[dict[str, str]] = None) -> Optional[ApiEntry]:
    """Parse line.

    Parameters
    ----------
    line : str
        Line to supply to the function.
    help_map : Optional[dict[str, str]]
        Help map to supply to the function.

    Returns
    -------
    Optional[ApiEntry]
        Optional value produced by the operation.
    """
    if not isinstance(line, str):
        return None
    m = _LINE_RE.match(line.strip())
    if not m:
        return None
    session = m.group("session")
    raw_path = m.group("path") or ""
    kind = m.group("kind").strip()
    norm = _normalise_path(raw_path)
    if not norm:
        return None
    # Strip the PyFluent TUI bridge at the indexing boundary. The TUI
    # is a text-command escape hatch (``solver.tui.*``) that bypasses
    # every settings-API guardrail (no schema, no allowed-values, no
    # apply-time resolve). Excluding it from the search index means
    # the retriever can never surface a TUI path to clients, and the
    # AST validator's runtime block becomes pure defense-in-depth.
    if norm == "tui" or norm.startswith("tui.") or ".tui." in norm or norm.endswith(".tui"):
        return None
    tokens = _tokenise(norm)
    # Augment tokens with class-docstring tokens for EVERY segment of
    # the path. PyFluent's settings classes — ``velocity_inlet``,
    # ``thermal``, ``t`` — each carry their own one-paragraph
    # docstring; indexing only the leaf misses queries like
    # *"inlet gas temperature"* where the discriminating word lives
    # in the intermediate ``velocity_inlet`` class. A query token is
    # treated as evidence for any path whose token bag (path
    # segments + per-segment docstrings) contains it; BM25 then
    # rewards paths with denser overlap.
    #
    # ``seen_doc`` deduplicates so a leaf name that happens to repeat
    # in the path (rare, but e.g. ``mesh.mesh.size``) doesn't double-
    # count the same docstring.
    doc_parts: list[str] = []
    if help_map:
        seen_doc: set[str] = set()
        for seg in norm.split("."):
            if not seg:
                continue
            d = help_map.get(seg)
            if d and d not in seen_doc:
                seen_doc.add(d)
                doc_parts.append(d)
                tokens = tokens + _tokenise(d)
    doc = "\n\n".join(doc_parts)
    return ApiEntry(
        raw=line,
        path=norm,
        kind=kind,
        session=session,
        tokens=tokens,
        doc=doc,
    )


def _normalise_path(path: str) -> str:
    """Drop instance keys ``["<name>"]`` and leading separators.

    Parameters
    ----------
    path : str
        Fluent object path or file-system path to inspect.

    Returns
    -------
    str
        String result produced by the function.
    """
    if not path:
        return ""
    # Replace ["<name>"] / ['anything'] with empty so paths collapse.
    cleaned = re.sub(r"\[[^\]]*\]", "", path)
    cleaned = cleaned.strip(". ")
    # Collapse double dots produced by stripping instance keys.
    cleaned = re.sub(r"\.{2,}", ".", cleaned)
    return cleaned


def _tokenise(text: str) -> list[str]:
    """Split text into searchable tokens.

    Parameters
    ----------
    text : str
        Text value to parse, normalise, or write.

    Returns
    -------
    list[str]
        List of results produced by the operation.
    """
    return _TOKEN_RE.findall(text.lower())


# ---------------------------------------------------------------------------
# Singleton helper
# ---------------------------------------------------------------------------


_SOLVER_SESSIONS = ("solver_session",)
_MESHING_SESSIONS = ("meshing_session",)

_default_index: Optional[ApiIndex] = None
_default_meshing_index: Optional[ApiIndex] = None
_default_lock = threading.Lock()


def get_default_api_index() -> ApiIndex:
    """Return the default API index.

    Returns
    -------
    ApiIndex
       API index produced by the operation.
    """
    global _default_index
    if _default_index is None:
        with _default_lock:
            if _default_index is None:
                _default_index = ApiIndex()
    return _default_index


def get_meshing_api_index() -> ApiIndex:
    """Return the default meshing API index.

    Returns
    -------
    ApiIndex
       Meshing API index produced by the operation.
    """
    global _default_meshing_index
    if _default_meshing_index is None:
        with _default_lock:
            if _default_meshing_index is None:
                from ansys.fluent.mcp.solve.catalog.meshing_workflow_entries import (
                    get_meshing_workflow_entries,
                )

                _default_meshing_index = ApiIndex(
                    sessions=_MESHING_SESSIONS,
                    extra_entries=get_meshing_workflow_entries(),
                )
    return _default_meshing_index


def get_api_index_for_session(session: str) -> ApiIndex:
    """Return a default API index for a PyFluent session kind.

    Parameters
    ----------
    session : str
        Session kind from ``api_objects.json`` such as ``solver_session``
        or ``meshing_session``.

    Returns
    -------
    ApiIndex
        API index produced by the operation.
    """
    if session == "meshing_session":
        return get_meshing_api_index()
    return get_default_api_index()


def reset_default_api_index() -> None:
    """Test hook that drops the cached index so that the next call rebuilds.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    global _default_index, _default_meshing_index
    with _default_lock:
        _default_index = None
        _default_meshing_index = None


__all__ = [
    "ApiEntry",
    "ApiSearchHit",
    "ApiIndex",
    "get_default_api_index",
    "get_meshing_api_index",
    "get_api_index_for_session",
    "reset_default_api_index",
]
