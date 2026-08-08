# -*- coding: utf-8 -*-
"""result_exporter.py - build result_mesh.json (CAE-Agent-Hub viewer format).

Turns a CalculiX run into the ``result_mesh.json`` the repo's viewer loads:

    {
      "schemaVersion": 1,
      "source": "...", "instance": "...", "step": "...", "frame": 1,
      "deformationScale": <float>,
      "elementType": "S4",
      "nodes":    [{"label", "coordinates", "displacement", "deformed"}],
      "elements": [{"label", "type", "connectivity", "mises"}],
      "fieldRanges": {"misesMin", "misesMax", "maxDisplacement"}
    }

Why topology comes from the ``.inp`` and fields from the ``.dat`` (not the ``.frd``):
  * The ``.frd`` is not readable by meshio in current versions, and CalculiX expands
    shell elements (S4 -> 8-node solids) with internal relabelling, so its topology
    does not match the input deck.
  * The ``.dat`` text tables use the ORIGINAL node/element labels, which match the
    ``.inp`` exactly, so displacement (per node) and stress (per element) merge by
    label with no remap. They contain everything this viewer needs.

Viewer contract (verified against viewer/components/CaeResultViewer.js):
  * geometry is read from ``node.deformed`` (falls back to ``coordinates``);
    ``deformationScale`` is only a footer label, NOT re-applied, so ``deformed``
    must already carry the magnification: ``deformed = coordinates + displacement*scale``.
  * ``element.connectivity`` holds node LABELS (1-based, matching ``node.label``).
  * ``element.mises`` is one von Mises value per element, coloured against
    ``fieldRanges.misesMin/misesMax``.

When no ``.dat`` is available (e.g. ccx not yet run), a mesh-only file with zero
fields is emitted from the ``.inp`` — useful for wiring the viewer and for tests
that must not depend on a solver.
"""
import json
import logging
import math
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger("calculix_mcp.result_exporter")

_SCHEMA_VERSION = 1

_STRESS_HDR = re.compile(r"^\s*stresses\s*\(elem", re.IGNORECASE)
_DISP_HDR = re.compile(r"^\s*displacements\s*\(v", re.IGNORECASE)


