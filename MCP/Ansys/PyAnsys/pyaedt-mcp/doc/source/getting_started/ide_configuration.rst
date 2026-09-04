.. _ref_ide_configuration:

IDE and client configuration
=============================

PyAEDT-MCP works with any MCP-compatible client. This page shows the HTTP and
stdio configurations for Visual Studio Code with Copilot, Claude Code, OpenCode,
and Codex.

Prerequisite: install uv
------------------------

Install uv, which includes ``uvx``, before using the ``uvx`` examples below.
``uvx`` downloads and runs PyAEDT-MCP without cloning this repository. Follow
the `uv installation instructions <https://docs.astral.sh/uv/getting-started/installation/>`_.

For example, on Windows:

.. code-block:: powershell

   winget install --id=astral-sh.uv -e

On macOS or Linux:

.. code-block:: bash

   curl -LsSf https://astral.sh/uv/install.sh | sh

Choose a transport
------------------

Choose HTTP when a PyAEDT-MCP server is already running locally. It is
appropriate for debugging or development. The client connects to the URL; it does
not start the server on its own.

Choose stdio when the client should launch PyAEDT-MCP as a local child process.
It starts automatically from the client configuration with ``uvx`` or from the
virtual environment in a cloned repository. Stdio is normally the simplest
option for a single local client.

Transport configurations
------------------------

