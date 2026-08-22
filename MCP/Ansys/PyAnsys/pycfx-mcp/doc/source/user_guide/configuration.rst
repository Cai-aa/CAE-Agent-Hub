Configuration
=============

Configure PyCFX-MCP with command-line options and environment variables.
You can run the MCP server over STDIO or Streamable HTTP.

General settings
----------------

.. list-table:: **Server command settings**
   :header-rows: 1
   :widths: 30 70

   * - Setting
     - Description
   * - ``--transport``
     - MCP transport to use. Supported values are ``stdio`` and ``http``.
       The default is ``stdio``.
   * - ``--host``
     - Host interface for HTTP transport. The default is ``127.0.0.1``.
   * - ``--port``
     - HTTP port. A value of ``0`` uses the server default of ``8000`` for HTTP
       transport.
   * - ``--backend``
     - Default backend kind until ``connect`` is called. This package ships the
       ``pycfx`` backend.
   * - ``--log-level``
     - Python logging level for the server process. The default is ``INFO``.

Language-model ownership
------------------------

PyCFX-MCP does not call a server-side language model. Configure model providers
in your MCP host or higher-level agent layer when you need natural-language code
authoring. PyCFX-MCP only validates and runs reviewed Python snippets through
``validate_code`` and ``run_code``.


Server command-line tool options
--------------------------------

Run this command to inspect supported command-line tool options for your
installed version:

.. code-block:: bash

   ansys-cfx-mcp --help

To start PyCFX-MCP over STDIO:

.. code-block:: bash

   ansys-cfx-mcp --transport stdio

To start PyCFX-MCP over HTTP on the local host interface:

.. code-block:: bash

   ansys-cfx-mcp --transport http --host 127.0.0.1 --port 8000

.. warning::

   PyCFX-MCP does not add authentication or TLS to HTTP transport. Use HTTP
   only for trusted local integrations or behind infrastructure that provides
   authentication and TLS.

Next steps
----------

- Configure an MCP client as described in :doc:`../getting_started/ide_configuration`.
- Launch your first workflow as described in :doc:`../getting_started/quick_start`.
- Review the descriptions of available tools in :doc:`tools_and_capabilities`.
