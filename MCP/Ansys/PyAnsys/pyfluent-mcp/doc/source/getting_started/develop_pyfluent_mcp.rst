.. _ref_develop_pyfluent_mcp:

====================
Develop PyFluent-MCP
====================

Set up your development environment and start contributing code to PyFluent-MCP.

Naming conventions
==================

PyFluent-MCP uses the standard PyAnsys MCP naming pattern:

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Surface
     - Name
   * - GitHub repository
     - ``pyfluent-mcp``
   * - PyPI distribution
     - ``ansys-fluent-mcp``
   * - Python namespace
     - ``ansys.fluent.mcp``
   * - Console script
     - ``ansys-fluent-mcp``
   * - Module launch
     - ``python -m ansys.fluent.mcp``
   * - Documentation title
     - PyFluent-MCP

Architecture
============

PyFluent-MCP is built on the ``PyAnsysBaseMCP`` framework (from ``ansys-common-mcp``),
which is itself built on top of FastMCP. The server is a **stateless MCP leaf**: each tool
call is self-contained, and the only persistent state across calls is the live Fluent
connection and the per-session REPL namespace used by ``run_code``.

**Startup**

- Initializes the Solve MCP server (:class:`~ansys.fluent.mcp.solve.SolveMCP`).
- Loads the offline settings schema from ``settings_271.json.gz``.
- Waits for MCP client connections over STDIO or streamable HTTP.

**Runtime**

- Exposes 22 MCP tools for Fluent interaction.
- Routes live operations through the PyFluent backend.
- Runs Python through an AST sandbox before it reaches the solver.

**Shutdown**

- Releases the Fluent connection when ``disconnect`` is called or the server exits.

Package layout
--------------

.. code-block:: text

   pyfluent-mcp/
   ├── src/ansys/fluent/mcp/     # Main package (ansys.fluent.mcp)
   │   ├── __init__.py           # Version + public re-exports
   │   ├── __main__.py           # ``python -m ansys.fluent.mcp``
   │   ├── py.typed              # PEP 561 typing marker
   │   ├── server.py             # ``launcher`` CLI entry point
   │   ├── common/               # Shared infrastructure
   │   │   ├── base.py           # FluidsLeafMCP
   │   │   ├── backend.py        # Backend ABC
   │   │   ├── config.py         # FLUIDS_MCP_* env vars
   │   │   ├── network.py        # TLS and HTTP helpers
   │   │   └── validation.py     # AST sandbox
   │   └── solve/                # Fluent Solve MCP leaf
   │       ├── mcp/              # SolveMCP
   │       ├── backends/         # PyFluent backend (+ plugins)
   │       ├── catalog/          # Schema and local API search
   │       ├── lib/              # Domain tools
   │       ├── data/             # settings_271.json.gz
   │       └── skills/           # MCP-host routing skill
   ├── tests/
   └── doc/                      # Sphinx documentation

``ansys/`` and ``ansys/fluent/`` are namespace packages (no ``__init__.py``),
matching the PyAnsys layout used by ``ansys.fluent.core``.

Check prerequisites
===================

Before you begin, ensure you have:

- Python 3.12 or higher
- Git installed
- A text editor or IDE (such as Visual Studio Code or PyCharm)
- A GitHub account
- Ansys Fluent and PyFluent (for live-session testing)

Clone the repository
====================

#. Fork the GitHub repository.
#. Clone your fork locally:

   .. code-block:: bash

      git clone https://github.com/YOUR_USERNAME/pyfluent-mcp.git
      cd pyfluent-mcp

#. Add the upstream repository as a remote:

   .. code-block:: bash

      git remote add upstream https://github.com/ansys/pyfluent-mcp.git

Set up your development environment
===================================

#. Create a virtual environment:

   .. code-block:: bash

      python -m venv .venv

#. Activate the virtual environment:

   **On Windows:**

   .. code-block:: bash

      .venv\Scripts\activate

   **On macOS/Linux:**

   .. code-block:: bash

      source .venv/bin/activate

#. Install the package in editable mode with development dependencies:

   .. code-block:: bash

      pip install -e ".[pyfluent,tests]"

Run tests
=========

The test suite is offline-only (no live Fluent required):

.. code-block:: bash

   pytest -q

Lint with Ruff:

.. code-block:: bash

   ruff check src tests

Add a domain tool
=================

Domain tools are stateless backend/catalog operations registered in
``ansys.fluent.mcp.solve.lib.domain_tools``. To add one:

#. Write a typed coroutine in ``solve/lib/<area>.py``:

   .. code-block:: python

      async def my_tool_impl(
          backend: Backend,
          *,
          arg1: str,
          arg2: float | None = None,
      ) -> dict[str, Any]:
          ...

#. Append a ``DomainTool`` entry to ``get_solve_domain_tools()`` in
   ``solve/lib/domain_tools.py``.

``SolveMCP._register_tools()`` already registers everything returned by that function.

For a full walkthrough, see :doc:`../examples/implementing_a_tool`.

Install external backends
=========================

You can install packages through the ``ansys.fluent.mcp.solve_backends`` entry-point
group to provide additional execution backends. At construction time,
``SolveMCP`` discovers and merges external backends without modifying this repository.

Submit changes
==============

#. Create a feature branch from ``main``.
#. Make your changes with tests.
#. Run ``pytest`` and ``ruff check``.
#. Open a pull request against ``ansys/pyfluent-mcp``.

Next steps
==========

- To improve the documentation, see :ref:`ref_write_documentation`.
