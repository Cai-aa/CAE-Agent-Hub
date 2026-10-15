# Peridigm MCP · Agentic PD

An initial CAE-Agent-Hub agent workflow for Peridigm: progressive context completion, a confirmed and frozen CaseSpec, build-specific PD checks, bounded real solver jobs, independent result verification, and material-point visualization. The current AI client interprets the request; shared Python functions execute the same deterministic workflow through CLI or the 12-tool STDIO MCP adapter.

**Status: prototype with two qualified profiles.** It does not generate arbitrary CAD, infer calibrated damage parameters, perform autonomous engineering certification, or embed a model service. See [architecture](ARCHITECTURE.md), [Skill](../../Skill/peridigm/peridigm-evidence-fracture/SKILL.md), and [demo provenance](DEMO.md).

## View the demos first

From the repository's `viewer/` directory, run `npm ci` and `npm run dev`, then open the printed address with:

- `/peridigm.html?demo=elastic` — [2-point elastic code verification](../../models/peridigm-elastic), 6 actual frames, source-gold and independent oscillator checks.
- `/peridigm.html?demo=fracture` — [precracked tensile damage demonstration](../../models/peridigm-notched-tension), 3,200 points, 31 actual display frames, independent per-step bond reconstruction.

The packaged demos work without SSH, a solver or an API key. A static build includes both datasets. The viewer explicitly replays recorded results; it does not submit new jobs. Damage/displacement switching, playback, actual histories and verification limits are included.

![Recorded synthetic damage demonstration](../../assets/peridigm-fracture-preview.jpg)

## Qualified physics

| Profile | Execution | Verification | Boundary |
| --- | --- | --- | --- |
| `compression-two-point-v1` | MPI1/2; 2 points, 6 frames | Source gold differences 0; independent displacement error 0.2427% < 0.5% | Synthetic elastic code verification; no fracture or calibrated strength |
| `notched-tension-damage-v1` | MPI1; 40x20x0.5mm layer, 3,200 points, 601 native states | 6,661 newly failed pairs; point-Damage reconstruction difference 0; connected front indicator advances 12.5mm | Single-layer synthetic damage demonstration; no exact crack surface, experimental calibration or spatial convergence |

Fracture has an explicitly confirmed `time_step_variant: half` (25ns vs 50ns). It gives 6,700 failed pairs and the same final front indicator, with a maximum common-time indicator difference of 0.5mm. This is descriptive sensitivity, not a formal convergence certificate. The inspected solver build requires `Critical Stretch_tension` and `Critical Stretch_compression`; the upstream single-threshold input must not be substituted. Read [the fracture reference](../../Skill/peridigm/peridigm-evidence-fracture/references/fracture.md).

## Configure actual solves

Use Linux with an already installed compatible Peridigm/MPI build and Python 3.10+. Create an independent environment outside the repository, then install this module editable:

```sh
python3 -m venv /path/to/agentic-pd/runtime/venv
/path/to/agentic-pd/runtime/venv/bin/python -m pip install -e './MCP/Peridigm[dev]'
```

If system ensurepip is unavailable, bootstrap pip inside the project environment using official PyPA get-pip; do not install globally. Copy [config.example.json](config.example.json) outside the repository and fill the independent root, solver, matching MPI launcher and library paths. For elastic verification, copy the original source `test/verification/Compression_2x1x1/Compression_2x1x1_gold.e` to the external runtime reference path. Export `PERIDIGM_CONFIG=/path/to/project/config/local.json` only for this project invocation. The tools create external `runs/<id>/` records, never replace the installed solver or modify global library settings.

## CLI and MCP

From this module, with the independent environment active and `PERIDIGM_CONFIG` set:

