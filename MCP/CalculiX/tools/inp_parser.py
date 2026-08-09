# -*- coding: utf-8 -*-
"""inp_parser.py - Abaqus/CalculiX ``.inp`` card parsing + text in-place editing.

Core constraints:

* **meshio only reads the mesh** (nodes/elements/NSET/ELSET) and silently skips
  every card — so ``*SHELL SECTION`` / ``*BEAM SECTION`` / ``*MATERIAL`` /
  ``*CLOAD`` / ``*DLOAD`` must be parsed from the raw ``.inp`` text directly.
* **Never use ``meshio.write``** — it drops all cards and rewrites ``B31`` to
  ``B31H`` (reverse-map collision, file corruption). ``modify_card`` does
  pure-text in-place replacement, no meshio round-trip.
* **Unknown cards degrade gracefully** and are collected into
  ``unsupported_cards`` rather than raising.

Public API (used by mcp_server.py):

* :func:`parse_model`      — read an ``.inp``, return a model overview
* :func:`list_design_vars` — extract tunable design variables (each with a modify locator)
* :func:`modify_card`      — text in-place edit of a card field, writing a new ``.inp``

Unit system: results keep the .inp's working units (e.g. mm-t-s-MPa). This module
attaches no units; the ``unit`` field on each design variable informs the caller.
"""
from __future__ import annotations

import contextlib
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("calculix_mcp.inp_parser")


@contextlib.contextmanager
def _suppress_stdio():
    """Temporarily redirect ``sys.stdout`` / ``sys.stderr`` to devnull at the Python object level.

    On an unknown element type meshio's ``_helpers._read_file`` emits noise via
    ``print(e)`` (-> ``sys.stdout``) and ``_common.error()`` (-> a rich
    ``Console(stderr=True)`` -> ``sys.stderr``) before calling ``sys.exit(1)``.
    We already degrade gracefully with a text fallback, so this noise is
    meaningless and misleading to the caller and is suppressed here.

    A Python object-level swap is used rather than a ``dup2`` fd redirect: all of
    meshio's output goes through the Python-layer ``sys.stdout``/``sys.stderr``,
    the swap never touches real fd 1/2 and never flushes globally, so it cannot
    swallow the caller's own unflushed stdio buffer. A successful ``meshio.read``
    produces no stdio output, so suppressing it is safe; the failure reason is
    still recorded in the ``meshio_error`` field.
    """
    devnull_out = open(os.devnull, "w")
    devnull_err = open(os.devnull, "w")
    saved_out, saved_err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = devnull_out, devnull_err
    try:
        yield
    finally:
        sys.stdout, sys.stderr = saved_out, saved_err
        devnull_out.close()
        devnull_err.close()


@dataclass
class Card:
    """A single ``*KEYWORD`` card.

    Attributes:
        keyword:    upper-case keyword, e.g. ``"SHELL SECTION"`` / ``"ELASTIC"``.
        params:     keyword-line parameters, e.g. ``{"ELSET": "UPPER", "MATERIAL": "STEEL"}``;
                    flag parameters without a value map to ``None``.
        data_lines: raw data lines (rstripped; blank/comment lines skipped).
        header_line_no: 0-based line number of the keyword line in the source file (diagnostics).
        data_line_nos:  0-based line numbers of each data line.
    """

    keyword: str
    params: dict[str, str | None]
    data_lines: list[str]
    header_line_no: int = -1
    data_line_nos: list[int] = field(default_factory=list)


_PARAM_KV = re.compile(r"^\s*\*([A-Za-z0-9 _]+)\b")


