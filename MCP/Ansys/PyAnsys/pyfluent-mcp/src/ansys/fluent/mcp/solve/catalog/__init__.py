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

"""Solve settings catalog (discovery, indexing, retrieval).

* :mod:`ansys.fluent.mcp.solve.catalog.schema`: Offline-cached
  PyFluent settings tree (~62k paths) used by the plan validator and
  the indexer.
* :mod:`ansys.fluent.mcp.solve.catalog.index`: Keyword inverted
  index built on top of the schema. Drives ``find_setting_path``.
* :mod:`ansys.fluent.mcp.solve.catalog.help`: Help/description
  dataclasses attached to catalog entries.
* :mod:`ansys.fluent.mcp.solve.catalog.retriever`: Semantic plus
  lexical retriever that returns ranked candidates for
  ``find_api``/RAG flows.

The catalog is consumed by BOTH backends (path validation,
``find_setting_path``) and the agent intelligence layer (RAG
grounding). Keeping it separate makes that dual ownership explicit.
"""
