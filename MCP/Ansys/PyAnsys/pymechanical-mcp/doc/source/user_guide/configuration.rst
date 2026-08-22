Configuration
=============

You can configure PyMechanical-MCP through command-line flags and environment variables.

Command-line tool startup flags
-------------------------------

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Flag
     - Description
   * - ``--transport stdio|http``
     - MCP transport (default ``stdio``).
   * - ``--http-host`` / ``--http-port``
     - HTTP bind address and port for ``--transport http``.
   * - ``--ip`` / ``--port``
     - Mechanical endpoint for ``connect_to_mechanical`` and ``--connect-on-startup``.
   * - ``--connect-on-startup``
     - Connection to Mechanical on startup. Locks lifecycle tools.
   * - ``--static-tools``
     - Expose all tools from startup instead of dynamically hiding tools
       that require a Mechanical connection. See `Static tool exposure`_.
   * - ``--transport-mode``
     - gRPC mode: ``auto``, ``insecure``, ``mtls``, or ``wnua``.
   * - ``--certs-dir``
     - Path to mTLS certificates directory (``ca.crt``, and ``client.crt``,
       ``client.key``).
   * - ``--cors-origins``
     - Comma-separated allowed origins for HTTP transport.
   * - ``--on-aali``
     - AALI-specific runtime behavior.

Environment variables
---------------------

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Variable
     - Description
   * - ``PYMECHANICAL_TRANSPORT_MODE``
     - Default gRPC mode when ``--transport-mode`` is not passed.
   * - ``ANSYS_GRPC_CERTIFICATES``
     - Default certificate directory when ``--certs-dir`` is not passed.
   * - ``PYMECHANICAL_IP`` / ``PYMECHANICAL_PORT``
     - Preferred endpoint values in containerized deployments.
   * - ``FASTMCP_LOG_LEVEL``
     - MCP server log verbosity.

Connection-lock behavior
------------------------

When you use ``--connect-on-startup``, the server connects to Mechanical
during startup and then disables:

- ``launch_mechanical``
- ``connect_to_mechanical``
- ``disconnect_from_mechanical``

This keeps the active session stable for clients that expect a fixed
connection lifecycle.

Static tool exposure
---------------------

By default, PyMechanical-MCP dynamically hides tools tagged
``requires_mechanical`` (see :doc:`tools_and_capabilities`) until
``launch_mechanical`` or ``connect_to_mechanical`` succeeds. Some MCP clients
do not reliably refresh their tool list when the server notifies them of a
change, which can make newly enabled tools appear unavailable until you send
another message or manually refresh the client's tool list.

Pass ``--static-tools`` to expose the full tool surface from startup instead.
Mechanical-only tools remain visible the whole time; calling one before a
connection exists returns a clear "No Mechanical connection available"
message rather than hiding the tool. This trades a small amount of prompt
size (all tool schemas are sent up front) for avoiding client-side tool list
refresh issues. ``--static-tools`` can be combined with ``--connect-on-startup``.

Next steps
----------

- For install and startup examples, see :doc:`../getting_started/installation`.
- For client setup, see :doc:`../getting_started/ide_configuration`.
