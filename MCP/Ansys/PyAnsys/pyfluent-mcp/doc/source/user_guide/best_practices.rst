Best practices
==============

Session management
------------------

**Reuse Fluent sessions**
    Keep the same Fluent session open for multiple operations to improve performance.
    Only disconnect when you are finished or need a clean solver state.

**Clean shutdown**
    Always call ``disconnect`` when finished to free resources.

**Check status**
    Use ``session_status`` and ``solver_status`` to verify connection and iteration state
    before mutating operations.

Discover-generate-validate-execute loop
---------------------------------------

For almost every non-trivial setup change:

#. **Discover**: Use ``find_api``, ``get_state``, or ``list_named_objects`` before
   writing code.
#. **Validate**: Use ``validate_code`` to catch sandbox violations before execution.
#. **Execute**: Use ``run_code`` to apply the change.
#. **Verify**: Use ``summarize_setup`` or ``get_state`` to confirm the result.

Never skip discovery for path-dependent settings (URF, Courant, UTL vs classic tree).

Code execution
--------------

**Validate before running**
    Always call ``validate_code`` on generated or untrusted code before ``run_code``.

**Prefer targeted reads**
    Use ``get_state`` with specific paths rather than reading large subtrees.

**Use named-object tools**
    Use ``list_named_objects`` and ``find_named_object`` instead of guessing collection
    paths.

Mesh and diagnostics
--------------------

**Route mesh quality intents correctly**
    Use ``mesh_quality`` for skewness, orthogonal quality, aspect ratio, and ``mesh.check``
    output. Do not use ``run_code`` with invented PyFluent accessors.

**Use compare_files for case diffs**
    ``compare_files`` runs in isolated headless sessions and never touches the live
    workspace session.

Workflow design
---------------

**Modular workflows**
    Break complex setup into smaller, verifiable steps.

**Error recovery**
    When ``run_code`` fails, read the error, re-discover with ``get_state``, and
    regenerate rather than retrying blindly.

**Offline-first discovery**
    Use ``find_api`` and ``get_help`` even when offline; only call live tools when you
    need current values or mutations.

Performance
-----------

**Minimize reconnects**
    Avoid repeated ``connect`` / ``disconnect`` cycles within a single workflow.

**Batch related changes**
    Combine related ``run_code`` snippets when safe. However, smaller steps are preferred
    for easier debugging.

**Compare files sparingly**
    Using ``compare_files`` launches two headless Fluent sessions. Use it for explicit diff
    requests, not routine inspection.

Common patterns
---------------

Boundary condition setup
~~~~~~~~~~~~~~~~~~~~~~~~

#. ``connect`` and load case/mesh.
#. ``list_named_objects("setup.boundary_conditions.velocity_inlet")`` lists inlets.
#. ``get_state(["setup.boundary_conditions.velocity_inlet.inlet-1"]``) reads current values.
#. ``validate_code`` → ``run_code`` applies the desired settings update.
#. ``summarize_setup(scope="boundaries")`` verifies the boundary setup.

Convergence check
~~~~~~~~~~~~~~~~~

#. ``solver_status`` checks if Fluent is iterating.
#. ``simulation_report`` returns a structured solution report.
#. ``get_state(["solution.monitors.residual"]``) reads residuals.

Case comparison
~~~~~~~~~~~~~~~

#. ``compare_files(path_a="baseline.cas.h5", path_b="modified.cas.h5")``.
#. Reply with the pre-rendered ``summary`` markdown table verbatim.
