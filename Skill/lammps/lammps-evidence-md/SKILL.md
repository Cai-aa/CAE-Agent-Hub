---
name: lammps-evidence-md
description: Evidence-first LAMMPS molecular-dynamics workflow for input decks, potentials, minimization, equilibration, deformation, thermo logs, trajectories, restart/data files, stress-strain extraction, and reproducibility checks. Use when Codex must prepare, run, diagnose, or report a LAMMPS materials simulation or hand its trajectory to OVITO without overstating nanoscale demo results as calibrated macroscopic properties.
---

# LAMMPS Evidence MD

Keep the input deck, potential provenance, random seeds, executable build, log,
trajectory, and postprocessing chain traceable.

## Start

```powershell
ai-cae-toolbox context-scope --solver lammps
ai-cae-toolbox bridge-plan --solver lammps --objective "<objective>"
ai-cae-toolbox create-run --solver lammps --case <case-name> --objective "<objective>"
ai-cae-toolbox write-smoke-template --solver lammps --run-dir <run-dir>
```

Use `lammps_check_installation` and `lammps_run_input_file` when MCP is available.

## Build and Run

- Declare units, boundary conditions, atom style, dimensions, masses, and atom types.
- Record potential filename, source, license, supported species, and parameterization scope.
- Separate minimization, equilibration, loading, and production phases.
- Record timestep, thermostat/barostat damping, deformation rate, dump interval,
  thermo fields, random seeds, and restart strategy.
- Run a tiny parser/smoke case before a long trajectory.

Read [references/validation.md](references/validation.md) before interpreting
stress, fracture, diffusion, or phase behavior.

## Finish

Require a normal LAMMPS termination signal, complete log, expected step count,
thermo data, and trajectory or final data output. Export derived curves through
a versioned script. Hand trajectories to the OVITO skill for visualization, but
keep LAMMPS solve evidence and OVITO render evidence separate.
