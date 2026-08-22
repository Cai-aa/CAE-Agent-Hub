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

"""Static, Fluent-specific risk classifier for ``run_code`` snippets.

This module is **stateless**. It does NOT plan, schedule, or track
history. It only inspects a single snippet's AST against a fixed
table of Fluent-specific crash signatures and (optionally) performs
a single intra-snippet topological reorder when use-before-create is
detected for a small set of well-known dependencies (such as named
expressions and materials).

By design this module:

* Contains no model orchestration and no rule-pack DSL. Only a fixed table
  of code shapes that have empirically crashed PyFluent/the gRPC
  channel during in-house sessions.
* Is **opt-out** via ``FLUIDS_MCP_INTENT_GUARD=0`` so a host that
  prefers its own planner can disable it entirely.
* Never imports ``ansys.fluent.core``. It pure ``ast`` walks only
  so that it is safe to evaluate before a solver session exists.
* Returns the same ``RunCodeResult`` envelope the rest of the leaf
  uses, with one of three new ``error_code`` values:
  ``risk_blocked``, ``sequence_error``, ``and solver_disconnected``.
  (The third is set by :mod:`pyfluent` backend, not here.)

This is a defense-in-depth layer **at the execution boundary**, in
scope for the standalone leaf. It is NOT a planner. Higher-level
planning, recipes, and journaling remain out of scope.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
import os
import re
from typing import Iterable, Mapping, Optional, TypeGuard, cast

from ansys.fluent.mcp.common.models import RunCodeResult

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GuardFinding:
    """Single signature hit on a snippet."""

    signature: str
    severity: str  # "block" | "warn" | "rewrite"
    message: str
    suggestion: Optional[str] = None
    line: Optional[int] = None


@dataclass
class GuardReport:
    """Collection of findings for a snippet."""

    findings: list[GuardFinding] = field(default_factory=list)
    rewritten_code: Optional[str] = None  # toposorted variant when applicable

    @property
    def has_blocking(self) -> bool:
        """Whether the report contains any blocking finding.

        Returns
        -------
        bool
            ``True`` when at least one finding has ``severity="block"``.
        """
        return any(f.severity == "block" for f in self.findings)

    def to_run_code_result(self) -> RunCodeResult:
        """Render the report as the ``RunCodeResult`` callers expect.

        Only invoked when at least one BLOCK-level finding is present.
        Sequence-error findings produce ``error_code="sequence_error"``;
        every other block produces ``error_code="risk_blocked"``.

        Returns
        -------
        RunCodeResult
            Error result containing the blocking findings and guard-specific
            ``error_code`` value.
        """
        block = [f for f in self.findings if f.severity == "block"]
        is_seq = any(f.signature.startswith("seq.") for f in block)
        lines = []
        for f in block:
            prefix = f"[{f.signature}]"
            if f.line is not None:
                prefix += f" line {f.line}"
            lines.append(f"{prefix}: {f.message}")
            if f.suggestion:
                lines.append(f"  suggestion: {f.suggestion}")
        return RunCodeResult(
            status="error",
            error_code="sequence_error" if is_seq else "risk_blocked",
            stdout="",
            stderr="\n".join(lines),
            message=lines[0] if lines else "intent_guard blocked execution",
            warnings=[f.message for f in self.findings if f.severity == "warn"],
        )


def is_enabled(env: Optional[dict[str, str]] = None) -> bool:
    """Honor ``FLUIDS_MCP_INTENT_GUARD`` (default ON).

    Parameters
    ----------
    env : dict[str, str], optional
        Environment mapping to inspect. When omitted, ``os.environ`` is used.

    Returns
    -------
    bool
        ``False`` only when the environment value is ``0``, ``false``,
        ``no``, or ``off``. Otherwise, ``True``.
    """
    src = os.environ if env is None else env
    raw = src.get("FLUIDS_MCP_INTENT_GUARD")
    if raw is None:
        return True
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def evaluate(
    code: str,
    *,
    live_named_objects: Optional[Mapping[str, Iterable[str]]] = None,
    iterating: bool = False,
) -> GuardReport:
    """Evaluate code against intent-guard risk signatures.

    Parameters
    ----------
    code : str
        Python code or command text to execute or validate.
    live_named_objects : Optional[Mapping[str, Iterable[str]]]
        Live named objects to supply to the function.
    iterating : bool
        Whether to enable or apply iterating.

    Returns
    -------
    GuardReport
        GuardReport produced by the operation.
    """
    report = GuardReport()
    if not code or not code.strip():
        return report
    try:
        tree = ast.parse(code)
    except SyntaxError:
        # Don't shadow the AST validator's own syntax error — let
        # validate_python_source produce the canonical message.
        return report

    _check_boundary_rename_with_whitespace(tree, report)
    _check_vof_count_direct_assign(tree, report)
    _check_phase_material_before_rename(tree, report)
    _check_write_while_iterating(tree, report, iterating=iterating)
    _check_named_expression_use_before_create(
        tree,
        report,
        code,
        live_named_objects=live_named_objects or {},
    )
    _check_report_def_surface_field(tree, report)
    _check_named_expr_missing_units(tree, report)
    _check_tui_usage(tree, report)
    return report


# ---------------------------------------------------------------------------
# Signatures (each populates ``report.findings`` in place)
# ---------------------------------------------------------------------------


_WHITESPACE_RE = re.compile(r"\s")


def _check_boundary_rename_with_whitespace(
    tree: ast.AST,
    report: GuardReport,
) -> None:
    """Block boundary renames whose target name contains whitespace.

    Two patterns observed in the wild that crashed the gRPC channel:

    * Settings-tree assignment::

          solver.settings.setup.boundary_conditions.velocity_inlet["inlet1"].name = "oil inlet"

    * The ``rename`` command::

          solver.settings.setup.boundary_conditions.velocity_inlet.rename("oil inlet", "inlet1")

    Both die mid-call when the new name contains a space. Underscore
    forms (``"oil_inlet"``) succeed reliably.

    Parameters
    ----------
    tree : ast.AST
        Parsed snippet tree to inspect.
    report : GuardReport
        Report to update with blocking findings.

    Returns
    -------
    None
    """
    for node in ast.walk(tree):
        # Pattern 1: <chain that includes boundary_conditions>.name = "<has whitespace>"
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if (
                    isinstance(tgt, ast.Attribute)
                    and tgt.attr == "name"
                    and _chain_contains_segment(tgt.value, "boundary_conditions")
                    and _is_whitespace_str_const(node.value)
                ):
                    report.findings.append(
                        GuardFinding(
                            signature="bc.rename.whitespace",
                            severity="block",
                            message=(
                                "Boundary rename with whitespace in the new "
                                "name has crashed the Fluent gRPC channel "
                                "in observed sessions."
                            ),
                            suggestion=(
                                f"Use an underscored name ({_quote(_to_underscore(_const_str(node.value)))})."  # noqa: E501
                            ),
                            line=getattr(node, "lineno", None),
                        )
                    )
        # Pattern 2: <chain>.rename("<has whitespace>", ...)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if (
                node.func.attr == "rename"
                and _chain_contains_segment(node.func.value, "boundary_conditions")
                and node.args
                and _is_whitespace_str_const(node.args[0])
            ):
                report.findings.append(
                    GuardFinding(
                        signature="bc.rename.whitespace",
                        severity="block",
                        message=(
                            "Boundary rename(new=..., ...) with whitespace in the "
                            "new name has crashed the Fluent gRPC channel in "
                            "observed sessions."
                        ),
                        suggestion=(
                            f"Use an underscored name ({_quote(_to_underscore(_const_str(node.args[0])))})."  # noqa: E501
                        ),
                        line=getattr(node, "lineno", None),
                    )
                )


def _check_vof_count_direct_assign(tree: ast.AST, report: GuardReport) -> None:
    """Rewrite ``multiphase.number_of_phases = N`` → suggest the active subfield.

    The legal Fluent path on 27.1 is
    ``multiphase.number_of_phases.number_of_eulerian_phases``;
    direct assignment of an integer to ``.number_of_phases`` raises a
    ``TypeError: 'NamedObject' has no attribute 'set_state'`` style
    error and leaves the model partially configured.

    Parameters
    ----------
    tree : ast.AST
        Parsed snippet tree to inspect.
    report : GuardReport
        Report to update with blocking findings.

    Returns
    -------
    None
    """
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not isinstance(node.value, ast.Constant) or not isinstance(node.value.value, int):
            continue
        for tgt in node.targets:
            if not isinstance(tgt, ast.Attribute) or tgt.attr != "number_of_phases":
                continue
            if not _chain_contains_segment(tgt.value, "multiphase"):
                continue
            report.findings.append(
                GuardFinding(
                    signature="multiphase.number_of_phases.shape",
                    severity="block",
                    message=(
                        "Setting `multiphase.number_of_phases` to an int "
                        "is not the active write path on Fluent 27.1."
                    ),
                    suggestion=(
                        "Assign to "
                        "`multiphase.number_of_phases.number_of_eulerian_phases` "
                        f"= {node.value.value} instead."
                    ),
                    line=getattr(node, "lineno", None),
                )
            )


def _check_phase_material_before_rename(
    tree: ast.AST,
    report: GuardReport,
) -> None:
    """Block snippets that set ``phases["phase-1"].material`` before renaming the phase.

    Fluent silently drops the material assignment because the named
    object is replaced when the phase is renamed in the same call;
    catching this in advance saves a confusing "phase-2 ended up with
    the default material" debug round-trip.

    Parameters
    ----------
    tree : ast.AST
        Parsed snippet tree to inspect.
    report : GuardReport
        Report to update with blocking findings.

    Returns
    -------
    None
    """
    rename_targets: dict[str, int] = {}  # phase-key → lineno
    material_writes: dict[str, int] = {}  # phase-key → lineno

    for node in ast.walk(tree):
        # Rename: phases["phase-1"].name = "water"
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                key = _phase_key_under_rename(tgt)
                if key is not None and _is_str_const(node.value):
                    rename_targets[key] = getattr(node, "lineno", -1)
                key = _phase_key_under_material(tgt)
                if key is not None:
                    material_writes[key] = getattr(node, "lineno", -1)

    for key, mat_line in material_writes.items():
        ren_line = rename_targets.get(key)
        if ren_line is not None and ren_line >= mat_line:
            report.findings.append(
                GuardFinding(
                    signature="seq.phase.material_before_rename",
                    severity="block",
                    message=(
                        f"Phase {key!r} is renamed AFTER its material is "
                        "assigned in the same snippet; Fluent will discard "
                        "the material write."
                    ),
                    suggestion=("Rename the phase first, then assign the material to the new key."),
                    line=mat_line if mat_line >= 0 else None,
                )
            )


def _check_write_while_iterating(
    tree: ast.AST,
    report: GuardReport,
    *,
    iterating: bool,
) -> None:
    """Block setup mutations submitted while the solver is iterating.

    Parameters
    ----------
    tree : ast.AST
        Parsed snippet tree to inspect.
    report : GuardReport
        Report to update with blocking findings.
    iterating : bool
        Whether the solver is currently iterating.

    Returns
    -------
    None
    """
    if not iterating:
        return
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for tgt in node.targets:
            chain = _chain_segments(tgt)
            if "setup" in chain:
                report.findings.append(
                    GuardFinding(
                        signature="runtime.write_during_iter",
                        severity="block",
                        message=(
                            "Refusing to mutate `setup.*` while the solver "
                            "is iterating; Fluent occasionally drops the "
                            "gRPC channel when this races with the "
                            "calculation thread."
                        ),
                        suggestion=(
                            "Call `solver.solution.run_calculation.interrupt()` "
                            "first, then re-issue the write."
                        ),
                        line=getattr(node, "lineno", None),
                    )
                )
                break


def _check_named_expression_use_before_create(
    tree: ast.AST,
    report: GuardReport,
    code: str,
    *,
    live_named_objects: Mapping[str, Iterable[str]],
) -> None:
    """Check for forward references to named expressions that are not yet created.

    Detect references to a named expression that the snippet does not define
    AND that is missing from the live tree.

    Fluent treats an unknown named-expression reference as a string
    literal at validation time; the BC / gravity component is then
    rejected with an opaque "value not allowed" error. Catching the
    forward-ref in advance gives a far clearer message.

    Also: when the snippet *does* define the expression, but does so
    AFTER the reference, emit a ``sequence_error`` and offer a
    reordered snippet.

    Parameters
    ----------
    tree : ast.AST
        Parsed snippet tree to inspect.
    report : GuardReport
        Report to update with sequence errors and advisory findings.
    code : str
        Original snippet text.
    live_named_objects : Mapping[str, Iterable[str]]
        Existing named objects by settings-family path.

    Returns
    -------
    None
    """
    live_keys = {str(k) for k in (live_named_objects.get("setup.named_expressions") or [])}

    # Collect "create" assignments: setup.named_expressions["expr_grav"] = ...
    creates: dict[str, int] = {}
    references: dict[str, int] = {}

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        # Pass 1: detect creates on the LHS.
        is_create_stmt = False
        for tgt in node.targets:
            key = _named_expr_create_key(tgt)
            if key is not None:
                is_create_stmt = True
                creates[key] = min(
                    creates.get(key, getattr(node, "lineno", 10**9)),
                    getattr(node, "lineno", 10**9),
                )
        if is_create_stmt:
            # Don't mine the create-statement's RHS for "references" —
            # the dict literal's keys/values are not name references.
            continue
        # Pass 2: detect references on the RHS, but ONLY when the LHS
        # target chain ends in a known expression-reference slot
        # (so a plain ``foo.name = "bar"`` write is NOT flagged).
        if not any(_target_is_named_expr_slot(tgt) for tgt in node.targets):
            continue
        if _is_str_const(node.value):
            text = cast(str, node.value.value)
            if _NAME_TOKEN_RE.fullmatch(text):
                references.setdefault(text, getattr(node, "lineno", -1))

    for ref, ref_line in references.items():
        if ref in live_keys:
            continue
        if ref in creates:
            create_line = creates[ref]
            if create_line > ref_line:
                report.findings.append(
                    GuardFinding(
                        signature="seq.named_expr.use_before_create",
                        severity="block",
                        message=(
                            f"Named expression {ref!r} is referenced on "
                            f"line {ref_line} but only created on line "
                            f"{create_line} of the same snippet."
                        ),
                        suggestion=(
                            "Move the named-expression assignment ABOVE "
                            "the first reference, or split into two "
                            "run_code calls."
                        ),
                        line=ref_line if ref_line > 0 else None,
                    )
                )
            continue
        report.findings.append(
            GuardFinding(
                signature="named_expr.unknown",
                severity="warn",
                message=(
                    f"Snippet references named expression {ref!r} but it "
                    "is neither defined in this snippet nor present in "
                    "the live `setup.named_expressions` family."
                ),
                suggestion=(
                    f"Create it first: "
                    f"`solver.setup.named_expressions[{ref!r}] = "
                    "{{'definition': '<expr> [<unit>]'}}`."
                ),
                line=ref_line if ref_line > 0 else None,
            )
        )


def _check_report_def_surface_field(
    tree: ast.AST,
    report: GuardReport,
) -> None:
    """Block ``surfaces=`` writes on a report definition.

    Report definitions take ``surface_names=[...]`` — they have no
    ``surfaces`` attribute, so both

        solver.settings.solution.report_definitions.surface["r1"].surfaces = ["s1"]
        ...report_definitions.surface["r1"].locations.surfaces = ["s1"]

    and the create-dict shape ``report_definitions.surface["r1"] =
    {"surfaces": [...]}`` mis-target or raise ``AttributeError``.
    (``surfaces`` is the *graphics*-object field, not the report-def
    field.) Catching the shape up front gives a far clearer message than
    the raw attribute error.

    Parameters
    ----------
    tree : ast.AST
        Parsed snippet tree to inspect.
    report : GuardReport
        Report to update with blocking findings.

    Returns
    -------
    None
    """
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        # Attribute form: <chain w/ report_definitions>.surfaces = ...
        # (also catches the ``.locations.surfaces`` variant — ``surfaces``
        # is the terminal attr and the chain still contains
        # ``report_definitions``).
        for tgt in node.targets:
            if (
                isinstance(tgt, ast.Attribute)
                and tgt.attr == "surfaces"
                and _chain_contains_segment(tgt.value, "report_definitions")
            ):
                report.findings.append(
                    GuardFinding(
                        signature="reportdef.surface_field",
                        severity="block",
                        message=(
                            "Report definitions have no `surfaces` field; the "
                            "write is a no-op / AttributeError."
                        ),
                        suggestion=(
                            "Use `surface_names=[...]` on the report definition "
                            "(`surfaces` is the graphics-object field)."
                        ),
                        line=getattr(node, "lineno", None),
                    )
                )
        # Create-dict form: report_definitions.<fam>["r1"] = {"surfaces": ...}
        if isinstance(node.value, ast.Dict) and any(
            isinstance(t, ast.Subscript) and _chain_contains_segment(t.value, "report_definitions")
            for t in node.targets
        ):
            for key_node in node.value.keys:
                if _is_str_const(key_node) and key_node.value in {
                    "surfaces",
                    "locations",
                }:
                    report.findings.append(
                        GuardFinding(
                            signature="reportdef.surface_field",
                            severity="block",
                            message=(
                                "Report-definition create dict uses "
                                f"{key_node.value!r}; report definitions take "
                                "`surface_names`."
                            ),
                            suggestion=("Replace the key with `surface_names=[...]`."),
                            line=getattr(node, "lineno", None),
                        )
                    )
                    break


def _check_named_expr_missing_units(
    tree: ast.AST,
    report: GuardReport,
) -> None:
    """Warn when a named expression is created with a unit-less number.

    A bare numeric definition (``"definition": "9.81"``) is treated as
    dimensionless and later fails with a confusing "expression not found"
    error when consumed by a dimensioned slot (gravity, velocity,
    pressure, ...). Pure formulas / symbol references (``CellArea() *
    rho``) are intentionally NOT flagged — only a literal number with no
    ``[unit]`` clause. This mirrors the agent-side validator heuristic so
    the standalone leaf gives the same advice.

    Parameters
    ----------
    tree : ast.AST
        Parsed snippet tree to inspect.
    report : GuardReport
        Report to update with advisory findings.

    Returns
    -------
    None
    """
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(_named_expr_create_key(t) is not None for t in node.targets):
            continue
        if not isinstance(node.value, ast.Dict):
            continue
        defn = _dict_str_value(node.value, "definition")
        if defn is None:
            continue
        stripped = defn.strip()
        if not stripped or ("[" in stripped and "]" in stripped):
            continue
        try:
            float(stripped)
        except ValueError:
            continue  # formula / symbol reference — fine
        report.findings.append(
            GuardFinding(
                signature="named_expr.missing_units",
                severity="warn",
                message=(
                    f"named expression definition {defn!r} has no unit "
                    "annotation; Fluent treats a bare number as dimensionless "
                    "and it fails when consumed by a dimensioned slot "
                    "(gravity, velocity, pressure, temperature, ...)."
                ),
                suggestion=(
                    "Add a unit in square brackets, e.g. '9.81 [m s^-2]', '101325 [Pa]', '300 [K]'."
                ),
                line=getattr(node, "lineno", None),
            )
        )


def _check_tui_usage(tree: ast.AST, report: GuardReport) -> None:
    """Warn on ``.tui.*`` access — fragile / unsupported vs the settings API.

    Parameters
    ----------
    tree : ast.AST
        Parsed snippet tree to inspect.
    report : GuardReport
        Report to update with advisory findings.

    Returns
    -------
    None
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "tui":
            report.findings.append(
                GuardFinding(
                    signature="tui.usage",
                    severity="warn",
                    message=(
                        "`.tui.*` (text-user-interface) calls are fragile and "
                        "version-sensitive; prefer the `solver.settings.*` tree, "
                        "which is what the rest of this server validates against."
                    ),
                    suggestion=(
                        "Find the equivalent settings path (e.g. via find_api) and use it instead of the TUI."  # noqa: E501
                    ),
                    line=getattr(node, "lineno", None),
                )
            )
            break  # one warning per snippet is enough


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def _chain_segments(node: ast.AST) -> list[str]:
    """Return the dotted attribute chain rooted at a Name, ignoring subscript keys.

    Subscript indices (e.g. ``["phase-1"]``) are flattened away so the
    function returns ``["solver","settings","setup","boundary_conditions",
    "velocity_inlet","name"]`` for ``solver.settings.setup.boundary_conditions
    .velocity_inlet["inlet1"].name``.

    Parameters
    ----------
    node : ast.AST
        AST node whose chain should be flattened.

    Returns
    -------
    list[str]
        Dotted attribute-chain segments found in the node.
    """
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, ast.Attribute):
        return _chain_segments(node.value) + [node.attr]
    if isinstance(node, ast.Subscript):
        return _chain_segments(node.value)
    if isinstance(node, ast.Call):
        return _chain_segments(node.func)
    return []


