.. _ref_release_notes:

Release notes
#############

This section contains the release notes for PyFluent-MCP.

.. vale off

.. towncrier release notes start

`0.4.0 <https://github.com/ansys/pyfluent-mcp/releases/tag/v0.4.0>`_ - August 14, 2026
======================================================================================

.. tab-set::


  .. tab-item:: Added

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - Integrate meshing workflow
          - `#45 <https://github.com/ansys/pyfluent-mcp/pull/45>`_


  .. tab-item:: Documentation

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - Update \`\`CONTRIBUTORS.md\`\` with the latest contributors
          - `#46 <https://github.com/ansys/pyfluent-mcp/pull/46>`_

        * - Add meshing docs
          - `#51 <https://github.com/ansys/pyfluent-mcp/pull/51>`_


  .. tab-item:: Dependencies

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - Bump the pip-deps group with 2 updates
          - `#47 <https://github.com/ansys/pyfluent-mcp/pull/47>`_

        * - Bump the pre-commit group with 2 updates
          - `#48 <https://github.com/ansys/pyfluent-mcp/pull/48>`_

        * - Bump the actions group with 17 updates
          - `#49 <https://github.com/ansys/pyfluent-mcp/pull/49>`_


  .. tab-item:: Maintenance

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - Update CHANGELOG for v0.3.0
          - `#42 <https://github.com/ansys/pyfluent-mcp/pull/42>`_

        * - Bump development version to 0.4.dev0
          - `#43 <https://github.com/ansys/pyfluent-mcp/pull/43>`_


`0.3.0 <https://github.com/ansys/pyfluent-mcp/releases/tag/v0.3.0>`_ - August 04, 2026
======================================================================================

.. tab-set::


  .. tab-item:: Fixed

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - Resolve binary crash
          - `#37 <https://github.com/ansys/pyfluent-mcp/pull/37>`_


  .. tab-item:: Dependencies

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - Bump the actions group with 15 updates
          - `#38 <https://github.com/ansys/pyfluent-mcp/pull/38>`_

        * - Bump the pre-commit group with 3 updates
          - `#41 <https://github.com/ansys/pyfluent-mcp/pull/41>`_


  .. tab-item:: Maintenance

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - Update CHANGELOG for v0.2.1
          - `#34 <https://github.com/ansys/pyfluent-mcp/pull/34>`_

        * - Update missing or outdated files
          - `#35 <https://github.com/ansys/pyfluent-mcp/pull/35>`_

        * - Add Dependabot support for pre-commit hook updates
          - `#40 <https://github.com/ansys/pyfluent-mcp/pull/40>`_


`0.2.1 <https://github.com/ansys/pyfluent-mcp/releases/tag/v0.2.1>`_ - July 31, 2026
====================================================================================

.. tab-set::


  .. tab-item:: Added

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - Readiness for next release
          - `#25 <https://github.com/ansys/pyfluent-mcp/pull/25>`_


  .. tab-item:: Dependencies

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - Bump the actions group across 1 directory with 20 updates
          - `#26 <https://github.com/ansys/pyfluent-mcp/pull/26>`_

        * - Bump sphinx-autodoc-typehints from 3.12.0 to 3.13.0 in the pip-deps group across 1 directory
          - `#29 <https://github.com/ansys/pyfluent-mcp/pull/29>`_


  .. tab-item:: Maintenance

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - Update CHANGELOG for v0.2.0
          - `#24 <https://github.com/ansys/pyfluent-mcp/pull/24>`_

        * - Update pyfluent
          - `#28 <https://github.com/ansys/pyfluent-mcp/pull/28>`_

        * - Bump PyFluent MCP dependencies
          - `#31 <https://github.com/ansys/pyfluent-mcp/pull/31>`_


`0.2.0 <https://github.com/ansys/pyfluent-mcp/releases/tag/v0.2.0>`_ - July 20, 2026
====================================================================================

