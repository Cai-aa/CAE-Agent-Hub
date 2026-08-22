.. _ref_develop_pymapdl_mcp:

===================
Develop PyMAPDL-MCP
===================

Set up your development environment and start contributing code to PyMAPDL-MCP.

Architecture
============

PyMAPDL-MCP is built on the ``PyAnsysBaseMCP`` framework (from ``ansys-common-mcp``), which
is itself built on top of FastMCP. The server lifecycle has three phases:

**Startup**

- Initializes a persistent Python session for custom code execution.
- If ``--connect-on-startup`` is used, connects to an existing MAPDL instance.
- Otherwise, waits for a dynamic connection through the ``connect_to_mapdl`` or
  ``launch_mapdl_session`` tools.

**Runtime**

- Exposes MCP tools for MAPDL interaction.
- Manages dynamic MAPDL connections through the tools.
- Executes commands in both the MAPDL session and the persistent Python session.
- Provides workflow guidance through the ``get_guidelines_for`` context tool.
- Dynamically enables and disables tools based on the MAPDL connection state.

**Shutdown**

- Gracefully disconnects from MAPDL.
- Cleans up the persistent Python session resources.

App context
-----------

The server uses a strongly typed ``PyMAPDLAppContext`` dataclass that holds:

- The active MAPDL instance connection
- The persistent Python session for custom code execution
- Transport configuration (STDIO or HTTP)
- Connection settings (IP, port, auto-connect flags)
- Command history tracking

Tool context and lifecycle
--------------------------

Each tool receives a FastMCP context object (``Context``) that provides:

- Access to the app context (``ctx.application_context``)
- Request and response metadata
- Logging utilities

The MAPDL lifecycle follows these phases:

#. Initialize without an active MAPDL connection.
#. Connect using ``launch_mapdl_session`` or ``connect_to_mapdl``.
#. Execute MAPDL and Python tools in the active session.
#. Disconnect using ``disconnect_from_mapdl``.
#. Reset state and allow a new connection.

Errors in context operations are logged and returned as tool errors to allow graceful recovery.
Context internals are intended for contributors and can change between releases. For stable
client behavior, rely on the documented MCP tools rather than internal context attributes.

Check prerequisites
===================

Before you begin, ensure you have:

- Python 3.10 or higher
- Git installed
- A text editor or IDE (such as Visual Studio Code or PyCharm)
- A GitHub account

Clone the repository
====================

#. Fork the GitHub repository.
#. Clone your fork locally:

   .. code-block:: bash

      git clone https://github.com/YOUR_USERNAME/pymapdl-mcp.git
      cd pymapdl-mcp

#. Add the upstream repository as a remote:

   .. code-block:: bash

      git remote add upstream https://github.com/ansys/pymapdl-mcp.git

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

      pip install -e .[tests]

#. Install pre-commit hooks:

   .. code-block:: bash

      pre-commit install

   This ensures code quality checks run automatically before each commit.

Explore the project structure
=============================

.. code-block::

   pymapdl-mcp/
   ├── src/ansys/mapdl/mcp/          # Main package source
   │   ├── __init__.py
   │   ├── __main__.py               # Entry point
   │   ├── contexts.py               # App context and guidelines
   │   ├── helpers.py                # Utility functions
   │   ├── mcp.py                    # MCP server setup
   │   ├── prompts.py                # Prompt definitions
   │   ├── server.py                 # Server implementation
   │   ├── tools.py                  # MCP tools
   │   └── python_helper/            # Python session helpers
   ├── tests/                        # Test suite
   ├── doc/                          # Documentation
   ├── docker/                       # Docker configuration
   ├── pyproject.toml               # Project metadata
   └── README.md                    # Main README

Follow the development workflow
===============================

#. Create a feature branch:

   .. code-block:: bash

      git checkout -b feature/your-feature-name

#. Make your changes:

   - Add or modify relevant files.
   - Add or modify tests as needed.
   - Update documentation if applicable.

#. Run tests:

   .. code-block:: bash

      # Run unit tests (no MAPDL required)
      pytest -m "not integration"

      # Run all tests with coverage
      pytest --cov=ansys.mapdl.mcp --cov-report=html

#. Check code quality:

   .. code-block:: bash

      # Run pre-commit checks manually
      pre-commit run --all-files

#. Commit your changes:

   .. code-block:: bash

      git add .
      git commit -m "feat: Add your feature description"

      # Pre-commit hooks will run automatically

#. Push to your fork:

   .. code-block:: bash

      git push origin feature/your-feature-name

#. Create a pull request (PR) on GitHub:

   - Go to the main repository on GitHub.
   - Click **New Pull Request**.
   - Select your feature branch.
   - Fill in the PR description.
   - Submit the PR.

Follow code conventions
=======================

**Branch naming**

- Features: ``feature/short-description``
- Fixes: ``fix/short-description``
- Documentation: ``doc/short-description``
- Tests: ``test/short-description``

