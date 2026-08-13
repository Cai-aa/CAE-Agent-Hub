# FEP Release Validation Checklist

## Runtime

- [ ] Local executable paths are configured outside public files.
- [ ] `scripts/install.ps1` completes.
- [ ] `scripts/doctor.py` finds FreeCADCmd, Gmsh, ElmerGrid, ElmerSolver, and pvpython.
- [ ] `scripts/protocol_smoke.py` reports 15/17/17 tools.
- [ ] Routine pytest suite passes.

## Native benchmark

- [ ] FreeCAD creates and validates the 10 mm cube.
- [ ] STEP and geometry manifest agree on bounds, centroid, and volume.
- [ ] Gmsh and ElmerGrid complete with exit code 0.
- [ ] Six semantic boundaries are mapped from coordinates.
- [ ] SIF validation passes before solver launch.
- [ ] ElmerSolver exits 0 with no fatal log marker.
- [ ] VTU temperature is finite.
- [ ] Tmin, Tmax, and Tmid pass their tolerances.
- [ ] ParaView exports visible PNG, CSV, and PVSM artifacts.

## Full MCP contract

- [ ] All 49 exposed tools are inventoried.
- [ ] Every exposed tool is invoked at least once.
- [ ] Supported capabilities return `SUCCEEDED`.
- [ ] Declared unsupported capabilities return the documented `BLOCKED` response.
- [ ] MCP-owned workers stop cleanly.
- [ ] Evidence JSON and Markdown reports are retained under the run workspace.
