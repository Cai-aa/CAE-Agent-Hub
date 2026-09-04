Installation
============

This page describes how to install PyLumerical-MCP.

Check prerequisites
-------------------

- Python 3.12 or later
- A valid Lumerical installation and license

For information on setting up your license, see the following article in the Lumerical Knowledge Base:
`Lumerical license configuration using environment variable and ini files
<https://optics.ansys.com/hc/en-us/articles/360025358714-Lumerical-license-configuration-using-environment-variable-and-ini-files>`_.

Create a virtual environment
----------------------------

To install PyLumerical-MCP, create a virtual environment. While its creation is not strictly necessary,
it is best practice to do so to avoid conflicts with other Python packages.

Create a virtual environment:

.. code:: bash

   # Create a virtual environment
   python -m venv .venv

Activate the virtual environment:

.. tab-set::

      .. tab-item:: Linux

         .. code-block:: bash

               source .venv/bin/activate

      .. tab-item:: Windows Command Prompt

         .. code-block:: bash

               .venv\\Scripts\\activate.bat

      .. tab-item:: Windows PowerShell

         .. code-block:: bash

               .venv\\Scripts\\Activate.ps1

Install from PyPI
------------------

To install from PyPI, first upgrade pip and then directly install PyLumerical-MCP:

.. code:: bash

   python -m pip install -U pip
   pip install ansys-lumerical-mcp

Install from GitHub
-------------------

Alternatively, clone the repository from GitHub and install it manually:

.. code:: bash

   git clone https://github.com/ansys/pylumerical-mcp.git
   cd pylumerical-mcp
   python -m pip install -U pip
   python -m pip install .

Verify the installation
-----------------------

Ensure that the installation was successful by running this command from your environment:

.. code:: bash

   ansys-lumerical-mcp
