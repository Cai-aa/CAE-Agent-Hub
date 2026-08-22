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

"""Live-schema probe tools.

The MCP leaf used to keep these primitives backend-private — agents
that ran outside the in-process leaf could call ``get_state`` /
``run_code`` and infer the same information one round-trip at a
time, but they could not directly ask "is this path active?",
"what allowed values does this enum take?", "does this NamedObject
template require a name argument?" or "does this path even exist
in the schema?". That gap meant external MCP clients (Cursor, VS
Code Copilot, Claude Desktop) had to write defensive ``try/except``
around every write and discovered violations only after Fluent
raised an opaque ``api-set-var``.

This module exposes those primitives as five domain tools:

* ``probe_path`` — batch ``{exists, is_active, is_user_creatable, kind}``
* ``get_active_status`` — batch ``{path: bool}``
* ``get_allowed_values`` — batch ``{path: [...]}``
* ``describe_named_object_template`` — single-path template fetch
* ``describe_path`` — unified batch :class:`PathDescriptor` (composes the
  four primitives above into one envelope per path)

The four primitive implementations are thin wrappers around the
corresponding :class:`Backend` methods so the leaf and the agent share
the same contract. ``describe_path`` fuses them so external MCP clients
don't have to stitch payloads together. All five are read-only /
introspective — they never mutate the live session.
"""

from __future__ import annotations

from typing import Any

from ansys.fluent.mcp.common.backend import Backend, BackendUnavailableError
from ansys.fluent.mcp.common.path_descriptor import PathDescriptor


async def probe_path_impl(
    backend: Backend,
    *,
    paths: list[str],
) -> dict[str, Any]:
    """Batch pre-flight probe for a list of settings paths.

    Returns ``{path: {exists, is_active, is_user_creatable, kind}}``
    in a single round-trip. Backends without a live session raise
    :class:`BackendUnavailableError`; the wrapper surfaces that as
    a structured error so callers can pivot to ``get_state`` or
    ``find_api`` without burning a turn.

    Parameters
    ----------
    paths
        One or more Fluent settings paths to probe. Bracket-indexed
        paths (``solution.controls.under_relaxation[pressure]``) are
        accepted in addition to plain paths.

    Returns
    -------
    dict[str, Any]
        ``{"connected": True, "results": {<path>: {...}}, "status": "ok"}``
        on success, or ``{"connected": ..., "status": "error",
        "error_code": "...", "message": "..."}`` on failure.
    """
    if not isinstance(paths, list) or not paths:
        return {
            "status": "error",
            "error_code": "invalid_arguments",
            "message": "`paths` must be a non-empty list of strings.",
        }
    if not backend.is_connected():
        return {
            "connected": False,
            "status": "error",
            "error_code": "no_session",
            "message": "no live session; connect Fluent first.",
        }
    try:
        results = await backend.probe_path([str(p) for p in paths])
    except BackendUnavailableError as exc:
        return {
            "connected": True,
            "status": "error",
            "error_code": "backend_unavailable",
            "message": str(exc),
        }
    except Exception as exc:  # noqa: BLE001 — backend probe must surface to callers
        return {
            "connected": True,
            "status": "error",
            "error_code": "probe_failed",
            "message": str(exc),
        }
    return {"connected": True, "status": "ok", "results": dict(results or {})}


async def get_active_status_impl(
    backend: Backend,
    *,
    paths: list[str],
) -> dict[str, Any]:
    """Batch active-status probe.

    Returns ``{path: bool}`` per requested path. Inactive paths
    cannot be written to — Fluent either silently ignores the
    assignment or raises ``InactiveObjectError``. Use this before
    proposing a write to a path that is gated by another model
    (``setup.models.viscous.k_omega_model`` is inactive unless
    ``viscous.model='k-omega'``, ``solution.controls.p_v_controls
    .explicit_pressure_under_relaxation`` is inactive under
    SIMPLE / SIMPLEC / PISO, etc.).

    Parameters
    ----------
    paths
        One or more Fluent settings paths to probe.

    Returns
    -------
    dict[str, Any]
        ``{"connected": True, "status": "ok", "results": {path: bool}}``
        on success.
    """
    if not isinstance(paths, list) or not paths:
        return {
            "status": "error",
            "error_code": "invalid_arguments",
            "message": "`paths` must be a non-empty list of strings.",
        }
    if not backend.is_connected():
        return {
            "connected": False,
            "status": "error",
            "error_code": "no_session",
            "message": "no live session; connect Fluent first.",
        }
    try:
        results = await backend.get_active_status([str(p) for p in paths])
    except BackendUnavailableError as exc:
        return {
            "connected": True,
            "status": "error",
            "error_code": "backend_unavailable",
            "message": str(exc),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "connected": True,
            "status": "error",
            "error_code": "probe_failed",
            "message": str(exc),
        }
    return {
        "connected": True,
        "status": "ok",
        "results": {k: bool(v) for k, v in (results or {}).items()},
    }


