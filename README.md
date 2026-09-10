# CAE Agent Hub

**Language:** English | [中文](README.zh-CN.md)

CAE Agent Hub is a collection of **MCP servers, reusable agent skills, solver automation workflows, and browser-based result viewers** for engineering simulation. It is designed to let AI coding clients such as **Codex, Cursor, Claude Code, and Claude Desktop** work with installed CAE applications and engineering solvers instead of producing only offline examples.

## What is included

The current repository provides:

- **MCP servers** for Abaqus/CAE, ANSYS Fluent, ANSYS Workbench/Mechanical, Ansys Electronics Desktop/HFSS, Altair HyperWorks, LAMMPS, OVITO, CalculiX, and the FreeCAD → Elmer FEM → ParaView FEP Agent Hub workflow.
- **Reusable Skills** for Abaqus modeling, setup, analysis, execution, postprocessing, optimization, and reference workflows, together with evidence-oriented workflows for several CAE ecosystems.
- **Subagent resources** stored under `Subagent/`.
- **Solver automation and supporting assets/models** stored under `assets/` and `models/`.
- The original **Text to CAE browser viewer** for inspecting lightweight `result_mesh.json` simulation results.
- Examples, tests, templates, and documentation intended to keep solver binaries, licenses, private paths, and generated results out of source control.

> The repository still contains some historical `text-to-cae` naming for compatibility with existing viewer cases.

## Repository

```text
https://github.com/Cai-aa/CAE-Agent-Hub
```

## Architecture

```text
AI client
   │
   ├── MCP server
   │      │
   │      └── live CAE application / solver
   │
   └── Skill / Subagent
          │
          └── modeling / setup / solving / validation workflow
                         │
                         ▼
                  native solver results
                         │
                         ▼
                lightweight result export
                         │
                         ▼
                browser viewer / report workflow
```

The repository separates responsibilities:

- **MCP servers** provide tool access to installed CAE applications and solvers.
- **Skills** provide reusable instructions for modeling, setup, solving, postprocessing, optimization, and validation.
- **Subagent resources** support task decomposition and specialized agent workflows.
- **CAE applications and solvers** perform the actual engineering calculations.
- **Viewer modules** inspect exported result data without requiring the solver to remain open.

## MCP Index

