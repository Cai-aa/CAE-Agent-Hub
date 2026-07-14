# -*- coding: utf-8 -*-
"""
Abaqus MCP GUI menu loader.

Copy this directory to the Abaqus user plugin folder. The loader executes the
main socket bridge plugin from ABAQUS_MCP_HOME so there is only one maintained
implementation.
"""

from __future__ import print_function

import os
import sys
import traceback


def _resolve_mcp_home():
    env_home = os.environ.get("ABAQUS_MCP_HOME", "").strip()
    if env_home:
        return env_home
    return os.path.join(os.path.expanduser("~"), ".abaqus-mcp")


def _load_main_plugin():
    plugin_path = os.path.join(_resolve_mcp_home(), "abaqus_mcp_plugin.py")
    if not os.path.exists(plugin_path):
        print("Abaqus MCP loader could not find: " + plugin_path)
        print("Set ABAQUS_MCP_HOME to the folder containing abaqus_mcp_plugin.py.")
        return

    try:
        import __main__
        if getattr(__main__, "_ABAQUS_MCP_MENU_REGISTERED", False):
            return
        with open(plugin_path, "r") as handle:
            code = handle.read()
        exec(compile(code, plugin_path, "exec"), __main__.__dict__)
    except Exception:
        print("Abaqus MCP loader failed:")
        traceback.print_exc()


_load_main_plugin()
