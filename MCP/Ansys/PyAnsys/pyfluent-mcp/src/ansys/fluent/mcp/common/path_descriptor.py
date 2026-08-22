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

"""Unified discovery envelope for Fluent settings paths.

Before this module the leaf published four separate probes
(``probe_path``, ``get_active_status``, ``get_allowed_values``,
``describe_named_object_template``) plus a couple of higher-level tools
(``find_api``, ``get_targeted_context``) and every one of them returned
a *different* payload shape. Validators, recipe grounders, and tool-call
handlers all built their own view of a
path by stitching those envelopes together, and each stitching layer
disagreed with the others on edge cases:

* ``probe_path`` returned ``kind='NamedObject'`` while
  ``describe_named_object_template`` returned ``child_class='<class
  name>'`` — callers had to know both.
* ``get_allowed_values`` returned ``[...]`` for a bounded enum, ``None``
  for a free-form string, ``None`` for a missing path, and raised for
  a mode-pruned path. Those three ``None`` cases had different semantics
  and the caller had to disambiguate by calling ``probe_path`` first.
* Commands (``kind='Command'``) had no unified way to publish their
  keyword-argument signature; only the live PyFluent backend's
  ``get_command_arguments`` accessor knew them, and it was invoked
  ad-hoc.

:class:`PathDescriptor` collapses all of that into one frozen dataclass
that every discovery tool, every validator guard, and every recipe
grounder consumes. Fields default to ``None`` (meaning "unknown /
unavailable"), never to a sentinel like ``[]`` that a caller might
misread as "empty allowed set".

The envelope is DELIBERATELY additive to the existing tools — the
per-probe responses still ship their historical shape so nothing on
the wire breaks, and :class:`PathDescriptor` is composed on top from
those responses via :meth:`PathDescriptor.from_batch`.

Example
-------
::

    from ansys.fluent.mcp.common.path_descriptor import PathDescriptor

    desc = PathDescriptor(
        path="setup.models.viscous.model",
        kind="Parameter",
        exists=True,
        is_active=True,
        allowed_values=(
            "laminar",
            "inviscid",
            "k-epsilon",
            "k-omega",
            "les",
            "des",
            "reynolds-stress",
            "transition-sst",
            "spalart-allmaras",
        ),
    )
    assert desc.is_bounded_enum
    assert "k-omega" in desc.allowed_values
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

# Kinds recognized by the descriptor. Aligned with the values Fluent's
# settings-API introspection returns for ``obj.__class__.__name__``
# grouped into families the validator can reason about.
_PARAMETER_KINDS: frozenset[str] = frozenset(
    {
        "Parameter",
        "String",
        "Integer",
        "Real",
        "RealList",
        "IntegerList",
        "StringList",
        "Boolean",
        "Filename",
        "FilenameList",
        "Vector",
    }
)
_GROUP_KINDS: frozenset[str] = frozenset({"Group"})
_NAMED_OBJECT_KINDS: frozenset[str] = frozenset(
    {"NamedObject", "NamedObjectContainer", "Named", "ListObject"}
)
_COMMAND_KINDS: frozenset[str] = frozenset({"Command", "Action"})
_QUERY_KINDS: frozenset[str] = frozenset({"Query", "QueryObject"})


@dataclass(frozen=True)
class CommandArgument:
    """Single keyword argument of a Fluent settings command.

    Populated from :meth:`Backend.get_command_arguments` — the live
    solver reports ``argument_names`` (ordered list) and ``arguments``
    (per-name descriptor). The offline schema in
    ``settings_271.json.gz`` carries the same information under
    ``args`` on command nodes.
    """

    name: str
    kind: str | None = None
    required: bool = False
    default: Any = None
    allowed_values: tuple[Any, ...] | None = None
    docstring: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe dict shape."""
        return {
            "name": self.name,
            "kind": self.kind,
            "required": self.required,
            "default": self.default,
            "allowed_values": (
                list(self.allowed_values) if self.allowed_values is not None else None
            ),
            "docstring": self.docstring,
        }


