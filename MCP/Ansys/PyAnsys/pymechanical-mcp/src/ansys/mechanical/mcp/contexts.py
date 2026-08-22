# Copyright (C) 2026 Synopsys, Inc. and ANSYS, Inc. All rights reserved.
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

"""Context tools for PyMechanical-MCP.

This module defines MCP tools that provide context and guidance for
PyMechanical and Ansys Mechanical workflows. These tools return context
information that can be accessed by the LLM to get help with various
aspects of Mechanical simulations.
"""

# flake8: noqa: E501

from typing import Literal

from ansys.mechanical.mcp import app

GuidelinesContent = Literal[
    "workflow",
    "geometry",
    "materials",
    "meshing",
    "analysis_setup",
    "boundary_conditions",
    "solution",
    "postprocessing",
    "named_selections",
    "general",
]


def get_guidelines_for_workflow_overview() -> str:
    """Get general simulation workflow guidelines for Mechanical.

    Use this tool when explaining or generating PyMechanical or Ansys Mechanical workflows.

    Returns
    -------
    str
        Overview of the general simulation process for all Mechanical analysis types.
    """
    return """# Mechanical Simulation Workflow Overview

When explaining or generating PyMechanical or Ansys Mechanical workflows, ALWAYS FOLLOW this general simulation process.

## PyMechanical Architecture

PyMechanical has two interfaces:
1. **Remote Session**: Connect to a running Mechanical gRPC server
2. **Embedded Instance**: Run Mechanical embedded in the Python process

For MCP server, we primarily use the Remote Session interface.

## API Entry Points

When running scripts inside Mechanical, you have access to these entry points:
- `ExtAPI`: Entry point for all APIs
- `DataModel`: Entry point to access CAD, mesh entities, and Outline objects
- `Model`: The Model object from the Outline
- `Tree`: The Outline (tree structure)
- `Graphics`: The 3D graphics engine

## Workflow Steps

1. **Preprocessing**
   - Import geometry (CAD files)
   - Define materials and assign to bodies
   - Set up mesh controls and generate mesh
   - Define analysis settings

2. **Analysis Setup**
   - Create analysis system (Static Structural, Modal, Thermal, etc.)
   - Apply boundary conditions (supports, constraints)
   - Apply loads (forces, pressures, temperatures)

3. **Solution**
   - Configure solver settings
   - Run the solution

4. **Postprocessing**
   - Add result objects (stress, strain, deformation)
   - Evaluate results
   - Export images and data

## Unit System

Always set the unit system explicitly before defining geometry, loads, or results:

```python
script = '''
ExtAPI.Application.ActiveUnitSystem = MechanicalUnitSystem.StandardMKS
ExtAPI.Application.ActiveAngleUnit = AngleUnitType.Radian
'''
mechanical.run_python_script(script)
```

Common unit systems: `StandardMKS`, `StandardCGS`, `StandardNMM`,
`StandardBIN`, `StandardBFT`.

## Code Execution Pattern

Use `mechanical.run_python_script()` to execute scripts inside Mechanical:

```python
script = '''
# Your Mechanical scripting code here
result = ExtAPI.DataModel.Project.ProductVersion
result
'''
version = mechanical.run_python_script(script)
```

## Transaction Pattern for Performance

When modifying multiple objects, wrap operations in a Transaction:

```python
script = '''
with Transaction():
    for obj in Tree.AllObjects:
        obj.Name = obj.Name + " modified"
'''
mechanical.run_python_script(script)
```
"""


