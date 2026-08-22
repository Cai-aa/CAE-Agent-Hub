.. _ref_pyexample_mcp:

PyExample-MCP
=============

This example shows how to implement a minimal MCP server for a
hypothetical PyAnsys library named ``PyExample``.

Project structure
-----------------

The very first step is to create the project structure.
This example uses a standard Python package layout with a ``src`` directory:

.. code-block:: text

   pyexample-mcp/
   ├── pyproject.toml
   ├── README.md
   └── src/
       └── pyexample_mcp/
           ├── __init__.py
           ├── __main__.py
           ├── server.py
           └── context.py


Once the structure is in place, you can start implementing the server.

Define the context
------------------

It is recommended to define a custom context class that inherits from
:class:`ansys.common.mcp.context.PyAnsysBaseAppContext`.
This context will hold any shared state or resources needed by your MCP tools.

**File:** ``src/pyexample_mcp/context.py``

.. literalinclude:: ../../../examples/src/pyexample_mcp/context.py
   :language: python

The context holds shared state accessible from all tools. See :ref:`user_guide_architecture` for
details on context management.

Implement the server
--------------------

The server class inherits from :class:`ansys.common.mcp.server.PyAnsysBaseMCP` and implements the
required methods to handle incoming requests.

**File:** ``src/pyexample_mcp/server.py``

.. literalinclude:: ../../../examples/src/pyexample_mcp/server.py
   :language: python


The ``product_startup()`` and ``product_cleanup()`` methods manage the lifecycle of the connection to
the product. The example uses a mock connection for demonstration purposes.
Those methods are required by the :class:`ansys.common.mcp.server.PyAnsysBaseMCP` class.

**Optional:** Override ``create_context()`` only if using a custom context class.

Implement tools
---------------

The server can have one or more tools that implement specific functionality.

**File:** ``src/pyexample_mcp/tools.py``

.. literalinclude:: ../../../examples/src/pyexample_mcp/tools.py
   :language: python


See the :ref:`user_guide_architecture` for details on context injection patterns.


Initialize the package
----------------------

**File:** ``src/pyexample_mcp/__init__.py``

.. literalinclude:: ../../../examples/src/pyexample_mcp/__init__.py
   :language: python


Define the entry point
----------------------

**File:** ``src/pyexample_mcp/__main__.py``

.. literalinclude:: ../../../examples/src/pyexample_mcp/__main__.py
   :language: python

The entry point delegates transport selection entirely to
:meth:`~ansys.common.mcp.server.PyAnsysBaseMCP.run_cli`, which is provided by the base
class. You do not need to implement argument parsing or transport dispatch yourself.

``run_cli()`` accepts the following command-line arguments:

.. list-table::
   :header-rows: 1
   :widths: 25 15 60

   * - Argument
     - Default
     - Description
   * - ``--transport {stdio,http}``
     - ``stdio``
     - Transport protocol to use.
   * - ``--http-host HOST``
     - ``127.0.0.1``
     - Host address when using HTTP transport.
   * - ``--http-port PORT``
     - ``8080``
     - Port number when using HTTP transport (1–65535).
   * - ``--cors-origins ORIGINS``
     - *(none)*
     - Comma-separated list of allowed CORS origins for HTTP transport.


Configure the package
---------------------

**File:** ``pyproject.toml``

.. literalinclude:: ../../../examples/pyproject.toml
   :language: toml


Run the example
---------------

Install the package in a virtual environment using pip:

.. code-block:: bash

   pip install .


Start the server with the default stdio transport:

.. code-block:: bash

   python -m pyexample_mcp


Start the server with HTTP transport on the default host and port (``127.0.0.1:8080``):

.. code-block:: bash

   python -m pyexample_mcp --transport http


Customize the host, port, and allowed CORS origins:

.. code-block:: bash

   python -m pyexample_mcp --transport http \
       --http-host 0.0.0.0 \
       --http-port 9000 \
       --cors-origins "http://localhost:3000,https://myapp.com"


VS Code configuration
~~~~~~~~~~~~~~~~~~~~~

For easier development and debugging, configure the server in VS Code by creating
a ``.vscode/mcp.json`` file.

Stdio transport (default):

.. code-block:: json

   {
       "servers": {
           "pyexample-mcp": {
               "type": "stdio",
               "command": ".\\.venv\\Scripts\\python.exe",
               "args": ["-m", "pyexample_mcp"]
           }
       }
   }


HTTP transport:

.. code-block:: json

   {
       "servers": {
           "pyexample-mcp": {
               "type": "http",
               "url": "http://127.0.0.1:8080/mcp"
           }
       }
   }

When using HTTP transport, start the server process separately before connecting VS Code:

.. code-block:: bash

   python -m pyexample_mcp --transport http


The server will start and communicate via the selected transport, ready to accept MCP requests
from AI clients.
