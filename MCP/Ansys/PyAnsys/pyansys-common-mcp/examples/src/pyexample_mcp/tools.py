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

"""Tools for PyExample MCP server."""

import json
from typing import Optional

from fastmcp.server import Context

from ansys.common.mcp.logging_config import get_logger
from pyexample_mcp import app

logger = get_logger(__name__)


@app.resource("toolsets://definition")
def list_tool_sets() -> list[dict]:
    """Toolset definitions."""
    return [
        {
            "name": "structures",
            "description": "Tools for creating and running structural models",
            "skill": (
                "Use these tools to set up and solve structural simulations. "
                "Start with create_model to define the model, then use "
                "run_simulation to execute the analysis."
            ),
            "tools": ["create_model", "run_simulation"],
        },
        {
            "name": "post_processing",
            "description": "Tools for processing and exporting simulation results",
            "skill": (
                "Use these tools to inspect results and run custom analyses after a simulation. "
                "Use get_command_history to review past commands and execute_python_code "
                "for custom post-processing scripts."
            ),
            "tools": ["get_command_history", "execute_python_code"],
        },
    ]


# Define tools for interacting with PyExample instance
@app.tool()
def execute_command(ctx: Context, command: str) -> str:
    """Execute a PyExample command.

    Parameters
    ----------
    ctx : Context
        The FastMCP context
    command : str
        PyExample command to execute

    Returns
    -------
    str
        Command execution result

    """
    app_context = ctx.fastmcp._lifespan_result

    if not app_context.example_instance:
        return "Error: PyExample not connected"

    try:
        result = app_context.example_instance.run_command(command)
        app_context.command_history.append(command)
        logger.info(f"Executed command: {command}")
        return str(result)
    except Exception as e:
        logger.error(f"Command execution failed: {e}")
        return f"Error: {e}"


@app.tool(tags={"structures"})
def create_model(
    ctx: Context,
    name: str,
    model_type: str = "default",
    parameters: Optional[dict] = None,
) -> str:
    """Create a new model in PyExample.

    Parameters
    ----------
    ctx : Context
        The FastMCP context
    name : str
        Name for the new model
    model_type : str
        Type of model to create
    parameters : Optional[dict]
        Additional model parameters

    Returns
    -------
    str
        Status message

    """
    app_context = ctx.fastmcp._lifespan_result

    if not app_context.example_instance:
        return "Error: PyExample not connected"

    # Create model (simulated)
    params = parameters or {}
    model = app_context.example_instance.create_model(name, model_type, **params)

    # Update command history
    command = f"CREATE MODEL {name} TYPE {model_type}"
    app_context.command_history.append(command)

    logger.info(f"Created model: {name} (type: {model_type})")
    return f"Model '{name}' created successfully\n{model}"


@app.tool(tags={"structures"})
def run_simulation(
    ctx: Context, model_name: Optional[str] = None, save_results: bool = True
) -> str:
    """Run a simulation on the specified model.

    Parameters
    ----------
    ctx : Context
        The FastMCP context
    model_name : Optional[str]
        Model to simulate (uses active model if not specified)
    save_results : bool
        Whether to save results in context

    Returns
    -------
    str
        Simulation results summary

    """
    app_context = ctx.fastmcp._lifespan_result

    if not app_context.example_instance:
        return "Error: PyExample not connected"

    # Determine which model to use
    target_model = model_name or app_context.example_instance.active_model

    if not target_model:
        return "Error: No model specified or active"

    # Run simulation (simulated)
    command = f"SOLVE MODEL {target_model}"
    result = app_context.example_instance.run_command(command)

    # Save results if requested
    if save_results:
        app_context.simulation_results[target_model] = {"status": "completed", "summary": result}

    app_context.command_history.append(command)
    logger.info(f"Simulation completed for model: {target_model}")

    return f"Simulation completed for '{target_model}'\n{result}"


@app.tool(tags={"post_processing"})
def get_command_history(ctx: Context, format: str = "list") -> str:
    """Retrieve command execution history.

    Parameters
    ----------
    ctx : Context
        The FastMCP context
    format : str
        Output format: 'list', 'numbered', or 'json'

    Returns
    -------
    str
        Command history in requested format

    """
    app_context = ctx.fastmcp._lifespan_result

    if not app_context.command_history:
        return "No commands executed yet"

    if format == "numbered":
        lines = [f"{i + 1}. {cmd}" for i, cmd in enumerate(app_context.command_history)]
        return "\n".join(lines)

    elif format == "json":
        return json.dumps(app_context.command_history, indent=2)

    else:  # list format
        return "\n".join(app_context.command_history)


@app.tool(tags={"post_processing"})
def execute_python_code(ctx: Context, code: str) -> str:
    """Execute Python code in the persistent session.

    This allows for custom analysis and processing using the
    full Python ecosystem.

    Parameters
    ----------
    ctx : Context
        The FastMCP context
    code : str
        Python code to execute

    Returns
    -------
    str
        Execution output

    """
    app_context = ctx.fastmcp._lifespan_result

    result = app_context.python_session.execute(code)

    if result["success"]:
        output = str(result["stdout"])
        if result["stderr"]:
            output += f"\n\nWarnings:\n{result['stderr']}"
        return output
    else:
        return f"Error: {result['error']}"
