.. _ref_write_documentation:

===================
Write documentation
===================

Contributing documentation is a valuable way to improve PyFluent-MCP for everyone.

Understand the benefits of documentation
========================================

Good documentation achieves these goals:

- Helps new users get started quickly.
- Reduces support questions.
- Makes the project more professional.
- Creates opportunities for learning.
- Builds community engagement.

Understand documentation types
==============================

**API documentation**
    Detailed reference for MCP tools, parameters, return values, and examples.
    Generated automatically from in-code docstrings by the
    ``ansys_sphinx_theme.extension.autoapi`` extension and rendered under
    ``api/index``. To update it, edit the docstrings in
    ``src/ansys/fluent/mcp/``.

**User guides**
    How-to guides, tutorials, and best practices.
    Located in the ``doc/source/user_guide/`` directory.

**Getting started**
    Installation, quick start, and initial setup guides.
    Located in the ``doc/source/getting_started/`` directory.

**Examples**
    Practical usage examples and tutorials.
    Located in the ``doc/source/examples/`` directory.

**API docstrings**
    In-code documentation of functions and classes.
    Located in the ``src/ansys/fluent/mcp/`` directory.

Use RST format
==============

PyFluent-MCP documentation uses reStructuredText (RST) format and Sphinx as its
documentation generator.

Set up documentation locally
============================

#. Install documentation dependencies:

   .. code-block:: bash

      pip install -e ".[pyfluent,doc]"

#. Navigate to the ``doc`` directory:

   .. code-block:: bash

      cd doc

#. Build HTML documentation:

   .. code-block:: bash

      make.bat html    # On Windows
      make html        # On Linux/macOS

#. View in your browser by opening the ``_build/html/index.html`` file.

Edit an existing page
=====================

#. Navigate to the RST file in the ``doc/source/`` directory.
#. Make your changes.
#. Save the file.
#. Rebuild the documentation using the ``make html`` command.
#. View your changes in your browser.

Create a page
=============

#. Create a RST file in the appropriate directory.
#. Write your content.
#. Add the file to the toctree in the parent ``index.rst`` file.
#. Rebuild the documentation using the ``make html`` command.

Write good documentation
========================

**Be clear and concise.**

.. code-block:: rst

   ✓ Good: This tool launches a new Fluent session through PyFluent.

   ✗ Bad: This tool can be used for launching an instance of Fluent and making a connection.

**Use examples** and **explain why, not just how.**

**Add cross-references** to related pages using ``:doc:`` and ``:ref:`` directives.

Run documentation checks
========================

Before submitting a pull request:

.. code-block:: bash

   cd doc
   make html
   make linkcheck

The CI pipeline also runs Ansys documentation style checks via Vale.

Next steps
==========

- See :ref:`ref_contributing` for general contribution guidelines.
- See :ref:`ref_develop_pyfluent_mcp` for development setup.
