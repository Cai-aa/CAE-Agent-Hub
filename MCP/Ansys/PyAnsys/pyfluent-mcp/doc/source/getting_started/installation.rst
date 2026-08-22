Installation
============

Check prerequisites
-------------------

- Python 3.12 or later
- A licensed local Ansys Fluent installation (to launch or attach a solver)
- PyFluent_ (``ansys-fluent-core`` 0.27 or later) for live-session tools

Install from PyPI
-----------------

The easiest way to install PyFluent-MCP is to use pip:

.. code-block:: bash

   pip install ansys-fluent-mcp

To also pull in the local PyFluent backend (**required for live Fluent sessions**):

.. code-block:: bash

   pip install "ansys-fluent-mcp[pyfluent]"

Optional extras:

.. code-block:: bash

   # HDF5 file-probe support for compare_files on .h5/.cas.h5 files
   pip install "ansys-fluent-mcp[pyfluent,file-probe]"

Install from source
-------------------

To install from the source repository:

.. code-block:: bash

   git clone https://github.com/ansys/pyfluent-mcp.git
   cd pyfluent-mcp
   pip install -e ".[pyfluent]"

Install development dependencies
--------------------------------

To contribute to development, install the development dependencies:

.. code-block:: bash

   pip install -e ".[pyfluent,tests]"

To build the documentation, install the documentation dependencies:

.. code-block:: bash

   pip install -e ".[pyfluent,doc]"

Verify installation
-------------------

To verify that PyFluent-MCP is installed correctly, run the following command to display
the command-line help:

.. code-block:: bash

   ansys-fluent-mcp --help

Next steps
----------

- To launch your first Fluent session, see :doc:`quick_start`.
- For detailed usage instructions, see the :doc:`../user_guide/index`.
