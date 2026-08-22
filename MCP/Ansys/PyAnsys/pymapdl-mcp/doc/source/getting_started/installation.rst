Installation
=============

Check prerequisites
-------------------

- Python 3.10 or later
- Ansys MAPDL installation (for running simulations)
- PyMAPDL (installed automatically as a dependency)

Install from PyPI
-----------------

The easiest way to install PyMAPDL-MCP is to use pip:

.. code-block:: bash

   pip install ansys-mapdl-mcp

Install from source
-------------------

To install from the source repository:

.. code-block:: bash

   git clone https://github.com/ansys/pymapdl-mcp.git
   cd pymapdl-mcp
   pip install -e .

Install development dependencies
---------------------------------

To contribute to development, install the development dependencies:

.. code-block:: bash

   pip install -e .[tests]

To build the documentation, install the documentation dependencies:

.. code-block:: bash

   pip install -e ".[doc]"

Verify installation
-------------------

To verify that PyMAPDL-MCP is installed correctly, run the following command to display
the command-line help:

.. code-block:: bash

   ansys-mapdl-mcp --help


Next steps
----------

- To launch your first MAPDL instance, see :doc:`quick_start`.
- For detailed usage instructions, see the :doc:`../user_guide/index` .
