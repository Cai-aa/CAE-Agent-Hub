.. _ref_tools_and_capabilities:

Tools and capabilities
======================

Tool availability model
-----------------------

PyMechanical-MCP uses connection-aware visibility.

- **Offline-capable tools** are available before any Mechanical session.
- **Live-session tools** use ``REQUIRES_MECHANICAL_TAG`` and remain hidden
  until you successfully call ``launch_mechanical`` or ``connect_to_mechanical``.
- If you use ``--connect-on-startup``, live-session tools are available
  immediately, and PyMechanical-MCP locks the connection lifecycle tools.
- If you use ``--static-tools``, all tools (including live-session tools) are
  visible from startup. Calling a live-session tool before connecting returns
  a clear "No Mechanical connection available" message instead of the tool
  being hidden. Use this if your MCP client does not reliably refresh its
  tool list when the server dynamically enables tools. See
  :doc:`configuration` for details.

Always available (before connection)
------------------------------------

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Tool
     - Description
   * - ``check_mechanical_installed``
     - Verify that Mechanical is installed and discoverable.
   * - ``check_mechanical_status``
     - Inspect current MCP connection state.
   * - ``list_mechanical_instances``
     - List running Mechanical processes.
   * - ``launch_mechanical``
     - Start a new Mechanical session. GUI is preferred by default, and batch mode remains available.
   * - ``connect_to_mechanical``
     - Attach to an existing Mechanical instance.
   * - ``get_guidelines_for``
     - Return workflow guidance by topic.

Available after connection
--------------------------

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Tool
     - Description
   * - ``disconnect_from_mechanical``
     - Gracefully detach from Mechanical.
   * - ``run_python_code``
     - Execute Python snippets in the persistent session.
   * - ``create_custom_plot``
     - Produce custom plots from analysis data.
   * - ``clear_mechanical``
     - Clear context and release session resources.
   * - ``run_python_script``
     - Execute a Mechanical script string or read one from a local file with ``file_path``.
   * - ``save_project``
     - Save active project.
   * - ``open_project``
     - Open an existing MECHDB project.
   * - ``upload_file``
     - Upload local file to Mechanical working directory.
   * - ``download_file``
     - Download file from Mechanical working directory.
   * - ``list_files``
     - List files in working directory.
   * - ``solve_analysis``
     - Solve active analysis system.
   * - ``get_model_info``
     - Return a structured model summary (geometry, mesh, analyses, results).
   * - ``screenshot``
     - Capture current Mechanical view.
   * - ``get_mechanical_logs``
     - Retrieve Mechanical logs for diagnostics.
   * - ``export_results``
     - Export result objects and artifacts.

.. note::
  When you run with ``--connect-on-startup``, PyMechanical-MCP disables
  the ``launch_mechanical``, ``connect_to_mechanical``, and
  ``disconnect_from_mechanical`` tools by design.

Guideline topics
----------------

``get_guidelines_for`` supports these topic values:

- ``workflow``
- ``geometry``
- ``materials``
- ``meshing``
- ``analysis_setup``
- ``boundary_conditions``
- ``solution``
- ``postprocessing``
- ``named_selections``
- ``general``

Tool set discovery resource
---------------------------

PyMechanical-MCP exposes ``toolsets://definition`` for service-side discovery.
The payload groups tools into:

- lifecycle
- scripting
- project-management
- file-management
- simulation
- inspection
- results
- guidelines

This resource is read-only metadata. It does not modify runtime behavior.

Example workflows
-----------------

Static structural run
~~~~~~~~~~~~~~~~~~~~~

#. ``check_mechanical_status``
#. ``launch_mechanical`` or ``connect_to_mechanical``
#. ``upload_file`` (geometry)
#. ``run_python_script`` (import geometry, assign material, and mesh)
#. ``run_python_script`` (apply boundary conditions and loads)
#. ``solve_analysis``
#. ``export_results`` and ``screenshot``

Modal analysis
~~~~~~~~~~~~~~

#. Connect to Mechanical.
#. Import the model and define fixed supports.
#. Create modal analysis settings with script tools.
#. Run ``solve_analysis``.
#. Use ``create_custom_plot`` for mode-shape reporting.

Checks after solving
~~~~~~~~~~~~~~~~~~~~~

#. ``get_model_info`` for verifying solved state
#. ``get_mechanical_logs`` for warnings and errors
#. ``run_python_code`` for custom data extraction
#. ``export_results`` for report artifacts

Feature reference
-----------------

For complete parameter signatures and return values for all tools, see
:doc:`/api/index`.

Next steps
----------

- See :doc:`best_practices` for recommendations on using the tools effectively.
- Explore :doc:`/examples/workflows/usage_examples_index` for end-to-end workflow examples.
- For startup and environment options, see :doc:`configuration`.
