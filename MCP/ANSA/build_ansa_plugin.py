"""Build a minimal, machine-specific ANSA Plugin Manager descriptor.

The generated .ppl is only a candidate until its GUI load and startup are
validated on an empty ANSA session. This script does not install or activate it.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
TEMPLATE = HERE / "plugin" / "ANSA_MCP_Bridge.ppl.in"
MARKER = "__ANSA_MCP_ENTRY_PATH__"


def render_descriptor(entry: Path) -> str:
    entry = entry.resolve(strict=True)
    if entry.name != "ansa_mcp_plugin.py" or not entry.is_file():
        raise ValueError("entry must be an existing ansa_mcp_plugin.py file")
    source = TEMPLATE.read_text(encoding="utf-8")
    if source.count(MARKER) != 1:
        raise ValueError("plugin template must contain exactly one entry marker")
    rendered = source.replace(MARKER, json.dumps(str(entry)))
    compile(rendered, "ANSA_MCP_Bridge.ppl", "exec")
    return rendered


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entry", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    parser.error(
        "Standalone descriptors are retired. Use build_ansa_plugin_package.py "
        "--bridge-entry <entry> --output <directory> --ansa-launcher <ansa64.bat>."
    )


if __name__ == "__main__":
    raise SystemExit(main())