| MCP | Status | Purpose | Main entry points | Trigger keywords |
| --- | --- | --- | --- | --- |
| [Abaqus MCP](MCP/Abaqus) | Active | Connect MCP clients to a live Abaqus/CAE session through a local TCP bridge; run Python in the Abaqus kernel, inspect models, submit jobs, monitor status, inspect ODB files, and capture viewport images. | `mcp_server.py`, `abaqus_mcp_plugin.py`, `abaqus_plugins/mcp_control/` | Abaqus MCP, Abaqus/CAE, ODB, viewport, submit job, live Abaqus |
| [ANSYS Fluent MCP](MCP/Ansys/Fluent%20MCP) | Active | Detect Fluent, launch batch journals, track jobs/logs, and optionally manage live PyFluent sessions for Scheme, TUI, and Python probes. | `server.py`, `tools/fluent_bridge.py`, `tools/pyfluent_session.py` | Fluent, PyFluent, journal, TUI, CFD, Scheme |
| [ANSYS Workbench MCP](MCP/Ansys/Workbench%20MCP) | Active | Control Workbench and Mechanical through Python helpers plus an ACT bridge, with file-queue and socket-timer communication modes. | `server.py`, `tools/`, `workbench_plugin/` | Workbench, Mechanical, ACT, LS-DYNA, socket timer |
| [Ansys AEDT MCP](MCP/Ansys/AEDT%20MCP) | Active | Connect MCP clients to Ansys Electronics Desktop / HFSS through a raw TCP JSON bridge; inspect projects, create HFSS designs, save projects, and run small AEDT Python snippets. | `mcp_server.py`, `aedt_mcp_bridge.py`, `scripts/install_aedt_toolkit_button.ps1` | AEDT, HFSS, Electronics Desktop, antenna, S-parameters |
| [Altair HyperWorks MCP](MCP/HyperWorks) | Active | Control HyperWorks and a live HyperMesh session through typed, workspace-scoped tools plus an authenticated in-application Python bridge; inspect models and entities, run screened batch Tcl, and manage solver jobs. | `src/hyperworks_mcp/server.py`, `hyperworks_extension/`, `install_hyperworks_extension.ps1` | HyperWorks, HyperMesh, HyperView, OptiStruct, Radioss, live Python bridge |
| [LAMMPS MCP](MCP/LAMMPS) | Active | Detect a local LAMMPS executable, run explicit input decks, and retain job evidence. | `server.py`, `tools/atomistic_bridge.py` | LAMMPS, molecular dynamics, trajectory |
| [OVITO MCP](MCP/OVITO) | Active | Detect OVITO scripting support and run explicit postprocessing scripts with evidence logs. | `server.py`, `tools/atomistic_bridge.py` | OVITO, atomistic, visualization |
| [CalculiX MCP](MCP/CalculiX) | Active | Wrap the open-source CalculiX FEM solver (`ccx`): parse `.inp` decks, edit design variables, run `ccx`, read `.dat` results, export `result_mesh.json`, extract natural frequencies and viewer-renderable mode shapes, and run two-stage sizing optimization. | `mcp_server.py`, `tools/inp_parser.py`, `tools/solver.py`, `tools/result_exporter.py`, `tools/optimizer.py` | CalculiX, FEM, ccx, `.inp`, `.dat`, `.frd`, von Mises, design variables, sizing optimization, modal analysis, resonance |
| [FEP Agent Hub](MCP/FEP-Agent-Hub) | Active | Coordinate independent FreeCAD CAD, Elmer FEM, and ParaView postprocessing MCP servers. Includes verified thermal, electromagnetic, structural, and laminar-flow profiles with evidence gates. | `mcp/*/src/*_mcp/server.py`, `scripts/protocol_smoke.py`, `scripts/mcp_full_validation.py` | FreeCAD, Elmer FEM, ParaView, FEP, heat, transformer, beam, laminar flow, Lenz law |

> Adding a new MCP should follow the repository pattern: keep reusable source, examples, tests, and bilingual README files together, while excluding virtual environments, solver results, private paths, licenses, and generated project data.

## Skill Index

The repository contains an Abaqus master router and specialized workflow skills, plus evidence-oriented workflows for other CAE ecosystems.

### Abaqus

