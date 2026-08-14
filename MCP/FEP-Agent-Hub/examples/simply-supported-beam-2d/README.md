# 2D simply-supported beam stress-strain smoke

This curated example records the lightweight, reviewable outputs of the
`elasticity_2d_static_v1` workflow. Native FCStd, STEP, Elmer meshes, VTU
results, PVSM state, animation frames, videos, and full logs remain in the
configured local workspace and are not committed.

Model scope: a 1000 mm × 100 mm structural-steel beam represented by a 2D
plane-stress continuum with a 10 mm equivalent thickness. The left and right
supports are one-mesh-width boundary segments, and the top edge carries a
uniform pressure. Ten independent static solves form a 10%..100% quasi-static
load sequence; this is not a transient structural-dynamics analysis.

Included evidence:

- `geometry_manifest.json`: FreeCAD planar face and dimensions.
- `mesh_manifest.json` and `semantic_map.json`: SI-coordinate mesh statistics
  and evidence-backed Elmer body/boundary IDs.
- `case.sif`: the full-load structured Elmer input.
- `beam_metrics.json`: sanitized load-step results and analytical comparison.
- `beam_centerline.csv`: 201 ParaView samples along the beam centerline.
- `beam_von_mises_full_load.png`: 1920×1080 full-load, warped ParaView view.

The full-load finite-element result is compared with Euler–Bernoulli reference
values. Midspan deflection, outer-fiber stress, and outer-fiber strain differ
by 14.82%, 17.90%, and 17.87%, respectively, all inside the 20% smoke-test
tolerance. The larger 135.83 MPa maximum von Mises value is a local support
peak and is not substituted for the midspan bending-stress comparison.

Reproduce locally after configuring `configs/open-cae.local.toml` and
registering the three MCP servers:

```powershell
.\.venv\Scripts\python.exe .\scripts\mcp_beam_smoke.py
```

