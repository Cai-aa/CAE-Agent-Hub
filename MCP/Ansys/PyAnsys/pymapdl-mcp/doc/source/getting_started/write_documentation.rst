.. _ref_write_documentation:

===================
Write documentation
===================

Contributing documentation is a valuable way to improve PyMAPDL-MCP for everyone.

Understand the benefits of documentation
=========================================

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
    Located in the ``doc/source/api/`` directory.

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
    Located in the ``src/ansys/mapdl/mcp/`` directory.

Use RST format
==============

PyMAPDL-MCP documentation uses reStructuredText (RST) format and Sphinx as its documentation generator.

Basic RST syntax
~~~~~~~~~~~~~~~~

.. code-block:: rst

   Heading level 1
   ===============

   Heading level 2
   ---------------

   Heading level 3
   ~~~~~~~~~~~~~~~

   **Bold text** and *italic text*

   - Bullet point 1
   - Bullet point 2

   1. Numbered item
   2. Second item

   `Link text <https://example.com>`_

   .. code-block:: python

      # Code block with syntax highlighting
      print("Hello, PyMAPDL-MCP!")

   .. image:: ../images/example.png
       :width: 400
       :align: center
       :alt: Alternative text

Cross-references
~~~~~~~~~~~~~~~~

The following examples show how to link to other documentation pages:

.. code-block:: rst

   For more information, see :doc:`../user_guide/overview`.
   For contribution guidelines, see :ref:`ref_contributing`.

Set up documentation locally
============================

#. Install documentation dependencies:

   .. code-block:: bash

      pip install -e ".[doc]"

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

   For example, to add a new page to the **User guide** section, open the
   ``doc/source/user_guide/index.rst`` file and edit it like this:

   .. code-block:: rst

      .. toctree::
         :maxdepth: 2

         existing_page
         your_new_page    # Add this line

#. Rebuild the documentation using the ``make html`` command.
#. View the new page in your browser.

.. note::
   For a page template to start from, see `Use the documentation template`_.

Write good documentation
========================

**Be clear and concise.**

.. code-block:: rst

   ✓ Good: This tool launches a new MAPDL instance and automatically connects to it.

   ✗ Bad: This tool can be used for launching an instance of MAPDL and making a connection.

**Use examples.**

Include practical code examples:

.. code-block:: rst

   Example
   ~~~~~~~

   .. code-block:: python

      # Launch MAPDL with 4 processors
      mapdl = launch_mapdl_session(nproc=4)

**Explain why, not just how.**

.. code-block:: rst

   Use ``run_multiple_mapdl_commands`` instead of individual commands
   for better performance, as batch execution is significantly faster.

**Structure logically.**

- Start with an overview.
- Progress to specific details.
- End with examples or next steps.

**Add cross-references.**

.. code-block:: rst

   For complete tool reference, see :doc:`../api/ansys/mapdl/mcp/tools/index`.
   To learn more, see :doc:`../user_guide/best_practices`.

Document code
=============

Add comprehensive docstrings to functions using NumPy style:

.. code-block:: python

   def launch_mapdl_session(ctx: Context, nproc: int = 4) -> str:
       """
       Launch a new MAPDL instance.

       This tool starts a new MAPDL process and automatically
       establishes a connection to it for immediate use.

       Parameters
       ----------
       ctx : Context
           Tool execution context.
       nproc : int, default: 4
           Number of processors to use.

       Returns
       -------
       str
           Status message with MAPDL version and connection information.

       Examples
       --------
       >>> launch_mapdl_session(nproc=4)
       'MAPDL launched with 4 processors'

       Notes
       -----
       This tool is disabled when --connect-on-startup is used.

       See Also
       --------
       connect_to_mapdl : Connect to existing instance.
       disconnect_from_mapdl : Close connection.
       """
       # Implementation here
       pass

Build documentation
===================

**Clean build (remove old build files):**

.. code-block:: bash

   cd doc
   make.bat clean   # On Windows
   make clean       # On Linux/macOS
   make.bat html    # On Windows
   make html        # On Linux/macOS

**Check for warnings:**

.. code-block:: bash

   # The build output shows warnings and errors
   # Address any RST syntax errors before committing

Test documentation
==================

Test that your documentation builds without warnings:

.. code-block:: bash

   cd doc
   make.bat html SPHINXOPTS="-W --keep-going"

The ``-W`` flag treats warnings as errors, which is useful for CI.

Check documentation quality
===========================

Before submitting a pull request, check that your documentation meets these criteria:

- **No broken links:** Verify all cross-references work.
- **No syntax errors:** Check the build output for RST errors.
- **Clear structure:** Use consistent heading levels.
- **Proper formatting:** Check code blocks render correctly.
- **Accurate information:** Verify all examples work.
- **Consistent style:** Match the existing documentation style.

Common documentation issues
===========================

**Broken cross-reference**

.. code-block:: rst

   ✗ :doc:`../non_existent_page`
   ✓ :doc:`../user_guide/overview`

**Indentation error in code blocks**

.. code-block:: rst

   ✗ No blank line before code block
   .. code-block:: python
   def example():
       pass

   ✓ Blank line before code block
   .. code-block:: python

      def example():
          pass

**Unescaped special character**

.. code-block:: rst

   ✗ Use \* for multiplication
   ✓ Use ``*`` for multiplication

Submit documentation changes
============================

#. Build locally using the ``make html`` command.
#. Open the :file:`_build/html/index.html` file in your browser and verify your changes for clarity, accuracy, formatting, and working cross-references.
#. Commit changes:

   .. code-block:: bash

      git add doc/source/
      git commit -m "docs: Update installation instructions"

#. Create a pull request with these criteria:

   - A clear description of changes
   - Screenshots if there are visual changes
   - Links to any related issues

Use the documentation template
==============================

For new pages, use this template:

.. code-block:: rst

   .. _ref_my_page:

   ========
   My title
   ========

   Brief introduction paragraph explaining what this page covers
   and who should read it.

   Overview
   ========

   Provides a high-level explanation of the topic.

   Concepts
   ========

   Explain key concepts and terminology.

   How-to guides
   =============

   Give step-by-step instructions for common tasks.

   Examples
   ~~~~~~~~

   Supply code examples demonstrating usage.

   Advanced topics
   ===============

   Provide complex information or edge cases.

   Troubleshooting
   ===============

   Describe common issues and provide solutions.

   See also
   ========

   - :doc:`related_page1`
   - :doc:`related_page2`

View resources
==============

- `Sphinx documentation <https://www.sphinx-doc.org/>`_: Documentation generator
- `reStructuredText Primer <https://www.sphinx-doc.org/en/master/usage/restructuredtext/basics.html>`_: RST syntax reference for Sphinx documentation
- `NumPy Style guide <https://numpydoc.readthedocs.io/en/latest/format.html>`_: Docstring format used with the numpydoc extension for Sphinx
- `PyAnsys developer's guide <https://dev.docs.pyansys.com/>`_: How the PyAnsys project exposes Ansys technologies in client libraries within the Python ecosystem

Earn recognition
================

Documentation contributors are recognized in:

- Pull request comments
- Release notes
- Contributors file


See also
========

- :ref:`ref_contributing`: General contribution guidelines
- :ref:`ref_develop_pymapdl_mcp`: Code development guidelines
