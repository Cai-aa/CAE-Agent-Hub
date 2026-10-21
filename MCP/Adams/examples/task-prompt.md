# Adams multibody dynamics task

Use the configured Adams MCP and the adams-evidence-mbd skill to build and run
the mechanism described below. Resolve installation and workspace settings from
the user's local configuration.

Fill in: mechanism geometry, coordinate system, length/mass/force/time units,
part masses and principal inertia, joints/axes, gravity, motion law, duration,
output steps and required reaction or displacement histories.

1. Probe the environment and capability registry. Run the installed native smoke
   fixture before the first native solve on a new installation.
2. Create a fresh isolated project, audit its manifest and build the requested
   supported bodies/joints/loads/motions. Report unsupported features explicitly.
3. Execute a bounded View batch run; inspect logs and validation. Preserve the
   actual generated files in the run workspace.
4. Extract requested numeric results, inspect sample count/time range/units and
   explain whether the outcome is command completion or a verified simulation.
5. Report evidence paths, assumptions, warnings and remaining engineering checks.

Use trusted CMD inputs. Only modify an open live View session when the task
calls for it. Do not claim plot/animation/direct-Solver capabilities that are
not implemented in the bridge.
