Overview
========

What is PyMAPDL-MCP?
--------------------

Use PyMAPDL-MCP as a bridge between AI assistants and Ansys MAPDL. It uses the Model Context Protocol
(MCP) to expose PyMAPDL capabilities as standardized tools that AI systems can call.

What is MCP?
~~~~~~~~~~~~

MCP is a standardized interface for connecting AI systems to external tools and data sources.
It allows AI assistants to perform the following tasks:

- Discover available tools and their capabilities.
- Call tools with structured parameters.
- Receive results and error information.
- Maintain state across multiple interactions.

How does MCP work?
~~~~~~~~~~~~~~~~~~

- **Client connection**: An MCP-compatible client (such as Claude) connects to the PyMAPDL-MCP server.
- **Tool discovery**: The client discovers available tools for controlling MAPDL.
- **Tool execution**: The client calls tools with appropriate parameters.
- **Result return**: The server returns results or errors to the client.
- **Interaction loop**: The cycle continues for the duration of the session.

Understand the architecture
----------------------------

PyMAPDL-MCP includes several key components:

- **MCP server**: Implements the MCP protocol and handles client connections.
- **Tool registry**: Maintains the list of available tools.
- **PyMAPDL integration**: Wraps PyMAPDL capabilities as MCP tools.
- **Session management**: Manages MAPDL instance lifecycle.
- **Context management**: Maintains app state across interactions.

Explore use cases
-----------------

**Automated simulations**
    Use AI to design and run parametric FEA studies automatically.

**Interactive analysis**
    Ask an AI assistant to analyze simulation results and suggest improvements.

**Documentation generation**
    Automatically create reports and documentation from simulations.

**Script debugging**
    Get AI assistance in debugging complex MAPDL scripts.

**Learning tool**
    Use an AI assistant as a tutor for learning MAPDL and FEA concepts.


Next steps
----------

- Learn about available :doc:`tools_and_capabilities`.
- Review :doc:`best_practices` for effective use.
- Explore the :doc:`../api/ansys/mapdl/mcp/tools/index` page for technical details.
