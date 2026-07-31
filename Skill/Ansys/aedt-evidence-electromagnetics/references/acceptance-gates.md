# AEDT Acceptance Gates

## Common

- AEDT actually started and reported a version.
- The saved project opens and contains the named design.
- Design type and solution type match the engineering objective.
- Material, excitation, boundary, mesh/adaptive setup, and units are recorded.
- Solver logs contain no fatal, license, or adaptive failure signal.
- Native field/table exports are separated from auxiliary Python plots.

## Maxwell

- Report winding names, turns, current direction, terminal normals, and matrix setup.
- Require positive self-inductances and physically bounded coupling coefficient.
- Check `M12` and `M21` reciprocity; investigate polarity instead of hiding a negative mutual term.
- State whether stranded or solid conductors were used and what losses they can represent.

## HFSS

- Report port type, mode count, reference conductor, radiation/PML boundary, and sweep type.
- Require an adaptive-convergence history and a valid solved frequency range.
- Check S-parameter magnitude, passivity, and energy balance where applicable.

## Credibility

- `functional-validation`: AEDT/PyAEDT starts and a script executes.
- `engineering-draft`: real solve plus native project, logs, numeric data, and fields.
- `report-grade`: engineering-draft plus convergence/sensitivity checks and physical or experimental validation.
