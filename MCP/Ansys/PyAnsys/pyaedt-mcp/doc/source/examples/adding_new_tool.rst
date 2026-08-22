.. _ref_adding_new_tool:

Add a new tool
==============

This example shows how to add a new ``@app.tool(...)`` safely and make it visible
at the right stages of an MCP session.

Where to implement
------------------

#. Add the tool implementation to ``src/ansys/aedt/mcp/tools.py``.
#. Add the tool to the appropriate group in ``src/ansys/aedt/mcp/toolsets.py``.
#. Document the tool behavior in :doc:`../user_guide/tools_and_capabilities`.

Decorator options and tags
--------------------------

Use FastMCP's ``@app.tool(...)`` decorator with these key options:

- ``tags``: Set of tags used for grouping and runtime filtering.
- ``timeout``: Maximum execution time for the tool.

Use these common tags in this repository:

- ``REQUIRES_AEDT_TAG``: Mark tools that require an active AEDT connection.
- ``aedt_tools``: Group core AEDT-facing tools.
- ``locked_connection``: Mark tools that are disabled when startup uses
  ``--connect`` and locks the connection for the server lifetime.

Use these timeout tiers in this repository:

- Quick: 30 seconds
- Medium: 120 seconds
- Long: 600 seconds

Example: AEDT-dependent tool
----------------------------

Use ``REQUIRES_AEDT_TAG`` when the tool cannot run before connection:

.. code-block:: python

   from fastmcp.server import Context
   from ansys.aedt.mcp import app
   from ansys.aedt.mcp.tools import REQUIRES_AEDT_TAG

   @app.tool(tags={"aedt_tools", REQUIRES_AEDT_TAG}, timeout=120)
   def my_new_tool(ctx: Context) -> str:
       return "ok"

Example: Pre-connection tool
----------------------------

Do not use ``REQUIRES_AEDT_TAG`` for tools that work before connecting:

.. code-block:: python

   from fastmcp.server import Context
   from ansys.aedt.mcp import app

   @app.tool(tags={"aedt_tools"}, timeout=30)
   def check_local_environment(ctx: Context) -> str:
       return "environment ready"

Runtime flags and their effect
------------------------------

Server startup flags affect tool visibility and behavior:

- ``--dynamic-tool-discovery``: Hide ``REQUIRES_AEDT_TAG`` tools until AEDT
  connects.
- ``--connect``: Connect at startup and lock the session. In this mode,
  ``launch_aedt``, ``connect_to_aedt``, and ``disconnect_from_aedt`` are
  disabled for the life of the process.
- ``--include-context``: Register optional context tools such as
  ``get_guidelines_for``.

Validation checklist
--------------------

#. Add or update tests in ``tests/test_tools.py``.
#. Ensure the tool appears in a toolset definition (validated by
   ``tests/test_toolsets.py``).
#. Run tests locally.
#. Verify that code coverage remains greater than 80%.
#. Update user-facing documentation.
