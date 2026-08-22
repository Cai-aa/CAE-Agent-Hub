.. _ref_release_notes:

Release notes
#############

This section contains the release notes for PyMechanical-MCP.

.. vale off

.. towncrier release notes start

`0.2.0 <https://github.com/ansys/pymechanical-mcp/releases/tag/v0.2.0>`_ - August 12, 2026
==========================================================================================

.. tab-set::


  .. tab-item:: Added

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - Add --static-tools flag to expose all tools from startup
          - `#69 <https://github.com/ansys/pymechanical-mcp/pull/69>`_


  .. tab-item:: Dependencies

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - Bump the pip-deps group with 2 updates
          - `#62 <https://github.com/ansys/pymechanical-mcp/pull/62>`_

        * - Bump the pre-commit group with 3 updates
          - `#64 <https://github.com/ansys/pymechanical-mcp/pull/64>`_

        * - Bump the actions group across 1 directory with 13 updates
          - `#66 <https://github.com/ansys/pymechanical-mcp/pull/66>`_

        * - Bump https://github.com/crate-ci/typos from v1.48.0 to 5.0.7 in the pre-commit group
          - `#67 <https://github.com/ansys/pymechanical-mcp/pull/67>`_

        * - Bump https://github.com/astral-sh/ruff-pre-commit from v0.16.0 to 0.16.1 in the pre-commit group
          - `#72 <https://github.com/ansys/pymechanical-mcp/pull/72>`_

        * - Bump the pip-deps group with 4 updates
          - `#73 <https://github.com/ansys/pymechanical-mcp/pull/73>`_

        * - Bump the actions group with 2 updates
          - `#74 <https://github.com/ansys/pymechanical-mcp/pull/74>`_


  .. tab-item:: Maintenance

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - Update CHANGELOG for v0.1.2
          - `#60 <https://github.com/ansys/pymechanical-mcp/pull/60>`_

        * - Group dependabot updates and track pre-commit hooks
          - `#61 <https://github.com/ansys/pymechanical-mcp/pull/61>`_

        * - Bump check-vulnerabilities action to v10.3.6 to fix flaky vulnerability scan
          - `#65 <https://github.com/ansys/pymechanical-mcp/pull/65>`_

        * - Update missing or outdated files
          - `#71 <https://github.com/ansys/pymechanical-mcp/pull/71>`_

        * - Prepare v0.2.0 (static-tools + post-merge fixes)
          - `#78 <https://github.com/ansys/pymechanical-mcp/pull/78>`_


  .. tab-item:: Miscellaneous

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - Chore(release): prepare (static-tools + post-merge fixes) (#70)
          - `#76 <https://github.com/ansys/pymechanical-mcp/pull/76>`_


`0.1.2 <https://github.com/ansys/pymechanical-mcp/releases/tag/v0.1.2>`_ - 2026-07-29
=====================================================================================

.. tab-set::


  .. tab-item:: Added

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - Prefer GUI Mechanical launches by default
          - `#40 <https://github.com/ansys/pymechanical-mcp/pull/40>`_

        * - Deprecate Python 3.11 and update \`\`ansys-common-mcp\`\`
          - `#55 <https://github.com/ansys/pymechanical-mcp/pull/55>`_


  .. tab-item:: Dependencies

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - Bump ansys/actions/doc-deploy-dev from 10.3.2 to 10.3.3
          - `#34 <https://github.com/ansys/pymechanical-mcp/pull/34>`_

        * - Bump ansys/actions/release-github from 10.3.2 to 10.3.3
          - `#35 <https://github.com/ansys/pymechanical-mcp/pull/35>`_

        * - Bump ansys/actions/tests-pytest from 10.3.2 to 10.3.3
          - `#36 <https://github.com/ansys/pymechanical-mcp/pull/36>`_

        * - Bump ansys/actions/doc-deploy-pr from 10.3.2 to 10.3.3
          - `#37 <https://github.com/ansys/pymechanical-mcp/pull/37>`_

        * - Bump ansys/actions/check-actions-security from 10.3.2 to 10.3.3
          - `#38 <https://github.com/ansys/pymechanical-mcp/pull/38>`_

        * - Bump ansys/actions/release-github from 10.3.3 to 10.3.4
          - `#41 <https://github.com/ansys/pymechanical-mcp/pull/41>`_

        * - Bump ansys/actions/build-wheelhouse from 10.3.2 to 10.3.4
          - `#42 <https://github.com/ansys/pymechanical-mcp/pull/42>`_

        * - Bump ansys-mechanical-core from 0.12.10 to 0.12.11
          - `#43 <https://github.com/ansys/pymechanical-mcp/pull/43>`_

        * - Bump ansys/actions/check-vulnerabilities from 10.3.2 to 10.3.4
          - `#44 <https://github.com/ansys/pymechanical-mcp/pull/44>`_

        * - Bump ansys/actions/doc-deploy-changelog from 10.3.2 to 10.3.4
          - `#45 <https://github.com/ansys/pymechanical-mcp/pull/45>`_

        * - Bump ansys/actions/check-actions-security from 10.3.3 to 10.3.4
          - `#46 <https://github.com/ansys/pymechanical-mcp/pull/46>`_

        * - Bump ansys/actions/doc-changelog from 10.3.2 to 10.3.5
          - `#48 <https://github.com/ansys/pymechanical-mcp/pull/48>`_

        * - Bump ansys/actions/doc-deploy-stable from 10.3.2 to 10.3.5
          - `#49 <https://github.com/ansys/pymechanical-mcp/pull/49>`_

        * - Bump ansys/actions/tests-pytest from 10.3.3 to 10.3.5
          - `#50 <https://github.com/ansys/pymechanical-mcp/pull/50>`_

        * - Bump ansys-mechanical-core from 0.12.11 to 0.12.12
          - `#51 <https://github.com/ansys/pymechanical-mcp/pull/51>`_

        * - Bump actions/labeler from 6.1.0 to 7.0.0
          - `#52 <https://github.com/ansys/pymechanical-mcp/pull/52>`_

        * - Bump matplotlib from 3.11.0 to 3.11.1
          - `#53 <https://github.com/ansys/pymechanical-mcp/pull/53>`_

        * - Bump ansys/actions/release-github from 10.3.4 to 10.3.5
          - `#54 <https://github.com/ansys/pymechanical-mcp/pull/54>`_

        * - Consolidate dependabot updates (#50, #51, #52, #53, #54)
          - `#57 <https://github.com/ansys/pymechanical-mcp/pull/57>`_


  .. tab-item:: Maintenance

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - Update CHANGELOG for v0.1.1
          - `#33 <https://github.com/ansys/pymechanical-mcp/pull/33>`_


`0.1.1 <https://github.com/ansys/pymechanical-mcp/releases/tag/v0.1.1>`_ - July 13, 2026
========================================================================================

.. tab-set::


  .. tab-item:: Fixed

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - README image
          - `#32 <https://github.com/ansys/pymechanical-mcp/pull/32>`_


  .. tab-item:: Maintenance

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - Update CHANGELOG for v0.1.0
          - `#31 <https://github.com/ansys/pymechanical-mcp/pull/31>`_


`0.1.0 <https://github.com/ansys/pymechanical-mcp/releases/tag/v0.1.0>`_ - July 13, 2026
========================================================================================

.. tab-set::


  .. tab-item:: Added

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - Technical review
          - `#16 <https://github.com/ansys/pymechanical-mcp/pull/16>`_


  .. tab-item:: Fixed

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - Follow up fixes
          - `#26 <https://github.com/ansys/pymechanical-mcp/pull/26>`_


  .. tab-item:: Documentation

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - Align tool visibility and improve docs onboarding
          - `#25 <https://github.com/ansys/pymechanical-mcp/pull/25>`_

        * - Edit for public release
          - `#29 <https://github.com/ansys/pymechanical-mcp/pull/29>`_


  .. tab-item:: Dependencies

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - Bump actions/checkout from 6.0.3 to 7.0.0
          - `#21 <https://github.com/ansys/pymechanical-mcp/pull/21>`_

        * - Bump ansys-sphinx-theme from 1.8.2 to 1.9.0
          - `#22 <https://github.com/ansys/pymechanical-mcp/pull/22>`_

        * - Bump pytest from 9.1.0 to 9.1.1
          - `#23 <https://github.com/ansys/pymechanical-mcp/pull/23>`_

        * - Bump sphinx-autodoc-typehints from 3.1.0 to 3.6.1
          - `#24 <https://github.com/ansys/pymechanical-mcp/pull/24>`_


  .. tab-item:: Maintenance

    .. list-table::
        :header-rows: 0
        :widths: auto

        * - Use PYANSYS_CI_BOT_TOKEN for doc-deploy-dev
          - `#28 <https://github.com/ansys/pymechanical-mcp/pull/28>`_

        * - Last changes
          - `#30 <https://github.com/ansys/pymechanical-mcp/pull/30>`_


.. vale on
