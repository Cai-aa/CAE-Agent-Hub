---
name: cst-simulation-workflow
description: "Use this skill when driving CST Studio Suite through the CST MCP for electromagnetic simulation workflows: creating or opening CST projects, resolving missing inputs, selecting templates, setting up geometry/materials/ports/boundaries/mesh/solvers/monitors, running or planning simulations, extracting S-parameters/far-field/near-field/eigenmode results, validating outputs, parameter sweeps, optimization handoff, and report generation."
---

# CST Simulation Workflow

Use this skill as the workflow and decision layer. Use the CST MCP as the execution layer.

Prefer the repository CST MCP native tools for live session control. Use the vendored `cst_runtime_*` or `cst_toolbox_*` wrappers for larger command catalogs, workspace pipelines, result export, parameter sweeps, and optimization helpers.

## Operating Modes

First classify the request:

| Mode | Use when | Action |
| --- | --- | --- |
| Plan only | User asks for a scheme, script outline, or workflow | Do not run CST; produce the setup plan and assumptions |
| New project | User wants a new CST case | Select a template, resolve inputs, create a run project |
| Existing project | User provides a `.cst` path or asks to modify an open project | Inspect first, then work on a copy unless explicitly told otherwise |
| Parameter sweep | User asks for ranges, cases, or comparison | Use sweep preview before running cases |
| Optimization | User asks to improve S11, gain, bandwidth, coupling, etc. | Hand off to runtime optimization workflow after confirming objective and bounds |

## Standard Workflow

1. Detect CST MCP availability and CST Design Environment status.
2. Determine whether to create a new project, open a copy of an existing `.cst`, or only generate a plan.
3. Identify the simulation class and select a template when appropriate.
4. Resolve missing inputs using the parameter policy.
5. Present a compact defaults card before expensive solves unless the user already said to use defaults or run directly.
6. Build or modify geometry, materials, coordinate system, ports/excitations, boundaries, mesh, solver, and monitors.
7. Save the working project before running a solver.
8. Run the solver only when the user requested execution or accepted the defaults.
9. Extract result tree items and export requested data.
10. Validate results against the objective and evidence requirements.
11. Generate a concise report with assumptions, files, commands/tools used, result paths, and validation status.
12. Close/cleanup the CST project/session and report any nonblocking residual locks or access-denied cleanup messages.

## Reference Files

Read only the reference file needed for the current task:

- `references/workflow.md` for the end-to-end workflow and mode-specific execution details.
- `references/parameter-policy.md` for required questions, defaults, derived values, and existing-project inspection.
- `references/mcp-tool-map.md` for this repository's CST MCP tool names and when to prefer native vs runtime tools.
- `references/templates.md` for V1 simulation templates and default values.
- `references/result-validation.md` for S-parameter, far-field, near-field, eigenmode, sweep, and report validation.
- `references/cst-red-lines.md` for correctness and safety rules that must not be violated.

## Input Policy

Ask at most one compact clarification when critical information is missing. If the user says "directly run", "use defaults", "先默认", or equivalent, use defaults and record them in the report.

Critical inputs that usually require confirmation:

- simulation case type
- target frequency or frequency band
- new project vs existing project
- primary result objective
- whether to actually run the solver

Defaultable inputs include units, background, common metals, antenna boundaries, solver choice, monitor frequencies, mesh level, and standard result exports. See `references/parameter-policy.md`.

## Execution Rules

- Do not overwrite a user's source `.cst` project. Copy it to a run directory unless the user explicitly requests in-place edits.
- Inspect existing projects before changing them.
- Prefer CST Macro Recorder-style VBA history blocks for modeling operations when no higher-level MCP tool exists.
- Save before solving.
- Treat solver success as unverified until result files, result tree entries, or exported data confirm it.
- For long or costly solves, state the assumptions and expected outputs before running.

## Result Rules

- Do not treat complex S-parameter values as dB. Convert with `20*log10(abs(S11))`.
- Do not report `Abs(E)` as gain. Use `Realized Gain`, `Gain`, or `Directivity` for far-field gain claims.
- Keep model-building/session operations separate from result-reading operations when the tool surface exposes separate modes.
- Include exact evidence paths for project files, exports, reports, and logs.

## V1 Scope

Focus V1 on:

- a single new standard antenna case, especially a 2.4 GHz Wi-Fi/IoT microstrip patch antenna;
- opening an existing `.cst`, inspecting it, changing parameters, and rerunning on a copy;
- S11, VSWR, far-field gain/directivity, radiation pattern, eigenmode frequency, and concise Markdown report outputs;
- parameter sweep preview/run through the CST MCP sweep tools.

Use 77 GHz 1x4 radar patch array as a demonstration template after the basic workflow is stable.
