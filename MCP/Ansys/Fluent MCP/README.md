# ANSYS Fluent MCP

This folder contains a portable MCP server for controlling ANSYS Fluent from MCP-capable clients. It follows the source layout used by `MCP/Ansys/Workbench MCP` while focusing on Fluent-specific workflows:

- batch journal execution through `fluent.exe`
- job metadata and log tracking
- optional live PyFluent sessions for Scheme, TUI, and Python-side probes

The project contains only reusable source files and configuration templates. It does not include ANSYS binaries, licenses, case/data files, local virtual environments, or generated solver output.

## Contents

- `server.py` exposes Fluent MCP tools over stdio.
- `tools/fluent_bridge.py` detects Fluent and launches batch journal jobs.
- `tools/pyfluent_session.py` manages optional live PyFluent sessions.
- `.env.example` documents machine-specific environment variables.
- `examples/codex_config.example.toml` shows a Codex MCP registration shape.
- `tests/` contains standard-library unit tests for the pure Python tool layer.

## Install

From this folder:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -e .[pyfluent]
```

If you only need batch journal launching and environment detection, the base install is enough:

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
```

Copy `.env.example` to `.env` and set your local ANSYS paths.

## MCP Client Setup Prompts

Replace `<repo>` with the absolute path to this folder, for example `C:\path\to\text-to-cae\MCP\Ansys\Fluent MCP`.

### Codex

```text
Install this local ANSYS Fluent MCP server for Codex.

Project folder:
<repo>

Please configure Codex MCP with a stdio server named `ansys-fluent`:
- command: <repo>\.venv\Scripts\python.exe
- args: ["<repo>\server.py"]
- cwd: <repo>
- env:
  - ANSYS_ROOT=<your ANSYS install root, for example C:\Program Files\ANSYS Inc\v261>
  - FLUENT_EXE=<path to fluent.exe>
  - FLUENT_MCP_JOBS_DIR=<repo>\jobs

If the virtual environment does not exist, create it and install the project with:
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -e .[pyfluent]

After configuring the server, verify it by listing MCP tools and then run `fluent_detect_tool`.
```

### Generic MCP Client

```json
{
  "mcpServers": {
    "ansys-fluent": {
      "command": "<repo>\\.venv\\Scripts\\python.exe",
      "args": ["<repo>\\server.py"],
      "cwd": "<repo>",
      "env": {
        "ANSYS_ROOT": "<your ANSYS install root>",
        "FLUENT_EXE": "<path to fluent.exe>",
        "FLUENT_MCP_JOBS_DIR": "<repo>\\jobs"
      }
    }
  }
}
```

## MCP Tools

- `fluent_detect_tool`: detect `fluent.exe`, `ANSYS_ROOT`, job folders, and `ansys-fluent-core`.
- `fluent_run_journal_tool`: launch a Fluent journal asynchronously through `fluent.exe`.
- `fluent_job_status_tool`: inspect a launched Fluent job.
- `fluent_job_log_tool`: read stdout or stderr tails for a launched job.
- `fluent_list_jobs_tool`: list recent Fluent jobs.
- `fluent_launch_session_tool`: start a live PyFluent session owned by the MCP process.
- `fluent_list_sessions_tool`: list live PyFluent sessions.
- `fluent_session_info_tool`: read basic metadata from a PyFluent session.
- `fluent_execute_scheme_tool`: evaluate a small Scheme expression in Fluent.
- `fluent_run_tui_tool`: run a Fluent TUI command in a live PyFluent session.
- `fluent_run_python_tool`: run Python in the MCP process with a `session` variable bound to the PyFluent session.
- `fluent_close_session_tool`: close a live PyFluent session.

## Example Workflows

### Batch journal

```text
1. Call `fluent_detect_tool`.
2. Write or select a Fluent journal file in a clean case folder.
3. Call `fluent_run_journal_tool` with `journal_path`.
4. Poll `fluent_job_status_tool`.
5. Inspect `fluent_job_log_tool` if the run exits unexpectedly.
```

The default batch command is equivalent to:

```powershell
fluent.exe 3ddp -g -t2 -i case.jou
```

### Live PyFluent

```text
1. Call `fluent_detect_tool` and confirm `pyfluent.available` is true.
2. Call `fluent_launch_session_tool`.
3. Call `fluent_session_info_tool`.
4. Validate the session with `fluent_execute_scheme_tool` using `(+ 2 3)`.
5. Use small TUI or Python probes before making larger solver changes.
6. Call `fluent_close_session_tool` when finished.
```

## Test

The included tests use the Python standard library:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Notes

This server requires a licensed local ANSYS Fluent installation for real solver operations. The PyFluent tools launch sessions owned by the MCP server process; if the MCP client restarts the server, those sessions are lost and should be relaunched.
