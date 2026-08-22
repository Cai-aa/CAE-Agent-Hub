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

"""PyFluent backend for the Solve leaf.

Holds a persistent ``ansys.fluent.core.Solver`` session. All live-context
work delegates to :mod:`ansys.fluent.mcp.common.introspection` so the logic is
*generic* and *caller-driven*. There is no hardcoded list of named-object
collections. This matches the behavior of the legacy
``/fluent_get_targeted_context`` endpoint in ``aali-flowkit-python``.

PyFluent is an optional dependency. Install with this command::

    pip install ansys-fluent-mcp[pyfluent]

If Pyfluent is not importable, ``connect()`` returns a typed error instead
of raising at import time.
"""

from __future__ import annotations

import ast
import asyncio
import base64
import contextlib
import io
import logging
import os
from pathlib import Path
import tempfile
import traceback
from typing import Any, Mapping, Optional, cast

from ansys.fluent.mcp.common.backend import Backend
from ansys.fluent.mcp.common.errors import (
    BackendUnavailableError,
    InvalidArgumentsError,
    NotConnectedError,
    UpstreamError,
)
from ansys.fluent.mcp.common.models import ConnectResult, RunCodeResult
from ansys.fluent.mcp.common.validation import (
    _ALLOWED_BUILTINS,
    _ALLOWED_IMPORTS,
    validate_python_source,
)
from ansys.fluent.mcp.solve.backends.introspection import (
    collect_global_state,
    collect_targeted_context,
    discover_named_objects_via_scheme,
    discover_named_objects_via_walk,
    resolve_path,
)
from ansys.fluent.mcp.solve.lib import intent_guard as _intent_guard

# ---------------------------------------------------------------------------
# Settings-path extraction helpers (used by validate_code)
# ---------------------------------------------------------------------------

_SETTINGS_ROOTS: frozenset[str] = frozenset(
    {
        "setup",
        "solution",
        "results",
        "file",
        "mesh",
        "workflow",
        "TaskObject",
        "PartManagement",
        "PMFileManagement",
    }
)


def _chain_from_ast_node(node: ast.AST) -> list[str]:
    """Recursively extract a flat attribute chain, skipping subscript keys.

    Returns the identifiers in left-to-right order, e.g.::

        solver.settings.setup.models.energy → ["solver", "settings", "setup", "models", "energy"]
        fluid["elbow-fluid"].general.material → ["fluid", "general", "material"]

    Parameters
    ----------
    node : ast.AST
        Node to supply to the function.

    Returns
    -------
    list[str]
        Collection containing the operation results.
    """
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, ast.Attribute):
        parent = _chain_from_ast_node(node.value)
        return parent + [node.attr]
    if isinstance(node, ast.Subscript):
        # e.g. fluid["elbow-fluid"] — the subscript key carries no path
        # information; follow the value only.
        return _chain_from_ast_node(node.value)
    return []


def _extract_settings_paths(tree: ast.AST) -> list[str]:
    """Walk the AST and collect normalized Fluent settings API paths.

    Looks for attribute chains that pass through a known settings or
    meshing workflow root (``setup``, ``solution``, ``workflow``, etc.).
    The ``settings`` level injected by ``solver.settings.<root>`` is
    stripped so the returned paths match the api_objects.json format.

    Only the deepest (leaf) attribute access at each assignment target
    or standalone expression is returned — intermediate sub-chains are
    subsumed by the full chain.

    Parameters
    ----------
    tree : ast.AST
        Tree to supply to the function.

    Returns
    -------
    list[str]
        Collection containing the operation results.
    """
    leaf_paths: set[str] = set()

    def _register(node: ast.AST) -> None:
        """Register the callback with the local registry.

        Parameters
        ----------
        node : ast.AST
            Node being inspected or registered.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        chain = _chain_from_ast_node(node)
        for idx, segment in enumerate(chain):
            if segment == "settings" and idx + 1 < len(chain) and chain[idx + 1] in _SETTINGS_ROOTS:
                leaf_paths.add(".".join(chain[idx + 1 :]))
                return
            if segment in _SETTINGS_ROOTS:
                leaf_paths.add(".".join(chain[idx:]))
                return

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                _register(tgt)
            # Also check the value side — e.g. reading a property to print it.
            _register(node.value)
        elif isinstance(node, ast.AugAssign):
            _register(node.target)
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            # e.g. solver.settings.solution.initialization.hybrid_initialize()
            if isinstance(node.value.func, (ast.Attribute, ast.Subscript)):
                _register(node.value.func)

    return list(leaf_paths)


logger = logging.getLogger("ansys.fluent.mcp.backends.pyfluent")


# ---------------------------------------------------------------------------
# Dead-channel classifier (run_code error path)
# ---------------------------------------------------------------------------
#
# When PyFluent's gRPC channel dies mid-call, the exception bubbles up
# through several layers — sometimes as ``grpc.RpcError``, sometimes as
# the PyFluent ``RuntimeError("Server not running")`` wrapper, and
# occasionally as a bare ``ConnectionError`` from the asyncio transport.
# A single substring scan over the exception class + str() reliably
# catches every form we have seen in the wild without importing grpc
# (which is an indirect, optional dep of pyfluent).

_DEAD_CHANNEL_TOKENS: tuple[str, ...] = (
    "rpcerror",
    "_inactiverpcerror",
    "channel closed",
    "stream removed",
    "connection reset",
    "connection refused",
    "server not running",
    "transport closed",
    "fluent process",  # PyFluent: "Fluent process is not running"
    "session is closed",
    "unavailable",  # gRPC StatusCode.UNAVAILABLE
)


def _looks_like_dead_channel(exc: BaseException) -> bool:
    """Check whether ``exc`` looks like a gRPC / Fluent-process failure.

    The match is intentionally tolerant — it scans both the exception
    class name and ``str(exc)`` against a fixed token list. False
    positives degrade to "we mark the session disconnected and ask the
    user to reconnect", which is the same recovery path the user takes
    manually after every Fluent crash anyway.

    Parameters
    ----------
    exc : BaseException
        Exc to supply to the function.

    Returns
    -------
    bool
        Boolean result produced by the function.
    """
    name = type(exc).__name__.lower()
    msg = str(exc).lower()
    blob = f"{name} {msg}"
    return any(tok in blob for tok in _DEAD_CHANNEL_TOKENS)


# Cap on how many NamedObject instances we will pull in a single
# ``family.get_state()`` round-trip. Above this we fall back to
# chunked reads so a 32K-member family doesn't materialise an
# enormous dict (or hang Fluent's serializer). Tunable via
# ``FLUIDS_MCP_BATCH_FAMILY_LIMIT`` (set to 0 to disable the cap
# entirely; default 5000 covers ~99% of real cases).
def _batch_family_limit() -> int:
    """Return the configured limit for batched named-object reads.

    Returns
    -------
    int
        Configured integer limit used by the helper.
    """
    raw = os.environ.get("FLUIDS_MCP_BATCH_FAMILY_LIMIT")
    if not raw:
        return 5000
    try:
        v = int(raw)
    except (TypeError, ValueError):
        return 5000
    return max(0, v)


def _read_family_state(family_node: Any) -> dict[str, Any]:
    """Fetch ``{name: state_dict, ...}`` for a NamedObject family.

    Uses a single ``family_node.get_state()`` round-trip when the
    member count is below :func:`_batch_family_limit`; otherwise
    falls back to per-instance reads so we never materialise a
    pathological dict in one shot. Returns ``{}`` on any failure
    (callers expect a defensive empty mapping).

    Parameters
    ----------
    family_node : Any
        Family node to supply to the function.

    Returns
    -------
    dict[str, Any]
        Mapping containing the operation result.
    """
    if family_node is None:
        return {}
    cap = _batch_family_limit()
    # When chunking is enabled, peek at the member count first so we
    # can pick the right strategy. ``get_object_names`` is cheap
    # (one Scheme call returning a flat name list).
    member_count: int | None = None
    if cap > 0 and hasattr(family_node, "get_object_names"):
        try:
            names = list(family_node.get_object_names())
            member_count = len(names)
        except Exception:
            names = []
            member_count = None
    else:
        names = []
    # If we definitively know the family has zero members, skip the
    # get_state() call — it would trigger a server-side "object is not
    # active" error on Fluent (harmless but noisy in the log/transcript).
    if member_count == 0:
        return {}
    if cap == 0 or member_count is None or member_count <= cap:
        # Fast path: single batched read.
        try:
            state = family_node.get_state() or {}
        except Exception:
            return {}
        return state if isinstance(state, dict) else {}
    # Slow path: per-instance reads. Soft-warns once per call so we
    # can spot the outlier cases in the gateway log.
    logger.info(
        "family has %d members (>%d cap); falling back to per-instance "
        "state reads to avoid one giant payload",
        member_count,
        cap,
    )
    out: dict[str, Any] = {}
    for nm in names:
        try:
            inst = family_node[nm]
            inst_state = inst.get_state()
        except Exception as exc:
            logger.debug(
                "Failed to get state for instance '%s' of family '%s': %s", nm, family_node, exc
            )
            continue
        if isinstance(inst_state, dict):
            out[str(nm)] = inst_state
    return out


def _make_safe_import() -> Any:
    """Return a guarded ``__import__`` that honors :data:`_ALLOWED_IMPORTS`.

    Without this, snippets validated under ``strict=True`` that contain
    ``import math`` or ``import json`` would fail at runtime because
    the restricted ``__builtins__`` strips the real ``__import__``.
    The guard delegates to the real ``__import__`` for whitelisted
    modules and raises ``ImportError`` for anything else, keeping the
    sandbox tight while letting the validator's allowed imports work.

    Returns
    -------
    Any
        Result produced by the function.
    """
    real_import = __import__

    def _safe_import(
        name: str,
        globals=None,
        locals=None,  # noqa: A002
        fromlist=(),
        level: int = 0,
    ) -> Any:
        # Block relative imports (level > 0): the agent's snippets are
        # synthesized top-level code, never package modules.
        """Import an allowed module inside the sandbox.

        Parameters
        ----------
        name : str
            Name of the object, module, or setting being processed.
        globals : Any
            Globals mapping supplied by Python's import machinery.
        locals : Any
            Locals mapping supplied by Python's import machinery.
        fromlist : Any
            Names requested by a ``from ... import ...`` statement.
        level : int
            Logging level or severity to apply.

        Returns
        -------
        Any
            Imported module or object returned by Python's import machinery.
        """
        if level != 0:
            raise ImportError(f"relative imports are not permitted: {name!r}")
        root_mod = name.split(".", 1)[0]
        if name not in _ALLOWED_IMPORTS and root_mod not in _ALLOWED_IMPORTS:
            raise ImportError(f"import of {name!r} is not permitted in sandboxed run_code")
        return real_import(name, globals, locals, fromlist, level)

    return _safe_import


def _strict_validation_enabled() -> bool:
    """Return ``True`` when opt-in strict schema validation is enabled.

    Set ``FLUIDS_MCP_STRICT_VALIDATION=1`` to promote near-match Fluent
    settings-path warnings to hard ``unknown_settings_path`` errors.
    Default off — near-matches stay warnings so clients can autocorrect.
    """
    val = os.environ.get("FLUIDS_MCP_STRICT_VALIDATION")
    return val is not None and val.strip().lower() in {"1", "true", "yes", "on"}


def _scan_reflection_writes(code: str) -> list[str]:
    """Return reflection-based write patterns found in ``code``.

    The settings API mutates state via direct attribute assignment
    (``solver.x.y = v``) or ``.set_state(...)``. Reflection writes
    (``setattr`` / ``delattr`` / ``.__setitem__`` / ``.__setattr__`` /
    ``.__delattr__``) are never legitimate here and are a common way to
    smuggle a write past schema / read-only guards, so they are
    rejected outright. (Dunder ATTRIBUTE access is already blocked by
    the shared validator; this catches the ``setattr(obj, name, v)``
    call form whose attribute name is not a literal dunder.)
    """
    flagged: list[str] = []
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return flagged
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in {
                "setattr",
                "delattr",
            }:
                flagged.append(f"{node.func.id}(...)")
            elif isinstance(node.func, ast.Attribute) and node.func.attr in {
                "__setitem__",
                "__setattr__",
                "__delattr__",
                "__delitem__",
            }:
                flagged.append(f".{node.func.attr}(...)")
    return flagged


def _build_safe_builtins() -> dict[str, Any]:
    """Construct a restricted ``__builtins__`` mapping for ``exec``.

    Only the names listed in :data:`ansys.fluent.mcp.common.validation._ALLOWED_BUILTINS`
    are exposed, plus a guarded ``__import__`` that enforces
    :data:`ansys.fluent.mcp.common.validation._ALLOWED_IMPORTS`. Notably
    absent: ``eval``, ``exec``, ``compile``, ``open``, ``input``,
    ``exit``, ``quit``, ``globals``, ``locals``, ``vars``. This is a
    defense-in-depth layer behind the AST validator — even a validator
    bypass cannot reach these names via the runtime ``builtins`` module.

    Returns
    -------
    dict[str, Any]
        Mapping containing the operation result.
    """
    import builtins as _b

    safe: dict[str, Any] = {}
    for name in _ALLOWED_BUILTINS:
        if hasattr(_b, name):
            safe[name] = getattr(_b, name)
    # Provide a guarded __import__ so snippets that the AST validator
    # accepted (e.g. ``import math``) actually run.
    safe["__import__"] = _make_safe_import()
    return safe


# ---------------------------------------------------------------------------
# Launch-argument normalisation + validation
# ---------------------------------------------------------------------------
#
# These helpers translate the user-facing surface (``dimension=2``,
# ``mode="meshing"``, ``gpu=True | [0,1] | False``) into the exact
# shape PyFluent's ``launch_fluent`` expects, and reject combinations
# that Fluent itself rejects (e.g. ``gpu`` + 2D — Fluent prints
# ``"Fluent GPU Solver is only supported for 3D. Exiting ..."`` and
# exits). Catching these here is much friendlier than waiting 10-30s
# for the subprocess to launch and crash with an opaque error.

_VALID_FLUENT_MODES: frozenset[str] = frozenset(
    {
        "solver",
        "meshing",
        "solver_aero",
        "solver_icing",
        "pre_post",
    }
)

_VALID_UI_MODES: frozenset[str] = frozenset(
    {
        "gui",
        "hidden_gui",
        "no_gui",
        "no_graphics",
        "no_gui_or_graphics",
    }
)

# Stock Fluent startup defaults when the user or host omits a field.
# Matches Fluent/PyFluent out-of-the-box behavior: serial CPU 3ddp solver.
FLUENT_LAUNCH_DEFAULTS: dict[str, Any] = {
    "precision": "double",
    "processor_count": 1,
    "dimension": 3,
    "ui_mode": "gui",
    "gpu": None,  # CPU — no ``-gpu`` flag
    "mode": None,  # standard solver (PyFluent default)
}


def resolve_fluent_launch_config(
    *,
    precision: str = FLUENT_LAUNCH_DEFAULTS["precision"],
    processor_count: int = FLUENT_LAUNCH_DEFAULTS["processor_count"],
    ui_mode: str = FLUENT_LAUNCH_DEFAULTS["ui_mode"],
    product_version: Optional[str] = None,
    dimension: Optional[int | str] = None,
    mode: Optional[str] = None,
    gpu: Optional[bool | list[int] | str] = None,
    journal_file_names: Optional[str | list[str]] = None,
    case_file_name: Optional[str] = None,
    case_data_file_name: Optional[str] = None,
    cwd: Optional[str] = None,
    fluent_path: Optional[str] = None,
    env: Optional[dict[str, Any]] = None,
    graphics_driver: Optional[str] = None,
    scheduler_options: Optional[dict[str, Any]] = None,
    start_timeout: Optional[int] = None,
    cleanup_on_exit: Optional[bool] = None,
    additional_arguments: Optional[str] = None,
) -> dict[str, Any]:
    """Merge caller overrides with stock launch defaults.

    Returns the *effective* configuration. What is actually launched
    with is echoed back to the user. Only keys the caller explicitly
    set (or that have non-``None`` defaults) appear. ``gpu`` stays absent
    for CPU unless the user opted in.

    Parameters
    ----------
    precision : str
        Precision to supply to the function.
    processor_count : int
        Processor count to supply to the function.
    ui_mode : str
        Ui mode to supply to the function.
    product_version : Optional[str]
        Product version to supply to the function.
    dimension : Optional[int | str]
        Dimension to supply to the function.
    mode : Optional[str]
        Mode to supply to the function.
    gpu : Optional[bool | list[int] | str]
        GPU to supply to the function.
    journal_file_names : Optional[str | list[str]]
        Journal file names to supply to the function.
    case_file_name : Optional[str]
        Case file name to supply to the function.
    case_data_file_name : Optional[str]
        Case data file name to supply to the function.
    cwd : Optional[str]
        Command to supply to the function.
    fluent_path : Optional[str]
        Fluent path to supply to the function.
    env : Optional[dict[str, Any]]
        Environment mapping to read instead of the process environment.
    graphics_driver : Optional[str]
        Graphics driver to supply to the function.
    scheduler_options : Optional[dict[str, Any]]
        Scheduler options to supply to the function.
    start_timeout : Optional[int]
        Start timeout to supply to the function.
    cleanup_on_exit : Optional[bool]
        Cleanup on exit to supply to the function.
    additional_arguments : Optional[str]
        Additional arguments to supply to the function.

    Returns
    -------
    dict[str, Any]
        Mapping containing the operation result.
    """
    norm_dimension = (
        _normalise_dimension(dimension)
        if dimension is not None
        else FLUENT_LAUNCH_DEFAULTS["dimension"]
    )
    norm_gpu = _normalise_gpu(gpu) if gpu is not None else None
    norm_mode = _normalise_mode(mode) if mode is not None else None
    norm_journal = _normalise_journal_names(journal_file_names)

    _validate_launch_combo(
        dimension=norm_dimension,
        gpu=norm_gpu,
        mode=norm_mode,
    )

    cfg: dict[str, Any] = {
        "precision": precision,
        "processor_count": processor_count,
        "ui_mode": ui_mode,
        "dimension": norm_dimension,
    }
    if norm_mode is not None:
        cfg["mode"] = norm_mode
    if norm_gpu:
        cfg["gpu"] = norm_gpu
    if product_version is not None:
        cfg["product_version"] = product_version
    if norm_journal is not None:
        cfg["journal_file_names"] = norm_journal
    if case_file_name is not None:
        cfg["case_file_name"] = case_file_name
    if case_data_file_name is not None:
        cfg["case_data_file_name"] = case_data_file_name
    if cwd is not None:
        cfg["cwd"] = cwd
    if fluent_path is not None:
        cfg["fluent_path"] = fluent_path
    if env is not None:
        cfg["env"] = env
    if graphics_driver is not None:
        cfg["graphics_driver"] = graphics_driver
    if scheduler_options is not None:
        cfg["scheduler_options"] = scheduler_options
    if start_timeout is not None:
        cfg["start_timeout"] = start_timeout
    if cleanup_on_exit is not None:
        cfg["cleanup_on_exit"] = cleanup_on_exit
    if additional_arguments is not None:
        cfg["additional_arguments"] = additional_arguments
    return cfg


def _normalise_dimension(value: Any) -> int | None:
    """Normalise the ``dimension`` argument to PyFluent's expected shape.

    Accept ``2``, ``3``, ``"2d"``, ``"3d"``, ``"2"``, ``"3"``,
    ``None`` → return ``2``/``3``/``None``. Raise ``ValueError`` on
    anything else (caught by the outer ``ValueError`` handler so the
    user sees a clean error instead of a launch-time crash).

    Parameters
    ----------
    value : Any
        Value to supply to the function.

    Returns
    -------
    int | None
        Integer result produced by the function.
    """
    if value is None:
        return None
    if isinstance(value, bool):  # bool is a subclass of int — disallow
        raise ValueError(f"dimension={value!r}: pass 2 or 3 (int), not a boolean")
    if isinstance(value, int):
        if value not in (2, 3):
            raise ValueError(f"dimension={value!r}: only 2 or 3 are supported")
        return value
    if isinstance(value, str):
        s = value.strip().lower().rstrip("d")
        if s in ("2", "3"):
            return int(s)
    raise ValueError(f"dimension={value!r}: pass 2 / 3 / '2d' / '3d'")


def _normalise_mode(value: Any) -> str | None:
    """Normalise the ``mode`` argument to PyFluent's expected shape.

    Accept ``"solver"`` / ``"meshing"`` / ``"solver_aero"`` /
    ``"solver_icing"`` / ``"pre_post"`` / ``None``. Common aliases
    (``"prepost"``, ``"post"``, ``"aero"``, ``"icing"``) are folded
    onto the canonical names PyFluent's ``FluentMode`` enum accepts.

    Parameters
    ----------
    value : Any
        Value to supply to the function.

    Returns
    -------
    str | None
        String result produced by the function.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"mode={value!r}: pass a string ('solver' / 'meshing' / ...)")
    s = value.strip().lower().replace("-", "_")
    aliases = {
        "prepost": "pre_post",
        "post": "pre_post",
        "aero": "solver_aero",
        "icing": "solver_icing",
    }
    s = aliases.get(s, s)
    if s not in _VALID_FLUENT_MODES:
        raise ValueError(f"mode={value!r}: one of {sorted(_VALID_FLUENT_MODES)}")
    return s


