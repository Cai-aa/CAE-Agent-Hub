# ANSYS Workbench MCP

This folder contains a portable MCP server plus an ANSYS Mechanical ACT bridge for controlling Workbench and Mechanical from an MCP client.

It is intentionally limited to reusable source files. Local virtual environments, job outputs, queue responses, solver result databases, and user-specific paths are not included.

## Contents

- `server.py` exposes Workbench, Mechanical, file queue, and socket timer MCP tools.
- `tools/` contains Python-side helpers for launching Workbench jobs and communicating with Mechanical.
- `workbench_plugin/` contains the ACT extension loaded by ANSYS Mechanical.
- `.env.example` documents the environment variables needed on each machine.
- `examples/codex_config.example.toml` shows a Codex MCP registration shape.

## Install

From this folder:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -e .[mechanical]
```

Copy `.env.example` to `.env` and set your local ANSYS paths.

## MCP Client Setup Prompts

Copy one of these prompts into the MCP-capable client you want to use. Replace `<repo>` with the absolute path to this folder, for example `C:\path\to\text-to-cae\MCP\Ansys\Workbench MCP`.

### Codex

```text
Install this local ANSYS Workbench MCP server for Codex.

Project folder:
<repo>

Please configure Codex MCP with a stdio server named `ansys-workbench`:
- command: <repo>\.venv\Scripts\python.exe
- args: ["<repo>\server.py"]
- cwd: <repo>
- env:
  - ANSYS_ROOT=<your ANSYS install root, for example C:\Program Files\ANSYS Inc\v261>
  - WORKBENCH_MCP_ROOT=<repo>
  - WORKBENCH_MCP_QUEUE_ROOT=<repo>\workbench_queue
  - WORKBENCH_MCP_HOST=127.0.0.1
  - WORKBENCH_MCP_PORT=9885

If the virtual environment does not exist, create it and install the project with:
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -e .[mechanical]

After configuring the server, verify it by listing MCP tools and then run `workbench_detect_tool`.
```

### Claude Code

```text
Add this local ANSYS Workbench MCP server to Claude Code.

Project folder:
<repo>

Use a stdio MCP server named `ansys-workbench`:
- command: <repo>\.venv\Scripts\python.exe
- args: ["<repo>\server.py"]
- cwd: <repo>
- env:
  - ANSYS_ROOT=<your ANSYS install root>
  - WORKBENCH_MCP_ROOT=<repo>
  - WORKBENCH_MCP_QUEUE_ROOT=<repo>\workbench_queue
  - WORKBENCH_MCP_PORT=9885

If dependencies are missing, create `.venv` and run `pip install -e .[mechanical]`.
Then restart Claude Code and confirm the Workbench MCP tools are available.
```

### Claude Desktop

```text
Help me add this local ANSYS Workbench MCP server to Claude Desktop.

Project folder:
<repo>

Create or update Claude Desktop's MCP configuration with a stdio server:

"ansys-workbench": {
  "command": "<repo>\\.venv\\Scripts\\python.exe",
  "args": ["<repo>\\server.py"],
  "cwd": "<repo>",
  "env": {
    "ANSYS_ROOT": "<your ANSYS install root>",
    "WORKBENCH_MCP_ROOT": "<repo>",
    "WORKBENCH_MCP_QUEUE_ROOT": "<repo>\\workbench_queue",
    "WORKBENCH_MCP_HOST": "127.0.0.1",
    "WORKBENCH_MCP_PORT": "9885"
  }
}

Create the virtual environment first if needed, then restart Claude Desktop and verify that the Workbench MCP tools appear.
```

### Cursor

```text
Configure this local ANSYS Workbench MCP server in Cursor.

Project folder:
<repo>

Add a stdio MCP server named `ansys-workbench` using:
- command: <repo>\.venv\Scripts\python.exe
- args: ["<repo>\server.py"]
- cwd: <repo>
- environment:
  - ANSYS_ROOT=<your ANSYS install root>
  - WORKBENCH_MCP_ROOT=<repo>
  - WORKBENCH_MCP_QUEUE_ROOT=<repo>\workbench_queue
  - WORKBENCH_MCP_HOST=127.0.0.1
  - WORKBENCH_MCP_PORT=9885

