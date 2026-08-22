.. _ref_contributing:

==========
Contribute
==========

You can contribute to PyAEDT-MCP in several ways:

- Answer questions on the PyAEDT-MCP `Discussions <https://github.com/ansys/pyaedt-mcp/discussions>`_ page.
- Report bugs or request features on the PyAEDT-MCP `Issues <https://github.com/ansys/pyaedt-mcp/issues>`_ page.
- Submit pull requests with bug fixes, new features, or documentation improvements.

Before contributing, read
`Contributing <https://dev.docs.pyansys.com/how-to/contributing.html>`_
and `Coding style <https://dev.docs.pyansys.com/coding-style/index.html>`_
in the *PyAnsys developer's guide*. To generate useful release notes, follow
the guidelines in `Branch-naming conventions
<https://dev.docs.pyansys.com/how-to/contributing.html#branch-naming-conventions>`_
and `Commit-naming conventions
<https://dev.docs.pyansys.com/how-to/contributing.html#commit-naming-conventions>`_.

Answer discussions
==================

Answering questions on the PyAEDT-MCP `Discussions <https://github.com/ansys/pyaedt-mcp/discussions>`_ page
is the easiest way to contribute. Only a GitHub account is required. Engaging with discussions
deepens your understanding of the project and helps other users who are facing similar issues,
making the repository more welcoming and inclusive.

Post issues
===========

Use the `PyAEDT-MCP Issues page <https://github.com/ansys/pyaedt-mcp/issues>`_ to
report bugs, suggest improvements, or request features.

When possible, use these issue templates:

- **🐞 Bug, problem, or error**: File a bug report.
- **📖 Documentation issue**: Suggest modifications needed to the documentation.
- **🎓 Adding an example**: Propose a new example for the library.
- **💡 New feature**: Propose a new capability.

If your issue does not fit into any existing category, click
`Blank issue <https://github.com/ansys/pyaedt-mcp/issues/new>`_.

Contribute code or documentation
================================

#. Clone the repository and install in editable mode with development dependencies:

   .. code-block:: bash

      git clone https://github.com/ansys/pyaedt-mcp.git
      cd pyaedt-mcp
      pip install -e .
      pre-commit install

#. Run tests:

   .. code-block:: bash

      pytest -q

   .. note::
      Pull requests are accepted only when code coverage is greater than 80%.

#. Run linters:

   .. code-block:: bash

      pre-commit run --all-files

#. Build the documentation:

   .. code-block:: bash

      python -m sphinx -W -b html doc/source doc/_build/html

Write clear API reference documentation
=======================================

PyAEDT-MCP API reference documentation is generated automatically during Sphinx builds.

- AutoAPI extension: ``ansys_sphinx_theme.extension.autoapi`` (configured in
  ``doc/source/conf.py``)
- Source package: ``src/ansys/aedt/mcp``
- Entry page: :doc:`../api/index`

When you add or rename modules, classes, or functions under
``src/ansys/aedt/mcp``, rebuild the documentation to generate fresh API pages:

.. code-block:: bash

   python -m sphinx -W -b html doc/source doc/_build/html

To improve API reference quality, write clear NumPy-style docstrings for public
objects and keep module docstrings up to date.

For tool-authoring guidance, see :doc:`../examples/adding_new_tool`.
