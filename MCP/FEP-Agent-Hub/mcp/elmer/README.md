# Elmer FEM MCP

Local STDIO MCP server for the verified `heat_steady_v1` workflow.

Tools cover environment and case inspection, STEP handoff, Gmsh tetrahedral mesh generation, ElmerGrid conversion, topology inspection, materials, equations, semantic boundary conditions, SIF generation/validation, serial solving, job/log status, and VTU result validation.

Raw unverified boundary IDs are not accepted by the public API. Semantic boundaries are derived from mesh coordinates and recorded as evidence.

Entry point:

```powershell
python -m elmer_mcp.server
```