def _normalise_gpu(value: Any) -> bool | list[int] | None:
    """Normalise the ``gpu`` argument to PyFluent's expected shape.

    Accept ``None`` (CPU), ``True`` (all GPUs → ``-gpu``), ``False``
    (explicit CPU), or a list of device indices (``-gpu=0,1``).

    Strings such as ``"0,1"`` are split and parsed for convenience —
    matches the raw ``-gpu=0,1`` form Fluent accepts.

    Parameters
    ----------
    value : Any
        Value to supply to the function.

    Returns
    -------
    bool | list[int] | None
        Boolean result produced by the function.
    """
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return [int(value)]
    if isinstance(value, str):
        parts = [p.strip() for p in value.split(",") if p.strip()]
        if not parts:
            return True
        try:
            return [int(p) for p in parts]
        except ValueError as exc:
            raise ValueError(
                f"gpu={value!r}: comma-separated device indices expected (e.g. '0,1')"
            ) from exc
    if isinstance(value, (list, tuple)):
        out: list[int] = []
        for v in value:
            try:
                out.append(int(v))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"gpu device index {v!r} is not an integer") from exc
        return out
    raise ValueError(
        f"gpu={value!r}: pass True / False / None / list[int] / comma-separated string"
    )


def _normalise_journal_names(
    value: Any,
) -> str | list[str] | None:
    """Accept ``None``, a single path string, or a list of paths.

    Paths are NOT existence-checked here — Fluent itself prints a
    clear error if a journal is missing and we don't want to race
    the file-system view on remote-launch / containerised setups.

    Parameters
    ----------
    value : Any
        Value to supply to the function.

    Returns
    -------
    str | list[str] | None
        String result produced by the function.
    """
    if value is None:
        return None
    if isinstance(value, str):
        s = value.strip()
        return s or None
    if isinstance(value, (list, tuple)):
        cleaned = [str(p).strip() for p in value if str(p).strip()]
        return cleaned or None
    raise ValueError(f"journal_file_names={value!r}: pass a string or list of strings")