def get_guidelines_for_geometry_import() -> str:
    """Get geometry import guidelines for Mechanical.

    Use this tool when explaining or generating geometry import operations.

    Returns
    -------
    str
        Guidelines for importing a geometry in Mechanical.
    """
    return """# Geometry Import in Mechanical

## Supported Geometry Formats

Mechanical supports various CAD formats:
- ANSYS DesignModeler files (.agdb)
- STEP files (.stp, .step)
- IGES files (.igs, .iges)
- Parasolid files (.x_t, .x_b)
- CATIA files (.CATProduct, .CATPart)
- SolidWorks files (.sldprt, .sldasm)
- NX files (.prt)
- And many more...

## Importing Geometry via Script

```python
script = '''
# Get the geometry import group
geometry_import = Model.GeometryImportGroup.AddGeometryImport()

# Set the geometry file path
geometry_file = r"C:\\path\\to\\your\\geometry.stp"

# Set import format and preferences
geometry_import_format = Ansys.Mechanical.DataModel.Enums.GeometryImportPreference.Format.Automatic
geometry_import_prefs = Ansys.ACT.Mechanical.Utilities.GeometryImportPreferences()
geometry_import_prefs.ProcessNamedSelections = True
geometry_import_prefs.ProcessCoordinateSystems = True

# Import the geometry
geometry_import.Import(geometry_file, geometry_import_format, geometry_import_prefs)
'''
mechanical.run_python_script(script)
```

## Uploading and Importing Geometry (Remote Session)

When using a remote Mechanical session, upload the file first:

```python
# Upload file from local to Mechanical working directory
mechanical.upload("local_geometry.stp")

# Then import using the file in the project directory
script = '''
import os
geometry_import = Model.GeometryImportGroup.AddGeometryImport()
project_dir = ExtAPI.DataModel.Project.ProjectDirectory
geometry_file = os.path.join(project_dir, "local_geometry.stp")

geometry_import_format = Ansys.Mechanical.DataModel.Enums.GeometryImportPreference.Format.Automatic
geometry_import_prefs = Ansys.ACT.Mechanical.Utilities.GeometryImportPreferences()
geometry_import_prefs.ProcessNamedSelections = True
geometry_import.Import(geometry_file, geometry_import_format, geometry_import_prefs)
'''
mechanical.run_python_script(script)
```

## Accessing Geometry Objects

```python
script = '''
# Access the Geometry object
geometry = Model.Geometry

# Get all bodies
bodies = geometry.GetChildren(DataModelObjectCategory.Body, True)

# Iterate through bodies
for body in bodies:
    print("Body: {0}, Material: {1}".format(body.Name, body.Material))
'''
mechanical.run_python_script(script)
```

## Key Considerations

- Ensure geometry files are accessible from the Mechanical server
- Use `mechanical.upload()` to transfer files to the server if needed
- Large assemblies may require longer import times
- Check for geometry errors after import
"""


def get_guidelines_for_materials() -> str:
    """Get material definition guidelines for Mechanical.

    Use this tool when explaining or generating material definitions.

    Returns
    -------
    str
        Guidelines for defining and assigning materials in Mechanical.
    """
    return """# Material Definition in Mechanical

## Accessing Engineering Data

Materials in Mechanical come from Engineering Data. The default material library
includes common materials like Structural Steel, Aluminum Alloy, etc.

## Assigning Materials to Bodies

```python
script = '''
# Get geometry
geometry = Model.Geometry

# Get all bodies
bodies = geometry.GetChildren(DataModelObjectCategory.Body, True)

# Assign material to each body
for body in bodies:
    body.Material = "Structural Steel"
'''
mechanical.run_python_script(script)
```

## Available Default Materials

Common materials available by default:
- "Structural Steel"
- "Aluminum Alloy"
- "Copper Alloy"
- "Gray Cast Iron"
- "Titanium Alloy"
- "Stainless Steel"

## Creating Custom Materials

For custom materials, you typically need to define them in Engineering Data
before importing into Mechanical. However, you can also use scripts:

```python
script = '''
# Access Engineering Data through ExtAPI
eng_data = ExtAPI.DataModel.Project.Model.Materials

# Get material assignment for a body
body = Model.Geometry.GetChildren(DataModelObjectCategory.Body, True)[0]
body.Material = "Aluminum Alloy"
'''
mechanical.run_python_script(script)
```

## Material Properties

Key material properties for structural analysis:
- Young's Modulus (EX)
- Poisson's Ratio (PRXY)
- Density (DENS)
- Yield Strength
- Ultimate Tensile Strength

For thermal analysis:
- Thermal Conductivity
- Specific Heat
- Coefficient of Thermal Expansion
"""


