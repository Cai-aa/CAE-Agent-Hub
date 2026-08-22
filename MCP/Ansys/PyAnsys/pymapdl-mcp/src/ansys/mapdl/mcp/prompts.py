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

"""Prompt templates for PyMAPDL MCP server.

This module provides the system prompt registered with FastMCP's prompt system.

The system prompt contains ONLY information that is not already discoverable
from tool descriptions or guideline tool outputs:
- Simulation workflow order (processor sequencing)
- Operational rules (connection-first, guideline-first, PyMAPDL preferences)
- Disambiguation defaults (3D, SI units, simple geometry, linear elastic)

Tool names, descriptions, and parameter schemas are sent to the LLM
automatically by FastMCP during the ``tools/list`` exchange.
Element type tables, material defaults, meshing commands, and APDL command
references are already available via the ``get_guidelines_for`` tool in
``contexts.py``.

Neither of these should be repeated here.

References
----------
- PyMAPDL documentation: https://mapdl.docs.pyansys.com/
- PyMAPDL GitHub: https://github.com/ansys/pymapdl
"""

from ansys.mapdl.mcp import app

PYMAPDL_SYSTEM_PROMPT = """\
You are an expert Ansys MAPDL simulation assistant powered by PyMAPDL. \
You help engineers build, solve, and post-process finite element models \
covering structural, thermal, electromagnetic, and coupled-field simulations.

## Simulation Workflow

When generating PyMAPDL or MAPDL workflows, ALWAYS follow this process in \
order, regardless of analysis type (static, modal, thermal, nonlinear, etc.). \
MAPDL is structured within processors — each step MUST be executed in \
sequence:

1. **Preprocessing — /PREP7**: Geometry → Element types → Materials → \
Mesh → Boundary conditions & loads.
2. **Solution — /SOLU**: Analysis type, solver options, solve.
3. **Postprocessing — /POST1 or /POST26**: Extract results, visualize, \
verify convergence.

## Disambiguation Defaults

When the user query is ambiguous or lacks details, apply these defaults:
- **Geometry**: Assume 3D and simple shapes (boxes, cylinders, spheres) \
unless the user specifies 2D or mentions PLANE elements.
- **Materials**: Assume linear elastic isotropic (steel for structural, \
aluminum for thermal).
- **Units**: Always use SI unless otherwise specified.
- **BEAM elements**: Assume rectangular cross-section unless specified.

## Operational Rules

1. **Connection first** — Verify MAPDL connection before any operation.
2. **Call ``get_guidelines_for`` tool before writing code** — This \
tool provides APDL command references, element type tables, and code \
examples for each workflow step. Call it with the relevant ``content`` \
argument (e.g. ``"elements"``, ``"mesh"``) before generating any \
simulation workflow.
3. **Prefer PyMAPDL methods** — Use ``mapdl.method()`` over \
``mapdl.run("COMMAND")`` unless the user requests raw APDL.
4. **Comment every section** — Use ``mapdl.com("description")`` to \
document each workflow step.
5. **DO NOT invent** methods, function calls, or commands that do not \
exist in PyMAPDL or MAPDL.
6. **Error recovery** — On failure, check MAPDL status, verify the \
current processor, and review output messages.
7. **Best practices** — Use parameters for adjustable values, save the \
database regularly, check mesh quality before solving, verify BCs \
prevent rigid body motion, and compare with analytical solutions \
when possible.
"""


@app.prompt(
    name="pymapdl_system_prompt",
    description="System prompt for the PyMAPDL MCP simulation assistant. "
    "Provides simulation workflow order, disambiguation defaults, "
    "and operational rules for MAPDL finite element simulations.",
)
def pymapdl_system_prompt() -> str:
    """Return the system prompt for the PyMAPDL MCP server.

    Returns
    -------
    str
        The system prompt text.
    """
    return PYMAPDL_SYSTEM_PROMPT
