---
name: peridigm-evidence-fracture
description: Clarify Peridigm simulation requirements, preserve confirmed physical intent, call evidence-producing CLI or MCP tools, and interpret actual solver results. Executable profiles cover two-point elastic verification and a synthetic precracked tensile damage demonstration; other physics require new qualification.
---

# Peridigm evidence workflow

The AI client supplies language understanding. The deterministic core supplies context state, compilation, execution and checks; neither silently invokes another model nor treats a successful process as physical validation.

## Clarify and confirm

1. Call `peridigm_doctor` and `peridigm_templates` before promising a supported simulation.
2. Call `peridigm_start_context(request, actor)` with the actual request. Retain its `run_id`.
3. Ask the returned questions, grouping at most three important questions per turn. Distinguish missing facts from facts inferable from an explicitly accepted template. Do not invent steel, concrete, damage or contact parameters.
4. Pass the actual answer to `peridigm_answer_context`. Selecting `compression-two-point-v1` or `notched-tension-damage-v1` returns its complete synthetic parameters and confirmation hash. Record whether confirmation comes from the human or an AI operator acting within explicit delegation; never label a scripted test or operator answer as a human response.
5. Submit the returned `confirm_spec_sha256` only after review. If the user changes the problem, start a new specification. Preserve the old one.

For CLI use `pd-agent start --json '{"request":"..."}'`, then `answer`, `validate`, `submit`, `status`, `log`, `repair`, `collect`, and `report`. CLI and MCP share `core.py`. The project-local launcher sets the machine config; do not embed server paths or credentials in reusable instructions.

## Execute and diagnose

`peridigm_validate` checks the frozen specification and exact compiled input. `peridigm_submit` launches a bounded detached worker. Query the same run after client disconnection; never restart just because observation timed out. Cancel only the recorded job with `peridigm_cancel`.

Use logs to distinguish dependency, syntax, field/node-set, numerical and physical-semantic errors. `peridigm_repair` only regenerates an invalid deck from an unchanged frozen spec, retaining the previous file and diff. It stops after three attempts. It does not tune constitutive laws, damage, boundaries, velocity or physical end time to force success.

Read [validation.md](references/validation.md) before interpreting displacement, energy or fracture. Read [capabilities.md](references/capabilities.md) before offering a different case or MPI mode.

## Finish

Call `peridigm_collect` and `peridigm_report`. Separately report process completion, output integrity, intent alignment and reference/analytic checks. Point exports use `representation: material-points`, zero invented finite elements and actual saved time frames. Show scale and units.

Preserve the raw result, logs, confirmed spec, event history and verification outputs. Do not infer unavailable fields or call zero energy an energy-conservation pass. The elastic profile has no damage. The fracture profile is synthetic, without contact or experimentally calibrated strength. Read [fracture.md](references/fracture.md) before selecting it or interpreting Damage and the crack-front indicator.
