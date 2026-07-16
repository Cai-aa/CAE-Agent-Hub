# Curing Parameters Reference

## Description

Reference parameter tables for composite curing simulation. Invoke when user needs curing temperatures, friction coefficients, pressure values, or material constants.

## Content

### Complete Parameter Table

| Parameter | vis Step | rub Step | glassy Step | sp Step |
|-----------|----------|----------|-------------|---------|
| Temperature | 150°C | 180°C | 25°C | 25°C |
| Pressure | 0.6 MPa | 0.6 MPa | — | — (removed) |
| Friction μ | 0.45 | 0.2 | 0.169 | — (contact removed) |
| taumax | 0.118 | 0.55 | 0.118 | — |
| Tool BC | U1=0, U2=0 | U1=0, U2=0 | U1=0, U2=0 | Removed |
| Composite BC | — | — | — | Set-2: U1=U2=U3=0 |
| Contact | Active | Active | Active | Removed |
| Step time | 1.0 | 1.0 | 1.0 | 1.0 |
| Initial increment | 0.1 | 0.1 | 0.1 | 0.1 |
| Min increment | 1e-05 | 1e-05 | 1e-05 | 1e-05 |
| Max increment | 0.5 | 0.3 | 0.5 | 0.5 |

### Material Constants

#### COM (Composite Material)
- **Type:** UMAT (User Material)
- **Depvar:** 4 (state variables)
- **User Material constants:** 1 (value=1.0)
- **Expansion:** ORTHO user (orthotropic, user-defined)

#### TOOL (Tool Material)
- **Type:** Elastic
- **E (Young's modulus):** 69000 MPa
- **nu (Poisson's ratio):** 0.33
- **Expansion:** 2.52e-05

### Mesh Parameters

| Parameter | 4-ply Model | 8-ply Model |
|-----------|-------------|-------------|
| Elements | 2160 | 4320 |
| Nodes | 3025 | 5445 |
| Elements through thickness | 4 | 8 |
| Element thickness | 0.25 mm each | 0.125 mm each |
| Element type | C3D8 | C3D8 |
| Through-thickness direction | X (-1 to 0) | X (-1 to 0) |

### Surface Definitions

| Surface | Name | Description |
|---------|------|-------------|
| S1 | com-surface | Outer surface of composite, contact with tool |
| S2 | _PickedSurf337 | Inner surface of composite, pressure application |
| S4+S6 | tool-surface | Tool contact faces |

### Set Definitions

| Set | Contents | Purpose |
|-----|----------|---------|
| Set-2 | 55 P8-1 nodes + 1 tool-1 node | Springback constraint (U1=U2=U3=0 in sp step) |
| _PickedSet327 | Tool nodes | Tool U2=0 boundary condition |
| _PickedSet328 | Tool nodes | Tool U1=0 boundary condition |
| _PickedSet329 | All tool elements (1-1672) | Model Change removal in sp step |
| _PickedSet333 | All nodes | Temperature field application |