def _validate_launch_combo(
    *,
    dimension: int | None,
    gpu: bool | list[int] | None,
    mode: str | None,
) -> None:
    """Fail-fast on combinations Fluent itself rejects.

    Tightens the error surface so the user sees a one-line ValueError
    instead of a 10-30s subprocess crash with an opaque message.

    Parameters
    ----------
    dimension : int | None
        Dimension to supply to the function.
    gpu : bool | list[int] | None
        Gpu to supply to the function.
    mode : str | None
        Mode to supply to the function.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    # Fluent: -gpu requires 3D.
    if gpu and dimension == 2:
        raise ValueError(
            "gpu=True / device-list requires dimension=3; "
            "Fluent rejects '-gpu' under 2D. Either drop gpu=... "
            "or set dimension=3."
        )
    # Meshing mode does not have a GPU solver; only the standard
    # 'solver' mode does. Flag the obvious mistake.
    if gpu and mode == "meshing":
        raise ValueError(
            "gpu=... is not meaningful in meshing mode; the GPU "
            "solver is solver-only. Either drop gpu=... or "
            "set mode='solver'."
        )


def _filter_launch_kwargs(
    launch_fluent_callable: Any,
    candidate: dict[str, Any],
) -> dict[str, Any]:
    """Return only the keys ``launch_fluent`` actually accepts.

    PyFluent has added / removed launch kwargs across minor versions
    (``topy`` arrived in 0.30, ``scheduler_options`` in 0.32, ``mode``
    replaced ``meshing_mode`` in 0.34, etc.). Rather than hard-coding
    one version's surface, we introspect the live ``launch_fluent``
    signature and drop any kwarg the installed build doesn't know
    about. ``None`` values are stripped so we never override PyFluent's
    own per-version defaults.

    Parameters
    ----------
    launch_fluent_callable : Any
        Launch fluent callable to supply to the function.
    candidate : dict[str, Any]
        Candidate to supply to the function.

    Returns
    -------
    dict[str, Any]
        Mapping containing the operation result.
    """
    import inspect

    try:
        sig = inspect.signature(launch_fluent_callable)
    except (TypeError, ValueError):
        # If introspection fails (custom callable wrapper, C-impl),
        # forward everything non-None and let PyFluent reject what
        # it doesn't know.
        return {k: v for k, v in candidate.items() if v is not None}

    supported = set(sig.parameters.keys())
    accepts_kwargs = any(p.kind is inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
    out: dict[str, Any] = {}
    dropped: list[str] = []
    for key, value in candidate.items():
        if value is None:
            continue
        if key in supported or accepts_kwargs:
            out[key] = value
        else:
            dropped.append(key)
    if dropped:
        logger.warning(
            "launch_fluent dropped unsupported kwargs: %s "
            "(installed PyFluent does not accept them — upgrade "
            "ansys-fluent-core if you need them)",
            dropped,
        )
    return out


class PyFluentBackend(Backend):
    """Persistent PyFluent Solver session."""

    kind = "pyfluent"

    def __init__(self, *, label: str = "PyFluent (solve)") -> None:
        """Initialize the PyFluentBackend instance.

        Parameters
        ----------
        label : str
            Human-readable label attached to the operation or test double.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        super().__init__()
        self.label = label
        self.endpoint: Optional[str] = None
        self._solver: Any = None
        self._mode: Optional[str] = None  # "launch" | "attach"
        self._session_kind = "solver_session"
        # Single-flight lock around every solver-touching coroutine. The
        # PyFluent gRPC channel is not safe under concurrent access from
        # the same process; serialize to avoid interleaved RPCs.
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(
        self,
        *,
        # --- attach mode --------------------------------------------------
        ip: Optional[str] = None,
        port: Optional[int] = None,
        password: Optional[str] = None,
        server_info_file: Optional[str] = None,
        # --- launch mode: basic --------------------------------------------
        precision: str = "double",
        processor_count: int = 1,
        ui_mode: str = "gui",
        product_version: Optional[str] = None,
        # --- launch mode: physics / dimensionality / GPU -------------------
        dimension: Optional[int | str] = None,
        mode: Optional[str] = None,
        gpu: Optional[bool | list[int]] = None,
        # --- launch mode: I/O ---------------------------------------------
        journal_file_names: Optional[str | list[str]] = None,
        case_file_name: Optional[str] = None,
        case_data_file_name: Optional[str] = None,
        cwd: Optional[str] = None,
        fluent_path: Optional[str] = None,
        env: Optional[dict[str, Any]] = None,
        # --- launch mode: graphics / cluster / passthrough ----------------
        graphics_driver: Optional[str] = None,
        scheduler_options: Optional[dict[str, Any]] = None,
        start_timeout: Optional[int] = None,
        cleanup_on_exit: Optional[bool] = None,
        additional_arguments: Optional[str] = None,
        **_: Any,
    ) -> ConnectResult:
        # ------------------------------------------------------------------
        # Normalise user-facing aliases and pre-validate forbidden
        # combinations BEFORE we cross into the PyFluent call site.
        # Unspecified fields use stock defaults: -t1, 3D, double, CPU.
        # ------------------------------------------------------------------
        """Connect to the configured backend or service.

        Parameters
        ----------
        ip : Optional[str]
            IP address of the Fluent server to connect to.
        port : Optional[int]
            Port number of the Fluent server to connect to.
        password : Optional[str]
            Password used when connecting to a Fluent server.
        server_info_file : Optional[str]
            Server-info file used to connect to an existing Fluent session.
        precision : str
            Solver precision requested for the Fluent session.
        processor_count : int
            Number of processors requested for the Fluent session.
        ui_mode : str
            Fluent UI mode requested for launch.
        product_version : Optional[str]
            Fluent product version requested for launch.
        dimension : Optional[int | str]
            Solver dimension requested for the Fluent session.
        mode : Optional[str]
            Execution or launch mode requested by the caller.
        gpu : Optional[bool | list[int]]
            GPU option forwarded to the Fluent launch API.
        journal_file_names : Optional[str | list[str]]
            Journal files passed to Fluent during startup.
        case_file_name : Optional[str]
            Case file path passed to Fluent at startup.
        case_data_file_name : Optional[str]
            Case-data file path passed to Fluent at startup.
        cwd : Optional[str]
            Working directory used when launching Fluent.
        fluent_path : Optional[str]
            Path for the fluent.
        env : Optional[dict[str, Any]]
            Environment mapping to read instead of the process environment.
        graphics_driver : Optional[str]
            Graphics driver requested for the Fluent session.
        scheduler_options : Optional[dict[str, Any]]
            Scheduler options forwarded to the Fluent launch API.
        start_timeout : Optional[int]
            Timeout in seconds used while starting Fluent.
        cleanup_on_exit : Optional[bool]
            Whether Fluent resources should be cleaned up when the process exits.
        additional_arguments : Optional[str]
            Additional launch arguments forwarded to Fluent.
        _ : Any
            Ignored compatibility options accepted by the backend interface.

        Returns
        -------
        ConnectResult
            ConnectResult produced by the operation.
        """
        try:
            effective = resolve_fluent_launch_config(
                precision=precision,
                processor_count=processor_count,
                ui_mode=ui_mode,
                product_version=product_version,
                dimension=dimension,
                mode=mode,
                gpu=gpu,
                journal_file_names=journal_file_names,
                case_file_name=case_file_name,
                case_data_file_name=case_data_file_name,
                cwd=cwd,
                fluent_path=fluent_path,
                env=env,
                graphics_driver=graphics_driver,
                scheduler_options=scheduler_options,
                start_timeout=start_timeout,
                cleanup_on_exit=cleanup_on_exit,
                additional_arguments=additional_arguments,
            )
        except ValueError as exc:
            return ConnectResult(
                status="error",
                error_code="invalid_launch_arguments",
                message=str(exc),
                backend_kind=self.kind,
            )

        # Validation passed — now import PyFluent.
        try:
            from ansys.fluent.core import connect_to_fluent, launch_fluent
        except ImportError:
            return ConnectResult(
                status="error",
                error_code="pyfluent_not_installed",
                message=(
                    "ansys-fluent-core is not installed. Install with "
                    "`pip install ansys-fluent-mcp[pyfluent]`."
                ),
                backend_kind=self.kind,
            )

        norm_dimension = effective["dimension"]
        norm_gpu = effective.get("gpu")
        norm_mode = effective.get("mode")
        norm_journal = effective.get("journal_file_names")
        session_kind = "meshing_session" if norm_mode == "meshing" else "solver_session"

        def _do_connect() -> Any:
            """Connect to the configured backend or service.

            Returns
            -------
            None
                The function completes through its side effects.
            """
            if server_info_file or (ip and port):
                self._mode = "attach"
                kwargs: dict[str, Any] = {}
                if server_info_file:
                    kwargs["server_info_file_name"] = server_info_file
                if ip:
                    kwargs["ip"] = ip
                if port:
                    kwargs["port"] = port
                if password:
                    kwargs["password"] = password
                return connect_to_fluent(**kwargs)
            self._mode = "launch"
            # Always start the PyFluent transcript stream. Several
            # core features depend on it:
            #
            #   * ``Backend.mesh_quality`` / ``Backend.mesh_check``
            #     parse the captured stdout chunk emitted by the
            #     settings-API commands of the same name.
            #   * The ``read_transcript`` MCP tool tails the
            #     ``fluent-*.trn`` file PyFluent writes to CWD.
            #   * ``diagnose_divergence`` augments residuals with
            #     transcript signals (FPE, reverse-flow, temperature
            #     limit warnings) the settings API can't surface.
            #
            # Earlier revisions gated this behind the
            # ``FLUIDS_PYFLUENT_TRANSCRIPT`` env var to avoid stray
            # ``fluent-*.trn`` artefacts; the gate was removed when
            # transcript-driven introspection moved from
            # opt-in-debugging to load-bearing-feature.
            #
            # Build the full candidate kwarg dict, then filter against
            # the installed PyFluent's ``launch_fluent`` signature so
            # users on older PyFluent builds don't trip "unexpected
            # keyword argument" — instead, unsupported fields are
            # silently dropped and (when meaningful) folded into
            # ``additional_arguments`` so the underlying ``fluent``
            # process still sees them.
            candidate: dict[str, Any] = {
                "precision": effective["precision"],
                "processor_count": effective["processor_count"],
                "ui_mode": effective["ui_mode"],
                "start_transcript": True,
                "dimension": norm_dimension,
                "product_version": effective.get("product_version"),
                "mode": norm_mode,
                "gpu": norm_gpu,
                "journal_file_names": norm_journal,
                "case_file_name": effective.get("case_file_name"),
                "case_data_file_name": effective.get("case_data_file_name"),
                "cwd": effective.get("cwd"),
                "fluent_path": effective.get("fluent_path"),
                "env": effective.get("env"),
                "graphics_driver": effective.get("graphics_driver"),
                "scheduler_options": effective.get("scheduler_options"),
                "start_timeout": effective.get("start_timeout"),
                "cleanup_on_exit": effective.get("cleanup_on_exit"),
                "additional_arguments": effective.get("additional_arguments"),
            }
            launch_kwargs = _filter_launch_kwargs(launch_fluent, candidate)
            return launch_fluent(**launch_kwargs)

        try:
            async with self._lock:
                connect_task = asyncio.create_task(asyncio.to_thread(_do_connect))
                try:
                    self._solver = await asyncio.shield(connect_task)
                    self._session_kind = session_kind
                except asyncio.CancelledError:
                    self._solver = await connect_task
                    self._session_kind = session_kind
                    self.close_sync()
                    raise
        except Exception as exc:  # boundary
            logger.exception("PyFluent connect failed")
            return ConnectResult(
                status="error",
                error_code="pyfluent_connect_failed",
                message=str(exc),
                backend_kind=self.kind,
            )

        # Fresh session → drop every cache from any prior session.
        self.invalidate_live_caches()
        self.invalidate_mesh_cache()
        try:
            from ansys.fluent.mcp.common.activity_logging import SESSION_LOGGER

            SESSION_LOGGER.info(
                "session connected mode=%s endpoint=%s precision=%s "
                "processor_count=%s dimension=%s solver_mode=%s "
                "gpu=%r journals=%s case=%s",
                self._mode,
                self.endpoint,
                effective["precision"],
                effective["processor_count"],
                norm_dimension,
                norm_mode,
                norm_gpu,
                norm_journal,
                effective.get("case_data_file_name") or effective.get("case_file_name"),
            )
        except Exception as exc:
            logger.debug("Failed to log session connect: %s", exc, exc_info=True)
        return ConnectResult(
            status="ok",
            backend_kind=self.kind,
            endpoint=self.endpoint,
            message=f"Connected via {self._mode}",
        )

    async def disconnect(self) -> None:
        # Acquire the lock FIRST so any in-flight ``run_code`` /
        # ``get_state`` / ``list_named_objects`` operation finishes
        # before we tear down ``solver``. Mutating ``self._solver``
        # outside the lock would race with worker threads still using
        # the live reference and could call ``solver.exit()`` while a
        # gRPC call is mid-flight.
        """Close resources for the PyFluentBackend object.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        async with self._lock:
            solver = self._solver
            if solver is None:
                return
            prev_endpoint = self.endpoint
            self._solver = None
            self.endpoint = None
            self._session_kind = "solver_session"
            self.invalidate_cache()

            def _do_close() -> None:
                """Execute the close helper.

                Returns
                -------
                None
                    The function completes through its side effects.
                """
                try:
                    if hasattr(solver, "exit"):
                        solver.exit()
                    elif hasattr(solver, "close"):
                        solver.close()
                except Exception:
                    logger.exception("Error closing PyFluent session")

            await asyncio.to_thread(_do_close)
        try:
            from ansys.fluent.mcp.common.activity_logging import SESSION_LOGGER

            SESSION_LOGGER.info(
                "session disconnected endpoint=%s",
                prev_endpoint,
            )
        except Exception as exc:
            logger.debug("Failed to log session disconnect: %s", exc, exc_info=True)

    def is_connected(self) -> bool:
        """Return whether connected.

        Returns
        -------
        bool
            Boolean result of the operation.
        """
        return self._solver is not None

    def close_sync(self) -> None:
        """Close backend resources from synchronous code.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        if self._solver is None:
            return
        solver = self._solver
        # Clear refs first so subsequent calls hit NotConnectedError even if
        # the underlying ``.exit()`` raises mid-shutdown.
        self._solver = None
        self.endpoint = None
        self._session_kind = "solver_session"
        try:
            if hasattr(solver, "exit"):
                solver.exit()
            elif hasattr(solver, "close"):
                solver.close()
        except Exception:  # best-effort sync close
            logger.exception("Error closing PyFluent session in close_sync()")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _require(self) -> Any:
        """Return the active solver session or raise if unavailable.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        if self._solver is None:
            raise NotConnectedError("PyFluent backend is not connected.")
        return self._solver

    def _settings_root(self) -> Any:
        """Return the live settings root used by introspection helpers.

        Returns
        -------
        Any
            Result produced by the function.
        """
        solver = self._require()
        return getattr(solver, "settings", solver)

    async def find_api(
        self,
        query: str,
        *,
        top_k: int = 10,
        kinds: list[str] | None = None,
        under: str | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve API candidates from the active PyFluent session catalog.

        Parameters
        ----------
        query : str
            Search query supplied by the caller.
        top_k : int
            Maximum number of search hits to return.
        kinds : list[str] | None
            Optional API object kinds used to filter search results.
        under : str | None
            Optional root path used to constrain API search results.

        Returns
        -------
        list[dict[str, Any]]
            Collection containing ranked API hits.
        """
        from ansys.fluent.mcp.solve.catalog.retriever import get_api_retriever_for_session

        retriever = get_api_retriever_for_session(self._session_kind)
        hits = await retriever.retrieve(query, top_k=top_k, kinds=kinds, under=under)
        if not hits:
            raise BackendUnavailableError(
                "No API retriever returned results. "
                "Install pyfluent and ensure the lexical API index is available."
            )
        return [h.to_tool_dict() for h in hits]

    # ------------------------------------------------------------------
    # Intent-guard probes (best-effort, never raise into the guard)
    # ------------------------------------------------------------------

    def _probe_live_named_for_guard(self) -> dict[str, list[str]]:
        """Return a small subset of live NamedObject keys the guard needs.

        Only ``setup.named_expressions`` is probed today (the
        named-expression forward-reference signature). Returns an empty
        mapping on any failure so the guard degrades to syntactic checks.

        Returns
        -------
        dict[str, list[str]]
            Mapping containing the operation result.
        """
        if getattr(self, "_solver", None) is None:
            return {}
        out: dict[str, list[str]] = {}
        try:
            ne = self._settings_root().setup.named_expressions
            getter = getattr(ne, "get_object_names", None)
            if callable(getter):
                out["setup.named_expressions"] = [str(n) for n in getter()]
        except Exception:  # guard probes are best-effort
            return {}
        return out

    def _probe_iterating_for_guard(self) -> bool:
        """Best-effort 'is the solver iterating?' check for the guard.

        Returns ``False`` on any failure — the guard signature that
        relies on this is opt-in and false-negative-safe (we miss a
        warning, not allow an invalid write).

        Returns
        -------
        bool
            Boolean result produced by the function.
        """
        solver = getattr(self, "_solver", None)
        if solver is None:
            return False
        try:
            scheme = getattr(solver, "scheme", None)
            if scheme is None:
                return False
            raw = scheme.eval("(%cx-is-solution-iterating)")
            return bool(raw)
        except Exception:
            return False

    def _mark_solver_disconnected(self) -> None:
        """Drop the cached solver handle and live caches.

        Called from :meth:`run_code` when the underlying gRPC channel
        is detected as dead. Subsequent ``session_status`` /
        ``solver_status`` calls report ``connected=False`` immediately
        instead of bouncing through one more failing settings call.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        self._solver = None
        self.endpoint = None
        try:
            self.invalidate_live_caches()
            self.invalidate_mesh_cache()
        except Exception as exc:
            logger.debug("Failed to invalidate live caches: %s", exc, exc_info=True)

    # ------------------------------------------------------------------
    # Live model context (generic — no hardcoded paths)
    # ------------------------------------------------------------------

    async def list_named_objects(self) -> dict[str, Any]:
        """Discover every named-object collection.

        Strategy:

        1. Try the Scheme ``api-get-named-object-names`` (one call,
           covers every collection Fluent knows about).
        2. Fall back to a generic depth-limited tree walk.

        No hardcoded path list.

        Returns
        -------
        dict[str, Any]
            Mapping containing the operation result.
        """
        cached = self._cache_get("named_objects", ttl=15.0)
        if cached is not None:
            from ansys.fluent.mcp.common.timings import get_collector as _get_timings

            _get_timings().record("backend", "list_named_objects:cache_hit", 0.0)
            return cached
        from ansys.fluent.mcp.common.backend_trace import trace_call

        trace_call("list_named_objects")

        def _do() -> dict[str, list[str]]:
            """Execute the nested helper for the enclosing operation.

            Returns
            -------
            dict[str, list[str]]
                Mapping containing the operation result.
            """
            solver = self._require()
            via_scheme = discover_named_objects_via_scheme(solver)
            if via_scheme is not None:
                return via_scheme
            return discover_named_objects_via_walk(self._settings_root())

        from ansys.fluent.mcp.common.timings import get_collector as _get_timings

        with _get_timings().time("backend", "list_named_objects"):
            async with self._lock:
                result = await asyncio.to_thread(_do)
        self._cache_put("named_objects", result)
        return result

    async def get_named_object_names(self, collection_path: str) -> list[str]:
        """Return instance names for a single named-object collection using ``get_object_names()``.

        A single cheap Scheme call that does not need to read the full collection state.

        Falls back to the full ``list_named_objects()`` snapshot if the
        collection node does not expose ``get_object_names``.

        Parameters
        ----------
        collection_path : str
            Path to the named-object collection.

        Returns
        -------
        list[str]
            Collection containing the operation results.
        """
        from ansys.fluent.mcp.common.backend_trace import trace_call

        trace_call("get_named_object_names", summary=f"path={collection_path}")

        def _do() -> list[str]:
            """Execute the nested helper for the enclosing operation.

            Returns
            -------
            list[str]
                List of results produced by the operation.
            """
            root = self._settings_root()
            try:
                node = resolve_path(root, collection_path)
            except (AttributeError, KeyError, TypeError):
                return []
            fn = getattr(node, "get_object_names", None)
            if callable(fn):
                try:
                    return [str(n) for n in fn()]
                except Exception as exc:
                    logger.debug(
                        "get_object_names() failed for %s: %s", collection_path, exc, exc_info=True
                    )
            # Fallback: use dict-style keys() if the node is indexable.
            if hasattr(node, "keys"):
                try:
                    return [str(k) for k in node.keys()]
                except Exception as exc:
                    logger.debug("keys() failed for %s: %s", collection_path, exc, exc_info=True)
                    pass
            return []

        from ansys.fluent.mcp.common.timings import get_collector as _get_timings

        with _get_timings().time("backend", "get_named_object_names"):
            async with self._lock:
                return await asyncio.to_thread(_do)

    async def get_state(self, paths: list[str] | None = None) -> dict[str, Any]:
        """Return the state.

        Parameters
        ----------
        paths : list[str] | None
            Fluent object paths supplied to the operation.

        Returns
        -------
        dict[str, Any]
            Mapping containing the operation result.
        """
        from ansys.fluent.mcp.common.backend_trace import trace_call

        trace_call(
            "get_state",
            summary=("paths=*" if not paths else f"paths={len(paths)}"),
        )

        def _do() -> dict[str, Any]:
            """Execute the nested helper for the enclosing operation.

            Returns
            -------
            dict[str, Any]
                Mapping containing the operation result.
            """
            return collect_global_state(self._settings_root(), paths=paths)

        from ansys.fluent.mcp.common.timings import get_collector as _get_timings

        with _get_timings().time("backend", "get_state"):
            async with self._lock:
                return await asyncio.to_thread(_do)

    async def get_active_status(self, paths: list[str]) -> dict[str, bool]:
        """Return the active status.

        Parameters
        ----------
        paths : list[str]
            Fluent object paths supplied to the operation.

        Returns
        -------
        dict[str, bool]
            Mapping containing the operation result.
        """
        if not paths:
            raise InvalidArgumentsError("paths must be non-empty")
        from ansys.fluent.mcp.common.backend_trace import trace_call

        trace_call("get_active_status", summary=f"paths={len(paths)}")
        from ansys.fluent.mcp.common.timings import get_collector as _get_timings

        _timings = _get_timings()

        def _do() -> dict[str, bool]:
            """Execute the nested helper for the enclosing operation.

            Returns
            -------
            dict[str, bool]
                Mapping containing the operation result.
            """
            root = self._settings_root()
            out: dict[str, bool] = {}
            for path in paths:
                try:
                    node = resolve_path(root, path)
                except Exception:  # broaden: bracket-subscript paths
                    # ``solution.controls.under_relaxation["pressure"]``
                    # can raise non-(AttributeError/KeyError/TypeError)
                    # after a case reload (settings tree rebuilt with a
                    # different schema for the new pv-coupling). Treat
                    # every resolve failure as "not active" so the
                    # caller still gets a complete status map.
                    out[path] = False
                    continue
                fn = getattr(node, "is_active", None)
                if callable(fn):
                    try:
                        out[path] = bool(fn())
                    except Exception:
                        out[path] = False
                else:
                    out[path] = True
            return out

        with _timings.time("backend", "get_active_status"):
            async with self._lock:
                return await asyncio.to_thread(_do)

    async def get_allowed_values(self, paths: list[str]) -> dict[str, list[Any]]:
        """Return the allowed values.

        Parameters
        ----------
        paths : list[str]
            Fluent object paths supplied to the operation.

        Returns
        -------
        dict[str, list[Any]]
            Mapping containing the operation result.
        """
        if not paths:
            raise InvalidArgumentsError("paths must be non-empty")
        from ansys.fluent.mcp.common.timings import get_collector as _get_timings

        _timings = _get_timings()

        def _do() -> dict[str, list[Any]]:
            """Execute the nested helper for the enclosing operation.

            Returns
            -------
            dict[str, list[Any]]
                Mapping containing the operation result.
            """
            root = self._settings_root()
            out: dict[str, list[Any]] = {}
            for path in paths:
                try:
                    node = resolve_path(root, path)
                except (AttributeError, KeyError, TypeError):
                    out[path] = []
                    continue
                values: list[Any] = []
                for accessor in ("allowed_values", "get_allowed_values"):
                    fn = getattr(node, accessor, None)
                    if callable(fn):
                        try:
                            values = list(fn())
                            break
                        except Exception as exc:
                            logger.debug(
                                "allowed_values() failed for %s: %s", path, exc, exc_info=True
                            )
                out[path] = values
            return out

        with _timings.time("backend", "get_allowed_values"):
            async with self._lock:
                return await asyncio.to_thread(_do)

    async def get_node_attrs(
        self,
        paths: list[str],
        attrs: list[str],
    ) -> dict[str, dict[str, Any]]:
        """Batched per-node settings-attribute fetch.

        For each ``path`` resolves the settings node and asks Fluent
        for ALL requested ``attrs`` in one Scheme RPC via PyFluent's
        ``node.get_attrs([...])``. Returns ``{path: {attr: value}}``.

        ``attrs`` use the Scheme spelling (``"active?"``,
        ``"read-only?"``, ``"user-creatable?"``, ``"allowed-values"``,
        ``"min"``, ``"max"``, ``"default"``, ``"units-quantity"``,
        ``"file-purpose"``). Attrs the node does not expose are simply
        omitted from its inner dict — Fluent never raises for missing
        attrs in a batch request.

        Unresolvable paths and nodes that do not implement
        ``get_attrs`` map to ``{}``. Empty ``paths`` raises
        :class:`InvalidArgumentsError`; empty ``attrs`` raises the same.

        This is the foundation for enrichment passes such as
        ``describe_named_object_template`` that would otherwise issue
        one RPC per attribute.

        Parameters
        ----------
        paths : list[str]
            Fluent object paths supplied to the operation.
        attrs : list[str]
            Attribute names requested from the backend object.

        Returns
        -------
        dict[str, dict[str, Any]]
            Mapping containing the operation result.
        """
        if not paths:
            raise InvalidArgumentsError("paths must be non-empty")
        if not attrs:
            raise InvalidArgumentsError("attrs must be non-empty")
        from ansys.fluent.mcp.common.timings import get_collector as _get_timings

        _timings = _get_timings()
        attrs_list = [str(a) for a in attrs]

        def _do() -> dict[str, dict[str, Any]]:
            """Execute the nested helper for the enclosing operation.

            Returns
            -------
            dict[str, dict[str, Any]]
                Mapping containing the operation result.
            """
            root = self._settings_root()
            out: dict[str, dict[str, Any]] = {}
            for path in paths:
                try:
                    node = resolve_path(root, path)
                except (AttributeError, KeyError, TypeError):
                    out[path] = {}
                    continue
                fn = getattr(node, "get_attrs", None)
                if not callable(fn):
                    out[path] = {}
                    continue
                try:
                    raw = fn(attrs_list)
                except Exception:
                    out[path] = {}
                    continue
                if isinstance(raw, dict):
                    out[path] = {str(k): v for k, v in raw.items()}
                else:
                    out[path] = {}
            return out

        with _timings.time("backend", "get_node_attrs"):
            async with self._lock:
                return await asyncio.to_thread(_do)

    async def get_node_attrs_bulk(
        self,
        parent_path: str,
        attrs: list[str],
    ) -> dict[str, dict[str, Any]]:
        """Recursively fetch attributes for all children of ``parent_path``.

        Calls ``node.get_attrs(attrs, True)``, a single Scheme RPC —
        returning ``{relative_child_path: {attr: value}}`` for every
        descendant that exposes those attributes.  This replaces N per-field
        ``get_node_attrs`` round-trips when the caller needs metadata for
        a whole subtree (such as validating every leaf in a ``set_named``
        value dict before apply).

        Falls back to ``{}`` gracefully when the node is unreachable or
        does not support the recursive form.

        Parameters
        ----------
        parent_path : str
            Parent Fluent object path used for bulk lookup.
        attrs : list[str]
            Attribute names requested from the backend object.

        Returns
        -------
        dict[str, dict[str, Any]]
            Mapping containing the operation result.
        """
        if not attrs:
            return {}
        attrs_list = [str(a) for a in attrs]
        from ansys.fluent.mcp.common.timings import get_collector as _get_timings

        _timings = _get_timings()

        def _do() -> dict[str, dict[str, Any]]:
            """Execute the nested helper for the enclosing operation.

            Returns
            -------
            dict[str, dict[str, Any]]
                Mapping containing the operation result.
            """
            root = self._settings_root()
            try:
                node = resolve_path(root, parent_path)
            except (AttributeError, KeyError, TypeError):
                return {}
            fn = getattr(node, "get_attrs", None)
            if not callable(fn):
                return {}
            try:
                # Second positional arg ``True`` activates recursive mode:
                # returns ``{child_relative_path: {attr: value, ...}, ...}``
                raw = fn(attrs_list, True)
            except Exception:
                return {}
            if not isinstance(raw, dict):
                return {}
            out: dict[str, dict[str, Any]] = {}
            for child_path, child_attrs in raw.items():
                if isinstance(child_attrs, dict):
                    out[str(child_path)] = {str(k): v for k, v in child_attrs.items()}
            return out

        with _timings.time("backend", "get_node_attrs_bulk"):
            async with self._lock:
                return await asyncio.to_thread(_do)

    async def probe_path(self, paths: list[str]) -> dict[str, dict[str, Any]]:
        """Cheap pre-flight: ``{path: {exists, is_active, is_user_creatable, kind}}``.

        Designed to be called once before a batch of mutating writes so
        the executor can skip steps that would fail anyway (path
        missing, settings node currently inactive, NamedObject family
        that does not accept ``create``). Each path costs ONE Scheme
        RPC via the leaf's batched ``get_attrs([active?,
        user-creatable?])`` plus a local class-name lookup.

        ``kind`` is one of ``"missing"``, ``"command"``, ``"query"``,
        ``"named_object"``, ``"group"``, ``"leaf"``. Unknown / unusual
        nodes default to ``"leaf"``.

        Parameters
        ----------
        paths : list[str]
            Fluent object paths supplied to the operation.

        Returns
        -------
        dict[str, dict[str, Any]]
            Mapping containing the operation result.
        """
        if not paths:
            raise InvalidArgumentsError("paths must be non-empty")
        from ansys.fluent.mcp.common.timings import get_collector as _get_timings

        _timings = _get_timings()

        def _do() -> dict[str, dict[str, Any]]:
            """Execute the nested helper for the enclosing operation.

            Returns
            -------
            dict[str, dict[str, Any]]
                Mapping containing the operation result.
            """
            root = self._settings_root()
            out: dict[str, dict[str, Any]] = {}
            for path in paths:
                try:
                    node = resolve_path(root, path)
                except (AttributeError, KeyError, TypeError):
                    out[path] = {"exists": False, "kind": "missing"}
                    continue
                # Default conservative facts.
                rec: dict[str, Any] = {
                    "exists": True,
                    "is_active": True,
                    "is_user_creatable": False,
                    "kind": "leaf",
                }
                # Kind sniff — cheap class/attr probes only.
                arg_names = getattr(node, "argument_names", None)
                if arg_names is not None and callable(node):
                    rec["kind"] = "query" if "query" in type(node).__name__.lower() else "command"
                elif getattr(node, "child_object_type", None) is not None:
                    rec["kind"] = "named_object"
                elif hasattr(node, "child_names") and getattr(node, "child_names", None):
                    rec["kind"] = "group"
                # Single batched attr fetch.
                fn = getattr(node, "get_attrs", None)
                if callable(fn):
                    try:
                        raw = fn(["active?", "user-creatable?"]) or {}
                    except Exception:
                        raw = {}
                    if isinstance(raw, dict):
                        if "active?" in raw:
                            rec["is_active"] = bool(raw["active?"])
                        if "user-creatable?" in raw:
                            rec["is_user_creatable"] = bool(raw["user-creatable?"])
                else:
                    # Fallback to the legacy is_active() accessor.
                    is_active = getattr(node, "is_active", None)
                    if callable(is_active):
                        try:
                            rec["is_active"] = bool(is_active())
                        except Exception as exc:
                            logger.debug("is_active() failed for %s: %s", path, exc, exc_info=True)
                out[path] = rec
            return out

        with _timings.time("backend", "probe_path"):
            async with self._lock:
                return await asyncio.to_thread(_do)

    async def mesh_adjacency_probe(
        self,
        cellzones: list[str],
        *,
        bc_filter: tuple[str, ...] | None = None,
    ) -> dict[str, list[str]]:
        """Return ``{cellzone -> [adjacent_face_zone_names]}``.

        Read-only. Implementation walks every BC family that exposes
        ``adjacent_cell_zone`` (wall, velocity_inlet, pressure_outlet,
        mass_flow_inlet, …) and inverts the mapping. Coupled-wall
        ``shadow_face_zone`` entries are added to BOTH sides so the
        cellzone-↔-cellzone neighbour query (set-intersection on shared
        face names) finds CHT solid-fluid pairs.

        IMPORTANT — PyFluent Query objects: both ``adjacent_cell_zone``
        and ``shadow_face_zone`` are PyFluent *Query* objects (not
        Parameters). They are never included in ``get_state()`` output
        and must be read by calling them: ``instance.adjacent_cell_zone()``.
        The implementation enumerates instance names via a batched
        ``get_state()`` (cheap), then calls the Query per-instance.

        ``bc_filter`` (optional) restricts the walk to the listed BC
        families (e.g. ``("wall",)`` to answer "walls adjacent to X";
        ``("velocity_inlet","pressure_inlet")`` for inlets). Unknown
        families are silently dropped. The coupled-wall shadow pass
        runs only when ``"wall"`` is in scope (or the filter is None).

        Limitation: interior face zones are NOT enumerated — they are
        gated INACTIVE on ``boundary_conditions.interior[*]`` and the
        ``mesh.adjacency`` Command's argument-binding side-channel is
        broken on Fluent ≥ 27.1 (``cellzones.set_state`` raises
        ``attr value not defined``). Callers that need interior-face
        coverage must supplement with ``run_code``.

        Parameters
        ----------
        cellzones : list[str]
            Cell zone names used for the mesh adjacency query.
        bc_filter : tuple[str, ...] | None
            Boundary-condition filter used to limit the probe.

        Returns
        -------
        dict[str, list[str]]
            Mapping containing the operation result.
        """
        if not cellzones:
            return {}

        def _do() -> dict[str, list[str]]:
            """Execute the nested helper for the enclosing operation.

            Returns
            -------
            dict[str, list[str]]
                Mapping containing the operation result.
            """
            root = self._settings_root()
            try:
                bc = resolve_path(root, "setup.boundary_conditions")
            except (AttributeError, KeyError, TypeError) as exc:
                raise BackendUnavailableError(
                    f"boundary_conditions surface unavailable ({exc})."
                ) from exc

            # Restrict probing to a fixed allowlist of families that
            # carry adjacent_cell_zone in current PyFluent builds.
            # Verified live on 27.1.0; safe-no-op on older builds where
            # the family or attribute is absent.
            allowed_families = (
                "wall",
                "velocity_inlet",
                "pressure_outlet",
                "mass_flow_inlet",
                "mass_flow_outlet",
                "pressure_inlet",
                "pressure_far_field",
                "outflow",
                "inlet_vent",
                "outlet_vent",
                "exhaust_fan",
                "intake_fan",
                "fan",
                "porous_jump",
                "radiator",
                "symmetry",
                "axis",
                "periodic",
            )
            families: tuple[str, ...]
            if bc_filter is None:
                families = allowed_families
            else:
                # Caller-restricted: silently drop unknown family names
                # (defensive against typos in tool args).
                allow_set = set(allowed_families)
                families = tuple(f for f in bc_filter if f in allow_set)
            requested = {str(c) for c in cellzones}
            cz_to_faces: dict[str, set[str]] = {c: set() for c in requested}

            # Pass 1 — direct ACZ walk over BC families.
            #
            # Optimisation: instead of N RPC round-trips per family
            # (one per instance just to read ``adjacent_cell_zone``),
            # call ``family_node.get_state()`` ONCE — PyFluent returns
            # ``{instance_name: {full_state_dict}, ...}`` for every
            # member in a single round-trip. ``_read_family_state``
            # caps the batch at ``FLUIDS_MCP_BATCH_FAMILY_LIMIT`` and
            # falls back to per-instance reads on outlier families
            # (32K+ members) so we never materialise a pathological
            # dict in one shot.
            for fam in families:
                family_node = getattr(bc, fam, None)
                if family_node is None:
                    continue
                # Quick member-count check: if the family has zero
                # instances in this mesh, skip it entirely to avoid
                # the Fluent server-side "object is not active" noise.
                try:
                    if hasattr(family_node, "get_object_names") and not list(
                        family_node.get_object_names()
                    ):
                        continue
                except Exception as exc:
                    # get_object_names() itself threw "not active" —
                    # this family is definitively absent from the mesh.
                    logger.debug("get_object_names() failed for %s: %s", fam, exc, exc_info=True)
                # Use _read_family_state to enumerate instance names in one
                # round-trip. Note: adjacent_cell_zone is a PyFluent Query
                # object — it is NOT included in get_state() output. We must
                # call instance.adjacent_cell_zone() explicitly per instance.
                fam_state = _read_family_state(family_node)
                for face_name in fam_state:
                    try:
                        acz_node = getattr(family_node[face_name], "adjacent_cell_zone", None)
                        acz = str(acz_node()) if acz_node is not None else None
                    except Exception as exc:
                        logger.debug(
                            "adjacent_cell_zone() failed for %s.%s: %s",
                            fam,
                            face_name,
                            exc,
                            exc_info=True,
                        )
                        continue
                    if not acz:
                        continue
                    if acz in cz_to_faces:
                        cz_to_faces[acz].add(str(face_name))

            # Pass 2 — coupled walls: also attribute the shadow face zone
            # to whichever cellzone owns the shadow side. This is the key
            # mechanism that turns the bipartite map into a CHT-pairing
            # source via set-intersection in the consumer.
            #
            # Skipped if the caller's bc_filter excludes walls.
            #
            # We still batch-read the wall family state (one round-trip)
            # to get thermal_condition cheaply — that IS in get_state().
            # But shadow_face_zone and adjacent_cell_zone are Queries and
            # must be called per-instance.
            wall_in_scope = "wall" in families
            wall_node = getattr(bc, "wall", None)
            if wall_in_scope and wall_node is not None:
                walls_state = _read_family_state(wall_node)
                for wname, wstate in walls_state.items():
                    if not isinstance(wstate, dict):
                        continue
                    # Only coupled walls have a meaningful shadow.
                    thermal = wstate.get("thermal") or {}
                    if not isinstance(thermal, dict):
                        continue
                    if thermal.get("thermal_condition") != "Coupled":
                        continue
                    # shadow_face_zone is a Query — call it.
                    try:
                        sfz_node = getattr(wall_node[wname], "shadow_face_zone", None)
                        shadow = str(sfz_node()) if sfz_node is not None else None
                    except Exception:
                        shadow = None
                    if not shadow:
                        continue
                    # Shadow wall's ACZ — also a Query.
                    try:
                        shadow_acz_node = getattr(wall_node[shadow], "adjacent_cell_zone", None)
                        shadow_acz = str(shadow_acz_node()) if shadow_acz_node is not None else None
                    except Exception:
                        shadow_acz = None
                    if shadow_acz and str(shadow_acz) in cz_to_faces:
                        cz_to_faces[str(shadow_acz)].add(wname)
                    # Symmetric: original wall's cellzone also "sees" shadow.
                    try:
                        my_acz_node = getattr(wall_node[wname], "adjacent_cell_zone", None)
                        my_acz = str(my_acz_node()) if my_acz_node is not None else None
                    except Exception:
                        my_acz = None
                    if my_acz and str(my_acz) in cz_to_faces:
                        cz_to_faces[str(my_acz)].add(shadow)

            return {cz: sorted(cz_to_faces[cz]) for cz in requested}

        from ansys.fluent.mcp.common.timings import get_collector as _get_timings

        with _get_timings().time("backend", "mesh_adjacency_probe"):
            async with self._lock:
                return await asyncio.to_thread(_do)

    async def get_command_arguments(self, path: str) -> dict[str, Any] | None:
        """Introspect a Command's keyword-argument signature via PyFluent.

        Parameters
        ----------
        path : str
            Fluent object path or file-system path to inspect.

        Returns
        -------
        dict[str, Any] | None
            Mapping containing the operation result.
        """

        def _do() -> dict[str, Any] | None:
            """Execute the nested helper for the enclosing operation.

            Returns
            -------
            dict[str, Any] | None
                Mapping containing the operation result.
            """
            root = self._settings_root()
            try:
                node = resolve_path(root, path)
            except (AttributeError, KeyError, TypeError):
                return None
            # PyFluent Command objects expose ``argument_names`` (tuple of
            # str) and per-argument settings nodes accessible by attribute.
            # ``argument_names`` is REQUIRED on Command/Query types — its
            # absence means ``node`` is not a Command at all.
            arg_names = getattr(node, "argument_names", None)
            if arg_names is None:
                return None
            try:
                names = [str(n) for n in arg_names]
            except TypeError:
                return None
            # No-arg Commands (e.g. ``hybrid_initialize``) report an
            # empty tuple — return the empty signature explicitly so the
            # caller can distinguish 'no arguments' from 'not a command'.
            if not names:
                return {"argument_names": [], "arguments": {}}
            args: dict[str, Any] = {}
            for n in names:
                child = getattr(node, n, None)
                if child is None:
                    args[n] = {}
                    continue
                info: dict[str, Any] = {}
                cls = type(child)
                # Most argument nodes have a ``_python_name`` and one of
                # the base classes (String/Integer/Real/Boolean/StringList).
                bases = [b.__name__ for b in cls.__mro__[:4]]
                info["type_hint"] = next(
                    (
                        b
                        for b in bases
                        if b
                        in {
                            "String",
                            "Integer",
                            "Real",
                            "Boolean",
                            "StringList",
                            "RealList",
                            "IntegerList",
                            "Filename",
                        }
                    ),
                    bases[0] if bases else "unknown",
                )

                attrs_fn = getattr(child, "get_attrs", None)
                if callable(attrs_fn):
                    try:
                        raw = attrs_fn(["active?", "allowed-values"]) or {}
                    except Exception:
                        raw = {}
                    if isinstance(raw, dict):
                        is_active_flag = raw.get("active?")
                        if is_active_flag is not None:
                            info["is_active"] = bool(is_active_flag)
                        allowed = raw.get("allowed-values")
                        if isinstance(allowed, list) and allowed and info.get("is_active", True):
                            info["allowed_values"] = list(allowed)[:25]
                else:
                    is_active = getattr(child, "is_active", None)
                    active_ok = True
                    if callable(is_active):
                        try:
                            active_ok = bool(is_active())
                            info["is_active"] = active_ok
                        except Exception as exc:
                            logger.debug("is_active() failed for %s: %s", n, exc, exc_info=True)
                    if active_ok:
                        fn = getattr(child, "allowed_values", None)
                        if callable(fn):
                            try:
                                vals = list(fn())
                                if vals:
                                    info["allowed_values"] = vals[:25]
                            except Exception as exc:
                                logger.debug(
                                    "allowed_values() failed for %s: %s",
                                    n,
                                    exc,
                                    exc_info=True,
                                )
                args[n] = info
            return {"argument_names": names, "arguments": args}

        async with self._lock:
            return await asyncio.to_thread(_do)

    async def describe_named_object_template(self, path: str) -> dict[str, Any] | None:
        """Describe the field shape of a fresh child of a NamedObject collection.

        Uses PyFluent's static settings classes (``child_object_type``)
        so we never have to create-and-delete a transient object on the
        live session. Returns a flat ``{field_name: {type_hint, allowed_values?, child_kind}}``
        map plus the create-command signature when present.

        Parameters
        ----------
        path : str
            Fluent object path or file-system path to inspect.

        Returns
        -------
        dict[str, Any] | None
            Mapping containing the operation result.
        """

        def _do() -> dict[str, Any] | None:
            """Execute the nested helper for the enclosing operation.

            Returns
            -------
            dict[str, Any] | None
                Mapping containing the operation result.
            """
            root = self._settings_root()
            try:
                node = resolve_path(root, path)
            except (AttributeError, KeyError, TypeError):
                return None
            child_cls = getattr(node, "child_object_type", None)
            if child_cls is None:
                return None
            # ``command_names`` and ``argument_names`` come from PyFluent
            # base classes; child_names lists settings child attributes.
            try:
                child_names = list(getattr(child_cls, "child_names", []) or [])
            except Exception:
                child_names = []

            # Field types are NOT class attributes on ``child_object_type``;
            # PyFluent generates per-instance leaf classes lazily. Borrow
            # one existing live instance to introspect each field's actual
            # base class. Falls back to ``unknown`` only when no instance
            # exists yet AND the field is not exposed on the template.
            sample_key: Any = None
            try:
                live_keys = list(node.get_object_names())
            except Exception:
                live_keys = []
            if live_keys:
                sample_key = live_keys[0]
            sample_inst = None
            if sample_key is not None:
                try:
                    sample_inst = node[sample_key]
                except Exception:
                    sample_inst = None

            _scalar_base = {
                "String",
                "Integer",
                "Real",
                "Boolean",
                "StringList",
                "RealList",
                "IntegerList",
                "Filename",
                "Group",
                "NamedObject",
                "Object",
            }
            # Pull every per-leaf attr in a SINGLE Scheme RPC instead of
            # up to 4 round-trips per leaf (allowed_values + min + max +
            # default + units …). The batched ``get_attrs`` returns the
            # subset the leaf actually exposes — missing keys are simply
            # absent.
            _leaf_attrs = [
                "active?",
                "read-only?",
                "user-creatable?",
                "allowed-values",
                "min",
                "max",
                "default",
                "units-quantity",
            ]
            fields: dict[str, Any] = {}
            for name in child_names[:60]:  # cap to keep payload small
                bases: list[str] = []
                leaf = getattr(sample_inst, name, None) if sample_inst is not None else None
                # Preferred: read the live leaf's class mro.
                if leaf is not None:
                    bases = [b.__name__ for b in type(leaf).__mro__[:6]]
                # Fallback: child_object_type may expose the leaf class
                # for some collections (older builds).
                if not bases:
                    attr = getattr(child_cls, name, None)
                    if isinstance(attr, type):
                        bases = [b.__name__ for b in attr.__mro__[:6]]
                type_hint = next(
                    (b for b in bases if b in _scalar_base),
                    bases[0] if bases else "unknown",
                )
                info: dict[str, Any] = {"type_hint": type_hint}
                # Single batched get_attrs() per leaf — replaces the
                # legacy sequential allowed_values()/min()/max() chain.
                if leaf is not None:
                    fn = getattr(leaf, "get_attrs", None)
                    if callable(fn):
                        try:
                            raw = fn(_leaf_attrs) or {}
                        except Exception:
                            raw = {}
                        if isinstance(raw, dict):
                            allowed = raw.get("allowed-values")
                            if isinstance(allowed, list) and allowed:
                                info["allowed_values"] = list(allowed)[:25]
                            if "active?" in raw:
                                info["is_active"] = bool(raw["active?"])
                            if "read-only?" in raw:
                                info["is_read_only"] = bool(raw["read-only?"])
                            if "user-creatable?" in raw:
                                info["is_user_creatable"] = bool(raw["user-creatable?"])
                            if "min" in raw and raw["min"] is not None:
                                info["min"] = raw["min"]
                            if "max" in raw and raw["max"] is not None:
                                info["max"] = raw["max"]
                            if "default" in raw and raw["default"] is not None:
                                info["default"] = raw["default"]
                            units = raw.get("units-quantity")
                            if units:
                                info["units"] = units
                fields[name] = info
            out: dict[str, Any] = {
                "child_class": getattr(child_cls, "__name__", "unknown"),
                "fields": fields,
            }
            # Collection-level metadata in one RPC: tells callers whether
            # they may even call ``create`` on this family before they
            # bother building the command.
            coll_attrs_fn = getattr(node, "get_attrs", None)
            if callable(coll_attrs_fn):
                try:
                    coll_raw = coll_attrs_fn(["active?", "user-creatable?"]) or {}
                except Exception:
                    coll_raw = {}
                if isinstance(coll_raw, dict):
                    if "active?" in coll_raw:
                        out["is_active"] = bool(coll_raw["active?"])
                    if "user-creatable?" in coll_raw:
                        out["is_user_creatable"] = bool(coll_raw["user-creatable?"])
            # Surface the create-command signature too (most NamedObject
            # collections have a ``create`` method that takes ``name``).
            create = getattr(node, "create", None)
            arg_names = getattr(create, "argument_names", None)
            if arg_names:
                out["create_command"] = {
                    "argument_names": [str(n) for n in arg_names],
                }
            return out

        async with self._lock:
            return await asyncio.to_thread(_do)

    async def list_fields(self, *, scope: str = "any") -> dict[str, Any] | None:
        """Enumerate solver field/variable names available for reports & post.

        ``scope`` is a hint passed to Fluent's field-info API:
        ``"any"`` (default), ``"surface"``, ``"cell"``, ``"node"``.
        Returns ``{"fields": [...], "scope": scope}`` or ``None`` when
        unavailable.

        Parameters
        ----------
        scope : str
            Scope used to limit the field or API lookup.

        Returns
        -------
        dict[str, Any] | None
            Mapping containing the operation result.
        """

        def _do() -> dict[str, Any] | None:
            """Execute the nested helper for the enclosing operation.

            Returns
            -------
            dict[str, Any] | None
                Mapping containing the operation result.
            """
            solver = self._require()
            # PyFluent exposes field info under ``field_info`` on the
            # session (sometimes under ``fields``). Try several names.
            candidates = ("field_info", "fields_info", "fields")
            field_info = None
            for c in candidates:
                v = getattr(solver, c, None)
                if v is not None:
                    field_info = v
                    break
            if field_info is None:
                return None
            for fn_name in ("get_scalar_field_info", "get_scalar_fields_info", "get_fields_info"):
                fn = getattr(field_info, fn_name, None)
                if callable(fn):
                    try:
                        info = fn()
                    except Exception as exc:
                        logger.debug("%s() failed for %s: %s", fn_name, scope, exc, exc_info=True)
                        continue
                    # ``info`` is typically a dict ``{field_name: {...}}``.
                    if isinstance(info, dict):
                        names = sorted(str(k) for k in info)
                        return {"fields": names[:200], "scope": scope, "source": fn_name}
            return None

        async with self._lock:
            return await asyncio.to_thread(_do)

    async def get_targeted_context(
        self,
        *,
        paths_to_check: list[str],
        named_object_types: list[str] | None = None,
        instance_state_fetch: list[str] | None = None,
    ) -> dict[str, Any]:
        """Return the targeted context.

        Parameters
        ----------
        paths_to_check : list[str]
            Fluent object paths to validate or inspect.
        named_object_types : list[str] | None
            Named-object families that should be considered during lookup.
        instance_state_fetch : list[str] | None
            Whether named-object instance state should be fetched.

        Returns
        -------
        dict[str, Any]
            Mapping containing the operation result.
        """
        if not paths_to_check:
            raise InvalidArgumentsError("paths_to_check must be non-empty")

        def _do() -> dict[str, Any]:
            """Execute the nested helper for the enclosing operation.

            Returns
            -------
            dict[str, Any]
                Mapping containing the operation result.
            """
            return collect_targeted_context(
                self._settings_root(),
                paths_to_check=paths_to_check,
                named_object_types=named_object_types or [],
                instance_state_fetch=instance_state_fetch or [],
            )

        async with self._lock:
            return await asyncio.to_thread(_do)

    # ------------------------------------------------------------------
    # Code execution
    # ------------------------------------------------------------------

    def _diagnose_command_call_error(
        self,
        code: str,
        exc: BaseException,
    ) -> str | None:
        """Best-effort hint when a snippet trips a Settings-API call shape.

        PyFluent's settings tree mixes three shapes that look identical
        at the call site but bind differently:

        * **Command** (``solver.setup.materials.database.copy_by_name``)
          — kwargs only; ``argument_names`` is the canonical signature.
        * **NamedObject family** (``boundary_conditions.wall``,
          ``materials.fluid``) — must be indexed with ``[name]``;
          calling ``family(arg)`` triggers ``set_state(arg)`` which
          raises an opaque internal error
          (``'X' object has no attribute '_has_migration_adapter'``).
        * **Property leaf** — assignment, not call.

        A caller cannot tell which is which from the traceback alone.
        This helper inspects the user's source AST for ``Call`` nodes
        rooted at ``solver``/``session``, resolves each to a live
        settings node, and — when the failure pattern matches one of
        the three known shapes — returns a multi-line hint string the
        caller can append to ``stderr`` and ``message``.

        Returns ``None`` when nothing useful can be said (so the
        caller leaves the original error untouched).

        Parameters
        ----------
        code : str
            Python code snippet to validate or execute.
        exc : BaseException
            Exc to supply to the function.

        Returns
        -------
        str | None
            String result produced by the function.
        """
        msg = str(exc)
        is_call_shape = (
            isinstance(exc, TypeError) and "__call__()" in msg and "positional argument" in msg
        )
        is_setstate_probe = isinstance(exc, AttributeError) and "_has_migration_adapter" in msg
        if not (is_call_shape or is_setstate_probe):
            return None

        # Parse defensively — the snippet already executed once, so it
        # must parse, but a future edit might pre-validate against a
        # newer grammar.
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return None

        try:
            root = self._settings_root()
        except Exception:  # diagnostic must not raise
            return None

        def _chain(node: ast.AST) -> list[str] | None:
            """Return ['solver','setup','materials','database',...] or None.

            Parameters
            ----------
            node : ast.AST
                Node to supply to the function.

            Returns
            -------
            list[str] | None
                Collection containing the operation results.
            """
            parts: list[str] = []
            cur = node
            while isinstance(cur, ast.Attribute):
                parts.append(cur.attr)
                cur = cur.value
            if not isinstance(cur, ast.Name):
                return None
            parts.append(cur.id)
            parts.reverse()
            return parts

        def _resolve(parts: list[str]) -> Any | None:
            """Resolve a value from the configured inputs.

            Parameters
            ----------
            parts : list[str]
                Path segments that make up the Fluent object reference.

            Returns
            -------
            Any | None
                Optional value produced by the operation.
            """
            if not parts or parts[0] not in {"solver", "session"}:
                return None
            tail = parts[1:]
            # ``solver.settings.foo`` and ``solver.foo`` both resolve
            # against the same root (``_settings_root`` already strips
            # the ``settings`` accessor when present).
            if tail and tail[0] == "settings":
                tail = tail[1:]
            if not tail:
                return root
            try:
                return resolve_path(root, ".".join(tail))
            except (AttributeError, KeyError, TypeError):
                return None

        hints: list[str] = []
        seen: set[str] = set()

        for sub in ast.walk(tree):
            if not isinstance(sub, ast.Call):
                continue
            chain = _chain(sub.func)
            if chain is None:
                continue
            dotted = ".".join(chain)
            if dotted in seen:
                continue
            seen.add(dotted)
            target = _resolve(chain)
            if target is None:
                continue

            # Pattern A: target is a Command — list its kwargs.
            arg_names = getattr(target, "argument_names", None)
            if arg_names is not None:
                try:
                    names = [str(n) for n in arg_names]
                except TypeError:
                    names = []
                arg_lines: list[str] = []
                for n in names:
                    child = getattr(target, n, None)
                    bits = [n]
                    if child is not None:
                        bases = [b.__name__ for b in type(child).__mro__[:4]]
                        kind = next(
                            (
                                b
                                for b in bases
                                if b
                                in {
                                    "String",
                                    "Integer",
                                    "Real",
                                    "Boolean",
                                    "StringList",
                                    "RealList",
                                    "IntegerList",
                                    "Filename",
                                }
                            ),
                            None,
                        )
                        if kind:
                            bits.append(f"({kind})")
                        fn = getattr(child, "allowed_values", None)
                        if callable(fn):
                            try:
                                vals = list(fn())
                                if vals:
                                    sample = ", ".join(repr(v) for v in vals[:8])
                                    if len(vals) > 8:
                                        sample += f", … (+{len(vals) - 8} more)"
                                    bits.append(f"allowed=[{sample}]")
                            except Exception as exc:
                                logger.debug(
                                    "allowed_values() failed for %s.%s: %s",
                                    dotted,
                                    n,
                                    exc,
                                    exc_info=True,
                                )
                    arg_lines.append("    - " + " ".join(bits))
                example_kwargs = ", ".join(f"{n}=..." for n in names) or "(no arguments)"
                hints.append(
                    f"[hint] '{dotted}' is a Command. Call it with "
                    f"keyword arguments only:\n"
                    f"    {dotted}({example_kwargs})\n"
                    f"  Argument signature:\n"
                    + ("\n".join(arg_lines) if arg_lines else "    (no arguments)")
                )
                continue

            # Pattern B: target is a NamedObject family — must be
            # indexed by [name], not called.
            if hasattr(target, "get_object_names"):
                try:
                    current = list(target.get_object_names())
                except Exception:
                    current = []
                sample = ", ".join(repr(n) for n in current[:6])
                if len(current) > 6:
                    sample += f", … (+{len(current) - 6} more)"
                hints.append(
                    f"[hint] '{dotted}' is a NamedObject family — "
                    f"index it with [name], do NOT call it:\n"
                    f"    {dotted}['<name>']    # e.g. one of: "
                    f"{sample or '(none yet)'}\n"
                    f"  Calling '{dotted}(...)' triggers a set_state "
                    f"on the family and raises the internal "
                    f"'_has_migration_adapter' error you just saw."
                )
                continue

            # Pattern C: anything else that isn't a callable — guide
            # the user toward .get_state() / assignment.
            if is_setstate_probe and not callable(target):
                kind = type(target).__name__
                hints.append(
                    f"[hint] '{dotted}' is a {kind} settings node, "
                    "not a function. Read it with `.get_state()` or "
                    "assign with `=`."
                )

        if not hints:
            return None
        return "\n\n".join(hints)

    # ------------------------------------------------------------------
    # Code execution
    # ------------------------------------------------------------------

    async def run_code(
        self,
        code: str,
        *,
        namespace: dict[str, Any] | None = None,
        filename: str = "<ansys-fluent-mcp>",
    ) -> RunCodeResult:
        """Execute Python code through the backend runtime.

        Parameters
        ----------
        code : str
            Python code or command text to execute or validate.
        namespace : dict[str, Any] | None
            Namespace used to resolve the backend object or route.
        filename : str
            File name or path used by the backend operation.

        Returns
        -------
        RunCodeResult
            RunCodeResult produced by the operation.
        """
        if not code or not code.strip():
            raise InvalidArgumentsError("code must be a non-empty string")

        # Strict sandbox: block arbitrary imports / top-level names
        # outside the injected `solver`/`session` and a small builtin
        # whitelist. Catches the worst host-authored invalid snippets before exec.
        # When a caller supplies a persistent namespace they are using
        # the REPL surface explicitly — bound names from prior cells
        # would otherwise be flagged as "unknown free name". We still
        # enforce the import allow-list, dunder block and forbidden-call
        # list; we just widen the allowed-name set with the keys the
        # caller has already bound (plus the always-present
        # ``solver``/``session``).
        if namespace is None:
            check = validate_python_source(code, strict=True)
        else:
            check = validate_python_source(
                code,
                strict=True,
                extra_allowed_names=tuple(namespace.keys()),
            )
        if check.status == "error":
            return check

        # Reflection-write guard (Phase 1a). Block ``setattr`` /
        # ``__setitem__`` / ``__setattr__`` etc. that could smuggle a
        # mutation past the schema / read-only guards. Settings writes
        # use direct attribute assignment or ``.set_state``.
        reflection = _scan_reflection_writes(code)
        if reflection:
            return RunCodeResult(
                status="error",
                error_code="forbidden_call",
                message=(
                    "Reflection-based writes are forbidden: "
                    f"{sorted(set(reflection))}. Use direct attribute "
                    "assignment (solver.x.y = value) or .set_state(...)."
                ),
            )

        # Stateless intent guard: catch a fixed set of Fluent-specific
        # crash signatures (BC rename with whitespace, VOF count direct-
        # assign, intra-snippet use-before-create on named expressions,
        # phase-material assignment before phase rename, setup writes
        # while iterating). See solve/lib/intent_guard.py. Disable with
        # ``FLUIDS_MCP_INTENT_GUARD=0``.
        guard_warnings: list[str] = []
        if _intent_guard.is_enabled():
            live_named: Mapping[str, list[str]] = self._probe_live_named_for_guard()
            iterating = self._probe_iterating_for_guard()
            report = _intent_guard.evaluate(
                code,
                live_named_objects=live_named,
                iterating=iterating,
            )
            if report.has_blocking:
                return report.to_run_code_result()
            # Non-blocking advisories (e.g. unit-less named expressions,
            # `.tui.*` usage) are surfaced on the successful result so the
            # caller — and any external MCP host — still sees the hint.
            guard_warnings = [f.message for f in report.findings if f.severity == "warn"]

        def _do() -> RunCodeResult:
            """Execute the nested helper for the enclosing operation.

            Returns
            -------
            RunCodeResult
                RunCodeResult produced by the operation.
            """
            solver = self._require()
            stdout = io.StringIO()
            stderr = io.StringIO()
            # If caller provided a namespace, reuse it so variables
            # bound in earlier `run_code` calls remain in scope (REPL
            # semantics). Always re-bind solver/session — these are
            # injected by the runtime and must point at the live
            # session, never at whatever a prior cell may have shadowed.
            #
            # Restricted ``__builtins__``: we install only the names our
            # AST validator allows, so even a sandbox-bypass that
            # smuggled past ``validate_python_source`` cannot reach
            # ``__import__``, ``eval``, ``open``, etc. through the
            # runtime ``builtins`` module.
            safe_builtins = _build_safe_builtins()
            if namespace is None:
                local_ns: dict[str, Any] = {
                    "solver": solver,
                    "session": solver,
                    "__builtins__": safe_builtins,
                }
            else:
                local_ns = namespace
                local_ns["solver"] = solver
                local_ns["session"] = solver
                local_ns["__builtins__"] = safe_builtins

            # Jupyter-style "auto-display": if the snippet's last
            # statement is an expression, evaluate it separately and
            # print its repr (when not None and stdout was empty for
            # that line). Lets callers write `solver.setup.models.energy`
            # without an explicit print and still see the value.
            try:
                tree = ast.parse(code, filename=filename, mode="exec")
            except SyntaxError as exc:
                return RunCodeResult(
                    status="error",
                    error_code="syntax_error",
                    stdout="",
                    stderr=f"SyntaxError: {exc}",
                    message=str(exc),
                )

            last_expr_node: ast.Expression | None = None
            body = list(tree.body)
            if body and isinstance(body[-1], ast.Expr):
                last = cast(ast.Expr, body.pop())
                last_expr_node = ast.Expression(body=last.value)
                ast.copy_location(last_expr_node, last)

            try:
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    if body:
                        exec_tree = ast.Module(body=body, type_ignores=[])
                        exec(  # noqa: S102  # nosec B102
                            compile(exec_tree, filename, "exec"),
                            local_ns,
                            local_ns,
                        )
                    auto_value: Any = None
                    if last_expr_node is not None:
                        auto_value = eval(  # noqa: S307  # nosec B307
                            compile(last_expr_node, filename, "eval"),
                            local_ns,
                            local_ns,
                        )
                        # Auto-display the last expression (REPL-style).
                        # ``print`` here writes into the captured ``stdout``
                        # buffer (we are inside ``redirect_stdout``), not
                        # the gateway's stdout — the value also flows out
                        # via ``RunCodeResult.return_value``.
                        if auto_value is not None:
                            print(repr(auto_value))
                # ``__return__`` is an opt-in override the user code can
                # set; honor it when present *and* non-None, otherwise
                # fall back to the auto-displayed last-expression value
                # so explicitly setting ``__return__ = None`` doesn't
                # accidentally hide the auto value.
                explicit = local_ns.get("__return__")
                stdout_payload = stdout.getvalue()
                # Post-call hint for the well-known "list_materials only
                # shows fluids" Fluent quirk. Without this callers see
                # a list with no solids and falsely concludes those
                # materials are absent from the database.
                if 'Listing "fluid" materials' in stdout_payload and ("list_materials" in code):
                    stdout_payload += (
                        "\n[hint] database.list_materials() prints the "
                        "FLUID half only by default; SOLID, MIXTURE, "
                        "and PARTICLE materials in the shipped "
                        "database are NOT shown above and DO exist. "
                        "Do NOT enumerate to 'verify' a material — use "
                        "the dedicated `copy_material` tool, or call "
                        "`copy_by_name(type=<known type>, name=<name>)` "
                        "directly. If the name is wrong Fluent raises a "
                        "clear error; that is the only signal that "
                        "matters.\n"
                    )
                return RunCodeResult(
                    status="ok",
                    stdout=stdout_payload,
                    stderr=stderr.getvalue(),
                    return_value=explicit if explicit is not None else auto_value,
                )
            except Exception as exc:  # surface to callers
                logger.exception("PyFluent run_code failed")
                tb = traceback.format_exc(limit=8)
                # Dead-channel detection: classify gRPC / channel-closed
                # failures distinctly so callers (and ``session_status``)
                # learn the truth on the very next call instead of
                # bouncing off a zombie ``self._solver`` reference for
                # several round-trips.
                if _looks_like_dead_channel(exc):
                    self._mark_solver_disconnected()
                    return RunCodeResult(
                        status="error",
                        error_code="solver_disconnected",
                        stdout=stdout.getvalue(),
                        stderr=stderr.getvalue() + "\n" + tb,
                        message=(
                            "Fluent gRPC channel was lost during the call. "
                            "Reconnect with `connect` and re-load any "
                            "case/data before retrying."
                        ),
                    )
                # Best-effort: when the failure looks like a Settings
                # API call-shape mistake (positional arg on a Command,
                # ``(...)`` on a NamedObject family, etc.), append the
                # discovered argument signature so the caller can fix it on
                # the next attempt instead of hallucinating workarounds.
                hint = self._diagnose_command_call_error(code, exc)
                stderr_payload = stderr.getvalue() + "\n" + tb
                if hint:
                    stderr_payload += "\n" + hint
                return RunCodeResult(
                    status="error",
                    error_code="execution_error",
                    stdout=stdout.getvalue(),
                    stderr=stderr_payload,
                    message=str(exc) + (f"\n{hint}" if hint else ""),
                )

        try:
            from ansys.fluent.mcp.common.backend_trace import trace_call
            from ansys.fluent.mcp.common.timings import get_collector as _get_timings

            trace_call("run_code", summary=f"chars={len(code)}")
            with _get_timings().time("backend", "run_code"):
                async with self._lock:
                    result = await asyncio.to_thread(_do)
            # Attach non-blocking guard advisories to a successful run.
            if guard_warnings and result.status == "ok":
                result.warnings = list(result.warnings or []) + guard_warnings
        finally:
            # Mutating call → invalidate cached named objects / state.
            self.invalidate_live_caches()
            self.maybe_invalidate_mesh_cache(code)
        # Activity log: per-snippet trace into the session log file.
        # Gated on logger level so disabled-state has zero overhead
        # beyond a single attribute lookup.
        try:
            from ansys.fluent.mcp.common.activity_logging import SESSION_LOGGER

            if SESSION_LOGGER.isEnabledFor(logging.INFO):
                from ansys.fluent.mcp.common.activity_logging import truncate_text

                SESSION_LOGGER.info(
                    "run_code status=%s error_code=%s stdout_bytes=%d stderr_bytes=%d code=%r",
                    result.status,
                    getattr(result, "error_code", None),
                    len(result.stdout or ""),
                    len(result.stderr or ""),
                    truncate_text(code, limit=1000),
                )
                if SESSION_LOGGER.isEnabledFor(logging.DEBUG):
                    stdout_brief = truncate_text(
                        result.stdout or "",
                        limit=600,
                    )
                    stderr_brief = truncate_text(
                        result.stderr or "",
                        limit=600,
                    )
                    if stdout_brief.strip():
                        SESSION_LOGGER.debug(
                            "run_code stdout: %s",
                            stdout_brief,
                        )
                    if stderr_brief.strip():
                        SESSION_LOGGER.debug(
                            "run_code stderr: %s",
                            stderr_brief,
                        )
        except Exception as exc:  # logging must never raise
            logger.debug("run_code activity log failed: %s", exc, exc_info=True)
        return result

    # ------------------------------------------------------------------
    # Help / status / mode info
    # ------------------------------------------------------------------

    async def get_help(self, path: str) -> dict[str, Any]:
        """Return ``{path, doc, kind, child_names, allowed_values}``.

        Parameters
        ----------
        path : str
            Fluent object path or file-system path to inspect.

        Returns
        -------
        dict[str, Any]
            Mapping containing the operation result.
        """
        if not path or not path.strip():
            raise InvalidArgumentsError("path must be non-empty")

        def _do() -> dict[str, Any]:
            """Execute the nested helper for the enclosing operation.

            Returns
            -------
            dict[str, Any]
                Mapping containing the operation result.
            """
            root = self._settings_root()
            try:
                node = resolve_path(root, path)
            except (AttributeError, KeyError, TypeError) as exc:
                return {"path": path, "error": f"unresolvable: {exc}"}
            doc = (getattr(node, "__doc__", None) or "").strip()
            kind = type(node).__name__
            child_names: list[str] = []
            for accessor in ("child_names", "_child_names"):
                attr = getattr(node, accessor, None)
                if isinstance(attr, (list, tuple)):
                    child_names = [str(n) for n in attr]
                    break
            allowed: list[Any] = []
            for accessor in ("allowed_values", "get_allowed_values"):
                fn = getattr(node, accessor, None)
                if callable(fn):
                    try:
                        allowed = list(fn())
                        break
                    except Exception as exc:
                        logger.debug("%s() failed for %s: %s", accessor, path, exc, exc_info=True)
                        continue
            result: dict[str, Any] = {
                "path": path,
                "doc": doc[:1500],
                "kind": kind,
                "child_names": child_names[:60],
                "allowed_values": allowed[:50],
            }
            # graphics_objects is a dynamic named container whose entries
            # are created via set_state, not by indexing with existing names.
            if "graphics_objects" in path:
                result["note"] = (
                    "Add entries via set_state({'<obj-name>': {'name': '<obj-name>', "
                    "'transparency': 0-100}}). "
                    "Transparency is only active for mesh objects, not vectors."
                )
            return result

        async with self._lock:
            return await asyncio.to_thread(_do)

    async def mesh_counts(self) -> dict[str, int | None]:
        """Probe live mesh element totals via Fluent Scheme.

        Returns ``{"cell_count", "face_count", "node_count"}``; each
        value is ``int`` when the Scheme call resolved or ``None``
        when unavailable (no mesh loaded, partition pending, Scheme
        call failed). Never raises — surfaces failures as an all-
        ``None`` payload so callers can branch on ``is None`` without
        try/except.

        Why Scheme: Fluent does not surface mesh-element totals on
        the settings tree. The canonical accessor is
        ``(inquire-grids)`` — it returns a list whose LAST element is
        the global grid summary in the shape
        ``(<id-or-name> cells faces nodes ...)``. ``cadr``/``caddr``/
        ``cadddr`` extract the three counts. This matches the pattern
        Fluent itself uses internally (e.g. in
        ``wb-is-data-file-compatible?`` for cross-file count checks)
        and is stable across versions back to 19.0. ``rpgetvar
        'tinfo/n-cells`` does NOT exist as an rpvar.

        Returns
        -------
        dict[str, int | None]
            Mapping containing the operation result.
        """
        empty: dict[str, int | None] = {
            "cell_count": None,
            "face_count": None,
            "node_count": None,
        }
        if self._solver is None:
            return empty
        cached = self._mesh_cache_get("mesh_counts")
        if cached is not None:
            return cached
        from ansys.fluent.mcp.common.backend_trace import trace_call

        trace_call("mesh_counts")

        # Ask Fluent for cells / faces / nodes in a single round-trip:
        # (inquire-grids) -> ((<g0> ...) ... (<gN> cells faces nodes ...))
        # The last element is the global summary; cadr/caddr/cadddr
        # pull the three counts. Wrapped in `if (pair? ...)` to return
        # an empty list when no mesh is loaded so Python sees `[]`/`()`
        # instead of a Scheme error.
        _mesh_count_scheme = (
            "(let ((__all (inquire-grids))) "
            "  (if (pair? __all) "
            "      (let ((__g (car (reverse __all)))) "
            "        (list (cadr __g) (caddr __g) (cadddr __g))) "
            "      '()))"
        )

        def _to_int(raw: Any) -> int | None:
            """Convert a value to an integer.

            Parameters
            ----------
            raw : Any
                Raw string value to parse or validate.

            Returns
            -------
            int | None
                Optional value produced by the operation.
            """
            if raw is None or raw is False:
                return None
            try:
                n = int(raw)
            except (TypeError, ValueError):
                try:
                    n = int(float(raw))
                except (TypeError, ValueError):
                    return None
            # Counts are always positive when a mesh is loaded; treat
            # zero as "no mesh" (matches Fluent's pre-load behavior
            # where the surface evaluates to 0 / nil).
            return n if n > 0 else None

        def _do() -> dict[str, int | None]:
            """Execute the nested helper for the enclosing operation.

            Returns
            -------
            dict[str, int | None]
                Mapping containing the operation result.
            """
            solver = self._solver
            if solver is None:
                return empty
            scheme = getattr(solver, "scheme", None) or getattr(solver, "scheme_eval", None)
            if scheme is None:
                return empty
            try:
                if hasattr(scheme, "eval"):
                    raw = scheme.eval(_mesh_count_scheme)
                else:
                    raw = scheme(_mesh_count_scheme)
            except Exception:  # fail-soft per docstring
                return empty
            # Expect a 3-element sequence (cells faces nodes). Anything
            # shorter means no mesh / partial state.
            if not isinstance(raw, (list, tuple)) or len(raw) < 3:
                return empty
            return {
                "cell_count": _to_int(raw[0]),
                "face_count": _to_int(raw[1]),
                "node_count": _to_int(raw[2]),
            }

        try:
            async with self._lock:
                counts = await asyncio.to_thread(_do)
        except Exception:  # boundary
            return empty
        if any(v is not None for v in counts.values()):
            self._mesh_cache_put("mesh_counts", counts)
        return counts

    async def mesh_quality(self) -> dict[str, float | None]:
        """Return mesh quality information from the backend.

        Returns
        -------
        dict[str, float | None]
            Mapping containing the operation result.
        """
        from ansys.fluent.mcp.solve.backends.mesh_report_parsers import (
            parse_mesh_quality,
        )

        empty: dict[str, float | None] = {
            "min_orthogonal_quality": None,
            "max_ortho_skew": None,
            "max_aspect_ratio": None,
        }
        if self._solver is None:
            return empty
        cached = self._mesh_cache_get("mesh_quality")
        if cached is not None:
            return cached
        from ansys.fluent.mcp.common.backend_trace import trace_call

        trace_call("mesh_quality")

        try:
            result = await self.run_code("session.settings.mesh.quality()")
        except Exception:  # fail-soft per contract
            return empty
        if getattr(result, "status", None) != "ok":
            return empty
        parsed = parse_mesh_quality(getattr(result, "stdout", "") or "")
        self._mesh_cache_put("mesh_quality", parsed)
        return parsed

    async def mesh_check(self) -> dict[str, Any]:
        """Run the backend mesh check operation.

        Returns
        -------
        dict[str, Any]
            Mapping containing the operation result.
        """
        from ansys.fluent.mcp.solve.backends.mesh_report_parsers import (
            parse_mesh_check,
        )

        empty: dict[str, Any] = {
            "domain_extents": {"x": None, "y": None, "z": None},
            "volume_min": None,
            "volume_max": None,
            "volume_total": None,
            "face_area_min": None,
            "face_area_max": None,
            "warnings": [],
            "errors": [],
            "raw": "",
        }
        if self._solver is None:
            return empty
        cached = self._mesh_cache_get("mesh_check")
        if cached is not None:
            return cached
        from ansys.fluent.mcp.common.backend_trace import trace_call

        trace_call("mesh_check")

        try:
            result = await self.run_code("session.settings.mesh.check()")
        except Exception:  # fail-soft per contract
            return empty
        if getattr(result, "status", None) != "ok":
            return empty
        parsed = parse_mesh_check(getattr(result, "stdout", "") or "")
        self._mesh_cache_put("mesh_check", parsed)
        return parsed

    async def solver_status(self) -> dict[str, Any]:
        """Best-effort summary of where the solver currently is.

        Returns
        -------
        dict[str, Any]
            Mapping containing the operation result.
        """
        from ansys.fluent.mcp.common.backend_trace import trace_call

        trace_call("solver_status")

        def _do() -> dict[str, Any]:
            """Execute the nested helper for the enclosing operation.

            Returns
            -------
            dict[str, Any]
                Mapping containing the operation result.
            """
            root = self._settings_root()
            out: dict[str, Any] = {}
            try:
                init = resolve_path(root, "solution.initialization")
                out["initialized"] = bool(getattr(init, "is_initialized", lambda: False)())
            except Exception:
                out["initialized"] = None
            try:
                rc = resolve_path(root, "solution.run_calculation")
                state = rc.get_state() if hasattr(rc, "get_state") else {}
                if isinstance(state, dict):
                    for k in ("iter_count", "number_of_iterations", "iterations"):
                        if k in state:
                            out["iterations"] = state[k]
                            break
            except Exception as exc:
                logger.debug("solver_status: run_calculation probe failed: %s", exc, exc_info=True)
            try:
                solv = resolve_path(root, "setup.general.solver")
                state = solv.get_state() if hasattr(solv, "get_state") else {}
                if isinstance(state, dict) and "time" in state:
                    out["solver_mode"] = (
                        "transient"
                        if str(state["time"]).lower().startswith("unsteady")
                        else "steady"
                    )
            except Exception as exc:
                logger.debug("solver_status: solver_mode probe failed: %s", exc, exc_info=True)
            # UTL probe: setup.physics.is_active() is the canonical
            # signal — present in BOTH families, only active when the
            # 'utl feature is enabled. Best-effort; absence treated
            # as standard mode (False).
            try:
                phys = resolve_path(root, "setup.physics")
                fn = getattr(phys, "is_active", None)
                out["utl_enabled"] = bool(fn()) if callable(fn) else False
            except Exception:
                out["utl_enabled"] = False
            return out

        async with self._lock:
            return await asyncio.to_thread(_do)

    async def validate_code(self, code: str) -> RunCodeResult:
        """Validate code.

        Parameters
        ----------
        code : str
            Python code or command text to execute or validate.

        Returns
        -------
        RunCodeResult
            RunCodeResult produced by the operation.
        """
        # ``strict=True`` enforces the AST import allow-list and
        # top-level Name allow-list (``solver`` / ``session`` /
        # ``ansys.fluent.core`` only). It catches host-generated
        # snippets that import ``os`` / ``subprocess`` / hand-rolled
        # helpers that the sandbox would reject at run time.
        result = validate_python_source(code, strict=True)
        if result.status != "ok":
            return result

        # Best-effort semantic check: extract settings API paths from the
        # AST and verify them against the bundled api_objects.json index.
        # This catches plausible-looking but wrong attribute names (e.g.
        # ``fluid["zone"].material_name`` → the real path is
        # ``fluid["zone"].general.material``) before the code ever reaches
        # the live solver. The check is best-effort: if the index is not
        # available (no api_objects.json found) we skip silently.
        #
        # Paths the index reports as completely unknown (i.e. no
        # similar path of distance ≤ 2 from the leaf token) are
        # promoted from warnings to a structured ``unknown_settings_path``
        # error, because such tokens almost always signal a
        # hallucinated API call rather than a typo. Paths that have a
        # plausible nearby match stay as warnings so clients can
        # autocorrect without aborting the whole snippet.
        warnings: list[str] = []
        hallucinated: list[tuple[str, str]] = []
        try:
            tree = ast.parse(code)
            paths = _extract_settings_paths(tree)
            if paths:
                from ansys.fluent.mcp.solve.catalog.index import get_api_index_for_session

                index = get_api_index_for_session(self._session_kind)
                if index.available:
                    for path in sorted(set(paths)):
                        if index.lookup(path) is None:
                            leaf = path.rsplit(".", 1)[-1]
                            parent = path.rsplit(".", 1)[0] if "." in path else None
                            similar = index.search(
                                leaf,
                                top_k=3,
                                kinds=["Parameter", "Command"],
                                under=parent,
                            )
                            if similar and not _strict_validation_enabled():
                                hint = ", ".join(h.entry.path for h in similar[:2])
                                warnings.append(
                                    f"unknown settings path '{path}'; did you mean: {hint}"
                                )
                            else:
                                # No near-match, OR strict mode promotes
                                # every near-match miss to a hard error.
                                hallucinated.append((path, ""))
        except (SyntaxError, Exception) as exc:  # best-effort only
            logger.debug("validate_code: semantic check failed: %s", exc, exc_info=True)

        if hallucinated:
            joined = ", ".join(p for p, _ in hallucinated)
            return RunCodeResult(
                status="error",
                error_code="unknown_settings_path",
                message=(
                    "validate_code rejected the snippet: the following "
                    "settings path(s) were not found in the bundled "
                    f"Fluent API index and have no near-match: {joined}. "
                    "These are almost certainly hallucinated. Use "
                    "``find_api`` / ``probe_path`` to discover the real "
                    "path before calling ``validate_code`` again."
                ),
                warnings=warnings,
            )

        if not self.is_connected():
            return RunCodeResult(
                status="ok",
                message="parse_ok",
                warnings=warnings,
            )

        def _do() -> RunCodeResult:
            """Execute the nested helper for the enclosing operation.

            Returns
            -------
            RunCodeResult
                RunCodeResult produced by the operation.
            """
            try:
                compile(code, "<ansys-fluent-mcp:validate>", "exec")
            except SyntaxError as exc:
                return RunCodeResult(
                    status="error",
                    error_code="syntax_error",
                    message=f"SyntaxError: {exc.msg}",
                )
            return RunCodeResult(status="ok", message="parse_ok", warnings=warnings)

        return await asyncio.to_thread(_do)

    # ------------------------------------------------------------------
    # Visuals
    # ------------------------------------------------------------------

    async def screenshot(self, *, view: Optional[str] = None) -> dict[str, Any]:
        """Capture a screenshot from the backend runtime.

        Parameters
        ----------
        view : Optional[str]
            Graphics view or camera preset requested by the caller.

        Returns
        -------
        dict[str, Any]
            Mapping containing the operation result.
        """
        if self._solver is None:
            raise NotConnectedError("PyFluent backend is not connected.")

        def _do() -> dict[str, Any]:
            """Execute the nested helper for the enclosing operation.

            Returns
            -------
            dict[str, Any]
                Mapping containing the operation result.
            """
            solver = self._require()
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            tmp.close()
            try:
                save = None
                try:
                    save = solver.settings.results.graphics.picture.save_picture
                except AttributeError:
                    pass
                if save is None:
                    raise UpstreamError("Screenshot API not available on this PyFluent version.")
                save(file_name=tmp.name)
                with Path(tmp.name).open("rb") as f:
                    data = f.read()
                return {
                    "format": "png",
                    "data": base64.b64encode(data).decode("ascii"),
                    "view": view,
                }
            finally:
                try:
                    Path(tmp.name).unlink()
                except OSError:
                    pass

        return await asyncio.to_thread(_do)
