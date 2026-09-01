---
name: ansys-structural-workbench
description: "Operate or inspect live ANSYS Workbench Mechanical structural simulations through the configured MCP, including model setup, materials, connections, loads, mesh, solve, convergence, validation, and reporting. Use whenever a user asks Codex to create, configure, inspect, mesh, solve, troubleshoot, or validate a live Workbench structural analysis. Before model decisions or mutation, load ansys-workbench-practical-reference once as the book-distilled router and then the matching narrow reference Skill. Load static-modeling for every Static Structural task, plus nonlinear-contact for contact, friction, plasticity, large deformation, buckling, or nonlinear convergence. Do not use for theory-only questions or Fluent/CFX operation."
---

# ANSYS Structural Workbench

Operate Workbench as an engineering workflow with explicit quality gates. Treat the MCP as the execution adapter and this Skill as the analysis, meshing, validation, and reporting policy.

## Mandatory book-guidance route

Before inspecting settings for engineering acceptance, mutating the model, meshing, or solving, load `ansys-workbench-practical-reference` once and use it to select the physics-specific book-derived guidance. This is a required intake gate, not an optional source lookup.

- Every Static Structural task must load `ansys-workbench-static-modeling-reference`.
- A static task with contact or friction must load both `ansys-workbench-static-modeling-reference` and `ansys-workbench-nonlinear-contact-reference`.
- Also load `ansys-workbench-nonlinear-contact-reference` for plasticity, large deflection, buckling, stabilization, changing contact state, or nonlinear convergence.
- Modal, transient, explicit, thermal, and optimization tasks load only their matching narrow reference Skill; do not load unrelated book domains.

The book-derived Skills govern modeling assumptions and physical checks. This Skill governs live MCP actions, evidence, and safe execution. Record which guidance Skills were loaded in the task intake or final report. Do not repeatedly re-route after the applicable set has been loaded.

## Start safely

1. Discover the available Workbench MCP tools and read `references/mcp-adapter.md`. Require the registered server name `ansys-workbench` unless the user configured an equivalent alias.
2. Probe both bridge health and live Workbench/Mechanical state. A reachable server is not proof that a project, Model, or analysis is loaded.
3. Convert the request into the contract in `references/job-spec.md`, including every applicable analysis profile. Use a temporary in-memory object unless a saved spec benefits the task.
4. Inspect the current project before mutation. Never clear, overwrite, suppress, or replace existing user work without explicit authorization.
5. Record assumptions. Stop for missing information only when no conservative, reversible default exists.

If the MCP lacks a required capability, use its generic Workbench/Mechanical script-execution tool when available. Otherwise report the exact unsupported gate; do not fabricate completion.

## Select references

Always read:

- `references/core-workflow.md`
- `references/quality-gates.md`

Then read only what applies:

- Analysis behavior: `references/analysis-profiles.md`
- Mesh generation or review: `references/mesh-orchestration.md` and `references/mesh-profiles.md`
- Mesh repair loop: `references/mesh-closed-loop.md`
- Solver failure or warnings: `references/solver-diagnostics.md`
- Double-shear clevis regression/smoke test: `references/example-clevis-pin.json`

## Execute the gated workflow

