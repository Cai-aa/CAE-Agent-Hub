Contribute
===========

Follow the `PyAnsys developer's guide <https://dev.docs.pyansys.com/>`__ when contributing to PyLumerical-MCP.

You can contribute to PyLumerical-MCP in several ways:

* Report bugs by opening an issue on GitHub.
* Contribute to the documentation with text and examples.

Install PyLumerical-MCP in developer mode
-----------------------------------------

#. Clone the repository:

   .. code:: bash

      git clone https://github.com/ansys/pylumerical-mcp

#. Create a clean Python virtual environment:

   .. code:: bash

      # Create a virtual environment
      python -m venv .venv

#. Activate the virtual environment:

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

#. Install PyLumerical in editable mode:

   .. code:: bash

      python -m pip install -U pip
      python -m pip install -e .

#. Install additional requirements as needed for documentation and tests:

   .. code:: bash

      python -m pip install .[tests]
      python -m pip install .[doc]

Follow code style guidelines
-----------------------------

Use `pre-commit`_ to ensure that your code meets the style requirements for PyLumerical before opening a pull request.
The automatic CI/CD pipeline uses the same checks as pre-commit, so you should run pre-commit locally first.

To install `pre-commit`_ and check all your files, run these commands:

.. code:: bash

    pip install pre-commit
    pre-commit run --all-files


You can also set up pre-commit as a Git hook to automatically run before you commit changes.

.. code:: bash

    pre-commit install

.. _pre-commit: https://pre-commit.com/

Run tests
---------

PyLumerical-MCP uses `pytest <https://docs.pytest.org/en/stable/>`__ for testing. To run the test suite,
install the test requirements and then run this command from the repository root:

.. code:: bash

    pytest

Build the documentation
-----------------------

PyLumerical-MCP uses `Sphinx <https://www.sphinx-doc.org/>`__ for documentation.

To build the documentation, install the documentation requirements and then run this
command from the ``/doc`` directory:

.. tab-set::

    .. tab-item:: Windows

        .. code-block:: bash

            .\\make.bat html

    .. tab-item:: Linux

        .. code-block:: bash

            make html

The documentation generated is in the ``doc/_build/html`` directory.

You can also clean the documentation build directory:

.. tab-set::

    .. tab-item:: Windows

        .. code-block:: bash

            .\\make.bat clean

    .. tab-item:: Linux

        .. code-block:: bash

            make clean
