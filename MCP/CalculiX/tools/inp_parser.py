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
    """临时把 ``sys.stdout`` / ``sys.stderr`` 指到 devnull（Python 对象级）。

    meshio 读到未知单元类型时：``_helpers._read_file`` 用 ``print(e)``（→
    ``sys.stdout``）+ ``_common.error()``（→ rich ``Console(stderr=True)`` →
    ``sys.stderr``）输出噪声，再 ``sys.exit(1)``。我们已用文本兜底 graceful 降级，
    这些噪声对调用方无意义且误导，故屏蔽。

    采用 **Python 对象级 swap** 而非 ``dup2`` fd：meshio 的输出全部走 Python 层
    ``sys.stdout``/``sys.stderr``；swap 不触碰真实 fd 1/2，也**不全局 flush**，所以
    不会吞掉调用方自己尚未 flush 的 stdio 缓冲。meshio.read 成功时无 stdio 输出，
    屏蔽安全；失败原因仍记进 ``meshio_error`` 字段。
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

# ──────────────────────────────────────────────────────────────────────────
# 数据结构
# ──────────────────────────────────────────────────────────────────────────


@dataclass
class Card:
    """一个 ``*KEYWORD`` 卡片。

    Attributes:
        keyword:    大写关键字，如 ``"SHELL SECTION"`` / ``"ELASTIC"``。
        params:     关键字行参数，如 ``{"ELSET": "UPPER", "MATERIAL": "STEEL"}``。
                    无值的旗标参数值为 ``None``。
        data_lines: 数据行原文（已 rstrip，跳过空行/注释）。
        header_line_no: 关键字行在原文件中的 0-based 行号（诊断/调试用）。
        data_line_nos:  各数据行的 0-based 行号。
    """

    keyword: str
    params: dict[str, str | None]
    data_lines: list[str]
    header_line_no: int = -1
    data_line_nos: list[int] = field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────────
# 通用 .inp 扫描器
# ──────────────────────────────────────────────────────────────────────────

_PARAM_KV = re.compile(r"^\s*\*([A-Za-z0-9 _]+)\b")


def _parse_keyword_line(line: str) -> tuple[str, dict[str, str | None]]:
    """解析 ``*KEYWORD, ELSET=UPPER, MATERIAL=STEEL, GENERATE`` 行。

    Returns:
        (keyword_upper, params_dict)
    """
    body = line.lstrip()
    body = body[1:]  # 去掉前导 '*'
    # 按 ',' 分割，第一段是 keyword，其余是参数
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
            params[p.upper()] = None  # 旗标参数（如 GENERATE / SRT）
    return keyword, params


def scan_cards(lines: list[str]) -> list[Card]:
    """扫描整份 ``.inp``，把每个 ``*KEYWORD`` 收成一张 :class:`Card`。

    注释行（``**``）和空行被跳过；每个卡片的数据行持续到下一个 ``*`` 关键字
    （注释 ``**`` 不算）。未知关键字同样被收成 Card（由上层决定是否归入
    ``unsupported_cards``），保证 graceful。
    """
    cards: list[Card] = []
    i = 0
    n = len(lines)
    while i < n:
        ln = lines[i]
        s = ln.strip()
        # 注释 or 空行
        if not s or s.startswith("**"):
            i += 1
            continue
        if s.startswith("*"):
            keyword, params = _parse_keyword_line(s)
            header_no = i
            data_lines: list[str] = []
            data_nos: list[int] = []
            i += 1
            # 收集数据行直到下一个关键字；注释 ** 与空行跳过
            while i < n:
                ds = lines[i].strip()
                if not ds or ds.startswith("**"):
                    i += 1
                    continue
                if ds.startswith("*"):
                    break  # 下一个卡片
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
            # 文件级裸数据行（理论上不该出现，跳过）
            i += 1
    return cards


# ──────────────────────────────────────────────────────────────────────────
# meshio 网格概览（带 graceful 文本兜底）
# ──────────────────────────────────────────────────────────────────────────


def _meshio_overview(path: str, lines: list[str]) -> dict:
    """读网格统计：节点数 + 各单元类型计数（保留**原始 Abaqus TYPE 名**）。

    设计要点：
      * meshio 把 ``S4`` 归一化成 ``quad``、``B31``→``line``，且 reverse-map 有
        collision bug —— 所以 ``elements_by_type`` **以文本扫描的原始 TYPE 名为准**
        （S4/B31/C3D8），meshio 只用来补充 bbox / NSET / ELSET 名。
      * meshio 对未知 TYPE 硬抛 ReadError；本函数对 meshio 失败 graceful 降级，
        保证 ``parse_model`` 永不因 meshio 挂。
    """
    # 1) 文本计数（原始 TYPE 名，永远可得）
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
        "elements_by_type": dict(elements_by_type),  # 原始 TYPE 名
        "elset_names": [],
        "nset_names": [],
        "bbox": None,
        "meshio_used": False,
        "meshio_error": None,
    }

    # 2) meshio 补充 bbox / 集合名（失败不影响主字段）
    try:
        import meshio  # 延迟导入
    except Exception as e:  # pragma: no cover - 环境问题
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
        # ⚠️ 必须捕 BaseException：meshio 对未知单元 TYPE 会 sys.exit(1)（SystemExit
        #    是 BaseException 不是 Exception），这里要 graceful 降级到文本计数，绝不崩。
        overview["meshio_error"] = f"{type(e).__name__}: {e}"
        logger.warning("meshio.read failed, using text counts only: %s", e)

    return overview


# ──────────────────────────────────────────────────────────────────────────
# 卡片专用抽取器
# ──────────────────────────────────────────────────────────────────────────


def _to_float(s: str) -> float | None:
    """安全 str→float；解析失败返回 None。"""
    s = s.strip().rstrip(",")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def extract_shell_sections(cards: list[Card]) -> list[dict]:
    """抽取 ``*SHELL SECTION`` 卡 → 壳厚 T + ELSET + MATERIAL。

    Abaqus/CalculiX 约定：厚度在卡片后**第 1 个数据行的第 1 个数值**。
    （OFFSET/MATERIAL 等放在关键字行的参数里，不动。）
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
    """抽取 ``*BEAM SECTION`` 卡 → 截面类型 SECTION= 与参数。

    强制库截面 ``SECTION=I``（避开 ``*BEAM GENERAL SECTION`` 在 ccx 历史版本的
    bug）。其它 SECTION 类型同样
    读出原值，但 list_design_vars 只暴露 SECTION=I 的 h/b/t1/t2。
    数据行 line1: ``h, b, t1, t2``（Abaqus/CalculiX 4 参数，顺序一致）。
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
                "params": vals,  # [h, b, t1, t2] (SECTION=I)
                "header_line_no": c.header_line_no,
                "data_line_no": c.data_line_nos[0] if c.data_line_nos else -1,
            }
        )
    return out


def extract_materials(cards: list[Card]) -> dict[str, dict]:
    """抽取材料：把 ``*ELASTIC`` / ``*DENSITY`` / ``*PLASTIC`` 关联到所属 ``*MATERIAL``。

    Abaqus 语义：``*MATERIAL, NAME=X`` 后紧跟若干子卡（``*ELASTIC``/``*DENSITY``/
    ``*PLASTIC``），它们没有 NAME 参数，靠**出现顺序**归属到最近的 ``*MATERIAL``。
    本函数按顺序遍历 cards 维护 "当前材料" 上下文。
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
    """抽取 ``*CLOAD`` / ``*DLOAD`` 载荷。

    ``*CLOAD`` 数据行：``<node|nset>, <DOF>, <magnitude>``
    ``*DLOAD`` 数据行：``<elset|element>, <TYPE>, <magnitude>``
    每行作为一个独立载荷项（index 在 list_design_vars 里作 var_id 后缀）。
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


# 已知/关心的关键字白名单（其余归入 unsupported_cards）
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


# ──────────────────────────────────────────────────────────────────────────
# 公开 API
# ──────────────────────────────────────────────────────────────────────────


def parse_model(inp_path: str) -> dict:
    """读 ``.inp`` 返回模型概览（``parse_inp`` MCP 工具用）。

    Returns:
        包含 ``nodes`` / ``elements_by_type`` / ``shell_sections`` /
        ``beam_sections`` / ``materials`` / ``loads`` / ``unsupported_cards``
        等键的 dict。
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
    """提取可调设计变量，每个变量带 ``modify`` 定位器（供 :func:`modify_card`）。

    覆盖 4 类（PRD 变量族 C）：
      * 壳厚（``*SHELL SECTION``）
      * 梁截面（``*BEAM SECTION, SECTION=I`` 的 h/b/t1/t2）
      * 材料属性（E / nu / 密度）
      * 载荷幅值（``*CLOAD`` / ``*DLOAD``）

    Returns:
        ``{"variables": [ {..., "modify": {...}} ], "count": N}``
    """
    model = parse_model(inp_path)
    variables: list[dict] = []

    # 1) 壳厚
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

    # 2) 梁截面 SECTION=I（h/b/t1/t2）
    beam_fields = [
        ("h", 0, "mm"),
        ("b", 1, "mm"),
        ("t1", 2, "mm"),
        ("t2", 3, "mm"),
    ]
    for b in model["beam_sections"]:
        if b.get("section") != "I":
            continue  # 仅暴露 SECTION=I（ccx 历史版本对 GENERAL SECTION 有 bug）
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

    # 3) 材料属性（E / nu / 密度）
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

    # 4) 载荷幅值
    # ⚠️ _index 必须按 card_type 分别编号：modify_card 的 _index 定位（见 _locate_card）
    #    是在**单种 card_type 内**把所有该类型卡片的数据行拍平后取下标。若这里用跨类型
    #    全局 enumerate 索引，CLOAD+DLOAD 混存时 DLOAD 的 _index 会从 CLOAD 计数后接着
    #    编，导致 modify 时越界（cross-layer 契约修正）。var_id 前缀带类型，无冲突。
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
                    "data_line": -1,  # 特殊：按 index 定位（见 _locate_card）
                    "value_pos": 2,
                },
            }
        )

    return {"variables": variables, "count": len(variables)}


