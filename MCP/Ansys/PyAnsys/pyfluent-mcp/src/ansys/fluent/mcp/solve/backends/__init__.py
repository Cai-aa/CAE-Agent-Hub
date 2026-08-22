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

"""Solve connection/data-plane backends.

* :mod:`ansys.fluent.mcp.solve.backends.composite`: The
  :class:`SolveCompositeBackend`; PyFluent for execution and live
  context.
* :mod:`ansys.fluent.mcp.solve.backends.pyfluent`: local in-process
  :class:`PyFluentBackend` over gRPC.
* :mod:`ansys.fluent.mcp.solve.backends.introspection`: Fluent
  state probes used exclusively by ``PyFluentBackend``.
* :mod:`ansys.fluent.mcp.solve.backends.mesh_report_parsers`:
  Transcript scrapers that lift mesh-quality numbers out of Fluent
  console output.

Backends are the data plane shared by every higher layer (MCP leaf,
agent, gateway). They never know anything about LLMs, prompts, or
recipes.
"""
