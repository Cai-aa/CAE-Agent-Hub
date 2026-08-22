.. _ref_ide_configuration:

IDE and client configuration
=============================

PyAEDT-MCP works with any MCP-compatible client. This page covers the most
common ones: Claude Code, Visual Studio Code, and Claude Desktop.

Claude Code
-----------

Claude Code is Anthropic's AI-powered code editor with built-in MCP support.

Configure for a specific project (recommended)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Configure PyAEDT-MCP for a specific project:

**Linux (bash):**

.. code-block:: bash

   cd my-project
   claude mcp add --transport stdio pyaedt-mcp -- \
     uvx --from git+https://github.com/ansys/pyaedt-mcp ansys-aedt-mcp

On Windows PowerShell, run:

.. code-block:: powershell

   cd my-project
   claude mcp add --transport stdio pyaedt-mcp -- `
     uvx --from git+https://github.com/ansys/pyaedt-mcp ansys-aedt-mcp

Advantages:

- Scoped to the project, shareable via version control.
- Supports per-project CLI flags (for example ``--include-context``).

Configure globally
~~~~~~~~~~~~~~~~~~

Configure PyAEDT-MCP for all your Claude Code projects:

**Linux (bash):**

.. code-block:: bash

   claude mcp add --transport stdio --scope user pyaedt-mcp -- \
     uvx --from git+https://github.com/ansys/pyaedt-mcp ansys-aedt-mcp

On Windows PowerShell, run:

.. code-block:: powershell

   claude mcp add --transport stdio --scope user pyaedt-mcp -- `
     uvx --from git+https://github.com/ansys/pyaedt-mcp ansys-aedt-mcp

Advantages:

- Available in all Claude Code projects without per-project configuration.

See `Claude Code MCP installation
<https://code.claude.com/docs/en/mcp#installing-mcp-servers>`_ for details.

Visual Studio Code
------------------

Visual Studio Code integrates MCP servers through the Copilot extension.

Start from GitHub (recommended)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Add this to the ``.vscode/mcp.json`` file in your project directory:

.. code-block:: json

   {
     "servers": {
       "pyaedt-mcp": {
         "type": "stdio",
         "command": "uvx",
         "args": [
           "--index-strategy", "unsafe-best-match",
           "--from", "git+https://github.com/ansys/pyaedt-mcp.git",
           "ansys-aedt-mcp"
         ]
       }
     }
   }

If the ``.vscode/mcp.json`` file does not exist, create it.

Set up for local development
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Use this configuration when working from a local clone of the repository:

.. code-block:: json

   {
     "servers": {
       "pyaedt-mcp": {
         "type": "stdio",
         "command": ".venv/Scripts/python",
         "args": ["-m", "ansys.aedt.mcp"],
         "env": {
           "FASTMCP_LOG_LEVEL": "DEBUG"
         }
       }
     }
   }

.. note::
  On Linux or macOS, use ``bin/python`` instead of ``Scripts/python``.

Use uv as an alternative
~~~~~~~~~~~~~~~~~~~~~~~~

If you prefer, you can use uv as your Python package and project manager:

.. code-block:: json

   {
     "servers": {
       "pyaedt-mcp": {
         "type": "stdio",
         "command": "uv",
         "args": ["run", "python", "-m", "ansys.aedt.mcp"]
       }
     }
   }

Configure HTTP transport
~~~~~~~~~~~~~~~~~~~~~~~~

If you start PyAEDT-MCP with ``--transport http``, use this client configuration:

.. code-block:: json

   {
     "servers": {
       "pyaedt-mcp": {
         "type": "http",
         "url": "http://127.0.0.1:8080"
       }
     }
   }

Start PyAEDT-MCP before you connect. This command works in any terminal:

.. code-block:: console

   ansys-aedt-mcp --transport http --http-host 127.0.0.1 --http-port 8080

Use Docker endpoint
~~~~~~~~~~~~~~~~~~~

If you start PyAEDT-MCP with Docker Compose, use the default HTTP endpoint:

.. code-block:: json

   {
     "servers": {
       "pyaedt-mcp": {
         "type": "http",
         "url": "http://localhost:8080"
       }
     }
   }

For more information, see :doc:`../user_guide/docker`.

Enable MCP in Visual Studio Code
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. Open VS Code settings (``Ctrl+,`` or ``Cmd+,``).
2. Search for ``MCP``.
3. Enable the settings that allow Copilot to use MCP servers.

   For more information, see `Add and manage MCP servers in VS Code
   <https://code.visualstudio.com/docs/agents/reference/mcp-configuration>`_
   in the Visual Studio Code documentation.

4. Restart Visual Studio Code.

Claude Desktop
--------------

