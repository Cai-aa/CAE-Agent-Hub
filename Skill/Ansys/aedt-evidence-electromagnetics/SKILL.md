---
name: aedt-evidence-electromagnetics
description: Evidence-first Ansys Electronics Desktop and PyAEDT automation for Maxwell, HFSS, Q3D, Icepak, and related electromagnetic workflows. Use when Codex must check AEDT/PyAEDT, create or run a real AEDT design, verify the selected design and solution type, extract fields or matrices, export an .aedt project, or distinguish direct PyAEDT work from an AEDT MCP bridge.
---

# AEDT Evidence Electromagnetics

Use the repository toolbox and a user-owned AEDT installation. Never infer a
successful electromagnetic solve from `ansysedt.exe`, a project file, or a
geometry screenshot.

## Start

```powershell
ai-cae-toolbox context-scope --solver aedt
ai-cae-toolbox bridge-plan --solver aedt --objective "<objective>"
ai-cae-toolbox create-run --solver aedt --case <case-name> --objective "<objective>"
ai-cae-toolbox write-smoke-template --solver aedt --run-dir <run-dir>
```

If MCP is available, prefer:

- `aedt_check_installation`
- `aedt_run_pyaedt_script_file`
- `scan_run_evidence`
- `generate_run_report`

## Select the Correct Route

- Use direct PyAEDT when the requested solver or API surface is not exposed by
  the installed MCP.
- Use an AEDT MCP only for capabilities it actually exposes.
- Do not build HFSS when the task requires Maxwell, or claim that an HFSS-focused
  MCP completed a Maxwell workflow.
- Record AEDT version, PyAEDT version, project, design name, design type, solution
  type, and whether a new or existing desktop session was used.

## Execute

Keep scripts in `scripts/`, source parameters in `inputs/`, project outputs in
`outputs/`, and field plots/tables in `exports/`. Make every geometry dimension,
material, excitation, boundary, setup, and sweep explicit.

For Maxwell matrix work, audit winding polarity and reciprocity. For HFSS, audit
ports, modes, radiation boundaries, frequency setup, adaptive convergence, and
S-parameter passivity. Read [references/acceptance-gates.md](references/acceptance-gates.md)
before interpreting solver output.

## Finish

Collect the AEDT project, solver/adaptive log, mesh statistics, numeric CSV/JSON,
field images, and a report. Clearly label any external circuit calculation or
Python-derived plot that is not a native AEDT result.

```powershell
ai-cae-toolbox scan-evidence <run-dir>
ai-cae-toolbox generate-report <run-dir>
```
