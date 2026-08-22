Best practices
==============

Keep MCP requests narrow and explicit. Ask for one workflow action, state
query, or code-generation task at a time so the server can return bounded
context.

Suggested workflow
------------------

#. Check ``session_status`` before you run CFX-specific tools.
#. Use ``connect`` to attach to or start the required CFX backend.
#. Use ``cfx_model_context`` to inspect names, state, or API help before you
   make changes.
#. Use ``cfx_workflow`` for higher-level CFX-Pre, CFX-Solver, and CFD-Post
   actions.
#. Use ``validate_code`` before you run generated snippets.

Generated code
--------------

Review generated Python before execution, especially when it modifies solver
setup, writes files, or launches product processes. Prefer small snippets that
you can validate and rerun safely.

Session state
-------------

CFX workflows depend on external product state, files, and licensing. Keep
input paths explicit, preserve solver output files, and disconnect sessions
when you no longer need them.
