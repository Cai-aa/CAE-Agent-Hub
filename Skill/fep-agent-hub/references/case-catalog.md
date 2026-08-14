# Verified case catalog

Use this catalog to select a profile and its benchmark. Values below summarize the repository's checked public evidence; rerun the current scripts before making a release claim.

## Profile routing

| Profile | Proven use | Reference workflow | Required scientific boundary |
|---|---|---|---|
| `heat_steady_v1` | 3D steady conduction cube | `scripts/mcp_heat_smoke.py` | Conduction only; one steady field is not an animation |
| `heat_transient_v1` | 3D transient conduction cube | `scripts/mcp_transient_heat_smoke.py` | BDF time history; no convection, radiation, phase change, or thermal stress |
| `magnetodynamics_2d_harmonic_v1` | Linear 2D open-circuit transformer effect | `scripts/mcp_transformer_smoke.py` | Harmonic phasor model; no saturation, hysteresis, copper loss, load power, or 3D end effects |
| `elasticity_2d_static_v1` | Linear 2D plane-stress simply supported beam | `scripts/mcp_beam_smoke.py` | Independent static load levels; no structural dynamics, contact, plasticity, or buckling |
| `navier_stokes_2d_steady_v1` | 2D steady incompressible laminar channel | `scripts/mcp_channel_flow_smoke.py` | Newtonian low-Re flow; no turbulence, free surface, compressibility, or FSI |
| `magnetodynamics_2d_transient_eddy_v1` | Linear 2D transient conductor eddy current and Lenz response | `scripts/mcp_lenz_eddy_smoke.py --variants full` | Total `Az` solve with derived `Ez`/`Jeddy`; no 3D current closure, motion, nonlinear iron, or thermal feedback |

## Benchmark snapshots

### Steady heat cube

- Geometry: 10 mm cube.
- Boundary temperatures: 300 K and 400 K.
- Verified midpoint: about 350.270 K.
- Published mesh: 235 nodes, 734 volume elements, 396 boundary elements.
- Gate: finite temperature within imposed bounds and midpoint consistency.

### Transient heat cube

- Geometry/material: 10 mm cube, `k=15 W/(m K)`, `rho=8000 kg/m3`, `cp=500 J/(kg K)`.
- Initial/boundary state: 300 K initial; opposing faces at 400 K and 300 K; remaining faces insulated.
- Discretization: BDF1, 20 steps at 1 s.
- Verified midpoint: 308.448 K at 1 s and 349.643 K at 20 s.
- Fourier reference at 20 s: 349.961 K; absolute error 0.318 K, about 0.091%.
- Gates: 20/20 native steps, 300..400 K bounds, monotone midpoint history, Fourier comparison.

### Harmonic transformer

- Model: 2D three-limb linear core, 20 mm effective depth, 50 Hz.
- Core: relative permeability 1000, zero conductivity. Primary: 100 turns at 1 A RMS. Secondary: 50 turns, open circuit.
- Baseline: center-limb mean `B=1.144675 T`, flux `4.5786634e-4 Wb`, open-circuit secondary voltage `7.19215 V RMS`.
- Gates: real finite complex A/B arrays, core flux concentration, `V2/V1=0.5`, half-current linearity, and mesh sensitivity.
- Verified sensitivity: flux and voltage difference 0.0956%; `Bmax` difference 0.2918% between 1.50 mm and 1.25 mm meshes.
- Do not treat the turns-ratio check as an independent experiment; both voltages derive from the same FE flux.

### Simply supported beam

- Model: 1000 x 100 mm plane-stress steel beam, 10 mm effective thickness, `E=210 GPa`, `nu=0.3`, 1 MPa top pressure.
- Sequence: 10 independent static load levels from 0.1 to 1.0.
- Full-load FE/theory comparison: midpoint deflection 0.633804/0.744048 mm, error 14.82%; midpoint outer-fiber stress 61.5716/75.0000 MPa, error 17.90%; strain error 17.87%.
- Gate: all three analytical errors at or below the 20% smoke threshold; constrained residuals zero; 10/10 finite, nonzero levels.
- Do not compare the support-localized peak von Mises value with beam-theory midpoint stress.

### Laminar channel

- Model: 100 x 20 mm channel, `rho=1000 kg/m3`, `mu=0.01 Pa s`, target mean speed 0.05 m/s, `Re=100`.
- Verified: mean-speed error 1.55%; Poiseuille profile relative L2 error 1.76%; 10%-90% length pressure-drop error 1.04%; wall speed zero.
- Gates: converged steady solve, finite pressure/velocity, inlet/outlet flow consistency, no slip, profile and pressure-drop checks.

### Transient Lenz eddy current

- Model: 160 x 120 mm 2D air domain; 40 x 30 mm copper conductor; two 8 x 40 mm source-coil sections; 20 mm effective depth.
- Excitation: four-ramp triangular current-density history, peak magnitude `1.0e6 A/m2`, total time 20 ms.
- Baseline: 40 x 0.5 ms steps and 2.0 mm mesh. Sensitivity cases: 80 x 0.25 ms and 1.5 mm mesh.
- Derived from adjacent native `Az` steps: `Ez=-dAz/dt`, `Jeddy=sigma*Ez`, and nonnegative Joule density.
- Verified baseline peak conductor eddy-current RMS: `2.16340e5 A/m2`; integrated copper Joule energy: `1.35093e-4 J`.
- Time sensitivity: 1.101% peak-current difference and 2.757% energy difference, threshold 8%.
- Mesh sensitivity: 0.423% peak-current difference and 0.684% energy difference, threshold 10%.
- Gates: 40/80/40 native time steps, four ramp-increment Lenz signs, current reversal, finite nonzero loss, sensitivity thresholds, and 40 true ParaView time values.
- Interpret `Ez` as induced out-of-plane electric field, not electrostatic potential.

## Extension rule

Treat nearby geometries or parameter sweeps as candidate extensions only when they remain inside the selected profile's physics. For a new dimensionality, constitutive law, coupling, or solver class, add a new allowlisted profile and independent benchmark instead of relaxing an existing gate.
