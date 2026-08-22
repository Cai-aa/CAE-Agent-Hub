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

"""ANSYS Fluent MCP server.

A Model Context Protocol (MCP) server that lets AI assistants drive an
ANSYS Fluent solver session through `PyFluent
<https://fluent.docs.pyansys.com/>`_. It load cases and meshes, inspects the
live settings tree, validates and executes settings and API code, runs
iterations, and queries results.

This package is the open-source distribution of the Fluent Solve MCP
leaf. The following public re-exports cover the server class plus the shared
result models, errors, and configuration used by integrators.
"""

from __future__ import annotations

import importlib.metadata as importlib_metadata

from ansys.fluent.mcp.common.config import (
    ConfigError,
    FluidsMCPConfig,
    load_config,
    validate_config,
)
from ansys.fluent.mcp.common.errors import (
    BackendUnavailableError,
    DiscoveryError,
    FluidsMCPError,
    InvalidArgumentsError,
    NotConnectedError,
    UpstreamError,
)
from ansys.fluent.mcp.common.models import ConnectResult, RunCodeResult
from ansys.fluent.mcp.solve import SolveMCP

__version__ = importlib_metadata.version(__name__.replace(".", "-"))
"""PyFluent MCP version."""

__all__ = [
    "__version__",
    "SolveMCP",
    "ConnectResult",
    "RunCodeResult",
    "BackendUnavailableError",
    "DiscoveryError",
    "FluidsMCPError",
    "InvalidArgumentsError",
    "NotConnectedError",
    "UpstreamError",
    "ConfigError",
    "FluidsMCPConfig",
    "load_config",
    "validate_config",
]