def get_guidelines_for_meshing() -> str:
    """Get mesh generation guidelines for Mechanical.

    Use this tool when explaining or generating mesh operations.

    Returns
    -------
    str
        Guidelines for generating meshes in Mechanical.
    """
    return """# Mesh Generation in Mechanical

## Accessing the Mesh Object

```python
script = '''
# Get the mesh object
mesh = Model.Mesh

# Generate mesh with default settings
mesh.GenerateMesh()

# Get mesh statistics
print("Nodes: {0}".format(mesh.Nodes.Count if mesh.Nodes else 0))
print("Elements: {0}".format(mesh.Elements.Count if mesh.Elements else 0))
'''
mechanical.run_python_script(script)
```

## Mesh Controls

### Global Mesh Size

```python
script = '''
mesh = Model.Mesh

# Set global element size (use square brackets for units)
mesh.ElementSize = Quantity("10 [mm]")
'''
mechanical.run_python_script(script)
```

### Adding Mesh Controls

```python
script = '''
mesh = Model.Mesh

# Add sizing control scoped to a Named Selection
sizing = mesh.AddSizing()
ns = ExtAPI.DataModel.GetObjectsByName("CriticalRegion")[0]
sizing.Location = ns
sizing.ElementSize = Quantity("2 [mm]")

# Generate mesh
mesh.GenerateMesh()
'''
mechanical.run_python_script(script)
```

## Mesh Methods

- **Automatic**: Default method, lets Mechanical choose
- **Tetrahedrons**: For complex 3D geometry
- **Hex Dominant**: Preferred for structural analysis when possible
- **Sweep**: For extruded geometry
- **MultiZone**: Combines structured and unstructured meshing

## Mesh Quality

```python
script = '''
mesh = Model.Mesh

# Check mesh quality metrics
mesh.GenerateMesh()

# Access mesh statistics
stats = mesh.GetMeshStatistics()
'''
mechanical.run_python_script(script)
```

## Best Practices

- Start with coarser mesh for initial analysis
- Refine mesh in areas of high stress gradients
- Use mesh refinement studies for convergence
- Check element quality: skewness < 0.95, aspect ratio < 20 for good quality
- Aim for skewness < 0.5 and aspect ratio < 5 in critical regions
- Use at least 2-3 elements through thickness for bending-dominated problems
- For contact regions, ensure matching mesh density on both surfaces
"""


def get_guidelines_for_analysis_setup() -> str:
    """Get analysis setup guidelines for Mechanical.

    Use this tool when setting up structural, modal, or thermal analyses.

    Returns
    -------
    str
        Guidelines for setting up analyses in Mechanical.
    """
    return """# Analysis Setup in Mechanical

## Analysis Types

Mechanical supports various analysis types:
- **Static Structural**: Linear and nonlinear static analysis
- **Modal**: Natural frequency and mode shape extraction
- **Harmonic Response**: Frequency response analysis
- **Transient Structural**: Time-dependent structural analysis
- **Steady-State Thermal**: Heat transfer at equilibrium
- **Transient Thermal**: Time-dependent heat transfer
- **Coupled Field**: Thermal-structural coupling

## Adding an Analysis

```python
script = '''
# Add a Static Structural analysis
analysis = Model.AddStaticStructuralAnalysis()

# Or add other analysis types:
# modal_analysis = Model.AddModalAnalysis()
# thermal_analysis = Model.AddSteadyStateThermalAnalysis()
'''
mechanical.run_python_script(script)
```

## Analysis Settings

```python
script = '''
# Get analysis settings
analysis = Model.Analyses[0]
settings = analysis.AnalysisSettings

# For Static Structural - configure step controls
settings.NumberOfSteps = 1

# For large deformation (nonlinear)
settings.LargeDeflection = True
'''
mechanical.run_python_script(script)
```

## Modal Analysis Settings

```python
script = '''
analysis = Model.AddModalAnalysis()
settings = analysis.AnalysisSettings

# Set number of modes to extract
settings.MaximumModesToFind = 10

# Set frequency range if needed
# settings.RangeMinimum = Quantity("0 [Hz]")
# settings.RangeMaximum = Quantity("1000 [Hz]")
'''
mechanical.run_python_script(script)
```

## Solver Controls

```python
script = '''
analysis = Model.Analyses[0]
settings = analysis.AnalysisSettings

# Solver type: Direct is more robust, Iterative is faster for large models
settings.SolverType = SolverType.Direct  # or SolverType.Iterative (PCG)

# For nonlinear analysis - substepping
settings.AutomaticTimeStepping = AutomaticTimeStepping.On
settings.DefineBy = TimeStepDefineByType.Substeps
settings.InitialSubsteps = 10
settings.MinimumSubsteps = 5
settings.MaximumSubsteps = 100
'''
mechanical.run_python_script(script)
```

## Contact Setup

```python
script = '''
# Access existing contact regions (auto-detected)
connections = Model.Connections
if connections.Children.Count > 0:
    contact_region = connections.Children[0].Children[0]  # First contact region
    contact_region.ContactType = ContactType.Bonded  # or Frictional, Frictionless, NoSeparation
    contact_region.ContactFormulation = ContactFormulation.AugmentedLagrange
'''
mechanical.run_python_script(script)
```

## Nonlinear Analysis Best Practices

- Enable `LargeDeflection = True` for any analysis with expected strains > 5%
- Use Direct solver for nonlinear problems (more robust convergence)
- Start with at least 10 initial substeps for nonlinear contact or material
- Enable Newton-Raphson line search for difficult convergence
- For contact problems, use Augmented Lagrange formulation (default)
"""


