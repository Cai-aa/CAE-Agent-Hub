"""ANSA -nogui probe for a generated .ppl descriptor (not Plugin Manager)."""

from __future__ import annotations

import os
from pathlib import Path


descriptor = Path(os.environ["ANSA_MCP_PPL_PROBE"]).resolve(strict=True)
if descriptor.name != "ANSA_MCP_Bridge.ppl":
    raise RuntimeError("probe requires a generated ANSA_MCP_Bridge.ppl")
namespace = {"__file__": str(descriptor), "__name__": "__ansa_mcp_ppl_probe__"}
exec(compile(descriptor.read_text(encoding="utf-8"), str(descriptor), "exec"), namespace)
print("ANSA MCP .ppl descriptor registered in no-GUI ANSA process")
