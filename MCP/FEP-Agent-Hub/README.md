# FEP Agent Hub

[中文说明](README.zh-CN.md)

FEP Agent Hub is an evidence-first, Windows-oriented CAE automation stack for:

- **F**reeCAD: parametric CAD and STEP handoff.
- **E**lmer FEM: Gmsh meshing, ElmerGrid conversion, structured SIF generation, solving, and result validation.
- **P**araView: persistent headless post-processing, images, CSV, and PVSM state export.

Each application is exposed as an independent local STDIO MCP server for Codex. The shared `open-cae-core` package provides workspace isolation, process whitelisting, structured responses, job state, logs, hashes, and an auditable evidence chain.

This directory is the CAE-Agent-Hub integration copy. The complete standalone project, including curated media assets, is maintained at [S2mon123/FEP-Agent-Hub](https://github.com/S2mon123/FEP-Agent-Hub).

## Validation status

Release validation was performed against the commands registered in Codex and real native CAE executables:

- 49/49 exposed tools invoked at least once.
- 52/52 contract calls passed.
- 46 unique tool capabilities returned `SUCCEEDED` in the full matrix.
- 3 context-appropriate calls returned their required `BLOCKED` contract: FreeCAD headless screenshots, electromagnetic excitation under the heat profile, and animation export from a one-step steady dataset. Animation export succeeds for verified multi-step datasets.
- The 10 mm cube steady heat-conduction benchmark passed the 300 K / 400 K / 350 K physics gates after the electromagnetic extension.
- The true transient heat benchmark passed 20/20 BDF1 time steps and matched the 20 s Fourier-series midpoint temperature within 0.318 K.
- The 2D harmonic open-circuit transformer-effect workflow passed field, flux, voltage, linearity, mesh-sensitivity, and ParaView gates.
- The 2D plane-stress simply-supported beam passed 10/10 quasi-static load levels, analytical deflection/stress/strain gates, and 10-frame ParaView export.
- The 2D steady laminar channel passed Poiseuille velocity-profile, flow-rate, no-slip, and pressure-drop gates at Re=100.
- The 2D transient Lenz-law eddy-current workflow passed 40/80/40 native time steps, four opposition-sign gates, time/mesh sensitivity, and 40-frame ParaView export.
- 17/17 routinely executed Python tests passed; the native pytest wrapper remains opt-in because it starts desktop CAE executables.

See the [transformer validation report](docs/transformer-induction-validation-report.zh-CN.md),
[beam validation report](docs/simply-supported-beam-validation-report.zh-CN.md),
[transient heat and flow report](docs/transient-heat-and-flow-validation-report.zh-CN.md),
[Lenz-law transient eddy-current report](docs/lenz-law-transient-eddy-current-validation-report.zh-CN.md),
[five-case research video validation](docs/five-case-research-video-validation.zh-CN.md),
[four-case research video and error review](docs/four-case-research-video-validation.zh-CN.md),
[release validation](docs/release-validation-report.md), and the original [Chinese heat case report](docs/OpenCAE_MCP_三软件协同仿真冒烟测试总结报告.md).

## Repository layout

```text
FEP_Agent_Hub/
├── mcp/
│   ├── freecad/                 # 15 tools
│   ├── elmer/                   # 17 tools
│   └── paraview/                # 17 tools
├── packages/open-cae-core/      # shared safety/evidence runtime
├── configs/                     # public templates + ignored local config
├── docs/                        # architecture and validation reports
├── examples/                    # curated thermal, electromagnetic, structural, and flow evidence
├── prompts/                     # reusable FEP workflow prompts
├── checklists/                  # evidence and release gates
├── scripts/                     # install, doctor, registration, smoke tests
├── tests/
└── workspace/                   # generated locally; gitignored
```

## Codex Skill

CAE Agent Hub includes [`Skill/fep-agent-hub`](../../Skill/fep-agent-hub/SKILL.md), a reusable Codex Skill that routes the six verified profiles, enforces the FreeCAD → Elmer FEM → ParaView sequence, and keeps workflow pass rates separate from numerical accuracy claims.

Invoke it with a request such as: `Use $fep-agent-hub to run and validate a transient heat benchmark.`

## Quick start

1. Copy `configs/open-cae.example.toml` to `configs/open-cae.local.toml` and set local executable paths.
2. Install the four editable packages into the repository virtual environment.
3. Run the unit and MCP protocol checks.

On Windows, use a short ASCII-only workspace path because some native CAE command-line runtimes do not reliably initialize from Unicode working directories. The source repository itself may remain in a Unicode path.

```powershell
cd <FEP_Agent_Hub>
.\scripts\install.ps1
$env:OPEN_CAE_CONFIG = "$PWD\configs\open-cae.local.toml"
.\.venv\Scripts\python.exe .\scripts\doctor.py
.\.venv\Scripts\python.exe .\scripts\protocol_smoke.py
.\.venv\Scripts\python.exe -m pytest -q
```

Run the native heat benchmark:

```powershell
.\scripts\run-smoke.ps1
```

Register the three servers with Codex:

```powershell
.\scripts\register-codex.ps1
codex mcp list
```

Run the workflow through the registered MCP protocol:

```powershell
.\.venv\Scripts\python.exe .\scripts\mcp_heat_smoke.py
.\.venv\Scripts\python.exe .\scripts\mcp_transformer_smoke.py
.\.venv\Scripts\python.exe .\scripts\mcp_beam_smoke.py
.\.venv\Scripts\python.exe .\scripts\mcp_transient_heat_smoke.py
.\.venv\Scripts\python.exe .\scripts\mcp_channel_flow_smoke.py
.\.venv\Scripts\python.exe .\scripts\mcp_full_validation.py
```

## Safety and claim policy

- No arbitrary shell, Python, `eval`, or executable tool is exposed.
- All project paths must remain inside the configured workspace.
- Native executables are restricted by name and launched with argument arrays and `shell=False`.
- Success requires process, log, artifact, data-field, finite-value, and physics gates where applicable.
- A declared unsupported capability must return `BLOCKED`; it must never fabricate output.
- Generated models, solver outputs, local paths, and private evidence stay gitignored.

## License

MIT. The repository does not redistribute FreeCAD, Gmsh, Elmer, ParaView, or their third-party components.
