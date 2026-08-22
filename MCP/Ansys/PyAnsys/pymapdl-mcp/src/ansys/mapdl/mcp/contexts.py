# Copyright (C) 2025 - 2026 ANSYS, Inc. and/or its affiliates.
# SPDX-License-Identifier: Apache-2.0
#
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Context tools for PyMAPDL MCP Server.

This module defines MCP tools that provide context and guidance for
PyMAPDL and Ansys MAPDL workflows. These tools return context information
that can be accessed by the LLM to get help with various aspects of
MAPDL simulations.
"""

# flake8: noqa: E501

from typing import Literal

# Import the mcp instance from mcp.py
from ansys.mapdl.mcp import app

GuidelinesContent = Literal[
    "workflow",
    "geometry",
    "elements",
    "materials",
    "mesh",
    "boundary_conditions",
    "solution",
    "postprocessing",
    "general",
]


def get_guidelines_for_workflow_overview() -> str:
    """Get general MAPDL simulation workflow guidelines."""
    return """# MAPDL Simulation Workflow Overview

When explaining or generating PyMAPDL or Ansys MAPDL workflows, ALWAYS FOLLOW this general simulation process, independent of the specific analysis type (static, modal, thermal, nonlinear, etc.):

## Code Documentation with Comments

**IMPORTANT**: Always introduce each major section of the workflow with a descriptive comment using `mapdl.com()` or the `/COM` command. This improves code readability and helps users understand the workflow structure.

Examples:
- `mapdl.com("Creating geometry")`
- `mapdl.com("Defining element types")`
- `mapdl.com("Setting material properties")`
- `mapdl.com("Generating mesh")`
- `mapdl.com("Applying boundary conditions")`
- `mapdl.com("Applying loads")`
- `mapdl.com("Solving")`
- `mapdl.com("Post-processing results")`

## Workflow Steps

1. **Preprocessing**
   - Geometry definition and meshing
   - Finite element model setup
   - Material model definition
   - Mesh generation
   - Boundary conditions and loads

2. **Solution**
   - Analysis type specification
   - Solver configuration
   - System assembly and solution

3. **Postprocessing**
   - Results extraction
   - Visualization
   - Data analysis

4. **General Rules**
   - Accuracy depends on element choice, mesh density, material modeling, and boundary conditions
   - Always include convergence checks or verification steps
   - Keep the workflow analysis-agnostic: details may vary, but the structure remains the same

Always follow this general simulation process when explaining or generating PyMAPDL or Ansys MAPDL workflows, independent of the specific analysis type.
"""


def get_guidelines_for_preprocessing_geometry() -> str:
    """Get geometry and meshing guidelines for MAPDL preprocessing."""
    return """# Preprocessing: Geometry

## Section Comment Requirement

**ALWAYS** start the geometry section with a descriptive comment:
```python
mapdl.com("Creating geometry")
```

## Geometry Guidelines

- If there is geometry, it must be meshed into finite elements.
- If the user does not specify the geometry dimensions (2D vs 3D) or it is not obvious from the query (for instance, the user is mentioning "PLANE" elements), assume 3D.
- If it is not specified, assume simple geometries (rectangles, circles, boxes, cylinders, spheres, etc.), instead of complex CAD geometries, imported meshed or elements/nodes models.

## Key Considerations

- **2D vs 3D**: Default to 3D unless explicitly specified or obvious from context
- **Geometry Complexity**: Prefer simple geometric shapes over complex CAD imports
- **Meshing Requirement**: All geometry must be converted to finite elements before analysis

## Common Geometry Types

- **2D**: Rectangles, circles, polygons
- **3D**: Boxes, cylinders, spheres, cones
- **Special Cases**: Beams, shells, and other structural elements may use simplified geometry representations
"""


def get_guidelines_for_preprocessing_elements() -> str:
    """Get element type selection and definition guidelines."""
    return """# Preprocessing: Finite Element Model

## Section Comment Requirement

**ALWAYS** start the element type definition section with a descriptive comment:
```python
mapdl.com("Defining element types")
```

## Element Type Selection

Element types determine the formulation and capabilities of the elements, and are normally defined using the ET command.

The following element types are commonly used in MAPDL simulations:

