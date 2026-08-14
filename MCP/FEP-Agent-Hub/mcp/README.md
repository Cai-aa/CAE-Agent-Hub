# MCP Servers

| Server | Package | Tools | Main responsibility |
|---|---|---:|---|
| FreeCAD | `mcp/freecad` | 15 | CAD documents, primitives, booleans, validation, STEP |
| Elmer FEM | `mcp/elmer` | 17 | Heat and harmonic 2D magnetic profiles, mesh, SIF, solve, result validation |
| ParaView | `mcp/paraview` | 17 | Persistent post-processing pipeline and exports |

All servers use STDIO transport and import the shared runtime from `packages/open-cae-core`.

The public tool surface intentionally contains no arbitrary execution endpoint. See each package's `server.py` for typed schemas and docstrings.
