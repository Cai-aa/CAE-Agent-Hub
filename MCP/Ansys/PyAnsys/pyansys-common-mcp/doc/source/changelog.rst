.. _ref_release_notes:

Release notes
#############

This document contains the release notes for the PyAnsys Common MCP project.

.. vale off

.. towncrier release notes start

`0.3.4 <https://github.com/ansys/pyansys-common-mcp/releases/tag/v0.3.4>`_ - September 03, 2026
===============================================================================================

.. tab-set::


  .. tab-item:: Added

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - Make check for consecutive empty reads timeout configurable
          - `#129 <https://github.com/ansys/pyansys-common-mcp/pull/129>`_


  .. tab-item:: Fixed

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - Fix execution of Python code requiring indentation
          - `#127 <https://github.com/ansys/pyansys-common-mcp/pull/127>`_


  .. tab-item:: Dependencies

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - Bump pandas from 3.0.3 to 3.0.5
          - `#145 <https://github.com/ansys/pyansys-common-mcp/pull/145>`_

        * - Bump actions/labeler from 6.2.0 to 7.0.0
          - `#150 <https://github.com/ansys/pyansys-common-mcp/pull/150>`_

        * - Bump ansys/actions/tests-pytest from 10.3.4 to 10.3.5
          - `#154 <https://github.com/ansys/pyansys-common-mcp/pull/154>`_

        * - Bump ansys-sphinx-theme from 1.9.0 to 1.10.0
          - `#155 <https://github.com/ansys/pyansys-common-mcp/pull/155>`_

        * - Bump pypa/gh-action-pypi-publish from 1.14.0 to 1.14.2
          - `#156 <https://github.com/ansys/pyansys-common-mcp/pull/156>`_

        * - Bump fastmcp from 3.4.4 to 3.4.5
          - `#157 <https://github.com/ansys/pyansys-common-mcp/pull/157>`_

        * - Bump sphinx-autodoc-typehints from 3.13.0 to 3.13.2
          - `#161 <https://github.com/ansys/pyansys-common-mcp/pull/161>`_


  .. tab-item:: Maintenance

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - Update CHANGELOG for v0.3.3
          - `#143 <https://github.com/ansys/pyansys-common-mcp/pull/143>`_


`0.3.3 <https://github.com/ansys/pyansys-common-mcp/releases/tag/v0.3.3>`_ - July 29, 2026
==========================================================================================

