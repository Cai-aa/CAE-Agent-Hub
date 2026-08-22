.. title:: Welcome to PyCFX-MCP

.. meta::
   :keywords: ansys.cfx.mcp, pycfx, cfx, mcp, ai, cfd, simulation, python
   :description: Welcome to PyCFX-MCP documentation.

.. only:: html

   .. image:: ../source/_static/logo-dark.svg
      :class: only-dark
      :width: 800
      :alt: PyCFX-MCP logo
      :align: center

   .. image:: ../source/_static/logo-light.svg
      :class: only-light
      :width: 800
      :alt: PyCFX-MCP logo
      :align: center

.. toctree::
   :hidden:
   :maxdepth: 3

   getting_started/index
   user_guide/index
   api/index
   examples/index
   changelog

.. vale off

**Welcome to the PyCFX-MCP documentation!** Use PyCFX-MCP, an MCP (Model Context Protocol)
server, to connect your AI assistant to Ansys CFX workflows through PyCFX.

**What do you want to do?**

.. vale on

.. grid:: 2 2 3 3
   :gutter: 1 2 3 3
   :padding: 1 2 3 3

   .. grid-item-card:: :fa:`info-circle` Learn about PyCFX-MCP
      :link: user_guide/overview
      :link-type: doc

      Learn what PyCFX-MCP is, how it works, when to use it, and how MCP
      clients interact with CFX through a compact tool surface.

   .. grid-item-card:: :fa:`rocket` Get started quickly
      :link: getting_started/installation
      :link-type: doc

      Install PyCFX-MCP and run your first MCP server over STDIO or
      Streamable HTTP.

   .. grid-item-card:: :fa:`cogs` Configure your IDE
      :link: getting_started/ide_configuration
      :link-type: doc

      Set up PyCFX-MCP with Visual Studio Code or another MCP-compatible client.

   .. grid-item-card:: :fa:`tools` Explore available tools
      :link: user_guide/tools_and_capabilities
      :link-type: doc

      Review tools for sessions, workflows, model context, code generation,
      validation, and execution.

   .. grid-item-card:: :fa:`book` Learn best practices
      :link: user_guide/best_practices
      :link-type: doc

      Follow practical guidance for safe session management, routed workflow
      actions, and bounded model-context gathering.

   .. grid-item-card:: :fa:`code` Browse code examples
      :link: examples/index
      :link-type: doc

      Explore usage examples and learn how to implement custom MCP tools for
      CFX-oriented workflows.

   .. grid-item-card:: :fa:`book-open-reader` Use the API reference
      :link: api/index
      :link-type: doc

      Access complete API reference documentation for PyCFX-MCP.

   .. grid-item-card:: :fa:`question` Find help or report issues
      :link: https://github.com/ansys/pycfx-mcp/issues
      :link-type: url

      Ask questions or report issues on the GitHub Issues page.

   .. grid-item-card:: :fa:`users` Contribute to the project
      :link: getting_started/contribution
      :link-type: doc

      Contribute to PyCFX-MCP by reporting bugs, writing code, or improving
      the documentation.
