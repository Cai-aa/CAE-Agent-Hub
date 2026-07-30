# LAMMPS MCP

This MCP server provides explicit local LAMMPS input execution and OVITO batch
postprocessing. It only contains reusable source, examples, and templates.
Potential files, trajectories, restart files, solver logs, images, and local
machine paths stay outside version control.

## Install

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -e .[dev]
Copy-Item .env.example .env
```

Set `LAMMPS_EXE` for LAMMPS. Set `OVITOS_EXE` or `OVITO_PYTHON` for automated
OVITO scripts; `OVITO_EXE` by itself only records GUI availability.

## Codex Setup

```toml
[mcp_servers.lammps_ovito]
command = "E:\\Code\\CAE-Agent-Hub\\MCP\\LAMMPS\\.venv\\Scripts\\python.exe"
args = ["E:\\Code\\CAE-Agent-Hub\\MCP\\LAMMPS\\server.py"]
cwd = "E:\\Code\\CAE-Agent-Hub\\MCP\\LAMMPS"
env = { LAMMPS_EXE = "C:\\Program Files\\LAMMPS\\lmp.exe", OVITOS_EXE = "C:\\Program Files\\OVITO Basic\\ovitos.exe" }
```

## Tools

- `lammps_detect_tool` and `lammps_run_input_tool`
- `ovito_detect_tool` and `ovito_run_script_tool`
- `atomistic_job_status_tool`, `atomistic_job_log_tool`, and `atomistic_list_jobs_tool`

Start by detecting the executable, then use an explicit input deck or OVITO
script. The job directory keeps process stdout, stderr, and metadata. LAMMPS
outputs follow the paths in its input deck, so use a clean case directory.

`examples/in.smoke` uses `pair_style zero` and only validates the LAMMPS
execution path. It is not a material model. OVITO exports are postprocessing
evidence, not proof that the upstream simulation completed or is physically
valid.

## Test

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```
