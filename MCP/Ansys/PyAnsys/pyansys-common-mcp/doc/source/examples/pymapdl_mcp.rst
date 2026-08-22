.. _ref_pymapdl_mcp:

PyMAPDL-MCP
===========

Explore the `PyMAPDL-MCP <pymapdl_mcp_>`_ repository for a production-ready, real-world implementation. It provides a complete MCP server for PyMAPDL, offering these benefits:

- **Fully integrates with MAPDL**: Launch, control, and interact with MAPDL.
- **Provides comprehensive tools**: Create geometry, mesh, solve, and postprocess.
- **Offers advanced features**: Manage sessions, plot, and extract results.
- **Follows production patterns**: Handle errors, log, and test.

Key functions
-------------

- ``launch_mapdl_session()``: Start a MAPDL instance with configurable parameters.
- ``run_mapdl_commands()``: Execute APDL commands.
- ``run_python_code()``: Execute Python code in a persistent session.
- ``screenshot()``: Capture and return MAPDL graphics.

Usage with Claude Desktop
-------------------------

.. code-block:: json

   {
     "pymapdl-mcp": {
       "pymapdl": {
         "command": "python",
         "args": ["-m", "ansys.mapdl.mcp"]
       }
     }
   }