1. `CAPABILITY_CHECK`: prove that the MCP can inspect, modify, mesh, solve, query results, and export the evidence required by the selected profile set.
2. `INTAKE`: normalize model source, units, materials, analysis profile, outputs, and acceptance criteria.
3. `MODEL_INSPECTION`: inventory bodies, dimensions, materials, named selections, connections, analyses, loads, supports, and existing results.
4. `MODEL_SETUP`: create only missing or authorized objects. Prefer existing named selections; otherwise use validated geometry predicates.
5. `MODEL_GATE`: verify entity counts, geometry properties, material coverage, connection scoping, units, load directions, and rigid-body restraint.
6. `MESH_PLAN`: classify bodies and critical regions before generating mesh.
7. `MESH_GATE`: generate, extract normalized metrics and worst-element regions, run `recommend_mesh_repairs.py`, apply at most the configured repair limit through the MCP, regenerate, and reject unresolved hard failures.
8. `PRE_SOLVE_GATE`: inspect initial contact state where applicable and verify load-step tables and solution controls.
9. `SOLVE`: solve and retain solver output, warnings, errors, substep history, and final converged time.
10. `SOLVER_GATE`: reject incomplete or unconverged final states even if the UI says Completed.
11. `RESULT_EXTRACTION`: extract scoped engineering quantities, reactions, energy, contact quantities, modal/buckling values, mesh statistics, and evidence images.
12. `VALIDATION_GATE`: run deterministic checks and compare with analytical, test, or user-defined criteria when available.
13. `CONVERGENCE_GATE`: compare at least the final two mesh levels for every configured metric. Do not use a singular peak stress as the only metric.
14. `REPORT`: state pass, warning, blocked, or unsupported; include assumptions, evidence paths, limitations, and unresolved warnings.

Each gate must produce a structured status and evidence. Do not continue past a hard failure merely to create a report.

## Geometry and scoping rules

- Prefer named selections over raw topology IDs.
- Validate every selection by entity type, body, count, location, size, orientation, and surface/curve type as applicable.
- Allow temporary entity IDs only after property validation; recreate semantic selections before later operations.
- Reject zero or ambiguous matches. Never silently choose the nearest entity.
- Prefer imported CAD for complex geometry. Limit procedural construction to geometries supported by the MCP and straightforward to validate.

## Mesh rules

- Choose beam, shell, or solid representation from structural behavior, not convenience.
- Prefer sweep or MultiZone only when topology and physics support them; a good quadratic tetrahedral mesh is preferable to distorted hexahedra.
- Resolve thickness, curvature, holes, fillets, contacts, load introduction, and expected gradients.
- Inspect metric distributions and worst-element locations, not only a single minimum.
- Keep opposing contact meshes reasonably similar and prove adequacy with engineering-result convergence.
- Do not automatically suppress geometry or enable aggressive defeaturing without preserving a record and user intent.

## Deterministic scripts

Run with a known-good Python interpreter:

```text
python scripts/validate_job_spec.py job.json
python scripts/evaluate_mesh_quality.py mesh-quality.json
python scripts/recommend_mesh_repairs.py mesh-loop.json
python scripts/validate_results.py analysis-results.json
python scripts/validate_contact_results.py contact-results.json
python scripts/evaluate_mesh_convergence.py convergence.json
python scripts/normalize_units.py quantities.json
python scripts/calculate_reference_values.py references.json
python scripts/build_analysis_report.py report-data.json output-report.md
```

The scripts emit JSON and return exit code `0` for pass, `1` for warning/fail, and `2` for invalid input. Read their output; do not replace it with qualitative judgment.

For a live mesh loop, prepend a JSON-compatible `REQUEST` object to `scripts/mechanical_mesh_bridge.py` and send the complete code through `workbench_queue_execute_python_tool`. Use `probe_session`, `mesh_snapshot`, `apply_mesh_updates`, or `generate_mesh`. Parse the `ANSYS_STRUCTURAL_JSON:` stdout marker. Supply exact existing object names and typed property updates; reject ambiguous names and unsupported metric properties.

## Non-negotiable rules

- Never silently change units, materials, load magnitudes, contacts, or supports.
- Never enable weak springs solely to hide rigid-body motion.
- Never claim a solve, result, image, mesh statistic, or convergence value that was not observed.
- Never use an unconverged substep as the final result.
- Never equate solver completion with model validity.
- Never judge mesh adequacy from appearance alone.
- Never compare nominal hand calculations directly with a contact-edge or singular nodal peak without explaining the mismatch.
- Preserve the project and evidence needed to reproduce the reported state.

## Output

Return the live project/system analyzed, execution status, assumptions, model and mesh summary, solver diagnostics, validation matrix, convergence table, result artifacts, and engineering limitations. Match the user's language.
