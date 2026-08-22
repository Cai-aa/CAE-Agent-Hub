Quick start
===========

Launch PyMechanical-MCP
-----------------------

Launch PyMechanical-MCP with the default STDIO transport:

.. code-block:: bash

   ansys-mechanical-mcp

To run the server over streamable HTTP:

.. code-block:: bash

   ansys-mechanical-mcp --transport http --http-host 127.0.0.1 --http-port 8080

Connect to your IDE or client
-----------------------------

PyMechanical-MCP works with multiple MCP-compatible clients. For setup information,
see :doc:`ide_configuration`.

- Claude Code
- Visual Studio Code with Copilot
- Claude Desktop
- Other MCP-compatible clients

Follow the basic workflow
-------------------------

There are three common ways to begin once the server is running.

**Option 1: Launch a new Mechanical session (recommended).**

Ask your assistant to call ``launch_mechanical``.

By default, ``launch_mechanical`` prefers a visible GUI session. If the MCP
client supports elicitation, it can ask whether to launch in GUI or batch mode.
Use ``batch=true`` to force a background launch.

**Option 2: Connect to an existing Mechanical session.**

Ask your assistant to call ``connect_to_mechanical`` with the host and port.

The existing Mechanical session must already be running with gRPC enabled. For
example, on Windows PowerShell:

.. code-block:: powershell

   & "C:\Program Files\ANSYS Inc\v261\aisol\bin\winx64\AnsysWBU.exe" -DSApplet -AppModeMech -grpc 50053

Then connect with ``ip=127.0.0.1`` and ``port=50053``.

**Option 3: Connect on startup.**

Use ``--connect-on-startup`` when launching the MCP server:

.. code-block:: bash

   ansys-mechanical-mcp --connect-on-startup --ip 127.0.0.1 --port 10000

.. warning::
   When you use ``--connect-on-startup``, PyMechanical-MCP locks the connection and
   disables the ``launch_mechanical``, ``connect_to_mechanical``, and
   ``disconnect_from_mechanical`` tools.

Tool availability before and after connecting
---------------------------------------------

Before connection, use offline-capable tools such as:

- ``check_mechanical_installed``
- ``check_mechanical_status``
- ``list_mechanical_instances``
- ``get_guidelines_for``

After you connect, session-dependent tools become available for scripting,
file transfer, solving, and result export.

First workflow checklist
------------------------

1. ``check_mechanical_status``
2. ``launch_mechanical`` or ``connect_to_mechanical``
3. ``upload_file`` (geometry or script, as needed)
4. ``run_python_script`` (model setup)
5. ``solve_analysis``
6. ``get_model_info``, ``export_results``, and/or ``screenshot``

Next steps
----------

- See :doc:`../user_guide/tools_and_capabilities` for the complete tool reference.
- See :doc:`../user_guide/best_practices` for workflow recommendations.
- See :doc:`../user_guide/configuration` for startup flags and environment settings.