def _chain_contains_segment(node: ast.AST, segment: str) -> bool:
    """Check whether an AST chain contains a segment.

    Parameters
    ----------
    node : ast.AST
        AST node whose attribute chain should be inspected.
    segment : str
        Chain segment to find.

    Returns
    -------
    bool
        ``True`` when ``segment`` is present in the flattened chain.
    """
    return segment in _chain_segments(node)


def _is_str_const(node: ast.AST | None) -> TypeGuard[ast.Constant]:
    """Check whether a node is a string constant.

    Parameters
    ----------
    node : ast.AST, optional
        Node to inspect.

    Returns
    -------
    TypeGuard[ast.Constant]
        ``True`` when ``node`` is an ``ast.Constant`` with a string value.
    """
    return isinstance(node, ast.Constant) and isinstance(node.value, str)


def _const_str(node: ast.AST) -> str:
    """Return the string value of an AST constant.

    Parameters
    ----------
    node : ast.AST
        Node to read.

    Returns
    -------
    str
        String constant value, or an empty string when the node is not a
        string constant.
    """
    return cast(str, node.value) if _is_str_const(node) else ""


def _is_whitespace_str_const(node: ast.AST) -> bool:
    """Check whether a node is a non-empty string constant with whitespace.

    Parameters
    ----------
    node : ast.AST
        Node to inspect.

    Returns
    -------
    bool
        ``True`` when the node is a string constant containing whitespace.
    """
    if not _is_str_const(node):
        return False
    value = cast(str, node.value)
    return bool(value) and bool(_WHITESPACE_RE.search(value))


