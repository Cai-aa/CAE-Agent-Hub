"""Run this file inside ANSA to stop the MCP bridge."""

import os
import sys


PLUGIN_ROOT = os.path.dirname(os.path.abspath(__file__))
if PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, PLUGIN_ROOT)

from ansa_mcp_bridge import stop  # noqa: E402


def main():
    return stop()


STOP_RESULT = main()
print("ANSA MCP stop result:", STOP_RESULT)