### Structural Analysis Elements

- **3D Solids**: SOLID186
  - Example: `ET,1,SOLID186`
- **Shells**: SHELL181
  - Example: `ET,1,SHELL181`
- **Beams**: BEAM189
  - Example: `ET,1,BEAM189`
  - Note: Assume rectangular cross-section unless specified otherwise

### Thermal Analysis Elements

- **3D Solids**: SOLID278
  - Example: `ET,1,SOLID278`
- **Shells**: SHELL131
  - Example: `ET,1,SHELL131`

### 2D Analysis Elements

- **Structural 2D**: PLANE183
  - Example: `ET,1,PLANE183`
- **Thermal 2D**: PLANE293
  - Example: `ET,1,PLANE293`

### Contact Elements

- **Contact**: CONTA174
  - Example: `ET,1,CONTA174`
- **Target**: TARGE170
  - Example: `ET,2,TARGE170`

### Specialized Elements

- **Fluid Dynamics**: FLUID30, FLUID80
- **Electromagnetic**: SOLID5, SOLID97
- **Coupled Field**: SOLID226

## Element Assignment Requirements

- Each geometry must have an appropriate element type assigned
- Define element types before creating the mesh
- Choose elements based on analysis type and geometry
- For beam elements, ensure proper cross-section definition
"""


def get_guidelines_for_preprocessing_materials() -> str:
    """Get material model definition guidelines."""
    return """# Preprocessing: Material Models

## Section Comment Requirement

**ALWAYS** start the material properties section with a descriptive comment:
```python
mapdl.com("Setting material properties")
```

## Material Property Definition

Define material properties (elastic, plastic, thermal, damping, etc.) as needed.

### Key Requirements

- Material properties must be assigned to the relevant regions of the model
- If not specified, assume linear elastic isotropic materials

### Default Material Assumptions

- **Structural Analysis**: Steel
  - Young's Modulus: ~200 GPa
  - Poisson's Ratio: ~0.3
  - Density: ~7850 kg/m³

- **Thermal Analysis**: Aluminum
  - Thermal Conductivity: ~200 W/(m·K)
  - Specific Heat: ~900 J/(kg·K)
  - Density: ~2700 kg/m³

### Material Property Types

1. **Elastic Properties**
   - Young's Modulus (EX)
   - Poisson's Ratio (PRXY)
   - Shear Modulus (GXY)

2. **Plastic Properties**
   - Yield Stress
   - Hardening Parameters
   - Plasticity Models

3. **Thermal Properties**
   - Thermal Conductivity (KXX)
   - Specific Heat (C)
   - Thermal Expansion (ALPX)

4. **Damping Properties**
   - Structural Damping
   - Material Damping Ratio

### Example Material Definition

```python
# Linear elastic isotropic material (Steel)
mapdl.mp("EX", 1, 200e9)    # Young's modulus in Pa
mapdl.mp("PRXY", 1, 0.3)    # Poisson's ratio
mapdl.mp("DENS", 1, 7850)   # Density in kg/m³
```
"""


def get_guidelines_for_preprocessing_mesh() -> str:
    """Get mesh generation guidelines."""
    return """# Preprocessing: Mesh

## Section Comment Requirement

**ALWAYS** start the meshing section with a descriptive comment:
```python
mapdl.com("Generating mesh")
```

## Mesh Generation Guidelines

### Key Requirements

- If meshing is required, generate the mesh using appropriate meshing commands
- Ensure mesh quality and density are suitable for the analysis
- Use parameters to control mesh size and refinement, so the user can adjust them as needed

### Mesh Quality Considerations

1. **Element Size**: Balance between accuracy and computational cost
2. **Element Shape**: Avoid highly distorted elements
3. **Mesh Density**: Refine in areas of high gradients or stress concentration
4. **Mesh Transitions**: Gradual transitions between fine and coarse regions

### Common Meshing Commands

- **Automatic Meshing**: `mapdl.vmesh()`, `mapdl.amesh()`, `mapdl.lmesh()`
- **Mesh Size Control**: `mapdl.esize()`, `mapdl.aesize()`, `mapdl.lesize()`
- **Mesh Refinement**: `mapdl.mopt()`, `mapdl.smrtsize()`

