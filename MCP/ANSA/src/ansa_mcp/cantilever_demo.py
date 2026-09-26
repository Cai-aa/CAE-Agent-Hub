"""A fixed, auditable ANSA/Abaqus cantilever exercise driven by MCP tools."""

from __future__ import annotations

import json
import hashlib
import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path

from .environment import environment_report
from .settings import Settings, within


LENGTH_MM = 200.0
WIDTH_MM = 20.0
HEIGHT_MM = 10.0
YOUNG_MPA = 210000.0
POISSON = 0.3
END_FORCE_N = -100.0
NX, NY, NZ = 40, 4, 2
RUN_ID_RE = re.compile(r"^[0-9a-f]{32}$")
FIXED_CANTILEVER_SHA256 = "aa7b763d488b454495f47ef056d32400e93798cd40e15143e28350a56c61d803"


def _node(i: int, j: int, k: int) -> int:
    return 1 + i + (NX + 1) * (j + (NY + 1) * k)


def _write_model(path: Path) -> None:
    lines = [
        "*Heading",
        "ANSA MCP cantilever static demonstration; mm, N, MPa",
        "** Fixed benchmark: 200 x 20 x 10 mm, E=210000 MPa, nu=0.3, Fz=-100 N",
        "*Node",
    ]
    for k in range(NZ + 1):
        for j in range(NY + 1):
            for i in range(NX + 1):
                lines.append(
                    f"{_node(i,j,k)}, {i*LENGTH_MM/NX:.8f}, "
                    f"{j*WIDTH_MM/NY:.8f}, {k*HEIGHT_MM/NZ:.8f}"
                )
    # Incompatible-mode bricks are suitable for bending-dominated solids;
    # the reduced-integration trial was too soft for this slender beam.
    lines.append("*Element, type=C3D8I, elset=EALL")
    eid = 0
    for k in range(NZ):
        for j in range(NY):
            for i in range(NX):
                eid += 1
                connectivity = (
                    _node(i,j,k), _node(i+1,j,k),
                    _node(i+1,j+1,k), _node(i,j+1,k),
                    _node(i,j,k+1), _node(i+1,j,k+1),
                    _node(i+1,j+1,k+1), _node(i,j+1,k+1),
                )
                lines.append(f"{eid}, " + ", ".join(str(n) for n in connectivity))
    fixed = [_node(0,j,k) for k in range(NZ+1) for j in range(NY+1)]
    tip = [_node(NX,j,k) for k in range(NZ+1) for j in range(NY+1)]
    lines.extend(["*Nset, nset=FIX", ", ".join(map(str,fixed))])
    lines.extend(["*Nset, nset=TIP", ", ".join(map(str,tip))])
    lines.extend([
        "*Material, name=STEEL", "*Elastic", f"{YOUNG_MPA:.1f}, {POISSON:.6f}",
        "*Solid Section, elset=EALL, material=STEEL", ",",
        "*Step, name=Static, nlgeom=NO", "*Static", "1.0, 1.0, 1e-5, 1.0",
        "*Boundary", "FIX, 1, 3, 0.0",
        "*Cload", f"TIP, 3, {END_FORCE_N/len(tip):.12f}",
        "*Output, field", "*Node Output", "U, RF",
        "*Element Output", "S, E", "*End Step", "",
    ])
    path.write_text("\n".join(lines), encoding="ascii")


def _run_dir(settings: Settings, run_id: str) -> Path:
    if not isinstance(run_id, str) or RUN_ID_RE.fullmatch(run_id) is None:
        raise ValueError("run_id must be the 32-character identifier returned by preparation")
    path = within(settings.workspace / "cantilever_demo" / run_id, settings.workspace)
    if not path.is_dir():
        raise FileNotFoundError("Cantilever run not found")
    return path