def _to_underscore(value: str) -> str:
    """Replace whitespace in a string with underscores.

    Parameters
    ----------
    value : str
        Value to normalize.

    Returns
    -------
    str
        Normalized value with whitespace collapsed to underscores and leading
        or trailing underscores removed.
    """
    return _WHITESPACE_RE.sub("_", value).strip("_")


def _quote(value: str) -> str:
    """Wrap a value in double quotes for display.

    Parameters
    ----------
    value : str
        Value to quote.

    Returns
    -------
    str
        Double-quoted value.
    """
    return f'"{value}"'


def _phase_key_under_rename(node: ast.AST) -> Optional[str]:
    """Return the phase key for a phase rename target.

    Parameters
    ----------
    node : ast.AST
        Assignment target to inspect.

    Returns
    -------
    str, optional
        Phase key when ``node`` is ``phases[<key>].name``. Otherwise,
        ``None``.
    """
    if not isinstance(node, ast.Attribute) or node.attr != "name":
        return None
    sub = node.value
    if not isinstance(sub, ast.Subscript):
        return None
    if not _chain_contains_segment(sub.value, "phases"):
        return None
    key = _subscript_key(sub)
    return key


def _phase_key_under_material(node: ast.AST) -> Optional[str]:
    """Return the phase key for a phase material target.

    Parameters
    ----------
    node : ast.AST
        Assignment target to inspect.

    Returns
    -------
    str, optional
        Phase key when ``node`` ends in ``...material`` or
        ``...general.material`` under a ``phases[...]`` subscript.
        Otherwise, ``None``.
    """
    if not isinstance(node, ast.Attribute):
        return None
    if node.attr != "material":
        return None
    cur: ast.AST = node.value
    # Walk down looking for phases[<key>] subscript.
    while isinstance(cur, ast.Attribute):
        cur = cur.value
    if not isinstance(cur, ast.Subscript):
        return None
    if not _chain_contains_segment(cur.value, "phases"):
        return None
    return _subscript_key(cur)


