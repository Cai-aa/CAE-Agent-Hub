Overview
========

What is PyFluent-MCP?
---------------------

Use PyFluent-MCP (``ansys.fluent.mcp``) as a bridge between external MCP clients and
Ansys Fluent. It uses the Model Context Protocol (MCP) to expose PyFluent capabilities
as standardized deterministic tools.

What is MCP?
~~~~~~~~~~~~

MCP is a standardized interface for connecting external clients to tools and data
sources. It allows clients to perform the following tasks:

- Discover available tools and their capabilities.
- Call tools with structured parameters.
- Receive results and error information.
- Maintain state across multiple interactions.

How does MCP work?
~~~~~~~~~~~~~~~~~~

- **Client connection**: An MCP-compatible client connects
  to the PyFluent-MCP server.
- **Tool discovery**: The client discovers available tools for controlling Fluent.
- **Tool execution**: The client calls tools with appropriate parameters.
- **Result return**: The server returns results or errors to the client.
- **Interaction loop**: The cycle continues for the duration of the session.

Understand the architecture
---------------------------

PyFluent-MCP includes several key components under the ``ansys.fluent.mcp`` namespace:

- **MCP server** (:class:`~ansys.fluent.mcp.solve.SolveMCP`): Implements the MCP
  protocol and handles client connections.
- **Tool surface**: Stateless tools for connection, discovery, execution,
  validation, and reporting.
- **PyFluent backend**: In-process gRPC to a local or remote Fluent solver.
- **Settings catalog**: Offline schema (~62k paths) with local BM25-based search.
- **AST sandbox**: Validates Python before it reaches the solver.

PyFluent-MCP intentionally stays a deterministic substrate. It does not own
provider orchestration, runtime model routing, transport policy, retries,
workflow reasoning, or agent loops. Those concerns belong in higher-level
products or external MCP hosts that consume this package over MCP.

Design tenets
-------------

- **Stateless per call.** Each tool call is self-contained except for the live Fluent
  connection and the ``run_code`` REPL namespace.
- **Python never writes Fluent directly without validation.** Python only runs through
  ``run_code`` / ``validate_code``, which pass through an AST sandbox.
- **Offline-first knowledge.** ``find_api`` and ``get_help`` work from
  the bundled settings schema without any network service.
- **Pluggable backends.** PyFluent ships in-box. Other backends can be contributed via
  entry points.

Explore use cases
-----------------

**Solver setup**
    Configure boundary conditions, materials, and numerics interactively.

**Interactive analysis**
    Inspect residuals, mesh quality, or setup summaries.

**Case comparison**
    Diff two case files to see what changed between versions.

**Learning tool**
    Use deterministic tooling to learn Fluent's settings API and PyFluent.

Next steps
----------

- Learn about available :doc:`tools_and_capabilities`.
- Review :doc:`configuration` for environment variables and transport setup.
- Review :doc:`best_practices` for effective use.
- Explore the :doc:`../user_guide/tools_and_capabilities` for technical details.