| Skill | Status | Purpose |
| --- | --- | --- |
| `abaqus` | Active | Master router for Abaqus FEA scripting and analysis workflows. |
| `abaqus-geometry` | Active | Create parts, sketches, extrusions, assemblies, and import CAD. |
| `abaqus-material` | Active | Define materials, sections, density, elasticity, plasticity, and common engineering properties. |
| `abaqus-mesh` | Active | Generate finite element meshes and choose element types. |
| `abaqus-interaction` | Active | Define contact, friction, tie constraints, connectors, and bonded surfaces. |
| `abaqus-amplitude` | Active | Define time-varying amplitudes for ramp, pulse, cyclic, or transient loads. |
| `abaqus-bc` | Active | Define boundary conditions such as fixed, pinned, clamped, displacement, and symmetry constraints. |
| `abaqus-docs` | Active | Download and manage abqpy / Abaqus API documentation. |
| `abaqus-field` | Active | Define initial conditions and predefined fields such as initial temperature or residual stress. |
| `abaqus-load` | Active | Apply concentrated forces, pressures, gravity, and distributed loads. |
| `abaqus-output` | Active | Configure field and history output requests. |
| `abaqus-step` | Active | Define analysis steps, procedures, increments, time periods, and nonlinear geometry settings. |
| `abaqus-static-analysis` | Active | Complete static structural workflow for stress, displacement, reactions, strength, and stiffness. |
| `abaqus-modal-analysis` | Active | Extract natural frequencies and mode shapes for vibration and resonance checks. |
| `abaqus-dynamic-analysis` | Active | Complete dynamic workflow for impact, crash, drop test, transient, explicit, or implicit dynamics. |
| `abaqus-thermal-analysis` | Active | Heat transfer workflow for steady-state or transient temperature distribution. |
| `abaqus-coupled-analysis` | Active | Coupled thermomechanical workflow for thermal stress and temperature-driven deformation. |
| `abaqus-contact-analysis` | Active | Multi-body contact workflow for friction, press fit, bolts, and assemblies. |
| `abaqus-fatigue-analysis` | Active | Fatigue and durability workflow for cycles, damage accumulation, and life prediction. |
| `abaqus-job` | Active | Create, submit, monitor, and manage Abaqus jobs and input files. |
| `abaqus-export` | Active | Export Abaqus geometry and results to STL, STEP, CSV, INP, or external formats. |
| `abaqus-odb` | Active | Read ODB results and extract stress, displacement, reaction force, and result summaries. |
| `abaqus-optimization` | Active | Configure Tosca optimization responses, objectives, constraints, and SIMP-style settings. |
| `abaqus-shape-optimization` | Active | Optimize fillet/notch/surface shape to reduce peak stress without topology removal. |
| `abaqus-topology-optimization` | Active | Topology optimization workflow for reducing mass while preserving stiffness. |

### Cross-ecosystem and evidence-oriented workflows

| Skill | Status | Purpose |
| --- | --- | --- |
| `fea-structural` | Reference | General structural FEA guidance across static, dynamic, nonlinear, and validation domains. |
| `fenics-fem` | Reference | FEniCS/dolfinx reference for weak forms, gmsh meshes, PDEs, and ParaView export. |
| `lammps-evidence-md` | Active | Evidence-first LAMMPS molecular-dynamics workflow. |
| `ovito-evidence-postprocessing` | Active | Evidence-first OVITO atomistic postprocessing workflow. |
| `ansys-mechanical-evidence-structural` | Active | Mechanical evidence and acceptance gates, complementary to the Workbench workflow skill. |
| `aedt-evidence-electromagnetics` | Active | Generic AEDT evidence workflow with Maxwell checks. |
| `comsol-motor-nvh-evidence` | Active | Checkpointed permanent-magnet motor NVH workflow coupling rotating electromagnetics, structural modes, acoustics, and Campbell validation. |
| `calculix-fem` | Active | Workflow for driving the CalculiX MCP, including `.inp` inspection, variable editing, solving, result extraction, and viewer export. |
| `calculix-sizing-optimization` | Active | Two-stage sizing optimization using LHS sweep and coordinate descent under stress/displacement or natural-frequency constraints. |
| `calculix-modal-analysis` | Active | Natural frequencies and mode shapes from a CalculiX `*FREQUENCY` step, with viewer export. |
| `fep-agent-hub` | Active | Evidence-first router for FreeCAD → Elmer FEM → ParaView workflows, verified profiles, physics gates, sensitivity checks, and scientifically honest animation semantics. |

> Adding a new Skill should keep the complete skill directory together with `SKILL.md`, `metadata.json` when available, upstream attribution, references, assets, and workflow scripts.

## Installation

### 1. Clone the repository

```powershell
git clone https://github.com/Cai-aa/CAE-Agent-Hub.git
Set-Location .\CAE-Agent-Hub
```

If you cloned the repository before the rename, the old `text-to-cae` remote may still work through GitHub redirects. Updating the remote URL is clearer:

```powershell
git remote set-url origin https://github.com/Cai-aa/CAE-Agent-Hub.git
```

### 2. Use an MCP server