async def get_allowed_values_impl(
    backend: Backend,
    *,
    paths: list[str],
) -> dict[str, Any]:
    """Batch allowed-values probe.

    Returns ``{path: [allowed, values, ...]}`` for paths that are
    enum-style (``setup.models.viscous.model``,
    ``setup.boundary_conditions.wall["foo"].thermal.thermal_condition``,
    discretization schemes, ...). Returns an empty list for paths
    that have no allowed-values constraint. Use BEFORE writing to
    an enum field so callers can pick a value from the live set
    instead of guessing.

    Parameters
    ----------
    paths
        One or more Fluent settings paths.

    Returns
    -------
    dict[str, Any]
        ``{"connected": True, "status": "ok", "results": {path: list}}``.
    """
    if not isinstance(paths, list) or not paths:
        return {
            "status": "error",
            "error_code": "invalid_arguments",
            "message": "`paths` must be a non-empty list of strings.",
        }
    if not backend.is_connected():
        return {
            "connected": False,
            "status": "error",
            "error_code": "no_session",
            "message": "no live session; connect Fluent first.",
        }
    try:
        results = await backend.get_allowed_values([str(p) for p in paths])
    except BackendUnavailableError as exc:
        return {
            "connected": True,
            "status": "error",
            "error_code": "backend_unavailable",
            "message": str(exc),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "connected": True,
            "status": "error",
            "error_code": "probe_failed",
            "message": str(exc),
        }
    out: dict[str, list[Any]] = {}
    for k, v in (results or {}).items():
        try:
            out[k] = list(v) if v is not None else []
        except TypeError:
            out[k] = []
    return {"connected": True, "status": "ok", "results": out}


async def describe_named_object_template_impl(
    backend: Backend,
    *,
    path: str,
) -> dict[str, Any]:
    """Describe the field shape of a NamedObject collection's child.

    For a NamedObject family (boundary_conditions.velocity_inlet,
    solution.report_definitions.surface, materials.fluid, ...) this
    returns the per-field metadata needed to construct a valid
    create / update payload:

    * ``child_class`` — name of the child class (Group / scalar leaf)
    * ``fields`` — a mapping of ``field_name`` to its metadata
      (``type_hint``, ``is_active``, ``is_read_only``,
      ``is_user_creatable``, ``allowed_values``, ``min``, ``max``,
      ``default``, ``units``)
    * ``is_active`` — whether the collection itself is active
    * ``is_user_creatable`` — whether ``.create()`` may be called
    * ``create_command`` — ``{"argument_names": [...]}`` if a
      create command exists

    Use BEFORE proposing a ``set_named`` step to learn which fields
    are required, read-only, or have allowed_values constraints.

    Parameters
    ----------
    path
        Fluent collection path (no bracket key — that's appended
        automatically when the template is consulted for a child).

    Returns
    -------
    dict[str, Any]
        ``{"connected": True, "status": "ok", "template": {...}}`` on
        success. ``template`` is ``None`` if the backend cannot
        introspect or the path is not a NamedObject collection.
    """
    if not isinstance(path, str) or not path:
        return {
            "status": "error",
            "error_code": "invalid_arguments",
            "message": "`path` must be a non-empty string.",
        }
    if not backend.is_connected():
        return {
            "connected": False,
            "status": "error",
            "error_code": "no_session",
            "message": "no live session; connect Fluent first.",
        }
    try:
        template = await backend.describe_named_object_template(path)
    except BackendUnavailableError as exc:
        return {
            "connected": True,
            "status": "error",
            "error_code": "backend_unavailable",
            "message": str(exc),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "connected": True,
            "status": "error",
            "error_code": "probe_failed",
            "message": str(exc),
        }
    return {
        "connected": True,
        "status": "ok",
        "template": template if isinstance(template, dict) else None,
    }


