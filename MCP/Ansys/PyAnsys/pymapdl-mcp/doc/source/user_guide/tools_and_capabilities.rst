Tools and capabilities
======================

Tool availability
-----------------

PyMAPDL-MCP dynamically enables and disables tools based on whether an MAPDL instance is
connected. This keeps the AI assistant's context small when MAPDL is not in use.

**Before connecting to MAPDL**, you can access these tools:

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Tool
     - Description
   * - ``check_mapdl_installed``
     - Check if MAPDL is installed on the system
   * - ``list_mapdl_instances``
     - Discover running MAPDL instances
   * - ``connect_to_mapdl``
     - Connect to an existing MAPDL instance
   * - ``launch_mapdl_session``
     - Launch and connect to a new MAPDL instance
   * - ``get_guidelines_for``
     - Workflow guidance and best-practice context tool

**After connecting to MAPDL**, you gain access to the full set of tools. When you call the
``disconnect_from_mapdl`` tool, the MAPDL-specific tools become unavailable.

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Tool
     - Description
   * - ``check_mapdl_status``
     - Get comprehensive MAPDL status
   * - ``run_mapdl_command``
     - Execute a single MAPDL command
   * - ``run_multiple_mapdl_commands``
     - Execute multiple MAPDL commands in batch
   * - ``disconnect_from_mapdl``
     - Disconnect from the MAPDL instance
   * - ``screenshot``
     - Capture the MAPDL graphics window as a static image
   * - ``run_python_code``
     - Execute Python/PyMAPDL code in a persistent session
   * - ``custom_plot``
     - Create custom matplotlib or PyVista plots
   * - ``upload_file``
     - Upload a local file to the MAPDL working directory
   * - ``download_file``
     - Download a file from the MAPDL working directory
   * - ``resume_model``
     - Restore a saved model from a ``.db`` or ``.cdb`` file
   * - ``open_results``
     - Enter POST1 and set the active results file for post-processing

.. note::
   When you use ``--connect-on-startup``, MAPDL connects at startup and all tools are immediately
   available (except ``connect_to_mapdl``, ``launch_mapdl_session``, and ``disconnect_from_mapdl``,
   which are locked).

Tool sets
---------

PyMAPDL-MCP groups tools into logical tool sets so MCP clients can discover capabilities by role.
These sets are exposed through the ``toolsets://definition`` resource.

.. list-table::
   :header-rows: 1
   :widths: 20 45 35

   * - Tool set
     - Purpose
     - Tools included
   * - ``session_management``
     - Manage MAPDL lifecycle and connection state
     - ``check_mapdl_installed``, ``check_mapdl_status``, ``launch_mapdl_session``,
       ``connect_to_mapdl``, ``disconnect_from_mapdl``, ``list_mapdl_instances``
   * - ``file_management``
     - Transfer files to/from MAPDL and manage saved models
     - ``upload_file``, ``download_file``, ``resume_model``, ``open_results``
   * - ``command_execution``
     - Execute MAPDL commands and command batches
     - ``run_mapdl_command``, ``run_multiple_mapdl_commands``, ``run_python_code``
   * - ``visualization``
     - Capture or generate result visualizations
     - ``screenshot``, ``custom_plot``
   * - ``python_execution``
     - Execute arbitrary Python or PyMAPDL code in the persistent session
     - ``run_python_code``

The ``list_tool_sets()`` resource function returns the complete tool set definitions,
allowing client applications to discover and organize available capabilities.

Using the tools
---------------

Running MAPDL commands
~~~~~~~~~~~~~~~~~~~~~~

Use ``run_mapdl_command`` for single commands:

*"Run VPLOT on the MAPDL instance."*

For multiple commands, use ``run_multiple_mapdl_commands``, which uses MAPDL's ``input_strings``
method for batch execution. This is significantly faster than running commands one by one:

*"Run these commands: /PREP7, ET,1,SOLID185, MP,EX,1,200E9."*

Custom Python code execution
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Use ``run_python_code`` to execute arbitrary Python and PyMAPDL code in a persistent session:

*"Execute this Python code: displacements = mapdl.get_array('NODE', item1='U', it1num='Y'); print(f'Max displacement: {displacements.max()}')."*

This is useful for:

- Custom data processing and analysis
- Advanced PyVista visualizations
- NumPy/Pandas data manipulation
- Complex computations not available through direct MAPDL commands

Creating custom plots
~~~~~~~~~~~~~~~~~~~~~

Use ``custom_plot`` to create Matplotlib or PyVista plots that are not available in MAPDL's
native plotting:

*"Create a Matplotlib plot showing nodal displacements versus node number."*

.. important::
   ``custom_plot`` is for plots that MAPDL cannot produce natively. For standard MAPDL plots
   (``APLOT``, ``LPLOT``, ``KPLOT``, ``PLNSOL``, etc.), use the MAPDL commands together with
   the ``screenshot`` tool.

Capturing plots
~~~~~~~~~~~~~~~

