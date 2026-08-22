.. _ref_contributing:

==========
Contribute
==========

You can contribute to PyMechanical-MCP in several ways:

- Answer discussions
- Post issues
- Contribute code or documentation

Before contributing, read `Contributing
<https://dev.docs.pyansys.com/how-to/contributing.html>`_ and `Coding style
<https://dev.docs.pyansys.com/coding-style/index.html>`_ in the *PyAnsys developer's
guide*. To generate useful release notes, follow the guidelines in
`Branch-naming conventions
<https://dev.docs.pyansys.com/how-to/contributing.html#branch-naming-conventions>`_
and `Commit-naming conventions
<https://dev.docs.pyansys.com/how-to/contributing.html#commit-naming-conventions>`_.

Answer discussions
==================

Answering discussions is an excellent way to contribute without any setup.
Only a GitHub account is required. Engaging with discussions deepens your
understanding of the project, helps other users facing similar issues, and
makes the repository more welcoming and inclusive.

To see where you can help, visit the `PyMechanical-MCP Discussions
<https://github.com/ansys/pymechanical-mcp/discussions>`_ page.

Post issues
===========

Use the `PyMechanical-MCP Issues
<https://github.com/ansys/pymechanical-mcp/issues>`_ page to report bugs,
suggest improvements, and request features.

When possible, use these issue templates:

- 🐞 **Bug, problem, or error**: File a bug report.
- 📖 **Documentation issue**: Suggest modifications needed to the documentation.
- 🎓 **Adding an example**: Propose a new example for the library.
- 💡 **New feature**: Propose a new feature for the library.

If your issue does not fit into any existing category, click
`Blank issue <https://github.com/ansys/pymechanical-mcp/issues/new>`_.

Contribute code or documentation
================================

#. Clone and install in editable mode with development dependencies:

   .. code-block:: bash

      git clone https://github.com/ansys/pymechanical-mcp.git
      cd pymechanical-mcp
      pip install -e ".[dev]"
      pre-commit install

#. Run tests:

   .. code-block:: bash

      # Fast unit tests (default CI matrix path)
      pytest -m "not integration"

      # Integration tests (requires Mechanical)
      pytest -m integration

#. Run linters:

   .. code-block:: bash

      pre-commit run --all-files

#. Build documentation:

   .. code-block:: bash

      python -m sphinx -W -b html doc/source doc/_build/html

Next steps
==========

- To implement a custom tool, see :doc:`/examples/implementing_a_tool`.
- For an overview of available tools, see :doc:`/user_guide/tools_and_capabilities`.
- For the complete API reference, see :doc:`/api/index`.