.. tab-set::


  .. tab-item:: Added

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - Guard _import_litellm against the tokenizers
          - `#9 <https://github.com/ansys/pyfluent-mcp/pull/9>`_

        * - Unified LLM provider configuration, transport diagnostics, and validator/active-path hardening
          - `#13 <https://github.com/ansys/pyfluent-mcp/pull/13>`_

        * - Python version support according to PyAnsys guidelines
          - `#14 <https://github.com/ansys/pyfluent-mcp/pull/14>`_

        * - Skip allowed_values() on inactive command arguments to avoid Scheme \"object is not active\" transcript spam
          - `#18 <https://github.com/ansys/pyfluent-mcp/pull/18>`_

        * - Slim the Fluent MCP leaf - remove in-server LLM codegen, normalize the tool surface
          - `#19 <https://github.com/ansys/pyfluent-mcp/pull/19>`_


  .. tab-item:: Maintenance

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - Update CHANGELOG for v0.1.0
          - `#12 <https://github.com/ansys/pyfluent-mcp/pull/12>`_


`0.1.0 <https://github.com/ansys/pyfluent-mcp/releases/tag/v0.1.0>`_ - July 10, 2026
====================================================================================

.. tab-set::


  .. tab-item:: Added

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - Guard _import_litellm against the tokenizers
          - `#9 <https://github.com/ansys/pyfluent-mcp/pull/9>`_

        * - Raise unit-test coverage above 80%, expand the live-Fluent integration tests, and remove bandit skips as part of the technical review.
          - `#13 <https://github.com/ansys/pyfluent-mcp/pull/13>`_

        * - Add numpy-style docstrings across the public API so the autoapi reference documentation renders complete signatures and parameter descriptions.
          - `#24 <https://github.com/ansys/pyfluent-mcp/pull/24>`_

        * - Add Anthropic message normalization for LiteLLM transport
          - `#26 <https://github.com/ansys/pyfluent-mcp/pull/26>`_

        * - Probe APIs for Settings APIs
          - `#28 <https://github.com/ansys/pyfluent-mcp/pull/28>`_

        * - Deterministic path-discovery + write-target resolver for the Solve leaf
          - `#33 <https://github.com/ansys/pyfluent-mcp/pull/33>`_


  .. tab-item:: Fixed

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - Follow-up fixes prior to public release
          - `#6 <https://github.com/ansys/pyfluent-mcp/pull/6>`_

        * - Links
          - `#7 <https://github.com/ansys/pyfluent-mcp/pull/7>`_

        * - GitHub runner label change
          - `#11 <https://github.com/ansys/pyfluent-mcp/pull/11>`_

        * - Fix Vale documentation style violations so the Ansys documentation style check passes.
          - `#25 <https://github.com/ansys/pyfluent-mcp/pull/25>`_

        * - License in \`\`SECURITY.md\`\`
          - `#32 <https://github.com/ansys/pyfluent-mcp/pull/32>`_


  .. tab-item:: Documentation

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - Editorial review of all RST files and docstrings in PY files.
          - `#27 <https://github.com/ansys/pyfluent-mcp/pull/27>`_

        * - Edit to use active voice and shorter, clearer sentences
          - `#31 <https://github.com/ansys/pyfluent-mcp/pull/31>`_


  .. tab-item:: Dependencies

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - Bump the pip-deps group with 6 updates
          - `#1 <https://github.com/ansys/pyfluent-mcp/pull/1>`_

        * - Bump actions/checkout from 6.0.3 to 7.0.0 in the actions group across 1 directory
          - `#5 <https://github.com/ansys/pyfluent-mcp/pull/5>`_


  .. tab-item:: Maintenance

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - Update and align Ansys action version to v10.3.3
          - `#4 <https://github.com/ansys/pyfluent-mcp/pull/4>`_


`0.1.0 <https://github.com/ansys/pyfluent-mcp/releases/tag/v0.1.0>`_ - Initial release
========================================================================================

.. tab-set::

  .. tab-item:: Added

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - Initial release of the standalone Fluent Solve MCP server plus the shared
            ``ansys.fluent.mcp.common`` infrastructure.
          -

        * - 22-tool MCP surface: connection, schema discovery, named objects, codegen,
            execution, reporting, and domain tools.
          -

        * - PyFluent backend with pluggable backend entry-point seam.
          -

        * - Offline-first settings schema catalog and LLM codegen pipeline.
          -

        * - Model- and provider-agnostic LLM transport via ``llm_wire``.
          -

  .. tab-item:: Security

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - TLS certificate verification enabled by default for outbound LLM and
            retrieval calls.
          -

        * - Network retrievers honor ``FLUIDS_AGENT_OFFLINE`` and host allowlists.
          -