Claude Desktop is Anthropic’s macOS desktop app with full MCP support.
Edit the ``~/Library/Application Support/Claude/claude_desktop_config.json``
file on macOS or the equivalent path on Windows:

.. code-block:: json

   {
     "mcpServers": {
       "pyaedt-mcp": {
         "command": "uvx",
         "args": [
           "--from", "git+https://github.com/ansys/pyaedt-mcp.git",
           "ansys-aedt-mcp"
         ],
        "description": "MCP server for Ansys AEDT through PyAEDT",
        "version": "0.0.1",
        "language": "python"
       }
     }
   }

Claude Code versus Visual Studio Code
-------------------------------------

.. list-table::
   :header-rows: 1

   * - Feature
     - Claude Code
     - Visual Studio Code
   * - Configuration method
     - CLI command (``claude mcp add``)
     - JSON file (``.vscode/mcp.json``)
   * - Setup level
     - Project or global
     - Project-level only
   * - Transport support
     - STDIO (default)
     - STDIO or HTTP
   * - Team sharing
     - With project config files
     - With ``.vscode/mcp.json`` in the repository
   * - Learning curve
     - Low (CLI-based)
     - Medium (JSON configuration)

Advanced configuration
----------------------

Auto-connect to AEDT on startup
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Pass ``--connect`` to have the server connect to AEDT during initialization.
Use ``--machine`` and ``--port`` to target a specific gRPC endpoint:

**Visual Studio Code**

Edit the ``.vscode/mcp.json`` file:

.. code-block:: json

   {
     "servers": {
       "pyaedt-mcp": {
         "type": "stdio",
         "command": "uvx",
         "args": [
           "--index-strategy", "unsafe-best-match",
           "--from", "git+https://github.com/ansys/pyaedt-mcp.git",
           "ansys-aedt-mcp",
           "--connect",
           "--machine", "192.168.1.100",
           "--port", "50051"
         ]
       }
     }
   }

**Claude Code:**

**Linux (bash):**

.. code-block:: bash

   claude mcp add --transport stdio pyaedt-mcp -- \
     uvx --from git+https://github.com/ansys/pyaedt-mcp ansys-aedt-mcp \
     --connect --machine 192.168.1.100 --port 50051

**Windows PowerShell:**

.. code-block:: powershell

   claude mcp add --transport stdio pyaedt-mcp -- `
     uvx --from git+https://github.com/ansys/pyaedt-mcp ansys-aedt-mcp `
     --connect --machine 192.168.1.100 --port 50051

.. warning::
   When ``--connect`` is used, the server locks the connection. The
   ``launch_aedt``, ``connect_to_aedt``, and ``disconnect_from_aedt`` tools
   are disabled for the lifetime of the server process.

Enable optional context tools
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``--include-context`` flag registers ``get_guidelines_for``, which provides
inline AEDT and PyAEDT workflow guidance to the AI assistant.

.. code-block:: json

   {
     "servers": {
       "pyaedt-mcp": {
         "type": "stdio",
         "command": "uvx",
         "args": [
           "--index-strategy", "unsafe-best-match",
           "--from", "git+https://github.com/ansys/pyaedt-mcp.git",
           "ansys-aedt-mcp",
           "--include-context"
         ]
       }
     }
   }

Enable dynamic tool discovery
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Use ``--dynamic-tool-discovery`` to hide AEDT-only tools until a session is
established. This keeps the AI assistant's context small before connection.

.. code-block:: console

   ansys-aedt-mcp --dynamic-tool-discovery

Enable debug logging
~~~~~~~~~~~~~~~~~~~~~

Set the ``FASTMCP_LOG_LEVEL`` environment variable to ``DEBUG``:

**Visual Studio Code**

Edit the ``.vscode/mcp.json`` file:

.. code-block:: json

   {
     "servers": {
       "pyaedt-mcp": {
         "type": "stdio",
         "command": "uvx",
         "args": [
           "--index-strategy", "unsafe-best-match",
           "--from", "git+https://github.com/ansys/pyaedt-mcp.git",
           "ansys-aedt-mcp"
         ],
         "env": {
           "FASTMCP_LOG_LEVEL": "DEBUG"
         }
       }
     }
   }

**Linux (bash):**

.. code-block:: bash

   FASTMCP_LOG_LEVEL=DEBUG ansys-aedt-mcp

**Windows PowerShell:**

.. code-block:: powershell

  $env:FASTMCP_LOG_LEVEL = "DEBUG"
  ansys-aedt-mcp

Connect with HTTP (Docker or remote)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

For containerized or remote deployments, see :doc:`../user_guide/docker`.

Next steps
----------

- To understand which tools are available, see :doc:`../user_guide/tools_and_capabilities`.
- For recommended usage patterns, see :doc:`../user_guide/best_practices`.
