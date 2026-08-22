.. _user_guide_architecture:

============
Architecture
============

This page describes the architecture of PyAnsys Common MCP and explains how components work together.

Overview
========

PyAnsys Common MCP uses a layered architecture with a clear separation of concerns:

.. mermaid::

   flowchart TD
       A["AI client<br/>(Claude, ChatGPT)"]
       B["Your product MCP server<br/>• Custom context<br/>• Product startup/cleanup<br/>• MCP tools"]
       C["PyAnsysBaseMCP<br/>(Base class)<br/>• Lifecycle orchestration<br/>• Python session management<br/>• Context creation and injection<br/>• Error handling and logging"]
       D["FastMCP<br/>(MCP protocol library)<br/>• MCP protocol implementation<br/>• Tool registration and execution<br/>• Transport layer (stdio)"]

       A -->|"MCP protocol (stdio)"| B
       B -.->|extends| C
       C -.->|uses| D

       style A fill:#e1f5ff
       style B fill:#fff4e1
       style C fill:#e8f5e9
       style D fill:#f3e5f5

Core components
===============

PyAnsysBaseMCP
--------------

``PyAnsysBaseMCP`` is the base class for all PyAnsys product-specific MCP servers.

**Responsibilities:** It orchestrates the lifecycle, manages Python sessions, injects context, and
handles errors.

.. important::

   **Methods you must implement:**

   - ``product_startup()``: Initialize your product connection.
   - ``product_cleanup()``: Clean up your product connection.

   These methods are abstract and must be implemented in your subclass.
   If you fail to implement them, the system raises a ``TypeError`` at instantiation.

**Methods you can optionally override:**

- ``create_context()``: Override this method only if you use a custom context class.
  It returns the ``PyAnsysBaseAppContext`` dataclass by default.

**Methods already implemented:**

- ``start_python_session()``: Start a persistent Python subprocess.
- ``cleanup_python_session()``: Stop the Python session.
- ``product_lifespan()``: Manage the complete server lifecycle.

PyAnsysBaseAppContext
---------------------

``PyAnsysBaseAppContent`` is the dataclass that holds the shared state accessible from all MCP tools.

**Built-in fields:**

.. code-block:: python

   @dataclass
   class PyAnsysBaseAppContext:
       product_instance: Optional[Any] = None
       python_executable: Optional[Any] = None
       python_session: Optional[Any] = None  # PersistentPythonSession
       metadata: dict = field(default_factory=dict)
       command_history: list = field(default_factory=list)

**Extending the context:**

Product-specific servers can extend this class to add custom fields:

.. code-block:: python

   from dataclasses import dataclass
   from typing import Optional
   from ansys.common.mcp import PyAnsysBaseAppContext

   @dataclass
   class MyProductContext(PyAnsysBaseAppContext):
       """Extended dataclass for MyProduct MCP context."""
       custom_field: Optional[str] = None

.. tip::

    If you need a custom field, you can either extend this class or use the
    ``metadata`` dictionary to store arbitrary key-value pairs.

Context injection
=================

The system injects context into tools using FastMCP's dependency system. You can inject context in
two ways:

.. _function_parameter:

Function parameter
------------------

The recommended way to inject context is to declare ``ctx: Context`` as a parameter. FastMCP then
automatically injects it.

- Always include ``ctx: Context`` as the first parameter to ensure proper injection.
  This also enforces implementation of critical methods like ``product_startup()``
  and ``product_cleanup()`` in your server class.

- Do not attempt to pass ``ctx`` manually when calling the tool. The framework handles it
  automatically.

  This code shows how to declare ``ctx: Context`` as a parameter:

.. code-block:: python

   from mcp.server.fastmcp import Context

   @mcp.tool()
   def my_tool(ctx: Context, param: str) -> str:
       """Execute something.

       Parameters
       ----------
       ctx : Context
           MCP context (automatically injected). Do not pass manually.
       param : str
           Your parameter.
       """
       # Access application context
       app_context = ctx.request_context.lifespan_context

       # Access product instance
       result = app_context.product_instance.run(param)

       # Add to command history if successful
       if result["success"]:
            app_context.command_history.append(param)

       return result

``get_context()`` function
--------------------------

The other way to inject context is to import and call the ``get_context()`` function
inside the tool function. This function retrieves the current context instance.

