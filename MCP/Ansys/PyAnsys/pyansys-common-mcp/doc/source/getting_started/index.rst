.. _ref_getting_started:

Getting started
===============

Introduction
------------

PyAnsys Common MCP is a foundational library that helps you build Model Context Protocol (MCP)
servers. These servers let AI assistants interact with Ansys products through PyAnsys libraries.

This section shows how to create your first MCP server in under 30 minutes. For architectural
concepts and advanced patterns, see the :ref:`ref_user_guide`.

**Target audience:** PyAnsys library developers who create MCP servers for their products.

Installation
------------

Here are the requirements for PyAnsys Common MCP:

Requirements
~~~~~~~~~~~~
- Python 3.12 or later (up to 3.14)
- A PyAnsys library for your product (such as PyMAPDL or PyFluent)

Install in user mode
~~~~~~~~~~~~~~~~~~~~

The ``ansys.common.mcp`` package currently supports Python 3.12 through
Python 3.14 on Windows, Mac OS, and Linux.

Install the latest package for use with this command:

.. code-block:: bash

   pip install ansys-common-mcp

Alternatively, install the latest
`PyAnsys Common MCP GitHub <https://github.com/ansys/pyansys-common-mcp>`_ package
with this command:

.. code-block:: bash

   pip install git+https://github.com/ansys/pyansys-common-mcp.git


Install in developer mode
~~~~~~~~~~~~~~~~~~~~~~~~~

If you want to contribute to PyAnsys Common MCP or create custom servers, install in developer mode:

.. code-block:: bash

   # Clone the repository
   git clone https://github.com/ansys/pyansys-common-mcp.git
   cd pyansys-common-mcp

   # Install in editable mode with development dependencies
   pip install -e .[dev]

   # Or install documentation dependencies for building documentation
   pip install -e .[doc]

Verify the installation
~~~~~~~~~~~~~~~~~~~~~~~

Verify the installation by importing the package:

.. code-block:: python

   >>> from ansys.common.mcp import PyAnsysBaseMCP, PyAnsysBaseAppContext
   >>> from ansys.common.mcp import PersistentPythonSession

Quick start
-----------

Refer to the :ref:`ref_pyexample_mcp` section for a step-by-step example.
Below is a high-level overview of the steps to create a simple MCP server using the
``pyansys-common-mcp`` library.

1. **Define the context**: Create a custom context class that inherits from
   :class:`ansys.common.mcp.context.PyAnsysBaseAppContext`.

2. **Implement the server**: Create a server class that inherits from
   :class:`ansys.common.mcp.server.PyAnsysBaseMCP` and implements the ``product_startup()`` and
   ``product_cleanup()`` methods.

3. **Add tools**: Implement one or more tools in the server to provide specific functionality.

4. **Initialize the package**: Create an ``__init__.py`` to initialize the package and import
   necessary components.

5. **Create the entry point**: Define the entry point for the server in
   `src/pyexample_mcp/__main__.py`.

6. **Configure the package**: Set up the package configuration in `pyproject.toml`.

7. **Run the server**: Install the package and run the server using the entry point.

The server starts and communicates using stdio. It is ready to accept MCP requests from AI clients.

Next steps
==========

Your MCP server is ready. Explore these sections:

- :ref:`ref_user_guide`: Learn how the framework works and discover advanced patterns.
- :ref:`ref_examples`: See complete working examples like `PyMAPDL-MCP <pymapdl_mcp_>`_
