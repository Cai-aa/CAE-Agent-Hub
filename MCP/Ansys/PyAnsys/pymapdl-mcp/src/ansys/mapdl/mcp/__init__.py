# Copyright (C) 2025 - 2026 ANSYS, Inc. and/or its affiliates.
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

"""PyMAPDL MCP Server - Model Context Protocol server for Ansys MAPDL.

This package provides a Model Context Protocol (MCP) server that enables
AI assistants to interact with Ansys MAPDL through PyMAPDL. By default,
it is configured to use PyMAPDL code unless a clear statement is made to
use APDL code or for plotting MAPDL/PyMAPDL plots.

"""

# Version
# ------------------------------------------------------------------------------

import importlib.metadata as importlib_metadata

__version__ = importlib_metadata.version(__name__.replace(".", "-"))
"""PyMAPDL MCP version."""

# Ease import statements
# ------------------------------------------------------------------------------

from ansys.mapdl.mcp.server import (
    app,
    launcher,
)

__all__ = [
    "app",
    "launcher",
    "__version__",
]
