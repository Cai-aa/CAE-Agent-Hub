# True transient heat-conduction cube

This curated example records lightweight evidence from the
`heat_transient_v1` workflow. A 10 mm stainless-steel cube starts at 300 K;
the x-min and x-max faces are held at 400 K and 300 K. Elmer advances 20 real
BDF1 steps with `dt=1 s` on an SI-scaled tetrahedral mesh.

The midpoint temperature increases monotonically from 308.448 K at 1 s to
349.643 K at 20 s. The corresponding 1D Fourier-series value is 349.961 K,
giving a 0.318 K absolute error. ParaView validated and exported all 20 time
steps. This is a physical transient solve, not a camera scan of a steady field.

Included evidence:

- geometry, mesh, and semantic manifests;
- the structured transient Elmer `case.sif`;
- all time-step scalar metrics and the final centerline CSV;
- representative 1 s and 20 s ParaView frames.

Native FCStd, STEP, mesh, 20 VTU files, PVSM, full animation frames, and logs
remain in the configured local workspace.

```powershell
.\.venv\Scripts\python.exe .\scripts\mcp_transient_heat_smoke.py
```