def _to_float(s: str) -> float | None:
    s = s.strip().rstrip(",")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _read_topology_from_inp(inp_path: str):
    """Return (nodes, elements).

    nodes:    list of {"label": int, "coordinates": [x,y,z]} in file order.
    elements: list of {"label": int, "type": str, "connectivity": [labels...]}.
    """
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import inp_parser

    with open(inp_path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    cards = inp_parser.scan_cards(lines)

    nodes: list[dict] = []
    for c in cards:
        if c.keyword != "NODE":
            continue
        for dl in c.data_lines:
            p = [x.strip() for x in dl.split(",")]
            if len(p) < 4:
                continue
            label = int(p[0])
            coords = [_to_float(x) for x in p[1:4]]
            nodes.append({"label": label, "coordinates": coords})

    elements: list[dict] = []
    for c in cards:
        if c.keyword != "ELEMENT":
            continue
        etype = (c.params.get("TYPE") or "UNKNOWN").upper()
        for dl in c.data_lines:
            p = [x.strip() for x in dl.split(",")]
            if len(p) < 2:
                continue
            label = int(p[0])
            conn = [int(x) for x in p[1:] if x.strip()]
            elements.append({"label": label, "type": etype, "connectivity": conn})

    return nodes, elements


def _parse_dat_displacements(text: str) -> dict[int, list[float]]:
    """node label -> [vx, vy, vz] from the .dat displacement section."""
    lines = text.splitlines()
    n = len(lines)
    out: dict[int, list[float]] = {}
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
                    node = int(parts[0])
                    vx, vy, vz = float(parts[1]), float(parts[2]), float(parts[3])
                except (ValueError, IndexError):
                    break
                out[node] = [vx, vy, vz]
                i += 1
            continue
        i += 1
    return out


def _parse_dat_element_mises(text: str) -> dict[int, float]:
    """elem label -> max von Mises over its integration points (from the .dat stress section)."""
    lines = text.splitlines()
    n = len(lines)
    out: dict[int, float] = {}
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
                    elem = int(parts[0])
                    int(parts[1])
                    sxx, syy, szz = float(parts[2]), float(parts[3]), float(parts[4])
                    sxy, sxz, syz = float(parts[5]), float(parts[6]), float(parts[7])
                except (ValueError, IndexError):
                    break
                vm = math.sqrt(
                    0.5
                    * (
                        (sxx - syy) ** 2
                        + (syy - szz) ** 2
                        + (szz - sxx) ** 2
                        + 6.0 * (sxy**2 + syz**2 + sxz**2)
                    )
                )
                if vm > out.get(elem, 0.0):
                    out[elem] = vm
                i += 1
            continue
        i += 1
    return out


def _resolve_dat_path(inp_path: str, dat_path: str | None) -> Path | None:
    if dat_path:
        p = Path(dat_path)
        if p.is_dir():
            dats = sorted(p.glob("*.dat"))
            p = dats[0] if dats else None
        return p if p and p.exists() else None
    sibling = Path(inp_path).with_suffix(".dat")
    return sibling if sibling.exists() else None


def _auto_deformation_scale(coords, disp_by_node, target_fraction: float = 0.15) -> float:
    """Pick a scale so the max displacement is ~``target_fraction`` of the model extent."""
    if not coords:
        return 1.0
    xs = [c[0] for c in coords]
    ys = [c[1] for c in coords]
    zs = [c[2] for c in coords]
    extent = max(
        1e-9,
        max(xs) - min(xs),
        max(ys) - min(ys),
        max(zs) - min(zs),
    )
    max_u = 0.0
    for v in disp_by_node.values():
        max_u = max(max_u, math.sqrt(sum(c * c for c in v)))
    if max_u <= 0.0:
        return 1.0
    return max(1.0, min(target_fraction * extent / max_u, 1.0e6))


def export_result_mesh(
    inp_path: str,
    dat_path: str | None = None,
    out_path: str | None = None,
    deformation_scale: float | str | None = None,
    source: str | None = None,
    instance: str = "PART-1",
    step: str = "Load",
    frame: int = 1,
) -> dict:
    """Build (and by default write) a ``result_mesh.json`` for the viewer.

    Args:
        inp_path: path to the CalculiX ``.inp`` (mesh + labels + source name).
        dat_path: path to the ``.dat`` results (or the job dir); None -> look for a
            sibling ``<stem>.dat``; missing -> mesh-only with zero fields.
        out_path: where to write the JSON; None -> ``<inp stem>.result_mesh.json``
            next to the .inp (or .dat).
        deformation_scale: numeric scale baked into ``deformed``; None/"auto" ->
            auto-magnify so the deformation is visible (~15% of model size).
        source/instance/step/frame: metadata echoed into the JSON.

    Returns:
        The result_mesh dict (also written to ``out_path``).
    """
    nodes_raw, elements_raw = _read_topology_from_inp(inp_path)
    coords_by_label = {nd["label"]: nd["coordinates"] for nd in nodes_raw}

    dat = _resolve_dat_path(inp_path, dat_path)
    has_fields = dat is not None
    disp_by_node: dict[int, list[float]] = {}
    mises_by_elem: dict[int, float] = {}
    if has_fields:
        text = dat.read_text(encoding="utf-8", errors="ignore")  # type: ignore[union-attr]
        disp_by_node = _parse_dat_displacements(text)
        mises_by_elem = _parse_dat_element_mises(text)

    if deformation_scale in (None, "auto"):
        scale = _auto_deformation_scale(list(coords_by_label.values()), disp_by_node)
    else:
        scale = float(deformation_scale)

    nodes = []
    for nd in nodes_raw:
        label = nd["label"]
        c = nd["coordinates"]
        d = disp_by_node.get(label, [0.0, 0.0, 0.0])
        nodes.append(
            {
                "label": label,
                "coordinates": c,
                "displacement": d,
                "deformed": [c[i] + d[i] * scale for i in range(3)],
            }
        )

    elements = []
    type_counts: dict[str, int] = {}
    for el in elements_raw:
        mises = float(mises_by_elem.get(el["label"], 0.0))
        elements.append(
            {
                "label": el["label"],
                "type": el["type"],
                "connectivity": el["connectivity"],
                "mises": mises,
            }
        )
        type_counts[el["type"]] = type_counts.get(el["type"], 0) + 1

    nonzero_mises = [e["mises"] for e in elements if e["mises"] > 0.0]
    mises_min = min(nonzero_mises) if nonzero_mises else 0.0
    mises_max = max(nonzero_mises) if nonzero_mises else 0.0
    max_disp = max((math.sqrt(sum(c * c for c in d)) for d in disp_by_node.values()), default=0.0)

    result = {
        "schemaVersion": _SCHEMA_VERSION,
        "source": source or Path(inp_path).name,
        "instance": instance,
        "step": step,
        "frame": frame,
        "deformationScale": scale,
        "elementType": max(type_counts, key=type_counts.get) if type_counts else "",
        "nodes": nodes,
        "elements": elements,
        "fieldRanges": {
            "misesMin": mises_min,
            "misesMax": mises_max,
            "maxDisplacement": max_disp,
        },
    }

    if out_path is None:
        base_dir = dat.parent if has_fields else Path(inp_path).parent
        out_path = str(base_dir / f"{Path(inp_path).stem}.result_mesh.json")
    Path(out_path).write_text(json.dumps(result), encoding="utf-8")
    result["_out_path"] = out_path
    logger.info(
        "export_result_mesh: %d nodes / %d elements -> %s (scale=%.3g, fields=%s, misesMax=%.3g)",
        len(nodes),
        len(elements),
        out_path,
        scale,
        has_fields,
        mises_max,
    )
    return result


__all__ = ["export_result_mesh"]
