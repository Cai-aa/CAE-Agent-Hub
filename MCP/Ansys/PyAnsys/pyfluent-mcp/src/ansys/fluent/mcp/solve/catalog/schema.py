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

"""Static index over PyFluent's canonical ``settings.json`` schema.

The full schema (``setup``/``solution``/``results``/... consists of 77k+ nodes,
including command-argument signatures, query lists, enum-flagged
parameters, and child-aliases). It ships gzipped under
``ansys/fluent/mcp/solve/data/settings_271.json.gz``. PyFluent itself only
ships the slimmer ``api_objects.json`` (path plus kind only) The full
schema is what allows validation of command kwargs, enum strings, and
path/alias resolution **without a live solver**.

The on-disk file is ~0.8 MB gzipped (~11.7 MB uncompressed). Because parsing
the JSON is the expensive step (~150 ms on a recent laptop), the
loader is lazy and lru-cached.

Override the bundled file by setting ``FLUIDS_MCP_SETTINGS_JSON`` to
an absolute path (``.json`` or ``.json.gz``). This is useful for testing a
newer Fluent build before rolling a new vendored snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import gzip
from importlib import resources
import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_VERSION = "271"
_OVERRIDE_ENV = "FLUIDS_MCP_SETTINGS_JSON"


@dataclass(frozen=True)
class CommandArg:
    """One argument of a command or query."""

    name: str  # canonical (kebab-case as in settings.json)
    py_name: str  # snake_case form (what PyFluent accepts in Python)
    type_hint: str  # "string" | "real" | "integer" | "boolean" | "file" | "real-list" | ...
    help: str
    file_purpose: str | None = None  # "input" or "output" for file args


@dataclass(frozen=True)
class CommandSpec:
    """Static signature for a command or query."""

    name: str  # canonical
    py_name: str  # snake_case
    help: str
    arguments: tuple[CommandArg, ...]
    is_query: bool = False

    def arg_names(self) -> list[str]:
        """Return both canonical and snake_case names of every arg.

        Returns
        -------
        list[str]
            Collection containing the operation results.
        """
        out: list[str] = []
        for a in self.arguments:
            out.append(a.py_name)
            if a.name != a.py_name:
                out.append(a.name)
        return out


@dataclass(frozen=True)
class SettingsNode:
    """One node in the settings tree.

    Path uses snake_case dotted notation (e.g.
    ``setup.boundary_conditions.wall``). NamedObject members are
    addressed as ``setup.boundary_conditions.wall["<name>"]`` by the
    caller; the lookup helpers below transparently descend through
    the schema's ``object-type`` envelope.
    """

    path: str  # snake_case dotted
    kind: str  # group | named-object | list-object | string | real | integer | boolean | file | ...
    help: str
    child_names: tuple[str, ...]  # snake_case
    commands: dict[str, CommandSpec]  # keyed by snake_case
    queries: dict[str, CommandSpec]  # keyed by snake_case
    has_allowed_values: bool
    user_creatable: bool  # only meaningful when kind == "named-object"
    aliases: dict[str, str]  # alias name (snake) -> target path (snake)


def _kebab_to_snake(s: str) -> str:
    # Fluent marks boolean parameters with a trailing ``?`` in the
    # schema (``enable?``, ``enabled?``, ``frozen_flux?``, ...).
    # PyFluent strips it for the Python attribute, so callers always
    # spell the path without ``?``. Normalise here so both forms hit
    # the same index entry.
    """Convert a kebab-case name to snake_case.

    Parameters
    ----------
    s : str
        S to supply to the function.

    Returns
    -------
    str
        String value produced by the helper.
    """
    if s.endswith("?"):
        s = s[:-1]
    return s.replace("-", "_")


def _normalise_path(path: str) -> str:
    """Normalise a Fluent object path to snake_case dotted notation.

    Strip ``solver.settings.`` prefix, convert kebab to snake, drop
    bracketed named-object keys (the static schema has no per-name
    facts; the member shape is what matters).

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
    p = path.strip()
    for prefix in ("solver.settings.", "settings."):
        if p.startswith(prefix):
            p = p[len(prefix) :]
            break
    # Drop ["..."] / ['...'] member selectors.
    out_parts: list[str] = []
    for raw in p.split("."):
        if not raw:
            continue
        # split off bracketed parts: cell_zone_conditions["fluid-1"] → cell_zone_conditions
        bracket = raw.find("[")
        if bracket >= 0:
            raw = raw[:bracket]
        out_parts.append(_kebab_to_snake(raw))
    return ".".join(out_parts)


