.. _ref_implementing_a_tool:

Implement a custom tool
=======================

Learn how to implement a custom MCP tool for PyMechanical-MCP.

Tool overview
-------------

A tool is a Python function decorated with ``@app.tool(...)`` that performs a specific task
using an Ansys Mechanical instance. Tools typically:

- Accept structured input parameters.
- Perform an operation (usually by calling ``run_python_script`` against the Mechanical API).
- Return structured output as a JSON string or plain text.

MCP clients discover registered tools and call them with the appropriate parameters.

Tool anatomy
------------

Here is a minimal tool structure:

.. code-block:: python

   from mcp.server.fastmcp import Context
   from ansys.mechanical.mcp import app
   from ansys.mechanical.mcp.tools import REQUIRES_MECHANICAL_TAG

   @app.tool(tags={REQUIRES_MECHANICAL_TAG})
   def my_analysis_tool(ctx: Context, model_name: str, load_magnitude: float) -> str:
       """Run a simple structural analysis.

       Parameters
       ----------
       ctx : Context
           MCP context with access to the Mechanical instance.
       model_name : str
           Name or description of the model.
       load_magnitude : float
           Load magnitude in Newtons.

       Returns
       -------
       str
           Analysis result summary.
       """
       mechanical = ctx.request_context.lifespan_context.mechanical

       if mechanical is None:
           return "No Mechanical connection available. Use connect_to_mechanical first."

       try:
           result = mechanical.run_python_script(f"str({load_magnitude})")
           return f"Analysis '{model_name}' completed. Result: {result}"
       except Exception as e:
           return f"Error during analysis: {e}"

Key components
~~~~~~~~~~~~~~

- **``REQUIRES_MECHANICAL_TAG``**: Tags the tool so it is hidden until a Mechanical session is active.
- **``ctx``**: Provides access to the live Mechanical instance via
  ``ctx.request_context.lifespan_context.mechanical``.
- **Input parameters**: Typed Python parameters become the MCP tool input schema automatically.
- **Error handling**: Return a plain string error message rather than raising exceptions.
- **Return value**: JSON string or plain text received by MCP clients as the tool result.

Connection-gating
-----------------

Tools tagged with ``REQUIRES_MECHANICAL_TAG`` remain hidden until ``launch_mechanical`` or
``connect_to_mechanical`` succeeds. Always-available tools (such as ``check_mechanical_status``)
must not carry this tag.

Add any always-available tool name to the ``ALWAYS_AVAILABLE_TOOLS`` allowlist in
``tests/test_tools.py::TestRequiresMechanicalVisibility::test_no_tool_surface_drift``.

Registering the tool
--------------------

Once you write the function:

1. Place it in ``src/ansys/mechanical/mcp/tools.py``.
2. Add the tool name to ``src/ansys/mechanical/mcp/toolsets.py`` under the appropriate tool group.
3. Document the tool in :doc:`/user_guide/tools_and_capabilities`.
4. Run ``pytest -m "not integration"`` to confirm the surface-drift test still passes.

Best practices
--------------

- Write a NumPy-style docstring for every tool.
- Use type hints for all parameters and the return value.
- Validate inputs at the function boundary and return a descriptive error string.
- Use ``json.dumps`` to safely escape file paths passed into Mechanical scripts.
- Keep tools focused: one engineering action per tool.

Tool testing
------------

Test your tool in the following ways:

- **Unit testing**: Use mock contexts (``MagicMock``) to test tool logic without a live Mechanical instance.
- **Integration testing**: Run with an actual Mechanical connection using ``pytest -m integration``.
- **Error cases**: Test invalid inputs, missing connections, and edge conditions.
- **Surface drift check**: Run ``pytest tests/test_tools.py -k test_no_tool_surface_drift`` after
  adding or removing tools.

Tool debugging
--------------

Use these techniques when troubleshooting a tool:

- **Logging**: Use ``logger = get_logger(__name__)`` from ``ansys.common.mcp`` to emit structured log messages.
- **Status messages**: Return detailed status strings at intermediate steps.
- **Script tracing**: Add ``ExtAPI.Log.WriteMessage()`` calls inside Mechanical scripts.
- **Screenshots**: Call ``screenshot`` after key model-setup steps to verify the state visually.

Advanced topics
---------------

- **Tool composition**: Combine multiple low-level script calls into a higher-level orchestration tool.
- **Streaming results**: For tools producing large tabular outputs, consider chunking the return string.
- **Persistent session**: Use ``run_python_code`` to share state between tool calls in the persistent
  Python session rather than re-importing data on each call.

See also
--------

- Source code: ``src/ansys/mechanical/mcp/tools.py``
- Tool catalog: ``src/ansys/mechanical/mcp/toolsets.py``
- :doc:`/user_guide/tools_and_capabilities`
- :doc:`/user_guide/best_practices`
