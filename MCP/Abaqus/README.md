# Abaqus MCP

This folder contains a portable MCP server plus a low-latency Abaqus/CAE socket bridge. MCP-capable clients can execute Python in a live Abaqus session, inspect models, list and submit jobs, monitor solver files, inspect ODB files, and capture viewport images.

The v5 bridge replaces the older file-based `commands/` and `results/` queue with a local TCP bridge, matching the interaction model used by [Whfkl/Abaqus-Control-MCP](https://github.com/Whfkl/Abaqus-Control-MCP). The implementation keeps this project's existing Abaqus-specific tool names for compatibility while adding the stronger `run_python`, `set_workdir`, `monitor_job_status`, `inspect_odb`, and `capture_viewport` workflow.

Only reusable source files and templates are included. Runtime logs, solver outputs, ODB files, screenshots, local virtual environments, and private machine paths are intentionally excluded.

## Contents

- `mcp_server.py` runs outside Abaqus and exposes MCP tools over stdio.
- `abaqus_mcp_plugin.py` runs inside Abaqus/CAE and starts the TCP socket bridge.
- `abaqus_plugins/mcp_control/` is a small Abaqus plugin loader for the GUI menu.
- `stop_mcp.py` requests the running socket bridge to stop.
- `abaqus_v6.env.example` shows how to auto-load the GUI menu on Abaqus startup.
- `.env.example` documents socket and timeout environment variables.
- `examples/mcp_config.example.json` shows a generic MCP client configuration.
- `THIRD_PARTY_NOTICES.md` records upstream MIT license attribution.

## Architecture

```text
MCP client
  <stdio MCP>
mcp_server.py
  <local TCP JSON, default 127.0.0.1:48152>
Abaqus/CAE GUI bridge
  <AFX timeout dispatcher + sendCommand>
Abaqus kernel
```

The bridge processes requests on the Abaqus GUI thread and executes code in the kernel through `sendCommand`. This avoids polling command files and makes short interactive probes much faster.

## Install

From this folder:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -e .
```

Set these environment variables in your MCP client if you need non-default values:

```text
ABAQUS_MCP_HOST=127.0.0.1
ABAQUS_MCP_PORT=48152
ABAQUS_MCP_TIMEOUT=60
ABAQUS_MCP_HOME=<repo>
```

`ABAQUS_MCP_HOME` should point to this folder when you install the optional Abaqus GUI menu loader.

## MCP Client Setup

Replace `<repo>` with the absolute path to this folder, for example `C:\path\to\text-to-cae\MCP\Abaqus`.

```json
{
  "mcpServers": {
    "abaqus-mcp-server": {
      "command": "<repo>\\.venv\\Scripts\\python.exe",
      "args": ["<repo>\\mcp_server.py"],
      "cwd": "<repo>",
      "env": {
        "ABAQUS_MCP_HOST": "127.0.0.1",
        "ABAQUS_MCP_PORT": "48152",
        "ABAQUS_MCP_TIMEOUT": "60",
        "ABAQUS_MCP_HOME": "<repo>"
      }
    }
  }
}
```

## Configure Abaqus/CAE

### Option 1: Auto-load on startup

Copy `abaqus_v6.env.example` to your Abaqus startup environment file and set `ABAQUS_MCP_HOME` to this folder.

Windows example:

```powershell
$env:ABAQUS_MCP_HOME = "<repo>"
Copy-Item "<repo>\abaqus_v6.env.example" "$env:USERPROFILE\abaqus_v6.env"
```

Restart Abaqus/CAE, then use:

```text
Plug-ins > Abaqus MCP > Start Socket Bridge
```

### Option 2: Install the GUI menu loader

Copy `abaqus_plugins/mcp_control` into your Abaqus user plugin directory:

```powershell
Copy-Item -Recurse "<repo>\abaqus_plugins\mcp_control" "$env:USERPROFILE\abaqus_plugins\mcp_control"
```

Set `ABAQUS_MCP_HOME=<repo>`, restart Abaqus/CAE, then start the bridge from the Plug-ins menu.

## MCP Tools

- `ping`: verify the socket bridge and return live session telemetry.
- `check_abaqus_connection`: human-readable status.
- `run_python`: execute Abaqus Python with structured return values and diagnostics.
- `execute_script`: compatibility wrapper around `run_python`.
- `set_workdir`: change Abaqus working directory before creating jobs.
- `get_model_info`: inspect models, parts, sets, surfaces, jobs, and viewports.
- `inspect_part_mesh`: inspect counts, element types, global seed size, and optional element checks for a named part.
- `list_jobs`: list jobs in the current CAE session.
- `submit_job`: submit an existing job and wait for completion.
- `monitor_job_status`: list jobs or tail `.sta`/`.msg` diagnostics.
- `inspect_job_files`: inspect local job logs from an explicit directory without contacting the CAE session.
- `inspect_odb`: inspect ODB metadata and available outputs.
- `get_odb_info`: compatibility wrapper around `inspect_odb`.
- `capture_viewport`: capture viewport image as structured base64 data.
- `get_viewport_image`: compatibility wrapper returning a data URI.

Resources:

- `abaqus://status`
- `abaqus://session-telemetry`
- `abaqus://agent-instructions`

### Inspect job files without a CAE session

Call `inspect_job_files` with a job name and an existing absolute directory on
the MCP server, for example `job_name="Example"` and
`job_directory="C:/analysis/example"`. The tool reads that job's
`.sta`, `.msg`, `.dat`, and `.log`, so it also works for jobs launched
from the command line. Pass `encoding="gb18030"` for files written in that
encoding. The response reports a bounded tail, diagnostic messages, file
read errors, and the evidence for distinguishing a data check from a
completed analysis. An Explicit success footer at increment zero is not\naccepted as full analysis completion. A lock file or an incomplete log alone cannot establish
that the solver is still running.

## Recommended Workflow

1. Start Abaqus/CAE.
2. Run `Plug-ins > Abaqus MCP > Start Socket Bridge`.
3. From the MCP client, call `ping`.
4. Call `set_workdir` with a clean analysis folder.
5. Build or modify the model in small `run_python` chunks.
6. Validate with `get_model_info`, `list_jobs`, `monitor_job_status`, and `inspect_odb`.

## Design Note

The socket dispatcher and GUI-thread execution model are inspired by `Whfkl/Abaqus-Control-MCP`, which is MIT licensed. This project keeps an independent implementation and preserves the original `text-to-cae` Abaqus MCP compatibility tools.

## Notes

This project requires a licensed Abaqus/CAE installation on the user's machine. It does not include Abaqus binaries, analysis results, ODB files, or private local configuration.
## Inspecting a part mesh

`inspect_part_mesh(model_name, part_name, analysis_checks=false, label_limit=20)`
reads a named part in the current CAE session. It returns element and node
counts, an element type breakdown, and the global seed size in the model's
length units. No seed is reported for an orphan mesh. A zero seed on a
native part means a global size was not assigned.

Set `analysis_checks=true` to run Abaqus's element checks and retrieve warning,
failure and not-applicable counts with a bounded sample of element labels.
An empty mesh is reported separately. The tool leaves parts and jobs
unchanged. Use it to record each mesh before running a comparison; element
checks cannot by themselves establish mesh convergence.
