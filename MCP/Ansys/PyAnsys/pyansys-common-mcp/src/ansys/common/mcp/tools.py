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

"""Common tool implementations for PyAnsys MCP servers.

This module provides reusable tool functions that product-specific MCP
servers can use or extend. These are not registered tools themselves,
but functions that can be called from product-specific tool implementations.
"""

import json

from fastmcp import Context

from ansys.common.mcp.helpers import (
    _sanitize_output,
    logger,
)
from mcp.types import ImageContent, TextContent


async def execute_python_code(
    ctx: Context,
    code: str,
    timeout: int = 60,
) -> str:
    """Execute Python code in the persistent Python session with automatic rule generation.

    This function should be used for custom Python code execution. When code execution
    fails, it automatically generates a rule using LLM analysis to prevent similar
    errors in the future.

    Parameters
    ----------
    ctx : Context
        MCP context containing server session and application context.
    code : str
        Python code to execute.
    timeout : int, default: 60
        Maximum time in seconds to allow for code execution.

    Returns
    -------
    str
        Execution result or error message. Returns JSON for structured output
        compatible with both stdio and http transports.

    Examples
    --------
    Execute simple Python code:

    .. code:: python

        code = '''
        result = sum([i**2 for i in range(10)])
        print(f"Sum of squares: {result}")
        '''
        await execute_python_code(ctx, code)


    Execute code with automatic rule generation on failure:

    .. code:: python

        code = "result = 1/0"  # This will fail
        await execute_python_code(ctx, code)


    Automatically adds rule like: ``{"Division Operations": ["Do not divide by zero"]}``

    """
    app_context = ctx.request_context.lifespan_context
    session = app_context.python_session

    if session is None:
        return json.dumps(
            {
                "success": False,
                "error": "No Python session available. The persistent Python session was not initialized.",  # noqa: E501
            },
            ensure_ascii=False,
        )

    try:
        # Sanitize the input code to remove problematic Unicode characters
        sanitized_code = _sanitize_output(code)

        logger.info(f"Executing Python code in persistent session:\n{sanitized_code}")

        # Execute code in persistent session
        result = session.execute(sanitized_code, timeout=timeout)

        # Parse the result
        if isinstance(result, dict):
            stdout = _sanitize_output(result.get("stdout", ""))
            stderr = _sanitize_output(result.get("stderr", ""))

            if result.get("success"):
                return json.dumps(
                    {
                        "success": True,
                        "stdout": stdout,
                        "stderr": stderr,
                        "message": "Python code executed successfully.",
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            else:
                # Execution failed - generate rule if enabled
                error_msg = result.get("error", "Unknown error occurred.")
                error_msg = _sanitize_output(error_msg)

                return json.dumps(
                    {
                        "success": False,
                        "stdout": stdout,
                        "stderr": stderr,
                        "error": error_msg,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
        else:
            # Fallback if result is not a dict
            return json.dumps(
                {
                    "success": True,
                    "stdout": _sanitize_output(str(result)) if result else "",
                    "stderr": "",
                    "message": "Python code executed successfully.",
                },
                ensure_ascii=False,
                indent=2,
            )

    except TimeoutError:
        error_dict = {
            "success": False,
            "error": f"Python code execution timed out after {timeout} seconds.",
        }
        logger.error(error_dict["error"])
        return json.dumps(error_dict, ensure_ascii=False)

    except Exception as e:
        error_dict = {"success": False, "error": f"Error executing Python code: {str(e)}"}
        logger.error(error_dict["error"])
        return json.dumps(error_dict, ensure_ascii=False)


def create_custom_plot(
    ctx: Context,
    plot_code: str,
    plot_type: str = "matplotlib",
    timeout: int = 60,
) -> list[TextContent | ImageContent] | str:
    """Create a custom plot using Matplotlib or PyVista in the persistent Python session.

    Parameters
    ----------
    ctx : Context
        MCP context containing server session and application context.
    plot_code : str
        Python code for creating the plot. You should use ``matplotlib.pyplot`` or PyVista.
        For Matplotlib, the code should create the figure/plot but NOT call ``plt.show()``.
        Use the ``save_matplotlib_plot() or ``save_plot()`` helper functions to return the plot.
    plot_type : str, default: "matplotlib"
        Type of plot. Options are ``"matplotlib"`` or ``"pyvista"``.
    timeout : int, default: 60
        Maximum time in seconds for plot generation.

    Returns
    -------
    list[TextContent | ImageContent]
        List containing:
        - TextContent with the plot creation status message
        - ImageContent with the base64-encoded image data if successful
        or a JSON string with error details if failed.

    Examples
    --------
    Create a custom Matplotlib line plot:

    .. code:: python

        plot_code = '''
        import matplotlib.pyplot as plt
        import numpy as np

        # Extract data from MAPDL
        displacements = mapdl.get_array("NODE", item1="U", it1num="Y")

        # Create custom plot
        plt.figure(figsize=(10, 6))
        plt.plot(displacements)
        plt.xlabel("Node Number")
        plt.ylabel("Displacement (m)")
        plt.title("Custom Displacement Plot")
        plt.grid(True)
        # Save and return
        result = save_matplotlib_plot(dpi=150)
        print(result)
        '''

        create_custom_plot(ctx, plot_code, plot_type="matplotlib")

    """
    session = ctx.request_context.lifespan_context.python_session

    if session is None:
        return [
            TextContent(
                type="text",
                text="No Python session available. The persistent Python session was not initialized.",  # noqa: E501
            )
        ]

    try:
        logger.info(f"Creating custom {plot_type} plot in persistent session.")

        # Sanitize the plot code to remove problematic Unicode characters
        # This prevents encoding issues on Windows systems with limited charsets
        sanitized_plot_code = _sanitize_output(plot_code)

        # Execute the plot code
        result = session.execute(sanitized_plot_code, timeout=timeout)

        # Parse the result
        if isinstance(result, dict):
            stdout = _sanitize_output(result.get("stdout", ""))
            stderr = _sanitize_output(result.get("stderr", ""))

            if result.get("success"):
                # Try to extract plot data from stdout
                # The helper functions return data URI format:
                # "data:image/png;base64,<base64_string>"
                plot_data = stdout.strip()

                # Check if the output contains a base64 data URI
                if "data:image/png;base64," in plot_data:
                    # Extract the base64 part
                    base64_data = plot_data.split("data:image/png;base64,")[1].strip()

                    return [
                        TextContent(
                            type="text",
                            text=f"Custom {plot_type} plot created successfully",
                        ),
                        ImageContent(type="image", data=base64_data, mimeType="image/png"),
                    ]
                elif plot_data.startswith("Plot saved to"):
                    # File path returned
                    return [
                        TextContent(
                            type="text",
                            text=f"Custom {plot_type} plot created successfully\n{plot_data}",
                        )
                    ]
                else:
                    # Unexpected output format
                    return [
                        TextContent(
                            type="text",
                            text=f"Plot created but unexpected output format:\n{stdout}",
                        )
                    ]
            else:
                error_msg = result.get("error", "Unknown error occurred.")
                error_msg = _sanitize_output(error_msg)
                return [
                    TextContent(
                        type="text",
                        text=f"Error creating custom {plot_type} plot: {error_msg}\nStdout: {stdout}\nStderr: {stderr}",  # noqa: E501
                    )
                ]
        else:
            # Fallback if result is not a dict
            return [
                TextContent(
                    type="text",
                    text=f"Unexpected result format: {_sanitize_output(str(result)) if result else 'No result'}",  # noqa: E501
                )
            ]

    except TimeoutError:
        error_msg = f"Plot creation timed out after {timeout} seconds."
        logger.error(error_msg)
        return [TextContent(type="text", text=error_msg)]

    except Exception as e:
        error_msg = f"Error creating custom plot: {str(e)}"
        logger.error(error_msg)
        return [TextContent(type="text", text=error_msg)]


__all__ = [
    "execute_python_code",
    "create_custom_plot",
]
