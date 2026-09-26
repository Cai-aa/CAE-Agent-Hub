"""ANSA user-script buttons for the MCP bridge, without Plugin Manager.

Load this file through Development > Load Script or Script Manager. Loading it
only registers buttons; the bridge starts solely after the user presses Start.
"""

import os
import sys

import ansa


_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def _plugin_module():
    """Restore the script directory if ANSA resets sys.path before a click."""
    if _ROOT not in sys.path:
        sys.path.insert(0, _ROOT)
    import ansa_mcp_plugin

    return ansa_mcp_plugin


@ansa.session.defbutton("ANSA MCP", "Start")
def ansa_mcp_start():
    """Start the MCP bridge and dock its status window beside Database."""
    return _plugin_module().start_bridge()


@ansa.session.defbutton("ANSA MCP", "Status")
def ansa_mcp_status():
    """Print the current bridge status in the ANSA message area."""
    return _plugin_module().show_bridge_status()


@ansa.session.defbutton("ANSA MCP", "Stop")
def ansa_mcp_stop():
    """Stop the MCP bridge and close its status window."""
    return _plugin_module().stop_bridge()
