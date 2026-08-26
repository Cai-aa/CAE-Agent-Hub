# CAE Agent Hub

**Language:** English | [中文](README.zh-CN.md)

CAE Agent Hub is a collection of MCP servers, reusable agent skills, solver automation scripts, and browser result viewers for mainstream engineering simulation software. The goal is to let AI coding clients such as Codex, Cursor, Claude Code, or Claude Desktop work with real CAE tools instead of only generating offline examples.

The current repository includes:

- MCP servers for Abaqus/CAE, ANSYS Fluent, ANSYS Workbench Mechanical, and Ansys Electronics Desktop / HFSS.
- Abaqus-focused finite element skills organized by workflow stage.
- The original Text to CAE browser viewer for inspecting exported `result_mesh.json` simulation results.
- Example workflows and templates that keep solver binaries, licenses, private paths, and generated results out of source control.

## Repository

```text
https://github.com/Cai-aa/CAE-Agent-Hub
```

The old `text-to-cae` name is kept in some folder names for compatibility with existing viewer cases.

## Architecture

```text
AI client
  -> MCP server or skill instruction
  -> live CAE application or solver script
  -> native solver results
  -> exported lightweight viewer data
  -> browser inspection or report workflow
```

This repository separates responsibilities:

- **MCP servers** provide live tool access to installed CAE applications.
- **Skills** provide reusable modeling, setup, solving, postprocessing, and validation instructions.
- **CAE applications** perform the real solve.
- **Viewer modules** inspect exported result data without requiring the solver to be open.

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
| [CalculiX MCP](MCP/CalculiX) | Active | Wrap the open-source CalculiX FEM solver (`ccx`, GPLv2, no license): parse a `.inp` deck, edit design variables in place, run ccx fire-and-forget, read `.dat` text results, export them to `result_mesh.json` for the viewer, extract natural frequencies (`*FREQUENCY`) with viewer-renderable mode shapes, and run two-stage sizing optimization (LHS + coordinate descent) minimizing mass under stress/displacement or frequency constraints (avoid resonance). | `mcp_server.py`, `tools/inp_parser.py`, `tools/solver.py`, `tools/result_exporter.py`, `tools/optimizer.py` | CalculiX, FEM, ccx, .inp, .dat, .frd, von Mises, design variables, sizing optimization, modal analysis, resonance |
| [FEP Agent Hub](MCP/FEP-Agent-Hub) | Active | Coordinate three independent, workspace-scoped STDIO MCP servers for FreeCAD CAD, Elmer FEM meshing/solving, and ParaView postprocessing. Includes six verified thermal, electromagnetic, structural, and laminar-flow profiles with evidence gates. | `mcp/*/src/*_mcp/server.py`, `scripts/protocol_smoke.py`, `scripts/mcp_full_validation.py` | FreeCAD, Elmer FEM, ParaView, FEP, heat, transformer, beam, laminar flow, Lenz law |

> Adding a new MCP? Follow this pattern: keep reusable source, examples, tests, and bilingual README files; exclude virtual environments, solver results, private paths, licenses, and generated project data.

## Skill Index

