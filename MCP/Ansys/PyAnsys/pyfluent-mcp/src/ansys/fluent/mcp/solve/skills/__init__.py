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

"""Routing skill for the standalone ``ansys-fluent-mcp`` server.

This package ships ``SKILL.md``, which targets the **MCP-exposed tool surface**.
The 22 tools and external host (such as VS Code Copilot, Cursor, or Claude
Desktop) sees over STDIO/HTTP. It is consumed by MCP clients that
support agent skills/rules.

DO NOT add Python code here. Keeping ``skills/`` empty of imports
keeps this folder shippable from the MCP-only package without pulling
in any heavier dependencies.
"""