def get_guidelines_for_boundary_conditions() -> str:
    """Get boundary condition and load guidelines for Mechanical.

    Use this tool when applying supports, constraints, and loads.

    Returns
    -------
    str
        Guidelines for applying boundary conditions and loads in Mechanical.
    """
    return """# Boundary Conditions and Loads in Mechanical

## Supports (Constraints)

### Fixed Support

```python
script = '''
analysis = Model.Analyses[0]

# Add Fixed Support scoped to Named Selection (recommended)
fixed_support = analysis.AddFixedSupport()
ns = [n for n in Model.NamedSelections.Children if n.Name == "FixedFace"][0]
fixed_support.Location = ns
'''
mechanical.run_python_script(script)
```

### Displacement Constraint

```python
script = '''
analysis = Model.Analyses[0]

# Add Displacement
displacement = analysis.AddDisplacement()

# Set displacement values (use square brackets for units)
displacement.XComponent.Output.SetDiscreteValue(0, Quantity("0 [mm]"))
displacement.YComponent.Output.SetDiscreteValue(0, Quantity("0 [mm]"))
# Leave Z free (don't set it) for a partial constraint
'''
mechanical.run_python_script(script)
```

### Frictionless Support

```python
script = '''
analysis = Model.Analyses[0]
frictionless = analysis.AddFrictionlessSupport()
'''
mechanical.run_python_script(script)
```

## Loads

### Force

```python
script = '''
analysis = Model.Analyses[0]

# Add Force scoped to Named Selection
force = analysis.AddForce()
ns = [n for n in Model.NamedSelections.Children if n.Name == "LoadFace"][0]
force.Location = ns

# Define force by components (use .Output.DiscreteValues list)
force.DefineBy = LoadDefineBy.Components
force.XComponent.Output.DiscreteValues = [Quantity("0 [N]")]
force.YComponent.Output.DiscreteValues = [Quantity("-1000 [N]")]
force.ZComponent.Output.DiscreteValues = [Quantity("0 [N]")]
'''
mechanical.run_python_script(script)
```

### Pressure

```python
script = '''
analysis = Model.Analyses[0]

# Add Pressure
pressure = analysis.AddPressure()
ns = [n for n in Model.NamedSelections.Children if n.Name == "PressureFace"][0]
pressure.Location = ns

# Set pressure value
pressure.Magnitude.Output.SetDiscreteValue(0, Quantity("1 [MPa]"))
'''
mechanical.run_python_script(script)
```

### Remote Force

```python
script = '''
analysis = Model.Analyses[0]

# Add Remote Force with remote point
remote_force = analysis.AddRemoteForce()
remote_force.Location = Model.RemotePoints.Children[0]  # scope to remote point
remote_force.DefineBy = LoadDefineBy.Components
remote_force.XComponent.Output.DiscreteValues = [Quantity("100 [N]")]
'''
mechanical.run_python_script(script)
```

## Thermal Loads

### Temperature

```python
script = '''
analysis = Model.Analyses[0]

# Add Temperature
temp = analysis.AddTemperature()
temp.Magnitude.Output.SetDiscreteValue(0, Quantity("100 [C]"))
'''
mechanical.run_python_script(script)
```

### Convection

```python
script = '''
analysis = Model.Analyses[0]

# Add Convection
convection = analysis.AddConvection()
convection.FilmCoefficient.Output.SetDiscreteValue(0, Quantity("10 [W m^-1 m^-1 C^-1]"))
convection.AmbientTemperature.Output.SetDiscreteValue(0, Quantity("22 [C]"))
'''
mechanical.run_python_script(script)
```

## Using Named Selections

Named Selections are the preferred way to scope loads and supports:

```python
script = '''
analysis = Model.Analyses[0]

# Get Named Selection by name (preferred pattern)
ns = [n for n in Model.NamedSelections.Children if n.Name == "FixedFace"][0]

# Apply to boundary condition
fixed_support = analysis.AddFixedSupport()
fixed_support.Location = ns
'''
mechanical.run_python_script(script)
```

## Important Notes

1. **Component values are read-only properties**: set values via:
   `force.YComponent.Output.DiscreteValues = [Quantity("-1000 [N]")]`
2. **Always scope BCs to Named Selections** for reliability and reproducibility
3. **Ensure BCs prevent rigid-body motion**: at least 6 DOF must be constrained
4. **Use square brackets in Quantity units**: `Quantity("5 [mm]")` not `Quantity("5 mm")`
"""


