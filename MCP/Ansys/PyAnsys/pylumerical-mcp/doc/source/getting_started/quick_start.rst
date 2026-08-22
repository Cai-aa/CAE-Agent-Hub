Quick start
===========

Learn how to connect PyLumerical-MCP to your preferred agentic AI client.
Before you begin, install PyLumerical-MCP by following the instructions in
:doc:`Installation <installation>`.

Connect to your agentic client
------------------------------

You can use PyLumerical-MCP with transport over both `Streamable HTTP <https://modelcontextprotocol.io/specification/2025-11-25/basic/transports#streamable-http>`__
and `STDIO <https://modelcontextprotocol.io/specification/2025-11-25/basic/transports#stdio>`__.

Since PyLumerical-MCP uses the open source MCP standard, which enables AI applications to seamlessly integrate with external systems,
you can use it with a wide range of agent-based frameworks and agent harnesses that support MCP.

The following sections show you the important settings for PyLumerical-MCP. For instructions on how to connect,
see your preferred client's documentation.

Configure Streamable HTTP transport
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

To configure Streamable HTTP transport, you can set it through the ``.env`` file.

#. Copy the ``.env.example`` template file and rename it to ``.env``.

#. Set the following variables:

   - ``FASTMCP_TRANSPORT``: Set to ``"streamable-http"``.
   - ``FASTMCP_HOST``: Set to the hostname for the server. For local use, set to ``"127.0.0.1"``.
   - ``FASTMCP_PORT``: Set to the port for the server, such as ``8081``.

#. Start the MCP server by running ``ansys-lumerical-mcp`` from the command line in the environment where the MCP server is installed.

#. Connect to the MCP server from your client.

Configure STDIO transport
~~~~~~~~~~~~~~~~~~~~~~~~~

The configuration for STDIO transport depends on your specific client. However, these general guidelines can help:

- Set the target executable to the ``ansys-lumerical-mcp`` in the environment where it is installed.
- Set the transport type to ``stdio``. The specific key can vary by client.
- Leave the argument field empty.

View additional resources
-------------------------

.. grid:: 2 2 3 3

   .. grid-item-card:: :fa:`code` Usage examples
      :link: ../examples/usage_examples
      :link-type: doc

      View example prompts for using PyLumerical-MCP to drive Lumerical tools.

   .. grid-item-card:: :fa:`book` User guide
      :link: ../user_guide/index
      :link-type: doc

      Learn how to use PyLumerical-MCP effectively.

   .. grid-item-card:: :fa:`tools` Available tools
      :link: ../api/ansys/lumerical/mcp/tools/index
      :link-type: doc

      Access references for every tool the server exposes.