**Commit messages**

Use conventional commits format:

.. code-block:: bash

   feat: Add new tool for XYZ feature.
   fix: Correct handling of edge case.
   docs: Update installation instructions.
   test: Add tests for feature ABC.
   refactor: Simplify tool implementation.
   chore: Update dependencies.

**Code style**

- Follow PEP 8 and the `Coding style <https://dev.docs.pyansys.com/coding-style/index.html>`_.
- Use type hints for all functions.
- Write docstrings following NumPy style.
- Keep line lengths to 100 characters or less.
- Format code with Black and isort (run automatically via pre-commit).

Add a new tool
==============

#. Edit the ``src/ansys/mapdl/mcp/tools.py`` file.

#. Add your tool using the ``@app.tool()`` decorator:

   .. code-block:: python

      @app.tool()
      def your_new_tool(ctx: Context, param1: str, param2: int = 10) -> str:
          """
          Brief description of what this tool does.

          Parameters
          ----------
          ctx : Context
              Tool execution context with access to MAPDL.
          param1 : str
              Description of param1.
          param2 : int, default: 10
              Description of param2.

          Returns
          -------
          str
              Description of what this tool returns
          """
          mapdl = ctx.application_context.mapdl

          if mapdl is None:
              return "Error: No MAPDL connection available"

          try:
              # Your implementation here
              result = mapdl.your_operation()
              return f"Success: {result}"
          except Exception as e:
              return f"Error: {str(e)}"

#. Write tests in the ``tests/test_tools.py`` file.

#. Ensure the tool docstring is complete so AutoAPI generates accurate documentation under
   :doc:`../api/ansys/mapdl/mcp/tools/index`.

#. Add a usage example if appropriate in the ``doc/source/examples/`` directory.

Add or modify documentation
===========================

You can tag tools with the ``@app.tool()`` decorator to selectively turn them off at runtime. After applying a tag, call ``app.disable()`` with that tag when the condition
applies (for example, when ``--connect-on-startup`` locks the connection):

.. code-block:: python

   # Tag the tool so it can be turned off as a group
   @app.tool(tags={"locked_connection"})
   def connect_to_mapdl(ctx: Context, port: int = 50052, ip: str = "localhost") -> str:
       ...

   # Turn off all tools with this tag when the connection is locked
   app.disable(tags={"locked_connection"})

#. Edit RST files in the ``doc/source/`` directory.

#. Build documentation locally:

   .. code-block:: bash

      cd doc
      make.bat html    # On Windows
      make html        # On Linux/macOS

#. View the documentation by opening the ``_build/html/index.html`` file in your browser.

#. Commit changes to your documentation files.

Run tests
=========

PyMAPDL-MCP includes a comprehensive test suite with more than 40 tests.

**Run unit tests (recommended for development):**

.. code-block:: bash

   pytest -m "not integration"

**Run all tests with coverage:**

.. code-block:: bash

   pytest --cov=ansys.mapdl.mcp --cov-report=html

**Run a specific test file:**

.. code-block:: bash

   pytest tests/test_tools.py -v

**Run integration tests (requires MAPDL):**

.. code-block:: bash

   pytest -m integration

Test coverage goal
------------------

Aim for greater than 80% test coverage on new code. Open the ``htmlcov/index.html`` file
after report generation to view the report:

.. code-block:: bash

   pytest --cov=ansys.mapdl.mcp --cov-report=html

Get help
========

If you need help:

- Check issues on the `PyMAPDL-MCP Issues <https://github.com/ansys/pymapdl-mcp/issues>`_ page.
- Ask a question on the `PyMAPDL-MCP Discussions <https://github.com/ansys/pymapdl-mcp/discussions>`_ page.
- Review the `PyAnsys developer's guide <https://dev.docs.pyansys.com/>`_.
- Check `PyMAPDL documentation <https://mapdl.docs.pyansys.com/>`_.

Submit your work
================

When your feature is ready:

#. Use the ``pytest -m "not integration"`` command to ensure all tests pass.
#. Use the ``pre-commit run --all-files`` command to ensure code quality.
#. Update relevant documentation.
#. Add tests for new features to ensure greater than 80% coverage.
#. Create a PR with:

   - A clear description of changes
   - References to related issues (such as ``Fixes #123``)
   - A list of changes made
   - A note of any breaking changes

Follow PR guidelines
====================

- Keep PRs focused on a single feature or fix.
- Include tests for new features.
- Update documentation as needed.
- Respond to review feedback.
- Keep the PR up to date with the main branch.
- Use GitHub's **Squash and merge** option when possible to keep the history clean.

Earn recognition
================

Contributors are recognized in:

- PR comments
- Release notes
- Contributors file (as applicable)


See also
========

- :ref:`ref_contributing`: General contribution guidelines
- :ref:`write_documentation`: Documentation contribution guide