def get_guidelines_for_solution() -> str:
    """Get solution phase guidelines for Mechanical.

    Use this tool when running solutions in Mechanical.

    Returns
    -------
    str
        Guidelines for solving analyses in Mechanical.
    """
    return """# Solution Phase in Mechanical

## Running the Solution

```python
script = '''
# Get the analysis
analysis = Model.Analyses[0]

# Solve
analysis.Solve()

# Check solution status
solution = analysis.Solution
print("Status: {0}".format(solution.Status))
'''
mechanical.run_python_script(script)
```

## Solution Object

```python
script = '''
solution = Model.Analyses[0].Solution

# Get solution information
print("Solver Type: {0}".format(solution.SolverType))
print("Status: {0}".format(solution.Status))
'''
mechanical.run_python_script(script)
```

## Handling Long Solutions

For long-running solutions, consider:

```python
script = '''
analysis = Model.Analyses[0]

# Start solve (returns immediately for monitoring)
analysis.Solve(True)  # True for background solve

# Check status
while analysis.Solution.Status == SolutionStatusType.Solving:
    # Wait and check periodically
    pass
'''
mechanical.run_python_script(script)
```

## Solution Output Controls

```python
script = '''
analysis = Model.Analyses[0]
settings = analysis.AnalysisSettings

# Control result output frequency
settings.ResultFileSettings.SaveResultsAtAllTimePoints = True
'''
mechanical.run_python_script(script)
```

## Convergence Issues

If the solution doesn't converge:
1. **Check mesh quality**: skewness > 0.95 or aspect ratio > 50 causes issues
2. **Verify boundary conditions**: model must be fully constrained (no rigid body motion)
3. **Review load magnitudes**: start with smaller loads and ramp up
4. **Enable Large Deflection**: `settings.LargeDeflection = True` for strains > 5%
5. **Increase substeps**: `settings.InitialSubsteps = 20` for nonlinear problems
6. **Use Direct solver**: `settings.SolverType = SolverType.Direct` for difficult convergence
7. **Check contact**: ensure initial penetration is zero, use Augmented Lagrange
8. **Review solve.out**: download and inspect for warnings/errors

## Solver Selection Guide

| Problem Type | Recommended Solver | Notes |
|---|---|---|
| Small model (< 100k nodes) | Direct | More robust, higher memory |
| Large model (> 500k nodes) | Iterative (PCG) | Faster, less memory |
| Nonlinear / Contact | Direct | Better convergence |
| Modal Analysis | Direct (default) | Block Lanczos |
| Ill-conditioned | Direct | PCG may not converge |

## Error Handling

```python
script = '''
try:
    analysis = Model.Analyses[0]
    analysis.Solve()

    if analysis.Solution.Status == SolutionStatusType.Done:
        print("Solution completed successfully")
    else:
        print("Solution status: {0}".format(analysis.Solution.Status))
except Exception as e:
    print("Solution error: {0}".format(e))
'''
mechanical.run_python_script(script)
```
"""


