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
- Solver options are typed and CPU counts are bounded.
- Live entity edits, interactive selection, model saving, GUI launch, solver submission,
  and cancellation are explicit side effects.
- The live bridge binds only to `127.0.0.1`, authenticates every request with a random
  token, limits payload size, and exposes a fixed method allowlist without `eval`.
- The socket thread never invokes the HyperWorks API. A Qt timer drains requests and
  invokes `hm`, `hw`, and `hw.hv` from the application's main thread.

The Tcl filter is defense in depth, not an operating-system sandbox. HyperMesh has a large
domain command surface, so scripts must still be reviewed before execution.

## Current boundary

Version 0.2 combines the live Extension/API path with the existing HyperMesh Batch and
solver paths. HyperView-specific contour and capture handlers remain a later extension;
the bridge already probes `hw.hv` capability and retains an allowlisted handler design.
