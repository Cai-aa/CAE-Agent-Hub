# Curing Material Setup

## Description

Define UMAT material for composite curing and elastic material for mold. Invoke when user needs COM material with UMAT subroutine, TOOL material, or material constants for curing simulation.

## COM Material (Composite)

The composite material uses a user-defined material (UMAT) subroutine to model the curing behavior, including cure kinetics, glass transition, and orthotropic thermal expansion.

```
*Material, name=COM
*Depvar
      4,
*Expansion, type=ORTHO, user
*User Material, constants=1
1.,
```

### Keyword Details

- **\*Depvar**: Defines 4 state variables (SDV1-SDV4) that track the curing state throughout the analysis.
- **\*Expansion, type=ORTHO, user**: User-defined orthotropic thermal expansion. The expansion coefficients are computed inside the UMAT subroutine based on the current curing state and temperature.
- **\*User Material, constants=1**: A single material constant is passed to the UMAT subroutine (value=1.0). This constant is used as a flag or scaling factor within the subroutine logic.

### UMAT Subroutine

- The UMAT file (`Threestep.for`) must be provided at job submission.
- The subroutine implements the three-step curing model (viscous, rubbery, glassy states).
- The UMAT uses temperature and state variables to determine the current material state and compute the Jacobian, stress, and state variable updates.

### How to Attach UMAT

The UMAT subroutine is attached to the job via the `userSubroutine` argument when creating the job from an input file:

```python
mdb.JobFromInputFile(
    name='curing_job',
    inputFileName='curing.inp',
    userSubroutine=umat_path
)
```

Where `umat_path` is the absolute path to the `Threestep.for` file.

### State Variables Meaning

The 4 state variables (SDV1-SDV4) track the curing state:

- **SDV1**: Degree of cure (alpha) - ranges from 0 (uncured) to 1 (fully cured)
- **SDV2**: Glass transition temperature (Tg) - evolves with degree of cure
- **SDV3**: Current material state indicator (viscous/rubbery/glassy)
- **SDV4**: Additional curing parameter (e.g., residual cure strain or volumetric shrinkage)

These state variables are updated at each increment by the UMAT subroutine and can be monitored through field output requests.

## TOOL Material (Mold)

The mold material is modeled as a standard linear elastic material with isotropic thermal expansion.

```
*Material, name=TOOL
*Elastic
69000., 0.33
*Expansion
 2.52e-05,
```

### Keyword Details

- **\*Elastic**: Isotropic linear elasticity.
  - Young's modulus E = 69000 MPa (69 GPa, typical aluminum mold)
  - Poisson's ratio nu = 0.33
- **\*Expansion**: Isotropic thermal expansion coefficient = 2.52e-05 /°C

The mold material does not require a UMAT subroutine since it behaves as a standard elastic solid throughout the curing cycle. Its thermal expansion contributes to the contact interaction and stress transfer to the composite during heating and cooling.

## Notes

- The COM material requires the UMAT subroutine to function; without it, the analysis will fail.
- The TOOL material uses built-in Abaqus material models and does not require any subroutine.
- Material constants and expansion coefficients should be verified against the specific composite system and mold material being used.
- The UMAT subroutine name (`Threestep.for`) refers to the three-step curing model (viscous, rubbery, glassy).
