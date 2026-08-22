.. _ref_release_notes:

Release notes
#############

This section contains the release notes for PyMAPDL-MCP.

.. vale off

.. towncrier release notes start

`0.2.1 <https://github.com/ansys/pymapdl-mcp/releases/tag/v0.2.1>`_ - June 10, 2026
===================================================================================

.. tab-set::


  .. tab-item:: Documentation

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - Adding pdf build
          - `#141 <https://github.com/ansys/pymapdl-mcp/pull/141>`_


  .. tab-item:: Maintenance

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - Update CHANGELOG for v0.2.0
          - `#140 <https://github.com/ansys/pymapdl-mcp/pull/140>`_

        * - Add order for GH and PyPI releases
          - `#142 <https://github.com/ansys/pymapdl-mcp/pull/142>`_


`0.2.0 <https://github.com/ansys/pymapdl-mcp/releases/tag/v0.2.0>`_ - June 09, 2026
===================================================================================

.. tab-set::


  .. tab-item:: Added

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - Adding changelog
          - `#105 <https://github.com/ansys/pymapdl-mcp/pull/105>`_

        * - Update pre-commit with best practices
          - `#106 <https://github.com/ansys/pymapdl-mcp/pull/106>`_

        * - Replace MIT License with ANSYS MCP Server Technology Preview License Agreement
          - `#113 <https://github.com/ansys/pymapdl-mcp/pull/113>`_

        * - Rename system_prompt to pymapdl_system_prompt for clarity
          - `#114 <https://github.com/ansys/pymapdl-mcp/pull/114>`_

        * - Remove write_comment tool and related documentation
          - `#117 <https://github.com/ansys/pymapdl-mcp/pull/117>`_

        * - Adding \`commands\` argument to screenshot tool
          - `#119 <https://github.com/ansys/pymapdl-mcp/pull/119>`_

        * - Update ansys-common-mcp dependency to version 0.3.0
          - `#121 <https://github.com/ansys/pymapdl-mcp/pull/121>`_

        * - Standardize all tools to return ToolResult
          - `#123 <https://github.com/ansys/pymapdl-mcp/pull/123>`_

        * - Turn off and on tools based on MAPDL connection state
          - `#124 <https://github.com/ansys/pymapdl-mcp/pull/124>`_

        * - Reducing guidelines tools
          - `#126 <https://github.com/ansys/pymapdl-mcp/pull/126>`_

        * - Tech review
          - `#131 <https://github.com/ansys/pymapdl-mcp/pull/131>`_


  .. tab-item:: Fixed

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - Pass real_context to list_mapdl_instances in integration test
          - `#120 <https://github.com/ansys/pymapdl-mcp/pull/120>`_

        * - Auto-clear crashed MAPDL instance on launch/connect
          - `#128 <https://github.com/ansys/pymapdl-mcp/pull/128>`_

        * - List all MAPDL installations in \`check_mapdl_installed\`
          - `#129 <https://github.com/ansys/pymapdl-mcp/pull/129>`_


  .. tab-item:: Documentation

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - Alignment with PyAnsys documentation
          - `#107 <https://github.com/ansys/pymapdl-mcp/pull/107>`_

        * - Fix documentation build + add \`\`doc-deploy-pr\`\`
          - `#109 <https://github.com/ansys/pymapdl-mcp/pull/109>`_

        * - Review to meet style guide
          - `#135 <https://github.com/ansys/pymapdl-mcp/pull/135>`_


  .. tab-item:: Dependencies

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - Bump the actions group across 1 directory with 3 updates
          - `#134 <https://github.com/ansys/pymapdl-mcp/pull/134>`_

        * - Bump the actions group across 1 directory with 2 updates
          - `#137 <https://github.com/ansys/pymapdl-mcp/pull/137>`_

        * - Bump the pip-deps group across 1 directory with 5 updates
          - `#138 <https://github.com/ansys/pymapdl-mcp/pull/138>`_


  .. tab-item:: Maintenance

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - Enable official release
          - `#139 <https://github.com/ansys/pymapdl-mcp/pull/139>`_


  .. tab-item:: Miscellaneous

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - Add prompts system and fix _cli_config propagation
          - `#96 <https://github.com/ansys/pymapdl-mcp/pull/96>`_


.. vale on