def get_guidelines_for_postprocessing() -> str:
    """Get postprocessing guidelines for Mechanical.

    Use this tool when extracting and visualizing results.

    Returns
    -------
    str
        Guidelines for postprocessing in Mechanical.
    """
    return """# Postprocessing in Mechanical

## Adding Result Objects

### Deformation Results

```python
script = '''
solution = Model.Analyses[0].Solution

# Total Deformation
total_deform = solution.AddTotalDeformation()

# Directional Deformation
dir_deform = solution.AddDirectionalDeformation()
dir_deform.NormalOrientation = NormalOrientationType.YAxis

# Evaluate results
total_deform.EvaluateAllResults()
'''
mechanical.run_python_script(script)
```

### Stress Results

```python
script = '''
solution = Model.Analyses[0].Solution

# Equivalent (von-Mises) Stress
equiv_stress = solution.AddEquivalentStress()

# Normal Stress
normal_stress = solution.AddNormalStress()
normal_stress.NormalOrientation = NormalOrientationType.XAxis

# Maximum Principal Stress
max_principal = solution.AddMaximumPrincipalStress()

# Evaluate
equiv_stress.EvaluateAllResults()
'''
mechanical.run_python_script(script)
```

### Strain Results

```python
script = '''
solution = Model.Analyses[0].Solution

# Equivalent Strain
equiv_strain = solution.AddEquivalentElasticStrain()

# Evaluate
equiv_strain.EvaluateAllResults()
'''
mechanical.run_python_script(script)
```

## Reading Result Values

```python
script = '''
solution = Model.Analyses[0].Solution

# Get stress result
stress = solution.AddEquivalentStress()
stress.EvaluateAllResults()

# Get min and max values
print("Maximum Stress: {0}".format(stress.Maximum))
print("Minimum Stress: {0}".format(stress.Minimum))
print("Average Stress: {0}".format(stress.Average))
'''
mechanical.run_python_script(script)
```

## Modal Analysis Results

```python
script = '''
solution = Model.Analyses[0].Solution

# Add Total Deformation for each mode
for i in range(1, 11):  # First 10 modes
    deform = solution.AddTotalDeformation()
    deform.Mode = i
    deform.EvaluateAllResults()
    print("Mode {0} Frequency: {1}".format(i, deform.ReportedFrequency))
'''
mechanical.run_python_script(script)
```

## Exporting Results

### Export to Image

```python
script = '''
# Get result object
stress = Model.Analyses[0].Solution.Children[0]

# Export image
Graphics.ExportImage(r"C:\\temp\\stress_result.png", GraphicsImageExportFormat.PNG)
'''
mechanical.run_python_script(script)
```

### Export Data to File

```python
script = '''
result = Model.Analyses[0].Solution.Children[0]

# Export to text file
result.ExportToTextFile(r"C:\\temp\\results.txt")
'''
mechanical.run_python_script(script)
```

## Result Scoping

```python
script = '''
solution = Model.Analyses[0].Solution

# Add result scoped to specific geometry
stress = solution.AddEquivalentStress()

# Scope to Named Selection
ns = ExtAPI.DataModel.GetObjectsByName("CriticalRegion")[0]
stress.Location = ns

stress.EvaluateAllResults()
'''
mechanical.run_python_script(script)
```
"""


