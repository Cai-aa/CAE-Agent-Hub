# CSV Export

## Description

Export curing simulation results to CSV with node coordinates and displacements. Invoke when user needs CSV output, data export, or result comparison.

## Content

### CSV Format

The exported CSV file uses the following column format:

```
Node,X,Y,Z,U1,U2,U3
```

- `Node`: Node label (integer)
- `X, Y, Z`: Node coordinates
- `U1, U2, U3`: Displacement components from the sp step last frame

### Complete Export Script

```python
import os
from abaqusConstants import *

work_dir = 'C:\\Users\\...\\work_directory'
recipes = ['P8_mold_recipe_1', 'P8_mold_recipe_2', 'P8_mold_recipe_3']

for name in recipes:
    odb_path = os.path.join(work_dir, name + '.odb')
    odb = session.openOdb(name=name+'_odb', path=odb_path, readOnly=True)

    inst = odb.rootAssembly.instances['P8-1']
    last_frame = odb.steps['sp'].frames[-1]
    u_field = last_frame.fieldOutputs['U']

    u_map = {}
    for val in u_field.values:
        u_map[val.nodeLabel] = (val.data[0], val.data[1], val.data[2])

    csv_path = os.path.join(work_dir, name + '.csv')
    lines = ['Node,X,Y,Z,U1,U2,U3']
    for node in inst.nodes:
        nid = node.label
        x, y, z = node.coordinates
        if nid in u_map:
            u1, u2, u3 = u_map[nid]
            lines.append('%d,%.6f,%.6f,%.6f,%.6f,%.6f,%.6f' % (nid, x, y, z, u1, u2, u3))

    with open(csv_path, 'w') as f:
        f.write('\n'.join(lines))
    odb.close()
```

### Output Details

- **8-ply model:** 5445 nodes exported
- **4-ply model:** 3025 nodes exported
- Data is extracted from the sp step (springback) last frame, which represents the final deformation

### Usage Scenarios

#### Comparing Ply Layups
Use the CSV output to compare different ply layup configurations:
- Symmetry analysis of deformation patterns
- Identifying maximum displacement locations
- Comparing springback magnitudes across recipes

#### Extending with Additional Fields
The script can be extended to include additional field outputs by adding more columns:

```python
# Add stress (S) components
s_field = last_frame.fieldOutputs['S']
s_map = {}
for val in s_field.values:
    s_map[val.elementLabel] = val.data

# Add state variables (SDV1-4)
sdv1_field = last_frame.fieldOutputs['SDV1']
sdv1_map = {}
for val in sdv1_field.values:
    sdv1_map[val.elementLabel] = val.data
```

Available additional fields:
- `S` — Stress (6 components: S11, S22, S33, S12, S13, S23)
- `PE` — Plastic strain
- `SDV1` to `SDV4` — State variables

### Notes

- Use the `%` operator for string formatting (Abaqus uses Python 2.7)
- Always close the ODB after processing each recipe
- The CSV files are saved in the same work directory as the ODB files
- Node coordinates are retrieved from `instance.nodes`, not from a COORD field output