def _parse_keyword_line(line: str) -> tuple[str, dict[str, str | None]]:
    """Parse a ``*KEYWORD, ELSET=UPPER, MATERIAL=STEEL, GENERATE`` header line.

    Returns:
        (keyword_upper, params_dict)
    """
    body = line.lstrip()
    body = body[1:]
    parts = [p.strip() for p in body.split(",")]
    keyword = parts[0].upper()
    params: dict[str, str | None] = {}
    for p in parts[1:]:
        if not p:
            continue
        if "=" in p:
            k, v = p.split("=", 1)
            params[k.strip().upper()] = v.strip()
        else:
            params[p.upper()] = None
    return keyword, params


def scan_cards(lines: list[str]) -> list[Card]:
    """Scan a full ``.inp`` and fold each ``*KEYWORD`` into a :class:`Card`.

    Comment lines (``**``) and blank lines are skipped; a card's data lines run
    up to the next ``*`` keyword (``**`` comments do not terminate it). Unknown
    keywords are still collected as Cards (the caller decides whether to file
    them under ``unsupported_cards``), keeping parsing graceful.
    """
    cards: list[Card] = []
    i = 0
    n = len(lines)
    while i < n:
        ln = lines[i]
        s = ln.strip()
        if not s or s.startswith("**"):
            i += 1
            continue
        if s.startswith("*"):
            keyword, params = _parse_keyword_line(s)
            header_no = i
            data_lines: list[str] = []
            data_nos: list[int] = []
            i += 1
            while i < n:
                ds = lines[i].strip()
                if not ds or ds.startswith("**"):
                    i += 1
                    continue
                if ds.startswith("*"):
                    break
                data_lines.append(ds)
                data_nos.append(i)
                i += 1
            cards.append(
                Card(
                    keyword=keyword,
                    params=params,
                    data_lines=data_lines,
                    header_line_no=header_no,
                    data_line_nos=data_nos,
                )
            )
        else:
            i += 1
    return cards


def _meshio_overview(path: str, lines: list[str]) -> dict:
    """Read mesh statistics: node count + per-element-type counts (preserving the
    **original Abaqus TYPE names**).

    Design notes:
      * meshio normalizes ``S4`` to ``quad`` and ``B31`` to ``line``, and its
        reverse map has a collision bug, so ``elements_by_type`` is taken from
        the text-scanned original TYPE names (S4/B31/C3D8); meshio only fills in
        the bbox and the NSET/ELSET names.
      * On an unknown element TYPE meshio calls ``sys.exit(1)`` (a SystemExit,
        i.e. a BaseException, not a plain Exception), so the meshio block must
        catch BaseException and degrade to the text counts rather than crash.
    """
    n_nodes = 0
    elements_by_type: dict[str, int] = {}
    for card in scan_cards(lines):
        if card.keyword == "NODE":
            n_nodes = max(n_nodes, len(card.data_lines))
        elif card.keyword == "ELEMENT":
            etype = (card.params.get("TYPE") or "UNKNOWN").upper()
            elements_by_type[etype] = elements_by_type.get(etype, 0) + len(
                card.data_lines
            )

    overview: dict[str, Any] = {
        "n_nodes": n_nodes,
        "elements_by_type": dict(elements_by_type),
        "elset_names": [],
        "nset_names": [],
        "bbox": None,
        "meshio_used": False,
        "meshio_error": None,
    }

    try:
        import meshio
    except Exception as e:  # pragma: no cover
        overview["meshio_error"] = f"meshio import failed: {e}"
        return overview

    try:
        with _suppress_stdio():
            mesh = meshio.read(path, file_format="abaqus")
        overview["meshio_used"] = True
        overview["n_nodes"] = int(len(mesh.points))
        overview["nset_names"] = sorted(mesh.point_sets.keys())
        overview["elset_names"] = sorted(mesh.cell_sets.keys())
        overview["bbox"] = [
            [float(v) for v in mesh.points.min(axis=0)],
            [float(v) for v in mesh.points.max(axis=0)],
        ]
    except BaseException as e:
        overview["meshio_error"] = f"{type(e).__name__}: {e}"
        logger.warning("meshio.read failed, using text counts only: %s", e)

    return overview


