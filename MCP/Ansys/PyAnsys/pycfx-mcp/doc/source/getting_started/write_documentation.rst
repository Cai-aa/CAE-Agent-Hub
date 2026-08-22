Writing documentation
=====================

Write documentation source files in reStructuredText (RST) files under the
``doc/source`` directory. Keep pages short, task-oriented, and linked from the nearest
section index.

Build the documentation locally before you open a pull request:

.. code-block:: powershell

   cd doc
   .\make.bat html

On Linux or macOS, run:

.. code-block:: bash

   make -C doc html

When a change is user-visible, add a `Towncrier <https://towncrier.readthedocs.io/en/stable/>`_ fragment in the
``doc/changelog.d`` directory using the pull request number and category.

For example:

``123.added.rst`` or ``123.documentation.rst``.
