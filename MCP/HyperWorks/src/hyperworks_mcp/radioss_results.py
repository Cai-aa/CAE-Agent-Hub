from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any


_PROGRESS_RE = re.compile(
    r"^\s*(?P<cycle>\d+)\s+"
    r"(?P<time>[+\-0-9.Ee]+)\s+"
    r"(?P<timestep>[+\-0-9.Ee]+)\s+"
    r"(?P<element_type>[A-Za-z0-9_]+)\s+"
    r"(?P<element_id>\d+)\s+"
    r"(?P<energy_error>[+\-0-9.Ee]+)%\s+"
    r"(?P<internal_energy>[+\-0-9.Ee]+)\s+"
    r"(?P<translational_kinetic_energy>[+\-0-9.Ee]+)\s+"
    r"(?P<rotational_kinetic_energy>[+\-0-9.Ee]+)\s+"
    r"(?P<external_work>[+\-0-9.Ee]+)\s+"
    r"(?P<mass_error>[+\-0-9.Ee]+)\s+"
    r"(?P<total_mass>[+\-0-9.Ee]+)\s+"
    r"(?P<mass_added>[+\-0-9.Ee]+)"
)


def parse_radioss_engine_output(text: str) -> dict[str, Any]:
    """Extract auditable explicit-dynamics quality signals from Engine output."""
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        match = _PROGRESS_RE.match(line)
        if not match:
            continue
        values = match.groupdict()
        try:
            row = {
                "cycle": int(values["cycle"]),
                "time": float(values["time"]),
                "time_step": float(values["timestep"]),
                "controlling_element_type": values["element_type"],
                "controlling_element_id": int(values["element_id"]),
                "energy_error_percent": float(values["energy_error"]),
                "internal_energy": float(values["internal_energy"]),
                "translational_kinetic_energy": float(
                    values["translational_kinetic_energy"]
                ),
                "rotational_kinetic_energy": float(
                    values["rotational_kinetic_energy"]
                ),
                "external_work": float(values["external_work"]),
                "mass_error_percent": float(values["mass_error"]),
                "total_mass": float(values["total_mass"]),
                "mass_added": float(values["mass_added"]),
            }
        except (TypeError, ValueError):
            continue
        if all(
            math.isfinite(value)
            for key, value in row.items()
            if key not in {"controlling_element_type"}
        ):
            rows.append(row)

    lower = text.casefold()
    normal_termination = "normal termination" in lower
    negative_volume = any(
        marker in lower
        for marker in (
            "negative volume",
            "negative solid volume",
            "zero or negative volume",
        )
    )
    fatal_error = any(
        marker in lower
        for marker in ("fatal error", "abnormal termination", "termination with error")
    )
    penetration_error = any(
        marker in lower
        for marker in (
            "initial penetration error",
            "penetration is too large",
            "excessive penetration",
        )
    )
    maximum_absolute_energy_error = (
        max(abs(row["energy_error_percent"]) for row in rows) if rows else None
    )
    maximum_absolute_mass_error = (
        max(abs(row["mass_error_percent"]) for row in rows) if rows else None
    )
    minimum_time_step = min((row["time_step"] for row in rows), default=None)
    return {
        "normal_termination": normal_termination,
        "fatal_error_detected": fatal_error,
        "negative_volume_detected": negative_volume,
        "contact_penetration_error_detected": penetration_error,
        "progress_row_count": len(rows),
        "first_progress": rows[0] if rows else None,
        "last_progress": rows[-1] if rows else None,
        "maximum_absolute_energy_error_percent": maximum_absolute_energy_error,
        "maximum_absolute_mass_error_percent": maximum_absolute_mass_error,
        "minimum_time_step": minimum_time_step,
    }


def audit_radioss_output_files(
    starter_output: Path | None,
    engine_output: Path,
    maximum_absolute_energy_error_percent: float = 15.0,
    maximum_added_mass_percent: float = 5.0,
) -> dict[str, Any]:
    if not engine_output.is_file():
        raise ValueError(f"Radioss Engine output does not exist: {engine_output}")
    engine_text = engine_output.read_text(encoding="utf-8", errors="replace")
    parsed = parse_radioss_engine_output(engine_text)
    starter_text = (
        starter_output.read_text(encoding="utf-8", errors="replace")
        if starter_output and starter_output.is_file()
        else ""
    )
    starter_lower = starter_text.casefold()
    starter_ok = bool(starter_text) and "normal termination" in starter_lower
    starter_errors = None
    starter_warnings = None
    errors_match = re.findall(r"(\d+)\s+error\(s\)", starter_lower)
    warnings_match = re.findall(r"(\d+)\s+warning\(s\)", starter_lower)
    if errors_match:
        starter_errors = int(errors_match[-1])
    if warnings_match:
        starter_warnings = int(warnings_match[-1])

    energy = parsed["maximum_absolute_energy_error_percent"]
    mass_error = parsed["maximum_absolute_mass_error_percent"]
    gates = {
        "starter_normal_termination": starter_ok and starter_errors == 0,
        "engine_normal_termination": parsed["normal_termination"]
        and not parsed["fatal_error_detected"],
        "energy_error_within_limit": energy is not None
        and energy <= float(maximum_absolute_energy_error_percent),
        "added_mass_within_limit": mass_error is not None
        and mass_error <= float(maximum_added_mass_percent),
        "no_negative_volume": not parsed["negative_volume_detected"],
        "no_contact_penetration_error": not parsed[
            "contact_penetration_error_detected"
        ],
        "positive_time_step": parsed["minimum_time_step"] is not None
        and parsed["minimum_time_step"] > 0.0,
    }
    return {
        "passed": all(gates.values()),
        "gates": gates,
        "limits": {
            "maximum_absolute_energy_error_percent": float(
                maximum_absolute_energy_error_percent
            ),
            "maximum_added_mass_percent": float(maximum_added_mass_percent),
        },
        "starter": {
            "output_file": str(starter_output) if starter_output else None,
            "normal_termination": starter_ok,
            "error_count": starter_errors,
            "warning_count": starter_warnings,
        },
        "engine": {"output_file": str(engine_output), **parsed},
    }
