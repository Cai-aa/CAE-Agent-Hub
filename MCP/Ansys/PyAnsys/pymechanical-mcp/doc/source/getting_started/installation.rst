.. _ref_installation:

Installation
============

PyMechanical-MCP supports Python 3.12 through 3.14.

Prerequisites
-------------

- Ansys Mechanical installation (local or remote) with an available gRPC endpoint
- Python 3.12 through 3.14
- Network access between PyMechanical-MCP and the Mechanical server

Install from PyPI
-----------------

Install PyMechanical-MCP using ``pip``:

.. code-block:: bash

   pip install ansys-mechanical-mcp

Install from source
-------------------

Clone and install in editable mode:

.. code-block:: bash

   git clone https://github.com/ansys/pymechanical-mcp
   cd pymechanical-mcp
   pip install -e ".[dev]"

Run the server
--------------

Use STDIO transport (the default) for MCP clients such as Visual Studio Code and Claude Code:

.. code-block:: bash

   ansys-mechanical-mcp

Use Streamable HTTP transport for remote or server-style deployments:

.. code-block:: bash

   ansys-mechanical-mcp --transport http --http-host 127.0.0.1 --http-port 8080

Connect on startup (optional)
-----------------------------

To auto-connect to a running Mechanical instance at startup:

.. code-block:: bash

   ansys-mechanical-mcp --connect-on-startup --ip 127.0.0.1 --port 10000

.. warning::
   When you use ``--connect-on-startup``, PyMechanical-MCP locks the connection and
   disables the ``launch_mechanical``, ``connect_to_mechanical``, and
   ``disconnect_from_mechanical`` tools.

Transport security mode
-----------------------

Select gRPC transport behavior with ``--transport-mode``:

- ``auto``: Automatically detects the mode based on the platform and certificates.
- ``insecure``: Uses plaintext gRPC.
- ``mtls``: Uses mutual TLS (requires certificates).
- ``wnua``: Uses Windows Named User Authentication.

Example:

.. code-block:: bash

   ansys-mechanical-mcp --transport-mode mtls --certs-dir /path/to/certs

You can supply the same values with environment variables:

- ``PYMECHANICAL_TRANSPORT_MODE``
- ``ANSYS_GRPC_CERTIFICATES``

Next steps
----------

- To run your first Mechanical workflow, see :doc:`quick_start`.
- For IDE setup, see :doc:`ide_configuration`.
- For startup options and environment variables, see :doc:`../user_guide/configuration`.