.. code-block:: python

   from fastmcp.server.dependencies import get_context

   @mcp.tool()
   def my_tool(param: str) -> str:
       """Execute something."""
       ctx = get_context()
       app_context = ctx.fastmcp._lifespan_result

       result = app_context.product_instance.do_something(param)
       app_context.command_history.append(f"my_tool({param})")
       return result

Tools
=====

This library provides a set of built-in tools for common operations, such as executing Python code
and creating custom plots. You can explore the :py:mod:`ansys.common.mcp.tools` module to use the
available functions directly in your server or extend them with additional logic.

If you identify a missing function that could benefit multiple repositories, consider opening an
issue or submitting a pull request (PR) to add it. The tools module serves as a shared utility belt
for all PyAnsys product MCP servers.

Lifecycle management
====================

The ``product_lifespan()`` method automatically manages the server lifecycle:

**Phases:**

1. Create context.
2. Start Python session.
3. **Start product.** ← Add your code here.
4. Server runs (handles requests).
5. **Clean up product.** ← Add your code here.
6. Stop Python session.

Using the abstract base class ensures that product-specific servers implement the
``product_startup()`` and ``product_cleanup()`` methods. If these methods are not
implemented, the system raises runtime errors:

.. code-block:: python

   # This raises TypeError if methods are not implemented
   server = MyProductMCP()
   # TypeError: Can't instantiate abstract class MyProductMCP with abstract methods
   # product_cleanup() and product_startup()

Configuring Python session management
--------------------------------------

The ``need_python`` parameter controls whether the server automatically manages a persistent
Python session during the lifecycle. By default, this is enabled (``True``).

**When to use Python sessions:**

A persistent Python session is useful when your MCP tools need to execute Python code and
maintain state between executions. For example:

- Running generated Python scripts that interact with your product
- Maintaining Python objects or connections across multiple tool calls
- Executing complex calculations or data processing pipelines

**When to disable Python sessions:**

If your MCP server primarily exposes product functionality through direct API calls and does not
need to execute arbitrary Python code, you can disable the Python session to reduce overhead.
Pass ``need_python=False`` to the constructor:

.. code-block:: python

   from ansys.common.mcp import PyAnsysBaseMCP

   class MyProductMCP(PyAnsysBaseMCP):
       """MCP server that does not use Python sessions."""

       def __init__(self, *args, **kwargs):
           super().__init__(*args, need_python=False, **kwargs)

       def product_startup(self):
           """Initialize product without Python session."""
           self.context.product_instance = MyProduct()

       def product_cleanup(self):
           """Clean up product."""
           if self.context.product_instance:
               self.context.product_instance.close()

Alternatively, you can pass it directly when instantiating:

.. code-block:: python

   # Disable Python session
   server = MyProductMCP(need_python=False)

   # Enable Python session (default)
   server = MyProductMCP(need_python=True)

**Configuring the Python session:**

When Python sessions are enabled, you can customize the Python environment using constructor
parameters:

.. code-block:: python

   import sys

   # Use custom Python executable and working directory
   server = MyProductMCP(
       python_executable="/path/to/python/executable",
       working_directory="/custom/working/dir",
       need_python=True  # Enable Python session (default)
   )

   # Use current interpreter with Python session disabled
   server = MyProductMCP(need_python=False)

The Python session is automatically configured with:

- Non-interactive matplotlib backend (Agg) to prevent blocking
- PyVista off-screen rendering
- Helper functions for saving plots (both PyVista and Matplotlib)
- Access through ``context.python_session`` in your tools

**Asynchronous lifecycle:**

FastMCP uses async/await for all operations because the MCP protocol is inherently asynchronous.
The ``product_lifespan()`` method is an async context manager that integrates with FastMCP's event
loop. This allows the framework to handle all asynchronous complexity internally.

**Note:** Your ``product_startup()`` and ``product_cleanup()`` methods are regular
(synchronous) functions. The framework handles the async part.

Logging
=======

Logs are written to **stderr** (not ``stdout``) to avoid interfering with the MCP protocol. To
configure logging, use this code:

.. code-block:: python

   from ansys.common.mcp.logging_config import setup_logging, get_logger

   setup_logging(level="INFO")  # or use LOGLEVEL env variable
   logger = get_logger(__name__)

   logger.info("Starting...")
   logger.error("Error occurred")