### Best Practices

- Use parametric mesh sizing for easy adjustment
- Check mesh quality after generation
- Refine mesh in critical areas
- Consider symmetry to reduce model size
- Verify element connectivity

### Example Mesh Generation

```python
# Set global element size
mapdl.esize(0.01)

# Mesh volumes
mapdl.vmesh("ALL")

# Or use smart sizing
mapdl.smrtsize(4)  # Medium mesh density
mapdl.vmesh("ALL")
```
"""


def get_guidelines_for_preprocessing_boundary_conditions() -> str:
    """Get boundary conditions and loads application guidelines."""
    return """# Preprocessing: Boundary Conditions and Loads

## Section Comment Requirement

**ALWAYS** start the boundary conditions and loads sections with descriptive comments:
```python
mapdl.com("Applying boundary conditions")
# ... apply boundary conditions ...

mapdl.com("Applying loads")
# ... apply loads ...
```

## Application Guidelines

Apply boundary conditions and loads (supports, forces, pressures, temperatures, displacements, etc.).

### Key Requirements

- Ensure that all necessary constraints and loads are defined for the analysis
- Ensure there is no rigid body motion (unconstrained model so it "flies" away) unless specifically intended. For that purpose, at least one node must be fixed in all degrees of freedom, unless the user specifies otherwise.
- If not specified, assume common boundary conditions (fixed supports, uniform loads, etc.) based on the analysis type
- For beam elements, ensure that loads and supports are applied correctly at nodes or along the length of the beam
- For beam elements, make sure to constrain the rotational degrees of freedom (ROTX, ROTY, ROTZ) as needed to prevent rigid body motions

### Common Boundary Conditions by Analysis Type

#### Structural Analysis
- **Fixed Supports**: Constrain all DOFs (UX, UY, UZ, ROTX, ROTY, ROTZ)
- **Pinned Supports**: Constrain translational (UX, UY, UZ) DOFs only
- **Roller Supports**: Constrain specific DOFs based on orientation
- **Symmetry**: Constrain appropriate DOFs on symmetry planes

#### Thermal Analysis
- **Fixed Temperature**: Apply temperature constraints
- **Convection**: Apply heat transfer coefficients
- **Heat Flux**: Apply heat flow rates
- **Insulation**: Zero heat flux boundary

### Load Types

Prefer forces and displacements over equivalent loads, body forces or surface forces unless the user specifies otherwise.
Prefer point forces over distributed loads unless the user specifies otherwise.
Prefer displacements over equivalent forces unless the user specifies otherwise.

Unless specified otherwise, assume downward forces in the negative Y direction for 2D and negative Z direction for 3D.

1. **Structural Loads**
   - Point Forces: `mapdl.f()`
   - Prescribed Displacements: `mapdl.d()`
   - Surface Pressures: `mapdl.sf()`
   - Body Forces: `mapdl.bf()`

2. **Thermal Loads**
   - Heat Flow: `mapdl.f()`
   - Temperature: `mapdl.d()`
   - Heat Flux: `mapdl.sf()`
   - Heat Generation: `mapdl.bf()`

### Example Applications

```python
# Fix all DOFs on a surface
mapdl.nsel("S", "LOC", "Z", 0)
mapdl.d("ALL", "ALL", 0)
mapdl.allsel()

# Apply pressure on a surface
mapdl.nsel("S", "LOC", "Z", 1.0)
mapdl.sf("ALL", "PRES", 1000)
mapdl.allsel()

# Apply point force
mapdl.f(node_id, "FY", -1000)
```

### Special Considerations for Beam Elements

- Apply loads at nodes or distributed along length
- Constrain rotational DOFs to prevent rigid body motion
- Ensure proper moment and force directions
- Check beam orientation and local coordinate systems
"""


def get_guidelines_for_solution_phase() -> str:
    """Get solution phase guidelines for MAPDL analysis."""
    return """# Solution Phase

## Section Comment Requirement

**ALWAYS** start the solution section with a descriptive comment:
```python
mapdl.com("Solving")
```

## Solution Configuration

### Entering Solution Mode

- Use `mapdl.solution()` to enter solution mode, instead of `mapdl.run('/SOLU')`

### Analysis Type Selection