def get_guidelines_for_named_selections() -> str:
    """Get named selection guidelines for Mechanical.

    Use this tool when working with named selections.

    Returns
    -------
    str
        Guidelines for creating and using named selections in Mechanical.
    """
    return """# Named Selections in Mechanical

Named selections are the preferred way to define geometry scopes for loads,
supports, and results in Mechanical scripting.

## Creating named selections

### Worksheet-based (recommended for scripting)

```python
script = '''
# Create a named selection using worksheet criteria (location-based)
ns = Model.AddNamedSelection()
ns.ScopingMethod = GeometryDefineByType.Worksheet
worksheet = ns.GenerationCriteria

# Define criterion (e.g., faces at X = 0)
criterion = Ansys.ACT.Automation.Mechanical.NamedSelectionCriterion()
criterion.Active = True
criterion.Action = SelectionActionType.Add
criterion.EntityType = SelectionType.GeoFace
criterion.Criterion = SelectionCriterionType.LocationX
criterion.Operator = SelectionOperatorType.Equal
criterion.Value = Quantity("0 [mm]")
worksheet.Add(criterion)

ns.Generate()
ns.Name = "FixedEnd"
'''
mechanical.run_python_script(script)
```

### Available Criterion Types

- `SelectionCriterionType.LocationX/Y/Z`: filter by coordinate
- `SelectionCriterionType.Size`: filter by area/volume
- `SelectionCriterionType.Type`: filter by entity type
- `SelectionCriterionType.Name`: filter by CAD body name

### Available entity types

- `SelectionType.GeoFace`: faces
- `SelectionType.GeoEdge`: edges
- `SelectionType.GeoVertex`: vertices
- `SelectionType.GeoBody`: bodies

### Accessing existing named selections

```python
script = '''
# Get all named selections
named_selections = Model.NamedSelections.GetChildren(
    DataModelObjectCategory.NamedSelection, True
)

for ns in named_selections:
    print("Named selection: {0}".format(ns.Name))
'''
mechanical.run_python_script(script)
```

### Get named selection by name

```python
script = '''
# Preferred pattern: iterate Children (reliable)
ns = [n for n in Model.NamedSelections.Children if n.Name == "FixedEnd"][0]

# Alternative: ExtAPI lookup
ns = ExtAPI.DataModel.GetObjectsByName("FixedEnd")[0]
'''
mechanical.run_python_script(script)
```

## Use named selections

### With boundary conditions

```python
script = '''
analysis = Model.Analyses[0]

# Add fixed support scoped to named selection
fixed = analysis.AddFixedSupport()
ns = [n for n in Model.NamedSelections.Children if n.Name == "FixedEnd"][0]
fixed.Location = ns
'''
mechanical.run_python_script(script)
```

### With results

```python
script = '''
solution = Model.Analyses[0].Solution

# Add stress result scoped to named selection
stress = solution.AddEquivalentStress()
ns = [n for n in Model.NamedSelections.Children if n.Name == "CriticalArea"][0]
stress.Location = ns

stress.EvaluateAllResults()
'''
mechanical.run_python_script(script)
```

## Best Practices

1. Create named selections for frequently used geometry scopes.
2. Use descriptive names (such as "FixedSupport_Bottom" and "Load_TopFace").
3. Named selections persist across geometry updates (when possible).
4. Use named selections for parameterization and automation.
"""


