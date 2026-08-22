# Copyright (C) 2026 Synopsys, Inc. and ANSYS, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""PyAEDT-MCP is an MCP (Model Context Protocol) server for Ansys Electronics Desktop (AEDT).

This package provides an MCP server that enables AI assistants to interact
with AEDT through PyAEDT.

Supported AEDT applications:

- HFSS (High-frequency structure simulator)
- Maxwell 2D/3D (Low-frequency electromagnetics)
- Q3D/Q2D (Parasitic extraction)
- Icepak (Thermal management)
- Circuit (Circuit simulation)
- TwinBuilder (System modeling)
- Mechanical (Structural analysis)
- EMIT (EMI/EMC analysis)
- RMXprt (Rotating machine design)
- HFSS 3D Layout (High-speed electronics)

Example:
    Run the MCP server::

        $ ansys-aedt-mcp --transport stdio

    Or connect to a running AEDT instance::

        $ ansys-aedt-mcp --connect --machine localhost --port 50051
"""

import importlib.metadata as importlib_metadata

from ansys.aedt.mcp.server import app, launcher

__version__ = importlib_metadata.version(__name__.replace(".", "-"))
"""PyAEDT-MCP version."""

__all__ = ["app", "launcher", "__version__"]
