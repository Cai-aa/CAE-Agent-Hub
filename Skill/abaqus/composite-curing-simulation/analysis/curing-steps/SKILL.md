# Curing Steps Analysis

## Description

Configure 4-step curing analysis (vis, rub, glassy, sp) in Abaqus. Invoke when user needs curing step sequence, static step settings, or step-by-step curing process setup.

## Content

The composite curing simulation uses 4 steps in sequence, all defined as `*Static` steps with `nlgeom=NO`.

### Step Sequence

#### Step 1: vis (viscous state)
- **Increment control:** 0.1, 1., 1e-05, 0.5
- **Temperature:** 150°C
- **Pressure:** 0.6 MPa
- **Friction:** 0.45
- **Tool BC:** U1=0, U2=0

#### Step 2: rub (rubbery state)
- **Increment control:** 0.1, 1., 1e-05, 0.3
- **Temperature:** 180°C
- **Pressure:** 0.6 MPa
- **Friction:** 0.2 (taumax=0.55)
- **Tool BC:** continues from vis step

#### Step 3: glassy (glassy state)
- **Increment control:** 0.1, 1., 1e-05, 0.5
- **Temperature:** 25°C
- **Pressure:** No pressure
- **Friction:** 0.169
- **Tool BC:** continues from rub step

#### Step 4: sp (springback)
- **Increment control:** 0.1, 1., 1e-05, 0.5
- **Temperature:** 25°C
- **Pressure:** No pressure
- **BC:** Set-2 U1=U2=U3=0
- **Model Change:** removes contact + tool

### Static Step Format

The `*Static` step uses the following format with initial increment, total time, min increment, and max increment:

```
*Static
initial_increment, total_time, min_increment, max_increment
```

Example for vis step:
```
*Static
0.1, 1., 1e-05, 0.5
```

### Output Requests Per Step

Each step includes the following output requests:

```
*Output, field
*Node Output
CF, NT, RF, U
*Element Output, directions=YES
LE, PE, PEEQ, PEMAG, S, SDV, TEMP
*Contact Output
CDISP, CSTRESS
*Output, history, variable=PRESELECT
```

### Restart Configuration

No restart output is written:
```
*Restart, write, frequency=0
```

### Step Transitions

Loads and boundary conditions carry forward from one step to the next unless explicitly replaced with `op=NEW`. This means:
- Tool BCs applied in the vis step remain active through the glassy step
- Pressure applied in vis/rub steps is carried forward unless removed
- To replace all previous loads/BCs, use `op=NEW` on the load or BC keyword