def get_guidelines_for_general_rules() -> str:
    """Get general rules and best practices for Mechanical workflows.

    Use this tool when working with Mechanical simulations.

    Returns
    -------
    str
        General rules and best practices for Mechanical simulations.
    """
    return """# General Rules and Best Practices for PyMechanical

## Script execution pattern

Always use `mechanical.run_python_script()` to execute Mechanical scripts:

```python
script = '''
# Your Mechanical scripting code
result = ExtAPI.DataModel.Project.ProductVersion
result
'''
output = mechanical.run_python_script(script)
```

## Return values

The script returns the string value of the last executed statement:

```python
# Returns '5'
mechanical.run_python_script("2 + 3")

# Returns product version string
mechanical.run_python_script("ExtAPI.DataModel.Project.ProductVersion")

# Returns empty string for assignments
mechanical.run_python_script("x = 10")
```

## Using qantities

Mechanical uses the Quantity class for values with units.
**Always use square brackets** around the unit string:

```python
script = '''
# Force in Newtons
force = Quantity("1000 [N]")

# Length in millimeters
length = Quantity("100 [mm]")

# Pressure in MPa
pressure = Quantity("1 [MPa]")

# Temperature in Celsius
temp = Quantity("100 [C]")

# Angular velocity
omega = Quantity("10 [rad/s]")
'''
mechanical.run_python_script(script)
```

## IronPython compatibility for older Mechanical versions

Mechanical versions before 2026 R1 use **IronPython 2.7**. Do NOT use:
- f-strings (`f"value: {x}"`): use `.format()` instead
- walrus operator (`:=`)
- Type hints in scripts
- `pathlib.Path`: use `os.path` instead

```python
# WRONG (f-string):
# script = 'f"Result: {value}"'

# CORRECT (.format()):
script = '"Result: {0}".format(value)'
```

## Transaction for performance

Wrap multiple modifications in a transaction:

```python
script = '''
with Transaction():
    # Multiple operations here
    for obj in Tree.AllObjects:
        if hasattr(obj, 'Name'):
            obj.Name = obj.Name + "_modified"
'''
mechanical.run_python_script(script)
```

## Error handling

```python
try:
    result = mechanical.run_python_script(script)
except grpc.RpcError as error:
    print("Script error: {0}".format(error.details()))
```

## File transfers

Use upload and download for file operations:

```python
# Upload file to Mechanical
mechanical.upload("local_file.stp")

# Download results
mechanical.download("results.txt", target_dir="./output")

# Download entire project
mechanical.download_project(target_dir="./project_backup")
```

## Common pitfalls

- **Not checking connection status** before running scripts
- **Missing mesh generation** before solving
- **No boundary conditions** causing rigid body motion
- **Forgetting to evaluate results** after adding result objects
- **Path issues**: Use raw strings (r"path") or double backslashes
- **Using f-strings**: Mechanical versions before 2026 R1 use IronPython 2.7
    (no f-strings)
- **Wrong Quantity format**: Use `Quantity("5 [mm]")` with square brackets
- **Setting component values directly**: Use `.Output.DiscreteValues = [...]`

## Verification steps

1. Check model setup: geometry, materials, and mesh.
2. Verify boundary conditions prevent rigid body motion.
3. Review solver messages for warnings.
4. Validate results against expected behavior.
5. Check mesh convergence for critical results.
6. Compare stress results against material yield strength.
"""


_CONTENT_MAP = {
    "workflow": get_guidelines_for_workflow_overview,
    "geometry": get_guidelines_for_geometry_import,
    "materials": get_guidelines_for_materials,
    "meshing": get_guidelines_for_meshing,
    "analysis_setup": get_guidelines_for_analysis_setup,
    "boundary_conditions": get_guidelines_for_boundary_conditions,
    "solution": get_guidelines_for_solution,
    "postprocessing": get_guidelines_for_postprocessing,
    "named_selections": get_guidelines_for_named_selections,
    "general": get_guidelines_for_general_rules,
}


@app.tool()
def get_guidelines_for(content: GuidelinesContent) -> str:
    """Get Mechanical simulation guidelines for a specific topic.

    Use this tool before writing PyMechanical or Ansys Mechanical scripting
    code to retrieve the relevant guidelines for the workflow step you are
    about to implement. Call it once per topic needed. You should call it
    before every code-generation task.

    Parameters
    ----------
    content : str
        The guideline topic to retrieve. options are:

        - ``"workflow"``: Mechanical simulation workflow overview.
        - ``"geometry"``: Geometry import (CAD files, units, and scoping).
        - ``"materials"``: Material assignment and engineering data.
        - ``"meshing"``: Mesh controls, sizing, and quality.
        - ``"analysis_setup"``: Analysis system creation
          (such as static structural, modal, or thermal).
        - ``"boundary_conditions"``: Supports, constraints, loads
          (forces, pressures, and temperatures).
        - ``"solution"``: Solver configuration and execution.
        - ``"postprocessing"``: Result objects, evaluation, and exports.
        - ``"named_selections"``: Creating and using named selections.
        - ``"general"``: General Mechanical rules and best practices.

    Returns
    -------
    str
        Guideline text for the requested topic.
    """
    return _CONTENT_MAP[content]()
