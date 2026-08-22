.. _user_guide_advanced_patterns:

=================
Advanced patterns
=================

This page explains advanced techniques for building robust MCP servers.

.. note::

   All tool examples use the recommended ``ctx: Context`` parameter pattern to access
   the application context. For more information, see :ref:`function_parameter`.

Initialize a Python session
===========================

Set up a session with startup code
----------------------------------

You can set up a Python session with custom startup code that runs automatically
when the session starts. This approach is useful for importing commonly used libraries,
configuring settings, or defining helper functions.

.. code-block:: python

   from ansys.common.mcp.helpers import PersistentPythonSession

   # Create a session with startup code
   startup_code = """
   import numpy as np
   import pandas as pd
   import matplotlib.pyplot as plt

   # Define a helper function
   def quick_plot(data):
       plt.figure(figsize=(10, 6))
       plt.plot(data)
       plt.show()
   """

   session = PersistentPythonSession(startup_code=startup_code)
   session.start()

   # Now numpy, pandas, and plt are already imported
   result = session.execute("arr = np.array([1, 2, 3, 4, 5])")

When you restart the session using the ``session.restart()`` method, the startup
code runs again, ensuring that all imports and configurations are
reestablished. This approach is particularly useful when resetting the session state
while maintaining necessary dependencies.

Run Python code from tools
--------------------------

The ``execute_python_code`` tool lets you run arbitrary Python code in the persistent session.
Because the code runs in the context of the session, it has access to all imports and variables
defined in the startup code.

.. code-block:: python

   from mcp.server.fastmcp import Context
   from ansys.common.mcp.tools import execute_python_code

   @mcp.tool()
   async def run_python_code(ctx: Context, code: str) -> str:
       """Run Python code in the persistent session.

       Parameters
       ----------
       ctx : Context
           MCP context (automatically injected).
       code : str
           Python code to run.
       """
       # Add additional execution logic here (such as logging and error handling)
       await return execute_python_code(ctx=ctx, code=code)

Restart a session with history
------------------------------

You can create a tool to restart the Python session while optionally replaying the command history.
This approach allows you to reset the session state without losing previous commands.

.. code-block:: python

   @mcp.tool()
   def restart_session(ctx: Context, replay_history: bool = True) -> str:
       """Restart the Python session and optionally replay commands.

       Parameters
       ----------
       ctx : Context
           MCP context (automatically injected).
       replay_history : bool, default: True
           Whether to replay command history.
       """
       app_context = ctx.request_context.lifespan_context

       history = app_context.command_history.copy()
       result = app_context.python_session.restart()

       if not result["success"]:
           return f"Restart failed: {result['error']}"

       if replay_history and history:
           for cmd in history:
               app_context.python_session.execute(cmd)
           return f"Restarted and replayed {len(history)} commands"

       return "Session restarted"

Track command history
=====================

Create and export command history
---------------------------------

You can maintain a command history in the application context and provide tools
to export it in various formats.

.. code-block:: python

   from mcp.server.fastmcp import Context

   @mcp.tool()
   def execute_command(ctx: Context, command: str) -> str:
       """Run and track a command.

       Parameters
       ----------
       ctx : Context
           MCP context (automatically injected).
       command : str
           Command to run.
       """
       app_context = ctx.request_context.lifespan_context
       result = app_context.product_instance.run(command)
       if result["success"]:
           app_context.command_history.append(command)
       return result

   @mcp.tool()
   def export_history(ctx: Context, format: str = "json") -> str:
       """Export the command history as JSON or text.

       Parameters
       ----------
       ctx : Context
           MCP context (automatically injected).
       format : str, default: 'json'
           Export format ('json' or 'text').
       """
       app_context = ctx.request_context.lifespan_context

       if format == "json":
           import json
           return json.dumps(app_context.command_history, indent=2)
       return "\n".join(app_context.command_history)

Handle errors
=============

Use graceful degradation
-------------------------

Handle errors without crashing the server:

.. code-block:: python

    from ansys.common.mcp.logging_config import get_logger

    logger = get_logger(__name__)

    def product_startup(self):
       """Start with graceful error handling."""
       try:
           logger.info("Attempting to connect to product...")
           self.context.product_instance = connect(timeout=30)
           logger.info(f"Connected: {self.context.product_instance}")

       except ConnectionTimeout as e:
           logger.error(f"Connection timeout: {e}")
           logger.warning("Server will start in limited mode")
           self.context.product_instance = None
           self.context.metadata["mode"] = "limited"

       except Exception as e:
           logger.error(f"Unexpected error during startup: {e}")
           raise  # Re-raise for critical errors

.. note::

   Logs automatically redirect to stderr (not stdout) to avoid interfering
   with the MCP protocol. The logging configuration handles this behavior.

Add retry logic
---------------

Implement retry logic for flaky connections:

.. code-block:: python

   import time

   def product_startup(self):
       """Connect with retry logic."""
       max_retries = 3
       retry_delay = 5  # seconds

       for attempt in range(1, max_retries + 1):
           try:
               logger.info(f"Connection attempt {attempt}/{max_retries}...")
               self.context.product_instance = connect()
               logger.info("Connected successfully")
               return

           except Exception as e:
               logger.warning(f"Attempt {attempt} failed: {e}")

               if attempt < max_retries:
                   logger.info(f"Retrying in {retry_delay} seconds...")
                   time.sleep(retry_delay)
               else:
                   logger.error("All connection attempts failed")
                   raise

Track metadata
==============

Monitor session state
---------------------

.. code-block:: python

   from datetime import datetime
   import uuid

   def product_startup(self):
       """Initialize with state tracking."""
       self.context.product_instance = connect()
       self.context.metadata.update({
           "session_id": str(uuid.uuid4()),
           "start_time": datetime.now().isoformat(),
           "statistics": {"commands_executed": 0, "errors": 0}
       })

