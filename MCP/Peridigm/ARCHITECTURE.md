# Peridigm integration architecture

Reference: CAE-Agent-Hub commit `194ef498e6efb1984cd65325e21e71087588a581`, inspected before implementation. Reviewed root bilingual README, MCP/LAMMPS server/README, MCP/CalculiX solver/exporter, Skill/lammps, Skill/calculix, MCP/FEP-Agent-Hub instructions/readme, Subagent/README and viewer contracts. The input implementation is tailored to the installed Peridigm 1.5.1 Dev build, not copied from a GUI bridge.

| Hub layer | Existing reference | Peridigm addition |
| --- | --- | --- |
| Tool access | LAMMPS explicit solver invocation | `core.py`, CLI and thin STDIO MCP adapter |
| Workflow | Evidence-oriented Skills | Parameter provenance, progressive questions, frozen intent and repair limits |
| Native solve | Installed solver executable | Project-scoped environment, detached worker, owned job cancellation |
| Validation | FEP evidence gates and CalculiX result extraction | Source gold and independent elastic oscillator checks |
| Result export | Hub node/frame result schema | Real material-point values; empty FE connectivity; synchronized rank merge |
| Viewer | Existing CaeResultViewer | Optional injected data plus point-only rendering; original FE branch retained |

The shared core never calls a model API. The current AI client performs language reasoning and forwards actual answers. Each question/answer/specification/repair is recorded. Machine configuration, binary, reference data, environments and runs remain outside the repository. Source exposes neither arbitrary shell nor arbitrary Python execution tools.

The separate `peridigm.html` viewer entry uses the existing component and preserves the default app. It accepts an explicitly opened JSON export or a same-origin `/run/` result path. Generated artifacts are served from the external run directory through a loopback-only read-only server. There is no new public endpoint or global client registration.

The minimal prototype qualifies a small elastic verification profile, not general natural-language engineering design. Fracture cases, broad geometry generation, large retrieval systems, independent multi-agent orchestration, training and cloud services require future work.

## v0.2 damage profile

`core.py` selects a reviewed profile and retains the same state/worker/repair lifecycle. `fracture.py` adds canonical Text File mesh generation, build-specific damage deck, neighbor and bond-history reconstruction, Damage export and report. The elastic postprocessor remains unchanged. The Hub viewer uses the same material-point renderer, per-profile point size, honest Damage legend and switchable field values; no FE connectivity is fabricated.
