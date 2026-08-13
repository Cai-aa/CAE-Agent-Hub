---
name: fep-agent-hub
description: Orchestrate and validate evidence-first CAE workflows through the independent FreeCAD, Elmer FEM, and ParaView MCP servers in FEP Agent Hub. Use for FEP repository setup or diagnostics; CAD-to-mesh-to-solver-to-postprocessing automation; steady or transient heat transfer; 2D harmonic transformer induction; 2D plane-stress beams; 2D steady laminar channel flow; 2D transient eddy-current and Lenz-law studies; regression, acceptance reports, or scientifically honest CAE videos built from these verified profiles.
---

# FEP Agent Hub

Run the three MCP servers as independent stages joined by manifests, semantic IDs, native solver artifacts, and explicit physics gates. Preserve auditability over convenience.

## Establish the run contract

1. Locate the FEP Agent Hub repository and read its `AGENTS.md`, root README, relevant prompt, and relevant report before changing a workflow.
2. Resolve native executables through `OPEN_CAE_CONFIG`, environment variables, or `configs/open-cae.local.toml`. Treat public paths as placeholders.
3. Choose a unique project name beneath the configured workspace. Keep FCStd, STEP, mesh, SIF, logs, VTU/PVD, images, tables, and evidence inside that project.
4. Probe all three MCP environments before modeling. Stop if a required native executable or server is unavailable.
5. Never expose arbitrary shell, Python, executable, macro, MATC, or raw SIF input. Use only fixed runners, structured parameters, and allowlisted analysis profiles.

## Select a verified profile

Read [references/case-catalog.md](references/case-catalog.md) when selecting a profile, copying benchmark parameters, or deciding whether the request exceeds verified capability.

Use a listed profile only for the physics and dimensionality it declares. Add a new profile, deterministic benchmark, tests, and gates before claiming a new class of analysis is supported.

## Orchestrate the native chain

Read [references/orchestration.md](references/orchestration.md) before executing or modifying a case.

Follow this order:

1. **Preflight** — inspect tool/resource inventories and probe FreeCAD, Elmer/Gmsh, and ParaView.
2. **FreeCAD** — create or open the document; create named features; apply only required booleans/transforms; inspect objects; validate geometry; save FCStd; export STEP plus geometry manifest.
3. **Elmer geometry and mesh** — create the case with an allowlisted profile; import STEP and manifest; generate Gmsh physical groups; convert with ElmerGrid; inspect SI bounds, entity counts, and semantic mappings.
4. **Elmer physics** — set materials, the structured equation profile, excitations, and boundary conditions; generate and validate SIF; run ElmerSolver; check job state, process exit, logs, expected time steps, actual arrays, finite values, and physics gates.
5. **ParaView** — start the MCP-owned headless session; open the actual VTU/PVD; inspect dataset type, arrays, associations, ranges, and time values before creating filters; render/export PNG, CSV, animation frames, and PVSM; inspect the final pipeline; stop only the MCP-owned session.
6. **Report** — record inputs, versions, mesh, solver status, field extrema, benchmark errors, sensitivity checks, artifacts, hashes, pass/fail decisions, limitations, and the exact meaning of any animation.

Do not skip directly from file creation to visualization. Each stage must pass before its artifact becomes input to the next stage.

## Enforce evidence and claims

Read [references/validation-and-claims.md](references/validation-and-claims.md) before accepting results, publishing percentages, comparing accuracy, or composing video.

Apply these non-negotiable rules:

- Treat `SUCCEEDED`, `BLOCKED`, and `FAILED` as distinct outcomes. A contextually unsupported operation should return `BLOCKED`, not a fabricated artifact.
- Never infer solver success from file presence. Require successful process exit, completion markers, absence of fatal diagnostics, expected artifacts, finite/nontrivial fields, and case-specific physics gates.
- Preserve semantic identity across `FreeCAD semantic_id -> Gmsh Physical ID -> Elmer body/boundary ID -> VTU array -> ParaView proxy/array`.
- State contract coverage, call success rate, and numerical error separately. A 100% workflow pass rate is not 100% engineering accuracy.
- Keep large native results local. Commit only code, prompts, compact metrics, curated evidence, and reports permitted by `.gitignore`.
- Describe transient, harmonic, quasi-static, and steady media honestly. Postproduction motion never upgrades the underlying physics.

## Use repository regression scripts

When a deterministic full-case replay is requested, prefer the repository scripts instead of reconstructing long tool sequences:

- `scripts/mcp_heat_smoke.py`
- `scripts/mcp_transient_heat_smoke.py`
- `scripts/mcp_transformer_smoke.py`
- `scripts/mcp_beam_smoke.py`
- `scripts/mcp_channel_flow_smoke.py`
- `scripts/mcp_lenz_eddy_smoke.py --variants full`
- `scripts/mcp_full_validation.py`
- `scripts/protocol_smoke.py`

Run the repository's current prescribed test matrix before release. Report the observed counts from that run rather than copying historical counts into a new claim.

## Block unsupported extensions

Return `BLOCKED` with the missing profile, model, reference data, or validation work when the request requires unverified nonlinear materials, contact, plasticity, structural dynamics, turbulence, free surfaces, compressibility, three-dimensional end effects, magnetic hysteresis/saturation, motion, bidirectional multiphysics, MPI, arbitrary scripts, or industrial-certification accuracy.
