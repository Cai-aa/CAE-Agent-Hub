Quick start
===========

Launch PyFluent-MCP
-------------------

The simplest way to start the MCP server is the ``ansys-fluent-mcp`` console script or
the ``ansys.fluent.mcp`` module:

.. code-block:: bash

   ansys-fluent-mcp

   # equivalent
   python -m ansys.fluent.mcp

It launches the server over STDIO (the default MCP transport) and waits for connections
from MCP clients.

To run over streamable HTTP instead:

.. code-block:: bash

   ansys-fluent-mcp --transport http --host 127.0.0.1 --port 8000

Connect to your IDE or client
-----------------------------

PyFluent-MCP works with multiple MCP-compatible clients. For setup information, see
:doc:`ide_configuration`.

- Claude Code (recommended for AI-assisted development)
- Visual Studio Code with Copilot (for Visual Studio Code users)
- Claude Desktop (macOS app)
- Cursor and other MCP-compatible clients

Follow the basic workflow
-------------------------

Connect to Fluent
~~~~~~~~~~~~~~~~~

There are two ways to connect to Fluent once the MCP server is running.

**Option 1: Launch a new Fluent session (recommended).**

Ask your AI assistant to use the ``connect`` tool:

*"Connect to Fluent and launch a new solver session."*

This starts a new Fluent process through PyFluent and connects to it automatically.

**Option 2: Attach to an existing instance.**

Ask your AI assistant to use the ``connect`` tool with IP and port:

*"Connect to Fluent on localhost port 18500."*

This option is useful when Fluent is already running on a remote machine.

Inspect, generate, and execute
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Once Fluent is connected, the recommended loop for most setup tasks is:

1. **Discover**: Use ``find_api``, ``get_state``, or ``list_named_objects`` to inspect
   the live settings tree.
2. **Validate**: Use ``validate_code`` to pre-check Python snippets against the AST sandbox.
3. **Execute**: Use ``run_code`` to apply the change to the live solver.
4. **Verify**: Use ``summarize_setup`` or ``simulation_report`` to confirm the result.

Use offline-only tools
~~~~~~~~~~~~~~~~~~~~~~

You can use several tools **without** a live Fluent session:

- ``find_api`` searches the bundled settings schema.
- ``get_help`` returns per-path help text.
- ``validate_code`` performs an AST pre-check only.

Consider example use cases
--------------------------

- Set up boundary conditions and solver settings with AI guidance.
- Inspect mesh quality and cell counts on a loaded case.
- Compare two case files to see what changed between versions.
- Generate and debug PyFluent settings-API scripts interactively.

Next steps
----------

- For an overview of available tools, see :doc:`../user_guide/overview`.
- For additional API reference, see :doc:`../user_guide/tools_and_capabilities`.
- For practical examples, browse :doc:`../examples/index`.
- For configuration options, see :doc:`../user_guide/configuration`.