Each MCP folder has its own README and environment template. The common local pattern is:

```powershell
Set-Location ".\MCP\<vendor>\<server folder>"
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -e .
```

Then register the server with your MCP-capable client using the example configuration provided by that MCP.

> Installing an MCP server does not install the underlying commercial CAE software or provide a solver license. The required CAE application, executable, license, bridge, and local environment must be available separately where applicable.

### 3. Use Skills

Skills are instruction modules, not solver binaries. Copy the complete skill directory into your agent's skill directory or attach the relevant `SKILL.md` as project context.

For Codex:

```powershell
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.codex\skills" | Out-Null
Copy-Item -Recurse -Force ".\Skill\abaqus\analysis\abaqus-static-analysis" "$env:USERPROFILE\.codex\skills\abaqus-static-analysis"
```

Example prompt:

```text
Use the abaqus-static-analysis, abaqus-mesh, abaqus-job, and abaqus-odb skills.
Build a complete Abaqus static-analysis workflow, run it if the Abaqus MCP
or local Abaqus CLI is available, and report the exact files and commands used.
```

## Text to CAE Viewer

The original viewer remains the browser-based result-inspection layer. It can display cases containing `result_mesh.json` even when the original solver is not installed.

```powershell
Set-Location .\viewer
npm.cmd install
npm.cmd run dev
```

Open the Vite URL, usually:

```text
http://127.0.0.1:4178/
```

Example cases:

```text
http://127.0.0.1:4178/?case=cantilever
http://127.0.0.1:4178/?case=hole-plate
http://127.0.0.1:4178/?case=hole-plate-modal
http://127.0.0.1:4178/?case=sphere-impact
http://127.0.0.1:4178/?case=milling-3d
http://127.0.0.1:4178/?case=gear-mesh
http://127.0.0.1:4178/?case=bullet-plate
```

## Repository Layout

```text
CAE-Agent-Hub/
├── .github/
│   └── workflows/
├── MCP/
│   ├── Abaqus/
│   ├── CalculiX/
│   ├── HyperWorks/
│   ├── LAMMPS/
│   ├── OVITO/
│   ├── FEP-Agent-Hub/
│   └── Ansys/
│       ├── AEDT MCP/
│       ├── Fluent MCP/
│       └── Workbench MCP/
├── Skill/
├── Subagent/
├── assets/
├── models/
├── viewer/
├── .gitignore
├── LICENSE
├── README.md
└── README.zh-CN.md
```

The repository root currently contains the MCP, Skill, Subagent, assets, models, viewer, workflow, licensing, and bilingual documentation areas shown above. Individual MCP and Skill directories contain their own implementation and documentation structures.

## Source Control Policy

The repository should include reusable source, documentation, tests, examples, templates, and skill instructions.

It should not include:

- CAE software binaries or licenses.
- Private machine paths or credentials.
- Virtual environments and package caches.
- Generated solver outputs such as ODB, case/data, AEDT results, Workbench projects, logs, and screenshots.
- Large local result artifacts that can be regenerated.

## Build

Build the frontend viewer:

```powershell
Set-Location .\viewer
npm.cmd run build
```

## Roadmap

The hub is designed to grow toward more mainstream simulation ecosystems:

- More solver-specific MCP servers.
- More productized Skill packs for repeatable modeling and validation workflows.
- Shared result export formats for viewer and report generation.
- Safer install prompts and verification scripts for each CAE application.

## Contributing a New MCP or Skill

When extending the hub:

1. Keep reusable source code and workflow instructions together.
2. Provide examples and tests where appropriate.
3. Provide a README for the new component.
4. Keep private paths, credentials, licenses, virtual environments, and generated solver results out of source control.
5. Follow the existing repository structure and naming conventions.
6. For Skills, preserve the complete `SKILL.md`-based workflow and supporting references/assets.

## License

This repository is released under the **MIT License**. See [LICENSE](LICENSE) for details.