def _dict_str_value(node: ast.Dict, key: str) -> Optional[str]:
    """Return a string value from an ``ast.Dict`` literal.

    Parameters
    ----------
    node : ast.Dict
        Dictionary literal to inspect.
    key : str
        String key to find.

    Returns
    -------
    str, optional
        String value for ``key`` when both the key and value are string
        constants. Otherwise, ``None``.
    """
    for k, v in zip(node.keys, node.values):
        if _is_str_const(k) and k.value == key and _is_str_const(v):
            return cast(str, v.value)
    return None


def _subscript_key(node: ast.Subscript) -> Optional[str]:
    """Return the string key from a subscript node.

    Parameters
    ----------
    node : ast.Subscript
        Subscript node to inspect.

    Returns
    -------
    str, optional
        String subscript key when the slice is a string constant. Otherwise,
        ``None``.
    """
    sl = node.slice
    # py3.9+: slice is the expr directly (no Index wrapper).
    if _is_str_const(sl):
        return cast(str, sl.value)
    return None


def _named_expr_create_key(target: ast.AST) -> Optional[str]:
    """Return the named-expression key for a create target.

    Parameters
    ----------
    target : ast.AST
        Assignment target to inspect.

    Returns
    -------
    str, optional
        Named-expression key when ``target`` is
        ``...named_expressions["<key>"]``. Otherwise, ``None``.
    """
    if not isinstance(target, ast.Subscript):
        return None
    if not _chain_contains_segment(target.value, "named_expressions"):
        return None
    return _subscript_key(target)


_NAME_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")


# Settings-tree leaf attributes that, when assigned a bare identifier-like
# string, are conventionally a named-expression reference. Keeping this
# list small avoids false-positives on unrelated string assignments.
_EXPR_REF_SLOTS: frozenset[str] = frozenset(
    {
        "definition",
        "value",
        "x_component",
        "y_component",
        "z_component",
        "component",
    }
)


def _target_is_named_expr_slot(target: ast.AST) -> bool:
    """Check whether a target is a named-expression reference slot.

    Parameters
    ----------
    target : ast.AST
        Assignment target to inspect.

    Returns
    -------
    bool
        ``True`` when ``target`` ends in a known expression-reference slot and
        is not itself a named-expression definition.
    """
    if not isinstance(target, ast.Attribute):
        return False
    if target.attr not in _EXPR_REF_SLOTS:
        return False
    # Reject the create slot itself (``named_expressions["x"].definition``)
    # — the snippet's RHS there is a definition string, not a reference.
    if _chain_contains_segment(target, "named_expressions"):
        return False
    return True


__all__ = [
    "GuardFinding",
    "GuardReport",
    "evaluate",
    "is_enabled",
]