def _locate_default_data() -> Path | None:
    """Find the bundled gzipped schema, returning ``None`` if missing.

    Returns
    -------
    Path | None
        Result produced by the function.
    """
    name = f"settings_{_DEFAULT_VERSION}.json.gz"
    try:
        res = resources.files("ansys.fluent.mcp.solve.data").joinpath(name)
        # On editable installs ``res`` is a Path-like; ``is_file`` works
        # in both ``zipfile.Path`` and ``pathlib.Path`` flavours.
        if res.is_file():
            return Path(str(res))
    except (ModuleNotFoundError, AttributeError, FileNotFoundError):
        pass
    return None


def _load_raw(path: Path) -> dict[str, Any]:
    """Load raw.

    Parameters
    ----------
    path : Path
        Filesystem path or API path to process.

    Returns
    -------
    dict[str, Any]
        Mapping containing the operation result.
    """
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rb") as fh:
        return json.load(fh)


def _build_command_spec(name: str, raw: dict[str, Any], *, is_query: bool) -> CommandSpec:
    """Build command spec.

    Parameters
    ----------
    name : str
        Name of the object, module, or setting being processed.
    raw : dict[str, Any]
        Raw string value to parse or validate.
    is_query : bool
        Whether to enable or apply is query.

    Returns
    -------
    CommandSpec
        CommandSpec produced by the operation.
    """
    args: list[CommandArg] = []
    for arg_name, arg_raw in (raw.get("arguments") or {}).items():
        if not isinstance(arg_raw, dict):
            continue
        args.append(
            CommandArg(
                name=arg_name,
                py_name=_kebab_to_snake(arg_name),
                type_hint=str(arg_raw.get("type") or ""),
                help=str(arg_raw.get("help") or ""),
                file_purpose=arg_raw.get("file-purpose"),
            )
        )
    return CommandSpec(
        name=name,
        py_name=_kebab_to_snake(name),
        help=str(raw.get("help") or ""),
        arguments=tuple(args),
        is_query=is_query,
    )


