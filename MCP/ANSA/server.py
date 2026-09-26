"""Source-checkout entry point for MCP clients.

Installed environments should normally use ``python -m ansa_mcp``.  This
wrapper keeps a checkout runnable without relying on the caller's PYTHONPATH.
"""

from __future__ import annotations

import sys
from pathlib import Path


SRC = Path(__file__).resolve().parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ansa_mcp.__main__ import main  # noqa: E402
from ansa_mcp.server import mcp  # noqa: E402,F401


if __name__ == "__main__":
    main()