def _to_float(s: str) -> float | None:
    """Best-effort str→float; return None on parse failure."""
    s = s.strip().rstrip(",")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def extract_shell_sections(cards: list[Card]) -> list[dict]:
    """Extract ``*SHELL SECTION`` cards -> thickness T + ELSET + MATERIAL.

    Abaqus/CalculiX convention: the thickness is the **first value on the first
    data line** of the card. OFFSET/MATERIAL etc. live as keyword-line
    parameters and are left untouched.
    """
    out: list[dict] = []
    for c in cards:
        if c.keyword != "SHELL SECTION":
            continue
        thickness = c.data_lines[0].split(",")[0] if c.data_lines else ""
        out.append(
            {
                "elset": c.params.get("ELSET", ""),
                "material": c.params.get("MATERIAL", ""),
                "thickness": _to_float(thickness),
                "header_line_no": c.header_line_no,
                "data_line_no": c.data_line_nos[0] if c.data_line_nos else -1,
            }
        )
    return out


def extract_beam_sections(cards: list[Card]) -> list[dict]:
    """Extract ``*BEAM SECTION`` cards -> section type SECTION= and parameters.

    The library section ``SECTION=I`` is preferred (``*BEAM GENERAL SECTION``
    has bugs in some ccx releases). Other SECTION types are read with their raw
    values too, but list_design_vars only exposes h/b/t1/t2 for SECTION=I.
    Data line 1: ``h, b, t1, t2`` (the four Abaqus/CalculiX parameters, in order).
    """
    out: list[dict] = []
    for c in cards:
        if c.keyword != "BEAM SECTION":
            continue
        section = (c.params.get("SECTION") or "").upper()
        vals: list[float | None] = []
        if c.data_lines:
            vals = [_to_float(x) for x in c.data_lines[0].split(",")][:4]
        out.append(
            {
                "elset": c.params.get("ELSET", ""),
                "material": c.params.get("MATERIAL", ""),
                "section": section,
                "params": vals,
                "header_line_no": c.header_line_no,
                "data_line_no": c.data_line_nos[0] if c.data_line_nos else -1,
            }
        )
    return out


def extract_materials(cards: list[Card]) -> dict[str, dict]:
    """Extract materials: attach ``*ELASTIC`` / ``*DENSITY`` / ``*PLASTIC`` to their ``*MATERIAL``.

    Abaqus semantics: ``*MATERIAL, NAME=X`` is followed by sub-cards
    (``*ELASTIC``/``*DENSITY``/``*PLASTIC``) that carry no NAME parameter and
    belong to the most recent ``*MATERIAL`` by **position**. This function walks
    the cards in order, tracking the "current material" context.
    """
    materials: dict[str, dict] = {}
    current = None
    for c in cards:
        if c.keyword == "MATERIAL":
            name = c.params.get("NAME", "")
            current = name
            materials.setdefault(name, {"name": name, "elastic": None, "density": None})
        elif c.keyword == "ELASTIC" and current is not None:
            mat = materials.setdefault(
                current, {"name": current, "elastic": None, "density": None}
            )
            if c.data_lines:
                p = [x.strip() for x in c.data_lines[0].split(",")]
                mat["elastic"] = {
                    "E": _to_float(p[0]) if len(p) > 0 else None,
                    "nu": _to_float(p[1]) if len(p) > 1 else None,
                    "header_line_no": c.header_line_no,
                    "data_line_no": c.data_line_nos[0] if c.data_line_nos else -1,
                }
        elif c.keyword == "DENSITY" and current is not None:
            mat = materials.setdefault(
                current, {"name": current, "elastic": None, "density": None}
            )
            if c.data_lines:
                rho = _to_float(c.data_lines[0].split(",")[0])
                mat["density"] = {
                    "rho": rho,
                    "header_line_no": c.header_line_no,
                    "data_line_no": c.data_line_nos[0] if c.data_line_nos else -1,
                }
    return materials


