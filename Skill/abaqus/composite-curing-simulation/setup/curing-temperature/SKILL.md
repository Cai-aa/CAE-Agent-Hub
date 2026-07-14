# Curing Temperature Setup

## Description

Define temperature fields for composite curing simulation. Invoke when user needs temperature initialization, temperature changes, or thermal fields for curing steps.

## Initial Conditions

The initial temperature is set for all nodes in both instances (tool-1 and P8-1) at the start of the analysis:

```
*Initial Conditions, type=TEMPERATURE
_PickedSet333, 25.
```

- **_PickedSet333**: Node set covering ALL nodes in both instances (tool-1 and P8-1).
- **Initial temperature**: 25°C (room temperature).

### _PickedSet333 Definition

The node set _PickedSet333 is defined using generated node ranges for both instances:

```
*Nset, nset=_PickedSet333, internal, instance=tool-1, generate
    1,  2691,     1
*Nset, nset=_PickedSet333, internal, instance=P8-1, generate
    1,  5445,     1    # (or 3025 for 4-ply model)
```

- **tool-1**: Nodes 1 to 2691 (all tool nodes).
- **P8-1**: Nodes 1 to 5445 (all composite nodes for 8-ply model) or 1 to 3025 (for 4-ply model).
- The `generate` option creates a sequential node set from the start to end label with the given increment.

## Temperature in Each Step

The temperature is updated in each step of the curing cycle using the `*Temperature` predefined field. The temperature drives the UMAT material response (curing kinetics and glass transition).

### vis Step (Viscous State)

```
*Temperature
_PickedSet333, 150.
```

- Temperature changes from 25°C to 150°C.
- At 150°C, the resin is in a low-viscosity state, allowing flow and compaction.
- The UMAT subroutine recognizes this as the viscous state.

### rub Step (Rubbery State)

```
*Temperature
_PickedSet333, 180.
```

- Temperature changes from 150°C to 180°C.
- At 180°C, the cure reaction progresses and the material transitions to a rubbery state.
- The UMAT subroutine recognizes this as the rubbery state.

### glassy Step (Glassy State)

```
*Temperature
_PickedSet333, 25.
```

- Temperature changes from 180°C to 25°C (cooling to room temperature).
- As the material cools below its glass transition temperature (Tg), it transitions to a glassy state.
- The UMAT subroutine recognizes this as the glassy state.

### sp Step (Springback)

```
*Temperature
_PickedSet333, 25.
```

- Temperature maintained at 25°C.
- The tool is removed (via Model Change) and the composite undergoes springback at room temperature.

## Temperature Schedule Summary

| Step | Start Temp (°C) | End Temp (°C) | Material State |
|------|----------------|---------------|----------------|
| (initial) | 25 | 25 | - |
| vis  | 25  | 150 | Viscous |
| rub  | 150 | 180 | Rubbery |
| glassy | 180 | 25 | Glassy |
| sp   | 25  | 25  | Glassy (springback) |

## Temperature as a Predefined Field

Temperature is a predefined field in Abaqus, applied to all nodes in the model:

- The `*Temperature` keyword assigns a uniform temperature to all nodes in the specified set.
- The temperature is ramped linearly from the previous step's value to the new value over the step time.
- The UMAT subroutine receives the current temperature at each integration point and uses it to:
  - Determine the material state (viscous, rubbery, or glassy).
  - Compute the degree of cure (cure kinetics).
  - Update the glass transition temperature (Tg).
  - Calculate thermal strains and cure shrinkage strains.

## UMAT and Temperature Interaction

The UMAT subroutine uses temperature as the primary driver for material state transitions:

1. **Viscous state** (high temperature, ~150°C): Low resin viscosity, resin flow and compaction occur. The material is soft and deformable.
2. **Rubbery state** (intermediate temperature, ~180°C): Cure reaction advances, cross-linking increases. The material becomes rubbery and begins to develop stiffness.
3. **Glassy state** (low temperature, ~25°C): Below Tg, the material is rigid and glassy. Residual stresses are locked in during this phase.

The state variables (SDV1-SDV4) are updated based on the temperature history, tracking:
- Degree of cure progression
- Glass transition temperature evolution
- Current material state
- Accumulated cure strain

## Notes

- The temperature values (25, 150, 180, 25°C) represent a typical three-step curing cycle. Adjust based on the specific resin system and cure schedule.
- The temperature is applied uniformly to all nodes. For spatially varying temperature fields, use a field variable or mapped temperature data.
- The _PickedSet333 node set must include all nodes in both instances to ensure uniform temperature application.
- When changing the mesh (e.g., from 8-ply to 4-ply), update the node range for P8-1 in _PickedSet333 accordingly (5445 for 8-ply, 3025 for 4-ply).
- The temperature ramp rate is controlled by the step time. Ensure the step time is sufficient for the cure reaction to complete (especially in the rub step).
