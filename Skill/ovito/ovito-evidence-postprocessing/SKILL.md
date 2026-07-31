---
name: ovito-evidence-postprocessing
description: Evidence-first OVITO atomistic postprocessing for LAMMPS trajectories and other particle data, including pipeline construction, modifiers, coloring, clipping, camera setup, images, animations, tables, and state files. Use when Codex must inspect or present molecular-dynamics results while distinguishing OVITO Basic GUI availability from ovitos/external Python automation and separating rendering evidence from upstream solver evidence.
---

# OVITO Evidence Postprocessing

OVITO explains and renders atomistic data; it does not prove that the upstream
simulation was physically correct.

## Start

```powershell
ai-cae-toolbox context-scope --solver ovito
ai-cae-toolbox bridge-plan --solver ovito --objective "<objective>"
ai-cae-toolbox create-run --solver ovito --case <case-name> --objective "<objective>"
ai-cae-toolbox write-smoke-template --solver ovito --run-dir <run-dir>
```

Use `ovito_check_installation` before scripting. OVITO Basic may include
`ovito.exe` but not `ovitos`; configure a compatible external Python with the
OVITO package when batch scripting is required.

## Build the Pipeline

Record input trajectory, frame range, particle properties, modifiers and their
parameters, selection/deletion rules, color mapping, clipping plane, camera,
render size, background, and export interval.

For strain or defect visualizations, record the reference configuration,
neighbor cutoff, crystal structure, and modifier assumptions. Read
[references/render-evidence.md](references/render-evidence.md).

## Finish

Export the pipeline script, PNG/MP4, numeric table when available, and a short
caption defining every color and scalar range. State whether the output came
from OVITO, a compatible Python implementation, or another plotting library.
Never label a substitute plot as native OVITO output.
