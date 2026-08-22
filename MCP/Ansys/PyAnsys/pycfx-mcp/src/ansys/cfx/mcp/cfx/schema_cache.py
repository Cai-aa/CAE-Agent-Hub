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

"""Schema cache built from the CFX engine ``*_info.json`` file dumps.

The cache walks the nested CFX-Pre, CFX-Solver, and CFX-Post API trees shipped in
the ``ansys/cfx/mcp/config`` file and flattens them into dotted Python attribute paths
that match what real PyCFX code emits. For example:

``setup.flow["Flow Analysis 1"].domain["Default Domain"].fluid_models.turbulence_model.option``

It is used to *ground* PyCFX code by validating attribute chains and suggesting
the nearest real path for an unknown one.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import get_close_matches
from functools import lru_cache
from importlib import resources
import json
import keyword
import string
from typing import Any, Iterable

__all__ = ["CFXSchemaCache", "SchemaNode", "to_python_name", "get_schema_cache"]

# Configuration JSON file dumps to index. ``static_info.json`` carries the bulk of the
# CFX-Pre setup tree. The others add Pre/Solver/Post-specific entries.
_CONFIG_FILES = (
    "static_info.json",
    "pre_info.json",
    "solver_info.json",
    "post_info.json",
)

# Placeholder used for the element schema of a named-object. Real code uses a
# quoted instance name (``flow["Flow Analysis 1"]``). The cache normalizes any
# bracket key to this token so paths are comparable.
_NAMED_PLACEHOLDER = '["<name>"]'

_TTABLE = str.maketrans(
    string.punctuation + " ",
    "_" * len(string.punctuation + " "),
)


def to_python_name(cfx_name: str) -> str:
    """Convert a CCL display name into the PyCFX snake-case attribute name.

    Parameters
    ----------
    cfx_name : str
        CCL (CFX Command Language) display name to convert into a Python attribute name.

    Returns
    -------
    str
        String value produced for the requested CFX or provider operation.
    """
    if not cfx_name:
        return cfx_name
    name = cfx_name.lower().translate(_TTABLE)
    while name in keyword.kwlist:
        name = name + "_"
    return name


# CFX node ``type`` -> coarse kind used by the grounding logic.
_KIND_BY_TYPE = {
    "group": "Group",
    "named-object": "NamedObject",
    "command": "Command",
    "query": "Query",
    "string": "Parameter",
    "boolean": "Parameter",
    "integer": "Parameter",
    "real": "Parameter",
    "string-list": "Parameter",
    "real-list": "Parameter",
    "integer-list": "Parameter",
    "vector": "Parameter",
}


@dataclass(frozen=True)
class CommandArgument:
    """One argument of a CFX command, as declared by the schema."""

    name: str
    type_hint: str = ""
    default: str | None = None
    help: str = ""


@dataclass(frozen=True)
class SchemaNode:
    """A single indexed entry in the CFX schema tree."""

    path: str
    kind: str
    cfx_type: str
    help: str = ""
    # Allowed-value enumeration declared by the schema for this path.
    # ``None`` means "no enumeration known" (free-form value). An empty
    # tuple means "the schema declared an empty enumeration" (rare).
    allowed_values: tuple[Any, ...] | None = None
    # Command/query argument schema is indexed from the bundled
    # configuration files. Empty tuple for non-command nodes.
    arguments: tuple[CommandArgument, ...] = ()

    @property
    def is_named(self) -> bool:
        """Whether this schema entry represents a named-object collection.

        Returns
        -------
        bool
            Boolean answer for the requested condition.
        """
        return self.kind == "NamedObject"

    @property
    def is_parameter(self) -> bool:
        """Whether this schema entry represents a parameter leaf.

        Returns
        -------
        bool
            Boolean answer for the requested condition.
        """
        return self.kind == "Parameter"

    @property
    def has_allowed_values(self) -> bool:
        """Whether this schema declared an explicit value set.

        ``True`` only when the bundled configuration files attach an
        enum-style values list to this path. ``False`` for
        free-form primitives (``integer``/``real``/``string``
        without an enum cross-reference.
        """
        return self.allowed_values is not None and len(self.allowed_values) > 0

    @property
    def is_command(self) -> bool:
        """Whether this schema entry represents a command."""
        return self.kind == "Command"


def _normalize_for_lookup(path: str) -> str:
    """Normalize a CFX schema path into the canonical lookup key.

    Parameters
    ----------
    path : str
        CFX API, object, schema, or file path to process.

    Returns
    -------
    str
        String value produced for the requested CFX or provider operation.
    """
    out = []
    depth = 0
    for ch in path:
        if ch == "[":
            depth += 1
            if depth == 1:
                out.append(_NAMED_PLACEHOLDER)
        elif ch == "]":
            depth -= 1
        elif depth == 0:
            out.append(ch)
    return "".join(out)


class CFXSchemaCache:
    """In-memory index of the CFX API tree for code generation grounding."""

    def __init__(self, config_files: Iterable[str] | None = None) -> None:
        """Initialize this object with the dependencies required for later operations.

        Parameters
        ----------
        config_files : Iterable[str] | None, default: None
            Schema JSON files to load. If ``None``, the bundled configuration files are used.

        Returns
        -------
        None
            No value is returned. Side effects are applied to the relevant cache, session, or
            server.
        """
        self._by_path: dict[str, SchemaNode] = {}
        self._children: dict[str, set[str]] = {}
        # ``enum_name -> tuple[str, ...]`` lookup populated from the
        # top-level ``enums`` block of each loaded config file. Used
        # by :meth:`_walk` to attach ``allowed_values`` to a leaf
        # whose ``type`` references an enum.
        self._enums: dict[str, tuple[Any, ...]] = {}
        self._config_files = tuple(config_files) if config_files else _CONFIG_FILES
        self._loaded = False

    # -- loading ----------------------------------------------------------
    def _ensure_loaded(self) -> None:
        """Load CFX schema metadata on first use of the cache.

        Returns
        -------
        None
            No value is returned. Side effects are applied to the relevant cache, session, or
            server.
        """
        if not self._loaded:
            self._load()
            self._loaded = True

    def _load(self) -> None:
        """Load bundled CFX schema JSON files into the cache.

        Returns
        -------
        None
            No value is returned. Side effects are applied to the relevant cache, session, or
            server.
        """
        pkg = "ansys.cfx.mcp.config"
        for filename in self._config_files:
            try:
                text = resources.files(pkg).joinpath(filename).read_text(encoding="utf-8")
            except (FileNotFoundError, ModuleNotFoundError, OSError):
                continue
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                continue
            # Capture top-level ``enums`` so per-leaf ``type``
            # references like ``"type": "UIMode"`` can attach the
            # canonical allowed-value list to the SchemaNode.
            for ename, edata in (data.get("enums") or {}).items():
                if isinstance(edata, dict):
                    raw_values = edata.get("values") or edata.get("allowed_values") or ()
                    if isinstance(raw_values, (list, tuple)):
                        self._enums[ename] = tuple(raw_values)
            # Top-level tree describes the root group. Descend into children,
            # commands, and queries without emitting a node for the root itself.
            self._walk_children(data, "")

    def _walk(self, node: object, prefix: str) -> None:
        """Walk a schema JSON node and record every reachable CFX API path.

        Parameters
        ----------
        node : object
            AST or PyCFX object node being inspected.
        prefix : str
            Current schema path prefix used while walking nested configuration data.

        Returns
        -------
        None
            No value is returned.Side effects are applied to the relevant cache, session, or
            server.
        """
        if not isinstance(node, dict):
            return
        cfx_type = node.get("type", "group")
        kind = _KIND_BY_TYPE.get(cfx_type, "Group")
        help_text = node.get("help", "") or ""
        # Inline ``values`` declaration on a leaf (rare but legal for
        # logical / enum-style parameters that don't reference a
        # shared enum name).
        allowed: tuple[Any, ...] | None = None
        if isinstance(node.get("values"), (list, tuple)):
            allowed = tuple(node["values"])
        elif isinstance(cfx_type, str) and cfx_type in self._enums:
            allowed = self._enums[cfx_type]
        self._record(prefix, kind, cfx_type, help_text, allowed_values=allowed)
        self._walk_children(node, prefix)

    def _walk_children(self, node: dict, prefix: str) -> None:
        """Walk child entries for a schema JSON node.

        Parameters
        ----------
        node : dict
            AST or PyCFX object node being inspected.
        prefix : str
            Current schema path prefix used while walking nested configuration data.

        Returns
        -------
        None
            No value is returned. Side effects are applied to the relevant cache, session, or
            server.
        """
        for name, child in (node.get("children") or {}).items():
            self._walk(child, self._join(prefix, to_python_name(name)))

        element = node.get("object-type")
        if isinstance(element, dict):
            self._walk(element, (prefix or "") + _NAMED_PLACEHOLDER)

        # Commands carry an ``args`` list of ``{name, type, default}``
        # dicts that the agent needs to compose a valid call. Index
        # them on the command's SchemaNode so ``get_command_arguments``
        # can return them without re-walking the JSON.
        for name, cmd in (node.get("commands") or {}).items():
            cmd_path = self._join(prefix, to_python_name(name))
            args = self._extract_arguments(cmd) if isinstance(cmd, dict) else ()
            help_text = (cmd.get("help") if isinstance(cmd, dict) else "") or ""
            self._record(
                cmd_path,
                "Command",
                "command",
                help_text=help_text,
                arguments=args,
            )

        for name, qry in (node.get("queries") or {}).items():
            qry_path = self._join(prefix, to_python_name(name))
            args = self._extract_arguments(qry) if isinstance(qry, dict) else ()
            help_text = (qry.get("help") if isinstance(qry, dict) else "") or ""
            self._record(
                qry_path,
                "Query",
                "query",
                help_text=help_text,
                arguments=args,
            )

    def _extract_arguments(self, node: dict) -> tuple[CommandArgument, ...]:
        """Parse a command/query schema node's ``args`` block.

        The bundled configuration files store ``args`` as a list of
        ``{name, type, default}`` dictionaries. Any non-dictionary entry is
        ignored so a future schema-format extension does not crash
        the loader.
        """
        raw_args = node.get("args")
        if not isinstance(raw_args, list):
            return ()
        parsed: list[CommandArgument] = []
        for entry in raw_args:
            if not isinstance(entry, dict):
                continue
            arg_name = str(entry.get("name") or "").strip()
            if not arg_name:
                continue
            parsed.append(
                CommandArgument(
                    name=arg_name,
                    type_hint=str(entry.get("type") or ""),
                    default=(
                        str(entry["default"])
                        if "default" in entry and entry["default"] is not None
                        else None
                    ),
                    help=str(entry.get("help") or ""),
                )
            )
        return tuple(parsed)

    @staticmethod
    def _join(prefix: str, name: str) -> str:
        """Join CFX schema path parts into a normalized dotted path.

        Parameters
        ----------
        prefix : str
            Current schema path prefix used while walking nested configuration data.
        name : str
            Name of the object, resource, or field to process.

        Returns
        -------
        str
            String value produced for the requested CFX or provider operation.
        """
        return f"{prefix}.{name}" if prefix else name

    def _record(
        self,
        path: str,
        kind: str,
        cfx_type: str,
        help_text: str = "",
        *,
        allowed_values: tuple[Any, ...] | None = None,
        arguments: tuple[CommandArgument, ...] = (),
    ) -> None:
        """Record one CFX schema metadata entry in the cache.

        Parameters
        ----------
        path : str
            CFX API, object, schema, or file path to process.
        kind : str
            Type or category used to select behavior.
        cfx_type : str
            CFX object type recorded for the schema entry.
        help_text : str, default: ``""``
            Help text associated with the schema entry.
        allowed_values : tuple[Any, ...] | None
            Allowed-value enumeration for the path (resolved from the
            schema's ``enums`` block or an inline ``values`` list).
        arguments : tuple[CommandArgument, ...]
            Argument schema for ``Command``/``Query`` paths.
        """
        if not path:
            return
        # First writer wins for {kind, cfx_type}, but later writers
        # may enrich the entry with ``help_text``, ``allowed_values``,
        # or ``arguments`` data not available on first sight.
        existing = self._by_path.get(path)
        if existing is None:
            self._by_path[path] = SchemaNode(
                path=path,
                kind=kind,
                cfx_type=cfx_type,
                help=help_text,
                allowed_values=allowed_values,
                arguments=arguments,
            )
        else:
            new_help = help_text if help_text and not existing.help else existing.help
            new_allowed = existing.allowed_values
            if new_allowed is None and allowed_values is not None:
                new_allowed = allowed_values
            new_args = existing.arguments
            if not new_args and arguments:
                new_args = arguments
            if (
                new_help is not existing.help
                or new_allowed is not existing.allowed_values
                or new_args is not existing.arguments
            ):
                self._by_path[path] = SchemaNode(
                    path=path,
                    kind=existing.kind,
                    cfx_type=existing.cfx_type,
                    help=new_help,
                    allowed_values=new_allowed,
                    arguments=new_args,
                )

        parent, _, leaf = self._split_parent(path)
        if parent is not None:
            self._children.setdefault(parent, set()).add(leaf)

    @staticmethod
    def _split_parent(path: str) -> tuple[str | None, str, str]:
        """Split a schema path into parent path and leaf name.

        Parameters
        ----------
        path : str
            CFX API, object, schema, or file path to process.

        Returns
        -------
        tuple[str | None, str, str]
            Value computed by the helper for the requested CFX workflow.
        """
        depth = 0
        for i in range(len(path) - 1, -1, -1):
            ch = path[i]
            if ch == "]":
                depth += 1
            elif ch == "[":
                depth -= 1
            elif ch == "." and depth == 0:
                return path[:i], ".", path[i + 1 :]
        return None, "", path

    # -- public API -------------------------------------------------------
    def __len__(self) -> int:
        """Return the number of schema paths currently stored in the cache.

        Returns
        -------
        int
            Number of schema entries stored in the cache.
        """
        self._ensure_loaded()
        return len(self._by_path)

    def get(self, path: str) -> SchemaNode | None:
        """Get schema metadata for a CFX API path.

        Parameters
        ----------
        path : str
            Dotted CFX schema path to find. The path may be supplied in display
            form or normalized PyCFX attribute form.

        Returns
        -------
        SchemaNode | None
            Schema metadata for the path when it exists in the cache. Otherwise,
            ``None``.
        """
        self._ensure_loaded()
        node = self._by_path.get(path)
        if node is not None:
            return node
        return self._by_path.get(_normalize_for_lookup(path))

    def exists(self, path: str) -> bool:
        """Return whether a normalized CFX path exists in the schema cache.

        Parameters
        ----------
        path : str
            CFX API, object, schema, or file path to process.

        Returns
        -------
        bool
            Whether the cache contains the requested normalized CFX path.
        """
        return self.get(path) is not None

    def has_allowed_values(self, path: str) -> bool:
        """Return whether the schema declares an explicit value set for ``path``.

        ``True`` when the bundled configuration files attach an
        ``enum``-style allowed-value list to the path or to its
        ``cfx_type`` (such as ``UIMode``). ``False`` for free-form
        primitives (``integer``/``real``/``string``/``boolean``)
        and for paths that the schema does not know.
        """
        node = self.get(path)
        return bool(node and node.has_allowed_values)

    def get_allowed_values(self, path: str) -> tuple[Any, ...] | None:
        """Get the schema-declared allowed values for ``path``.

        Returns ``None`` when no enumeration is known. Callers should
        prefer the live-state probe (``Backend.get_allowed_values``)
        and use this as a fallback for offline/disconnected
        workflows.
        """
        node = self.get(path)
        if node is None or node.allowed_values is None:
            return None
        return node.allowed_values

    def get_command_arguments(self, path: str) -> tuple[CommandArgument, ...]:
        """Get the argument schema for a CFX ``Command``/``Query`` path.

        Returns an empty tuple for non-command paths or for paths
        not present in the cache.
        """
        node = self.get(path)
        if node is None:
            return ()
        return node.arguments

    def children(self, path: str) -> list[str]:
        """Return child schema paths directly under a CFX parent path.

        Parameters
        ----------
        path : str
            Parent CFX schema path whose immediate children should be listed.

        Returns
        -------
        list[str]
            Sorted child paths recorded for the parent, or an empty list when the
            parent is unknown or has no recorded children.
        """
        self._ensure_loaded()
        norm = _normalize_for_lookup(path)
        kids = self._children.get(path) or self._children.get(norm)
        return sorted(kids) if kids else []

    def suggest(self, path: str, *, limit: int = 3) -> list[str]:
        """Suggest close schema paths for an unknown CFX path.

        Parameters
        ----------
        path : str
            Unknown or partially typed CFX schema path to match against known
            entries.
        limit : int, default: 3
            Maximum number of suggested schema paths to return.

        Returns
        -------
        list[str]
            Candidate schema paths ordered by closeness to the requested path.
        """
        self._ensure_loaded()
        norm = _normalize_for_lookup(path)
        if norm in self._by_path:
            return [path]

        # Resolve the longest known prefix, then fuzzy-match the broken leaf
        # against the valid children of that prefix.
        parent, _, leaf = self._split_parent(norm)
        candidates: list[str] = []
        if parent is not None and (parent in self._children or parent in self._by_path):
            child_names = self._children.get(parent, set())
            for match in get_close_matches(leaf, sorted(child_names), n=limit, cutoff=0.6):
                candidates.append(self._join(parent, match))
        if candidates:
            return candidates

        # Fall back to a global fuzzy match on the normalized full path.
        return get_close_matches(norm, list(self._by_path.keys()), n=limit, cutoff=0.6)


@lru_cache(maxsize=1)
def get_schema_cache() -> CFXSchemaCache:
    """Get the process-wide CFX schema cache instance.

    Returns
    -------
    CFXSchemaCache
        Requested CFX data or metadata for the active session.
    """
    cache = CFXSchemaCache()
    cache._ensure_loaded()
    return cache
