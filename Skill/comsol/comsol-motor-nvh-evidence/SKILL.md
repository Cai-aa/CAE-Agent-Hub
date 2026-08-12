---
name: comsol-motor-nvh-evidence
description: Evidence-first COMSOL Java API and batch workflow for permanent-magnet motor NVH. Use when Codex must build, resume, solve, validate, or report a 2D motor model that couples rotating magnetic machinery, Maxwell-force harmonics, structural eigenmodes, pressure acoustics, acoustic-structure interaction, far-field SPL, or Campbell sweeps; also use when converting an existing motor NVH prompt or run into public-safe scripts, checkpoints, exports, and acceptance evidence.
---

# COMSOL Motor NVH Evidence

Execute a checkpointed motor-NVH workflow and prove each completed stage with solver-native evidence. Treat reference models as read-only fact sources, never as the target model.

## Required context

1. Read `MCP/COMSOL/README.md` and inspect only the files needed for the selected COMSOL backend.
2. Use the repository COMSOL MCP for installation detection, MPh session startup, model inspection, parameter changes, study execution, evaluation, export, and save-copy operations. Use `comsolcompile` plus COMSOL batch only when the independent Java API build requires capabilities not exposed by typed MCP tools.
3. Read [references/model-contract.md](references/model-contract.md) before creating geometry, physics, studies, or result nodes.
4. Read [references/evidence-gates.md](references/evidence-gates.md) before solving or claiming success.

## Execution sequence

1. Inspect the environment without writing to reference models.
2. Create a new run directory. Use [scripts/New-ComsolMotorNvhRun.ps1](scripts/New-ComsolMotorNvhRun.ps1) when a project scaffold is needed.
3. Extract source-backed facts once into `facts.json`; use that compact file in later stages.
4. Create the target with `ModelUtil.create()` for the independent Java API route, or use the MCP MPh session route for an existing user-owned model. Parameterize geometry, selections, materials, physics, mesh, studies, and exports.
5. Build without solving. Stop if environment, topology, selections, material tables, physics compilation, or mesh gates fail.
6. Compile with `comsolcompile`; do not substitute ordinary `javac`.
7. Solve structural modes and save a new checkpoint.
8. Solve the time-periodic electromagnetic field and force harmonics; save a new checkpoint.
9. Run the mandatory reduced NVH smoke matrix. Do not start the full sweep until every smoke value is finite and traceable.
10. Run the full speed/harmonic sweep, in batches when memory is constrained.
11. Postprocess from solved checkpoints. Fix result expressions or export nodes without rerunning physics unless solution evidence is invalid.
12. Validate exported CSV data with [scripts/validate_nvh_exports.py](scripts/validate_nvh_exports.py), scan run evidence, and generate the report.

For the MPh route, start with `comsol_detect_tool`,
`comsol_mph_availability_tool`, `comsol_start_session_async_tool`, and
`comsol_start_session_status_tool`. Continue with the session-scoped open,
summary, parameter, solve, evaluate, export, and save tools. Detection alone is
not license proof; require a real solver-native operation.

## Checkpoint contract

Use monotonic checkpoints such as:

```text
models/01_built.mph
models/02_modes_solved.mph
models/03_em_solved.mph
models/04_smoke_solved.mph
models/05_final_solved.mph
```

Resume only when the checkpoint, corresponding successful solver log, and validation record all exist. File presence alone is insufficient.

## Modeling guardrails

- Use named selections for physics assignments. Use numeric entity IDs only as topology diagnostics for the current build.
- Preserve the verified finalization method, usually Form Assembly with identity pairs for the motor/acoustic partition. Do not switch to Form Union to silence a pairing problem.
- Do not invent missing magnet, winding, B-H, support, boundary, or observation-point data.
- Do not change materials, polarity, winding phase, force scale, damping, or acoustic pressure to match a reference curve.
- Keep unsolved Campbell cells missing/null; never convert them to `0 dB`.
- Do not describe scan-line, interpolation, or dashboard effects as physical deformation.
- Do not claim a study solved unless the COMSOL exit code, log, checkpoint, and expected numerical exports agree.

## Failure policy

Use `PENDING`, `INSPECTED`, `CONFIGURED`, `BUILT`, `COMPILED`, `SOLVED`, `EXPORTED`, `VERIFIED`, `FAILED`, or `BLOCKED` for stages.

Allow automatic repair only for paths, quoting, version-specific API names, missing output directories, result expressions, export-node compatibility, and machine-specific solver allocation. Never auto-repair the physical definition to improve agreement.

Report final status only as `PASSED`, `PASSED_WITH_LIMITATIONS`, `FAILED`, or `BLOCKED`.

## Public-safe output

- Keep executable paths in environment variables or ignored private configuration.
- Do not commit `.mph`, `.class`, solver logs, commercial manuals, source reference models, videos, or large generated datasets.
- Remove usernames, attachment identifiers, workstation paths, license-server details, and temporary-directory names.
- Commit only reusable scripts, relative-path examples, small synthetic/sample tables, and documentation.
