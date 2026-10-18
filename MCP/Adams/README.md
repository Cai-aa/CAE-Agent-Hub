# Adams MCP

**Language:** English | [中文](README.zh-CN.md)

A standalone Python stdio MCP server for a user-owned Hexagon Adams/View
installation on Windows. This package was extracted from a working Codex
configuration targeting Adams 2024.1. It provides 16 tools and three resources.

## Scope

- Probe the installation, configured release and localhost Command Server.
- Create project manifests and CMD files; add box rigid bodies, revolute joints,
  gravity and rotational motions.
- Run bounded Adams/View batch jobs with isolated run directories, file-backed
  stdout/stderr, disconnected stdin and process-tree timeout cleanup.
- Extract and summarize single-column numeric exports; retain validation,
  SHA-256 hashes and run reports.
- Query or send prefix-allowlisted commands to a user-started localhost listener.

Direct Solver execution, plot creation and animation export remain unsupported.
Other releases require their own native smoke test. A capability probe detects
components; it does not itself prove a successful simulation or license checkout.

## Installation and configuration

Run from this package directory with Python 3.11 or later:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

Copy [config.example.toml](config.example.toml) outside the checkout, replace the
installation/launcher/workspace placeholders, and set `ADAMS_MCP_CONFIG` to that
file. Without it, the server reads `~/.adams-mcp/config.toml`. Environment overrides
are `ADAMS_ROOT`, `ADAMS_LAUNCHER`, `ADAMS_RELEASE`, `ADAMS_MCP_WORKSPACE`,
`ADAMS_COMMAND_SERVER_PORT` and `ADAMS_MCP_RAW_COMMANDS`.

Merge [codex-config.example.toml](codex-config.example.toml) into your Codex config,
or adapt [client-config.example.json](client-config.example.json) for another MCP
client. The Python command must name the environment where this package is
installed. Start with `python -m adams_mcp.server` or the `adams-mcp` entry point.

## Workflow and tools

Call `adams_environment_probe`, `adams_capabilities`, then `adams_smoke_test` when
native execution is intended. The native smoke test reads `para_4bar.cmd` from
the user's installed examples; vendor sample source is not distributed here.

| Group | Tools |
| --- | --- |
| Discovery | `adams_environment_probe`, `adams_capabilities`, `adams_live_status` |
| Projects | `adams_project_create`, `adams_project_inspect` |
| Modeling | `adams_rigid_body_create`, `adams_revolute_joint_create`, `adams_gravity_set`, `adams_rotational_motion_create` |
| Execution | `adams_simulation_run`, `adams_batch_run_cmd`, `adams_smoke_test` |
| Results | `adams_result_summary`, `adams_evidence_latest` |
| Live | `adams_live_query`, `adams_live_command` |

Resources: `adams://environment`, `adams://capabilities`, `adams://evidence/latest`.

See [examples/project_recipe.json](examples/project_recipe.json) for ordered tool
arguments. For a project with joints, the runner requests the first joint's `FY`
history. Other result component paths must be discovered in Adams.

## Validation and trust boundary

A process exit and `validation.status=VERIFIED` on a plain CMD run only prove
the requested batch gates. Simulation claims additionally require model
verification, a simulation command, actual numeric exports and a completed time
range. `validation.json` records each gate. No-joint models and arbitrary CMD
runs do not automatically prove a numeric simulation. Numeric summaries support
one finite scalar per line; general multi-column CSV parsing is not implemented.

The workspace check constrains input file locations, not the operations inside
an Adams command file. Execute only trusted CMD files. Likewise, localhost and
prefix allowlists are not a security sandbox: permitted live commands can modify
the open model or write files. Raw commands are disabled by default. Stop the
listener when not needed. Runtime evidence contains local paths and should be
reviewed before sharing.

## Tests

From this package directory:

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts\protocol_smoke.py
```

Unit and protocol tests do not need Adams. Windows-only subprocess regressions
use temporary mock launchers. Native validation requires the installed solver,
its examples and a valid user license; see the [validation record](VALIDATION.md).

## License

The bridge source is under the [MIT license](LICENSE). Adams, its binaries,
documentation, examples and licenses remain the property of their owners and
are not included in this package.
