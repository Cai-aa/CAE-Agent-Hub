.. _ref_installation:

Installation
============

You can run PyAEDT-MCP in two modes:

- Start the MCP server and let it launch AEDT later through tools.
- Start or reuse an AEDT gRPC session, and then connect PyAEDT-MCP to it.

Check prerequisites
-------------------

- Python 3.12 or later
- AEDT 2022 R2 or later for gRPC workflows
- A local AEDT installation or a reachable remote AEDT endpoint

Run PyAEDT-MCP with uvx
-----------------------

Use uvx when you want to run PyAEDT-MCP without cloning the repository:

.. code-block:: bash

   uvx --from git+https://github.com/ansys/pyaedt-mcp.git ansys-aedt-mcp

Install PyAEDT-MCP with ``pip``
-------------------------------

Use ``pip`` when you want to install PyAEDT-MCP in your current Python
environment:

.. code-block:: bash

   pip install git+https://github.com/ansys/pyaedt-mcp.git

Install PyAEDT-MCP from source
------------------------------

Use this option when you want to install from a local clone of the
PyAEDT-MCP repository.

.. code-block:: bash

   git clone https://github.com/ansys/pyaedt-mcp
   cd pyaedt-mcp
   pip install .

If you plan to contribute, follow the development setup in
:ref:`ref_contributing` for an editable installation, development dependencies,
tests, and linters.

Start AEDT in gRPC mode
-----------------------

If you want to connect to an existing AEDT session, start AEDT in gRPC mode.
You can start it from the command line or from the AEDT GUI. PyAEDT supports
gRPC in AEDT 2022 R2 and later.

.. code-block:: bash

   "C:\Program Files\ANSYS Inc\v261\AnsysEM\ansysedt.exe" -grpcsrv 50051

Start PyAEDT-MCP
----------------

PyAEDT-MCP uses STDIO by default.

.. code-block:: bash

   ansys-aedt-mcp

You can use these common options:

.. code-block:: bash

   ansys-aedt-mcp --connect --machine localhost --port 50051
   ansys-aedt-mcp --transport http --http-host 127.0.0.1 --http-port 8080
   ansys-aedt-mcp --include-context
   ansys-aedt-mcp --dynamic-tool-discovery

After PyAEDT-MCP starts, connect to it with any MCP-compatible client, such as
Claude Code, Copilot CLI, Codex, or Cursor. For more information, see
:doc:`ide_configuration`.

Review important CLI options
----------------------------

.. list-table::
   :header-rows: 1

   * - Option
     - Purpose
   * - ``--transport {stdio,http}``
     - Choose how PyAEDT-MCP connects to the client.
   * - ``--machine`` / ``--port``
     - Point the startup connection to an AEDT gRPC endpoint.
   * - ``--connect``
     - Connect to AEDT during server startup instead of waiting for a tool call.
   * - ``--include-context``
     - Register optional guidance tools for AEDT and PyAEDT workflows.
   * - ``--dynamic-tool-discovery``
     - Hide AEDT-only tools until ``launch_aedt`` or ``connect_to_aedt`` succeeds.
   * - ``--http-host`` / ``--http-port``
     - Set the HTTP transport endpoint.

Follow a typical first workflow
-------------------------------

After your client connects to PyAEDT-MCP, follow this typical workflow:

1. Call ``check_aedt_installed``.
2. Call ``check_aedt_status``.
3. Use ``launch_aedt`` or ``connect_to_aedt``.
4. Open a project or create a design.
5. Use dedicated tools or ``run_python_code`` for the rest of the workflow.

.. note::

   If the tool surface does not support an operation, the AI agent can generate
   a Python snippet and run it with ``run_python_code`` in the persistent
   PyAEDT session.

For recommended usage patterns, see :doc:`../user_guide/best_practices`.
To review the available tools, see :doc:`../user_guide/tools_and_capabilities`.
