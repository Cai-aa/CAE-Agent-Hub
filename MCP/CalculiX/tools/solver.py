# -*- coding: utf-8 -*-
"""solver.py - CalculiX solver layer: run ccx + parse .dat text results.

Core contracts (all from public CalculiX docs / CLI observation):

* ccx exit code is UNTRUSTED — ccx returns 0 even when it prints ``*ERROR``.
  ``run_solver`` never trusts the returncode; success = (no ``*ERROR`` in stdout)
  AND (``.sta`` has >=1 data row) AND (no timeout).
* ``.dat`` has NO von Mises column — only 6 stress components
  (sxx, syy, szz, sxy, sxz, syz); sigma_vm is self-computed.
* ``.dat`` has NO total volume/mass — computed from meshio geometry of the
  sibling .inp (shell = area x thickness; solid = element volume) x *DENSITY.

Public API (used by mcp_server.py):

* :func:`run_solver`    — fire-and-forget ccx subprocess
* :func:`read_results`  — parse .dat -> {max_stress_vm, max_disp, volume, mass}
* :func:`detect_ccx`    — locate the ccx executable (fea_health reuses this)

Units: results keep the .inp's working unit system (e.g. mm-t-s-MPa ->
stress=MPa, disp=mm, volume=mm^3, mass=t). This module attaches no units.
"""
from __future__ import annotations

import logging
import math
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

logger = logging.getLogger("calculix_mcp.solver")

sys.path.insert(0, str(Path(__file__).resolve().parent))
import inp_parser  # noqa: E402


def detect_ccx() -> str:
    """Locate the CalculiX executable: ``CCX_EXE`` env > ``ccx`` > ``ccx_preCICE``.

    Returns the absolute path, or an empty string if not found.
    """
    exe = os.environ.get("CCX_EXE", "").strip()
    if exe:
        return exe
    for cand in ("ccx", "ccx_preCICE"):
        p = shutil.which(cand)
        if p:
            return p
    return ""


def run_solver(inp_path: str, timeout: int = 1800) -> dict:
    """Run CalculiX on an ``.inp`` deck; return status + output-file paths.

    Invokes ``ccx -i <jobname>`` (ccx appends the ``.inp`` suffix itself, so
    ``<jobname>`` carries no extension) with cwd set to the .inp's directory
    (ccx drops its outputs in cwd). ccx writes its diagnostics, including
    ``*ERROR``, to stdout, so stderr is merged into stdout before scanning. The
    exit code is NOT trusted (ccx returns 0 even on ``*ERROR``); success is
    judged by: no ``*ERROR`` in stdout AND the ``.sta`` file has at least one
    data row AND the run did not time out.

    Args:
        inp_path: path to the ``.inp`` (absolute is safest; outputs land in its
            parent directory).
        timeout: seconds; on timeout the child is killed and ``status="error"``.

    Returns:
        ``{status, returncode, has_error, errors, timeout, job_dir, jobname,
        dat_path, sta_path, sta_has_data, stdout_tail, elapsed}``.
    """
    return _run_ccx(inp_path, timeout)