# ──────────────────────────────────────────────────────────────────────────
# 文本原位改值（核心：绝不用 meshio.write）
# ──────────────────────────────────────────────────────────────────────────


def _fmt_value(v: float) -> str:
    """数值格式化：紧凑科学计数，保留 6 位有效数字。"""
    return f"{float(v):.6g}"


def _set_field_on_line(line: str, value_pos: int, new_value: float) -> str:
    """对一行逗号分隔的数据，原位替换第 ``value_pos`` 个数值。

    保留行首缩进与原始尾随逗号；未触及的字段保持原文（含小数点），最小化 diff。
    """
    # 分离行尾换行
    nl = "\n" if line.endswith("\n") else ""
    body = line.rstrip("\n")
    # 保留行首缩进
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
    # 尾随逗号（最后一个 part 为空）→ 重建时保留
    trailing = bool(raw_parts and raw_parts[-1].strip() == "")
    if trailing:
        # 丢掉末尾空 part，join 后补一个尾随逗号
        body_parts = parts[:-1] if parts and parts[-1] == "" else parts
        return f"{indent}{', '.join(body_parts)},{nl}"
    return f"{indent}{', '.join(parts)}{nl}"


def _header_matches(header_line: str, card_type: str, match: dict) -> str | None:
    """检查一行是否是目标卡片头。

    Returns:
        命中时返回归一化的上下文 key（用于 ELASTIC/DENSITY 的材料归属），
        否则 ``None``。
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
    # ELASTIC/DENSITY 靠 _material 上下文，不在 header 上判定（由 _locate_card 处理）
    if "_material" in match or "_index" in match:
        return "ctx"  # 仅确认 keyword 匹配，上下文由调用方判
    for k, v in match.items():
        if k.startswith("_"):
            continue
        if params.get(k.upper()) != v:
            return None
    return kw


def _locate_card(
    lines: list[str], card_spec: dict
) -> tuple[int, int]:
    """在文件行里定位目标卡片的 header 行号与目标数据行号。

    支持三类 match：
      * 普通参数（ELSET/MATERIAL 等）—— 找 header 参数匹配
      * ``_material`` —— 找 ``*MATERIAL, NAME=X`` 之后的该卡片
      * ``_index`` —— 该卡片下第 N 个数据行（载荷用）

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
        # 先找 *MATERIAL, NAME=mat_name
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
        # 在材料之后找第一个 *<card_type>（遇到下一个 *MATERIAL 停止）
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
                    break  # 进入下一个材料
                if kw == card_type:
                    # 收数据行
                    data_nos = _collect_data_line_nos(lines, j)
                    if data_line_idx < len(data_nos):
                        return data_nos[data_line_idx], value_pos
                    raise ValueError(
                        f"{card_type} under {mat_name} has no data_line {data_line_idx}"
                    )
        raise ValueError(f"*{card_type} under material {mat_name} not found")

    if "_index" in match:
        idx = int(match["_index"])
        # ⚠️ 与 extract_loads 的语义对齐：把**所有**该 card_type 卡片的数据行拍平成一个
        #    全局 list 再按 idx 取（不能只看第一个卡片）。否则多个 *CLOAD/*DLOAD 卡时，
        #    list_design_vars 给的全局 idx 会越界（cross-layer 契约修正）。
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

    # 普通参数匹配
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
    """从 header 行往后收集数据行号（直到下一个关键字，跳过注释/空行）。"""
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
    """对 ``.inp`` 指定卡片的某个字段做**文本原位替换**，写出新 ``.inp``。

    策略：读全部行 → 按定位器找到目标数据行 → 改第 ``value_pos`` 个逗号字段 →
    原样写回其余所有行。**不 round-trip meshio**（research 警告 meshio.write 会
    丢卡片且改单元类型）。

    Args:
        inp_path:  原 ``.inp`` 路径。
        card_spec: 定位器。可为：
            * str —— ``list_design_vars`` 返回的 ``var_id``（自动重查定位器）；
            * dict —— 形如 ``{"card_type", "match", "data_line", "value_pos"}``，
              即设计变量的 ``modify`` 字段。
        new_value: 新数值。
        out_path:  输出路径；None 则写回原文件（``inp_path``）。

    Returns:
        ``{"out_path", "changed", "card_type", "field_or_pos", "old_value",
        "new_value"}``
    """
    with open(inp_path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    # var_id → locator（调用方可直接传 var_id）
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
