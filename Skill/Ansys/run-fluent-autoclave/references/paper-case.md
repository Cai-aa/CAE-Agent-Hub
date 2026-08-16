# Validated Bohne-style case

Use these values only when reproducing the validated simplified open autoclave case.

## Solver

- 3-D, double precision, pressure based, incompressible transient RANS.
- Spalart-Allmaras turbulence model with energy enabled.
- First-order transient formulation; second-order spatial momentum, pressure, energy, and modified turbulent viscosity.
- Time step: 0.05 s. End time: 15 s. Run one test step, then 299 additional steps.

## Fluid at 55 C and 7 bar

- Density: 7.4326 kg/m3.
- Dynamic viscosity: 1.9948e-5 Pa s.
- Thermal conductivity: 0.0286 W/(m K).
- Specific heat: 1015.7 J/(kg K).

Do not confuse the inlet turbulent kinematic viscosity with molecular dynamic viscosity. The paper gives turbulent kinematic viscosity 2.7e-5 m2/s, equivalent to a turbulent viscosity ratio of about 10 with the fluid properties above.

## Boundaries

- Operating absolute pressure: 700000 Pa.
- Annular velocity inlet: 5.058 m/s, normal to boundary, 333.15 K.
- Pressure outlet: 0 Pa gauge, backflow temperature 333.15 K.
- Exposed calorimeter faces: fixed 323.15 K.
- Other walls: stationary, no slip, zero heat flux.

## Validated supplied-geometry result

- Mesh: 221638 tetrahedra, 41376 nodes.
- Inlet/outlet mass flow: 105.0516 / -105.0495 kg/s.
- Mass imbalance: 0.0020 percent.
- Outlet average/max speed: 3.078 / 4.237 m/s.
- Global maximum speed: 5.974 m/s at the upper inlet/head region.
- Pressure drop: 62.67 Pa.

The supplied geometry is about 5.2 m in diameter and 17.3 m long, much larger than the roughly 1 m by 2 m laboratory vessel in the paper. Compare flow topology, not the paper's approximately 7.23 m/s peak as an exact target.

Primary reference: Bohne et al., Journal of Composite Materials 52(12), 1677-1687, DOI 10.1177/0021998317729210.
