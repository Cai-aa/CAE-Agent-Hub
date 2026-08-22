.. _ref_bracket_modal:

Bracket modal analysis
======================

This example demonstrates a modal analysis on an L-shaped bracket using PyMechanical-MCP.
The workflow extracts the first six natural frequencies and mode shapes to identify resonance risks.

Engineering objective
---------------------

Determine the first six natural frequencies and mode shapes of a five-millimeter thick L-shaped steel bracket.
Identify the fundamental bending mode and higher-order twisting modes. Confirm natural frequencies
are in the range of approximately 100 Hz to several kilohertz.

Geometry
--------

- **File**: ``bracket.step``
- **L-bracket dimensions**: 100 millimeters vertical x 60 millimeters horizontal x 80 millimeters wide x 5 millimeters thick
- **Features**: Two eight-millimeter mounting holes in the horizontal leg and one 15-millimeter hole in the vertical plate

Setup requirements
------------------

.. list-table::
   :widths: 25 75
   :header-rows: 1

   * - Setting
     - Value
   * - Material
     - Structural Steel (default)
   * - Mesh
     - Element size is 3 millimeters for good mode-shape resolution
   * - Fixed support
     - Cylindrical faces of the two mounting holes in the horizontal leg
   * - Analysis type
     - Modal
   * - Number of modes
     - First 6
   * - Frequency range
     - 0 to 10,000 hertz

Tool workflow
-------------

1. Connect to or launch Mechanical using `connect_to_mechanical` or `launch_mechanical`.
2. Upload the `bracket.step` file using `upload_file`.
3. Assign structural steel as the material to all bodies using `run_python_script`.
4. Insert a modal analysis system and set the number of modes to six using `run_python_script`.
5. Apply fixed supports to the bolt-hole cylindrical faces using `run_python_script`.
6. Generate a three-millimeter element size mesh using `run_python_script`.
7. Run the solver using `solve_analysis`.
8. Retrieve and print natural frequencies using `run_python_script`.
9. Capture a screenshot of Mode 1 (the fundamental mode) using `screenshot`.

Expected outcome
----------------

- **Mode 1**: Bending of the vertical plate (fundamental mode)
- **Modes 2 to 6**: Progressive twisting and complex deformation patterns
- Natural frequencies ranging from approximately 100 hertz to several kilohertz

Prompt example
--------------

.. code-block:: text

   Perform a modal analysis on an L-shaped bracket to find the first 6 natural frequencies
   and mode shapes. Upload the geometry file bracket.step.

   - Material: Structural Steel (default)
   - Mesh: element size 3 mm
   - Fixed support on mounting hole cylindrical faces (horizontal leg)
   - Modal analysis: first 6 modes, frequency range 0-10,000 Hz
   - Results: Total Deformation for each mode, list of natural frequencies
   - Take a screenshot of Mode 1 (fundamental mode)
