# HyperWorks MCP

A local, workspace-scoped FastMCP server for auditable Altair HyperWorks automation.

Version 0.2 discovers the installed HyperMesh/HyperStudy/solver launchers, manages
isolated projects, runs screened Tcl through HyperMesh Batch, launches HyperMesh or
HyperView, submits typed OptiStruct/Radioss jobs, and exposes real status, bounded logs,
cancellation, and artifact inventory. It also includes an authenticated in-application
Extension that runs allowlisted `hm` API operations on the HyperWorks Qt main thread.

## Find your HyperWorks installation

Do not copy another machine's installation path. `HYPERWORKS_HOME` must point to the
Altair version directory that contains `hwdesktop` and, when solvers are installed,
`hwsolvers`. A typical layout is:

```text
<HYPERWORKS_INSTALL_ROOT>\
  hwdesktop\hwx\bin\win64\runhwx.exe
  hwdesktop\hm\bin\win64\hmbatch.exe
  hwdesktop\hst\bin\win64\hstbatch.exe
  hwsolvers\scripts\optistruct.bat        # optional
  hwsolvers\scripts\radioss.bat           # optional
```

First check the **Target** of the HyperWorks/HyperMesh desktop shortcut. You can also
search the standard Windows installation locations with PowerShell:

```powershell
$searchRoots = @(
  "$env:ProgramFiles\Altair"
  "$env:ProgramW6432\Altair"
  "$env:SystemDrive\Altair"
) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -Unique

Get-ChildItem -Path $searchRoots -Filter runhwx.exe -File -Recurse `
  -ErrorAction SilentlyContinue |
  Where-Object FullName -Match '\\hwdesktop\\hwx\\bin\\win64\\runhwx\.exe$' |
  Select-Object -ExpandProperty FullName
```

For a custom installation location, search its parent directory instead. Remove the
trailing `\hwdesktop\hwx\bin\win64\runhwx.exe` from the result to obtain
`<HYPERWORKS_INSTALL_ROOT>`. `probe_environment.py` reports which desktop, batch, and
solver launchers are actually available; missing solver launchers are reported as a
capability limitation rather than assumed from this repository.

## Setup

```powershell
uv sync --extra dev
$env:HYPERWORKS_HOME = '<HYPERWORKS_INSTALL_ROOT>'
$env:HYPERWORKS_MCP_WORKSPACE = Join-Path `
  ([Environment]::GetFolderPath('MyDocuments')) 'HyperWorksMCP\workspace'
.\.venv\Scripts\python.exe .\probe_environment.py
$env:PYTHONPATH = 'src'
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe .\stdio_smoke.py
# This briefly starts hmbatch and may consume a license.
.\.venv\Scripts\python.exe .\hmbatch_smoke.py --run
```

Use [`examples/codex_config.example.toml`](examples/codex_config.example.toml), or run:

```powershell
.\register_codex_mcp.ps1 `
  -PythonExe "$PWD\.venv\Scripts\python.exe" `
  -HyperWorksHome $env:HYPERWORKS_HOME `
  -Workspace $env:HYPERWORKS_MCP_WORKSPACE
```

Install the in-application Extension:

```powershell
.\install_hyperworks_extension.ps1 `
  -Workspace $env:HYPERWORKS_MCP_WORKSPACE
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
