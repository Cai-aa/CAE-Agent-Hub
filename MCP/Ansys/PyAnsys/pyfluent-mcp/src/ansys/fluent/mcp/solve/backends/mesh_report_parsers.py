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

r"""Pure-functional parsers for Fluent's ``mesh.check`` and ``mesh.quality`` reports.

These commands print a human-readable block to the Fluent transcript/console.
PyFluent forwards that print stream to Python's stdout, which
:meth:`ansys.fluent.mcp.solve.backends.pyfluent.PyFluentBackend.run_code`
captures into ``RunCodeResult.stdout`` via
``contextlib.redirect_stdout``. The following parsers take that captured
text and extract structured numbers/lists.

Why parse instead of using a programmatic API:

* ``mesh.check`` and ``mesh.quality`` are settings-API commands. They
  return ``None`` and emit their result to the console. There is no
  structured return value across the supported Fluent versions.
  (Newer PyFluent versions have experimental structured reports under
  ``solver.report.*``, but the names have churned across the 24.x / 25.x)
  releases.
* The transcript wording for the headline lines cared about
  (``Minimum Orthogonal Quality``/``Maximum Ortho Skew``/``Maximum Aspect
  Ratio``/``Volume statistics``/``Face area statistics``/``Domain Extents``)
  has been stable since Fluent 19.0. Extra histograms/hints below
  the headline lines are version-dependent and ignored.

Fluent 2024 and later formats notes (verified against a real session):

* ``mesh.quality`` typically prints only ``Minimum Orthogonal Quality``
  and ``Maximum Aspect Ratio``. ``Maximum Ortho Skew`` is **often
  absent** because Fluent treats orthogonal quality as the canonical
  cell-quality metric (orthogonal quality ≈ 1 − ortho-skew, so the
  two are redundant). The parser returns ``None`` for the missing
  field. Callers MUST treat ``None`` as ``unknown`` and rely on
  ``min_orthogonal_quality`` as the primary signal.
* The headline lines now include trailing annotations like
  ``cell <id> on zone <z> (ID: <gid> on partition: <p>) at location
  (x, y, z)``. These are ignored by design. Only the number to the
  right of the ``=`` is captured.
* ``mesh.check`` may indent the ``Volume statistics:`` and ``Face area
  statistics:`` headers with one leading space and use single-space
  separators between ``total volume`` and ``(m3)``. The regex
  whitespace classes (``\\s+``, ``\\s*``) tolerate both styles.

Both parsers are intentionally **lenient**. Anything that cannot be matchd
collapses to ``None`` rather than raising. Callers are expected to
treat ``None`` as ``unknown``, never as a passing score.

Tested against transcripts from both pressure-based and density-based
solvers in :mod:`tests.test_mesh_report_parsers`.
"""

from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Regexes — anchored on the literal phrasing Fluent emits.
# ---------------------------------------------------------------------------
#
# Fluent always prints numbers in C locale (decimal point, scientific
# notation), so a single ``[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?`` covers
# every numeric token. We deliberately allow leading whitespace (Fluent
# indents the report block with tabs and spaces).

_NUMBER = r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"

# Quality block: three known headline lines. Each is on its own line and
# has the form  "<key> = <number>" — usually followed by " cell <id> on
# zone <z>" which we ignore.
_RE_MIN_ORTHOGONAL_QUALITY = re.compile(
    r"Minimum\s+Orthogonal\s+Quality\s*=\s*(" + _NUMBER + r")",
    re.IGNORECASE,
)
_RE_MAX_ORTHO_SKEW = re.compile(
    r"Maximum\s+Ortho\s+Skew\s*=\s*(" + _NUMBER + r")",
    re.IGNORECASE,
)
_RE_MAX_ASPECT_RATIO = re.compile(
    r"Maximum\s+Aspect\s+Ratio\s*=\s*(" + _NUMBER + r")",
    re.IGNORECASE,
)

