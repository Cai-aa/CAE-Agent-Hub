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

"""Entry point for running PyExample MCP server."""

import sys

from ansys.common.mcp.logging_config import setup_logging
from pyexample_mcp import app

# Import tools to register them with the app
import pyexample_mcp.tools  # noqa: F401


def main(argv=None):
    """Run the PyExample MCP server."""
    # Setup logging
    setup_logging(level="INFO")

    # Run the server using the base-class CLI handler.
    # Supports --transport stdio|http, --http-host, --http-port, --cors-origins.
    app.run_cli(argv)

    return 0


if __name__ == "__main__":
    sys.exit(main())
