# ODB Extraction

## Description

Extract field outputs from ODB files for curing simulation. Invoke when user needs to read ODB results, get displacement data, or inspect field outputs.

## Content

### Opening ODB

Open an ODB file in read-only mode:

```python
from abaqusConstants import *

odb = session.openOdb(name='odb1', path=odb_path, readOnly=True)
```

### ODB Structure

The curing simulation ODB has the following structure:

- **Instances:** `['P8-1', 'TOOL-1']`
  - `P8-1`: Composite part instance
  - `TOOL-1`: Tool part instance
- **Steps:** `['vis', 'rub', 'glassy', 'sp']`
  - The `sp` step has 7 frames
  - The last frame of the `sp` step contains the final springback result

### Available Field Outputs

The following field outputs are available in the sp step last frame:

#### Standard Field Outputs
- `U` — Displacement
- `S` — Stress
- `PE` — Plastic strain
- `SDV1` to `SDV4` — State variables
- `TEMP` — Temperature
- `RF` — Reaction force
- `NT` — Nodal temperature

#### Contact Field Outputs
- `CDISP` — Contact displacement
- `CSTRESS` — Contact stress
- `COPEN` — Contact opening
- `CPRESS` — Contact pressure
- `CSHEAR1`, `CSHEAR2` — Contact shear stresses
- `CSLIP1`, `CSLIP2` — Contact slip

**Note:** `COORD` is NOT available as a field output. To get node coordinates, access them directly from `instance.nodes`.

### Extracting Displacement

Extract displacement data from the last frame of the sp step:

```python
last_frame = odb.steps['sp'].frames[-1]
u_field = last_frame.fieldOutputs['U']

u_map = {}
for val in u_field.values:
    u_map[val.nodeLabel] = (val.data[0], val.data[1], val.data[2])
```

### Getting Node Coordinates

Retrieve node coordinates directly from the instance:

```python
inst = odb.rootAssembly.instances['P8-1']

for node in inst.nodes:
    x, y, z = node.coordinates
    # Process coordinates
```

### Closing ODB

Always close the ODB after extraction to free resources:

```python
odb.close()
```

**Important:** After calling `odb.close()`, do NOT access any instance objects (nodes, elements, field outputs) that were obtained before closing. Doing so will raise an `AccessError`. Extract all needed data into Python data structures (lists, dicts) before closing the ODB.

### Best Practices

1. Open ODB in `readOnly=True` mode to prevent accidental modifications
2. Extract all needed data into local variables before closing
3. Use the last frame of the sp step for final springback results
4. Node labels from field output values match instance node labels
5. Close the ODB promptly after extraction to release file locks
