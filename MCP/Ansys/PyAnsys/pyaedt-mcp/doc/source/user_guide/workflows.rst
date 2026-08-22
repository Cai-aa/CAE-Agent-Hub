.. _ref_workflows:

Workflows
=========

Use these practical, end-to-end workflows to run common AEDT tasks with
PyAEDT-MCP tools.

HFSS patch antenna
~~~~~~~~~~~~~~~~~~

See :doc:`../examples/hfss_patch_antenna_workflow` for a complete step-by-step
workflow that covers geometry creation, setup, solve, reporting, and screenshots.

Maxwell motor analysis
~~~~~~~~~~~~~~~~~~~~~~

#. Run ``connect_to_aedt`` or ``launch_aedt`` to connect to or launch AEDT.
#. Create a design with ``create_design`` and ``app_type="Maxwell3d"``.
#. Run ``run_python_code`` to build the motor geometry and assign materials.
#. Run ``run_python_code`` to assign windings, excitations, and motion setup.
#. Run ``analyze_design`` to analyze your design.
#. Run ``run_python_code`` to create a torque and speed report.

Icepak thermal analysis
~~~~~~~~~~~~~~~~~~~~~~~

#. Run ``connect_to_aedt`` or ``launch_aedt`` to connect to or launch AEDT.
#. Create a design with ``create_design`` and ``app_type="Icepak"``.
#. Run ``run_python_code`` to create the PCB, components, and heat sources.
#. Run ``run_python_code`` to assign boundary conditions.
#. Run ``analyze_design`` to analyze your design.
#. Run ``run_python_code`` to create a temperature contour plot.
#. Run ``export_results`` to export the simulation results.
