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

"""Shared, stateless implementation for the ``compare_files`` tool.

This module owns the pure-domain pieces of the ``compare_files`` tool:

* An ephemeral PyFluent backend factory
* A deterministic snapshot collection over the ``Backend`` contract
* A recursive dictionary diff with stable named-object handling
* Compact rendering helpers used by the markdown summary

The leaf-side ``DomainTool`` entry point is
:func:`compare_files_impl`. The agent's in-process handler delegates
to the same coroutine so both surfaces share one source of truth.

There is **no** ``state`` parameter and no reference to ``LoopState``
on purpose. By the time this module is reached, all path validation
and same-file checks have already passed in :func:`compare_files_impl`
itself, using only the public :mod:`ansys.fluent.mcp.common.file_handlers`
registry. The handler spawns its own ephemeral sessions so the live
workspace (if any) is never touched.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from ansys.fluent.mcp.common.backend import Backend
from ansys.fluent.mcp.common.file_handlers import (
    find_handler as _find_file_handler,
    normalize_path_for_fluent as _normalize_path_for_fluent,
    supported_suffixes as _supported_file_suffixes,
)

logger = logging.getLogger("ansys.fluent.mcp.solve.lib.compare_tools")


# ---------------------------------------------------------------------------
# Ephemeral PyFluent factory
# ---------------------------------------------------------------------------


def ephemeral_pyfluent_backend(label: str = "PyFluent (compare)") -> Backend:
    """Return a new ephemeral PyFluent backend for file comparison.

    Lazy-imported so the test suite (which monkey-patches this symbol)
    does not need PyFluent installed. The ``label`` flows into
    PyFluent log lines so each ephemeral session is identifiable per
    file in compare output.

    Parameters
    ----------
    label : str
        Label to supply to the function.

    Returns
    -------
    Backend
        Result produced by the function.
    """
    from ansys.fluent.mcp.solve.backends.pyfluent import PyFluentBackend

    return PyFluentBackend(label=label)


# ---------------------------------------------------------------------------
# Pure helpers — snapshot / diff / render
# ---------------------------------------------------------------------------


async def collect_compare_snapshot(backend: Backend) -> dict[str, Any]:
    """Read a deterministic slice of session state for diffing.

    Combines the global-state slice (energy, viscous, solver, methods,
    operating conditions) with named-object name lists per family.
    Returns a dictionary shaped like this::

        {"global": {<path>: <state-or-marker>},
         "named":  {<family>: [<names>]}}

    Parameters
    ----------
    backend : Backend
        Backend to supply to the function.

    Returns
    -------
    dict[str, Any]
        Mapping containing the operation result.
    """
    snap: dict[str, Any] = {"global": {}, "named": {}}
    try:
        snap["global"] = await backend.get_state()
    except Exception as exc:  # boundary
        snap["global"] = {"_error": str(exc)}
    try:
        named = await backend.list_named_objects()
        snap["named"] = {
            family: sorted(list(names or [])) for family, names in (named or {}).items()
        }
    except Exception as exc:  # boundary
        snap["named"] = {"_error": str(exc)}
    return snap


def diff_snapshots(
    a: dict[str, Any],
    b: dict[str, Any],
    *,
    prefix: str = "",
) -> list[dict[str, Any]]:
    """Recursively diff two snapshot dictionaries.

    Emits one record per leaf-level difference with shape::

        {"path": "global.setup/models/energy.enabled",
         "change": "changed" | "only_in_a" | "only_in_b",
         "a": <value or None>, "b": <value or None>}

    Parameters
    ----------
    a : dict[str, Any]
        A dictionary to supply to the function.
    b : dict[str, Any]
        B dictionary to supply to the function.
    prefix : str
        Prefix to supply to the function.

    Returns
    -------
    list[dict[str, Any]]
        Mapping containing the operation result.
    """
    diffs: list[dict[str, Any]] = []
    keys = sorted(set(a) | set(b))
    for k in keys:
        path = f"{prefix}.{k}" if prefix else str(k)
        if k not in a:
            diffs.append({"path": path, "change": "only_in_b", "b": b[k]})
            continue
        if k not in b:
            diffs.append({"path": path, "change": "only_in_a", "a": a[k]})
            continue
        va, vb = a[k], b[k]
        if isinstance(va, dict) and isinstance(vb, dict):
            diffs.extend(diff_snapshots(va, vb, prefix=path))
        elif isinstance(va, list) and isinstance(vb, list):
            try:
                only_a = sorted(set(va) - set(vb))
                only_b = sorted(set(vb) - set(va))
                for name in only_a:
                    diffs.append({"path": f"{path}[{name!r}]", "change": "only_in_a", "a": name})
                for name in only_b:
                    diffs.append({"path": f"{path}[{name!r}]", "change": "only_in_b", "b": name})
            except TypeError:
                if va != vb:
                    diffs.append({"path": path, "change": "changed", "a": va, "b": vb})
        elif va != vb:
            diffs.append({"path": path, "change": "changed", "a": va, "b": vb})
    return diffs


def shorten_value(v: Any, *, limit: int = 80) -> str:
    """Render a diff value compactly for table cells.

    Lists are rendered as comma-separated values rather than ``repr``
    so a list of named-object names reads naturally in the summary.

    Parameters
    ----------
    v : Any
        Value to supply to the function.
    limit : int
        Maximum number of items or characters to include.

    Returns
    -------
    str
        String result produced by the function.
    """
    if v is None:
        return "—"
    if isinstance(v, list):
        s = ", ".join(str(x) for x in v)
    elif isinstance(v, str):
        s = v
    else:
        s = repr(v)
    s = s.replace("\n", " ").replace("|", "\\|")
    return s if len(s) <= limit else s[: limit - 1] + "…"


def split_diff_path(path: str) -> tuple[str, str]:
    """Split a diff path into ``(section, leaf)`` for hierarchical rendering.

    Strips the leading ``global.``/``named.`` scope and splits
    trailing ``[name]`` brackets or ``.field`` suffixes off as the
    leaf. The section is shown as a heading. The leaf is the table
    row name.

    Parameters
    ----------
    path : str
        Fluent object path or file-system path to inspect.

    Returns
    -------
    tuple[str, str]
        Collection containing the operation results.
    """
    for prefix in ("global.", "named."):
        if path.startswith(prefix):
            path = path[len(prefix) :]
            break
    if path.endswith("]") and "[" in path:
        section, _, rest = path.rpartition("[")
        leaf = rest.rstrip("]").strip("'\"")
        return section.rstrip("/"), leaf
    if "." in path:
        section, _, leaf = path.rpartition(".")
        return section, leaf
    if "/" in path:
        section, _, leaf = path.rpartition("/")
        return section, leaf
    return "", path


def format_compare_summary(
    diffs: list[dict[str, Any]],
    *,
    name_a: str,
    name_b: str,
) -> str:
    """Render a hierarchical markdown summary of a diff list.

    Groups rows by their parent path (rendered as a section heading
    with ``/`` separators) and emits one table per section with
    columns: ``Setting | <name_a> | <name_b>``. The change kind is
    implicit: ``—`` in either column means "not present in that file".

    Parameters
    ----------
    diffs : list[dict[str, Any]]
        Diffs to supply to the function.
    name_a : str
        Name a to supply to the function.
    name_b : str
        Name b to supply to the function.

    Returns
    -------
    str
        String result produced by the function.
    """
    if not diffs:
        return f"No differences between **{name_a}** and **{name_b}**."

    grouped: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for d in diffs:
        section, leaf = split_diff_path(str(d.get("path", "")))
        grouped.setdefault(section, []).append((leaf, d))

    parts = [
        f"### Differences: **{name_a}** vs **{name_b}**",
        f"_{len(diffs)} difference(s) total._",
    ]

    for section in sorted(grouped, key=lambda s: (s.count("/"), s)):
        rows = grouped[section]
        heading = section.replace("/", " / ") if section else "(root)"
        parts.append("")
        parts.append(f"#### {heading}")
        parts.append(f"| Setting | {name_a} | {name_b} |")
        parts.append("| --- | --- | --- |")
        for leaf, d in rows:
            a = shorten_value(d.get("a")) if "a" in d else "—"
            b = shorten_value(d.get("b")) if "b" in d else "—"
            parts.append(f"| `{leaf}` | {a} | {b} |")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Path validation (leaf-safe — uses only the common file-handler registry)
# ---------------------------------------------------------------------------


def _validate_compare_path(raw: Any) -> tuple[Path | None, str | None]:
    """Validate a user-supplied path for comparison.

    Resolve and validate a user-supplied path against the shared
    :mod:`ansys.fluent.mcp.common.file_handlers` registry.

    Mirrors the agent's ``_validate_read_file_path`` + handler check
    but lives on the leaf side so the solve MCP can run without the
    agent wheel installed. The leaf is invoked by trusted MCP hosts
    (Claude Desktop, Copilot) on the same host; the check is purely
    a defense-in-depth filter so we don't try to read non-case files
    in PyFluent.

    Parameters
    ----------
    raw : Any
        Raw text value to parse.

    Returns
    -------
    tuple[Path | None, str | None]
        Collection containing the operation results.
    """
    if not isinstance(raw, str) or not raw.strip():
        return None, "path must be a non-empty string"
    p = Path(raw).expanduser()
    parts = p.parts
    if any(seg in {"..", ""} for seg in parts):
        return None, "path must not contain '..' or empty segments"
    try:
        resolved = p.resolve(strict=True)
    except FileNotFoundError:
        return None, f"file not found: {p}"
    except OSError as exc:
        return None, f"cannot resolve path: {exc}"
    if not resolved.is_file():
        return None, f"not a regular file: {resolved}"
    name = resolved.name.lower()
    if not any(name.endswith(s) for s in _supported_file_suffixes()):
        return None, (
            f"unsupported file type. Supported suffixes: {', '.join(_supported_file_suffixes())}"
        )
    handler = _find_file_handler(resolved)
    if handler is None or handler.component != "solve":
        return None, (
            f"compare_files only supports solver case/mesh files; "
            f"{resolved.name} maps to component "
            f"'{handler.component if handler else 'unknown'}'"
        )
    return resolved, None


# ---------------------------------------------------------------------------
# Public entry point — leaf-side typed handler
# ---------------------------------------------------------------------------


async def compare_files_impl(
    backend: Backend,  # noqa: ARG001 — unused; tool spawns ephemeral backends
    *,
    path_a: str,
    path_b: str,
) -> dict[str, Any]:
    """Compare two Fluent case/mesh files in ephemeral PyFluent sessions.

    Open two Fluent case/mesh files in two SEPARATE ephemeral
    PyFluent sessions and summarize the differences between them.

    Both sessions are launched headless (no GUI) and the cases are
    read with ``lightweight_setup=True`` for speed. The live workspace
    session, if any, is NOT touched. Returns a structured diff of
    global model state and per-family named-object name lists plus a
    pre-rendered markdown summary in the ``summary`` field.

    The ``backend`` argument from the leaf framework is intentionally
    unused. The tool spawns its own ephemeral backends per file so
    that the diff is reproducible regardless of whether a live session is
    attached.

    Parameters
    ----------
    backend : Backend
        Backend to supply to the function.
    path_a : str
        Path a to supply to the function.
    path_b : str
        Path b to supply to the function.

    Returns
    -------
    dict[str, Any]
        Mapping containing the operation result.
    """
    res_a, err_a = _validate_compare_path(path_a)
    if err_a:
        return {"error": f"path_a: {err_a}"}
    res_b, err_b = _validate_compare_path(path_b)
    if err_b:
        return {"error": f"path_b: {err_b}"}
    if res_a is None or res_b is None:
        return {"error": "failed to resolve both comparison paths"}
    if res_a == res_b:
        return {"error": "path_a and path_b resolve to the same file"}
    path_a_resolved = res_a
    path_b_resolved = res_b

    backend_a = ephemeral_pyfluent_backend(
        label=f"PyFluent (compare:{path_a_resolved.name})",
    )
    backend_b = ephemeral_pyfluent_backend(
        label=f"PyFluent (compare:{path_b_resolved.name})",
    )
    launch = {"ui_mode": "gui", "precision": "double"}
    try:
        conn_a = await backend_a.connect(**launch)
        if getattr(conn_a, "status", None) != "ok":
            return {
                "error": "failed to launch session A",
                "detail": getattr(conn_a, "message", None),
            }
        conn_b = await backend_b.connect(**launch)
        if getattr(conn_b, "status", None) != "ok":
            return {
                "error": "failed to launch session B",
                "detail": getattr(conn_b, "message", None),
            }

        for backend_i, path in ((backend_a, path_a_resolved), (backend_b, path_b_resolved)):
            case_path = _normalize_path_for_fluent(path)
            snippet = f'session.settings.file.read_case(file_name="{case_path}", lightweight_setup=True)\n'  # noqa: E501
            run_res = await backend_i.run_code(snippet)
            if getattr(run_res, "error_code", None):
                return {
                    "error": f"failed to read {path.name}",
                    "detail": (
                        getattr(run_res, "message", None) or getattr(run_res, "stderr", None)
                    ),
                }

        snap_a = await collect_compare_snapshot(backend_a)
        snap_b = await collect_compare_snapshot(backend_b)
    finally:
        for label, b in (("path_a", backend_a), ("path_b", backend_b)):
            try:
                await asyncio.wait_for(b.disconnect(), timeout=30.0)
            except asyncio.TimeoutError:
                logger.warning(
                    "compare_files: disconnect of %s timed out after 30s; headless Fluent process may linger",  # noqa: E501
                    label,
                )
            except Exception:
                logger.exception(
                    "compare_files: failed to disconnect ephemeral session for %s",
                    label,
                )

    diffs = diff_snapshots(snap_a, snap_b)
    summary = format_compare_summary(
        diffs,
        name_a=path_a_resolved.name,
        name_b=path_b_resolved.name,
    )
    return {
        "status": "ok",
        "from": "compare_files",
        "path_a": str(path_a_resolved),
        "path_b": str(path_b_resolved),
        "launch": {"product": "pyfluent", **launch, "lightweight_setup": True},
        "diff_count": len(diffs),
        "summary": summary,
        "diffs": diffs,
    }


__all__ = [
    "compare_files_impl",
    "ephemeral_pyfluent_backend",
    "collect_compare_snapshot",
    "diff_snapshots",
    "format_compare_summary",
    "shorten_value",
    "split_diff_path",
]