# Mesh.check block fragments. The wording across Fluent versions is:
#   "Domain Extents:"
#       "x-coordinate: min (m) = -1.000e+00, max (m) =  1.000e+00"
#       "y-coordinate: ..."
#       "z-coordinate: ..."
#   "Volume statistics:"
#       "minimum volume (m3): 1.234e-09"
#       "maximum volume (m3): 5.678e-03"
#       "total volume  (m3): 4.560e-02"
#   "Face area statistics:"
#       "minimum face area (m2): 1.234e-06"
#       "maximum face area (m2): 5.678e-03"
_RE_AXIS_EXTENT = re.compile(
    r"([xyz])-coordinate\s*:\s*min\s*\([^)]*\)\s*=\s*(" + _NUMBER + r")"
    r"\s*,\s*max\s*\([^)]*\)\s*=\s*(" + _NUMBER + r")",
    re.IGNORECASE,
)
_RE_VOLUME_MIN = re.compile(
    r"minimum\s+volume\s*\([^)]*\)\s*:\s*(" + _NUMBER + r")",
    re.IGNORECASE,
)
_RE_VOLUME_MAX = re.compile(
    r"maximum\s+volume\s*\([^)]*\)\s*:\s*(" + _NUMBER + r")",
    re.IGNORECASE,
)
_RE_VOLUME_TOTAL = re.compile(
    r"total\s+volume\s*\([^)]*\)\s*:\s*(" + _NUMBER + r")",
    re.IGNORECASE,
)
_RE_FACE_AREA_MIN = re.compile(
    r"minimum\s+face\s+area\s*\([^)]*\)\s*:\s*(" + _NUMBER + r")",
    re.IGNORECASE,
)
_RE_FACE_AREA_MAX = re.compile(
    r"maximum\s+face\s+area\s*\([^)]*\)\s*:\s*(" + _NUMBER + r")",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# parse_mesh_quality
# ---------------------------------------------------------------------------


def _to_float(raw: str | None) -> float | None:
    """Convert text to a floating-point value.

    Parameters
    ----------
    raw : str | None
        Raw string value to parse or validate.

    Returns
    -------
    float | None
        Optional value produced by the operation.
    """
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def parse_mesh_quality(stdout: str | None) -> dict[str, float | None]:
    """Extract the three headline quality numbers from a ``mesh.quality`` report.

    The returned mapping contains ``"min_orthogonal_quality"``,
    ``"max_ortho_skew"``, and ``"max_aspect_ratio"``. A value is
    ``None`` when the line is not found in ``stdout`` (no mesh loaded,
    command failed, transcript capture truncated). Never raises.

    Parameters
    ----------
    stdout : str | None
        Stdout to supply to the function.

    Returns
    -------
    dict[str, float | None]
        Parsed quality metrics keyed by Fluent's headline mesh-quality fields.
    """
    empty: dict[str, float | None] = {
        "min_orthogonal_quality": None,
        "max_ortho_skew": None,
        "max_aspect_ratio": None,
    }
    if not stdout:
        return empty
    out = dict(empty)
    m = _RE_MIN_ORTHOGONAL_QUALITY.search(stdout)
    if m:
        out["min_orthogonal_quality"] = _to_float(m.group(1))
    m = _RE_MAX_ORTHO_SKEW.search(stdout)
    if m:
        out["max_ortho_skew"] = _to_float(m.group(1))
    m = _RE_MAX_ASPECT_RATIO.search(stdout)
    if m:
        out["max_aspect_ratio"] = _to_float(m.group(1))
    return out


# ---------------------------------------------------------------------------
# parse_mesh_check
# ---------------------------------------------------------------------------


def _scan_warnings_and_errors(stdout: str) -> tuple[list[str], list[str]]:
    """Return (warnings, errors) lists from a ``mesh.check`` report.

    Lines starting with ``Warning:`` or ``Error:`` (case-insensitive,
    leading whitespace allowed) are collected verbatim, stripped of
    leading whitespace, with the prefix removed. Duplicates are
    preserved (Fluent prints one line per offending entity, and the
    multiplicity is meaningful diagnostic info).

    Parameters
    ----------
    stdout : str
        Stdout to supply to the function.

    Returns
    -------
    tuple[list[str], list[str]]
        Collection containing the operation results.
    """
    warnings: list[str] = []
    errors: list[str] = []
    for line in stdout.splitlines():
        s = line.strip()
        if not s:
            continue
        low = s.lower()
        if low.startswith("warning:"):
            warnings.append(s[len("warning:") :].strip())
        elif low.startswith("error:"):
            errors.append(s[len("error:") :].strip())
    return warnings, errors


# Hard cap on the cleaned ``raw`` field's size. PyFluent's settings-API
# wrapper around ``mesh.check`` emits ~7–15 KB of Scheme-call trace
# (``(api-get-attr ...)``, ``(cx-sendq ...)``, ``(inquire-cell-threads)``,
# ``(thread-type thread)`` × N partitions, …) for every invocation —
# none of which has diagnostic value to the caller. The cleaner below
# drops the noise, and this cap is the safety net that keeps the
# envelope under the agent's 8 KB tool-result limit even when Fluent
# adds new Scheme noise we don't yet filter, which would otherwise
# overflow the ``tool_result_too_large`` response limit.
_RAW_HARD_CAP_CHARS: int = 2000

# Patterns that match purely internal Scheme call traces. These lines
# appear because PyFluent's settings-API wrapper enables verbose
# scheme-eval tracing while invoking ``mesh.check``. They carry no
# diagnostic value to users or clients and dwarf the actual mesh-check
# headline lines in size — dropping them keeps ``raw`` small enough to
# fit alongside the structured fields in the tool envelope.
_SCHEME_TRACE_LINE_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Bare action/lifecycle markers
    re.compile(r"^\(before\)\s*$"),
    re.compile(r"^\(action\)\s*$"),
    re.compile(r"^\(after\)\s*$"),
    # `(api-...)` / `(cx-...)` / `(rp-...)` / `(remoting-...)` /
    # `(suppress-...)` / `(set-remote-call ...)` and friends — verbose
    # PyFluent introspection noise.
    re.compile(
        r"^\("
        r"(api-|cx-|rp-|remoting-|suppress-|set-remote-call|fn |%|"
        r"#\[|context-rp|nc-rp|get-current-contexts|inquire-|"
        r"thread-type|thread-id|update-bcs|update-czs|grid-check|"
        r"%grid-check|func |get-varenv-object|cxsetvar|getq-|cx-var|"
        r"cx-mesher-mode|cx-send|cx-enable-input-dialogs|"
        r"command-args-to-callback-args|rpsetvar|rpgetvar|"
        r"api-checks-before-command-or-query|"
        r"api-trigger-event-wrapper|api-execute-cmd|api-eval-fn|"
        r"api-get-attr|api-get-attrs|api-get-obj|api-get-type|"
        r"api-filtered-active|api-filtered-read-only|api-has-any-observers|"
        r"%rp-var-value-set|get-all-threads|pad %display)"
    ),
)


