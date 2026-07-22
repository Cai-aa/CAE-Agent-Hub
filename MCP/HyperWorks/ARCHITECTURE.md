# HyperWorks MCP architecture

```text
Codex / MCP client
        |
        v
FastMCP typed tools
        |
        +-- live bridge client     -> authenticated 127.0.0.1 JSON requests
        |                                  |
        |                                  v
        |                          HyperWorks Extension
        |                                  |
        |                    Qt main-thread hm / hw / hw.hv API
        +-- installation discovery -> HyperMesh / HyperStudy / solver capability matrix
        +-- project service        -> workspace-bounded input, scripts, output, runs
        +-- Tcl safety gate        -> rejects OS/process escape and runner-owned quit
        +-- HyperMesh Batch        -> isolated asynchronous hmbatch jobs
        +-- HyperStudy API         -> typed MCP-generated study setup via hstpy
        +-- solver adapter         -> staged OptiStruct / Radioss jobs
        +-- process registry       -> status, bounded logs, cancellation, artifacts
        +-- GUI launcher           -> HyperMesh / HyperView launch only
```

## Trust boundaries

- MCP-managed project files and job staging are confined to `HYPERWORKS_MCP_WORKSPACE`.
- External input files are read only when explicitly named, then copied into a project.
- Tcl scripts cannot invoke process/network/dynamic-runtime commands, direct Tcl file
  access, absolute/parent paths, environment access, nested `source`, or `*quit`.
- There is no arbitrary shell, PowerShell, Python, or raw command-line tool.
- HyperStudy accepts typed study data and executes only MCP-generated Python scripts.
- Solver options are typed and CPU counts are bounded.
- Live entity edits/creation, controlled model loading, view refresh, interactive
  selection, model saving, GUI launch, solver submission, and cancellation are explicit
  side effects.
- Live geometry creation, CAD import, surface automeshing, native Solid Map, and the
  bounded cylindrical O-grid generator write a workspace-scoped `.hm` checkpoint first.
  Failed operations attempt an automatic rollback; manual rollback requires confirmation.
- Live CAD input is limited to project-scoped STEP, IGES, and Parasolid files. CAD options
  are bounded `name=value` strings, not an execution channel.
- The live bridge binds only to `127.0.0.1`, authenticates every request with a random
  token, limits payload size, and exposes a fixed method allowlist without `eval`.
- The socket thread never invokes the HyperWorks API. A Qt timer drains requests and
  invokes `hm`, `hw`, and `hw.hv` from the application's main thread.

The Tcl filter is defense in depth, not an operating-system sandbox. HyperMesh has a large
domain command surface, so scripts must still be reviewed before execution.

## Current boundary

Version 0.6 combines bounded live node/element/material and connection creation,
typed HyperStudy setup, block/cylinder geometry,
CAD import, surface automeshing, native Solid Map, a cylindrical radial O-grid generator,
quality summaries, controlled `.hm` loading, and fixed view refresh with the existing
HyperMesh Batch and solver paths. Native Solid Map still depends on HyperMesh recognizing
the selected topology as mappable. General geometry cleanup and HyperView-specific contour
and capture handlers remain later extensions; the bridge retains an allowlisted design.