def extract_loads(cards: list[Card]) -> list[dict]:
    """Extract ``*CLOAD`` / ``*DLOAD`` loads.

    ``*CLOAD`` data line: ``<node|nset>, <DOF>, <magnitude>``.
    ``*DLOAD`` data line: ``<elset|element>, <TYPE>, <magnitude>``.
    Each line becomes one load entry (its index is used as a var_id suffix in
    list_design_vars).
    """
    loads: list[dict] = []
    for c in cards:
        if c.keyword == "CLOAD":
            for dl in c.data_lines:
                p = [x.strip() for x in dl.split(",")]
                if len(p) >= 3:
                    loads.append(
                        {
                            "type": "CLOAD",
                            "target": p[0],
                            "dof": _to_float(p[1]),
                            "magnitude": _to_float(p[2]),
                            "header_line_no": c.header_line_no,
                        }
                    )
        elif c.keyword == "DLOAD":
            for dl in c.data_lines:
                p = [x.strip() for x in dl.split(",")]
                if len(p) >= 3:
                    loads.append(
                        {
                            "type": "DLOAD",
                            "target": p[0],
                            "load_type": p[1],
                            "magnitude": _to_float(p[2]),
                            "header_line_no": c.header_line_no,
                        }
                    )
    return loads


_KNOWN_CARDS = {
    "NODE", "ELEMENT", "NSET", "ELSET", "HEADING",
    "SHELL SECTION", "BEAM SECTION",
    "MATERIAL", "ELASTIC", "DENSITY", "PLASTIC",
    "CLOAD", "DLOAD", "DSLOAD", "BOUNDARY",
    "STEP", "STATIC", "STATIC GENERAL", "END STEP",
    "NODE PRINT", "EL PRINT", "NODE FILE", "EL FILE",
    "ORIENTATION", "SOLID SECTION", "INCLUDE",
    "PART", "END PART", "ASSEMBLY", "END ASSEMBLY", "INSTANCE", "END INSTANCE",
    "SURFACE", "TIE",
}


