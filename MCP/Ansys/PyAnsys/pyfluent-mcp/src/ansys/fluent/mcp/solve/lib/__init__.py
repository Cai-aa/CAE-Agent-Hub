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

"""Cross-cutting solve helpers that aren't backend/catalog/agent.

* :mod:`ansys.fluent.mcp.solve.lib.utl`: Unified Topology Layer
  detection and the :class:`PathFamily` helper used by every
  UTL-aware recipe and rule pack.
* :mod:`ansys.fluent.mcp.solve.lib.units`: Unit conversion and
  quantity-hint helpers.
* :mod:`ansys.fluent.mcp.solve.lib.pattern`: Wildcard pattern
  matching used by named-object resolution (also surfaced through
  :mod:`ansys.fluent.mcp.common.backend`).

These modules carry no model orchestration, no agent-loop, and no Fluent connection
state. They are pure helpers that the MCP, the backends, and the
agent layer all share.
"""
