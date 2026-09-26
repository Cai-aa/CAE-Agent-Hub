"""Fixed, non-interactive ANSA stage of the cantilever demonstration.

ANSA runs this file in its own embedded Python interpreter.  The external MCP
sets only a new run directory; no user-supplied Python or command is evaluated.
"""

from __future__ import annotations

import json
import os
import traceback
from pathlib import Path


def main() -> None:
    from ansa import base, constants

    run_dir = Path(os.environ["ANSA_MCP_CANTILEVER_RUN_DIR"]).resolve()
    source = run_dir / "cantilever_source.inp"
    database = run_dir / "cantilever.ansa"
    exported = run_dir / "cantilever_ansa_export.inp"
    report_path = run_dir / "ansa_stage.json"

    report = {"stage": "ansa", "ok": False}
    try:
        if not source.is_file():
            raise RuntimeError("The fixed cantilever input deck is missing")
        base.SetCurrentDeck(constants.ABAQUS)
        imported = base.InputAbaqus(str(source))
        nodes = base.CollectEntities(constants.ABAQUS, None, "NODE")
        elements = base.CollectEntities(constants.ABAQUS, None, "__ELEMENTS__")
        materials = base.CollectEntities(constants.ABAQUS, None, "__MATERIALS__")
        if len(nodes) != 615 or len(elements) != 320 or not materials:
            raise RuntimeError(
                "ANSA import entity counts differ from the prescribed 615 nodes "
                "and 320 hexahedral elements"
            )
        if base.SaveAs(str(database)) != 0 or not database.is_file():
            raise RuntimeError("ANSA did not save the database")
        base.OutputAbaqus(str(exported), mode="all", disregard_includes="on")
        if not exported.is_file() or exported.stat().st_size < 1000:
            raise RuntimeError("ANSA did not export a usable Abaqus deck")
        report.update(
            {
                "ok": True,
                "import_return": str(imported),
                "node_count": len(nodes),
                "element_count": len(elements),
                "material_count": len(materials),
                "database": str(database),
                "exported_deck": str(exported),
                "exported_bytes": exported.stat().st_size,
            }
        )
    except Exception as exc:
        report["error"] = "%s: %s" % (type(exc).__name__, exc)
        report["traceback"] = traceback.format_exc(limit=8)
    finally:
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