| Skill | Status | Purpose | Trigger keywords |
| --- | --- | --- | --- |
| [abaqus](Skill/abaqus/core/abaqus) | Active | Master router for Abaqus FEA scripting and analysis workflows. | Abaqus, FEA, finite element, simulation, route skills |
| [abaqus-geometry](Skill/abaqus/modeling/abaqus-geometry) | Active | Create parts, sketches, extrusions, assemblies, and import CAD. | geometry, part, sketch, extrude, STEP, IGES |
| [abaqus-material](Skill/abaqus/modeling/abaqus-material) | Active | Define materials, sections, density, elasticity, plasticity, and common engineering properties. | material, steel, aluminum, Young's modulus, plastic |
| [abaqus-mesh](Skill/abaqus/modeling/abaqus-mesh) | Active | Generate finite element meshes and choose element types. | mesh, elements, nodes, C3D8R, refine |
| [abaqus-interaction](Skill/abaqus/modeling/abaqus-interaction) | Active | Define contact, friction, tie constraints, connectors, and bonded surfaces. | contact, friction, tie, touching parts, bonded |
| [abaqus-amplitude](Skill/abaqus/setup/abaqus-amplitude) | Active | Define time-varying amplitudes for ramp, pulse, cyclic, or transient loads. | amplitude, ramp, pulse, cyclic, time-varying |
| [abaqus-bc](Skill/abaqus/setup/abaqus-bc) | Active | Define boundary conditions such as fixed, pinned, clamped, displacement, and symmetry constraints. | fixed, clamped, pinned, support, constraint |
| [abaqus-docs](Skill/abaqus/setup/abaqus-docs) | Active | Download and manage abqpy / Abaqus API documentation. | Abaqus docs, API reference, abqpy |
| [abaqus-field](Skill/abaqus/setup/abaqus-field) | Active | Define initial conditions and predefined fields such as initial temperature or residual stress. | initial condition, predefined field, residual stress |
| [abaqus-load](Skill/abaqus/setup/abaqus-load) | Active | Apply concentrated forces, pressures, gravity, and distributed loads. | force, pressure, gravity, load |
| [abaqus-output](Skill/abaqus/setup/abaqus-output) | Active | Configure field and history output requests. | output request, field output, history output |
| [abaqus-step](Skill/abaqus/setup/abaqus-step) | Active | Define analysis steps, procedures, increments, time periods, and nonlinear geometry settings. | step, static step, dynamic step, frequency, nlgeom |
| [abaqus-static-analysis](Skill/abaqus/analysis/abaqus-static-analysis) | Active | Complete static structural workflow for stress, displacement, reactions, strength, and stiffness. | static, stress, displacement, strength, reaction force |
| [abaqus-modal-analysis](Skill/abaqus/analysis/abaqus-modal-analysis) | Active | Extract natural frequencies and mode shapes for vibration and resonance checks. | modal, frequency, vibration, resonance, mode shape |
| [abaqus-dynamic-analysis](Skill/abaqus/analysis/abaqus-dynamic-analysis) | Active | Complete dynamic workflow for impact, crash, drop test, transient, explicit, or implicit dynamics. | impact, crash, drop test, transient, explicit |
| [abaqus-thermal-analysis](Skill/abaqus/analysis/abaqus-thermal-analysis) | Active | Heat transfer workflow for steady-state or transient temperature distribution. | thermal, heat transfer, conduction, convection |
| [abaqus-coupled-analysis](Skill/abaqus/analysis/abaqus-coupled-analysis) | Active | Coupled thermomechanical workflow for thermal stress and temperature-driven deformation. | thermal stress, expansion, temperature deformation |
| [abaqus-contact-analysis](Skill/abaqus/analysis/abaqus-contact-analysis) | Active | Multi-body contact workflow for friction, press fit, bolts, and assemblies. | contact analysis, friction, press fit, bolt |
| [abaqus-fatigue-analysis](Skill/abaqus/analysis/abaqus-fatigue-analysis) | Active | Fatigue and durability workflow for cycles, damage accumulation, and life prediction. | fatigue, durability, cycles, life prediction |
| [abaqus-job](Skill/abaqus/execution/abaqus-job) | Active | Create, submit, monitor, and manage Abaqus jobs and input files. | run analysis, submit job, input file, execute |
| [abaqus-export](Skill/abaqus/execution/abaqus-export) | Active | Export Abaqus geometry and results to STL, STEP, CSV, INP, or external formats. | export, STL, STEP, CSV, INP |
| [abaqus-odb](Skill/abaqus/postprocessing/abaqus-odb) | Active | Read ODB results and extract stress, displacement, reaction force, and result summaries. | ODB, maximum stress, displacement, reaction force |
| [abaqus-optimization](Skill/abaqus/optimization/abaqus-optimization) | Active | Configure Tosca optimization responses, objectives, constraints, and SIMP-style settings. | optimization, objective, constraint, Tosca |
| [abaqus-shape-optimization](Skill/abaqus/optimization/abaqus-shape-optimization) | Active | Optimize fillet/notch/surface shape to reduce peak stress without topology removal. | shape optimization, fillet, notch, stress concentration |
| [abaqus-topology-optimization](Skill/abaqus/optimization/abaqus-topology-optimization) | Active | Topology optimization workflow for reducing mass while preserving stiffness. | topology optimization, weight reduction, stiffness |
| [fea-structural](Skill/abaqus/reference/fea-structural) | Reference | General structural FEA guidance across static, dynamic, nonlinear, and validation domains. | structural FEA, nonlinear, validation |
| [fenics-fem](Skill/abaqus/reference/fenics-fem) | Reference | FEniCS/dolfinx finite element reference for weak forms, gmsh meshes, PDEs, and ParaView export. | FEniCS, dolfinx, PDE, weak form, gmsh |
| [lammps-evidence-md](Skill/lammps/lammps-evidence-md) | Active | Evidence-first LAMMPS molecular-dynamics workflow. | LAMMPS, molecular dynamics, stress-strain |
| [ovito-evidence-postprocessing](Skill/ovito/ovito-evidence-postprocessing) | Active | Evidence-first OVITO atomistic postprocessing workflow. | OVITO, visualization, atomistic |
| [ansys-mechanical-evidence-structural](Skill/Ansys/ansys-mechanical-evidence-structural) | Active | Mechanical evidence and acceptance gates, complementary to the Workbench workflow skill. | Mechanical, ACT, PyMechanical, MAPDL |
| [aedt-evidence-electromagnetics](Skill/Ansys/aedt-evidence-electromagnetics) | Active | Generic AEDT evidence workflow with Maxwell checks. | AEDT, Maxwell, HFSS, PyAEDT |
| [comsol-motor-nvh-evidence](Skill/comsol/comsol-motor-nvh-evidence) | Active | Checkpointed permanent-magnet motor NVH workflow coupling rotating electromagnetics, structural modes, acoustics, and Campbell validation. | COMSOL, motor NVH, Maxwell force, modes, Campbell |
| [calculix-fem](Skill/calculix/calculix-fem) | Active | Workflow for driving the CalculiX MCP: inspect a `.inp` deck, edit design variables in place, run ccx, read `.dat` results, export `result_mesh.json`. | CalculiX, FEM, ccx, .inp, linear static |
| [calculix-sizing-optimization](Skill/calculix/calculix-sizing-optimization) | Active | Two-stage sizing optimization on a CalculiX shell/beam deck (LHS sweep + coordinate descent) to minimize mass s.t. stress/displacement bounds, or s.t. a natural-frequency floor on a modal deck (avoid resonance). | CalculiX, sizing optimization, mass reduction, LHS, coordinate descent, resonance, natural frequency |
| [calculix-modal-analysis](Skill/calculix/calculix-modal-analysis) | Active | Natural frequencies and mode shapes from a CalculiX `*FREQUENCY` step; mode N exports to the viewer as a stress-free shape. | CalculiX, modal, natural frequency, mode shape, resonance, vibration |
| [fep-agent-hub](Skill/fep-agent-hub) | Active | Evidence-first router for FreeCAD → Elmer FEM → ParaView workflows, verified profiles, physics gates, sensitivity checks, and honest animation semantics. | FEP Agent Hub, FreeCAD, Elmer FEM, ParaView, CAE validation |

