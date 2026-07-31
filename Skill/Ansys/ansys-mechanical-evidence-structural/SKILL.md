---
name: ansys-mechanical-evidence-structural
description: Evidence-first Ansys Mechanical structural automation through Workbench RunWB2 journals, Mechanical Scripting/ACT ExtAPI, or PyMechanical gRPC. Use when Codex must build, solve, inspect, postprocess, or validate static, modal, thermal-structural, contact, nonlinear, or other Mechanical analyses with mesh metrics, MAPDL logs, reaction balance, RST files, numeric exports, and result images.
---

# Ansys Mechanical Evidence Structural

Treat Mechanical as its own solver module. Workbench is an orchestration route,
not proof that the Mechanical analysis solved.

## Start

```powershell
ai-cae-toolbox context-scope --solver ansys-mechanical
ai-cae-toolbox bridge-plan --solver ansys-mechanical --objective "<objective>"
ai-cae-toolbox create-run --solver ansys-mechanical --case <case-name> --objective "<objective>"
```

If MCP is available, prefer:

- `mechanical_check_installation`
- `mechanical_run_workbench_journal_file`
- `mechanical_run_python_controller_file`
- `mechanical_validate_result_summary_file`

## Choose One Control Route

1. Use `RunWB2.exe -B -R <journal.wbjn>` for project-level orchestration.
2. Use Mechanical Scripting/ACT with `ExtAPI` for model-tree operations.
3. Use PyMechanical gRPC for an external Python controller and explicit session lifecycle.

Record the selected route and do not let two controllers own the same session.

## Model and Solve

Audit units, geometry scale, materials, contacts, joints, loads, constraints,
large-deflection setting, solver controls, result requests, and mesh controls.
Use stable names for bodies, named selections, contacts, loads, and results.

Before claiming success, read
[references/acceptance-gates.md](references/acceptance-gates.md). A `.mechdat`,
Workbench project, or result PNG alone is insufficient.

## Finish

Export `.mechdat` or `.wbpj`, `file.rst`, `solve.out`, mesh metrics, load and
reaction data, result CSV/JSON, PNG images, and `report.md`. State every
approximation such as bonded contacts, suppressed bodies, linear materials, or
disabled large deformation.

```powershell
ai-cae-toolbox scan-evidence <run-dir>
ai-cae-toolbox generate-report <run-dir>
```