async def describe_path_impl(
    backend: Backend,
    *,
    paths: list[str],
    include_template: bool = True,
    include_command_arguments: bool = True,
) -> dict[str, Any]:
    """Batch unified path-descriptor probe.

    Composes ``probe_path`` + ``get_allowed_values`` (+ optionally
    ``describe_named_object_template`` + ``get_command_arguments``) into
    a single :class:`PathDescriptor` per input path so external MCP
    clients don't have to stitch four disparate probe payloads
    together to reason about a Fluent settings path.

    Returns ``{path: PathDescriptor.to_dict()}``. Fields default to
    ``None`` (meaning "unknown / unavailable") rather than to
    sentinels a caller might misread — an empty ``allowed_values``
    list carries "backend explicitly reports no allowed values",
    whereas ``None`` carries "we did not probe / the probe failed".

    The composition is fail-soft: if the allowed-values probe raises
    for one path, the descriptor for that path just gets
    ``allowed_values=None`` and the batch still succeeds. Only a
    hard failure of ``probe_path`` (which drives ``exists`` /
    ``is_active`` / ``kind``) surfaces a top-level error.

    Parameters
    ----------
    paths
        One or more Fluent settings paths to describe.
    include_template
        When True (default) and a path is a NamedObject collection,
        fold in :meth:`Backend.describe_named_object_template`.
    include_command_arguments
        When True (default) and a path is a Command, fold in
        :meth:`Backend.get_command_arguments`.

    Returns
    -------
    dict[str, Any]
        ``{"connected": True, "status": "ok", "results": {path:
        <PathDescriptor.to_dict()>}}`` on success.
    """
    if not isinstance(paths, list) or not paths:
        return {
            "status": "error",
            "error_code": "invalid_arguments",
            "message": "`paths` must be a non-empty list of strings.",
        }
    if not backend.is_connected():
        return {
            "connected": False,
            "status": "error",
            "error_code": "no_session",
            "message": "no live session; connect Fluent first.",
        }

    string_paths = [str(p) for p in paths]

    try:
        probes = await backend.probe_path(string_paths)
    except BackendUnavailableError as exc:
        return {
            "connected": True,
            "status": "error",
            "error_code": "backend_unavailable",
            "message": str(exc),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "connected": True,
            "status": "error",
            "error_code": "probe_failed",
            "message": str(exc),
        }

    # Allowed-values (soft — a per-path failure yields None on that entry)
    allowed_by_path: dict[str, list[Any] | None] = {p: None for p in string_paths}
    try:
        av = await backend.get_allowed_values(string_paths)
        for k, v in (av or {}).items():
            try:
                allowed_by_path[k] = list(v) if v is not None else None
            except TypeError:
                allowed_by_path[k] = None
    except Exception:  # noqa: BLE001
        # Fail-soft: a backend that cannot report allowed-values leaves
        # every entry at None (its initialised default) so the batch
        # still succeeds. See the composition contract in the module
        # docstring.
        allowed_by_path = {p: None for p in string_paths}

    # Templates (soft — only invoked for NamedObject-kind paths)
    templates_by_path: dict[str, dict[str, Any] | None] = {}
    if include_template:
        for p in string_paths:
            info = (probes or {}).get(p) or {}
            kind = info.get("kind")
            if kind in ("NamedObject", "NamedObjectContainer", "ListObject"):
                try:
                    tmpl = await backend.describe_named_object_template(p)
                    templates_by_path[p] = tmpl if isinstance(tmpl, dict) else None
                except Exception:  # noqa: BLE001
                    templates_by_path[p] = None

    # Command arguments (soft — only invoked for Command-kind paths)
    commands_by_path: dict[str, dict[str, Any] | None] = {}
    if include_command_arguments:
        for p in string_paths:
            info = (probes or {}).get(p) or {}
            kind = info.get("kind")
            if kind in ("Command", "Action"):
                try:
                    args = await backend.get_command_arguments(p)
                    commands_by_path[p] = args if isinstance(args, dict) else None
                except Exception:  # noqa: BLE001
                    commands_by_path[p] = None

    results: dict[str, Any] = {}
    for p in string_paths:
        desc = PathDescriptor.from_probe(
            p,
            (probes or {}).get(p),
            allowed_values=allowed_by_path.get(p),
            template=templates_by_path.get(p),
            command_arguments=commands_by_path.get(p),
        )
        results[p] = desc.to_dict()

    return {"connected": True, "status": "ok", "results": results}


__all__ = [
    "describe_named_object_template_impl",
    "describe_path_impl",
    "get_active_status_impl",
    "get_allowed_values_impl",
    "probe_path_impl",
]
