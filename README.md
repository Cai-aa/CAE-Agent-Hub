# CAE Agent Hub

<p align="center"><strong>Connect AI to real CAE. Keep the evidence behind every result.</strong></p>
<p align="center"><strong>English</strong> · <a href="README.zh-CN.md">简体中文</a></p>

![CAE Agent Hub workflow: AI clients → MCP and skills → CAE solvers → results and checks](assets/readme/workflow.svg)

A hub of **MCP tools, reusable skills, and result viewers** for engineering simulation. Connect clients such as Codex, Claude Code, Claude Desktop, and Cursor to modeling, meshing, solving, postprocessing, and validation workflows.

[Simulation gallery](#simulation-gallery) · [Tool index](#tool-index) · [Quick start](#quick-start) · [Result viewer](#text-to-cae-viewer)

Also includes [Subagent](Subagent/) resources and [Agentic PD](MCP/Peridigm) workflows with curated recorded demos.

<a id="simulation-gallery"></a>

## Representative simulation results

One representative case per software module with verifiable results. Modules without a suitable result are omitted for now. Click an image for full size; see the [full atlas](docs/simulation-atlas.md) for additional cases, checks, and provenance.

<table>
<tr>
<td width="50%" valign="top">
<a href="assets/readme/frame-result.png"><img src="assets/readme/frame-result.png" width="100%" alt="Abaqus · Frame dynamics" loading="lazy"></a><br>
<strong>Abaqus · Frame dynamics</strong><br>
20/30 kN pulse response; native ODB displacement contour, scale 300×.<br>
<a href="docs/simulation-atlas.md#frame">Case and provenance →</a>
</td>
<td width="50%" valign="top">
<a href="assets/readme/mechanical-clevis-deformation.png"><img src="assets/readme/mechanical-clevis-deformation.png" width="100%" alt="Workbench / Mechanical · Clevis-pin contact" loading="lazy"></a><br>
<strong>Workbench / Mechanical · Clevis-pin contact</strong><br>
30 kN static contact; M3 deformation contour and three-mesh displacement check.<br>
<a href="docs/simulation-atlas.md#mechanical-clevis">Case and provenance →</a>
</td>
</tr>
<tr>
<td width="50%" valign="top">
<a href="assets/readme/elbow-result.png"><img src="assets/readme/elbow-result.png" width="100%" alt="Fluent · Laminar elbow flow" loading="lazy"></a><br>
<strong>Fluent · Laminar elbow flow</strong><br>
Re≈498; fine-mesh full-pipe static pressure drop 2.93381 Pa.<br>
<a href="docs/simulation-atlas.md#elbow">Case and provenance →</a>
</td>
<td width="50%" valign="top">
<a href="assets/readme/heatsink-result.png"><img src="assets/readme/heatsink-result.png" width="100%" alt="COMSOL · Heatsink conduction" loading="lazy"></a><br>
<strong>COMSOL · Heatsink conduction</strong><br>
30 W fine-mesh peak 80.403 °C; two meshes and heat-balance checks.<br>
<a href="docs/simulation-atlas.md#heatsink">Case and provenance →</a>
</td>
</tr>
<tr>
<td width="50%" valign="top">
<a href="assets/readme/maxwell--B_midplane_30.png"><img src="assets/readme/maxwell--B_midplane_30.png" width="100%" alt="AEDT / Maxwell · Magnetic actuator" loading="lazy"></a><br>
<strong>AEDT / Maxwell · Magnetic actuator</strong><br>
Four-angle magnetostatic sweep with field, torque, and inductance results.<br>
<a href="docs/simulation-atlas.md#maxwell">Case and provenance →</a>
</td>
<td width="50%" valign="top">
<a href="assets/readme/cst-radar77-field.png"><img src="assets/readme/cst-radar77-field.png" width="100%" alt="CST · 77 GHz radar-array electric field" loading="lazy"></a><br>
<strong>CST · 77 GHz radar-array electric field</strong><br>
Port 1 excitation; native electric-field amplitude (V/m), time-domain hex solve.<br>
<a href="docs/simulation-atlas.md#cst-radar77">Case and provenance →</a>
</td>
</tr>
<tr>
<td width="50%" valign="top">
<a href="assets/readme/bracket-hex--235_fine_mises_average75.png"><img src="assets/readme/bracket-hex--235_fine_mises_average75.png" width="100%" alt="ANSA → Abaqus · All-hex bracket" loading="lazy"></a><br>
<strong>ANSA → Abaqus · All-hex bracket</strong><br>
Native preprocessing and 1000 N static solve with mesh and stress checks.<br>
<a href="docs/simulation-atlas.md#bracket-hex">Case and provenance →</a>
</td>
<td width="50%" valign="top">
<a href="assets/readme/radioss-cylinder-impact.png"><img src="assets/readme/radioss-cylinder-impact.png" width="100%" alt="HyperWorks / Radioss · Cylinder-plate impact" loading="lazy"></a><br>
<strong>HyperWorks / Radioss · Cylinder-plate impact</strong><br>
Mises stress (GPa) at 0.12 ms; energy error and scope documented in case notes.<br>
<a href="docs/simulation-atlas.md#radioss-cylinder">Case and provenance →</a>
</td>
</tr>
</table>

Case notes document image types, units, display scales, and validation scope. Engineering use requires the relevant engineer’s review.

<a id="tool-index"></a>

## Tools and workflow navigation

Choose an adapter by application. Each README covers installation, client configuration, and limitations. This is a source index; runtime availability depends on local software, versions, licenses, and bridge state.

| Application / toolchain | Workflow entry point |
| --- | --- |
| [Abaqus](MCP/Abaqus) | CAE kernel scripts, job submission, ODBs, and viewport exports |
| [Fluent](MCP/Ansys/Fluent%20MCP) | Batch journals, job logs, and PyFluent sessions |
| [Workbench / Mechanical](MCP/Ansys/Workbench%20MCP) | Workbench automation and a Mechanical ACT bridge |
| [AEDT](MCP/Ansys/AEDT%20MCP) | Electronics Desktop projects and electromagnetics automation |
| [COMSOL](MCP/COMSOL) | Multiphysics models, parameters, solving, and result export |
| [CST Studio Suite](MCP/CST) | EM modeling, solving, 1D results, and Touchstone export |
| [HyperWorks](MCP/HyperWorks) | HyperMesh sessions, entity inspection, and solver jobs |
| [CalculiX](MCP/CalculiX) | Open-source FEM, modal analysis, and sizing optimization |
| [LAMMPS](MCP/LAMMPS) | Molecular dynamics input execution and job evidence |
| [OVITO](MCP/OVITO) | Scripted atomistic postprocessing and visualization |
| [FreeCAD → Elmer → ParaView](MCP/FEP-Agent-Hub) | An open-source CAD, mesh, solve, and postprocessing chain |
| [PyAnsys MCP collection](MCP/Ansys/PyAnsys) | Specialized PyAnsys adapters with individual documentation |
| [Adams](MCP/Adams/README.md) | Rigid-body mechanisms and bounded batch jobs; native numeric checks passed, live integration unverified ([validation](MCP/Adams/VALIDATION.md)) |
| [Peridigm](MCP/Peridigm) | Prototype with verified profiles for peridynamics and damage-result replay |

**Skills:** [Full index](Skill/README.md) · [Abaqus workflows](Skill/abaqus/README.md) · [Ansys structural workflow](Skill/Ansys/ansys-structural-workbench) · [Cylinder O-grid](Skill/General/cylinder-o-grid)

<details>
<summary>Expand the detailed skill catalog</summary>

- [adams-evidence-mbd](Skill/Adams/adams-evidence-mbd/SKILL.md): rigid-body
  mechanism modeling, transient View batch execution and numeric reaction evidence.

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
| [`peridigm-evidence-fracture`](Skill/peridigm/peridigm-evidence-fracture) | Prototype · verified profiles | Progressive clarification, frozen physics, bounded repair, real solver evidence and honest material-point/fracture interpretation. |
| `fep-agent-hub` | Active | Evidence-first router for FreeCAD → Elmer FEM → ParaView workflows, verified profiles, physics gates, sensitivity checks, and scientifically honest animation semantics. |

> Adding a new Skill should keep the complete skill directory together with `SKILL.md`, `metadata.json` when available, upstream attribution, references, assets, and workflow scripts.

</details>

<a id="quick-start"></a>

## Quick start

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

Each adapter has its own dependencies and launch command; open its README from the table above. Install the required CAE application and confirm its license, then follow that adapter’s environment, dependency, and MCP registration steps. Install the in-application bridge where required.

Start with environment detection or a read-only model query, then run an example. Use a separate output directory and retain inputs, solver logs, and validation records.

### Use skills

Skills are instruction modules, not solver binaries. Copy the complete skill directory into your agent's skill directory or attach the relevant `SKILL.md` as project context.

Codex example:

```powershell
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.codex\skills" | Out-Null
Copy-Item -Recurse -Force ".\Skill\abaqus\analysis\abaqus-static-analysis" "$env:USERPROFILE\.codex\skills\abaqus-static-analysis"
```

Suggested prompt:

```text
Use the abaqus-static-analysis, abaqus-mesh, abaqus-job, and abaqus-odb skills. Check the Abaqus environment and inspect the current session first. Build a cantilever static-analysis case in a separate directory, mesh and solve it, extract ODB results, check force balance, and report the actual files, commands, and incomplete checks.
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

### Agentic PD recorded demos

Run the viewer as above, then open [the Peridigm entry](viewer/peridigm.html) at `/peridigm.html`. Choose either demo:

- `/peridigm.html?demo=elastic` — [two-point elastic verification](models/peridigm-elastic): 6 actual frames, source gold and an independent oscillator comparison.
- `/peridigm.html?demo=fracture` — [precracked tensile damage demonstration](models/peridigm-notched-tension): 3,200 material points, 31 actual display frames and independently reconstructed bond failure.

Replay requires neither Peridigm nor SSH. `npm run build` bundles both datasets for static hosting. These are recorded verified results, not a browser solver or a connected AI service. New solves use the [Peridigm CLI/MCP](MCP/Peridigm) and its [Skill](Skill/peridigm/peridigm-evidence-fracture). See [demo provenance and limits](MCP/Peridigm/DEMO.md).

## Repository Layout

```text
CAE-Agent-Hub/
  MCP/
    Abaqus/
    CalculiX/
    Adams/
    Peridigm/
    COMSOL/
    CST/
    FEP-Agent-Hub/
    HyperWorks/
    LAMMPS/
    OVITO/
    Ansys/
      AEDT MCP/
      Fluent MCP/
      Workbench MCP/
      PyAnsys/
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
  Subagent/
  models/
  viewer/
  assets/readme/   # Curated figures and provenance
  docs/           # Case notes and training material
```

## Source Control Policy

The repository should include reusable source, documentation, tests, examples, templates, and skill instructions. Curated public replay fixtures under `models/peridigm-*` are an explicit exception to excluding generated run data: they include only selected fields, verified summaries, canonical inputs and hashes, with attribution and capability limits. Full native jobs and private runtime state stay outside the repository.

It should not include:

- CAE software binaries or licenses.
- Private machine paths or credentials.
- Virtual environments and package caches.
- Raw solver outputs such as ODB, case/data, AEDT results, Workbench projects, and runtime logs.
- Large local result artifacts that can be regenerated.

Curated documentation images may live in `assets/readme/` with provenance, case definitions, and scope notes.

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

## Peridigm development module

The [Peridigm module](MCP/Peridigm/README.md) adds a shared CLI/MCP workflow, confirmed specifications, bounded repair and material-point viewer export. Qualified profiles cover two-point elastic code verification and a synthetic precracked tensile damage demonstration. Engineering strength and experimental accuracy remain unverified. See its [architecture map](MCP/Peridigm/ARCHITECTURE.md) and [Skill](Skill/peridigm/peridigm-evidence-fracture/SKILL.md).
