Quick start
===========

Launch PyCFX-MCP
----------------

Use the ``ansys-cfx-mcp`` console script to quickly start PyCFX-MCP:

.. code-block:: bash

   ansys-cfx-mcp

This script starts PyCFX-MCP over STDIO, the default MCP transport, and waits
for MCP client connections.

To run over Streamable HTTP instead:

.. code-block:: bash

   ansys-cfx-mcp --transport http --host 127.0.0.1 --port 8000

Connect to your IDE or client
-----------------------------

PyCFX-MCP works with multiple MCP-compatible clients. For setup information,
see :doc:`ide_configuration`.

- Use Claude Code for AI-assisted development.
- Use Visual Studio Code with Copilot.
- Use Claude Desktop.
- Use Cursor or another MCP-compatible client.

Follow the basic workflow
-------------------------

Connect to CFX
~~~~~~~~~~~~~~

Use one of these methods to connect to CFX after PyCFX-MCP starts.

**Option 1: Start a local CFX app.**

Ask your AI assistant to use the ``connect`` tool:

*"Connect to CFX and start a local PyCFX backend."*

This prepares the PyCFX backend so routed workflow actions can start or connect
to CFX-Pre, CFX-Solver, and CFD-Post sessions as needed.

**Option 2: Attach to an existing PyCFX server.**

Ask your AI assistant to use the ``connect`` tool with an IP address, port,
password, or server information file:

*"Connect to CFX on localhost port 18500."*

This option is useful when a PyCFX service is already running on another
machine or was started outside the MCP client.

Inspect, route, and execute
~~~~~~~~~~~~~~~~~~~~~~~~~~~

After CFX connects, use this loop for most setup and analysis tasks:

1. **Discover**: Use ``session_status`` and ``cfx_model_context`` to inspect
   the active backend, model names, API paths, and state snippets.
2. **Route**: Use ``cfx_workflow`` for supported lifecycle actions such as
   importing meshes, writing solver input, starting a solver, waiting for
   completion, and opening CFD-Post results.
3. **Validate**: Use ``validate_code`` to pre-check reviewed snippets against
   the AST sandbox.
4. **Execute**: Use ``run_code`` to run reviewed snippets against the active CFX
   backend.

Use offline-capable tools
~~~~~~~~~~~~~~~~~~~~~~~~~

Use these tools before you connect to a live CFX app:

- ``session_status``: Reports that no backend is connected and lists available
  tools.
- ``validate_code``: Performs an AST pre-check without mutating a CFX session.

Consider example use cases
--------------------------

- Start CFX-Pre and import a mesh with AI guidance.
- Write a solver input file and run a steady-state solver workflow.
- Locate the generated results file and open it in CFD-Post.
- Validate and run reviewed PyCFX snippets for custom inspection or edits.

Next steps
----------

- For an overview of available tools, see :doc:`../user_guide/overview`.
- For additional tool details, see :doc:`../user_guide/tools_and_capabilities`.
- For practical examples, browse :doc:`../examples/index`.
- For configuration options, see :doc:`../user_guide/configuration`.
