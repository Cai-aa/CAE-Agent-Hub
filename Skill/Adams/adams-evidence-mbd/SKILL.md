---
name: adams-evidence-mbd
description: Build and validate rigid-body mechanisms with the Adams MCP, including box bodies, revolute joints, gravity, rotational motion, bounded View batch runs and numeric reaction histories. Use for Adams or multibody dynamics tasks with a configured local Adams MCP.
---

# Adams evidence workflow

Probe `adams_environment_probe` and `adams_capabilities` before choosing an
operation. The bridge targets Adams/View 2024.1; a detected launcher or an
available tool does not prove native execution or license checkout.

## Model and execute

- Confirm the mechanism, coordinate system, units, masses, inertia about each
  center of mass, joint axes, constraints, drive law and requested observables.
- Prefer `adams_project_create` followed by rigid-body, revolute-joint, gravity
  and rotational-motion tools. Keep semantic IDs unique across model entities.
- Box inertia uses mass times squared model length. For mm/kg/sec, gravity is
  approximately 9806.65 mm/sec². Check force-unit conversion in Adams exports.
- Run a native smoke test before the first solve on a new installation. The
  smoke fixture is read from the user-owned installation, never downloaded or
  redistributed by this skill.
- Use `adams_simulation_run` with explicit duration, output steps and timeout.
  Existing trusted CMD inputs must be inside the configured workspace.
- Use live tools only when the user intends to modify the open View session.
  Localhost and prefix allowlists do not sandbox command side effects.

## Assess the result

Read `adams_evidence_latest` and `validation.json`. Require zero exit status,
no fatal log signals, model verification, actual numeric history and the full
requested time interval before reporting a simulation as verified.

A plain CMD run can pass process gates without numeric results. A no-joint
project can also complete without a numeric history. Describe those outcomes
as batch completion, not a validated dynamics result. The built-in extraction
targets the first joint FY; discover any other component in Adams before use.
Numeric summaries currently accept one scalar per line, not general table CSV.

Report model assumptions, units, actual duration/steps, mass/inertia, DOF,
reaction histories, warnings, evidence locations and remaining limitations.
Plot and animation tools and direct Solver execution are not implemented;
select a separate supported postprocessor when those outputs are required.