.. tab-set::


  .. tab-item:: Added

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - Drop support to Python 3.10 and 3.11
          - `#128 <https://github.com/ansys/pyansys-common-mcp/pull/128>`_

        * - Add configurable HTTP transport via CLI
          - `#130 <https://github.com/ansys/pyansys-common-mcp/pull/130>`_


  .. tab-item:: Fixed

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - Prevent Python REPL prompts from cluttering stderr
          - `#125 <https://github.com/ansys/pyansys-common-mcp/pull/125>`_

        * - Dependencies
          - `#142 <https://github.com/ansys/pyansys-common-mcp/pull/142>`_


  .. tab-item:: Documentation

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - Update \`\`CONTRIBUTORS.md\`\` with the latest contributors
          - `#141 <https://github.com/ansys/pyansys-common-mcp/pull/141>`_


  .. tab-item:: Dependencies

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - Bump fastmcp from 3.3.1 to 3.4.2
          - `#105 <https://github.com/ansys/pyansys-common-mcp/pull/105>`_

        * - Bump ansys-sphinx-theme from 1.8.2 to 1.9.0
          - `#106 <https://github.com/ansys/pyansys-common-mcp/pull/106>`_

        * - Bump actions/checkout from 6.0.2 to 7.0.0
          - `#109 <https://github.com/ansys/pyansys-common-mcp/pull/109>`_

        * - Bump mcp from 1.27.2 to 1.28.0
          - `#110 <https://github.com/ansys/pyansys-common-mcp/pull/110>`_

        * - Bump pytest from 9.0.3 to 9.1.1
          - `#111 <https://github.com/ansys/pyansys-common-mcp/pull/111>`_

        * - Bump mcp from 1.28.0 to 1.28.1
          - `#114 <https://github.com/ansys/pyansys-common-mcp/pull/114>`_

        * - Bump ansys/actions/doc-deploy-stable from 10.3.2 to 10.3.4
          - `#116 <https://github.com/ansys/pyansys-common-mcp/pull/116>`_

        * - Bump ansys/actions/release-github from 10.3.2 to 10.3.3
          - `#117 <https://github.com/ansys/pyansys-common-mcp/pull/117>`_

        * - Bump ansys/actions/doc-deploy-pr from 10.3.2 to 10.3.4
          - `#118 <https://github.com/ansys/pyansys-common-mcp/pull/118>`_

        * - Bump ansys/actions/doc-changelog from 10.3.2 to 10.3.4
          - `#119 <https://github.com/ansys/pyansys-common-mcp/pull/119>`_

        * - Bump ansys/actions/tests-pytest from 10.3.2 to 10.3.4
          - `#121 <https://github.com/ansys/pyansys-common-mcp/pull/121>`_

        * - Bump regex from 2026.5.9 to 2026.7.10
          - `#122 <https://github.com/ansys/pyansys-common-mcp/pull/122>`_

        * - Bump fastmcp from 3.4.2 to 3.4.4
          - `#123 <https://github.com/ansys/pyansys-common-mcp/pull/123>`_

        * - Bump ansys/actions/doc-deploy-dev from 10.3.2 to 10.3.4
          - `#131 <https://github.com/ansys/pyansys-common-mcp/pull/131>`_

        * - Bump ansys/actions/build-library from 10.3.2 to 10.3.5
          - `#132 <https://github.com/ansys/pyansys-common-mcp/pull/132>`_

        * - Bump ansys/actions/doc-build from 10.3.2 to 10.3.5
          - `#133 <https://github.com/ansys/pyansys-common-mcp/pull/133>`_

        * - Bump sphinx-autobuild from 2024.10.3 to 2025.8.25
          - `#134 <https://github.com/ansys/pyansys-common-mcp/pull/134>`_

        * - Bump ansys/actions/release-github from 10.3.3 to 10.3.5
          - `#135 <https://github.com/ansys/pyansys-common-mcp/pull/135>`_

        * - Bump sphinx from 8.2.3 to 9.1.0
          - `#136 <https://github.com/ansys/pyansys-common-mcp/pull/136>`_

        * - Bump actions/labeler from 6.1.0 to 6.2.0
          - `#137 <https://github.com/ansys/pyansys-common-mcp/pull/137>`_

        * - Bump pandas from 2.3.3 to 3.0.3
          - `#138 <https://github.com/ansys/pyansys-common-mcp/pull/138>`_

        * - Bump sphinx-autodoc-typehints from 3.2.0 to 3.13.0
          - `#140 <https://github.com/ansys/pyansys-common-mcp/pull/140>`_


  .. tab-item:: Maintenance

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - Update CHANGELOG for v0.3.2
          - `#108 <https://github.com/ansys/pyansys-common-mcp/pull/108>`_


`0.3.2 <https://github.com/ansys/pyansys-common-mcp/releases/tag/v0.3.2>`_ - June 24, 2026
==========================================================================================

.. tab-set::


  .. tab-item:: Added

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - Disabling python session if needed
          - `#107 <https://github.com/ansys/pyansys-common-mcp/pull/107>`_


  .. tab-item:: Dependencies

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - Bump ansys/actions from 10.3.1 to 10.3.2
          - `#92 <https://github.com/ansys/pyansys-common-mcp/pull/92>`_

        * - Bump mcp from 1.27.1 to 1.27.2
          - `#101 <https://github.com/ansys/pyansys-common-mcp/pull/101>`_

        * - Bump parse from 1.22.0 to 1.22.1
          - `#102 <https://github.com/ansys/pyansys-common-mcp/pull/102>`_


  .. tab-item:: Maintenance

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - Update CHANGELOG for v0.3.1
          - `#103 <https://github.com/ansys/pyansys-common-mcp/pull/103>`_