If `.venv` is missing, create it and install dependencies with `pip install -e .[mechanical]`.
After saving the MCP settings, reload Cursor and run a tool discovery check.
```

### Generic MCP Client

```json
{
  "mcpServers": {
    "ansys-workbench": {
      "command": "<repo>\\.venv\\Scripts\\python.exe",
      "args": ["<repo>\\server.py"],
      "cwd": "<repo>",
      "env": {
        "ANSYS_ROOT": "<your ANSYS install root>",
        "WORKBENCH_MCP_ROOT": "<repo>",
        "WORKBENCH_MCP_QUEUE_ROOT": "<repo>\\workbench_queue",
        "WORKBENCH_MCP_HOST": "127.0.0.1",
        "WORKBENCH_MCP_PORT": "9885"
      }
    }
  }
}
```

## Configure Mechanical ACT

Install the plugin files into the ANSYS ACT extensions directory for your version, for example:

```text
%APPDATA%\Ansys\v261\ACT\extensions\WorkbenchMCP.xml
%APPDATA%\Ansys\v261\ACT\extensions\WorkbenchMCP\main.py
%APPDATA%\Ansys\v261\ACT\extensions\WorkbenchMCP\mechanical_queue_processor.py
%APPDATA%\Ansys\v261\ACT\extensions\WorkbenchMCP\mechanical_socket_timer_v7.py
%APPDATA%\Ansys\v261\ACT\extensions\WorkbenchMCP\mechanical_analysis_workflows.py
```

When the ACT plugin is installed outside this folder, set these environment variables before launching Mechanical:

```text
WORKBENCH_MCP_ROOT=<path to this folder>
WORKBENCH_MCP_QUEUE_ROOT=<path to this folder>\workbench_queue
WORKBENCH_MCP_PORT=9885
```

Open Mechanical and use the `Workbench MCP` toolbar:

- `Process MCP Queue` processes pending file queue requests once.
- `Socket Timer Start` starts the localhost socket bridge.
- `Socket Timer Stop` stops the socket bridge.

The plugin also auto-starts the queue timer and socket timer by default. Set `WORKBENCH_MCP_AUTO_START_SOCKET=0` or `WORKBENCH_MCP_AUTO_START_QUEUE=0` to disable those behaviors.

## MCP Tools

The server exposes tools for:

- detecting Workbench and PyMechanical
- launching Workbench journals
- launching Mechanical Python scripts
- reading job logs and status
- submitting queue requests to Mechanical
- executing Python in the currently open Mechanical session through the queue or socket timer bridge

### Rotating-static and prestressed-modal tools

The added tools cover the complete structural-analysis chain:

- `mechanical_readiness_tool` and `mechanical_probe_session_tool` prove that the bridge, `Project`, `Model`, and `Model.Analyses` are usable.
- `workbench_create_prestressed_modal_chain_tool` creates Static Structural, zero-RPM Modal, and prestressed Modal Workbench systems.
- `mechanical_geometry_inventory_tool` and `mechanical_import_geometry_tool` import geometry and report bodies, face/edge IDs, named selections, contacts, and analyses.
- `mechanical_create_named_selection_tool` creates an explicit geometry named selection from entity IDs.
- `mechanical_create_analysis_chain_tool` creates rotating static, baseline modal, and prestressed modal analyses in one Mechanical model and assigns the prestress source.
- `mechanical_validate_rotor_job_tool` and `mechanical_configure_rotor_model_tool` validate and apply material, bonded contacts, support, axis, and rotational speed.
- `mechanical_validate_mesh_job_tool` and `mechanical_mesh_and_validate_tool` apply global/local sizing and return node/element evidence.
- `mechanical_solve_analysis_tool` and `mechanical_workflow_status_tool` submit ordered solves and poll long-running work without automatic resubmission after timeout.
- `mechanical_extract_structural_results_tool` and `mechanical_extract_modal_results_tool` extract deformation, stress, frequency, and prestress frequency shifts.
- `mechanical_export_evidence_tool` exports result images and tables with `error | versioned | replace`; the default is `error`.

Model-changing tools use `transport="queue"` by default so that Mechanical executes them on its UI thread. Use `transport="socket"` only for read-only diagnostics or operations explicitly proven safe in that context.

Recommended call order:

```text
mechanical_readiness_tool
  -> mechanical_probe_session_tool
  -> mechanical_import_geometry_tool
  -> mechanical_geometry_inventory_tool
  -> mechanical_create_named_selection_tool
  -> mechanical_create_analysis_chain_tool
  -> mechanical_validate_rotor_job_tool
  -> mechanical_configure_rotor_model_tool
  -> mechanical_validate_mesh_job_tool
  -> mechanical_mesh_and_validate_tool
  -> mechanical_solve_analysis_tool
  -> mechanical_workflow_status_tool
  -> mechanical_extract_structural_results_tool
  -> mechanical_extract_modal_results_tool
  -> mechanical_export_evidence_tool
```

Example rotating-static input:

```json
{
  "analysis_name": "Rotating_Static",
  "rotational_speed_rpm": 6000,
  "rotation_axis": "X",
  "fixed_support_named_selection": "Disk_Bore",
  "contact_mode": "existing",
  "expected_contact_count": 20,
  "material_name": "Structural Steel",
  "large_deflection": true
}
```

Run the validation tool first. Material, speed, named selections, and contact count must come from the confirmed model or teaching job specification; the MCP does not invent them.
See `examples/rotor_analysis.example.json` for a complete rotor-model and mesh input example.

Run the offline tests with:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -m unittest discover -s tests -v
```

## Notes

This project still requires a licensed ANSYS installation on the user's machine. It does not include ANSYS binaries, solver result files, or private local configuration.
