Best practices
==============

Session management
------------------

**Reuse MAPDL instances**
    Keep the same MAPDL instance open for multiple operations to improve performance.
    Only restart when necessary, such as when clearing the database.

**Clean shutdown**
    Always disconnect properly from MAPDL instances to free resources.

**Error handling**
    Check tool results for errors and handle them gracefully in your workflow.

Command execution
-----------------

**Batch commands**
    Use ``run_multiple_mapdl_commands`` instead of individual commands for better performance.

**Verify state**
    Use ``check_mapdl_status`` periodically to verify the session state.

**Use comments**
    Add comments in the MAPDL session to document your workflow for clarity.

Data handling
-------------

**Extract efficiently**
    Extract only the data you need rather than loading entire result sets.

**Cache results**
    Store extracted data in Python variables to avoid repeated extraction.

**Validate data**
    Check that extracted data (such as positive stresses and reasonable displacements) make sense.

Visualization
-------------

**Prefer MAPDL backend for large models**
    The ``screenshot`` tool renders on the MAPDL server and returns only a lightweight
    image. For large or complex models this is significantly faster than custom PyVista
    plots, which transfer the full mesh to the client.

**Screenshots after key steps**
    Take screenshots after geometry definition, meshing, and solving to verify progress.
    Pass the plot command in ``commands`` (for example ``EPLOT``) and the ``screenshot``
    tool captures it as a base64 image returned inline to the AI assistant.

**Popup for full-resolution inspection**
    Set ``show_plot_on_popup=True`` on ``screenshot`` to also open the captured image in
    the system's default image viewer, allowing the user to inspect it at full resolution
    without leaving the chat.

**Custom plots for analysis**
    Use custom Matplotlib plots for detailed analysis beyond MAPDL's built-in capabilities.

**Export for documentation**
    Save high-quality plots for reports and documentation.

Workflow design
---------------

**Modular workflows**
    Break complex analyses into smaller, independent steps.

**Error recovery**
    Design workflows that can recover from errors without complete restart.

**Progress feedback**
    Include status updates and progress indicators in long-running workflows.

**Parameter validation**
    Validate all input parameters before sending to MAPDL.

Performance
-----------

**Minimize restarts**
    Avoid restarting MAPDL unless absolutely necessary.

**Efficient meshing**
    Use adaptive meshing and mesh refinement selectively.

**Result processing**
    Process results in Python rather than repeatedly querying MAPDL.

**Parallel operations**
    Consider launching multiple MAPDL instances for independent analyses.

Common patterns
---------------

Parameter sweep
~~~~~~~~~~~~~~~
#. Define parameter ranges.
#. Clear results between runs.
#. Update parameters.
#. Run analysis.
#. Extract results.
#. Aggregate results across runs.

Convergence study
~~~~~~~~~~~~~~~~~
#. Run analysis with coarse mesh.
#. Refine mesh selectively.
#. Re-run analysis.
#. Compare results.
#. Repeat until converged.

Sensitivity analysis
~~~~~~~~~~~~~~~~~~~~
#. Identify key parameters.
#. Vary parameters one at a time.
#. Record output for each variation.
#. Analyze parameter importance.
#. Focus detailed studies on important parameters.
