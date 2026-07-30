# LAMMPS Validation

## Run Integrity

- No lost atoms, neighbor-list overflow, nonnumeric pressure/energy, or fatal error.
- Completed step count matches the requested run.
- Temperature, energy, pressure, and box dimensions are physically interpretable.
- Random seeds and executable/package details are recorded.
- Potential provenance and redistribution permission are known.

## Materials Interpretation

- Check lattice and energy minimization before loading.
- Demonstrate equilibration using temperature, pressure, and energy histories.
- Report strain rate and specimen size; MD tensile rates are usually much higher
  than laboratory rates.
- Distinguish virial/atomic stress conventions from macroscopic engineering stress.
- Use multiple seeds and size/rate sensitivity before quantitative claims.

Do not commit a potential file unless its redistribution license is verified.
