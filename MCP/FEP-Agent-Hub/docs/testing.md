# Testing

Unit tests cover workspace escape protection, response schema, Elmer mesh boundary classification, SIF generation/validation, and MCP tool registration.

The native smoke test executes the full software chain:

1. FreeCAD creates and validates a 10×10×10 mm cube.
2. Gmsh generates a 3D tetrahedral MSH2 mesh.
3. ElmerGrid converts it and coordinate fingerprints identify x-min/x-max.
4. Elmer solves steady conduction with 300 K and 400 K Dirichlet faces.
5. The result gate checks VTU readability, temperature, finite values, Tmin/Tmax, and mid-plane temperature.
6. ParaView exports a surface image, center slice, and CSV.

Run:

```powershell
.\scripts\run-smoke.ps1
```

Passing tolerances are `|Tmin-300| < 1 K`, `|Tmax-400| < 1 K`, and `|Tmid-350| < 3 K`.

The electromagnetic MCP smoke is run with:

```powershell
.\.venv\Scripts\python.exe .\scripts\mcp_transformer_smoke.py
```

It executes baseline 1 A, half-current 0.5 A, and refined-mesh 1 A cases through
the registered MCP servers. Gates cover SI bounds, physical IDs, SIF structure,
clean solver completion, real VTU A/B arrays, finite and non-zero fields,
core-to-far-air field concentration, flux and open-circuit voltage, turns-ratio
consistency, current linearity, mesh sensitivity, and inspected ParaView exports.

The plane-stress simply-supported-beam MCP smoke is run with:

```powershell
.\.venv\Scripts\python.exe .\scripts\mcp_beam_smoke.py
```

It executes ten independent 10%..100% static load levels through the registered
MCP servers. Gates cover semantic support/load boundaries, SIF structure,
solver/log/VTU completion, finite displacement and derived plane-stress fields,
support residuals, Euler–Bernoulli deflection/stress/strain comparisons, and ten
verified ParaView frames. The sequence is quasi-static, not transient dynamics.

The true transient heat smoke is run with:

```powershell
.\.venv\Scripts\python.exe .\scripts\mcp_transient_heat_smoke.py
```

It requires 20 finite BDF1 VTU steps, bounded and monotonic midpoint heating,
agreement with the fixed 1D Fourier-series reference, and 20 verified ParaView
frames.

The steady 2D laminar channel smoke is run with:

```powershell
.\.venv\Scripts\python.exe .\scripts\mcp_channel_flow_smoke.py
```

It checks a Re=100 Newtonian channel against the Poiseuille mean/max velocity,
cross-section profile, no-slip walls, and pressure drop. ParaView outputs the
velocity field, glyphs, and a sampled midsection CSV.