def _clean_check_raw(stdout: str) -> str:
    """Drop Scheme call-trace noise from a ``mesh.check`` transcript.

    Keeps every line that is NOT a purely internal Scheme trace and is
    NOT obviously a procedure-call dump. The output is suitable for
    embedding into the tool envelope: it preserves the diagnostic
    headline lines Fluent prints (``Domain Extents:``, ``Volume
    statistics:``, ``Face area statistics:``, ``Checking mesh...``,
    ``Done.``, ``Warning:`` / ``Error:`` rows, and any free-text
    summary) and discards everything else.

    Also enforces ``_RAW_HARD_CAP_CHARS`` as the final safety net so a
    new Scheme-trace pattern we haven't seen yet can never push the
    envelope over the 8 KB tool-result limit.

    Parameters
    ----------
    stdout : str
        Stdout to supply to the function.

    Returns
    -------
    str
        String result produced by the function.
    """
    if not stdout:
        return ""
    kept: list[str] = []
    for raw_line in stdout.splitlines():
        # Preserve original whitespace for the diagnostic headline
        # lines (they're indented intentionally by Fluent).
        stripped = raw_line.lstrip()
        if not stripped:
            continue
        skip = False
        for pat in _SCHEME_TRACE_LINE_PATTERNS:
            if pat.match(stripped):
                skip = True
                break
        if skip:
            continue
        kept.append(raw_line.rstrip())

    cleaned = "\n".join(kept).strip()
    if len(cleaned) <= _RAW_HARD_CAP_CHARS:
        return cleaned
    # Hard cap fallback: head + tail with an explicit truncation
    # marker so the consumer can see where the cut happened.
    head = cleaned[: _RAW_HARD_CAP_CHARS - 400]
    tail = cleaned[-300:]
    return (
        f"{head}\n... [truncated {len(cleaned) - len(head) - len(tail)} "
        f"chars of Fluent transcript] ...\n{tail}"
    )


def parse_mesh_check(stdout: str | None) -> dict[str, Any]:
    """Extract structured fields from a ``mesh.check`` report.

    Output shape is documented on
    :meth:`ansys.fluent.mcp.common.backend.Backend.mesh_check`. Missing
    fields are emitted as ``None`` (or empty list for ``warnings``/``errors``).
    Never raises.

    The ``raw`` field always carries the verbatim stdout chunk so
    callers that need a feature this parser doesn't extract yet can
    still get at it without re-running the command.

    Parameters
    ----------
    stdout : str | None
        Stdout to supply to the function.

    Returns
    -------
    dict[str, Any]
        Mapping containing the operation result.
    """
    out: dict[str, Any] = {
        "domain_extents": {"x": None, "y": None, "z": None},
        "volume_min": None,
        "volume_max": None,
        "volume_total": None,
        "face_area_min": None,
        "face_area_max": None,
        "warnings": [],
        "errors": [],
        # ``raw`` carries the verbatim Fluent transcript stripped of
        # internal Scheme-trace noise and hard-capped at
        # ``_RAW_HARD_CAP_CHARS``. The structured fields above are the
        # primary surface for downstream consumers — ``raw`` is a
        # last-resort fallback for new patterns we haven't extracted
        # yet, NOT a debug stream. See the cleaner docstring for the
        # exclusion list.
        "raw": _clean_check_raw(stdout) if stdout else "",
    }
    if not stdout:
        return out

    extents: dict[str, tuple[float, float] | None] = {
        "x": None,
        "y": None,
        "z": None,
    }
    for axis, lo, hi in _RE_AXIS_EXTENT.findall(stdout):
        lo_f = _to_float(lo)
        hi_f = _to_float(hi)
        if lo_f is not None and hi_f is not None:
            extents[axis.lower()] = (lo_f, hi_f)
    out["domain_extents"] = extents

    m = _RE_VOLUME_MIN.search(stdout)
    if m:
        out["volume_min"] = _to_float(m.group(1))
    m = _RE_VOLUME_MAX.search(stdout)
    if m:
        out["volume_max"] = _to_float(m.group(1))
    m = _RE_VOLUME_TOTAL.search(stdout)
    if m:
        out["volume_total"] = _to_float(m.group(1))
    m = _RE_FACE_AREA_MIN.search(stdout)
    if m:
        out["face_area_min"] = _to_float(m.group(1))
    m = _RE_FACE_AREA_MAX.search(stdout)
    if m:
        out["face_area_max"] = _to_float(m.group(1))

    warnings, errors = _scan_warnings_and_errors(stdout)
    out["warnings"] = warnings
    out["errors"] = errors
    return out


__all__ = ["parse_mesh_quality", "parse_mesh_check"]
