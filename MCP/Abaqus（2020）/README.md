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
- `list_jobs`: list jobs in the current CAE session.
- `submit_job`: submit an existing job and wait for completion.
- `monitor_job_status`: list jobs or tail `.sta`/`.msg` diagnostics.
- `inspect_odb`: inspect ODB metadata and available outputs.
- `get_odb_info`: compatibility wrapper around `inspect_odb`.
- `capture_viewport`: capture viewport image as structured base64 data.
- `get_viewport_image`: compatibility wrapper returning a data URI.

Resources:

- `abaqus://status`
- `abaqus://session-telemetry`
- `abaqus://agent-instructions`

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
