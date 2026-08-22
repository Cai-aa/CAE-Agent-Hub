.. _ref_plate_with_hole:

Plate with hole
===============

This example demonstrates a stress concentration analysis on a flat plate with a
central circular hole using PyMechanical-MCP. It is a classic benchmark for validating
stress concentration factors against the theoretical value of approximately 3x.

Engineering objective
---------------------

Compute the stress concentration factor for a 200 millimeter x 100 millimeter x 5 millimeter
rectangular plate with a 30 millimeter-diameter central hole under uniaxial tension. Compare
the maximum principal stress near the hole to the nominal far-field stress and confirm Kt
is approximately equal to 3.

Geometry
--------

- **File**: ``plate.step``
- **Plate dimensions**: 200 millimeters x 100 millimeters x 5 millimeters (with a diameter
  central hole of 30 millimeters)

Setup requirements
------------------

.. list-table::
   :widths: 25 75
   :header-rows: 1

   * - Setting
     - Value
   * - Material
     - Structural steel (default)
   * - Mesh
     - Element size is 2 millimeters (fine mesh to resolve stress concentration)
   * - Fixed support
     - Left end face (YZ face at X = -100 millimeters)
   * - Tensile force
     - 10,000 newton in +X direction on right end face (YZ face at X = +100 millimeters)

Tool workflow
-------------

1. Connect to or launch Mechanical using `connect_to_mechanical` or `launch_mechanical`.
2. Upload the `plate.step` file using `upload_file`.
3. Assign structural steel as the material to the plate body using `run_python_script`.
4. Generate a two-millimeter element size mesh for fine resolution near the hole using `run_python_script`.
5. Apply a fixed support on the left end face using `run_python_script`.
6. Apply a 10,000 newton tensile force in +X on the right end face using `run_python_script`.
7. Run the solver using `solve_analysis`.
8. Add total deformation, equivalent stress, and normal stress X results using `run_python_script`.
9. Capture a screenshot of the equivalent stress contour using `screenshot`.

Expected outcome
----------------

- Stress concentration factor of approximately 3x at the hole edges (top and bottom)
- Classic butterfly stress pattern: high stress (red) at the hole edges tapering to nominal (blue/green)
- Maximum stress approximately three times the applied nominal stress

Theory
------

For a plate with a central circular hole under uniaxial tension, Kt is approximately 3.0 when the hole
diameter is small relative to the plate width. For this geometry (d/W = 30/100 = 0.3), Kt is
approximately 3.0.

Prompt example
--------------

.. code-block:: text

   Perform a static structural analysis on a plate with a central circular hole.
   Upload the geometry file plate.step.

   - Material: Structural Steel (default)
   - Mesh: element size 2 mm (fine mesh to capture stress concentration around hole)
   - Fixed support on left end face (YZ face at X = -100 mm)
   - Tensile force of 10,000 N in +X on right end face (YZ face at X = +100 mm)
   - Results: Total Deformation, Equivalent (von Mises) Stress, Normal Stress X
   - Take a screenshot of the von Mises stress result