def _run_ccx(inp_path: str, timeout: int) -> dict:
    exe = detect_ccx()
    if not exe:
        return {
            "status": "error",
            "backend": "calculix",
            "returncode": -1,
            "has_error": True,
            "errors": ["ccx executable not found (set CCX_EXE or install ccx)"],
            "timeout": False,
            "job_dir": "",
            "jobname": "",
            "dat_path": "",
            "sta_path": "",
            "sta_has_data": False,
            "stdout_tail": "",
            "elapsed": 0.0,
        }

    inp = Path(inp_path).resolve()
    if not inp.exists():
        raise FileNotFoundError(f"inp not found: {inp_path}")
    job_dir = inp.parent
    jobname = inp.stem

    cmd = [exe, "-i", jobname]
    env = dict(os.environ)
    env.setdefault("OMP_NUM_THREADS", "1")

    logger.info("run_solver ccx: %s (cwd=%s)", " ".join(cmd), job_dir)
    start = time.monotonic()
    timeout_hit = False
    stdout_text = ""
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(job_dir),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        returncode = proc.returncode
        stdout_text = (proc.stdout or "") + (proc.stderr or "")
    except subprocess.TimeoutExpired as e:
        returncode = -1
        timeout_hit = True
        out = e.stdout or ""
        if isinstance(out, bytes):
            out = out.decode("utf-8", "replace")
        err = e.stderr or ""
        if isinstance(err, bytes):
            err = err.decode("utf-8", "replace")
        stdout_text = (out or "") + (err or "")
        logger.warning("run_solver ccx timeout after %ds (job=%s)", timeout, jobname)
    elapsed = time.monotonic() - start

    errors = [ln.strip() for ln in stdout_text.splitlines() if "*ERROR" in ln.upper()]

    sta_path = job_dir / f"{jobname}.sta"
    dat_path = job_dir / f"{jobname}.dat"
    sta_has_data = _sta_has_data_row(sta_path)

    has_error = bool(errors) or (not sta_has_data) or timeout_hit
    status = "error" if has_error else "ok"

    return {
        "status": status,
        "backend": "calculix",
        "returncode": returncode,
        "has_error": has_error,
        "errors": errors,
        "timeout": timeout_hit,
        "job_dir": str(job_dir),
        "jobname": jobname,
        "dat_path": str(dat_path) if dat_path.exists() else "",
        "sta_path": str(sta_path) if sta_path.exists() else "",
        "sta_has_data": sta_has_data,
        "stdout_tail": stdout_text[-2000:],
        "elapsed": round(elapsed, 2),
    }


def _sta_has_data_row(sta_path: Path) -> bool:
    """Return True if ``.sta`` has >=1 data row after its two header lines.

    ccx ``.sta`` starts with two header lines (``SUMMARY OF JOB INFORMATION`` and
    ``STEP INC ATT ...``); a real solve is followed by a numeric row like
    ``     1          1     1     1  ...``. Header-only means the solve did not
    finish.
    """
    if not sta_path.exists():
        return False
    try:
        text = sta_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    for ln in text.splitlines():
        s = ln.strip()
        if s and s[0].isdigit():
            return True
    return False


_STRESS_HDR = re.compile(r"^\s*stresses\s*\(elem", re.IGNORECASE)
_DISP_HDR = re.compile(r"^\s*displacements\s*\(v", re.IGNORECASE)


def read_results(result_path: str) -> dict:
    """Parse a CalculiX ``.dat`` result file.

    * ``max_stress_vm`` — von Mises self-computed from the 6 components, then max
      (the .dat has no von Mises column).
    * ``max_disp`` — max displacement magnitude ``|U|``.
    * ``volume`` / ``mass`` — from meshio geometry of the sibling .inp x the
      ``*DENSITY`` value (the .dat has neither).

    Args:
        result_path: a ``.dat`` file path, or a job directory (the unique ``.dat``
            inside it is used).

    Returns:
        ``{status, max_stress_vm, max_disp, volume, mass, density,
        n_stress_points, n_disp_points, dat_path, warnings}``. Unparseable items
        are ``None`` with an explanation in ``warnings``.
    """
    return _read_ccx_dat(result_path)


def _resolve_dat_path(result_path: str) -> Path:
    """``result_path`` may be a ``.dat`` file or a job dir (dir -> the unique .dat)."""
    p = Path(result_path)
    if p.is_dir():
        dats = sorted(p.glob("*.dat"))
        if not dats:
            raise FileNotFoundError(f"no .dat under directory {result_path}")
        if len(dats) > 1:
            logger.warning("multiple .dat under %s, using %s", result_path, dats[0].name)
        return dats[0]
    return p


def _read_ccx_dat(result_path: str) -> dict:
    try:
        dat = _resolve_dat_path(result_path)
    except FileNotFoundError as e:
        return {"status": "error", "error": str(e), "dat_path": ""}

    if not dat.exists() or dat.stat().st_size == 0:
        return {
            "status": "error",
            "error": f".dat missing or empty: {dat}",
            "dat_path": str(dat),
        }

    text = dat.read_text(encoding="utf-8", errors="ignore")
    warnings: list[str] = []

    max_vm, n_stress = _parse_max_von_mises(text)
    max_disp, n_disp = _parse_max_disp(text)
    if n_stress == 0:
        warnings.append("no stress data rows parsed (check *EL PRINT ... S in .inp)")
    if n_disp == 0:
        warnings.append("no displacement data rows parsed (check *NODE PRINT NSET=... U)")

    inp_path = dat.with_suffix(".inp")
    volume, mass, density = _compute_volume_mass(inp_path, warnings)

    return {
        "status": "ok",
        "max_stress_vm": max_vm if n_stress else None,
        "max_disp": max_disp if n_disp else None,
        "volume": volume,
        "mass": mass,
        "density": density,
        "n_stress_points": n_stress,
        "n_disp_points": n_disp,
        "dat_path": str(dat),
        "warnings": warnings,
    }


