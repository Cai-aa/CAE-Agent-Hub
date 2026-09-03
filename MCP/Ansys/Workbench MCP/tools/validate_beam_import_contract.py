from __future__ import annotations

import json
import sys
from pathlib import Path


REQUIRED = {"schema_version", "workflow", "phase", "status", "ok", "source_step", "units", "gates", "warnings", "errors", "evidence"}
GATES = ("step_file_check", "workbench_step_import", "spaceclaim_beam_idealization", "mechanical_line_body_import")
PHASES = {"PREPARED", "WORKBENCH_STEP_IMPORT", "SPACECLAIM_BEAM_IDEALIZATION", "MECHANICAL_LINE_BODY_IMPORT"}
STATUSES = {"NOT_RUN", "BLOCKED", "FAIL", "PASS"}


def validate(data: dict) -> list[str]:
    errors = []
    missing = sorted(REQUIRED - set(data))
    if missing:
        errors.append("missing keys: " + ", ".join(missing))
    if data.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if data.get("workflow") != "fusion_step_to_beam_smoke":
        errors.append("workflow must be fusion_step_to_beam_smoke")
    if data.get("phase") not in PHASES:
        errors.append("invalid phase")
    if data.get("status") not in STATUSES:
        errors.append("invalid status")
    if data.get("units") not in {"mm", "m", "in"}:
        errors.append("units must be mm, m, or in")
    if not isinstance(data.get("ok"), bool):
        errors.append("ok must be boolean")
    gates = data.get("gates")
    if not isinstance(gates, dict):
        errors.append("gates must be an object")
    else:
        for gate in GATES:
            if gate not in gates:
                errors.append("missing gate: " + gate)
            elif gates[gate] not in {True, False, None}:
                errors.append("gate must be true, false, or null: " + gate)
    for key in ("warnings", "errors"):
        if not isinstance(data.get(key), list):
            errors.append(key + " must be an array")
    if data.get("status") == "PASS":
        if data.get("ok") is not True:
            errors.append("PASS requires ok=true")
        if isinstance(gates, dict) and any(gates.get(gate) is not True for gate in GATES):
            errors.append("PASS requires every smoke gate=true")
        if data.get("errors"):
            errors.append("PASS requires an empty errors array")
    if data.get("ok") is True and data.get("status") != "PASS":
        errors.append("ok=true requires status=PASS")
    return errors


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(json.dumps({"ok": False, "errors": ["usage: validate_beam_import_contract.py result.json"]}))
        return 2
    try:
        data = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    except Exception as error:
        print(json.dumps({"ok": False, "errors": [str(error)]}))
        return 2
    errors = validate(data)
    print(json.dumps({"ok": not errors, "errors": errors}, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