#### Static Structural Analysis
```python
mapdl.antype('STATIC')
```

#### Modal Analysis
```python
mapdl.antype('MODAL')
```

#### Transient/Dynamic Analysis
```python
mapdl.antype('TRANSIENT')
```

#### Harmonic Analysis
```python
mapdl.antype('HARMONIC')
```

### Solver Configuration

1. **Linear Static Analysis**
   - Use direct solvers when possible
   - Configure solution options for efficiency

2. **Nonlinear Analysis**
   - Set appropriate nonlinear solution settings
   - Define convergence criteria
   - Configure load stepping

3. **Dynamic/Transient Analysis**
   - Define time steps and durations
   - Ensure time step is appropriate for the problem
   - Consider stability and accuracy requirements

4. **Modal Analysis**
   - Specify number of modes to extract
   - Define frequency range if needed
   - Choose appropriate eigenvalue solver

### Solution Process

1. Assemble the system of equations (stiffness, mass, damping if applicable)
2. Apply loads and constraints
3. Solve for the unknowns
4. Check for convergence (especially in nonlinear analyses)

### Example Solution Setup

```python
# Enter solution mode
mapdl.solution()

# Set analysis type
mapdl.antype('STATIC')

# Solve
mapdl.solve()
```

### Convergence Monitoring

- Monitor solution convergence in nonlinear analyses
- Check for warnings or errors in solution output
- Verify load step completion
- Review convergence plots if applicable
"""


def get_guidelines_for_postprocessing_phase() -> str:
    """Get postprocessing phase guidelines for MAPDL analysis."""
    return """# Postprocessing Phase

## Section Comment Requirement

**ALWAYS** start the postprocessing section with a descriptive comment,
followed by the postprocessing commands:
```python
mapdl.com("Post-processing results")
mapdl.post1()
mapdl.set(1, 1)  # Set load step and substep
...
```

## Entering Postprocessing Mode

When the solution is complete, enter postprocessing mode:
- **General Postprocessor**: `mapdl.post1()` - For static, modal, and time-point results
- **Time-History Postprocessor**: `mapdl.post26()` - For transient or harmonic analyses

## Results Extraction

### Key Requirements

- Ensure to select the appropriate time step or frequency using `mapdl.set(time_step)`.
- If you do not know the time step or frequency number, assume the first one (1).
- Always verify that the results being extracted correspond to the correct load step and substep.
- Make sure the right elements and nodes are selected for result extraction
- If using element tables, ensure the keys to populate those tables are correct

### Result Types by Analysis

#### Structural Analysis
- Displacements (UX, UY, UZ, USUM)
- Stresses (SX, SY, SZ, SEQV)
- Strains (EPELX, EPELY, EPELZ, EPEQV)
- Reaction Forces

#### Modal Analysis
- Natural Frequencies
- Mode Shapes
- Modal Participation Factors

#### Thermal Analysis
- Temperatures
- Heat Fluxes
- Temperature Gradients

## Visualization Methods

### Plotting Session Strategy

**IMPORTANT: By default, use MAPDL commands (`run_mapdl_command` tool) for all plots**

#### When to use normal MAPDL session (Default - Preferred)

Use the normal MAPDL session for:

1. **All MAPDL native plot methods** - These provide MAPDL-backend plots:
   - Geometry plots: `APLOT`, `LPLOT`, `KPLOT`, `VPLOT`
   - Mesh plots: `EPLOT`, `NPLOT`
   - Post-processing plots: `PLNSOL`, `PLESOL`, `PLDISP`

2. **Capturing Screenshots**: Use the `screenshot` tool with MAPDL plot commands.
   The `screenshot` tool accepts:
   - `commands`: MAPDL APDL commands to run before capturing (e.g. `EPLOT`)
   - `show_plot_on_popup`: set to `True` to also open the captured image in an
     external popup window

#### When to Use Persistent Python Session

Use the persistent Python session with `run_python_code ` or `custom_plot` tool ONLY for:

1. **Advanced post-processing tasks** that require Python libraries such as NumPy, Matplotlib,
   or PyVista. Examples include:
   Post-processing object methods:
     - `mapdl.post_processing.plot_nodal_solution()`
     - `mapdl.post_processing.plot_element_solution()`
     - `mapdl.post_processing.plot_nodal_displacement()`
     - `mapdl.post_processing.plot_nodal_stress()`