`0.3.1 <https://github.com/ansys/pyansys-common-mcp/releases/tag/v0.3.1>`_ - June 11, 2026
==========================================================================================

.. tab-set::


  .. tab-item:: Fixed

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - Uncomment version switcher
          - `#78 <https://github.com/ansys/pyansys-common-mcp/pull/78>`_


  .. tab-item:: Documentation

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - Update \`\`CONTRIBUTORS.md\`\` with the latest contributors
          - `#84 <https://github.com/ansys/pyansys-common-mcp/pull/84>`_

        * - Adding tool sets mention
          - `#89 <https://github.com/ansys/pyansys-common-mcp/pull/89>`_


  .. tab-item:: Dependencies

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - Bump actions/upload-artifact from 7.0.0 to 7.0.1
          - `#79 <https://github.com/ansys/pyansys-common-mcp/pull/79>`_

        * - Bump sphinx-gallery from 0.20.0 to 0.21.0
          - `#80 <https://github.com/ansys/pyansys-common-mcp/pull/80>`_

        * - Bump ansys/actions from 10.2.12 to 10.3.0
          - `#81 <https://github.com/ansys/pyansys-common-mcp/pull/81>`_

        * - Bump parse from 1.21.1 to 1.22.0
          - `#83 <https://github.com/ansys/pyansys-common-mcp/pull/83>`_

        * - Bump ansys/actions from 10.3.0 to 10.3.1
          - `#85 <https://github.com/ansys/pyansys-common-mcp/pull/85>`_

        * - Bump mcp from 1.27.0 to 1.27.1
          - `#86 <https://github.com/ansys/pyansys-common-mcp/pull/86>`_

        * - Bump actions/labeler from 6.0.1 to 6.1.0
          - `#87 <https://github.com/ansys/pyansys-common-mcp/pull/87>`_

        * - Bump regex from 2026.4.4 to 2026.5.9
          - `#90 <https://github.com/ansys/pyansys-common-mcp/pull/90>`_

        * - Bump fastmcp from 3.2.4 to 3.3.1
          - `#91 <https://github.com/ansys/pyansys-common-mcp/pull/91>`_

        * - Bump ansys-sphinx-theme from 1.7.2 to 1.8.2
          - `#95 <https://github.com/ansys/pyansys-common-mcp/pull/95>`_

        * - Bump pytest-asyncio from 1.3.0 to 1.4.0
          - `#100 <https://github.com/ansys/pyansys-common-mcp/pull/100>`_


  .. tab-item:: Maintenance

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - Update CHANGELOG for v0.3.0
          - `#75 <https://github.com/ansys/pyansys-common-mcp/pull/75>`_

        * - Update license metadata in pyproject.toml
          - `#96 <https://github.com/ansys/pyansys-common-mcp/pull/96>`_


`0.3.0 <https://github.com/ansys/pyansys-common-mcp/releases/tag/v0.3.0>`_ - April 22, 2026
===========================================================================================