@dataclass(frozen=True)
class PathDescriptor:
    """One-envelope description of a Fluent settings path.

    Every field defaults to ``None`` / empty so a partially known path
    (e.g. schema-only, no live backend) still serializes cleanly. The
    invariant callers rely on: **if a field is non-None it reflects a
    real live probe result** — the composition path never fabricates
    defaults for missing information.

    Callers must not compare with ``!=`` for equality on inequal live
    snapshots — the frozen contract only guarantees value equality of
    the exact fields present. Use :meth:`to_dict` for round-trip
    persistence.
    """

    #: Fully qualified settings path (e.g. ``setup.models.energy.enabled``).
    path: str

    #: One of ``Parameter`` (leaf value) / ``Group`` (container of
    #: fields) / ``NamedObject`` (indexed collection) / ``Command`` /
    #: ``Query`` — or ``None`` when the kind couldn't be determined.
    kind: str | None = None

    #: True iff the path resolves against the loaded schema and the
    #: live tree. ``None`` means unknown (schema-only lookup).
    exists: bool | None = None

    #: True iff the path is currently ACTIVE — i.e. not gated out by
    #: solver mode / physics / UTL. ``None`` means unknown.
    is_active: bool | None = None

    #: True iff a fresh child can be created under this path
    #: (NamedObject with a public ``create()`` command). ``None`` for
    #: non-collection paths.
    is_user_creatable: bool | None = None

    #: True iff the path is a read-only leaf (or a read-only field of
    #: a NamedObject template). Writes to a read-only path must be
    #: hard-blocked by the validator.
    is_read_only: bool | None = None

    #: For NamedObject collections: the child class name (as reported
    #: by ``describe_named_object_template``). ``None`` for
    #: non-collection paths.
    child_class: str | None = None

    #: For NamedObject collections: the fields of a fresh child
    #: ``{field_name: {"kind": ..., "is_read_only": ..., ...}}``.
    #: ``None`` when the backend cannot introspect templates.
    child_fields: tuple[str, ...] | None = None

    #: For bounded-enum leaves: the exhaustive allowed value set.
    #: ``None`` for free-form leaves and for paths the probe couldn't
    #: reach. An empty tuple means "the backend reports NO allowed
    #: values" — extremely rare (usually a live-state bug).
    allowed_values: tuple[Any, ...] | None = None

    #: For numeric leaves: the closed range ``[min, max]``. Fields are
    #: ``None`` when either bound is unset.
    min_value: float | None = None
    max_value: float | None = None

    #: For commands: the ordered keyword-argument signature.
    command_arguments: tuple[CommandArgument, ...] | None = None

    #: Some settings live at TWO physical paths whose active one
    #: depends on the live UTL flag (``setup.boundary_conditions.*``
    #: vs ``setup.physics.boundaries.*``). This field carries the
    #: sibling path when the current mode makes THIS path inactive.
    #: ``None`` when the path has no UTL twin.
    utl_alternate_path: str | None = None

    #: For BC / cell-zone leaves on a multiphase case: the per-phase
    #: path the caller should write instead
    #: (``...phase['<ph>'].multiphase.<leaf>.value``). ``None`` when
    #: the path is single-phase or the caller hasn't supplied phase
    #: context.
    multiphase_alternate_path: str | None = None

    #: Free-form notes surfaced to clients (e.g. ``"only writable
    #: after energy=on"``). Never load-bearing.
    notes: tuple[str, ...] = field(default_factory=tuple)

    # ------------------------------------------------------------------
    # Convenience predicates
    # ------------------------------------------------------------------

    @property
    def is_parameter(self) -> bool:
        """True iff the path is a leaf value (writable via ``set``)."""
        return self.kind in _PARAMETER_KINDS

    @property
    def is_group(self) -> bool:
        """True iff the path is a container of fields."""
        return self.kind in _GROUP_KINDS

    @property
    def is_named_object(self) -> bool:
        """True iff the path is an indexed NamedObject collection."""
        return self.kind in _NAMED_OBJECT_KINDS

    @property
    def is_command(self) -> bool:
        """True iff the path is a callable command."""
        return self.kind in _COMMAND_KINDS

    @property
    def is_bounded_enum(self) -> bool:
        """True iff this leaf accepts a bounded set of allowed values."""
        return bool(self.allowed_values)

    @property
    def has_utl_alternate(self) -> bool:
        """True iff a UTL-mode sibling path exists for this setting."""
        return bool(self.utl_alternate_path)

    def value_is_allowed(self, value: Any) -> bool | None:
        """Return True/False if ``value`` is in the allowed set; None if unknown.

        Comparison is exact for numerics/booleans and
        case-insensitive-strip for strings, matching Fluent's
        settings-API tolerance on enum spellings.
        """
        if not self.allowed_values:
            return None
        for candidate in self.allowed_values:
            if candidate is value or candidate == value:
                return True
            if (
                isinstance(candidate, str)
                and isinstance(value, str)
                and candidate.strip().lower() == value.strip().lower()
            ):
                return True
        return False

    def value_is_in_range(self, value: Any) -> bool | None:
        """Return True/False if numeric ``value`` is within [min, max]; None if unknown."""
        if self.min_value is None and self.max_value is None:
            return None
        try:
            v = float(value)
        except (TypeError, ValueError):
            return None
        if self.min_value is not None and v < self.min_value:
            return False
        if self.max_value is not None and v > self.max_value:
            return False
        return True

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe dict of the descriptor."""
        return {
            "path": self.path,
            "kind": self.kind,
            "exists": self.exists,
            "is_active": self.is_active,
            "is_user_creatable": self.is_user_creatable,
            "is_read_only": self.is_read_only,
            "child_class": self.child_class,
            "child_fields": (list(self.child_fields) if self.child_fields is not None else None),
            "allowed_values": (
                list(self.allowed_values) if self.allowed_values is not None else None
            ),
            "min_value": self.min_value,
            "max_value": self.max_value,
            "command_arguments": (
                [a.to_dict() for a in self.command_arguments]
                if self.command_arguments is not None
                else None
            ),
            "utl_alternate_path": self.utl_alternate_path,
            "multiphase_alternate_path": self.multiphase_alternate_path,
            "notes": list(self.notes),
        }

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------

    @classmethod
    def from_probe(
        cls,
        path: str,
        probe: Mapping[str, Any] | None = None,
        *,
        allowed_values: Iterable[Any] | None = None,
        template: Mapping[str, Any] | None = None,
        command_arguments: Mapping[str, Any] | None = None,
        utl_alternate_path: str | None = None,
        multiphase_alternate_path: str | None = None,
        notes: Iterable[str] | None = None,
    ) -> "PathDescriptor":
        """Compose a descriptor from the four legacy probe payloads.

        ``probe`` is the ``probe_path`` response (
        ``{exists, is_active, is_user_creatable, kind}``).
        ``allowed_values`` is the ``get_allowed_values`` response
        (``None`` or a list). ``template`` is the
        ``describe_named_object_template`` response
        (``{child_class, fields, is_active, is_user_creatable,
        create_command}``). ``command_arguments`` is the
        ``get_command_arguments`` response
        (``{argument_names, arguments}``).

        Every source is optional; missing sources leave the
        corresponding descriptor fields as ``None``.
        """
        p = probe or {}

        kind = p.get("kind")
        exists = p.get("exists")
        is_active = p.get("is_active")
        is_user_creatable = p.get("is_user_creatable")
        is_read_only = p.get("is_read_only")

        # NamedObject template (child class / field list / creatable flag override)
        child_class: str | None = None
        child_fields: tuple[str, ...] | None = None
        if template:
            child_class = template.get("child_class") or None
            fields = template.get("fields")
            if isinstance(fields, dict):
                child_fields = tuple(str(k) for k in fields.keys())
            elif isinstance(fields, (list, tuple)):
                child_fields = tuple(str(f) for f in fields)
            if is_user_creatable is None and "is_user_creatable" in template:
                is_user_creatable = template.get("is_user_creatable")
            if is_active is None and "is_active" in template:
                is_active = template.get("is_active")

        # Allowed values — ``None`` means unknown, ``[]`` means backend
        # returned an empty allowed set. We preserve the distinction.
        av: tuple[Any, ...] | None
        if allowed_values is None:
            av = None
        else:
            try:
                av = tuple(allowed_values)
            except TypeError:
                av = None

        # Command args
        cmd_args: tuple[CommandArgument, ...] | None = None
        if command_arguments:
            names = command_arguments.get("argument_names") or []
            arg_specs = command_arguments.get("arguments") or {}
            if isinstance(names, (list, tuple)):
                built: list[CommandArgument] = []
                for n in names:
                    spec = arg_specs.get(n) if isinstance(arg_specs, dict) else None
                    spec = spec or {}
                    av_arg = spec.get("allowed_values")
                    built.append(
                        CommandArgument(
                            name=str(n),
                            kind=spec.get("kind"),
                            required=bool(spec.get("required", False)),
                            default=spec.get("default"),
                            allowed_values=(
                                tuple(av_arg) if isinstance(av_arg, (list, tuple)) else None
                            ),
                            docstring=spec.get("docstring") or spec.get("help"),
                        )
                    )
                cmd_args = tuple(built)

        return cls(
            path=path,
            kind=kind,
            exists=exists,
            is_active=is_active,
            is_user_creatable=is_user_creatable,
            is_read_only=is_read_only,
            child_class=child_class,
            child_fields=child_fields,
            allowed_values=av,
            min_value=p.get("min_value"),
            max_value=p.get("max_value"),
            command_arguments=cmd_args,
            utl_alternate_path=utl_alternate_path,
            multiphase_alternate_path=multiphase_alternate_path,
            notes=tuple(notes) if notes else (),
        )

    @classmethod
    def unknown(cls, path: str) -> "PathDescriptor":
        """Return a descriptor that carries only the path (everything else None)."""
        return cls(path=path)


__all__ = [
    "PathDescriptor",
    "CommandArgument",
]
