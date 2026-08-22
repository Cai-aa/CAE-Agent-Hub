Develop PyCFX-MCP
=================

Review naming conventions
-------------------------

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Surface
     - Name
   * - GitHub repository
     - ``pycfx-mcp``
   * - PyPI distribution
     - ``ansys-cfx-mcp``
   * - Python package
     - ``ansys.cfx.mcp``
   * - Console script
     - ``ansys-cfx-mcp``
   * - Documentation title
     - PyCFX-MCP

Set up your development environment
-----------------------------------

Create and activate a virtual environment, and then install the package in
editable mode:

.. code-block:: bash

   python -m venv .venv
   source .venv/bin/activate
   pip install -e ".[dev,doc]"

On Windows, activate the environment with ``.venv\Scripts\activate``.

Run tests
---------

.. code-block:: bash

   pytest -q

Run lint checks
---------------

.. code-block:: bash

   ruff check src tests

Build documentation
-------------------

From the ``doc`` directory, run:

.. code-block:: bash

   make html

On Windows, run:

.. code-block:: powershell

   .\make.bat html
