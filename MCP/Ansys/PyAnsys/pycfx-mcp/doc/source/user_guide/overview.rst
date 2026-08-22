Overview
========

PyCFX-MCP is a compact MCP leaf server for CFX automation through PyCFX.
You can use its tools for session management, workflow actions, model context,
code generation, validation, and controlled code execution.

The default MCP surface is intentionally small so you can discover and use CFX
capabilities without being overwhelmed by low-level operations.

How PyCFX-MCP fits into a workflow
-----------------------------------

PyCFX-MCP gives your AI client a standard way to discover tools, call them with
structured parameters, and receive structured results. PyCFX-MCP uses this
interface to expose CFX operations without requiring full knowledge of the
PyCFX API surface.

A typical interaction looks like this:

#. Start PyCFX-MCP over STDIO or connect to an HTTP endpoint.
#. Call ``session_status`` to check whether a CFX backend is connected.
#. Request bounded model context before you plan edits or solver actions.
#. Call routed workflow actions for common lifecycle operations.
#. Use structured results, warnings, or typed errors from the server in your
   next step.

Design goals
------------

- Keep the exposed tool surface small and discoverable.
- Prefer routed workflow actions over arbitrary code execution.
- Return bounded context so large CFX models do not overwhelm your client.
- Make validation and clarification explicit before risky operations.