Manage user preferences
-----------------------

.. code-block:: python

   @mcp.tool()
   def set_preference(ctx: Context, key: str, value: str) -> str:
       """Set a user preference.

       Parameters
       ----------
       ctx : Context
           MCP context (automatically injected).
       key : str
           Preference key.
       value : str
           Preference value.
       """
       app_context = ctx.request_context.lifespan_context
       app_context.metadata.setdefault("preferences", {})[key] = value
       logger.info(f"Set {key} = {value}")
       return json.dumps(
           {
               "success": True,
               "stdout": "",
               "stderr": "",
               "message": "Preference updated",
           },
           ensure_ascii=False,
           indent=2,
       )

   @mcp.tool()
   def get_preference(ctx: Context, key: str, default: str = None) -> str:
       """Get a user preference.

       Parameters
       ----------
       ctx : Context
           MCP context (automatically injected).
       key : str
           Preference key.
       default : str, default: None
           Default value if the specified preference key is not found.
       """
       app_context = ctx.request_context.lifespan_context
       prefs = app_context.metadata.get("preferences", {})
       value = prefs.get(key, default)

       if value is None:
           return f"Preference '{key}' is not set."
       return value

Configure the transport protocol
================================

By default, MCP servers communicate over stdio, which is the standard transport
for local AI client integrations. The base class also supports HTTP transport,
which is useful for remote clients, web applications, and CORS-enabled frontends.

The :meth:`~ansys.common.mcp.server.PyAnsysBaseMCP.run_cli` method handles all transport
configuration. Call it from your package's ``__main__.py`` instead of
calling ``app.run()`` directly:

.. code-block:: python

   # src/myproduct_mcp/__main__.py
   import sys
   from ansys.common.mcp.logging_config import setup_logging
   from myproduct_mcp import app
   import myproduct_mcp.tools  # noqa: F401

   def main(argv=None):
       setup_logging(level="INFO")
       app.run_cli(argv)  # transport, host, port, and CORS are handled here
       return 0

   if __name__ == "__main__":
       sys.exit(main())

Your users can then select the transport at startup without any additional code in your
package:

.. code-block:: bash

   # stdio (default)
   python -m myproduct_mcp

   # HTTP on the default address (127.0.0.1:8080)
   python -m myproduct_mcp --transport http

   # HTTP with a custom host and port
   python -m myproduct_mcp --transport http --http-host 0.0.0.0 --http-port 9000

   # HTTP with CORS origins
   python -m myproduct_mcp --transport http \\
       --cors-origins "http://localhost:3000,https://myapp.com"

.. note::

   HTTP transport uses streamable HTTP (``/mcp`` endpoint). When using the HTTP
   transport, start the server process first, then point your AI client at
   ``http://<host>:<port>/mcp``.

Add product-specific CLI arguments
----------------------------------

For products that need their own CLI arguments (for example, a connection IP or port),
override :meth:`~ansys.common.mcp.server.PyAnsysBaseMCP._add_cli_arguments` to inject
them into the parser, and
:meth:`~ansys.common.mcp.server.PyAnsysBaseMCP._configure_from_cli` to process them.
The transport dispatch is unchanged — you never need to rewrite it.

Add arguments to the parser:

.. literalinclude:: ../../../examples/src/pyexample_mcp/server.py
   :language: python
   :pyobject: PyExampleMCP._add_cli_arguments

Store the parsed values before the server starts:

.. literalinclude:: ../../../examples/src/pyexample_mcp/server.py
   :language: python
   :pyobject: PyExampleMCP._configure_from_cli

The resulting server now accepts both the standard transport arguments and the
product-specific ones:

.. code-block:: bash

   python -m pyexample_mcp --ip 10.0.0.5 --port 50052 --connect-on-startup
   python -m pyexample_mcp --transport http --http-port 9000 --ip 10.0.0.5

Test CLI argument parsing
-------------------------

Because ``run_cli()`` accepts an optional ``argv`` list, you can test CLI argument
parsing without starting a real server. Tests for transport and CORS:

.. literalinclude:: ../../../tests/test_pyexample/test_main.py
   :language: python
   :pyobject: TestMainCliDispatch

Tests for product-specific arguments:

.. literalinclude:: ../../../tests/test_pyexample/test_main.py
   :language: python
   :pyobject: TestPyExampleCliHooks


Expose tool sets
================

A **tool set** groups tools under a named tag.

.. important::

   Registering the ``toolsets://definition`` resource is **required** for integration with
   some Ansys products, as it allows the product to discover and display available
   tool sets in the user interface.


Use ``@app.tool(tags={...})`` to assign a tool to one or more sets, and
``@app.resource("toolsets://definition")`` to expose the tool set definitions as a list.
Each tool set must include a ``name``, ``description``, ``skill`` (instructions for the AI
agent on when and how to use the tools), and ``tools`` (list of tool function names).

Register the resource:

.. literalinclude:: ../../../examples/src/pyexample_mcp/tools.py
   :language: python
   :pyobject: list_tool_sets

Tag a tool with the ``structures`` set:

.. literalinclude:: ../../../examples/src/pyexample_mcp/tools.py
   :language: python
   :pyobject: create_model

Tag a tool with the ``post_processing`` set:

.. literalinclude:: ../../../examples/src/pyexample_mcp/tools.py
   :language: python
   :pyobject: get_command_history

A tool can belong to multiple sets by listing several tags:

.. code-block:: python

   @app.tool(tags={"structures", "post_processing"})
   def get_stress_report(ctx: Context, model_name: str) -> str:
       """Generate a stress report."""
       ...
