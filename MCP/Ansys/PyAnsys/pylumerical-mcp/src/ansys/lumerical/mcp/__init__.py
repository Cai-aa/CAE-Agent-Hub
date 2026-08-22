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

"""PyLumerical MCP Server.

Model Context Protocol server that exposes Ansys Lumerical (via PyLumerical)
to LLM agents. Built on top of ``ansys-common-mcp``'s :class:`PyAnsysBaseMCP`,
extended to support multiple concurrent named Lumerical sessions hosted inside
the framework's persistent Python subprocess.
"""

# Version
# ------------------------------------------------------------------------
import importlib.metadata as importlib_metadata

__version__ = importlib_metadata.version(__name__.replace(".", "-"))
"""PyLumerical MCP version."""

# Importing ``tools`` and ``contexts`` runs their ``@app.tool()`` decorators,
# which is the only way tools get registered on :data:`app`.
from ansys.lumerical.mcp import (
    contexts as _contexts,  # noqa: F401
    tools as _tools,  # noqa: F401
)
from ansys.lumerical.mcp.server import app

__all__ = [
    "__version__",
    "app",
]
