# PM Motor NVH Model Contract

## Contents

- Baseline scope
- Parameter relations
- Geometry and selections
- Materials and physics
- Mesh
- Study sequence
- Outputs
- Reference-audit example

## Baseline scope

Use this contract as a reusable 2D surface-mounted permanent-magnet motor NVH baseline. Adapt dimensions and material data only from traceable user inputs, source files, or approved engineering assumptions.

The demonstrated topology is a 10-pole/12-slot machine with an external acoustic domain and PML. It couples:

```text
rotating magnetic machinery
-> Maxwell-force harmonics
-> structural frequency response
-> pressure acoustics
-> exterior sound-pressure level
```

## Parameter relations

Define all quantities as COMSOL parameters with units.

| Symbol | Meaning | Demonstrated value/relation |
|---|---|---|
| `Np` | pole count | `10` |
| `Ns` | slot count | `12` |
| `n_shaft` | shaft speed | parameter in `rpm` |
| `n_cog` | cogging-period count | `Ns/gcd(Np,Ns)*2` |
| `Nframes` | electromagnetic phase frames | `n_cog*6` |
| `Ipk` | phase-current peak | source-backed input |
| `init_ang` | initial electrical/mechanical alignment | source-backed input |
| `L` | axial stack length used by the 2D model | source-backed input |
| `freq_min` | lower Campbell control frequency | study input |

For a numeric speed in rpm:

```text
electrical_frequency_hz = n_shaft_rpm * Np / 120
excitation_frequency_hz = harmonic * electrical_frequency_hz
mechanical_order = harmonic * Np / 2
```

With `Np=10`, the electrical frequency is `rpm/12`, and harmonic `h=4` is mechanical order 20.

## Geometry and selections

Prefer COMSOL Application Library parametric rotor and stator geometry parts when they are available and licensed. Resolve them relative to `COMSOL_ROOT`; never commit an author-machine path.

Build the target from a blank model. A typical order is:

```text
parameters
rotor part instance
stator part instance
housing and supports
external acoustic domain and PML
boolean features
named selections
assembly finalization and identity pairs
```

Create stable named selections for at least:

- rotor magnets and alternating north/south subsets;
- stator iron and winding domains;
- phase A/B/C windings and reverse-current subsets;
- electromagnetic air/rotating domains;
- structural domains and fixed boundaries;
- acoustic and PML domains;
- acoustic-structure and exterior-field boundaries.

Require every selection used by a material, physics feature, mesh feature, coupling, or export to be nonempty after geometry finalization.

Topology counts from a reference model may diagnose a build, but they are not universal hard gates. Do not delete arbitrary domains merely to match counts.

## Materials and physics

Use source-backed material properties. A demonstrated configuration used:

- air for the acoustic/electromagnetic surroundings;
- structural steel for housing/support domains;
- soft iron with ordinary and effective B-H interpolation tables;
- N42 NdFeB with source-backed recoil permeability and remanence.

Create and audit these interfaces:

| Tag | Role |
|---|---|
| `mmtp` | Magnetic Machinery, Rotating, Time Periodic |
| `solid` | Solid Mechanics |
| `acpr` | Pressure Acoustics, Frequency Domain |
| `asb1` | Acoustic-Structure Boundary |

The electromagnetic definition must explicitly record magnet polarity, three-phase winding sequence, reverse-current domains, force-calculation selection, and whether speed-dependent induced currents are neglected. Reusing one electromagnetic solution across speeds is allowed only when those assumptions make force amplitude and phase speed-independent.

Do not introduce damping merely to suppress an undamped resonance. If damping is required by the real design, treat it as a separate, sourced model revision.

## Mesh

Use a user-controlled mesh. Include:

- resolved air-gap and magnet/tooth regions;
- mapped elements through PML where required by the acoustic formulation;
- boundary-layer or near-boundary refinement where source transfer requires it;
- exported element count, minimum quality, invalid-element count, and feature inventory.

Run a refined-mesh check only after the baseline passes. Recompute any physics affected by mesh changes.

## Study sequence

### Study 1: structural eigenmodes

- Solve `solid` only.
- Request enough modes to cover the excitation band; the demonstrated case requested seven.
- Require positive, ascending modes and no unintended near-zero rigid-body mode.
- Export the frequencies and representative mode shapes.

### Study 2: time-periodic electromagnetics

- Solve `mmtp` at the source-backed operating condition.
- Retain a complete phase cycle and force harmonics needed by Study 3.
- Require alternating magnet polarity, correct winding phase, finite fields, and finite force coefficients.

### Study 3 smoke: vibration and acoustics

Run a small matrix before the full sweep. A demonstrated smoke set used:

```text
speeds_rpm = 3000, 7000, 12000
harmonics = 2, 4, 6
```

Solve structural frequency response, pressure acoustics, and acoustic-structure coupling. Read the electromagnetic source from Study 2 without silently resolving or replacing it.

### Study 3 full: Campbell sweep

A demonstrated 17-speed grid was:

```text
900, 1200, 1500, 1800, 2100, 2400, 2700, 3000,
4000, 5000, 6000, 7000, 8000, 9000, 10000, 11000, 12000 rpm
```

For each speed, generate the requested harmonic frequencies from the parameter expression. Preserve missing low-frequency cells as missing data. When memory is limited, split speeds into batches, export scalars immediately, and retain full fields only for key cases.

## Outputs

Export at minimum:

```text
geometry overview and topology statistics
mesh overview and quality statistics
eigenfrequency CSV and mode-shape images
magnetic flux-density result
force-harmonic CSV
far-field directivity CSV for a key case
Campbell long-form CSV and matrix CSV
solver logs, evidence summary, and final report
```

Probe result expressions against the solved dataset before creating bulk exports. If an image export fails but the underlying numeric solution is valid, repair only the postprocessing path and document the limitation.

## Reference-audit example

The following values describe one completed 10-pole/12-slot baseline and are useful only to test a reproduction of that same definition:

```text
modes_hz = 929.448, 2324.427, 4507.714, 6888.555,
           9632.170, 10343.030, 12387.507
key_case = 7000 rpm, h=4, 2333.333 Hz, approximately 104.84 dB
```

Keep this comparison under `REFERENCE_AUDIT`. A different motor can pass the physical and numerical gates while producing different values.