.. tab-set::


  .. tab-item:: Added

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - Adding ruff
          - `#55 <https://github.com/ansys/pyansys-common-mcp/pull/55>`_

        * - Moving to public pypi
          - `#56 <https://github.com/ansys/pyansys-common-mcp/pull/56>`_

        * - Adding \`\`changelog\`\` in ansys-sphinx-theme dependency
          - `#60 <https://github.com/ansys/pyansys-common-mcp/pull/60>`_

        * - Using Apache-2.0 license
          - `#72 <https://github.com/ansys/pyansys-common-mcp/pull/72>`_


  .. tab-item:: Fixed

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - Remove empty module
          - `#57 <https://github.com/ansys/pyansys-common-mcp/pull/57>`_

        * - Remaining mentions of MIT license
          - `#73 <https://github.com/ansys/pyansys-common-mcp/pull/73>`_


  .. tab-item:: Dependencies

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - Pinning down test dependencies
          - `#40 <https://github.com/ansys/pyansys-common-mcp/pull/40>`_

        * - Bump sphinx-gallery from 0.19.0 to 0.20.0
          - `#41 <https://github.com/ansys/pyansys-common-mcp/pull/41>`_

        * - Bump ansys/actions from 10.2.4 to 10.2.10
          - `#42 <https://github.com/ansys/pyansys-common-mcp/pull/42>`_

        * - Bump ansys-sphinx-theme[autoapi] from 1.5.3 to 1.7.2
          - `#43 <https://github.com/ansys/pyansys-common-mcp/pull/43>`_

        * - Bump pypandoc from 1.15 to 1.17
          - `#44 <https://github.com/ansys/pyansys-common-mcp/pull/44>`_

        * - Bump pytest-sphinx from 0.6.3 to 0.7.1
          - `#45 <https://github.com/ansys/pyansys-common-mcp/pull/45>`_

        * - Bump parse from 1.20.2 to 1.21.1
          - `#46 <https://github.com/ansys/pyansys-common-mcp/pull/46>`_

        * - Bump actions/download-artifact from 6.0.0 to 8.0.1
          - `#47 <https://github.com/ansys/pyansys-common-mcp/pull/47>`_

        * - Bump regex from 2025.7.34 to 2026.2.28
          - `#49 <https://github.com/ansys/pyansys-common-mcp/pull/49>`_

        * - Bump numpydoc from 1.8.0 to 1.10.0
          - `#52 <https://github.com/ansys/pyansys-common-mcp/pull/52>`_

        * - Bump pytest-cov from 7.0.0 to 7.1.0
          - `#61 <https://github.com/ansys/pyansys-common-mcp/pull/61>`_

        * - Bump ansys/actions from 10.2.10 to 10.2.12
          - `#62 <https://github.com/ansys/pyansys-common-mcp/pull/62>`_

        * - Bump fastmcp from 3.1.1 to 3.2.0
          - `#64 <https://github.com/ansys/pyansys-common-mcp/pull/64>`_

        * - Bump pypa/gh-action-pypi-publish from 1.13.0 to 1.14.0
          - `#67 <https://github.com/ansys/pyansys-common-mcp/pull/67>`_

        * - Bump mcp from 1.26.0 to 1.27.0
          - `#68 <https://github.com/ansys/pyansys-common-mcp/pull/68>`_

        * - Bump regex from 2026.2.28 to 2026.4.4
          - `#69 <https://github.com/ansys/pyansys-common-mcp/pull/69>`_

        * - Bump fastmcp from 3.2.0 to 3.2.3
          - `#70 <https://github.com/ansys/pyansys-common-mcp/pull/70>`_

        * - Bump pytest from 9.0.2 to 9.0.3
          - `#71 <https://github.com/ansys/pyansys-common-mcp/pull/71>`_


  .. tab-item:: Miscellaneous

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - Missing replacement in CONTRIBUTING.md file
          - `#30 <https://github.com/ansys/pyansys-common-mcp/pull/30>`_

        * - README rendering
          - `#33 <https://github.com/ansys/pyansys-common-mcp/pull/33>`_

        * - Create CODEOWNERS
          - `#37 <https://github.com/ansys/pyansys-common-mcp/pull/37>`_

        * - Ci: missing CNAME on doc deploy actions
          - `#38 <https://github.com/ansys/pyansys-common-mcp/pull/38>`_


  .. tab-item:: Documentation

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - Typos
          - `#35 <https://github.com/ansys/pyansys-common-mcp/pull/35>`_

        * - Update README.md
          - `#58 <https://github.com/ansys/pyansys-common-mcp/pull/58>`_


  .. tab-item:: Maintenance

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - Add changelog + update documentation
          - `#26 <https://github.com/ansys/pyansys-common-mcp/pull/26>`_

        * - Remove prefixes from fragments
          - `#39 <https://github.com/ansys/pyansys-common-mcp/pull/39>`_

        * - Dependabot proper ecosystem
          - `#48 <https://github.com/ansys/pyansys-common-mcp/pull/48>`_

        * - Dynamic versioning
          - `#54 <https://github.com/ansys/pyansys-common-mcp/pull/54>`_


.. vale on
