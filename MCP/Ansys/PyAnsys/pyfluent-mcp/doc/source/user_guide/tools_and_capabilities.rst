Tools and capabilities
======================

Tool surface
------------

PyFluent-MCP exposes **25 tools** organized into 6 groups:

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Group
     - Tools
   * - Connection & session
     - ``connect``, ``disconnect``, ``session_status``, ``solver_status``, ``manage_fluent``
   * - Schema discovery
     - ``find_api``, ``get_help``, ``get_state``, ``get_targeted_context``
   * - Named objects
     - ``list_named_objects``, ``find_named_object``, ``select_named_objects``
   * - Execution & validation
     - ``run_code``, ``validate_code``
   * - Reporting & inspection
     - ``summarize_setup``, ``simulation_report``, ``screenshot``
   * - Domain tools
     - ``mesh_quality``, ``list_fields``, ``compare_files``, ``probe_path``,
       ``get_active_status``, ``get_allowed_values``,
       ``describe_named_object_template``, ``describe_path``

Live versus offline tools
-------------------------

**Offline-capable tools** work without a live Fluent session:

- ``find_api`` and ``get_help`` search the bundled settings schema.
- ``validate_code`` performs an AST pre-check only.

**Live-session tools** require PyFluent and a connected Fluent solver:

- ``connect``, ``disconnect``, ``session_status``, ``solver_status``, ``manage_fluent``
- ``get_state``, ``get_targeted_context``, named-object tools
- ``run_code``, ``summarize_setup``, ``simulation_report``, ``screenshot``
- ``mesh_quality``, ``list_fields``, ``compare_files``, ``probe_path``,
  ``get_active_status``, ``get_allowed_values``,
  ``describe_named_object_template``, ``describe_path``

Using the tools
---------------

Discover-validate-execute loop
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

For most setup tasks, follow this pattern:

#. **Discover**: ``find_api("turbulence model")`` or ``get_state("setup.general")``.
#. **Validate**: ``validate_code(python_snippet)``.
#. **Execute**: ``run_code(python_snippet)``.
#. **Verify**: ``summarize_setup()`` or ``simulation_report()``.

Connection management
~~~~~~~~~~~~~~~~~~~~~

Use ``connect`` to launch a new Fluent session or attach to an existing one:

*"Connect to Fluent and launch a new solver session."*

*"Connect to Fluent on 192.168.1.100 port 18500."*

Use ``session_status`` to check whether a session is active and ``disconnect`` to release
it.

Schema discovery
~~~~~~~~~~~~~~~~

Use ``find_api`` for ranked path search over the settings tree:

*"Find API paths related to boundary condition velocity inlet."*

Use ``get_state`` to read live values and ``list_named_objects`` to enumerate named
collections (boundary conditions, cell zones, materials, and so on).

Use ``probe_path`` to check whether settings paths exist, are active in the
current solver mode, and can be created. Use ``get_active_status`` for focused
active/inactive checks and ``get_allowed_values`` before writing enum or menu-style
settings.

Use ``describe_named_object_template`` to inspect the fields, defaults, read-only
state, and allowed values for a new object under a named-object collection. Use
``describe_path`` when one consolidated descriptor is more useful than separate
path probes.

Code execution
~~~~~~~~~~~~~~

``run_code`` executes sandboxed PyFluent Python in a persistent REPL namespace.
**This tool mutates the live solver**. Always prefer ``validate_code`` first for
untrusted code.

``validate_code`` performs an AST and signature pre-check without execution.

Domain tools
~~~~~~~~~~~~

PyFluent-MCP supports two mesh-related workflows: running Fluent meshing
workflows and inspecting loaded meshes from solver sessions.

Use ``mesh_quality`` for all solver-side requests about mesh counts, skewness,
orthogonal quality, aspect ratio, or Fluent mesh checks. It returns a structured
payload with ``cell_count``, ``face_count``, ``node_count``, quality metrics, and
optional ``mesh.check`` topology diagnostics when ``include_check=true``. Treat
``None`` values as unavailable data, not as passing values.

Quality metrics and ``mesh.check`` answer different questions. Quality metrics
summarize numeric mesh quality. ``mesh.check`` is a topology preflight for issues
such as non-positive volumes, face handedness, and boundary-pair consistency.
Route all "show mesh quality / skewness / check mesh" intents to
``mesh_quality`` rather than ``run_code``, ``summarize_setup``, or
``simulation_report``.

``list_fields`` enumerates scalar/vector fields available in the loaded case.

``compare_files`` diffs two case/mesh files in separate ephemeral headless sessions
without touching the live workspace session. Requires the ``file-probe`` extra for
``.h5``/``.cas.h5`` files.

Workflow examples
-----------------

Generate a mesh from geometry
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

#. ``connect(connect_kwargs={"mode": "meshing", "precision": "double"})`` launches
   Fluent in meshing mode.
#. ``find_api("workflow initialize watertight geometry", under="workflow")`` discovers
   workflow tasks.
#. ``validate_code`` checks the generated meshing commands.
#. ``run_code`` executes workflow steps such as geometry import, local sizing,
   surface mesh generation, boundary layers, volume mesh generation, and mesh checks.
#. ``run_code`` can switch to solver mode when the mesh is ready for setup.

The API catalog includes common entries for Watertight Geometry,
Fault-tolerant Meshing, and 2D Meshing workflows.

Load a case and inspect setup
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

#. ``connect`` launches or attaches to Fluent.
#. ``run_code`` loads a case file.
#. ``summarize_setup`` gets a compact digest of models, BCs, and materials.
#. ``mesh_quality(include_check=true)`` checks mesh counts, quality metrics, and topology diagnostics.

Generate and apply a settings change
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

#. ``find_api("under-relaxation pressure")`` discovers the active path family.
#. ``get_state("solution.controls")`` reads the live URF configuration.
#. ``validate_code`` then ``run_code`` applies the change.

Compare two case files
~~~~~~~~~~~~~~~~~~~~~~

``compare_files(path_a="old.cas.h5", path_b="new.cas.h5")`` returns a structured diff in
separate headless sessions.

Result models and errors
------------------------

Tool return types
~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Model
     - Returned by
   * - ``ConnectResult``
     - ``connect``
   * - ``RunCodeResult``
     - ``run_code``

Configuration is loaded from ``FLUIDS_MCP_*`` environment variables via
:func:`~ansys.fluent.mcp.load_config`. Use :func:`~ansys.fluent.mcp.validate_config`
to check the configuration at startup.

Error types
~~~~~~~~~~~

All errors inherit from ``FluidsMCPError``:

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Error
     - When raised
   * - ``NotConnectedError``
     - A live-session tool is called with no active Fluent connection.
   * - ``BackendUnavailableError``
     - The requested backend kind is not registered.
   * - ``InvalidArgumentsError``
     - Tool arguments fail validation.
   * - ``DiscoveryError``
     - Schema or API discovery fails
   * - ``UpstreamError``
     - PyFluent or the solver returns an error.
   * - ``ConfigError``
     - Configuration is invalid.

Python API
~~~~~~~~~~

The package re-exports the server class and shared models from its top-level namespace:

.. code-block:: python

   from ansys.fluent.mcp import (
       SolveMCP,
       ConnectResult,
       RunCodeResult,
       FluidsMCPConfig,
       load_config,
   )

Feature reference
-----------------

For full API details, including all parameters and return values, see :doc:`../api/index`.

Best practices
--------------

For recommendations on using PyFluent-MCP effectively, see :doc:`best_practices`.
