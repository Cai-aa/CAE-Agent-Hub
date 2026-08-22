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

"""Static code validation shared across backends.

AST parse plus a few cheap heuristics. Backends with a live solver
session can layer real semantic checks on top by extending `validate_code`
in their own implementation.
"""

from __future__ import annotations

import ast
from collections import OrderedDict
import hashlib
import io
import tokenize
from typing import Iterable

from ansys.fluent.mcp.common.models import RunCodeResult

# ---------------------------------------------------------------------------
# Result cache
# ---------------------------------------------------------------------------
#
# Validation is pure: same code + same allow-lists -> same RunCodeResult.
# The agent often emits short, near-identical run_code snippets (especially
# multi_edit batches that re-validate from scratch on every retry). A small
# bounded LRU keyed by (sha256(code), strict, frozensets) avoids re-walking
# the AST every turn.
_VALIDATE_CACHE_MAX = 256
_VALIDATE_CACHE: "OrderedDict[tuple[str, bool, frozenset[str], frozenset[str]], RunCodeResult]" = (
    OrderedDict()
)


def _cache_lookup(key: tuple) -> RunCodeResult | None:
    """Look up a validation result in the cache.

    Parameters
    ----------
    key : tuple
        Key used to look up or store the associated value.

    Returns
    -------
    RunCodeResult | None
        Optional value produced by the operation.
    """
    val = _VALIDATE_CACHE.get(key)
    if val is not None:
        _VALIDATE_CACHE.move_to_end(key)
    return val


