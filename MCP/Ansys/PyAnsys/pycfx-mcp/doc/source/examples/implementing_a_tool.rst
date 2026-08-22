Implement a tool
================

PyCFX-MCP keeps the public tool surface compact. When you add or change a tool,
start with backend behavior and expose only the smallest stable contract that
MCP clients need.

Recommended steps
-----------------

#. Add or update backend behavior in the ``src/ansys/cfx/mcp/cfx`` directory.
#. Return typed, JSON-friendly data from shared models when possible.
#. Register the public tool in the CFX MCP surface.
#. Add or update tests in the ``tests`` directory.
#. Document the behavior in the **User guide** or **API reference** section.

Make sure tests cover the typed response shape and the error path. If your tool
requires a live CFX product session, mark the test as an integration test and
keep a unit-level test for argument validation or dispatch behavior.