class SettingsSchema:
    """Indexed view over the static settings schema.

    Indexing is built once at construction. Resolution is
    ``O(depth)`` over the snake_case path components, with kebab and
    snake spellings accepted interchangeably.
    """

    def __init__(self, raw: dict[str, Any], *, source: str = "<bundled>") -> None:
        """Initialize the SettingsSchema instance.

        Parameters
        ----------
        raw : dict[str, Any]
            Raw string value to parse or validate.
        source : str
            Source to supply to the function.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        self._raw = raw
        self._source = source
        # Flat index by snake_case path.
        self._by_path: dict[str, SettingsNode] = {}
        # Member-of (path → snake_case path of element schema, e.g.
        # "setup.boundary_conditions.wall" → "setup.boundary_conditions.wall.<member>").
        self._member_of: dict[str, str] = {}
        self._build_index(raw, path="")

    # ----------------------------------------------------------------
    # public API
    # ----------------------------------------------------------------
    @property
    def source(self) -> str:
        """Return the source associated with the catalog node.

        Returns
        -------
        str
            String value produced by the helper.
        """
        return self._source

    @property
    def node_count(self) -> int:
        """Return the number of nodes in the catalog tree.

        Returns
        -------
        int
            Configured integer limit used by the helper.
        """
        return len(self._by_path)

    def resolve(self, path: str) -> SettingsNode | None:
        """Resolve a snake_case (or kebab-case) dotted path.

        Bracketed member selectors (``...wall["w1"]``) are stripped
        and the schema descends through the NamedObject's element
        envelope automatically — so
        ``resolve("setup.boundary_conditions.wall.thermal")`` returns
        the *element-level* node for wall thermal, not the container.

        Dot-form member keys are also supported:
        ``solution.controls.under_relaxation.pressure`` resolves to
        the ``under_relaxation`` member envelope (Fluent rejects new
        keys here at runtime, but the schema can't know which keys
        the user has created — so we accept any token after a
        NamedObject as a member-key access).

        Parameters
        ----------
        path : str
            Fluent object path or file-system path to inspect.

        Returns
        -------
        SettingsNode | None
            Collection containing the operation results.
        """
        norm = _normalise_path(path)
        if not norm:
            return self._by_path.get("")
        node = self._by_path.get(norm)
        if node is not None:
            return node
        parts = norm.split(".")
        cur = ""
        i = 0
        while i < len(parts):
            part = parts[i]
            candidate = f"{cur}.{part}" if cur else part
            if candidate in self._by_path:
                cur = candidate
                i += 1
                continue
            member = self._member_of.get(cur)
            if member is not None:
                via = f"{member}.{part}"
                if via in self._by_path:
                    cur = via
                    i += 1
                    continue
                # ``part`` is a member key (e.g. "pressure" under
                # ``under_relaxation``). Move into the member envelope
                # and consume the key; subsequent parts apply to it.
                cur = member
                i += 1
                continue
            return None
        return self._by_path.get(cur)

    def lookup_command(self, path: str) -> CommandSpec | None:
        """Resolve a command call path like ``solution.run_calculation.iterate``.

        Splits the trailing segment as the command name and looks it
        up on the parent node's ``commands`` (then ``queries`` as a
        fallback).

        Parameters
        ----------
        path : str
            Fluent object path or file-system path to inspect.

        Returns
        -------
        CommandSpec | None
            Result produced by the function.
        """
        norm = _normalise_path(path)
        if "." not in norm:
            return None
        parent, last = norm.rsplit(".", 1)
        node = self.resolve(parent)
        if node is None:
            return None
        cmd = node.commands.get(last)
        if cmd is not None:
            return cmd
        return node.queries.get(last)

    # ----------------------------------------------------------------
    # build
    # ----------------------------------------------------------------
    def _build_index(self, raw: dict[str, Any], path: str) -> None:
        """Build index.

        Parameters
        ----------
        raw : dict[str, Any]
            Raw string value to parse or validate.
        path : str
            Filesystem path or API path to process.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        kind = str(raw.get("type") or "")
        children_raw = raw.get("children") or {}
        child_names_snake: list[str] = sorted(_kebab_to_snake(k) for k in children_raw)
        commands_raw = raw.get("commands") or {}
        queries_raw = raw.get("queries") or {}
        commands: dict[str, CommandSpec] = {}
        for cname, craw in commands_raw.items():
            if not isinstance(craw, dict):
                continue
            spec = _build_command_spec(cname, craw, is_query=False)
            commands[spec.py_name] = spec
        queries: dict[str, CommandSpec] = {}
        for qname, qraw in queries_raw.items():
            if not isinstance(qraw, dict):
                continue
            spec = _build_command_spec(qname, qraw, is_query=True)
            queries[spec.py_name] = spec
        aliases_raw = raw.get("child-aliases") or {}
        aliases: dict[str, str] = {}
        for an, target in aliases_raw.items():
            if not isinstance(target, str):
                continue
            aliases[_kebab_to_snake(an)] = _kebab_to_snake(target)
        node = SettingsNode(
            path=path,
            kind=kind,
            help=str(raw.get("help") or ""),
            child_names=tuple(child_names_snake),
            commands=commands,
            queries=queries,
            has_allowed_values=bool(raw.get("has-allowed-values")),
            user_creatable=bool(raw.get("user-creatable?")),
            aliases=aliases,
        )
        self._by_path[path] = node
        # Recurse into children.
        for cname, craw in children_raw.items():
            if not isinstance(craw, dict):
                continue
            cpath = f"{path}.{_kebab_to_snake(cname)}" if path else _kebab_to_snake(cname)
            self._build_index(craw, cpath)
        # Recurse into named/list-object element schema (``object-type``).
        elem = raw.get("object-type")
        if isinstance(elem, dict):
            member_path = f"{path}.<member>" if path else "<member>"
            self._member_of[path] = member_path
            self._build_index(elem, member_path)


# ----------------------------------------------------------------------
# module-level loader
# ----------------------------------------------------------------------
@lru_cache(maxsize=4)
def load_settings_schema(version: str = _DEFAULT_VERSION) -> SettingsSchema | None:
    """Load the schema for a version. Currently only ``"271"`` is bundled.

    Honors ``FLUIDS_MCP_SETTINGS_JSON`` for ad-hoc overrides. Returns
    ``None`` (and logs at INFO) if no schema can be located. Callers
    must treat schema-based checks as best-effort.

    Parameters
    ----------
    version : str
        Version to supply to the function.

    Returns
    -------
    SettingsSchema | None
        Collection containing the operation results.
    """
    override = os.getenv(_OVERRIDE_ENV)
    src_path: Path | None = None
    if override:
        cand = Path(override)
        if cand.is_file():
            src_path = cand
        else:
            logger.warning("%s set but file missing: %s", _OVERRIDE_ENV, override)
    if src_path is None and version == _DEFAULT_VERSION:
        src_path = _locate_default_data()
    if src_path is None:
        logger.info("settings schema not located for version %s; static checks disabled", version)
        return None
    try:
        raw = _load_raw(src_path)
    except Exception as exc:
        logger.warning("failed to read settings schema %s: %s", src_path, exc)
        return None
    return SettingsSchema(raw, source=str(src_path))
