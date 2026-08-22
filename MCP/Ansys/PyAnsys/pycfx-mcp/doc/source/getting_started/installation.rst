Installation
============

Check prerequisites
-------------------

- Python 3.12 or later
- A licensed local Ansys CFX installation for live CFX-Pre, CFX-Solver, or
  CFD-Post workflows
- `PyCFX <https://github.com/ansys/pycfx>`_ through ``ansys-cfx-core`` for live-session tools

Install PyCFX-MCP from PyPI
---------------------------

Use pip for the simplest installation:

.. code-block:: bash

   pip install ansys-cfx-mcp

Install PyCFX-MCP from source
-----------------------------

Install from the source repository:

.. code-block:: bash

   git clone https://github.com/ansys/pycfx-mcp.git
   cd pycfx-mcp
   pip install -e .

Install development dependencies
--------------------------------

If you plan to contribute, install development dependencies:

.. code-block:: bash

   pip install -e ".[dev]"

If you plan to build documentation, install documentation dependencies:

.. code-block:: bash

   pip install -e ".[doc]"

If you need both sets of dependencies in one environment, install both extras:

.. code-block:: bash

   pip install -e ".[dev,doc]"

Verify installation
-------------------

To verify your installation, run this command from the command-line tool to display help:

.. code-block:: bash

   ansys-cfx-mcp --help

Next steps
----------

- To launch your first CFX workflow, see :doc:`quick_start`.
- For detailed usage instructions, see the :doc:`../user_guide/index`.
