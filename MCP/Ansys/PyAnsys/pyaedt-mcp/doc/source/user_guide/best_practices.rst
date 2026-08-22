.. _ref_best_practices:

Best practices
==============

Use these recommended patterns for PyAEDT-MCP to avoid common pitfalls,
improve performance, and build more robust workflows.

Session management
------------------

**Reuse the AEDT connection.**
    Keep the same AEDT session open across multiple tool calls. Each
    ``launch_aedt`` or ``connect_to_aedt`` call incurs a non-trivial startup
    cost; only reconnect when genuinely necessary.

**Check AEDT status before every workflow.**
    Always call ``check_aedt_status`` at the start of a workflow to confirm
    whether an AEDT connection already exists. Use the result to decide
    between ``launch_aedt`` (no session) and ``connect_to_aedt`` (existing
    session).

**Shut down cleanly.**
    Disconnect properly when done. Abrupt termination can leave AEDT processes
    running and files in an inconsistent state. The active AEDT session stays
    tied to the MCP server until you explicitly release it. If you do not
    release it first, AEDT might not close normally from the UI. Use
    ``disconnect_from_aedt`` for a graceful release or ``clear_aedt`` to also
    close all open projects.

**Check for errors.**
    Check the text returned by every tool for error messages before
    proceeding. Most tools return a human-readable error string rather than
    raising an exception, so the next step in a workflow can act on the result.

Scripting with ``run_python_code``
-----------------------------------

**Use the persistent session.**
    ``run_python_code`` and ``run_python_script`` share a persistent Python
    interpreter. Break complex workflows into several short
    ``run_python_code`` calls instead of one large script so you can inspect
    intermediate state.

    .. note::
        By default, PyAEDT-MCP applies ``settings.release_on_exception = False``
        in the execution session. This keeps the AEDT session alive when
        generated code fails, which allows the AI agent to iterate and retry
        fixes instead of losing the whole session.

**Choose** ``run_python_code`` **over** ``run_python_script``.
    Use ``run_python_code`` for short inline tasks. Reserve
    ``run_python_script`` for files that already exist on disk (for example,
    customer-provided scripts or parametric templates).

**Use** ``get_guidelines_for`` **before you generate code**.
    When ``--include-context`` is active, call ``get_guidelines_for`` with the
    relevant topic before writing PyAEDT code. The returned guidelines contain
    correct API patterns, avoiding common mistakes.

.. warning::
   AI-generated code can still close or destabilize a project unexpectedly in
   some cases. Save your project frequently and keep a backup copy before
   running larger generated code blocks.

Data handling
-------------

**Extract only what you need.**
    Query specific design properties or result values rather than loading
    entire result sets. AEDT result files can be large; targeted extraction is
    faster and less likely to hit tool timeouts.

**Cache extracted data.**
    Store extracted data in Python variables within the persistent session so
    subsequent analysis steps can reuse it without re-querying AEDT.

    .. note::
       A recommended workflow is to extract the data you need, then disconnect
       from AEDT when possible. This reduces risk, frees Desktop resources,
       and lets you continue post-processing in Python without keeping AEDT
       open longer than necessary.

Visualization
-------------

**Capture screenshots after key steps.**
    Call ``screenshot`` after geometry creation, after meshing, and after
    analysis to give the AI assistant a visual checkpoint. This helps detect
    geometry errors before solving.

    .. note::
       Screenshots need the project to be saved beforehand. If the project is unsaved,
       the screenshot tool returns an error.

**Use** ``run_python_code`` **for custom plots.**
    For plots beyond what AEDT produces natively, use PyAEDT's report API or
    Matplotlib inside ``run_python_code``. The persistent session keeps
    previously imported libraries available.

**Export artifacts for documentation.**
    Save high-quality screenshots and result plots with meaningful file names
    so they can be included directly in engineering reports.

Workflow design
---------------

**Break complex tasks into steps.**
    A well-structured workflow calls one dedicated tool per logical step
    (connect → create design → set up geometry → analyze → export). This keeps
    each tool call focused, makes errors easier to diagnose, and avoids timeout
    issues.

**Validate input before sending to AEDT.**
    Check parameter values (for example, frequencies, dimensions, materials)
    in a ``run_python_code`` call before passing them to the solver. Early
    validation avoids long solve runs that fail for trivial reasons.

**Design for recovery.**
    Structure workflows so that individual steps can be re-run without
    starting over. Use ``save_project`` after expensive geometry or mesh steps
    to create recovery points.

Performance
-----------

**Minimize AEDT restarts.**
    Relaunching AEDT adds tens of seconds of overhead. Reuse the existing
    session across as many operations as possible.

**Run independent analyses in parallel.**
    When running multiple independent designs (for example, a geometry sweep),
    consider using AEDT's built-in parametric solver rather than running
    designs sequentially from the MCP server.

**Process results in Python.**
    Extract result data into Python arrays or DataFrames and analyze it
    there rather than issuing repeated AEDT queries. The persistent session
    retains the data between calls.
