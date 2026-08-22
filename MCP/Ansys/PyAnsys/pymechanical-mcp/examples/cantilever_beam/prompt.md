# Cantilever Beam - Static Structural Analysis

## Prompt

Perform a static structural analysis of a cantilever beam. Upload the geometry file `beam.step` located in the `pymechanical-mcp/examples/cantilever_beam/` directory.

### Setup Requirements:
1. **Material**: Structural Steel (default)
2. **Mesh**: Default mesh with element size of 5mm
3. **Boundary Conditions**:
   - Fixed support on one end face (the YZ face at X = -100mm)
   - Pressure load of 1 MPa on the top face (XY face at Z = +5mm)
4. **Results**:
   - Total Deformation
   - Equivalent (von Mises) Stress
   - Take a screenshot of the von Mises stress result

### Expected Outcome:
- Maximum deformation at the free end of the beam
- Stress concentration at the fixed support
- Beautiful stress gradient from blue (low) to red (high)

## Geometry
- File: `beam.step`
- Dimensions: 200mm × 20mm × 10mm rectangular beam
- Generated with CadQuery (see `../generate_geometry.py`)
