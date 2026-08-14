# 2D laminar Poiseuille channel flow

This curated example records lightweight evidence from the
`navier_stokes_2d_steady_v1` workflow. The model is a 100 mm × 20 mm planar
channel containing an incompressible Newtonian fluid with density 1000 kg/m³,
dynamic viscosity 0.01 Pa·s, and target mean velocity 0.05 m/s. The Reynolds
number is 100.

The inlet profile is the fixed parabolic Poiseuille function, the outlet has a
zero-pressure gauge, and the two walls are no-slip. The real Elmer result gave:

- measured mean velocity 0.049223 m/s, 1.55% error;
- maximum velocity 0.075 m/s, matching `1.5 Umean`;
- midsection velocity-profile relative L2 error 1.76%;
- 10%L–90%L pressure-drop error 1.04%;
- zero wall-velocity residual.

Included evidence:

- geometry, mesh, and semantic manifests;
- the structured Navier–Stokes `case.sif`;
- flow metrics and the ParaView midsection CSV;
- velocity-magnitude and velocity-vector images.

Native FCStd, STEP, mesh, VTU, PVSM, and full logs remain in the configured
local workspace.

```powershell
.\.venv\Scripts\python.exe .\scripts\mcp_channel_flow_smoke.py
```

