# COMSOL MCP

This directory contains an MCP server for controlling COMSOL Multiphysics. The
preferred local backend is Python MPh (`mph.Client`), which can start and
manage a local COMSOL session without asking the user to manually run
`comsol.exe mphserver -port 2036`. The Java bridge / `mphserver` backend is
kept as a fallback for remote-server or process-isolation workflows.

The first target workflow is practical live automation:
open an existing `.mph` model, change parameters, solve, export plots/tables,
and save a copy.

The server intentionally separates three concerns:

- Python MCP server: exposes tools to Codex and manages process state.
- MPh backend: starts a local COMSOL session through JPype and COMSOL Java API.
- Java bridge: speaks newline-delimited JSON over stdin/stdout for fallback mode.
- COMSOL Java API: loaded directly by MPh or by the bridge at runtime.

This keeps Codex and MCP startup usable even when COMSOL is not installed or no
license is currently available.

## Contents

- `mcp_server.py`: FastMCP stdio server.
- `tools/detect.py`: COMSOL, Java, API jar, and run-directory detection.
- `tools/mph_session.py`: preferred MPh session backend.
- `tools/bridge_client.py`: MCP-owned Java bridge process client.
- `tools/model_tools.py`: model, parameter, solve, evaluation, and export helpers.
- `bridge/`: Java bridge source and Maven build file.
- `examples/codex_config.example.toml`: Codex MCP configuration example.
- `tests/`: unit tests that do not require COMSOL.

## Install

From this directory:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -e .[dev]
```

Copy `.env.example` to `.env` and fill the local paths:

```powershell
Copy-Item .env.example .env
```

Important variables:

- `COMSOL_ROOT`: COMSOL Multiphysics installation root.
- `COMSOL_MCP_RUNS_DIR`: output directory for MCP-generated files.
- `COMSOL_MCP_BRIDGE_JAR`: packaged Java bridge jar.
- `COMSOL_MCP_BRIDGE_COMMAND`: explicit bridge command, if you do not use a jar.

## Preferred MPh Workflow

Recommended first validation:

1. `comsol_detect_tool`
2. `comsol_mph_availability_tool`
3. `comsol_start_session_async_tool`
4. `comsol_start_session_status_tool`
5. `comsol_session_status_tool`
6. `comsol_open_model_session_tool`
7. `comsol_model_summary_session_tool`
8. `comsol_set_parameter_session_tool`
9. `comsol_solve_session_tool`
10. `comsol_evaluate_session_tool`
11. `comsol_export_session_tool`
12. `comsol_save_session_tool`

Use `comsol_start_session_tool` only when a blocking startup is acceptable.
The async startup tool avoids MCP client timeouts while COMSOL initializes its
JVM and stand-alone client. Repeated async starts reuse the existing startup job
instead of launching multiple COMSOL sessions.

Use the Java bridge / `mphserver` tools only when you explicitly need remote
server mode or process isolation.

## Build The Java Bridge

The bridge can be packaged with Maven:

```powershell
Set-Location .\bridge
mvn package
```

For a real COMSOL backend, the Java process must be launched with COMSOL Java
API jars on the classpath. The bridge uses reflection, so the source code does
not need to compile against a specific COMSOL version. A typical explicit
command looks like:

```powershell
java -cp "bridge\target\comsol-bridge-0.1.0.jar;<COMSOL jar paths>" com.caeagenthub.comsol.ComsolBridge
```

Set that command in `COMSOL_MCP_BRIDGE_COMMAND`.

For protocol-only testing, launch the bridge with:

```powershell
$env:COMSOL_MCP_PLACEHOLDER_BACKEND="true"
java -jar bridge\target\comsol-bridge-0.1.0.jar
```

The placeholder backend does not control COMSOL; it only validates the MCP to
bridge protocol.

## Codex Configuration

Add a server like this to `C:\Users\<you>\.codex\config.toml`:

```toml
[mcp_servers.comsol]
command = "E:\\Code\\CAE-Agent-Hub\\MCP\\COMSOL\\.venv\\Scripts\\python.exe"
args = ["E:\\Code\\CAE-Agent-Hub\\MCP\\COMSOL\\mcp_server.py"]
cwd = "E:\\Code\\CAE-Agent-Hub\\MCP\\COMSOL"
env = {
  COMSOL_ROOT = "C:\\Program Files\\COMSOL\\COMSOL62\\Multiphysics",
  COMSOL_MCP_RUNS_DIR = "E:\\Code\\CAE-Agent-Hub\\MCP\\COMSOL\\comsol_runs",
  COMSOL_MCP_BRIDGE_JAR = "E:\\Code\\CAE-Agent-Hub\\MCP\\COMSOL\\bridge\\target\\comsol-bridge-0.1.0.jar"
}
```

## Java Bridge Fallback

Fallback validation order:

1. `comsol_detect_tool`
2. `comsol_mphserver_status_tool`
3. `comsol_start_mphserver_tool`
4. `comsol_start_bridge_tool`
5. `comsol_bridge_ping_tool`
6. `comsol_connect_tool`
7. `comsol_open_model_tool`
8. `comsol_model_info_tool`
9. `comsol_set_parameter_tool`
10. `comsol_run_study_tool`
11. `comsol_export_plot_tool`
12. `comsol_export_table_tool`
13. `comsol_save_model_tool`

Do not treat detection as proof that a license is usable. License availability
is only proven once COMSOL or `mphserver` accepts a real operation.

## MCP Tools

- `comsol_detect_tool`
- `comsol_mph_availability_tool`
- `comsol_start_session_tool`
- `comsol_start_session_async_tool`
- `comsol_start_session_status_tool`
- `comsol_cancel_start_session_tool`
- `comsol_connect_session_tool`
- `comsol_session_status_tool`
- `comsol_disconnect_session_tool`
- `comsol_open_model_session_tool`
- `comsol_new_model_session_tool`
- `comsol_model_summary_session_tool`
- `comsol_list_parameters_session_tool`
- `comsol_set_parameter_session_tool`
- `comsol_solve_session_tool`
- `comsol_evaluate_session_tool`
- `comsol_export_session_tool`
- `comsol_save_session_tool`
- `comsol_start_bridge_tool`
- `comsol_bridge_status_tool`
- `comsol_stop_bridge_tool`
- `comsol_bridge_ping_tool`
- `comsol_mphserver_status_tool`
- `comsol_start_mphserver_tool`
- `comsol_stop_mphserver_tool`
- `comsol_connect_tool`
- `comsol_new_model_tool`
- `comsol_open_model_tool`
- `comsol_save_model_tool`
- `comsol_model_info_tool`
- `comsol_list_parameters_tool`
- `comsol_set_parameter_tool`
- `comsol_list_studies_tool`
- `comsol_run_study_tool`
- `comsol_evaluate_tool`
- `comsol_export_plot_tool`
- `comsol_export_table_tool`

## Tests

The Python tests avoid COMSOL and only validate detection helpers and bridge
protocol behavior:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Repository Rules

Do not commit COMSOL binaries, license files, generated `.mph` models, exported
solver results, local `.env`, or `comsol_runs/`.

For a checkpointed permanent-magnet motor noise, vibration, and harshness
workflow, use the repository
[`comsol-motor-nvh-evidence`](../../Skill/comsol/comsol-motor-nvh-evidence/SKILL.md)
skill together with this MCP. The skill adds model-contract, smoke-matrix,
Campbell-data, and release-evidence gates without storing proprietary models or
solver results.
