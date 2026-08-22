Tools and capabilities
======================

You can use these tools from the default MCP surface:

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Tool
     - Purpose
   * - ``session_status``
     - Inspect the active CFX session state.
   * - ``connect``
     - Connect to CFX resources.
   * - ``disconnect``
     - Release active sessions.
   * - ``cfx_workflow``
     - Coordinate lifecycle actions such as CFX-Pre, CFX-solver, and CFD-Post workflows.
   * - ``cfx_model_context``
     - Retrieve bounded model context, API help, named objects, and state snippets.
   * - ``run_code``
     - Run validated Python code in the configured backend.
   * - ``validate_code``
     - Pre-check Python code before execution.

Recommended tool order
----------------------

Use the tools in this order for most workflows:

#. Run ``session_status`` to see whether a backend is connected.
#. Run ``connect`` or ``cfx_workflow`` with ``start_pre`` when you need a
   CFX-Pre session.
#. Run ``cfx_model_context`` to inspect named objects, allowed values, or
   a selected state.
#. Run ``cfx_workflow`` for lifecycle operations such as importing meshes,
   writing solver input, running the solver, and opening results.
#. Use ``validate_code`` only when your task requires custom PyCFX code.
#. Run ``run_code`` only after validation and user approval in your MCP
   client.

Language-model ownership
------------------------

PyCFX-MCP is a deterministic leaf server and does not call a server-side
language model. Custom code authoring belongs in the MCP host or a higher-level
agent layer. This server validates and executes reviewed Python through
``validate_code`` and ``run_code``.

Common workflow actions
-----------------------

.. list-table::
   :header-rows: 1
   :widths: 24 76

   * - Action
     - Example request
   * - ``start_pre``
     - Start CFX-Pre to prepare a setup.
   * - ``import_mesh``
     - Import this mesh file into the active CFX-Pre session.
   * - ``write_def``
     - Write a solver input file for the current setup.
   * - ``start_solver``
     - Start the solver for this solver input file.
   * - ``wait_solver``
     - Wait until the current solver run finishes.
   * - ``get_results_file``
     - Return the result file produced by the solver run.
   * - ``open_post``
     - Open this result file in CFD-Post.

Context inspection actions
--------------------------

Ask for targeted context instead of broad dumps. For example:

- Find named boundary objects that contain ``inlet``.
- Show allowed values for a selected boundary setting.
- Return API help for a specific CFX path.
- Fetch state only for these paths and named-object types.
