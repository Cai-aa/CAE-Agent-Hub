Configuration
=============

PyFluent-MCP is configured primarily through ``FLUIDS_MCP_*`` environment variables.
You can set these in your shell, MCP client configuration, or a ``.env`` file loaded by
your client.

General settings
----------------

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Variable
     - Effect
   * - ``FLUIDS_MCP_SETTINGS_JSON``
     - External JSON file for overriding the bundled settings schema
   * - ``FLUIDS_MCP_LOG_LEVEL``
     - Server log level (default ``INFO``)
   * - ``FLUIDS_MCP_DISABLE_SESSION_LOGS``
     - ``1`` turns off session logs
   * - ``FLUIDS_MCP_MAX_STEPS``
     - Cap on deterministic tool-loop iterations (default ``30``)
   * - ``FLUIDS_MCP_INTENT_GUARD``
     - ``0`` turns off the ``run_code`` crash-signature guard (default on)

Execution and retrieval behavior
--------------------------------

PyFluent-MCP focuses on deterministic Fluent tooling and MCP transport
exposure.

The repository provides:

- validated Fluent execution
- schema retrieval and grounding
- backend abstraction
- deterministic tool execution
- MCP transport support

Transport security
------------------

TLS certificate verification is enabled by default for outbound retrieval and
HTTP operations.

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Variable
     - Purpose
   * - ``FLUIDS_MCP_CA_BUNDLE``
     - Path to a PEM CA bundle (also reads ``SSL_CERT_FILE`` / ``REQUESTS_CA_BUNDLE``)
   * - ``FLUIDS_MCP_VERIFY_TLS``
     - Enable or disable TLS verification (default enabled)
   * - ``FLUIDS_MCP_HTTP_TIMEOUT``
     - Timeout for outbound HTTP operations

Server command-line tool options
--------------------------------

The ``ansys-fluent-mcp`` console script accepts:

You can also launch the server as a module:

.. code-block:: bash

   python -m ansys.fluent.mcp

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Flag
     - Description
   * - ``--transport stdio|http``
     - MCP transport (default ``stdio``)
   * - ``--host`` / ``--port``
     - HTTP bind address (when ``--transport http``)
   * - ``--backend KIND``
     - Default backend kind until ``connect`` is called (ships ``pyfluent``)
   * - ``--log-level``
     - Log level (default ``INFO``)

Next steps
----------

- For passing environment variables through MCP clients, see :doc:`../getting_started/ide_configuration`.
