.. _ref_implementing_a_tool:

Implement a custom domain tool
==============================

Learn how to implement a custom MCP domain tool for PyFluent-MCP.

Tool overview
-------------

A *domain tool* is a stateless backend or catalog operation with no dependency on an
agent loop, journal, or recipe registry. Domain tool can perform the following tasks:

- Take structured input parameters.
- Perform an operation through the ``Backend`` interface.
- Return structured JSON output.

Tools are registered in ``ansys.fluent.mcp.solve.lib.domain_tools`` and discovered
automatically by :class:`~ansys.fluent.mcp.solve.SolveMCP`.

Tool anatomy
------------

Here's a minimal domain tool:

.. code-block:: python

   from typing import Any

   from ansys.fluent.mcp.common.backend import Backend


   async def cell_count_impl(
       backend: Backend,
       *,
       include_faces: bool = False,
   ) -> dict[str, Any]:
       """Return mesh cell counts from the live solver."""
       counts = await backend.mesh_counts()
       result = {"cell_count": counts.get("cell_count")}
       if include_faces:
           result["face_count"] = counts.get("face_count")
       return result

Key components follow:

- **First parameter** is always ``backend: Backend``.
- **All other parameters** are keyword-only with explicit type annotations.
- **Return type** is ``dict[str, Any]`` (structured JSON envelope).

Tool registration
-----------------

Append a ``DomainTool`` entry to ``get_solve_domain_tools()``:

.. code-block:: python

   from ansys.fluent.mcp.common.domain_tools import DomainTool, DomainToolSpec


   def get_solve_domain_tools() -> list[DomainTool]:
       return [
           # ... existing tools ...
           DomainTool(
               spec=DomainToolSpec(
                   name="cell_count",
                   description="Return live mesh cell counts from the connected solver.",
               ),
               handler=cell_count_impl,
           ),
       ]

Leave ``DomainToolSpec.parameters=None``. The framework derives the JSON schema from
the handler signature via ``schema_from_signature``.

No changes to ``SolveMCP._register_tools()`` are needed. It already registers everything
returned by ``get_solve_domain_tools()``.

How registration works
----------------------

:class:`~ansys.fluent.mcp.common.base.FluidsLeafMCP` synthesizes a wrapper whose
``inspect.Signature`` mirrors the handler minus the leading ``backend`` parameter. FastMCP
uses that wrapper to expose the tool to MCP clients with the correct input schema.

Testing
-------

Add offline tests using a fake backend in the ``tests/`` directory:

.. code-block:: python

   async def test_cell_count_impl(fake_backend):
       result = await cell_count_impl(fake_backend, include_faces=True)
       assert result["cell_count"] == 1000
       assert result["face_count"] == 5000

Run tests with this code:

.. code-block:: bash

   pytest tests/test_my_tool.py -q

Pluggable backends
------------------

Domain tools receive the active ``Backend`` instance. If your tool needs capabilities
beyond the base ABC, check for optional methods or probe the backend kind. External
backends can be contributed via the ``ansys.fluent.mcp.solve_backends`` entry-point group
without modifying this repository.

Next steps
----------

- See :ref:`ref_develop_pyfluent_mcp` for development environment setup and the
  full architecture reference.
