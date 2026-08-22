# Plate with Hole - Stress Concentration Analysis

## Prompt

Perform a static structural analysis on a plate with a central circular hole to demonstrate stress concentration effects. Upload the geometry file `plate.step` located in the `pymechanical-mcp/examples/plate_with_hole/` directory.

### Setup Requirements:
1. **Material**: Structural Steel (default)
2. **Mesh**: Mesh with element size of 2mm (fine mesh to capture stress concentration around hole)
3. **Boundary Conditions**:
   - Fixed support on the left end face (YZ face at X = -100mm)
   - Tensile force of 10000 N on the right end face (YZ face at X = +100mm), directed in the +X direction
4. **Results**:
   - Total Deformation
   - Equivalent (von Mises) Stress
   - Normal Stress in X direction
   - Take a screenshot of the von Mises stress result showing stress concentration around the hole

### Expected Outcome:
- Stress concentration factor of approximately 3× at the hole edges (top/bottom of hole)
- Clear stress gradient showing high stress (red) at hole edges tapering to nominal stress (blue/green) away from hole
- Classic "butterfly" stress pattern around the hole
- This is the quintessential stress concentration demo in engineering education

## Geometry
- File: `plate.step`
- Dimensions: 200mm × 100mm × 5mm rectangular plate
- Central circular hole: 30mm diameter
- Generated with CadQuery (see `../generate_geometry.py`)

## Theory
The theoretical stress concentration factor (Kt) for a plate with a central hole under uniaxial tension is approximately 3.0 when the hole diameter is small relative to the plate width. For this geometry (d/W = 30/100 = 0.3), Kt ≈ 3.0.