def parse_model(inp_path: str) -> dict:
    """Read an ``.inp`` and return a model overview (used by the ``parse_inp`` MCP tool).

    Returns:
        A dict with keys including ``nodes`` / ``elements_by_type`` /
        ``shell_sections`` / ``beam_sections`` / ``materials`` / ``loads`` /
        ``unsupported_cards``.
    """
    with open(inp_path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    cards = scan_cards(lines)
    ov = _meshio_overview(inp_path, lines)

    shell_secs = extract_shell_sections(cards)
    beam_secs = extract_beam_sections(cards)
    materials = extract_materials(cards)
    loads = extract_loads(cards)

    unsupported: list[str] = []
    seen = set()
    for c in cards:
        if c.keyword not in _KNOWN_CARDS and c.keyword not in seen:
            unsupported.append(c.keyword)
            seen.add(c.keyword)

    return {
        "inp_path": inp_path,
        "nodes": ov["n_nodes"],
        "elements_by_type": ov["elements_by_type"],
        "elset_names": ov["elset_names"],
        "nset_names": ov["nset_names"],
        "bbox": ov["bbox"],
        "shell_sections": shell_secs,
        "beam_sections": beam_secs,
        "materials": materials,
        "loads": loads,
        "unsupported_cards": unsupported,
        "meshio_used": ov["meshio_used"],
        "meshio_error": ov["meshio_error"],
    }


def list_design_vars(inp_path: str) -> dict:
    """Extract tunable design variables, each carrying a ``modify`` locator for :func:`modify_card`.

    Covers four families (PRD variable family C):
      * shell thickness (``*SHELL SECTION``)
      * beam section (h/b/t1/t2 of ``*BEAM SECTION, SECTION=I``)
      * material properties (E / nu / density)
      * load magnitudes (``*CLOAD`` / ``*DLOAD``)

    Returns:
        ``{"variables": [ {..., "modify": {...}} ], "count": N}``
    """
    model = parse_model(inp_path)
    variables: list[dict] = []

    for s in model["shell_sections"]:
        if s.get("thickness") is None:
            continue
        variables.append(
            {
                "var_id": f"shell.{s['elset']}.thickness",
                "card_type": "SHELL SECTION",
                "elset": s["elset"],
                "field": "thickness",
                "current_value": s["thickness"],
                "unit": "mm",
                "modify": {
                    "card_type": "SHELL SECTION",
                    "match": {"ELSET": s["elset"]},
                    "data_line": 0,
                    "value_pos": 0,
                },
            }
        )

    beam_fields = [
        ("h", 0, "mm"),
        ("b", 1, "mm"),
        ("t1", 2, "mm"),
        ("t2", 3, "mm"),
    ]
    for b in model["beam_sections"]:
        if b.get("section") != "I":
            continue
        params = b.get("params") or []
        for fname, pos, unit in beam_fields:
            if pos < len(params) and params[pos] is not None:
                variables.append(
                    {
                        "var_id": f"beam.{b['elset']}.{fname}",
                        "card_type": "BEAM SECTION",
                        "elset": b["elset"],
                        "field": fname,
                        "current_value": params[pos],
                        "unit": unit,
                        "modify": {
                            "card_type": "BEAM SECTION",
                            "match": {"ELSET": b["elset"]},
                            "data_line": 0,
                            "value_pos": pos,
                        },
                    }
                )

    for name, mat in model["materials"].items():
        el = mat.get("elastic")
        if el and el.get("E") is not None:
            variables.append(
                {
                    "var_id": f"material.{name}.E",
                    "card_type": "ELASTIC",
                    "material": name,
                    "field": "E",
                    "current_value": el["E"],
                    "unit": "MPa",
                    "modify": {
                        "card_type": "ELASTIC",
                        "match": {"_material": name},
                        "data_line": 0,
                        "value_pos": 0,
                    },
                }
            )
        if el and el.get("nu") is not None:
            variables.append(
                {
                    "var_id": f"material.{name}.nu",
                    "card_type": "ELASTIC",
                    "material": name,
                    "field": "nu",
                    "current_value": el["nu"],
                    "unit": "-",
                    "modify": {
                        "card_type": "ELASTIC",
                        "match": {"_material": name},
                        "data_line": 0,
                        "value_pos": 1,
                    },
                }
            )
        den = mat.get("density")
        if den and den.get("rho") is not None:
            variables.append(
                {
                    "var_id": f"material.{name}.density",
                    "card_type": "DENSITY",
                    "material": name,
                    "field": "density",
                    "current_value": den["rho"],
                    "unit": "t/mm^3",
                    "modify": {
                        "card_type": "DENSITY",
                        "match": {"_material": name},
                        "data_line": 0,
                        "value_pos": 0,
                    },
                }
            )

    load_idx_by_type: dict[str, int] = {}
    for ld in model["loads"]:
        if ld.get("magnitude") is None:
            continue
        ltype = ld["type"]
        idx = load_idx_by_type.get(ltype, 0)
        load_idx_by_type[ltype] = idx + 1
        unit = "N" if ltype == "CLOAD" else "MPa"
        variables.append(
            {
                "var_id": f"{ltype.lower()}.{idx}.magnitude",
                "card_type": ltype,
                "field": "magnitude",
                "current_value": ld["magnitude"],
                "unit": unit,
                "modify": {
                    "card_type": ltype,
                    "match": {"_index": idx},
                    "data_line": -1,
                    "value_pos": 2,
                },
            }
        )

    return {"variables": variables, "count": len(variables)}


def _fmt_value(v: float) -> str:
    """Format a number in compact notation with 6 significant digits."""
    return f"{float(v):.6g}"


def _set_field_on_line(line: str, value_pos: int, new_value: float) -> str:
    """In-place replace the ``value_pos``-th value of a comma-separated data line.

    Leading indent and any trailing comma are preserved; untouched fields keep
    their original text (decimal point included) to minimize the diff.
    """
    nl = "\n" if line.endswith("\n") else ""
    body = line.rstrip("\n")
    indent_len = len(body) - len(body.lstrip())
    indent = body[:indent_len]
    content = body[indent_len:]
    raw_parts = content.split(",")
    parts = [p.strip() for p in raw_parts]
    if value_pos < 0 or value_pos >= len(parts):
        raise ValueError(
            f"value_pos={value_pos} out of range (line has {len(parts)} fields): {line!r}"
        )
    parts[value_pos] = _fmt_value(new_value)
    trailing = bool(raw_parts and raw_parts[-1].strip() == "")
    if trailing:
        body_parts = parts[:-1] if parts and parts[-1] == "" else parts
        return f"{indent}{', '.join(body_parts)},{nl}"
    return f"{indent}{', '.join(parts)}{nl}"


def _header_matches(header_line: str, card_type: str, match: dict) -> str | None:
    """Check whether a line is the target card header.

    Returns:
        A normalized context key on a hit (used for ELASTIC/DENSITY material
        ownership), otherwise ``None``.
    """
    s = header_line.strip()
    if not s.startswith("*") or s.startswith("**"):
        return None
    try:
        kw, params = _parse_keyword_line(s)
    except Exception:
        return None
    if kw != card_type:
        return None
    if "_material" in match or "_index" in match:
        return "ctx"
    for k, v in match.items():
        if k.startswith("_"):
            continue
        if params.get(k.upper()) != v:
            return None
    return kw


def _locate_card(
    lines: list[str], card_spec: dict
) -> tuple[int, int]:
    """Locate the header line and target data line of a card in the file.

    Three match modes are supported:
      * plain parameters (ELSET/MATERIAL etc.) — match on the header parameters
      * ``_material`` — the first such card after ``*MATERIAL, NAME=X``
      * ``_index`` — the Nth data line of this card type (used for loads)

    For ``_index`` the data lines of **all** cards of this card_type are
    flattened into one list and indexed into (not just the first card). This is
    a cross-layer contract with list_design_vars, which numbers loads per
    card_type; a global cross-type index would misalign CLOAD/DLOAD and overflow
    here.

    Returns:
        (data_line_no_0based, value_pos)
    """
    card_type = card_spec["card_type"]
    match = card_spec.get("match", {})
    data_line_idx = int(card_spec.get("data_line", 0))
    value_pos = int(card_spec["value_pos"])

    n = len(lines)
    if "_material" in match:
        mat_name = match["_material"]
        mat_line = -1
        for i, ln in enumerate(lines):
            s = ln.strip()
            if s.startswith("*") and not s.startswith("**"):
                try:
                    kw, params = _parse_keyword_line(s)
                except Exception:
                    continue
                if kw == "MATERIAL" and params.get("NAME", "").upper() == mat_name.upper():
                    mat_line = i
                    break
        if mat_line < 0:
            raise ValueError(f"*MATERIAL, NAME={mat_name} not found")
        for j in range(mat_line + 1, n):
            s = lines[j].strip()
            if s.startswith("**") or not s:
                continue
            if s.startswith("*"):
                try:
                    kw, _ = _parse_keyword_line(s)
                except Exception:
                    kw = ""
                if kw == "MATERIAL":
                    break
                if kw == card_type:
                    data_nos = _collect_data_line_nos(lines, j)
                    if data_line_idx < len(data_nos):
                        return data_nos[data_line_idx], value_pos
                    raise ValueError(
                        f"{card_type} under {mat_name} has no data_line {data_line_idx}"
                    )
        raise ValueError(f"*{card_type} under material {mat_name} not found")

    if "_index" in match:
        idx = int(match["_index"])
        all_data_nos: list[int] = []
        for i, ln in enumerate(lines):
            s = ln.strip()
            if s.startswith("*") and not s.startswith("**"):
                try:
                    kw, _ = _parse_keyword_line(s)
                except Exception:
                    continue
                if kw == card_type:
                    all_data_nos.extend(_collect_data_line_nos(lines, i))
        if idx < len(all_data_nos):
            return all_data_nos[idx], value_pos
        raise ValueError(
            f"{card_type} has no load index {idx} (found {len(all_data_nos)})"
        )

    for i, ln in enumerate(lines):
        if _header_matches(ln, card_type, match):
            data_nos = _collect_data_line_nos(lines, i)
            if 0 <= data_line_idx < len(data_nos):
                return data_nos[data_line_idx], value_pos
            raise ValueError(
                f"*{card_type} {match} has no data_line {data_line_idx}"
            )
    raise ValueError(f"*{card_type} with match {match} not found")


def _collect_data_line_nos(lines: list[str], header_idx: int) -> list[int]:
    """Collect data line numbers after a header (until the next keyword, skipping comments/blank lines)."""
    out: list[int] = []
    i = header_idx + 1
    n = len(lines)
    while i < n:
        s = lines[i].strip()
        if not s or s.startswith("**"):
            i += 1
            continue
        if s.startswith("*"):
            break
        out.append(i)
        i += 1
    return out


def modify_card(
    inp_path: str,
    card_spec: dict | str,
    new_value: float,
    out_path: str | None = None,
) -> dict:
    """Do a **pure-text in-place** edit of one field on an ``.inp`` card and write a new ``.inp``.

    Strategy: read all lines -> use the locator to find the target data line ->
    change the ``value_pos``-th comma field -> write every other line back
    unchanged. There is **no meshio round-trip**: meshio.write drops cards and
    corrupts element types (e.g. B31 -> B31H).

    Args:
        inp_path:  path to the source ``.inp``.
        card_spec: the locator. Either:
            * str — a ``var_id`` returned by ``list_design_vars`` (the locator is
              re-resolved automatically);
            * dict — ``{"card_type", "match", "data_line", "value_pos"}``, i.e.
              a design variable's ``modify`` field.
        new_value: the new numeric value.
        out_path:  output path; None writes back to the original (``inp_path``).

    Returns:
        ``{"out_path", "changed", "card_type", "field_or_pos", "old_value",
        "new_value"}``.
    """
    with open(inp_path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    if isinstance(card_spec, str):
        dvars = list_design_vars(inp_path)["variables"]
        hit = [v for v in dvars if v["var_id"] == card_spec]
        if not hit:
            raise ValueError(f"var_id {card_spec!r} not found in {inp_path}")
        spec = hit[0]["modify"]
        field_name = hit[0]["field"]
    else:
        spec = card_spec
        field_name = card_spec.get(
            "field", f"line{card_spec.get('data_line', 0)}.pos{card_spec.get('value_pos', 0)}"
        )

    data_line_no, value_pos = _locate_card(lines, spec)
    old_line = lines[data_line_no]
    old_val = _to_float(old_line.split(",")[value_pos])
    lines[data_line_no] = _set_field_on_line(old_line, value_pos, new_value)

    target = out_path or inp_path
    with open(target, "w", encoding="utf-8") as f:
        f.writelines(lines)

    return {
        "out_path": target,
        "changed": True,
        "card_type": spec["card_type"],
        "field": field_name,
        "old_value": old_val,
        "new_value": float(new_value),
    }


__all__ = [
    "Card",
    "scan_cards",
    "parse_model",
    "list_design_vars",
    "modify_card",
    "extract_shell_sections",
    "extract_beam_sections",
    "extract_materials",
    "extract_loads",
]
