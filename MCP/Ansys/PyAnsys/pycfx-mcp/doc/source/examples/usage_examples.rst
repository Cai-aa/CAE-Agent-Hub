Usage examples
==============

Check session status
--------------------

Before you run CFX operations, ask the MCP client to call
``session_status``. This shows whether a backend is connected and which
capabilities are available.

Example prompt:

.. code-block:: text

	Check the current CFX MCP session status and tell me which actions are available.

Inspect model context
---------------------

Use ``cfx_model_context`` for bounded inspection tasks, such as finding named
objects, requesting API help, or retrieving current state snippets.

Example prompts:

.. code-block:: text

	Show a compact summary of the active CFX setup.

.. code-block:: text

	Find named boundary objects that contain inlet and return at most 10 matches.

.. code-block:: text

	Show API help and allowed values for the selected flow analysis path.

Run a workflow action
---------------------

Use ``cfx_workflow`` for common CFX lifecycle tasks, including writing solver
input, running a steady-state solver workflow, finding results files, and
opening results in CFD-Post.

Example prompts:

.. code-block:: text

	Start CFX-Pre and import the mesh from C:/cases/mixer/mixer.gtm.

.. code-block:: text

	Write a solver input file to C:/cases/mixer/mixer.def.

.. code-block:: text

	Start the CFX solver for C:/cases/mixer/mixer.def, wait for completion, and report the result file.

.. code-block:: text

	Open the result file in CFD-Post.

Validate and run code
---------------------

Use ``validate_code`` before running reviewed Python snippets through
``run_code``.

Example prompt:

.. code-block:: text

	Validate this small PyCFX snippet for inspecting the selected boundary condition before execution.

Use reviewed code for custom model edits or detailed inspection. For standard
lifecycle operations, use ``cfx_workflow`` so you receive typed results and
consistent errors.

Handle errors
-------------

If a tool returns an error, inspect the message and retry with more context.
Common recovery steps include checking ``session_status``, narrowing your
``cfx_model_context`` query, or supplying missing inputs before you run a
workflow action.