> Adding a new skill? Keep the complete skill directory together with `SKILL.md`, `metadata.json` when available, upstream attribution, references, assets, and any scripts needed by the workflow.

## Installation

### Clone

```powershell
git clone https://github.com/Cai-aa/CAE-Agent-Hub.git
Set-Location .\CAE-Agent-Hub
```

If you cloned the repository before the rename, the old `text-to-cae` remote may still work through GitHub redirects. Updating the remote URL is clearer:

```powershell
git remote set-url origin https://github.com/Cai-aa/CAE-Agent-Hub.git
```

### Use an MCP server

Each MCP folder has its own README and environment template. The common local pattern is:

```powershell
Set-Location ".\MCP\<vendor>\<server folder>"
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -e .
```

Then register the server with your MCP-capable client using the example config in that folder.

### Use skills

Skills are instruction modules, not solver binaries. Copy the complete skill directory into your agent's skill directory or attach the relevant `SKILL.md` as project context.

Codex example:

```powershell
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.codex\skills" | Out-Null
Copy-Item -Recurse -Force ".\Skill\abaqus\analysis\abaqus-static-analysis" "$env:USERPROFILE\.codex\skills\abaqus-static-analysis"
```

Suggested prompt:

```text
Use the abaqus-static-analysis, abaqus-mesh, abaqus-job, and abaqus-odb skills. Build a complete Abaqus static-analysis workflow, run it if the Abaqus MCP or local Abaqus CLI is available, and report the exact files and commands used.
```

## Text to CAE Viewer

The viewer is still included as the browser result-inspection layer. It can display cases that contain `result_mesh.json` even when the solver is not installed.

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
  MCP/
    Abaqus/
    CalculiX/
    Ansys/
      AEDT MCP/
      Fluent MCP/
      Workbench MCP/
  Skill/
    abaqus/
      core/
      modeling/
      setup/
      analysis/
      execution/
      postprocessing/
      optimization/
      reference/
  models/
  viewer/
```

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
- More productized skill packs for repeatable modeling and validation workflows.
- Shared result export formats for viewer and report generation.
- Safer install prompts and verification scripts for each CAE application.