```sh
python pd.py doctor
python pd.py templates
python pd.py start --json '{"request":"Demonstrate synthetic tensile damage","actor":"human"}'
python pd.py answer --json '{"run_id":"RETURNED_ID","answers":{"template_id":"notched-tension-damage-v1"},"actor":"human"}'
# Review every returned parameter, assumption, scope and hash before confirming.
python pd.py answer --json '{"run_id":"RETURNED_ID","answers":{"confirm_spec_sha256":"REVIEWED_HASH"},"actor":"human"}'
python pd.py validate --json '{"run_id":"RETURNED_ID"}'
python pd.py submit --json '{"run_id":"RETURNED_ID","timeout_seconds":120}'
python pd.py status --json '{"run_id":"RETURNED_ID"}'
python pd.py log --json '{"run_id":"RETURNED_ID"}'
python pd.py report --json '{"run_id":"RETURNED_ID"}'
```

Every case is single-use. Confirming a different physical problem requires a new case/profile; the tool rejects unknown overrides. Use the actual actor (`human`, AI operator or scripted test); never label an automatic confirmation as a human reply. `repair` retains input/mesh snapshots and diffs and restores only the unchanged frozen specification, at most three attempts. Solver timeout is bounded to 1–300 seconds; cancellation targets only the recorded project job.

Start the thin MCP adapter with `python server.py`. [Local client example](client.example.json) and [SSH example](client.ssh.example.json) use placeholders; configure one explicitly in your client. No global client settings are written by this module.

| Tools | Purpose |
| --- | --- |
| `peridigm_doctor / peridigm_templates` | Inspect dependencies and reviewed profiles / 检查依赖与模板 |
| `peridigm_start_context / peridigm_answer_context` | Ask for missing context, review parameters, confirm exact specification / 补全上下文、审阅并确认规格 |
| `peridigm_validate / peridigm_repair` | PD and identity gates; at most three canonical restorations / 规则检查，最多三次受限恢复 |
| `peridigm_submit / peridigm_status` | Detached bounded solve and persistent state / 后台求解与持久状态 |
| `peridigm_log / peridigm_cancel` | Inspect evidence; cancel only the recorded owned job / 日志及限定作业取消 |
| `peridigm_collect / peridigm_report` | Independent verification, material-point export and report / 独立验证、导出与报告 |

## Reproduction and checks

Unit/replay checks do not need a solver:

```sh
python -m pytest -q
python scripts/check_demos.py
```

When no project configuration is supplied, unit tests use isolated identity bytes, not a physical reference result. They verify workflow/guard behavior; the packaged demo provenance records separate real-solver evidence.

With a configured solver, `python scripts/protocol_smoke.py` checks real STDIO initialize/list/call. `python scripts/integration_mpi.py` performs the elastic MPI2 workflow; `python scripts/integration_fracture.py base` (or `half`) performs an actual small fracture solve through MCP. These scripts record their true test actor and create new run IDs. `scripts/export_demo.py` publishes only a reviewed verified replay fixture into a new local directory; see [DEMO.md](DEMO.md).

## Evidence, layout and limits

`core.py` owns CaseSpec state, canonical decks, guards and jobs; `fracture.py` owns the additional damage profile and independent bond history. `pd.py` and `server.py` share those functions. `postprocess.py` handles elastic source/analytic checks and MPI merge. `examples/`, `rules/`, `tests/` and `scripts/` are reusable source; the complete [Skill](../../Skill/peridigm/peridigm-evidence-fracture) sets workflow/acceptance rules. The [four-arm protocol](benchmarks/protocol.json) is a future research plan, not evidence of an agent-performance gain.

External runs retain original requests/answers and actor roles, specification/confirmation hashes, canonical input and mesh, job state, solver/output digests, logs, repair diffs, native Exodus outputs, CSV, validation, material-point JSON and HTML report. Missing or unverified data remain explicit. The viewer never invents FE connectivity, a crack surface or stress.

No full energy/work balance, calibrated fracture energy, arbitrary geometry/material, experimental accuracy, spatial convergence or fracture MPI is claimed. Full raw jobs, machine configuration, credentials, environments and solver binaries stay outside source control. Curated public demo fixtures are the documented exception. Preserve [third-party attribution and licenses](THIRD_PARTY_NOTICES.md).