def _process(argv: list[str], run_dir: Path, logfile: str, timeout: int,
             env: dict[str,str] | None = None) -> dict:
    log_path = run_dir / logfile
    try:
        with log_path.open("wb") as stream:
            completed = subprocess.run(
                argv, cwd=run_dir, env=env, stdin=subprocess.DEVNULL,
                stdout=stream, stderr=subprocess.STDOUT, timeout=timeout,
                check=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        return {"exit_code": completed.returncode, "log": str(log_path)}
    except subprocess.TimeoutExpired:
        return {"exit_code": None, "timed_out": True, "log": str(log_path)}


def prepare_cantilever(settings: Settings) -> dict:
    """Create a fixed 3D deck, then import, verify, save and export with ANSA."""
    run_id = uuid.uuid4().hex
    root = within(settings.workspace / "cantilever_demo" / run_id, settings.workspace)
    root.mkdir(parents=True, exist_ok=False)
    source = root / "cantilever_source.inp"
    _write_model(source)
    launcher = environment_report(settings).get("launcher")
    if not launcher or not Path(launcher).is_file():
        return {"ok": False, "run_id": run_id, "stage": "ansa",
                "error": "ANSA launcher is unavailable", "source": str(source)}
    script = Path(__file__).with_name("ansa_batch_cantilever.py")
    env = dict(os.environ)
    env["ANSA_MCP_CANTILEVER_RUN_DIR"] = str(root)
    process = _process(
        [str(launcher), "-nogui", "-exec", "load_script:" + str(script)],
        root, "ansa_batch.log", timeout=150, env=env,
    )
    report_path = root / "ansa_stage.json"
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else {}
    exported = root / "cantilever_ansa_export.inp"
    required = ("*NODE", "*ELEMENT", "*MATERIAL", "*SOLID SECTION",
                "*BOUNDARY", "*CLOAD", "*STATIC")
    deck_text = exported.read_text(encoding="utf-8",errors="replace").upper() if exported.is_file() else ""
    missing = [keyword for keyword in required if keyword not in deck_text]
    ok = process.get("exit_code") == 0 and bool(report.get("ok")) and exported.is_file() and not missing
    return {
        "ok": ok, "run_id": run_id, "stage": "ansa", "run_directory": str(root),
        "source_deck": str(source), "ansa_report": report,
        "missing_exported_keywords": missing, "process": process,
        "analytical_tip_deflection_mm": abs(END_FORCE_N) * LENGTH_MM**3 /
            (3 * YOUNG_MPA * (WIDTH_MM * HEIGHT_MM**3 / 12)),
        "analytical_nominal_root_stress_mpa": abs(END_FORCE_N) * LENGTH_MM *
            (HEIGHT_MM/2) / (WIDTH_MM * HEIGHT_MM**3 / 12),
    }


def stage_visible_cantilever(settings: Settings, live) -> dict:
    """Stage a fixed input only after a live bridge advertises this workflow."""
    capabilities = live.call("get_capabilities")
    if "import_fixed_cantilever" not in capabilities.get("methods", []):
        raise RuntimeError("The loaded ANSA bridge does not support visible cantilever import")
    workspace = settings.workspace.resolve()
    if not any(
        workspace == Path(root).resolve() or Path(root).resolve() in workspace.parents
        for root in capabilities.get("save_roots", [])
    ):
        raise RuntimeError("MCP workspace is outside the live bridge allowed roots")
    run_id = uuid.uuid4().hex
    root = within(workspace / "cantilever_demo" / run_id, workspace)
    root.mkdir(parents=True, exist_ok=False)
    source = root / "cantilever_source.inp"
    _write_model(source)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if digest != FIXED_CANTILEVER_SHA256:
        raise RuntimeError("Fixed cantilever deck hash changed; bridge contract needs review")
    return {
        "ok": True,
        "stage": "source_staged",
        "run_id": run_id,
        "run_directory": str(root),
        "source_deck": str(source),
        "source_sha256": digest,
        "next": "Import into a new empty ANSA GUI database using the returned run_id",
    }


def import_visible_cantilever(
    settings: Settings, live, run_id: str, expected_database: str,
    expected_session_nonce: str, operation_id: str,
) -> dict:
    root = _run_dir(settings, run_id)
    source = root / "cantilever_source.inp"
    if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != FIXED_CANTILEVER_SHA256:
        raise RuntimeError("Fixed source deck is absent or has changed")
    result = live.call_persistent_write(
        "import_fixed_cantilever",
        {
            "source_path": str(source),
            "expected_database": expected_database,
            "expected_session_nonce": expected_session_nonce,
            "operation_id": operation_id,
            "confirm": True,
        },
        operation_id=operation_id,
    )
    if result.get("imported") and result.get("run_id") == run_id:
        (root / "live_import.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return {"ok": bool(result.get("imported")), "stage": "live_import", **result}


def export_visible_cantilever(
    settings: Settings, live, run_id: str, expected_database: str,
    expected_session_nonce: str, operation_id: str,
) -> dict:
    root = _run_dir(settings, run_id)
    imported = root / "live_import.json"
    if not imported.is_file() or not json.loads(imported.read_text(encoding="utf-8")).get("imported"):
        raise RuntimeError("The fixed model has not been verified as imported in the live ANSA session")
    result = live.call_persistent_write(
        "export_fixed_cantilever",
        {
            "source_path": str(root / "cantilever_source.inp"),
            "expected_database": expected_database,
            "expected_session_nonce": expected_session_nonce,
            "operation_id": operation_id,
            "confirm": True,
        },
        operation_id=operation_id,
    )
    exported = root / "cantilever_ansa_export.inp"
    snapshot = root / "cantilever.ansa"
    required = ("*NODE", "*ELEMENT", "*MATERIAL", "*SOLID SECTION", "*BOUNDARY", "*CLOAD", "*STATIC")
    deck_text = exported.read_text(encoding="utf-8", errors="replace").upper() if exported.is_file() else ""
    missing = [keyword for keyword in required if keyword not in deck_text]
    ok = bool(result.get("exported")) and snapshot.is_file() and exported.is_file() and not missing
    stage = {
        "stage": "ansa",
        "mode": "visible_gui",
        "ok": ok,
        "run_id": run_id,
        "node_count": 615,
        "element_count": 320,
        "material_count": 1,
        "database": str(snapshot),
        "exported_deck": str(exported),
        "exported_bytes": exported.stat().st_size if exported.is_file() else 0,
        "missing_exported_keywords": missing,
        "bridge_result": result,
    }
    (root / "ansa_stage.json").write_text(
        json.dumps(stage, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return stage


def solve_visible_cantilever(settings: Settings, live, run_id: str) -> dict:
    root = _run_dir(settings, run_id)
    stage_path = root / "ansa_stage.json"
    if not stage_path.is_file() or not json.loads(stage_path.read_text(encoding="utf-8")).get("ok"):
        raise RuntimeError("Live ANSA export has not passed validation")
    if (root / "cantilever.sta").exists() or (root / "cantilever.odb").exists():
        raise RuntimeError("This run has already been submitted")
    live.call("set_fixed_cantilever_phase", {"run_id": run_id, "phase": "solving"})
    try:
        result = solve_cantilever(settings, run_id)
    except Exception:
        try:
            live.call("set_fixed_cantilever_phase", {"run_id": run_id, "phase": "solver_failed"})
        except Exception:
            pass
        raise
    phase = "solved" if result.get("ok") else "solver_failed"
    try:
        result["gui_progress"] = live.call(
            "set_fixed_cantilever_phase", {"run_id": run_id, "phase": phase}
        )
    except Exception as exc:
        result["gui_progress_error"] = f"{type(exc).__name__}: {exc}"
    return result


def inspect_visible_cantilever(settings: Settings, live, run_id: str) -> dict:
    result = inspect_cantilever(settings, run_id)
    if result.get("ok"):
        try:
            result["gui_progress"] = live.call(
                "set_fixed_cantilever_phase", {"run_id": run_id, "phase": "verified"}
            )
        except Exception as exc:
            result["gui_progress_error"] = f"{type(exc).__name__}: {exc}"
    return result


def solve_cantilever(settings: Settings, run_id: str) -> dict:
    """Solve only the ANSA-exported deck, never the pre-import source deck."""
    root = _run_dir(settings, run_id)
    report_path = root / "ansa_stage.json"
    if not report_path.is_file() or not json.loads(report_path.read_text(encoding="utf-8")).get("ok"):
        raise RuntimeError("ANSA import/export validation has not succeeded")
    deck = root / "cantilever_ansa_export.inp"
    if not deck.is_file():
        raise RuntimeError("ANSA-exported deck is missing")
    if (root / "cantilever.sta").exists() or (root / "cantilever.odb").exists():
        raise RuntimeError("This run has already been submitted; inspect its existing solver evidence")
    solver = shutil.which("abaqus.bat") or shutil.which("abaqus")
    if not solver:
        return {"ok": False, "stage": "solver", "run_id": run_id,
                "error": "Abaqus command is unavailable"}
    process = _process(
        [solver, "job=cantilever", "input=" + str(deck), "cpus=2", "interactive"],
        root, "abaqus_console.log", timeout=160,
    )
    sta = root / "cantilever.sta"
    status = sta.read_text(encoding="utf-8",errors="replace") if sta.is_file() else ""
    odb = root / "cantilever.odb"
    ok = (process.get("exit_code") == 0 and
          "THE ANALYSIS HAS COMPLETED SUCCESSFULLY" in status and odb.is_file())
    return {"ok": ok, "stage": "solver", "run_id": run_id,
            "process": process, "status_file": str(sta), "odb": str(odb),
            "success_marker": "THE ANALYSIS HAS COMPLETED SUCCESSFULLY" in status,
            "odb_exists": odb.is_file()}


def inspect_cantilever(settings: Settings, run_id: str) -> dict:
    root = _run_dir(settings, run_id)
    sta = root / "cantilever.sta"
    if not sta.is_file() or "THE ANALYSIS HAS COMPLETED SUCCESSFULLY" not in sta.read_text(encoding="utf-8",errors="replace"):
        raise RuntimeError("Abaqus success marker is unavailable")
    solver = shutil.which("abaqus.bat") or shutil.which("abaqus")
    if not solver:
        raise RuntimeError("Abaqus command is unavailable")
    script = Path(__file__).with_name("abaqus_extract_cantilever.py")
    process = _process([solver, "python", str(script), str(root)], root,
                       "abaqus_extract.log", timeout=90)
    path = root / "results.json"
    result = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    analytical = (
        abs(END_FORCE_N) * LENGTH_MM**3
        / (3 * YOUNG_MPA * (WIDTH_MM * HEIGHT_MM**3 / 12))
    )
    reaction = result.get("fixed_reaction_z_n")
    tip = result.get("tip_u3_average_mm")
    balance_error = abs(reaction - abs(END_FORCE_N)) / abs(END_FORCE_N) if isinstance(reaction,(float,int)) else None
    ratio = abs(tip) / analytical if isinstance(tip,(float,int)) else None
    displacement_sanity_pass = ratio is not None and 0.9 <= ratio <= 1.1
    summary = {"ok": process.get("exit_code") == 0 and bool(result.get("ok")) and
            balance_error is not None and balance_error < 0.01 and displacement_sanity_pass,
            "stage": "postprocess", "run_id": run_id, "run_directory": str(root),
            "process": process, "results": result,
            "analytical_tip_deflection_mm": analytical,
            "tip_deflection_to_beam_theory_ratio": ratio,
            "displacement_sanity_pass": displacement_sanity_pass,
            "reaction_balance_relative_error": balance_error,
            "note": "The solid-element peak Mises stress is not expected to equal nominal beam stress exactly."}
    (root / "verification.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary
