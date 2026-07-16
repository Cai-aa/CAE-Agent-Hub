"""Source-checkout entry point for Codex MCP configuration."""

from __future__ import annotations

import sys
from pathlib import Path


SRC = Path(__file__).resolve().parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from hyperworks_mcp.server import main, mcp  # noqa: E402


if __name__ == "__main__":
    main()