.. tab-set::

   .. tab-item:: HTTP

      HTTP client configurations require a running PyAEDT-MCP server. Start it
      from a cloned repository after creating and installing a virtual
      environment:

      **Windows PowerShell**

      .. code-block:: powershell

         git clone https://github.com/ansys/pyaedt-mcp.git
         cd pyaedt-mcp
         uv venv
         uv pip install .
         .venv\Scripts\ansys-aedt-mcp --transport http --http-host 127.0.0.1 --http-port 8080

      **macOS or Linux**

      .. code-block:: bash

         git clone https://github.com/ansys/pyaedt-mcp.git
         cd pyaedt-mcp
         uv venv
         uv pip install .
         .venv/bin/ansys-aedt-mcp --transport http --http-host 127.0.0.1 --http-port 8080

      Or run the server directly with ``uvx`` without cloning the repository:

      .. code-block:: console

         uvx --index-strategy unsafe-best-match \
           --from git+https://github.com/ansys/pyaedt-mcp.git ansys-aedt-mcp \
           --transport http --http-host 127.0.0.1 --http-port 8080

      Keep the command running while the HTTP client is in use. For Docker and
      remote deployment options, see :doc:`../user_guide/docker`.

      .. tab-set::

         .. tab-item:: VS Code and Copilot

            Add this configuration to ``.vscode/mcp.json``.

            .. code-block:: json

               {
                 "servers": {
                   "pyaedt-mcp": {
                     "type": "http",
                     "url": "http://127.0.0.1:8080/mcp"
                   }
                 }
               }

         .. tab-item:: Claude

            Configure Claude Code for the current project:

            .. code-block:: bash

               claude mcp add --transport http pyaedt-mcp http://127.0.0.1:8080/mcp

         .. tab-item:: OpenCode

            Add this entry to the ``mcp`` object in ``opencode.json`` or
            ``opencode.jsonc``:

            .. code-block:: json

               {
                 "mcp": {
                   "pyaedt-mcp": {
                     "type": "remote",
                     "url": "http://127.0.0.1:8080/mcp"
                   }
                 }
               }

         .. tab-item:: Codex

            Add this entry to ``~/.codex/config.toml``:

            .. code-block:: toml

               [mcp_servers.pyaedt-mcp]
               url = "http://127.0.0.1:8080/mcp"

   .. tab-item:: stdio

      Stdio clients launch the local server automatically when needed. The
      following examples use ``uvx``. To run from a cloned repository instead,
      create the virtual environment with ``uv venv`` and install the project
      with ``uv pip install .``. Then replace ``uvx`` and its arguments with
      ``.venv\\Scripts\\ansys-aedt-mcp`` on Windows or
      ``.venv/bin/ansys-aedt-mcp`` on macOS and Linux.

      .. tab-set::

         .. tab-item:: VS Code and Copilot

            Add this configuration to ``.vscode/mcp.json``. Use the Command
            Palette command ``MCP: List Servers`` to start, stop, or inspect
            the server.

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

         .. tab-item:: Claude

            Configure Claude Code for the current project. Add ``--scope user``
            before ``pyaedt-mcp`` to make it available in all projects.

            .. code-block:: bash

               claude mcp add --transport stdio pyaedt-mcp -- \
                 uvx --index-strategy unsafe-best-match \
                 --from git+https://github.com/ansys/pyaedt-mcp.git ansys-aedt-mcp

            On Windows PowerShell, use a backtick (`` ` ``) instead of ``\`` for
            line continuation. Claude Desktop supports local stdio servers
            through its ``mcpServers`` configuration; use the same ``command``
            and ``args`` values as the VS Code configuration above.

         .. tab-item:: OpenCode

            Add this entry to the ``mcp`` object in ``opencode.json`` or
            ``opencode.jsonc``:

            .. code-block:: json

               {
                 "mcp": {
                   "pyaedt-mcp": {
                     "type": "local",
                     "command": [
                       "uvx",
                       "--index-strategy", "unsafe-best-match",
                       "--from", "git+https://github.com/ansys/pyaedt-mcp.git",
                       "ansys-aedt-mcp"
                     ]
                   }
                 }
               }

         .. tab-item:: Codex

            Add this entry to ``~/.codex/config.toml``:

            .. code-block:: toml

               [mcp_servers.pyaedt-mcp]
               command = "uvx"
               args = [
                 "--index-strategy", "unsafe-best-match",
                 "--from", "git+https://github.com/ansys/pyaedt-mcp.git",
                 "ansys-aedt-mcp"
               ]

See `MCP configuration reference in VS Code
<https://code.visualstudio.com/docs/agents/reference/mcp-configuration>`_,
`Connect Claude Code to tools via MCP <https://code.claude.com/docs/en/mcp>`_,
the `OpenCode MCP server documentation <https://opencode.ai/docs/mcp-servers/>`_,
and the `Codex MCP documentation <https://developers.openai.com/codex/mcp/>`_
for client-specific configuration and authentication options.

Advanced configuration
----------------------

Add the following server arguments after ``ansys-aedt-mcp`` in a stdio
configuration, or to the command used to start an HTTP server.

.. list-table::
   :header-rows: 1
   :widths: 25 20 55

   * - Argument
     - Default
     - Description
   * - ``--transport {stdio,http}``
     - ``stdio``
     - Select the MCP transport. Set this to ``http`` only when starting a
       standalone HTTP server; stdio clients start the server with the default.
   * - ``--machine HOST``
     - ``localhost``
     - AEDT gRPC host name or IP address for a startup connection.
   * - ``--port PORT``
     - ``50051``
     - AEDT gRPC port for a startup connection. Values must be from 1 through
       65535.
   * - ``--version VERSION``
     - Unset
     - AEDT version to use, for example ``2026.1`` or ``261``.
   * - ``--graphical``
     - Non-graphical
     - Launch AEDT with its graphical interface. Omit it to use the default
       non-graphical mode.
   * - ``--non-graphical``
     - Enabled
     - Explicitly launch AEDT without its graphical interface.
   * - ``--connect``
     - Disabled
     - Connect to AEDT when PyAEDT-MCP starts, using ``--machine`` and
       ``--port``. This locks the connection, disabling ``launch_aedt``,
       ``connect_to_aedt``, and ``disconnect_from_aedt`` for the server lifetime.
   * - ``--include-context``
     - Disabled
     - Register the optional AEDT and PyAEDT workflow guidance tools.
   * - ``--dynamic-tool-discovery``
     - Disabled
     - Hide AEDT-only tools until an AEDT connection is established, reducing
       the initial client context.
   * - ``--http-host HOST``
     - ``127.0.0.1``
     - Network interface used by HTTP transport. This argument applies only
       with ``--transport http``.
   * - ``--http-port PORT``
     - ``8080``
     - Network port used by HTTP transport. This argument applies only with
       ``--transport http`` and must be from 1 through 65535.
   * - ``--cors-origins ORIGIN [ORIGIN ...]``
     - Unset
     - Space-separated origins allowed by the HTTP server's CORS policy. This
       argument applies only with ``--transport http``.

For example, append the arguments below to any stdio command to connect to a
specific AEDT gRPC session and register the optional context tools:

.. code-block:: console

   ansys-aedt-mcp --connect --machine 192.168.1.100 --port 50051 --include-context

Next steps
----------

After PyAEDT-MCP connects, follow :doc:`../user_guide/best_practices` for recommended
workflows and :doc:`../user_guide/tools_and_capabilities` to explore the
available tools.
