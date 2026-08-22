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

"""PyMechanical-MCP is a Model Context Protocol (MCP) server for Ansys Mechanical.

This package allows AI assistants to interact with Ansys Mechanical through PyMechanical.
It leverages the Mechanical scripting API to perform structural analysis,
preprocessing, solving, and postprocessing tasks.

"""

import importlib.metadata as importlib_metadata

from ansys.mechanical.mcp.server import (
    app,
    launcher,
)

__version__ = importlib_metadata.version(__name__.replace(".", "-"))
"""PyMechanical MCP version."""

__all__ = [
    "app",
    "launcher",
    "__version__",
]
