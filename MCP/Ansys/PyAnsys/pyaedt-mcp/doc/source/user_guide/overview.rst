.. _ref_overview:

Overview
========

PyAEDT-MCP is a Model Context Protocol (MCP) server that lets you use an AI
client with AEDT. It acts as a bridge between your AI client and AEDT.

Main modules
------------

.. list-table::
   :header-rows: 1

   * - Module
     - Responsibility
   * - ``server.py``
     - Defines the app, CLI, startup logic, cleanup, transport selection, and typed app context.
   * - ``tools.py``
     - Implements the AEDT-facing tool surface: connection, project management, scripting, analysis, inspection, and export.
   * - ``helpers.py``
     - Holds small helpers for endpoint probing, version parsing, and extracting structured AEDT model information.
   * - ``prompts.py``
     - Builds the system prompt exposed to MCP clients, including the connection workflow and tool-usage rules. It provides useful context for the AI client to understand the server's capabilities and limitations.
   * - ``toolsets.py``
     - Publishes the ``toolsets://definition`` discovery resource that groups tools into logical categories.
   * - ``contexts.py``
     - Registers optional guideline tools that are enabled only when the server starts with ``--include-context``.
   * - ``aedt_helper/startup_code.py``
     - Provides the startup imports and shared helpers loaded into the persistent Python session.

Tool groups
-----------

You get a small public tool surface grouped by workflow:

- **Lifecycle:** Check installation, verify connection status, launch and connect to AEDT,
  disconnect when needed, and clean up.
- **Project management:** List projects and designs, open projects, save work, and create designs.
- **Simulation:** Analyze the active design and export setup configuration.
- **Inspection and results:** Inspect the model, capture screenshots, read logs, and export
  solver results.
- **Scripting:** Run short inline PyAEDT code or a Python file against the current AEDT session.

.. note::

  When ``--dynamic-tool-discovery`` is enabled, tools tagged with
  ``REQUIRES_AEDT_TAG`` are hidden until the server has an active AEDT
  connection. This helps save LLM context budget because AEDT-dependent tools
  are not advertised by default before a connection exists. Without this flag,
  the full tool surface stays visible from startup.

Simple AEDT use cases
---------------------

Here are a few simple workflows you can run through the MCP server:

- **Check your environment and connect:** Verify installation, launch AEDT if
  needed, and connect to a running session.
- **Open and inspect a project:** List available projects and designs, open the
  one you need, and inspect model information, such as geometry, materials, and boundary conditions.
- **Run a basic analysis:** Analyze the active design and export setup
  configuration for review.
- **Collect quick outputs:** Capture a screenshot and export solver results to
  share with teammates.
- **Automate repetitive steps:** Use MCP tools and PyAEDT scripts to automate
  repeated tasks, iterate faster, and reduce manual errors.

Next steps
----------

- Begin with :doc:`../getting_started/index`.
- Review guidance in :doc:`best_practices`.
- Learn how to contribute in :ref:`ref_contributing`.
