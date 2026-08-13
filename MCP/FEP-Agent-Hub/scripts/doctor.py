from __future__ import annotations

import json

from open_cae_core import load_config
from elmer_mcp.service import ElmerService
from freecad_mcp.service import FreeCADService
from paraview_mcp.service import ParaViewService


def main() -> int:
    config = load_config()
    report = {
        "workspace": str(config.workspace_root),
        "freecad": FreeCADService(config).environment_probe().to_dict(),
        "elmer": ElmerService(config).environment_probe().to_dict(),
        "paraview": ParaViewService(config).environment_probe().to_dict(),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if all(report[name]["ok"] for name in ("freecad", "elmer", "paraview")) else 1


if __name__ == "__main__":
    raise SystemExit(main())

