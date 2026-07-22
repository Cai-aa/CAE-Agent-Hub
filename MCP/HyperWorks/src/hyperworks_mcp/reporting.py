from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any


def _table(rows: list[tuple[str, Any]]) -> str:
    return "\n".join(
        f"<tr><th>{html.escape(str(label))}</th><td>{html.escape(str(value))}</td></tr>"
        for label, value in rows
    )


def write_job_report(
    output_directory: Path,
    output_name: str,
    job: dict[str, Any],
    artifacts: dict[str, Any],
    audit: dict[str, Any] | None = None,
    evidence_files: list[Path] | None = None,
) -> dict[str, Any]:
    output_directory.mkdir(parents=True, exist_ok=True)
    stem = Path(output_name).stem or "hyperworks_job_report"
    html_path = output_directory / f"{stem}.html"
    json_path = output_directory / f"{stem}.json"
    if html_path.exists() or json_path.exists():
        raise ValueError("Report output already exists")
    evidence = [path for path in (evidence_files or []) if path.is_file()]
    payload = {
        "job": job,
        "artifacts": artifacts,
        "audit": audit,
        "evidence_files": [str(path) for path in evidence],
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    category_rows = []
    for category, items in artifacts.get("categories", {}).items():
        category_rows.append((category, len(items)))
    audit_rows = []
    if audit:
        audit_rows = [
            ("passed", audit.get("passed")),
            ("starter normal termination", audit.get("gates", {}).get("starter_normal_termination")),
            ("engine normal termination", audit.get("gates", {}).get("engine_normal_termination")),
            ("maximum absolute energy error (%)", audit.get("engine", {}).get("maximum_absolute_energy_error_percent")),
            ("maximum absolute mass error (%)", audit.get("engine", {}).get("maximum_absolute_mass_error_percent")),
            ("minimum time step", audit.get("engine", {}).get("minimum_time_step")),
        ]
    images = "\n".join(
        f'<figure><img src="{html.escape(path.as_uri())}" alt="CAE evidence"><figcaption>{html.escape(path.name)}</figcaption></figure>'
        for path in evidence
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".svg"}
    )
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>HyperWorks job report</title>
<style>body{{font:15px/1.5 Arial,sans-serif;max-width:1100px;margin:32px auto;padding:0 20px;color:#20242a}}
h1,h2{{color:#15365a}}table{{border-collapse:collapse;width:100%;margin:12px 0 24px}}
th,td{{border:1px solid #ccd5df;padding:8px;text-align:left}}th{{width:38%;background:#eef3f8}}
img{{max-width:100%;border:1px solid #ccd5df}}code{{background:#eef3f8;padding:2px 4px}}</style></head>
<body><h1>HyperWorks Job Report</h1>
<h2>Job</h2><table>{_table([("job id", job.get("job_id")), ("project id", job.get("project_id")), ("kind", job.get("kind")), ("state", job.get("state")), ("return code", job.get("return_code"))])}</table>
<h2>Artifacts</h2><table>{_table(category_rows)}</table>
<h2>Quality audit</h2><table>{_table(audit_rows or [("audit", "not available for this solver/job")])}</table>
<h2>Evidence</h2>{images or '<p>No image evidence was attached.</p>'}
<p>Machine-readable evidence: <code>{html.escape(json_path.name)}</code></p></body></html>"""
    html_path.write_text(document, encoding="utf-8")
    return {
        "generated": True,
        "html_file": str(html_path),
        "json_file": str(json_path),
        "html_size_bytes": html_path.stat().st_size,
        "json_size_bytes": json_path.stat().st_size,
        "evidence_count": len(evidence),
    }
