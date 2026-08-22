IDE and client configuration
============================

PyFluent-MCP can be integrated with multiple MCP-compatible tools. This page explains
configuration for the most popular clients.

Claude Code
-----------

Claude Code includes MCP support. You can add PyFluent-MCP using the
command-line tool.

Set up PyFluent-MCP for a specific project (recommended)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Configure PyFluent-MCP for a specific project:

.. code-block:: bash

   cd my-project
   claude mcp add --transport stdio pyfluent -- uvx --from git+https://github.com/ansys/pyfluent-mcp ansys-fluent-mcp

**Advantages**

- Provides project-specific configuration.
- Enables sharing with team members via version control.
- Simplifies maintenance of multiple configurations per project.
- Supports collaborative teams.

Set up PyFluent-MCP globally
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Configure PyFluent-MCP for all your Claude Code projects:

.. code-block:: bash

   claude mcp add --transport stdio --scope user pyfluent -- uvx --from git+https://github.com/ansys/pyfluent-mcp ansys-fluent-mcp

**Key features**

- Uses STDIO transport by default (local integration).
- Uses uvx for automatic fetching from GitHub.
- Requires no manual management of configuration files.
- Provides full MCP protocol support.

**Documentation**

See `Claude Code MCP installation <https://code.claude.com/docs/en/mcp#installing-mcp-servers>`_ documentation.

Visual Studio Code
------------------

Visual Studio Code integrates MCP servers through the Copilot extension using a JSON
configuration file.

Start quickly from GitHub
~~~~~~~~~~~~~~~~~~~~~~~~~

Add this code to the ``.vscode/mcp.json`` file in your project directory:

.. code-block:: json

   {
     "servers": {
       "pyfluent": {
         "type": "stdio",
         "command": "uvx",
         "args": [
           "--from",
           "git+https://github.com/ansys/pyfluent-mcp",
           "ansys-fluent-mcp"
         ]
       }
     }
   }

**Features**

- Uses STDIO transport (recommended for local development).
- Fetches the latest version from GitHub.
- Requires uvx to be installed on your system.

Set up for local development
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Use this code for development or testing with local source code:

.. code-block:: json

   {
     "servers": {
       "pyfluent": {
         "type": "stdio",
         "command": "./.venv/Scripts/python",
         "args": ["-m", "ansys.fluent.mcp"],
         "env": {
           "FLUIDS_MCP_LOG_LEVEL": "DEBUG"
         }
       }
     }
   }

On macOS or Linux, replace ``./.venv/Scripts/python`` with ``./.venv/bin/python``.

**Features**

- Uses a local Python virtual environment.
- Enables debug logging for troubleshooting.
- Works well for development and testing.
- Requires ``pip install -e ".[pyfluent]"`` in your virtual environment.

Claude Desktop
--------------

Add PyFluent-MCP to the Claude Desktop configuration file.

**On macOS:** ``~/Library/Application Support/Claude/claude_desktop_config.json``

**On Windows:** ``%APPDATA%\Claude\claude_desktop_config.json``

.. code-block:: json

   {
     "mcpServers": {
       "pyfluent": {
         "command": "ansys-fluent-mcp",
         "args": []
       }
     }
   }

Ensure ``ansys-fluent-mcp`` is on your ``PATH`` (installed via pip) or provide the full
path to the executable in your virtual environment.

Cursor
------

Cursor supports MCP servers through its settings UI or a project-level configuration
file. Add PyFluent-MCP using the same STDIO command as other clients:

.. code-block:: json

   {
     "mcpServers": {
       "pyfluent": {
         "command": "ansys-fluent-mcp",
         "args": []
       }
     }
   }

For HTTP transport (for example, when running the server separately):

.. code-block:: bash

   ansys-fluent-mcp --transport http --host 127.0.0.1 --port 8000

Then configure your client to connect to ``http://127.0.0.1:8000/mcp`` using streamable
HTTP transport (refer to your client's MCP documentation for the exact JSON schema).

Environment variables
---------------------

You can pass environment variables through the MCP client configuration. Common
variables include:

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Variable
     - Purpose
   * - ``FLUIDS_MCP_LOG_LEVEL``
     - Server log level (default ``INFO``)
   * - ``FLUIDS_MCP_HTTP_TIMEOUT``
     - Timeout for outbound HTTP operations
   * - ``FLUIDS_MCP_CA_BUNDLE``
     - Path to a PEM CA bundle for corporate or self-signed TLS environments
   * - ``FLUIDS_MCP_VERIFY_TLS``
     - Enable or disable TLS verification (default enabled)
   * - ``FLUIDS_MCP_SETTINGS_JSON``
     - External file for overriding the bundled settings schema

For the full list, see :doc:`../user_guide/configuration`.

Next steps
----------

- Follow the :doc:`quick_start` guide to connect to Fluent.
- Explore the :doc:`../user_guide/tools_and_capabilities` page.
