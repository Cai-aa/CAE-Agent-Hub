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

"""Entry point for running the MCP server as a module.

**Note:** This common package is primarily intended to be used as a library
by product-specific MCP servers (such as PyMAPDL or PyFluent). It does not
provide a standalone runnable server.

To create a product-specific MCP server, see the examples in the README.
"""

import sys


def main():
    """Provide usage information. This is the main entry point for module execution."""
    print(
        "ansys-common-mcp is a library for building PyAnsys MCP servers.\n"
        "It is not meant to be run directly.\n\n"
        "To create a product-specific MCP server, see the documentation:\n"
        "https://github.com/ansys/pyansys-common-mcp\n\n"
        "For example product-specific servers, see:\n"
        "  - pymapdl-mcp: https://github.com/ansys/pymapdl-mcp\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
