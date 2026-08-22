.. _ref_usage_examples:

Usage examples
==============

These examples show typical MCP workflows once the server is configured.

Load a case and summarize setup
-------------------------------

**User prompt:**

*"Connect to Fluent, load ``pipe.cas.h5``, and summarize the current setup."*

**Expected tool sequence:**

#. ``connect`` launches or attaches to Fluent.
#. ``run_code`` calls ``session.file.read_case(file_name="pipe.cas.h5")``.
#. ``summarize_setup`` returns a compact digest of models, boundary conditions,
   materials, and numerics.

Inspect mesh quality
--------------------

**User prompt:**

*"Show the mesh quality for this case, including skewness and orthogonal quality."*

**Expected tool:**

``mesh_quality(include_check=False)``

Use ``mesh_quality(include_check=True)`` when you also need Fluent's ``mesh.check()``
output.

Generate and apply a boundary condition change
----------------------------------------------

**User prompt:**

*"Set the velocity inlet ``inlet-1`` to 15 m/s."*

**Expected tool sequence:**

#. ``list_named_objects("setup.boundary_conditions.velocity_inlet")`` confirms the name.
#. ``get_state("setup.boundary_conditions.velocity_inlet")`` reads current inlet settings.
#. Generate a PyFluent settings snippet in the external orchestration layer.
#. ``validate_code`` pre-checks the snippet.
#. ``run_code`` applies the deterministic settings API calls.
#. ``get_state("setup.boundary_conditions.velocity_inlet")`` verifies the new value.

Perform offline API discovery
-----------------------------

**User prompt:**

*"What settings path controls the turbulence model when Fluent is not running?"*

**Expected tool sequence:**

#. ``find_api("turbulence model")`` performs ranked path search offline.
#. ``get_help("setup.general.turbulence.model")`` returns per-path help text.

Compare two case files
----------------------

**User prompt:**

*"Compare ``baseline.cas.h5`` and ``modified.cas.h5`` and summarize what changed."*

**Expected tool:**

``compare_files(path_a="baseline.cas.h5", path_b="modified.cas.h5")``

Reply with the ``summary`` markdown table from the response verbatim.

Next steps
----------

- See :doc:`../user_guide/best_practices` for workflow recommendations.
- See :doc:`../user_guide/tools_and_capabilities` for additional tool reference.