2. **Custom Matplotlib Plots** - When you need to create plots that MAPDL doesn't provide:
   ```python
   # Extract data from MAPDL
   displacements = mapdl.get_array("NODE", item1="U", it1num="Y")

   # Create custom matplotlib plot
   plt.figure()
   plt.plot(displacements)
   plt.xlabel("Node Number")
   plt.ylabel("Displacement (m)")

   # Save using the helper function from persistent session
   result = save_matplotlib_plot()
   print(result)

3. **Custom PyVista Visualizations** - When you need advanced 3D visualization beyond MAPDL's capabilities

4. **Data Processing and Visualization** - Combining NumPy/Pandas with custom plots

5. **Capturing plots**
   Use the ``custom_plot`` tool to create custom plots and capture them.
   Helpers available:
   - `save_matplotlib_plot` helper function: capture and return plots as base64 strings
   - `save_plot` helper function: capture and return other plot types


### Using Post Processing Methods (Preferred)

If using the persistent Python session for postprocessing, follow these guidelines:
- **DO NOT** use `mapdl.result` methods unless specifically requested by the user
- **USE** `mapdl.post_processing` methods
- These methods work with the `screenshot`` tool to capture plots

### Plot Types Available in MAPDL

1. **Contour Plots** (Preferred)
   - Show result distribution across model
   - Color-coded for easy interpretation
   - Use methods like `plot_nodal_solution()`, `plot_element_solution()`

2. **Vector Plots**
   - Show directional results
   - Useful for displacements and heat flux
   - Available in MAPDL native plotter

3. **Animations**
   - Show mode shapes
   - Display time-varying results

## Data Extraction for Custom Processing

### Using mapdl.get_value and mapdl.get_array

If you want to use `*GET` commands to extract specific results, use `mapdl.get_value()` instead and explain what each command does.

### NumPy and Matplotlib Integration (Custom Plots Only)

**NOTE: Use NumPy and Matplotlib ONLY when MAPDL native plots don't meet your needs. These require the persistent Python session.**

When you need custom plots not available in MAPDL, use the `run_python_code ` or `custom_plot` tool:

1. **Import required libraries** at the beginning of the code:
   ```python
   import numpy as np
   import matplotlib.pyplot as plt
   ```

2. **Extract data** using `mapdl.get_array()` and `mapdl.get_value()`:
   ```python
   # Extract nodal displacements
   displacements = mapdl.get_array("NODE", item1="U", it1num="Y")

   # Extract specific value
   max_stress = mapdl.get_value("SECR", 0, "S", "EQV", "MAX")
   ```

3. **Process and visualize** using NumPy and Matplotlib:
   ```python
   # Create custom plots
   plt.figure()
   plt.plot(displacements)
   plt.xlabel("Node Number")
   plt.ylabel("Displacement (m)")
   plt.title("Nodal Displacement Distribution")

   # Save using the helper function from persistent session
   result = save_matplotlib_plot()
   print(result)
   ```

## Example Postprocessing Workflow

```python
# Enter postprocessor
mapdl.post1()

# Select load step and substep
mapdl.set(1, 1)

# Plot nodal solution
mapdl.post_processing.plot_nodal_solution("USUM")

# Extract maximum von Mises stress
max_stress = mapdl.get_value("SECR", 0, "S", "EQV", "MAX")
print(f"Maximum von Mises Stress: {max_stress} Pa")

# Create element table for stress
mapdl.etable("SEQV", "S", "EQV")
mapdl.plot_element_solution("SEQV")
```

## Best Practices

- Always verify result units
- Check for unrealistic values
- Compare with hand calculations or analytical solutions
- Document key results and findings
- Create clear, labeled visualizations
"""


def get_guidelines_for_general_rules() -> str:
    """Get general rules and best practices for MAPDL workflows."""
    return """# General Rules and Best Practices

## Accuracy Factors

Simulation accuracy depends on multiple factors:

1. **Element Choice**
   - Select appropriate element types for the physics
   - Consider element formulation and capabilities
   - Match element to geometry and loading conditions

