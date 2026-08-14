# Architecture

```text
Codex
  ├─ FreeCAD MCP  ── fixed FreeCADCmd runner ── FCStd + STEP + geometry manifest
  ├─ Elmer MCP   ── Gmsh ── ElmerGrid ── structured SIF ── ElmerSolver ── VTU
  └─ ParaView MCP ── persistent pvpython worker ── pipeline + PNG + CSV + PVSM

All three ── open-cae-core ── workspace guard + process whitelist + evidence
```

Servers never call each other. Codex coordinates them through the shared project contract. This prevents lifecycle coupling and keeps failures attributable to one stage.

FreeCAD operations are isolated: each tool call opens the workspace FCStd, performs one whitelisted operation, recomputes, saves, validates expected artifacts, and exits. This favors auditability over GUI session speed.

Elmer owns meshing because STEP is geometry, not a finite-element mesh. The adapter writes a fixed Gmsh `.geo`, converts MSH2 with ElmerGrid, and classifies boundaries from actual Elmer node coordinates. The heat profiles use one-object/one-body mapping; the planar electromagnetic, plane-stress elasticity, and laminar-flow profiles use deterministic semantic IDs, Gmsh physical groups, and verified Elmer body/boundary IDs. Ambiguous or missing mappings block solving.

The `elasticity_2d_static_v1` profile runs Elmer's displacement solve, preserves
the raw VTU, and adds auditable plane-stress strain/stress arrays derived from
the actual finite-element displacement field. Multi-level demonstrations are
represented as PVD collections of independent static solves so they are not
misreported as physical transient dynamics.

The `heat_transient_v1` profile applies SI coordinate scaling, BDF time
integration, density/heat-capacity validation, one VTU per time step, monotonic
temperature-history checks, and a fixed one-dimensional Fourier-series gate.
The `navier_stokes_2d_steady_v1` profile uses a fixed parabolic inlet generator,
no-slip walls, an outlet pressure gauge, and Poiseuille velocity/pressure gates;
it does not expose arbitrary MATC or raw SIF input.

ParaView uses a persistent worker because repeatedly loading VTU files is expensive. JSON-line IPC addresses proxy aliases stored only in that worker. Loss of the child process is reported as `SESSION_LOST`; the MCP never pretends the pipeline survived.