def _parse_max_von_mises(text: str) -> tuple[float, int]:
    """Self-compute von Mises from the 6 stress components; return (max, count).

    Observed row format (ccx 2.20)::

        stresses (elem, integ.pnt.,sxx,syy,szz,sxy,sxz,syz) for set ALL and time ...

        1   1 -1.706905E+03 ... 9.136469E+01 _shell_0000000001

    Each row: ``<elem> <intpt> <sxx> <syy> <szz> <sxy> <sxz> <syz> [<label>]``;
    ``fields[2:8]`` are the 6 components; the trailing label is ignored.
    """
    lines = text.splitlines()
    n = len(lines)
    max_vm = 0.0
    count = 0
    i = 0
    while i < n:
        if _STRESS_HDR.search(lines[i]):
            i += 1
            while i < n:
                parts = lines[i].split()
                if not parts:
                    i += 1
                    continue
                if len(parts) < 8:
                    break
                try:
                    int(parts[0])
                    int(parts[1])
                    comps = [float(parts[k]) for k in range(2, 8)]
                except (ValueError, IndexError):
                    break
                sxx, syy, szz, sxy, sxz, syz = comps
                vm = math.sqrt(
                    0.5
                    * (
                        (sxx - syy) ** 2
                        + (syy - szz) ** 2
                        + (szz - sxx) ** 2
                        + 6 * (sxy**2 + syz**2 + sxz**2)
                    )
                )
                if vm > max_vm:
                    max_vm = vm
                count += 1
                i += 1
            continue
        i += 1
    return max_vm, count


def _parse_max_disp(text: str) -> tuple[float, int]:
    """Return (max displacement magnitude |U|, count) from the .dat displacement section.

    Observed row format (ccx 2.20)::

        displacements (vx,vy,vz) for set NALL and time ...

        23 -3.188453E-09  4.095213E-11 -2.683311E+03

    Each row: ``<node> <vx> <vy> <vz>``, ``|U| = sqrt(vx^2+vy^2+vz^2)``.
    """
    lines = text.splitlines()
    n = len(lines)
    max_u = 0.0
    count = 0
    i = 0
    while i < n:
        if _DISP_HDR.search(lines[i]):
            i += 1
            while i < n:
                parts = lines[i].split()
                if not parts:
                    i += 1
                    continue
                if len(parts) < 4:
                    break
                try:
                    int(parts[0])
                    vx, vy, vz = float(parts[1]), float(parts[2]), float(parts[3])
                except (ValueError, IndexError):
                    break
                u = math.sqrt(vx * vx + vy * vy + vz * vz)
                if u > max_u:
                    max_u = u
                count += 1
                i += 1
            continue
        i += 1
    return max_u, count


