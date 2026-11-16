"""Read Abaqus job diagnostics locally, without occupying the CAE kernel.

File evidence is a snapshot, not process telemetry or engineering acceptance.
Use a separate directory/name for each run: old output is not distinguishable
from a current run solely from its text. No project units or tolerances belong here.
"""
from __future__ import annotations

import codecs
from collections import deque
from pathlib import Path
import re
from typing import Any, BinaryIO, Iterator

_DIAGNOSTIC = re.compile(r"^\s*\*{3}\s*(ERROR|WARNING)\b\s*:?(.*)", re.IGNORECASE)
_WRAPPER_ERROR = re.compile(r"^\s*Abaqus\s+Error\s*:", re.IGNORECASE)
_ANALYSIS_COMPLETE = re.compile(
    r"^\s*(?:THE\s+)?ANALYSIS\s+HAS\s+(?:BEEN\s+COMPLETED|COMPLETED\s+SUCCESSFULLY)\s*[.!]?\s*$",
    re.IGNORECASE,
)
_DATACHECK_COMPLETE = re.compile(r"\bANALYSIS\s+DATA\s*CHECK\s+COMPLETE\b", re.IGNORECASE)
_ANALYSIS_STARTED = re.compile(r"^\s*INCREMENT\s+\d+\s+STARTS\.\s+ATTEMPT\s+NUMBER\b", re.IGNORECASE)
_ANALYSIS_FAILED = re.compile(r"^\s*(?:THE\s+)?ANALYSIS\s+HAS\s+NOT\s+BEEN\s+COMPLETED\s*[.!]?\s*$", re.IGNORECASE)
_EXPLICIT_HEADER = re.compile(
    r"^\s*INCREMENT\s+TIME\s+TIME\s+TIME\s+INCREMENT\b", re.IGNORECASE
)
_EXPLICIT_ROW = re.compile(
    r"^\s*(\d+)\s+[\d.Ee+-]+\s+[\d.Ee+-]+\s+\d+:\d{2}:\d{2}\s+[\d.Ee+-]+(?:\s|$)"
)
_NEWLINE = re.compile(r"\r\n|\r|\n")


def _strict_text_lines(handle: BinaryIO, encoding: str) -> Iterator[str]:
    """Yield complete valid lines before a decoding error, then raise it.

    TextIOWrapper can discard an entire decoded buffer when one later byte is
    invalid. Recover only that buffer's valid prefix using the decoder's saved
    state; byte-wise decoding occurs solely on the error path. No bytes are
    replaced or skipped, including for BOM/stateful/multibyte encodings.
    """
    decoder = codecs.getincrementaldecoder(encoding)(errors="strict")
    pending = ""
    while True:
        raw = handle.read(8192)
        state = decoder.getstate()
        failure = None
        try:
            decoded = decoder.decode(raw, final=not raw)
        except UnicodeDecodeError as exc:
            decoder.setstate(state)
            prefix = []
            for value in raw:
                try:
                    prefix.append(decoder.decode(bytes((value,)), final=False))
                except UnicodeDecodeError:
                    break
            decoded = "".join(prefix)
            failure = exc
        pending += decoded
        end = 0
        for newline in _NEWLINE.finditer(pending):
            # Retain a trailing CR until CRLF can be distinguished, except at
            # EOF/error where a CR itself completes the preceding valid line.
            if newline.group() == "\r" and newline.end() == len(pending) and raw and failure is None:
                break
            yield pending[end:newline.end()]
            end = newline.end()
        pending = pending[end:]
        if failure is not None:
            # An unterminated prefix is not a complete line and is not parsed.
            raise failure
        if not raw:
            if pending:
                yield pending
            return


def validate_job_name(job_name: str) -> str:
    """Accept a file stem, never a path or a Windows alternate data stream."""
    name = job_name.strip()
    if not name or name in {".", ".."} or any(c in name for c in '/\\:\x00\r\n'):
        raise ValueError("job_name must be a nonempty file stem without path separators")
    return name