def _cache_store(key: tuple, value: RunCodeResult) -> None:
    """Store a validation result in the cache.

    Parameters
    ----------
    key : tuple
        Key used to look up or store the associated value.
    value : RunCodeResult
        Value to inspect, convert, or store.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    _VALIDATE_CACHE[key] = value
    _VALIDATE_CACHE.move_to_end(key)
    while len(_VALIDATE_CACHE) > _VALIDATE_CACHE_MAX:
        _VALIDATE_CACHE.popitem(last=False)


# Patterns that almost always indicate unsafe host-authored operations.
_FORBIDDEN_CALLS: tuple[str, ...] = (
    "os.system",
    "subprocess.Popen",
    "subprocess.call",
    "subprocess.run",
    "subprocess.check_call",
    "subprocess.check_output",
    "shutil.rmtree",
    "shutil.move",
    "shutil.copy",
    "shutil.copytree",
    "eval",
    "exec",
    "compile",
    "__import__",
    "globals",
    "locals",
    "vars",
    "open",  # outside of explicit Fluent file APIs, callers should not open files
    "input",
    "exit",
    "quit",
    "breakpoint",
    "help",
)

# When ``strict=True`` the validator additionally enforces that every
# imported module is on this allow-list and every top-level Name lookup
# is one of these built-ins or one of the injected locals (``solver``,
# ``session``).
_ALLOWED_IMPORTS: frozenset[str] = frozenset(
    {
        "math",
        "json",
        "itertools",
        "functools",
        "collections",
        "dataclasses",
        "typing",
        "ansys.fluent.core",
        "ansys",
        "pyfluent",
    }
)
# Dunder names that are safe to *read* (no escape vector to
# ``__subclasses__`` / ``__globals__`` / ``__builtins__``). The AST
# validator allows attribute access and ``getattr(..., '<name>')`` for
# any name in this set; everything else dunder is rejected as
# ``forbidden_call``. ``__version__`` was the canonical missing entry
# \u2014 every module ships one and probing it is the standard way to
# verify a dependency. ``__class__`` is added because PyFluent's
# settings nodes carry useful type info on it (e.g. distinguishing a
# Parameter from a Command), and it cannot be used for object-escape
# because ``vars`` / ``globals`` / ``__subclasses__`` are independently
# blocked by ``_FORBIDDEN_CALLS``.
_SAFE_DUNDER_READS: frozenset[str] = frozenset(
    {
        "__init__",
        "__name__",
        "__doc__",
        "__version__",
        "__class__",
    }
)
_ALLOWED_BUILTINS: frozenset[str] = frozenset(
    {
        # value constructors
        "int",
        "float",
        "str",
        "bool",
        "list",
        "tuple",
        "dict",
        "set",
        "frozenset",
        "bytes",
        "bytearray",
        "complex",
        # iteration / reflection
        "range",
        "len",
        "enumerate",
        "zip",
        "map",
        "filter",
        "sorted",
        "reversed",
        "min",
        "max",
        "sum",
        "any",
        "all",
        "abs",
        "round",
        "isinstance",
        "issubclass",
        "hasattr",
        "getattr",
        "setattr",
        "type",
        "repr",
        "print",
        # ``dir`` is read-only attribute introspection — no side effects, no
        # way to mutate state. Blocking it forced every "what's available
        # under this object?" probe through extra find_api / get_help
        # roundtrips. Allowing it cuts discovery cost.
        "dir",
        # exception classes — needed for ``try/except`` blocks the agent
        # routinely writes when probing PyFluent state. They are class
        # references only; nothing destructive can be done with them.
        "Exception",
        "BaseException",
        "ValueError",
        "TypeError",
        "KeyError",
        "IndexError",
        "AttributeError",
        "RuntimeError",
        "LookupError",
        "ArithmeticError",
        "ZeroDivisionError",
        "StopIteration",
        "NotImplementedError",
        "AssertionError",
        # constants
        "True",
        "False",
        "None",
    }
)


def validate_python_source(
    code: str,
    *,
    forbidden_calls: Iterable[str] = _FORBIDDEN_CALLS,
    strict: bool = False,
    extra_allowed_names: Iterable[str] = (),
) -> RunCodeResult:
    """Parse code and return a typed result (memoized).

    This is a pure function, which means the same inputs always produce the same RunCodeResult.
    A bounded LRU keyed by ``(sha256(code), strict,
    frozenset(forbidden_calls), frozenset(extra_allowed_names))``
    avoids re-walking the AST when the agent re-validates the same
    snippet, which is common during multi-edit retries).

    Parameters
    ----------
    code : str
        Python code snippet to validate or execute.
    forbidden_calls : Iterable[str]
        Forbidden calls to supply to the function.
    strict : bool
        Strict to supply to the function.
    extra_allowed_names : Iterable[str]
        Extra allowed names to supply to the function.

    Returns
    -------
    RunCodeResult
        Result produced by the function.
    """
    if not code:
        return _validate_python_source_uncached(
            code,
            forbidden_calls=forbidden_calls,
            strict=strict,
            extra_allowed_names=extra_allowed_names,
        )
    code_hash = hashlib.sha256(code.encode("utf-8", errors="replace")).hexdigest()
    key = (
        code_hash,
        bool(strict),
        frozenset(forbidden_calls),
        frozenset(extra_allowed_names),
    )
    cached = _cache_lookup(key)
    if cached is not None:
        return cached
    result = _validate_python_source_uncached(
        code,
        forbidden_calls=forbidden_calls,
        strict=strict,
        extra_allowed_names=extra_allowed_names,
    )
    _cache_store(key, result)
    return result


def _validate_python_source_uncached(
    code: str,
    *,
    forbidden_calls: Iterable[str] = _FORBIDDEN_CALLS,
    strict: bool = False,
    extra_allowed_names: Iterable[str] = (),
) -> RunCodeResult:
    """Inner uncached implementation — see :func:`validate_python_source`.

    Returns ``status="ok"`` if the code parses and contains no forbidden
    calls; otherwise ``status="error"`` with a message describing the issue.

    When ``strict`` is ``True`` the validator additionally rejects:

    * Imports of any module outside an allow-list (``math``, ``json``,
      ``ansys.fluent.core``, ...);
    * References to top-level names other than a small set of safe
      built-ins plus the locals injected by the executor (``solver``,
      ``session``, plus any name in ``extra_allowed_names``).

    Strict mode is what :class:`PyFluentBackend.run_code` uses. The
    relaxed default is reused by :meth:`Backend.validate_code`, which
    is also used as a client-side dry-run.

    Parameters
    ----------
    code : str
        Python code snippet to validate or execute.
    forbidden_calls : Iterable[str]
        Forbidden calls to supply to the function.
    strict : bool
        Strict to supply to the function.
    extra_allowed_names : Iterable[str]
        Extra allowed names to supply to the function.

    Returns
    -------
    RunCodeResult
        Result produced by the function.
    """
    if not code or not code.strip():
        return RunCodeResult(
            status="error",
            error_code="invalid_arguments",
            message="code must be a non-empty string",
        )

    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return RunCodeResult(
            status="error",
            error_code="syntax_error",
            message=f"SyntaxError: {exc.msg} at line {exc.lineno}, col {exc.offset}",
            stderr=str(exc),
        )

    forbidden = set(forbidden_calls)
    flagged: list[str] = []
    tui_flagged: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _dotted_name(node.func)
            if name and name in forbidden:
                flagged.append(name)
            # Block ``getattr(obj, '__class__')``-style reflection used
            # to climb back up to ``object.__subclasses__()`` etc.
            if (
                isinstance(node.func, ast.Name)
                and node.func.id in {"getattr", "setattr", "delattr", "hasattr"}
                and len(node.args) >= 2
                and isinstance(node.args[1], ast.Constant)
                and isinstance(node.args[1].value, str)
                and node.args[1].value.startswith("__")
                and node.args[1].value.endswith("__")
                and node.args[1].value not in _SAFE_DUNDER_READS
            ):
                flagged.append(f"{node.func.id}(..., {node.args[1].value!r})")
        if (
            isinstance(node, ast.Attribute)
            and node.attr.startswith("__")
            and node.attr.endswith("__")
        ):
            # block dunder attribute access (``__class__``/``__globals__``/...)
            if node.attr not in _SAFE_DUNDER_READS:
                flagged.append(node.attr)
        # Block PyFluent TUI escape hatch: ``solver.tui.<anything>`` is a
        # text-command bridge that bypasses every settings-API guardrail
        # the rest of this validator enforces (no schema, no allowed-type
        # checks, no async-safety). The settings API is mandatory.
        if isinstance(node, ast.Attribute):
            dotted = _dotted_name(node)
            if dotted and (
                dotted == "tui"
                or dotted.startswith("tui.")
                or ".tui." in dotted
                or dotted.endswith(".tui")
            ):
                tui_flagged.append(
                    f"{dotted} (TUI escape hatch is forbidden \u2014 use settings API)"
                )
            # ``execute_tui(...)`` is the method-call form of the same
            # text-command bridge \u2014 reject it with the same code.
            if node.attr == "execute_tui":
                tui_flagged.append(
                    "execute_tui (TUI escape hatch is forbidden \u2014 use settings API)"
                )
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"getattr", "setattr", "delattr", "hasattr"}
            and len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant)
            and node.args[1].value in {"tui", "execute_tui"}
        ):
            tui_flagged.append(
                f"getattr(..., {node.args[1].value!r}) (TUI escape hatch is forbidden)"
            )

    # TUI escape hatches get a dedicated error code so callers can treat them
    # as a hard failure (see ``_HARD_VALIDATION_ERROR_CODES``).
    # They take priority over the generic ``forbidden_call`` classification.
    if tui_flagged:
        return RunCodeResult(
            status="error",
            error_code="tui_not_allowed",
            message=(
                "TUI escape hatch is forbidden \u2014 use the settings API: "
                f"{sorted(set(tui_flagged))}"
            ),
        )

    if flagged:
        return RunCodeResult(
            status="error",
            error_code="forbidden_call",
            message=f"Forbidden call(s) detected: {sorted(set(flagged))}",
        )

    if strict:
        allowed_names = (
            set(_ALLOWED_BUILTINS) | {"solver", "session", "pyfluent"} | set(extra_allowed_names)
        )
        # Collect bound local names so we don't flag user-defined helpers.
        bound: set[str] = set(allowed_names)

        def _bind_target(tgt: ast.AST) -> None:
            """Recursively register names introduced by an assignment target.

            Handles plain ``Name`` targets, tuple/list unpacking
            (``a, b = ...``, ``for k, v in items:``), and starred
            captures (``a, *rest = ...``). Without this, idiomatic
            patterns like ``for name, wall in walls.items():`` were
            wrongly flagged as ``forbidden_name`` even though the loop
            variables are obviously bound by the loop itself.

            Parameters
            ----------
            tgt : ast.AST
                Tgt to supply to the function.

            Returns
            -------
            None
                The function completes through its side effects.
            """
            if isinstance(tgt, ast.Name):
                bound.add(tgt.id)
            elif isinstance(tgt, (ast.Tuple, ast.List)):
                for elt in tgt.elts:
                    _bind_target(elt)
            elif isinstance(tgt, ast.Starred):
                _bind_target(tgt.value)

        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for tgt in node.targets:
                    _bind_target(tgt)
            elif isinstance(node, ast.AugAssign):
                _bind_target(node.target)
            elif isinstance(node, ast.AnnAssign) and node.target is not None:
                _bind_target(node.target)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                bound.add(node.name)
                # function arguments are also bound names inside the body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    args = node.args
                    for a in (*args.posonlyargs, *args.args, *args.kwonlyargs):
                        bound.add(a.arg)
                    if args.vararg:
                        bound.add(args.vararg.arg)
                    if args.kwarg:
                        bound.add(args.kwarg.arg)
            elif isinstance(node, (ast.For, ast.AsyncFor, ast.comprehension)):
                _bind_target(node.target)
            elif isinstance(node, ast.With):
                for item in node.items:
                    if item.optional_vars is not None:
                        _bind_target(item.optional_vars)
            elif isinstance(node, ast.Lambda):
                args = node.args
                for a in (*args.posonlyargs, *args.args, *args.kwonlyargs):
                    bound.add(a.arg)
                if args.vararg:
                    bound.add(args.vararg.arg)
                if args.kwarg:
                    bound.add(args.kwarg.arg)
            elif isinstance(node, ast.NamedExpr) and isinstance(node.target, ast.Name):
                bound.add(node.target.id)
            elif isinstance(node, (ast.ExceptHandler,)) and node.name is not None:
                bound.add(node.name)
        bad_names: list[str] = []
        bad_imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import,)):
                for alias in node.names:
                    root_mod = alias.name.split(".", 1)[0]
                    if alias.name not in _ALLOWED_IMPORTS and root_mod not in _ALLOWED_IMPORTS:
                        bad_imports.append(alias.name)
                    bound.add((alias.asname or alias.name).split(".", 1)[0])
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                root_mod = mod.split(".", 1)[0]
                if mod not in _ALLOWED_IMPORTS and root_mod not in _ALLOWED_IMPORTS:
                    bad_imports.append(mod)
                for alias in node.names:
                    bound.add(alias.asname or alias.name)
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                if node.id not in bound:
                    bad_names.append(node.id)
        if bad_imports:
            return RunCodeResult(
                status="error",
                error_code="forbidden_import",
                message=f"Imports outside allow-list: {sorted(set(bad_imports))}",
            )
        if bad_names:
            return RunCodeResult(
                status="error",
                error_code="forbidden_name",
                message=f"Names not in sandbox: {sorted(set(bad_names))[:10]}",
            )

    return RunCodeResult(
        status="ok", message="parse_ok", return_value={"node_count": _count_nodes(tree)}
    )


def _dotted_name(node: ast.AST) -> str | None:
    """Return a dotted name for the AST node.

    Parameters
    ----------
    node : ast.AST
        Node to inspect or register.

    Returns
    -------
    str | None
        Optional value produced by the operation.
    """
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _dotted_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return None


def _count_nodes(tree: ast.AST) -> int:
    """Count AST nodes in the parsed code.

    Parameters
    ----------
    tree : ast.AST
        Tree to supply to the function.

    Returns
    -------
    int
        Configured integer limit used by the helper.
    """
    return sum(1 for _ in ast.walk(tree))


# ---------------------------------------------------------------------------
# Python code sanitiser — fix common non-Pythonic tokens
# ---------------------------------------------------------------------------

# JavaScript / JSON-style tokens that are valid Python *names* but not the
# correct Python constants. Generated or caller-provided code can emit
# ``true`` / ``false`` / ``null`` instead of ``True`` / ``False`` /
# ``None``.  These are legal NAME tokens so ``ast.parse`` succeeds, but
# the code crashes at runtime with ``NameError``.
_JS_TO_PYTHON: dict[str, str] = {
    "true": "True",
    "false": "False",
    "null": "None",
}


def sanitize_python_code(code: str) -> tuple[str, list[str]]:
    """Replace JavaScript-style Booleans/null with Python equivalents.

    Uses the ``tokenize`` module so that replacements only affect
    ``NAME`` tokens. Occurrences inside string literals or comments
    are left untouched.

    Returns ``(sanitized_code, fixes)`` where ``fixes`` is a list of
    human-readable descriptions of each replacement made.  If no
    replacements are needed, the original code is returned unchanged.

    Parameters
    ----------
    code : str
        Python code snippet to validate or execute.

    Returns
    -------
    tuple[str, list[str]]
        Collection containing the operation results.
    """
    if not code or not code.strip():
        return code, []

    try:
        tokens = list(
            tokenize.generate_tokens(io.StringIO(code).readline),
        )
    except tokenize.TokenError:
        return code, []

    # Collect replacements as (line, col_start, col_end, replacement).
    edits: list[tuple[int, int, int, str, str]] = []
    for tok in tokens:
        if tok.type == tokenize.NAME and tok.string in _JS_TO_PYTHON:
            replacement = _JS_TO_PYTHON[tok.string]
            edits.append(
                (
                    tok.start[0],
                    tok.start[1],
                    tok.end[1],
                    replacement,
                    tok.string,
                )
            )

    if not edits:
        return code, []

    lines = code.split("\n")
    fixes: list[str] = []

    # Apply in reverse order so column offsets stay valid.
    for line_no, col_start, col_end, replacement, original in reversed(edits):
        idx = line_no - 1
        line = lines[idx]
        lines[idx] = line[:col_start] + replacement + line[col_end:]
        fixes.append(f"line {line_no}: {original} -> {replacement}")

    # Report fixes in forward order for readability.
    fixes.reverse()
    return "\n".join(lines), fixes