def _compute_volume_mass(
    inp_path: Path, warnings: list[str]
) -> tuple[float | None, float | None, float | None]:
    """Compute (volume, mass, density) from meshio geometry x *DENSITY.

    * shell (quad/triangle): volume = area x thickness; thickness per ELSET from
      ``*SHELL SECTION`` (meshio's ``cell_sets`` gives the ELSET -> element map).
    * solid (hexahedron/tetra): volume from node coordinates directly.
    * line (beam): not counted (needs beam cross-section A); recorded as warning.

    meshio ``sys.exit``s on unknown element TYPEs and reads 0 elements on inline
    ``**`` comments inside a data block — both degrade gracefully (volume/mass
    -> None + warning), never returning a wrong 0 mass.
    """
    if not inp_path.exists():
        warnings.append(f"no sibling .inp for volume/mass: {inp_path.name}")
        return None, None, None

    try:
        model = inp_parser.parse_model(str(inp_path))
    except Exception as e:  # pragma: no cover
        warnings.append(f"parse_model failed for volume/mass: {e}")
        return None, None, None

    density: float | None = None
    for mat in model["materials"].values():
        d = mat.get("density")
        if d and d.get("rho") is not None:
            density = d["rho"]
            break
    if density is None:
        warnings.append("no *DENSITY card found; mass cannot be computed")

    elset_thickness = {
        s["elset"]: s["thickness"]
        for s in model["shell_sections"]
        if s.get("thickness") is not None
    }

    try:
        with inp_parser._suppress_stdio():
            import meshio

            mesh = meshio.read(str(inp_path), file_format="abaqus")
    except BaseException as e:
        warnings.append(f"meshio.read failed for volume/mass: {type(e).__name__}: {e}")
        return None, None, density

    n_total_elem = sum(len(cb.data) for cb in mesh.cells)
    if n_total_elem == 0:
        warnings.append(
            "meshio read 0 elements (likely inline ** comments inside a data block "
            "or unknown TYPE); volume/mass unavailable"
        )
        return None, None, density

    try:
        import numpy as np
    except ImportError:  # pragma: no cover
        warnings.append("numpy unavailable; volume/mass cannot be computed")
        return None, None, density

    points = np.asarray(mesh.points, dtype=float)
    total_volume = 0.0
    skipped_types: list[str] = []

    for cb_idx, cb in enumerate(mesh.cells):
        ctype = cb.type
        conn = np.asarray(cb.data)
        n_elem = len(conn)

        if ctype in ("quad", "triangle"):
            areas = _shell_areas(points, conn, ctype)
            thick = np.zeros(n_elem)
            assigned = np.zeros(n_elem, dtype=bool)
            for ename, per_block in mesh.cell_sets.items():
                t = elset_thickness.get(ename)
                if t is None or cb_idx >= len(per_block):
                    continue
                idxs = np.asarray(per_block[cb_idx], dtype=int)
                if len(idxs):
                    thick[idxs] = t
                    assigned[idxs] = True
            vol = float(np.sum(areas[assigned] * thick[assigned]))
            unassigned = int(np.sum(~assigned))
            if unassigned:
                warnings.append(
                    f"{unassigned} {ctype} shell element(s) have no *SHELL SECTION "
                    f"thickness; excluded from volume/mass"
                )
            total_volume += vol

        elif ctype == "tetra":
            total_volume += float(np.sum(_tet_volumes(points, conn)))

        elif ctype == "hexahedron":
            total_volume += float(np.sum(_hex_volumes(points, conn)))

        else:
            if ctype not in skipped_types:
                skipped_types.append(ctype)

    for st in skipped_types:
        warnings.append(f"element type '{st}' not covered for volume/mass; skipped")

    mass = total_volume * density if density is not None else None
    return total_volume, mass, density


def _shell_areas(points, conn, ctype: str):
    """Shell element areas: quad via diagonal cross product, triangle via two-edge cross product."""
    import numpy as np

    if ctype == "quad":
        d1 = points[conn[:, 2]] - points[conn[:, 0]]
        d2 = points[conn[:, 3]] - points[conn[:, 1]]
        return 0.5 * np.linalg.norm(np.cross(d1, d2), axis=1)
    v1 = points[conn[:, 1]] - points[conn[:, 0]]
    v2 = points[conn[:, 2]] - points[conn[:, 0]]
    return 0.5 * np.linalg.norm(np.cross(v1, v2), axis=1)


def _tet_volumes(points, conn):
    """Tet volume = |((b-a) . ((c-a) x (d-a)))| / 6."""
    import numpy as np

    a = points[conn[:, 0]]
    b = points[conn[:, 1]]
    c = points[conn[:, 2]]
    d = points[conn[:, 3]]
    return np.abs(np.einsum("ij,ij->i", b - a, np.cross(c - a, d - a))) / 6.0


def _hex_volumes(points, conn):
    """C3D8 volume: tile into 6 tets sharing body diagonal (node0->node6), exact."""
    import numpy as np

    tets = np.array(
        [
            [0, 1, 2, 6],
            [0, 2, 3, 6],
            [0, 3, 7, 6],
            [0, 7, 4, 6],
            [0, 4, 5, 6],
            [0, 5, 1, 6],
        ]
    )
    vol = np.zeros(len(conn))
    for t in tets:
        sub = conn[:, t]
        vol += _tet_volumes(points, sub)
    return vol


__all__ = ["run_solver", "read_results", "detect_ccx"]
