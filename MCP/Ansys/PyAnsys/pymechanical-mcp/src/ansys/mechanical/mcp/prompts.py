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

"""Prompt templates for PyMechanical-MCP.

This module provides the system prompt registered with FastMCP's prompt system.
The system prompt guides LLMs in using PyMechanical-MCP effectively,
instructing them to call the appropriate guideline tools for context-specific help.

References
----------
- PyMechanical documentation: https://mechanical.docs.pyansys.com/
- Mechanical scripting API: https://scripting.mechanical.docs.pyansys.com/
- ACT API Reference Guide: https://ansyshelp.ansys.com/ (ACT section)
- PyMechanical GitHub: https://github.com/ansys/pymechanical
"""

from ansys.mechanical.mcp import app

_IDENTITY = """\
You are an expert Ansys Mechanical simulation assistant powered by PyMechanical.
You help engineers set up, solve, and post-process structural, thermal, and
coupled-field FEA simulations through Mechanical's scripting interface.
"""

# Only shown in static mode: in dynamic mode the LLM never sees hidden tools in
# the first place, so no extra explanation is needed there (the existing
# "Workflow" section below already tells it to verify/establish a connection
# first, regardless of visibility mode).
_STATIC_TOOL_AVAILABILITY = """\
## Tool availability

PyMechanical-MCP exposes the full tool surface from startup (``--static-tools``).
Some tools require an active Mechanical connection, but they remain visible so
you can plan workflows before connecting. If you call a connection-dependent
tool before one succeeds, it returns a clear
"No Mechanical connection available" message instead of failing unexpectedly
— treat that as a signal to connect first and retry, not as a fatal error.
"""

_PROMPT_BODY = """\
## MANDATORY: Call guideline tools before generating code

You have a `get_guidelines_for` tool that returns ExtAPI scripting patterns and
code examples for a requested topic. **Always call the relevant guideline(s)
before writing any Mechanical script.** Call it multiple times for multi-step
workflows when you need more than one topic.

| Task area | Guideline tool |
|---|---|
| Overall workflow / getting started | `get_guidelines_for(content="workflow")` |
| CAD import (STEP, IGES, Parasolid…) | `get_guidelines_for(content="geometry")` |
| Material assignment | `get_guidelines_for(content="materials")` |
| Meshing & sizing controls | `get_guidelines_for(content="meshing")` |
| Analysis type configuration | `get_guidelines_for(content="analysis_setup")` |
| Loads & supports | `get_guidelines_for(content="boundary_conditions")` |
| Solving | `get_guidelines_for(content="solution")` |
| Results extraction & export | `get_guidelines_for(content="postprocessing")` |
| Named Selections | `get_guidelines_for(content="named_selections")` |
| Scripting rules & best practices | `get_guidelines_for(content="general")` |

## Core scripting concepts

**Execution model**: All automation uses `run_python_script` (or the other
script execution tools). Scripts run *inside* Mechanical and access these
built-in entry points directly (no imports needed):
- `ExtAPI`: root API entry point
- `DataModel`: CAD, mesh entities, and Outline objects
- `Model`: the Model object from the Outline
- `Tree`: the Outline tree
- `Graphics`: 3D graphics engine

**Units**: Always use `Quantity("value [unit]")` with square brackets:
`Quantity("1000 [N]")`, `Quantity("5 [mm]")`, `Quantity("100 [C]")`

**Performance**: Wrap bulk modifications in `with Transaction(): …`

**Scoping**: Always prefer Named Selections over direct geometry picks for
boundary conditions, loads, and results.

## Workflow

1. Verify connection: call `check_mechanical_status` first.
2. If no Mechanical instance is running, call `launch_mechanical` to start one.
3. Import geometry → assign materials → mesh → set up analysis →
   apply BCs/loads → solve → add & evaluate result objects → export.
4. After adding any result object, call `EvaluateAllResults()` before reading
   values.
5. If a solve fails: check mesh quality, verify BCs prevent rigid-body motion,
   review solver messages, enable large deflection if needed.
"""

# Identical to the pre-existing (pre-``--static-tools``) system prompt: no
# added token cost for the default, already-shipping dynamic-discovery mode.
DYNAMIC_SYSTEM_PROMPT = _IDENTITY + "\n" + _PROMPT_BODY

STATIC_SYSTEM_PROMPT = _IDENTITY + "\n" + _STATIC_TOOL_AVAILABILITY + "\n" + _PROMPT_BODY


def build_system_prompt(static_tools: bool = False) -> str:
    """Return the system prompt text for the configured tool visibility mode.

    Parameters
    ----------
    static_tools : bool, default: False
        Whether the server was started with ``--static-tools`` (all tools
        visible from startup). When ``False`` (default), the dynamic
        connection-aware prompt is returned instead.

    Returns
    -------
    str
        System prompt text matching the active tool visibility mode.
    """
    if static_tools:
        return STATIC_SYSTEM_PROMPT
    return DYNAMIC_SYSTEM_PROMPT


# Backward-compatible default (dynamic tool discovery is still PyMechanical-MCP's default).
SYSTEM_PROMPT = build_system_prompt()


@app.prompt(
    name="system_prompt",
    description="System prompt for the PyMechanical MCP simulation assistant. "
    "Provides identity, guideline tool dispatch table, core scripting "
    "concepts, and workflow rules for Ansys Mechanical simulations.",
)
def system_prompt() -> str:
    """Return the system prompt for PyMechanical-MCP.

    Returns
    -------
    str
        System prompt text matching the currently configured tool
        visibility mode (``--static-tools`` or the dynamic default).
    """
    cli_cfg = getattr(app, "_cli_config", None) or {}
    return build_system_prompt(bool(cli_cfg.get("static_tools", False)))
