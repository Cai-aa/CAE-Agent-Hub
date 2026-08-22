.. _ref_implementing_a_tool:

Implement a custom tool
=======================

Learn how to implement a custom MCP tool for PyMAPDL-MCP.

Tool overview
-------------

A tool is a function that performs a specific task using MAPDL.
Tools typically perform as follows:

- Take structured input parameters.
- Perform some operation (usually involving MAPDL).
- Return structured output.

Tools are discovered by MCP clients and can be called with appropriate parameters.

Tool anatomy
------------

Here's a minimal tool structure:

.. code-block:: python

    from ansys.mapdl.mcp.contexts import Context

    def my_analysis_tool(ctx: Context, model_name: str, load_magnitude: float) -> str:
        """
        Run a simple FEA analysis.

        Parameters
        ----------
        ctx : Context
            Tool context with access to an MAPDL instance.
        model_name : str
            Name/description of the model.
        load_magnitude : float
            Load magnitude in Newtons.

        Returns
        -------
        str
            Analysis result summary.
        """
        # Get the MAPDL instance from context
        mapdl = ctx.application_context.mapdl

        if mapdl is None:
            return "Error: No MAPDL instance connected."

        try:
            # Perform the analysis
            mapdl.prep7()
            mapdl.et(1, 'SOLID185')
            # ... more MAPDL commands ...
            mapdl.run()

            # Extract results
            result = mapdl.post_processing.stress()

            return f"Analysis '{model_name}' completed. Max stress: {result:.2f} MPa"

        except Exception as e:
            return f"Error during analysis: {str(e)}"

Key components
~~~~~~~~~~~~~~

- Documentation string: Description of what the tool does.
- Context parameter: Access to MAPDL and the app state.
- Input parameters: Specific parameters for this tool.
- Error handling: Graceful handling of errors.
- Return value: Status message or results.

Tool registration
-----------------

Register tools in the MCP server's tool registry. Each registration includes:

- Function: The Python function to call.
- Name: Human-readable name.
- Description: What the tool does.
- Input schema: Parameter definitions and types.

Best practices
--------------

- Clear documentation: Write comprehensive docstrings explaining parameters, return values, and exceptions.

- Type hints: Use Python type hints for all parameters and return values.

- Error handling: Handle errors gracefully and return informative error messages.

- Input validation: Validate input parameters before using them.

- Status feedback: Provide feedback on progress for long-running operations.

- Context management: Always check whether MAPDL is connected before using it.

Complete analysis tool example
------------------------------

Here's a more complete example of a tool:

.. code-block:: python

    from ansys.mapdl.mcp.contexts import Context
    from typing import Optional

    def cantilever_beam_analysis(
        ctx: Context,
        length: float,
        width: float,
        height: float,
        material_e: float = 2.1e11,
        material_nu: float = 0.3,
        tip_load: float = 1000.0,
    ) -> str:
        """
        Analyze a cantilever beam under point load.

        Parameters
        ----------
        ctx : Context
            Tool execution context.
        length : float
            Beam length in meters.
        width : float
            Beam width in meters.
        height : float
            Beam height in meters.
        material_e : float, default: 2.1e11
            Young's modulus in Pa. The default, ``2.1e11``, corresponds to steel.
        material_nu : float, default: 0.3
            Poisson's ratio.
        tip_load : float, default: 1000.0
            Tip load in Newtons.

        Returns
        -------
        str
            Analysis results including maximum deflection and stress.
        """
        mapdl = ctx.application_context.mapdl

        if mapdl is None:
            return "Error: MAPDL is not connected."

        # Validate inputs
        if length <= 0 or width <= 0 or height <= 0:
            return "Error: Dimensions must be positive."

        if material_e <= 0 or material_nu < 0 or material_nu > 0.5:
            return "Error: Material properties are invalid."

        try:
            # Clear previous model
            mapdl.clear()
            mapdl.prep7()

            # Define material
            mapdl.mp('ex', 1, material_e)
            mapdl.mp('nuxy', 1, material_nu)

            # Define element type
            mapdl.et(1, 'SOLID185')

            # Create beam geometry
            mapdl.block(0, length, 0, width, 0, height)

            # Mesh
            mapdl.esize(length / 10)
            mapdl.vmesh('ALL')

            # Boundary conditions
            mapdl.nsel('s', 'loc', 'x', 0)
            mapdl.d('all', 'all', 0)

            # Apply load
            mapdl.nsel('s', 'loc', 'x', length)
            mapdl.nsel('a', 'loc', 'y', width / 2)
            mapdl.nsel('a', 'loc', 'z', height / 2)
            mapdl.f('all', 'fz', -tip_load)

            # Solve
            mapdl.run()
            mapdl.finish()

            # Extract results
            mapdl.post1()
            max_deflection = mapdl.post_processing.get_max_deflection()
            max_stress = mapdl.post_processing.get_max_stress()

            return (
                f"Cantilever analysis complete:\\n"
                f"  Beam: {length}m × {width}m × {height}m\\n"
                f"  Load: {tip_load}N\\n"
                f"  Max deflection: {max_deflection:.4e} m\\n"
                f"  Max stress: {max_stress:.2e} Pa"
            )

        except Exception as e:
            return f"Analysis failed: {str(e)}"

Tool testing
------------

When developing a tool, test it in these ways:

- Unit testing: Test with mock contexts.
- Integration testing: Test with actual MAPDL.
- Error cases: Test error conditions and invalid inputs.
- Performance: Verify that execution time is acceptable.

Tool debugging
--------------

Use these techniques to debug your tools:

- Logging: Use the ``ctx`` logger to log debug information.
- Status messages: Return detailed status messages.
- Comments: Add MAPDL comments to track execution.
- Screenshots: Take screenshots at key points.

Advanced topics
---------------

- Async tools: For long-running operations, consider async implementations.
- Streaming results: For tools producing large outputs, stream results.
- Caching: Cache expensive computations when appropriate.
- Tool composition: Combine multiple tools into workflows.

See also
--------

- Source code in the ``src/ansys/mapdl/mcp/tools.py`` file.
- Context class documentation in :doc:`../api/ansys/mapdl/mcp/server/PyMAPDLAppContext` and
    :doc:`../api/ansys/mapdl/mcp/server/SessionContext`.
- :doc:`../user_guide/best_practices` for general recommendations.