2. **Mesh Density**
   - Finer mesh in critical areas
   - Balance accuracy with computational cost
   - Perform mesh convergence studies

3. **Material Modeling**
   - Use accurate material properties
   - Include relevant nonlinear effects if needed
   - Validate material data sources

4. **Boundary Conditions**
   - Represent physical constraints accurately
   - Avoid over-constraining the model
   - Check for rigid body modes

## Verification and Validation

### Always Include

- **Convergence Checks**: Verify solution has converged
- **Mesh Independence**: Ensure results don't change significantly with finer mesh
- **Equilibrium Checks**: Verify force/moment balance
- **Sanity Checks**: Compare with expected behavior or analytical solutions

### Verification Steps

1. Check for errors and warnings in solution output
2. Verify deformed shape makes physical sense
3. Check stress distributions for smoothness
4. Validate reaction forces against applied loads
5. Compare with simplified hand calculations

## Workflow Consistency

### Analysis-Agnostic Structure

Keep the workflow structure consistent across all analysis types:
- Preprocessing steps remain the same
- Solution configuration varies by analysis type
- Postprocessing follows similar patterns

### Details May Vary, But Structure Remains

- Different analyses require different element types
- Load and boundary condition types change
- Result types differ by physics
- Core workflow steps stay constant

## Code Quality

1. **Use PyMAPDL Methods**: Prefer `mapdl.method()` over `mapdl.run("command")`
   **DO NOT USE `mapdl.run` COMMANDS UNLESS SPECIFICALLY REQUESTED BY THE USER**
2. **Parameter Usage**: Use variables for key values to enable easy modification
3. **Documentation**: Comment critical steps and assumptions
4. **Error Handling**: Include checks for common issues
5. **Reproducibility**: Make workflows repeatable with clear inputs

## Common Pitfalls to Avoid

- Missing units specification
- Over-constraining the model
- Inappropriate element selection
- Insufficient mesh refinement
- Ignoring convergence warnings
- Not validating results
- Using inconsistent coordinate systems
"""


_CONTENT_MAP = {
    "workflow": get_guidelines_for_workflow_overview,
    "geometry": get_guidelines_for_preprocessing_geometry,
    "elements": get_guidelines_for_preprocessing_elements,
    "materials": get_guidelines_for_preprocessing_materials,
    "mesh": get_guidelines_for_preprocessing_mesh,
    "boundary_conditions": get_guidelines_for_preprocessing_boundary_conditions,
    "solution": get_guidelines_for_solution_phase,
    "postprocessing": get_guidelines_for_postprocessing_phase,
    "general": get_guidelines_for_general_rules,
}


@app.tool()
def get_guidelines_for(content: GuidelinesContent) -> str:
    """Get MAPDL simulation guidelines for a specific topic.

    Use this tool before writing any PyMAPDL or MAPDL code to retrieve the
    relevant guidelines for the workflow step you are about to implement.
    Call it once per topic needed; it is strongly recommended before every
    code-generation task.

    Parameters
    ----------
    content : str
        The guideline topic to retrieve. One of:

        - ``"workflow"``: Complete simulation workflow overview
          (preprocessing → solution → postprocessing).
        - ``"geometry"``: Geometry creation: 2D/3D defaults, primitive
          shapes, meshing requirement.
        - ``"elements"``: Element type selection: SOLID186, SHELL181,
          BEAM189, PLANE183, thermal and contact elements.
        - ``"materials"``: Material property definition: elastic,
          plastic, thermal, damping; default steel/aluminum values.
        - ``"mesh"``: Mesh generation: sizing, quality, VMESH/
          AMESH commands, smart sizing.
        - ``"boundary_conditions"``: Boundary conditions and loads: fixed/pinned
          supports, forces, pressures, beam element constraints.
        - ``"solution"``: Solution configuration: analysis type
          (STATIC, MODAL, TRANSIENT, HARMONIC), solver options, SOLVE.
        - ``"postprocessing"``: Results extraction and visualization: POST1/
          POST26, plot methods, data extraction.
        - ``"general"``: General rules and best practices: accuracy
          factors, verification steps, code quality.

    Returns
    -------
    str
        Guideline text for the requested topic.
    """
    return _CONTENT_MAP[content]()
