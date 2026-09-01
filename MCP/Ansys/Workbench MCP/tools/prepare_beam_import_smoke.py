from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "examples" / "workbench_import_step_v252.wbjn.template"


def render(step: Path, project: Path, status: Path, system_name: str, units: str, allow_overwrite: bool, open_spaceclaim: bool) -> str:
    content = TEMPLATE.read_text(encoding="utf-8")
    replacements = {
        "__STEP_PATH_PY__": repr(str(step)),
        "__PROJECT_PATH_PY__": repr(str(project)),
        "__STATUS_PATH_PY__": repr(str(status)),
        "__SYSTEM_NAME_PY__": repr(system_name),
        "__UNITS_PY__": repr(units),
        "__ALLOW_OVERWRITE_PY__": repr(bool(allow_overwrite)),
        "__OPEN_SPACECLAIM_PY__": repr(bool(open_spaceclaim)),
    }
    for token, value in replacements.items():
        content = content.replace(token, value)
    unresolved = [token for token in replacements if token in content]
    if unresolved:
        raise RuntimeError("Unresolved template tokens: " + ", ".join(unresolved))
    return content


def prepare(args: argparse.Namespace) -> dict:
    step = Path(args.step).expanduser().resolve()
    project = Path(args.project).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    if step.suffix.lower() not in {".step", ".stp"}:
        raise ValueError("Input must use .step or .stp")
    if not step.is_file() or step.stat().st_size <= 0:
        raise FileNotFoundError("STEP file is missing or empty: %s" % step)
    if project.exists() and not args.allow_overwrite:
        raise FileExistsError("Project exists and overwrite is not authorized: %s" % project)
    output_dir.mkdir(parents=True, exist_ok=True)
    journal = output_dir / "workbench_import_step_v252.wbjn"
    status = output_dir / "workbench_import_status.json"
    request = output_dir / "beam_import_smoke_request.json"
    if journal.exists() and not args.allow_overwrite:
        raise FileExistsError("Rendered journal exists and overwrite is not authorized: %s" % journal)
    journal.write_text(
        render(step, project, status, args.system_name, args.units, args.allow_overwrite, args.open_spaceclaim),
        encoding="utf-8",
    )
    payload = {
        "schema_version": 1,
        "workflow": "fusion_step_to_beam_smoke",
        "phase": "PREPARED",
        "status": "NOT_RUN",
        "ok": False,
        "source_step": str(step),
        "project_path": str(project),
        "units": args.units,
        "gates": {
            "step_file_check": True,
            "workbench_step_import": None,
            "spaceclaim_beam_idealization": None,
            "mechanical_line_body_import": None,
        },
        "members": [],
        "warnings": ["Live ANSYS validation has not run."],
        "errors": [],
        "evidence": {"journal_path": str(journal), "status_path": str(status), "step_bytes": step.stat().st_size},
    }
    request.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare a guarded Workbench STEP import smoke journal.")
    parser.add_argument("--step", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--units", choices=["mm", "m", "in"], default="mm")
    parser.add_argument("--system-name", default="Fusion STEP Beam Intake")
    parser.add_argument("--allow-overwrite", action="store_true")
    parser.add_argument("--open-spaceclaim", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(prepare(args), indent=2, ensure_ascii=False))
        return 0
    except Exception as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
