.. _ref_best_practices:

Best practices
==============

Session management
------------------

Reuse the same Mechanical connection across a workflow whenever possible.
Repeated launch/connect cycles increase runtime and can create confusion in
stateful workflows.

- Call ``check_mechanical_status`` before starting each major step.
- Use ``connect_to_mechanical`` if a compatible instance already exists.
- Use ``disconnect_from_mechanical`` for clean shutdowns.

Scripting strategy
------------------

Use short, focused script calls rather than very large monolithic scripts.
This improves observability and error recovery.

- Use ``run_python_script`` for Mechanical API-heavy commands.
- Use ``run_python_code`` for lightweight Python processing and orchestration.
- Pass ``file_path`` to ``run_python_script`` when a script lives on disk.

For long setup scripts:

- Validate geometry import and named selections early.
- Save checkpoints with ``save_project`` after expensive setup steps.
- Keep scripts idempotent where possible to support reruns.

Model setup quality
-------------------

- Set units explicitly before defining loads and material parameters.
- Verify named selection scopes before applying boundary conditions.
- Check mesh quality and element sizing before solving.
- Confirm material assignment for every relevant body.

Solver and results
------------------

- Solve only after confirming analysis settings and boundary condition completeness.
- Use ``get_model_info`` after setup and after solve to validate state.
- Export only needed result objects to reduce file churn.
- Capture screenshots at key milestones for traceability.

File transfer hygiene
---------------------

- Use ``upload_file`` for all client-side artifacts (geometry and scripts).
- Keep working directory contents organized (prefix or suffix by workflow).
- Retrieve only required artifacts with ``download_file``.

AI workflow guidance
--------------------

Call ``get_guidelines_for`` at workflow boundaries (geometry, meshing,
analysis setup, and postprocessing). This reduces avoidable script mistakes and
keeps generated commands aligned with Mechanical best practices.

Next steps
----------

- See :doc:`tools_and_capabilities` for a complete list of available tools.
- Browse :doc:`/examples/workflows/usage_examples_index` for end-to-end workflow examples.
- See :doc:`configuration` for startup and transport options.
