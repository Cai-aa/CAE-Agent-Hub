from __future__ import annotations

import os
import sys
import importlib


folder = os.path.abspath(os.path.dirname(__file__))
if folder not in sys.path:
    sys.path.insert(0, folder)

# HyperWorks keeps extension modules in the embedded Python interpreter after
# the extension is disabled.  Reload the dependency chain on the next enable
# so deploying an updated handler does not require restarting the application.
for module_name in (
    "hyperworks_mcp_extension.config",
    "hyperworks_mcp_extension.protocol",
    "hyperworks_mcp_extension.handlers",
    "hyperworks_mcp_extension.bridge",
    "hyperworks_mcp_extension.runtime",
):
    module = sys.modules.get(module_name)
    if module is not None:
        importlib.reload(module)

from hyperworks_mcp_extension.runtime import load  # noqa: E402


load()
