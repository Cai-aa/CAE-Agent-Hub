"""Run inside ANSA to build (never install) a native MCP plugin package."""

import json
import os
import runpy
import traceback
from pathlib import Path

from ansa import session


root = Path(os.environ["ANSA_MCP_NATIVE_PACKAGE_DIR"]).resolve(strict=True)
api_path = Path(os.environ["ANSA_MCP_PACKAGER_API"]).resolve(strict=True)
metadata = json.loads((root / "packager_metadata.json").read_text(encoding="utf-8"))
archive_name = metadata["ansa_metadata"]["archive_name"]
if Path(archive_name).name != archive_name or not archive_name.endswith(".bpkg"):
    raise ValueError("archive_name must be a plain .bpkg filename")
archive = root / archive_name
if archive.exists():
    raise FileExistsError("BETA package already exists; refusing to overwrite")
report = {"ok": False, "archive": str(archive)}
try:
    api = runpy.run_path(str(api_path))
    api["no_gui_plugin_packager_smart"](
        str(root / "packager_metadata.json"), str(root / "ANSA_MCP_Bridge.ppl")
    )
    report["ok"] = archive.is_file() and archive.stat().st_size > 0
except Exception:
    report["error"] = traceback.format_exc()
(root / "bpkg_build_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print("ANSA MCP BPKG BUILD", json.dumps(report), flush=True)
session.Quit(0 if report["ok"] else 1)
