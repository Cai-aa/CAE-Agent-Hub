# HyperWorks MCP

A local, workspace-scoped FastMCP server for auditable Altair HyperWorks automation.

Version 0.2 discovers the installed HyperMesh/HyperStudy/solver launchers, manages
isolated projects, runs screened Tcl through HyperMesh Batch, launches HyperMesh or
HyperView, submits typed OptiStruct/Radioss jobs, and exposes real status, bounded logs,
cancellation, and artifact inventory. It also includes an authenticated in-application
Extension that runs allowlisted `hm` API operations on the HyperWorks Qt main thread.

## Local installation detected

```text
G:\Program Files\Altair\2026\hwdesktop\hwx\bin\win64\runhwx.exe
G:\Program Files\Altair\2026\hwdesktop\hm\bin\win64\hmbatch.exe
G:\Program Files\Altair\2026\hwdesktop\hst\bin\win64\hstbatch.exe
```

No `hwsolvers/scripts/optistruct.bat` or `radioss.bat` was found in this installation
tree. HyperMesh Batch is usable, but solver submission remains capability-gated until
HyperWorks Solvers is installed or the corresponding executable environment variable is
set.

## Setup

```powershell
uv sync --extra dev
$env:HYPERWORKS_HOME = 'G:\Program Files\Altair\2026'
.\.venv\Scripts\python.exe .\probe_environment.py
$env:PYTHONPATH = 'src'
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe .\stdio_smoke.py
# This briefly starts hmbatch and may consume a license.
.\.venv\Scripts\python.exe .\hmbatch_smoke.py --run
```

Use [`examples/codex_config.example.toml`](examples/codex_config.example.toml), or run:

```powershell
.\register_codex_mcp.ps1 -PythonExe "$PWD\.venv\Scripts\python.exe"
```

Install the in-application Extension:

```powershell
.\install_hyperworks_extension.ps1 -Workspace 'E:\CAE\hyperworks-mcp-workspace'
```

The installer also registers `HyperWorks MCP Bridge` in the current user's Altair
extension registry. Restart HyperMesh; if it is not enabled automatically, enable it
from `File > Extension Manager`, then verify the live session:

```powershell
.\.venv\Scripts\python.exe .\probe_live_bridge.py
```

The bridge binds only to `127.0.0.1`, authenticates every request with a generated token,
has a fixed method allowlist, and performs HyperWorks API calls through a Qt main-thread
queue. It does not expose `eval`, arbitrary Python, shell, or Tcl.

## Safe workflow

Call `get_environment`, create a project, import explicit files, write a screened Tcl
script, then request approval before `run_hmbatch`, `launch_hypermesh`,
`submit_solver_job`, or `cancel_job`. Monitor real job state and logs; the server never
guesses progress or convergence.

Tcl process/network/dynamic-runtime commands, direct file access, absolute/parent paths,
and environment access are rejected. This is defense in depth rather than an OS sandbox;
review scripts before execution. The server exposes no arbitrary shell, PowerShell,
Python, or raw command-line tool. See [ARCHITECTURE.md](ARCHITECTURE.md).

## Current boundary

Version 0.2 controls the live HyperMesh session and entity model through `hm`. Dedicated
HyperView contour/result/capture handlers remain future work; `hw.hv` availability is
already included in live capability probing.