def inspect_job_files(
    job_name: str,
    job_directory: str,
    *,
    encoding: str = "utf-8-sig",
    tail_lines: int = 8,
    diagnostic_limit: int = 12,
) -> dict[str, Any]:
    """Inspect .sta/.msg/.dat/.log using bounded tails and observed counts.

    Missing optional files are normal; read/decoding errors are explicit. A
    wrapper ``Abaqus JOB ... COMPLETED`` line alone never proves an analysis
    completed (it can describe a data check). ``incomplete`` does not assert a
    live process; the caller can combine it with CAE job status. Counts refer to
    diagnostic headers across files and may count a repeated solver message.
    """
    name = validate_job_name(job_name)
    directory = Path(job_directory).expanduser()
    if not directory.is_absolute() or not directory.is_dir():
        raise ValueError("job_directory must be an existing absolute directory")
    directory = directory.resolve()
    if not 1 <= tail_lines <= 1000 or not 1 <= diagnostic_limit <= 10000:
        raise ValueError("tail_lines must be 1..1000 and diagnostic_limit 1..10000")
    try:
        codecs.lookup(encoding)
    except LookupError as exc:
        raise ValueError("Unknown text encoding: " + encoding) from exc

    files: dict[str, Any] = {}
    diagnostics: deque[dict[str, Any]] = deque(maxlen=diagnostic_limit)
    evidence: list[dict[str, Any]] = []
    read_errors: list[dict[str, str]] = []
    error_count = warning_count = 0
    has_content = False
    analysis_completed = data_check_completed = analysis_started = analysis_failed = False

    zero_only_explicit_status = False

    for suffix in ("sta", "msg", "dat", "log"):
        path = directory / (name + "." + suffix)
        entry: dict[str, Any] = {"path": str(path), "state": "missing", "encoding": encoding,
                                 "tail": [], "partial": False}
        files[suffix] = entry
        local_diagnostics: deque[dict[str, Any]] = deque(maxlen=diagnostic_limit)
        local_evidence: list[dict[str, Any]] = []
        tail: deque[str] = deque(maxlen=tail_lines)
        local_errors = local_warnings = lines = 0
        pending: dict[str, Any] | None = None
        continuation_count = 0
        stat_before = None
        local_analysis_started = False
        explicit_progress_header = False
        explicit_progress_row_seen = False
        try:
            stat_before = path.stat()
            with path.open("rb") as handle:
                for lines, raw in enumerate(_strict_text_lines(handle, encoding), 1):
                    text = raw.rstrip("\r\n")
                    tail.append(text)
                    match = _DIAGNOSTIC.match(text)
                    wrapper_error = _WRAPPER_ERROR.match(text)
                    if match or wrapper_error:
                        severity = match.group(1).lower() if match else "error"
                        pending = {"severity": severity, "path": str(path), "line": lines, "message": text.strip()}
                        local_diagnostics.append(pending)
                        continuation_count = 0
                        if severity == "error":
                            local_errors += 1
                        else:
                            local_warnings += 1
                    elif pending is not None:
                        # Keep short indented continuation lines for actionable context.
                        if text.strip() and text[:1].isspace() and continuation_count < 4:
                            pending["message"] += "\n" + text.strip()
                            continuation_count += 1
                        else:
                            pending = None
                    if suffix == "sta":
                        explicit_progress_header |= bool(_EXPLICIT_HEADER.match(text))
                        if explicit_progress_header and (row := _EXPLICIT_ROW.match(text)):
                            explicit_progress_row_seen = True
                            if int(row[1]) > 0 and not local_analysis_started:
                                local_analysis_started = True
                                local_evidence.append({"kind": "analysis_started", "path": str(path),
                                                       "line": lines, "text": text.strip()})
                    if _ANALYSIS_COMPLETE.match(text):
                        local_evidence.append({"kind": "analysis_completed", "path": str(path), "line": lines, "text": text.strip()})
                    if _DATACHECK_COMPLETE.search(text):
                        local_evidence.append({"kind": "data_check_completed", "path": str(path), "line": lines, "text": text.strip()})
                    if not local_analysis_started and _ANALYSIS_STARTED.match(text):
                        local_analysis_started = True
                        local_evidence.append({"kind": "analysis_started", "path": str(path), "line": lines, "text": text.strip()})
                    if _ANALYSIS_FAILED.match(text):
                        local_evidence.append({"kind": "analysis_failed", "path": str(path), "line": lines, "text": text.strip()})
            stat_after = path.stat()
        except FileNotFoundError:
            # A file disappearing during the read is an error, rather than absent.
            if stat_before is not None:
                entry.update(state="read_error", error="FileNotFoundError: file disappeared during read")
                read_errors.append({"path": str(path), "error": entry["error"]})
            else:
                continue
        except (OSError, UnicodeError) as exc:
            entry.update(state="read_error", error=type(exc).__name__ + ": " + str(exc))
            read_errors.append({"path": str(path), "error": entry["error"]})
        else:
            changed = (stat_before.st_size, stat_before.st_mtime_ns) != (stat_after.st_size, stat_after.st_mtime_ns)
            entry.update(state="readable", size_bytes=stat_after.st_size,
                         modified_ns=stat_after.st_mtime_ns, changed_during_read=changed)
        # Preserve successfully decoded/processed evidence even if a later read
        # fails. Known errors must never disappear behind another file's success.
        entry.update(tail=list(tail), line_count=lines,
                     partial=entry["state"] == "read_error" and lines > 0)
        has_content = has_content or lines > 0
        diagnostics.extend(local_diagnostics)
        # Explicit can print the success footer after initialization alone.
        if explicit_progress_row_seen and not local_analysis_started:
            zero_only_explicit_status = True
            for observed in local_evidence:
                if observed["kind"] == "analysis_completed":
                    observed["kind"] = "completion_marker_without_advance"
        evidence.extend(local_evidence)
        error_count += local_errors
        warning_count += local_warnings
        analysis_completed = analysis_completed or any(e["kind"] == "analysis_completed" for e in local_evidence)
        data_check_completed = data_check_completed or any(e["kind"] == "data_check_completed" for e in local_evidence)
        analysis_started = analysis_started or local_analysis_started
        analysis_failed = analysis_failed or any(e["kind"] == "analysis_failed" for e in local_evidence)

    if error_count or analysis_failed:
        state, complete = "failed", False
    elif analysis_completed:
        state, complete = "completed", True
    elif data_check_completed and not analysis_started and (
        files["sta"]["state"] != "readable" or zero_only_explicit_status
    ):
        state, complete = "data_check_completed", False
    else:
        state, complete = ("incomplete" if has_content else "unknown"), None
    if state == "data_check_completed":
        stage = "data_check"
    elif analysis_started or analysis_completed or analysis_failed or files["sta"]["state"] == "readable":
        stage = "analysis"
    else:
        stage = "data_check" if data_check_completed else "unknown"
    return {
        "job_name": name,
        "job_directory": str(directory),
        "state": state,
        "stage": stage,
        "analysis_completed": complete,
        "terminal_failure_detected": analysis_failed,
        "read_success": not read_errors,
        "read_errors": read_errors,
        "error_count": error_count,
        "warning_count": warning_count,
        "diagnostics": list(diagnostics),
        "completion_evidence": evidence,
        "files": files,
        "lock_file_present": (directory / (name + ".lck")).exists(),
        "limitations": [
            "File evidence does not prove a live solver process or engineering acceptance.",
            "Use a unique job directory/name per run; stale files may conflict with current output.",
            "Diagnostic counts are header occurrences across files, not deduplicated solver events.",
        ],
    }
