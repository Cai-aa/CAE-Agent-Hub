.. _ref_user_guide:

==========
User guide
==========

This section provides comprehensive documentation for building MCP servers with
PyAnsys Common MCP. It explains architectural concepts and practical patterns.

Overview
========

PyAnsys Common MCP provides infrastructure to create Model Context Protocol (MCP)
servers that let AI assistants interact with Ansys products through PyAnsys libraries.

The library handles these tasks:

- **Lifecycle management**: Automatically starts, cleans up, and handles errors.
- **Python sessions**: Provides persistent Python environments for stateful code execution.
- **Context management**: Shares the state accessible from all tools.
- **Logging**: Configures logging without interfering with the MCP protocol.

As a library developer, you must perform these tasks:

- **Define the custom context**: Extend the ``PyAnsysBaseAppContext`` class with
  product-specific fields.
- **Implement the server**: Extend the ``PyAnsysBaseMCP`` class with startup and cleanup logic.
- **Create tools**: Define MCP tools that expose product functionality.

What's next?
============

- :ref:`user_guide_architecture` - Learn how the framework works.
- :ref:`user_guide_advanced_patterns` - Explore advanced techniques and patterns.
- :ref:`ref_examples` - Review complete working examples.

.. toctree::
   :maxdepth: 2
   :hidden:

   architecture
   advanced_patterns
