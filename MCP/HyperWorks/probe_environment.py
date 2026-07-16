from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from hyperworks_mcp.environment import environment_report  # noqa: E402
from hyperworks_mcp.settings import Settings  # noqa: E402


if __name__ == "__main__":
    settings = Settings.from_env()
    settings.ensure()
    print(json.dumps(environment_report(settings), ensure_ascii=False, indent=2))
