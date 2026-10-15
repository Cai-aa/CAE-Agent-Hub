# Verification and interpretation

The first executable profile is derived from Peridigm 1.5.1 `test/verification/Compression_2x1x1`. It has two material points, not a converged 3D specimen. Parameters are interpreted consistently in SI for this synthetic verification. No real steel or concrete calibration is claimed.

Each cell is 2 × 1 × 1 m, so its volume is 2 m³ and mass is density × 2 m³. Initial reference separation is r0 = 2 m. Initial velocities are +1 and −1 m/s along x; boundaries are free. K = 130 GPa, shear modulus = 78 GPa, density = 7800 kg/m³. The LPS shear correction is disabled as in the source verification input. Horizon = 2 m includes the neighboring point; this is not a general horizon/spacing prescription for 3D PD.

For this two-point stencil, the weighted volume is omegaWeight × r0² × neighborVolume and dilatation is 3e/r0. The deviatoric extension is zero, so the scalar force state reduces to the volumetric term. The opposite displacements u1 = −u2 obey:

    u1'' + omega² u1 = 0
    omega² = 36 K / (density r0²)
    u1(t) = sin(omega t) / omega
    v1(t) = cos(omega t)

This is an independent continuous-time check against the actual discrete Verlet trajectory. With dt = 1e−5 s and omega ≈ 12247.45 rad/s, omega×dt ≈ 0.12247 < 2. The maximum displacement relative-error tolerance is fixed at 0.5%; the absolute velocity-error tolerance is 0.001 m/s. These measure time-discretization error, not material calibration error. Compare the same original parameters to the source `_gold.e` at all six saved times using source `.comp` tolerances for displacement (1e−9 m), velocity (1e−9 m/s), force (1e−3 N) and dilatation (1e−12). Do not adjust tolerances after a failed comparison.

Check finite arrays, point count, time ordering, requested final time, displacement antisymmetry and total linear momentum of the isolated pair. Read the actual metadata for every shard; MPI merge requires complete rank files, synchronized times and unique owned IDs.

The supplied build/reference reports zero `Stored_Elastic_Energy` despite a nonzero response. Report full energy balance as unverified. Do not use that field to certify conservation. Fracture, contact, spatial convergence, 3D correspondence and engineering/experimental accuracy are unverified in this profile.