Use the ``screenshot`` tool to run a MAPDL plot command and capture the result as an image:

*"Show a plot of the mesh."*

*"Capture the average stress distribution."*

The tool returns the image directly so the AI assistant can display it inline. It supports all
MAPDL native plot commands:

- Geometry: ``APLOT``, ``LPLOT``, ``KPLOT``, ``VPLOT``
- Mesh: ``EPLOT``, ``NPLOT``
- Post-processing: ``PLNSOL``, ``PLESOL``, ``PLDISP``

**Parameters**

``commands``
    Optional APDL commands to run before capturing the screenshot
    (for example ``EPLOT`` or ``SET,LAST``).

``show_plot_on_popup``
    When ``True``, the captured image is also opened in the system's default image
    viewer so the user can inspect it at full resolution. Default is ``False``.

Python code execution
~~~~~~~~~~~~~~~~~~~~~

- Run Python code: Execute arbitrary Python code in the persistent session *(requires MAPDL connection)*.
- Integrate with data analysis: Use NumPy, Pandas, and other Python libraries.

File management
~~~~~~~~~~~~~~~

Use the file-management tools to transfer files between the local filesystem and the MAPDL
working directory, and to restore saved models or open result files for post-processing.

**Uploading files to MAPDL**

Use ``upload_file`` to transfer a local file (database, archive, or input file) to the MAPDL
working directory before referencing it with MAPDL commands:

*"Upload /home/user/project/beam.db to MAPDL."*

**Downloading files from MAPDL**

Use ``download_file`` to retrieve output files (result files, logs, databases) to the local
filesystem. Glob patterns such as ``"file*"`` are supported:

*"Download file.rst to /home/user/results."*

*"Download all files matching file* from MAPDL."*

**Resuming a saved model**

Use ``resume_model`` to restore a previously saved MAPDL model from a ``.db`` binary database
file or a ``.cdb`` coded ASCII archive file. If the file is not yet in the MAPDL working
directory, upload it first with ``upload_file``:

*"Resume the model from beam.db."*

*"Load the archived model from model.cdb."*

**Opening result files for post-processing**

Use ``open_results`` to switch MAPDL into the POST1 post-processor and optionally point it at
a specific RST result file. After calling this tool, you can query displacements, stresses, and
other result quantities:

*"Open the result file for post-processing."*

*"Enter POST1 and load beam.rst."*

**File-path resources**

Three MCP resources expose the paths to key MAPDL output files so the AI assistant can share
them with other tools or applications:

.. list-table::
   :header-rows: 1
   :widths: 45 55

   * - Resource URI
     - Returns
   * - ``files://mapdl/working_directory``
     - Absolute path to the MAPDL working directory
   * - ``files://mapdl/rst_path``
     - Expected path to ``<jobname>.rst``
   * - ``files://mapdl/db_path``
     - Expected path to ``<jobname>.db``


Workflow examples
-----------------

Linear static analysis
~~~~~~~~~~~~~~~~~~~~~~

#. Launch MAPDL instance.
#. Define geometry (blocks, cylinders, and so on).
#. Define materials and element types.
#. Mesh the geometry.
#. Apply boundary conditions and loads.
#. Run solution.
#. Extract and visualize results.

Parametric study
~~~~~~~~~~~~~~~~

#. Set up the base MAPDL model.
#. Define parameter ranges.
#. Update parameters, run analysis, and extract results for each parameter combination.
#. Analyze and plot parameter sensitivity.

Result postprocessing
~~~~~~~~~~~~~~~~~~~~~

#. Run or load MAPDL analysis.
#. Extract result data.
#. Create custom visualizations.
#. Generate analysis reports.

Loading and post-processing an external result file
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

#. Upload the RST file: ``upload_file("/local/path/beam.rst")``.
#. Open the result file: ``open_results("beam")``.
#. Query result quantities (displacements, stresses, etc.) with MAPDL commands.
#. Download the results if needed: ``download_file("beam.rst", "/local/results/")``.

Restoring a saved model
~~~~~~~~~~~~~~~~~~~~~~~

#. Upload the database file: ``upload_file("/local/path/model.db")``.
#. Restore the model: ``resume_model("model", "db")``.
#. Inspect geometry, mesh, and boundary conditions.
#. Continue with further pre-processing, solution, or post-processing steps.

Interpreting tool results
-------------------------

Most tools return structured results with one of these outcomes:

- Success: A status or result message.
- Error: A detailed message describing what failed and how to correct it.

Additionally, some tools might return data as structured payloads (for example, JSON text or image content).

When building workflows, always validate results before continuing to the next step.
If a tool returns an error message, adjust the request and retry instead of assuming
that downstream steps are still valid.

Feature reference
-----------------

For the documentation of all available tools, including parameters and return values, see
:doc:`../api/ansys/mapdl/mcp/tools/index`.

Best practices
--------------

For recommendations on using PyMAPDL-MCP effectively, see :doc:`best_practices`.
