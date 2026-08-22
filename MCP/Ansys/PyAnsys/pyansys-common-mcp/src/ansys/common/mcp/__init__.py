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

"""Common Model Context Protocol (MCP) infrastructure for PyAnsys libraries.

This package provides base classes, utilities, and common tools that
PyAnsys product-specific MCP servers can extend and use.
"""

import importlib.metadata as importlib_metadata

from ansys.common.mcp.context import PyAnsysBaseAppContext
from ansys.common.mcp.helpers import (
    PersistentPythonSession,
)
from ansys.common.mcp.logging_config import get_logger, setup_logging
from ansys.common.mcp.server import PyAnsysBaseMCP
from ansys.common.mcp.tools import (
    create_custom_plot,
    execute_python_code,
)

__version__ = importlib_metadata.version(__name__.replace(".", "-"))
"""PyAnsys Common MCP version."""

__all__ = [
    "PyAnsysBaseAppContext",
    "PyAnsysBaseMCP",
    "PersistentPythonSession",
    "setup_logging",
    "get_logger",
    "execute_python_code",
    "create_custom_plot",
    "__version__",
]
