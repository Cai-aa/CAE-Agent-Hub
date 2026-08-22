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

"""Entry point for PyAEDT-MCP when run as a module.

Usage:
    python -m ansys.aedt.mcp [options]

Options:

    --transport {stdio,http}  Transport type (default: stdio)
    --machine MACHINE         AEDT machine hostname (default: localhost)
    --port PORT              AEDT gRPC port (default: 50051)
    --version VERSION        AEDT version to use
    --non-graphical          Run AEDT in non-graphical mode (default)
    --graphical              Run AEDT in graphical mode
    --connect                Connect to AEDT on startup
    --include-context        Register optional context helper tools
    --dynamic-tool-discovery Hide AEDT-only tools until a connection exists
    --http-host HOST         HTTP transport host (default: 127.0.0.1)
    --http-port PORT         HTTP transport port (default: 8080)
    --cors-origins ORIGINS   Allowed CORS origins for HTTP transport
"""

from ansys.aedt.mcp.server import launcher

if __name__ == "__main__":
    launcher()
