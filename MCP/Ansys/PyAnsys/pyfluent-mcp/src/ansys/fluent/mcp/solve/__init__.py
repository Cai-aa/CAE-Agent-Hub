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

"""Solve leaf, which provides Fluent solver live-context and execution tools.

The MCP class :class:`SolveMCP` lives in
:mod:`ansys.fluent.mcp.solve.mcp`; it is re-exported here so both
``ansys.fluent.mcp.solve`` and ``ansys.fluent.mcp.solve.mcp`` resolve
to the same class. New code may prefer the direct import for
explicitness.

The product-domain layer is organised into subpackages:
:mod:`~ansys.fluent.mcp.solve.backends` (PyFluent / composite
backends), :mod:`~ansys.fluent.mcp.solve.catalog` (offline schema,
index, help, retriever), :mod:`~ansys.fluent.mcp.solve.lib` (domain
tools, units, patterns) and :mod:`~ansys.fluent.mcp.solve.data`
(bundled settings schema).
"""

from __future__ import annotations

from ansys.fluent.mcp.solve.mcp import SolveMCP

__all__ = ["SolveMCP"]
