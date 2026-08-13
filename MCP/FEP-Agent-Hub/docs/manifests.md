# Project and manifest contract

Every project uses:

```text
project/
├─ geometry/   # FCStd, STEP, geometry_manifest.json
├─ mesh/       # model.geo, model.msh, Elmer mesh, semantic_map.json
├─ solver/     # case_model.json, case.sif, logs
├─ results/    # VTU, result_manifest.json
├─ post/       # PNG, CSV, PVSM
└─ evidence/   # commands, tool calls, hashes, report
```

`geometry_manifest.json` records semantic object IDs and geometry fingerprints. `semantic_map.json` records actual Elmer body IDs and coordinate-derived boundary IDs. `result_manifest.json` records the actual output filename, arrays, ranges, time steps, and physics acceptance.

The handoff is evidence-first: a STEP file alone is insufficient for semantic automation, and a zero exit code alone is insufficient for a solved case.

