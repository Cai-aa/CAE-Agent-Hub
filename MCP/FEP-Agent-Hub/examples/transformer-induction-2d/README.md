# 2D harmonic transformer-induction smoke

This curated example records the lightweight, reviewable outputs of the
`magnetodynamics_2d_harmonic_v1` workflow. The native FCStd, STEP, mesh,
Elmer result, PVSM, and logs remain in the configured local workspace and are
not committed.

Model scope: linear, lossless, open-circuit, 2D planar harmonic magnetic field
with a 20 mm equivalent stack depth. It is a workflow and physics smoke test,
not an industrial transformer design.

Included evidence:

- `geometry_manifest.json`: FreeCAD planar regions and semantic IDs.
- `mesh_manifest.json` and `semantic_map.json`: SI-coordinate mesh summary and
  semantic-to-Elmer-ID mapping.
- `case.sif`: baseline harmonic Elmer input.
- `induction_metrics.json`: baseline, half-current, and refined-mesh metrics.
- `center_limb_flux.csv`: 201 ParaView `PlotOverLine` samples across the center limb.
- Three 1920×1080 ParaView images for B magnitude, A contours, and B vectors.

Reproduce locally after configuring `configs/open-cae.local.toml`:

```powershell
.\.venv\Scripts\python.exe .\scripts\mcp_transformer_smoke.py
```
