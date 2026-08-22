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

"""Context tools for PyAEDT-MCP.

This module defines MCP tools that provide context and guidance for
PyAEDT and Ansys Electronics Desktop (AEDT) workflows. These tools return
context information that can be accessed by the LLM to get help with various
aspects of electromagnetic and thermal simulations.
"""

# flake8: noqa: E501

from typing import Literal

from ansys.aedt.mcp import app

GuidelinesContent = Literal[
    "workflow",
    "hfss",
    "maxwell",
    "icepak",
    "circuit",
    "geometry",
    "mesh",
    "boundaries",
    "postprocessing",
    "parametric",
]


def get_guidelines_for_workflow_overview() -> str:
    """Get general AEDT simulation workflow guidelines.

    Use this tool when explaining or generating PyAEDT or AEDT workflows.

    Returns
    -------
    str
        Overview of the general simulation process for all AEDT analysis types.
    """
    return """# AEDT Simulation Workflow Overview

When explaining or generating PyAEDT or AEDT workflows, always follow this general simulation process.

## PyAEDT Architecture

PyAEDT is a Python library that provides direct access to AEDT via:

- **COM/Desktop API**: Direct connection to an AEDT instance
- **gRPC API** (2022 R2+): Remote connection via a gRPC server

For MCP server, both local and remote gRPC connections are supported.

## AEDT applications

AEDT includes multiple physics solvers:

- **HFSS**: High-frequency electromagnetic simulation (RF, microwave, antennas)
- **Maxwell 2D/3D**: Low-frequency electromagnetic simulation (motors, transformers)
- **Q3D/Q2D**: Parasitic extraction (capacitance, inductance, resistance)
- **Icepak**: Thermal management and CFD analysis
- **Circuit**: Circuit-level simulation
- **TwinBuilder**: System-level modeling
- **EMIT**: EMI/EMC analysis
- **Mechanical**: Structural analysis within AEDT

## General workflow steps

1. **Environment setup**
   - Launch or connect to AEDT.
   - Configure project settings.

2. **Preprocessing**
   - Create or open a project.
   - Create a design (application-specific).
   - Import or create geometry.
   - Define materials and assign to bodies.
   - Set up mesh operations.

3. **Analysis setup**
   - Create analysis setup (such as frequency or transient).
   - Apply boundary conditions.
   - Apply excitations/sources.
   - Configure parametric sweeps if needed.

4. **Solution**
   - Validate design.
   - Run simulation.
   - Monitor progress.

5. **Postprocessing**
   - Create reports (such as S-parameters and fields).
   - Export results.
   - Generate images/animations.

## Code Pattern

```python
from ansys.aedt.core import Hfss, Desktop

# Launch or connect to AEDT (omit ``version`` to use the latest installed AEDT version)
desktop = Desktop(non_graphical=True)

# Create an application — ALWAYS pass port=desktop.port to reuse the same AEDT instance
hfss = Hfss(project="MyProject", design="MyDesign", port=desktop.port)

# Create geometry
box = hfss.modeler.create_box([0, 0, 0], [10, 10, 2], name="Substrate", material="FR4_epoxy")

# Assign boundary conditions
hfss.assign_radiation_boundary_to_objects("AirBox")

# Create setup and analyze
setup = hfss.create_setup("Setup1")
hfss.analyze()

# Export results
hfss.export_touchstone()
```

## gRPC connection (remote)

For remote connections, AEDT must be started in gRPC server mode:
```bash
ansysedt.exe -grpcsrv 50051
```

Then connect via PyAEDT:
```python
from ansys.aedt.core import Hfss
from ansys.aedt.core.generic.settings import settings

settings.use_grpc_api = True
hfss = Hfss(machine="remote_server", port=50051)
```
"""


def get_guidelines_for_hfss() -> str:
    """Get HFSS-specific workflow guidelines.

    Use this tool when explaining or generating HFSS simulations.

    Returns
    -------
    str
        Guidelines for HFSS high-frequency electromagnetic simulations.
    """
    return """# HFSS Simulation Guidelines

HFSS (High Frequency Structure Simulator) is used for high-frequency electromagnetic simulations including antennas, RF circuits, and microwave components.

## Solution types

- **Modal**: Port-based network analysis (S-parameters)
- **Terminal**: Circuit-based terminal solutions
- **Transient**: Time-domain simulations
- **Eigenmode**: Resonant cavity analysis
- **SBR+**: Shooting and bouncing rays for large structures

## Common workflow

```python
from ansys.aedt.core import Hfss

# Create HFSS design — ALWAYS pass port=desktop.port to reuse the launched AEDT instance
hfss = Hfss(project="Antenna", design="PatchAntenna", solution_type="Modal", port=desktop.port)

# Set units
hfss.modeler.model_units = "mm"

# Create geometry
substrate = hfss.modeler.create_box(
    origin=[0, 0, 0],
    sizes=[40, 30, 1.6],
    name="Substrate",
    material="FR4_epoxy"
)

patch = hfss.modeler.create_rectangle(
    cs_plane="XY",
    position=[5, 5, 1.6],
    dimension_list=[30, 20],
    name="Patch"
)

# Assign copper to patch
hfss.assign_perfecte_to_sheets(patch.name)

# Create ground plane
ground = hfss.modeler.create_rectangle(
    cs_plane="XY",
    position=[0, 0, 0],
    dimension_list=[40, 30],
    name="Ground"
)
hfss.assign_perfecte_to_sheets(ground.name)

# Create airbox
airbox = hfss.modeler.create_box(
    origin=[-10, -10, -5],
    sizes=[60, 50, 30],
    name="AirBox",
    material="vacuum"
)

# Assign radiation boundary
hfss.assign_radiation_boundary_to_objects("AirBox")

# Create lumped port
hfss.lumped_port(
    assignment="Port1_Face",
    reference="Ground",
    name="Port1",
    impedance=50
)

# Create frequency sweep setup
setup = hfss.create_setup("Setup1")
setup.props["Frequency"] = "2.4GHz"

# Add frequency sweep
hfss.create_linear_count_sweep(
    setup="Setup1",
    unit="GHz",
    start_frequency=1,
    stop_frequency=4,
    num_of_freq_points=101
)

# Analyze
hfss.analyze()

# Export S-parameters
hfss.export_touchstone(output_file="antenna.s1p")
```

## Key HFSS methods

- `hfss.modeler.create_box()` - Create 3D box
- `hfss.modeler.create_cylinder()` - Create cylinder
- `hfss.modeler.create_rectangle()` - Create 2D rectangle
- `hfss.wave_port()` - Create wave port
- `hfss.lumped_port()` - Create lumped port
- `hfss.assign_radiation_boundary_to_objects()` - Radiation boundary
- `hfss.assign_perfecte_to_sheets()` - Perfect E (PEC)
- `hfss.create_setup()` - Create analysis setup
- `hfss.create_linear_count_sweep()` - Frequency sweep
- `hfss.analyze()` - Run simulation
- `hfss.export_touchstone()` - Export S-parameters

## Postprocessing

```python
# Create S-parameter report
hfss.post.create_report(
    expressions="dB(S(Port1,Port1))",
    setup_sweep_name="Setup1 : Sweep1"
)

# Get far-field data
hfss.post.create_report(
    expressions="GainTotal",
    primary_sweep_variable="Theta",
    context="Far Field"
)

# Export field plot image
hfss.post.export_field_jpg(
    quantity="E",
    setup_name="Setup1",
    output_file="efield.jpg"
)
```
"""


def get_guidelines_for_maxwell() -> str:
    """Get Maxwell 2D/3D workflow guidelines.

    Use this tool when explaining or generating Maxwell simulations.

    Returns
    -------
    str
        Guidelines for Maxwell electromagnetic simulations.
    """
    return """# Maxwell 2D/3D Simulation Guidelines

Maxwell is used for low-frequency electromagnetic simulations including electric machines, transformers, actuators, and sensors.

## Solution types

### Maxwell 3D
- **Magnetostatic**: DC magnetic fields
- **Electrostatic**: DC electric fields
- **EddyCurrent**: AC magnetic with eddy currents
- **Transient**: Time-varying fields
- **ElectroDCConduction**: DC current flow
- **ACConduction**: AC current flow

### Maxwell 2D
- **MagnetostaticXY/RZ**: 2D magnetostatic
- **TransientXY/RZ**: 2D transient
- **EddyCurrentXY/RZ**: 2D eddy current
- **ElectrostaticXY/RZ**: 2D electrostatic

## Common workflow - electric motor

```python
from ansys.aedt.core import Maxwell3d

# Create Maxwell 3D design — ALWAYS pass port=desktop.port to reuse the launched AEDT instance
m3d = Maxwell3d(
    project="Motor",
    design="IPM_Motor",
    solution_type="Transient",
    port=desktop.port
)

# Set units
m3d.modeler.model_units = "mm"

# Create rotor core
rotor = m3d.modeler.create_cylinder(
    cs_axis="Z",
    position=[0, 0, 0],
    radius=25,
    height=50,
    name="Rotor",
    material="steel_1008"
)

# Create magnets
magnet1 = m3d.modeler.create_box(
    origin=[15, -5, 0],
    sizes=[8, 10, 50],
    name="Magnet_N",
    material="N42"
)

# Assign magnetization direction
m3d.assign_material(magnet1, "N42")

# Create stator
stator = m3d.modeler.create_cylinder(
    cs_axis="Z",
    position=[0, 0, 0],
    radius=55,
    height=50,
    name="Stator",
    material="steel_1008"
)

# Create coils and assign windings
coil = m3d.modeler.create_box(
    origin=[30, -3, 0],
    sizes=[10, 6, 50],
    name="Coil_A"
)

# Assign winding excitation
m3d.assign_winding(
    assignment="Coil_A",
    winding_type="Current",
    current_value="10A"
)

# Create air region
region = m3d.modeler.create_region([100, 100, 50, 50, 50, 50])

# Assign rotation motion to rotor
m3d.assign_rotate_motion(
    assignment="Rotor",
    axis="Z",
    positive_movement=True,
    start_position=0,
    angular_velocity="1500rpm"
)

# Create setup
setup = m3d.create_setup("Setup1")
setup.props["StopTime"] = "20ms"
setup.props["TimeStep"] = "0.1ms"

# Assign force/torque calculation
m3d.assign_torque("Rotor", torque_axis="Z", name="Torque")

# Assign matrix for inductance
m3d.assign_matrix(sources=["Coil_A", "Coil_B", "Coil_C"])

# Analyze
m3d.analyze()
```

## Key Maxwell methods

- `m3d.assign_coil()`: Assign coil to objects.
- `m3d.assign_winding()`: Create winding excitation.
- `m3d.assign_current()`: Assign current source.
- `m3d.assign_voltage()`: Assign voltage source.
- `m3d.assign_torque()`: Calculate torque.
- `m3d.assign_force()`: Calculate force.
- `m3d.assign_rotate_motion()`: Assign rotational motion.
- `m3d.assign_translate_motion()`: Assign linear motion.
- `m3d.assign_matrix()`: Assign inductance/capacitance matrix.
- `m3d.eddy_effects_on()`: Enable eddy currents.
- `m3d.set_core_losses()`: Enable core loss calculation.

## Postprocessing

```python
# Get torque vs time
m3d.post.create_report(
    expressions="Torque.Torque",
    primary_sweep_variable="Time"
)

# Export inductance matrix
m3d.export_matrix(
    matrix_name="Matrix1",
    output_file="inductance.csv"
)

# Plot B-field
m3d.post.plot_field(
    quantity="Mag_B",
    objects_list=["Rotor", "Stator"]
)
```
"""


def get_guidelines_for_icepak() -> str:
    """Get Icepak thermal analysis guidelines.

    Use this tool when explaining or generating Icepak thermal simulations.

    Returns
    -------
    str
        Guidelines for Icepak thermal management simulations.
    """
    return """# Icepak Thermal Simulation Guidelines

Icepak is used for thermal management and CFD analysis of electronic systems.

## Solution Types

- **SteadyState** - Steady-state thermal analysis
- **Transient** - Time-dependent thermal analysis

## Common Workflow - Electronics Cooling

```python
from ansys.aedt.core import Icepak

# Create Icepak design — ALWAYS pass port=desktop.port to reuse the launched AEDT instance
ipk = Icepak(
    project="PCB_Cooling",
    design="ThermalAnalysis",
    solution_type="SteadyState",
    port=desktop.port
)

# Set units
ipk.modeler.model_units = "mm"

# Create PCB
pcb = ipk.modeler.create_box(
    origin=[0, 0, 0],
    sizes=[100, 80, 1.6],
    name="PCB",
    material="FR4_epoxy"
)

# Create IC package
ic = ipk.modeler.create_box(
    origin=[30, 30, 1.6],
    sizes=[20, 20, 3],
    name="IC_Package",
    material="Ceramic_material"
)

# Create heat source (die)
die = ipk.modeler.create_box(
    origin=[35, 35, 4.6],
    sizes=[10, 10, 0.5],
    name="Die",
    material="Silicon"
)

# Assign power dissipation
ipk.assign_solid_block(
    assignment="Die",
    power_assignment="5W",
    boundary_name="Die_Heat"
)

# Create heatsink
heatsink_base = ipk.modeler.create_box(
    origin=[25, 25, 5.1],
    sizes=[30, 30, 2],
    name="Heatsink_Base",
    material="Al-Extruded"
)

# Create heatsink fins
for i in range(5):
    fin = ipk.modeler.create_box(
        origin=[25, 25 + i*6, 7.1],
        sizes=[30, 2, 15],
        name=f"Fin_{i}",
        material="Al-Extruded"
    )

# Create enclosure with inlet/outlet
enclosure = ipk.modeler.create_box(
    origin=[-10, -10, -10],
    sizes=[120, 100, 50],
    name="Enclosure"
)

# Assign opening (inlet)
inlet_face = ipk.modeler.get_face_by_position([-10, 40, 15])
ipk.assign_opening(
    assignment=inlet_face,
    temperature="25degC",
    flow_type="Velocity",
    velocity_magnitude="1m_per_sec"
)

# Assign opening (outlet)
outlet_face = ipk.modeler.get_face_by_position([110, 40, 15])
ipk.assign_opening(
    assignment=outlet_face,
    flow_type="Pressure"
)

# Create setup
setup = ipk.create_setup("Setup1")
setup.props["Convergence Criteria - Flow"] = 0.001
setup.props["Convergence Criteria - Energy"] = 1e-7

# Assign mesh settings
ipk.mesh.assign_mesh_level(mesh_level=3)

# Analyze
ipk.analyze()
```

## Key Icepak Methods

- `ipk.assign_solid_block()` - Heat source
- `ipk.assign_surface_monitor()` - Monitor surface temperature
- `ipk.assign_opening()` - Inlet/outlet boundary
- `ipk.assign_grille()` - Grille boundary
- `ipk.assign_fan()` - Fan model
- `ipk.assign_blower()` - Blower model
- `ipk.assign_duct()` - Duct model
- `ipk.assign_radiation_boundary()` - Radiation boundary
- `ipk.mesh.assign_mesh_level()` - Global mesh level
- `ipk.mesh.assign_mesh_region()` - Local mesh refinement

## Post-Processing

```python
# Get temperature contours
ipk.post.create_fieldplot_surface(
    objects_list=["Die", "Heatsink_Base"],
    quantity="Temperature"
)

# Create temperature report
ipk.post.create_report(
    expressions="Temperature",
    variations={"Point": ["Die_center"]}
)

# Export temperature data
ipk.export_summary(output_file="thermal_summary.csv")

# Get max temperature
max_temp = ipk.post.get_solution_data(
    expression="MaximumTemperature(Die)"
)
```
"""


def get_guidelines_for_circuit() -> str:
    """Get Circuit simulation guidelines.

    Use this tool when explaining or generating Circuit simulations.

    Returns
    -------
    str
        Guidelines for Circuit and system-level simulations.
    """
    return """# Circuit Simulation Guidelines

Circuit Design is used for circuit-level simulations, system integration, and co-simulation with 3D field solvers.

## Key Capabilities

- Linear/nonlinear circuit analysis
- Transient analysis
- AC/DC analysis
- S-parameter network analysis
- Co-simulation with HFSS, Maxwell, Q3D
- Touchstone file import

## Common Workflow

```python
from ansys.aedt.core import Circuit

# Create Circuit design — ALWAYS pass port=desktop.port to reuse the launched AEDT instance
cir = Circuit(
    project="Filter",
    design="LPF",
    port=desktop.port
)

# Create schematic components
# Resistor
r1 = cir.modeler.schematic.create_resistor(
    value="50ohm",
    location=[0, 0],
    name="R1"
)

# Capacitor
c1 = cir.modeler.schematic.create_capacitor(
    value="10pF",
    location=[1, 0],
    name="C1"
)

# Inductor
l1 = cir.modeler.schematic.create_inductor(
    value="5nH",
    location=[2, 0],
    name="L1"
)

# Create ports
port1 = cir.modeler.schematic.create_interface_port(
    name="Port1",
    location=[-1, 0]
)
port2 = cir.modeler.schematic.create_interface_port(
    name="Port2",
    location=[3, 0]
)

# Connect components
cir.modeler.schematic.create_wire([[0, 0], [1, 0]])
cir.modeler.schematic.create_wire([[1, 0], [2, 0]])

# Import Touchstone file (e.g., from HFSS)
snp = cir.modeler.schematic.create_touchstone_component(
    touchstone_file="antenna.s1p",
    location=[4, 0],
    name="Antenna"
)

# Create linear network analysis setup
setup = cir.create_setup("LinearSetup", setup_type="NexximLNA")
setup.props["SweepDefinition"]["Start"] = "1MHz"
setup.props["SweepDefinition"]["Stop"] = "10GHz"
setup.props["SweepDefinition"]["Points"] = 1001

# Analyze
cir.analyze()

# Export results
cir.export_touchstone("filter_output.s2p", setup_name="LinearSetup")
```

## Co-Simulation with HFSS

```python
from ansys.aedt.core import Circuit, Hfss

# Create HFSS design first — ALWAYS pass port=desktop.port
hfss = Hfss(project="System", design="Antenna3D", port=desktop.port)
# ... create 3D model ...
hfss.analyze()

# Create Circuit design in same project
cir = Circuit(project="System", design="MatchingNetwork", port=desktop.port)

# Import HFSS design as dynamic link
cir.modeler.schematic.add_subcircuit_dynamic_link(
    design_name="Antenna3D",
    location=[0, 0]
)

# Add matching network components around it
# ...
```

## Key Circuit Methods

- `cir.modeler.schematic.create_resistor()` - Add resistor
- `cir.modeler.schematic.create_capacitor()` - Add capacitor
- `cir.modeler.schematic.create_inductor()` - Add inductor
- `cir.modeler.schematic.create_touchstone_component()` - Import S-parameters
- `cir.modeler.schematic.create_interface_port()` - Create port
- `cir.modeler.schematic.create_wire()` - Connect components
- `cir.create_setup()` - Create analysis setup
- `cir.analyze()` - Run simulation
- `cir.export_touchstone()` - Export results

## Post-Processing

```python
# Get S-parameters
s21 = cir.post.get_solution_data(
    expressions="dB(S(Port1,Port2))",
    setup_sweep_name="LinearSetup"
)

# Create report
cir.post.create_report(
    expressions=["dB(S(1,1))", "dB(S(2,1))"],
    setup_sweep_name="LinearSetup"
)
```
"""


def get_guidelines_for_geometry() -> str:
    """Get geometry creation guidelines for AEDT.

    Use this tool when explaining or generating geometry operations.

    Returns
    -------
    str
        Guidelines for creating and manipulating geometry in AEDT.
    """
    return """# Geometry Creation Guidelines in AEDT

All AEDT applications share a common modeler API for 3D geometry creation.

## Basic Primitives

```python
# Access modeler from any application
modeler = app.modeler

# Create box
box = modeler.create_box(
    origin=[0, 0, 0],          # Origin point [x, y, z]
    sizes=[10, 5, 2],          # Dimensions [dx, dy, dz]
    name="MyBox",
    material="copper"
)

# Create cylinder
cylinder = modeler.create_cylinder(
    cs_axis="Z",               # Axis of cylinder (X, Y, or Z)
    position=[0, 0, 0],        # Base center position
    radius=5,
    height=10,
    name="MyCylinder",
    material="aluminum"
)

# Create sphere
sphere = modeler.create_sphere(
    position=[0, 0, 0],        # Center position
    radius=5,
    name="MySphere"
)

# Create cone
cone = modeler.create_cone(
    cs_axis="Z",
    position=[0, 0, 0],
    bottom_radius=5,
    top_radius=2,
    height=10,
    name="MyCone"
)

# Create torus
torus = modeler.create_torus(
    cs_axis="Z",
    center=[0, 0, 0],
    major_radius=10,
    minor_radius=2,
    name="MyTorus"
)
```

## 2D Primitives

```python
# Create rectangle
rect = modeler.create_rectangle(
    cs_plane="XY",             # Plane (XY, XZ, YZ)
    position=[0, 0, 0],        # Corner position
    dimension_list=[10, 5],    # Width, height
    name="MyRect"
)

# Create circle
circle = modeler.create_circle(
    cs_plane="XY",
    position=[0, 0, 0],        # Center position
    radius=5,
    name="MyCircle"
)

# Create polyline
polyline = modeler.create_polyline(
    points=[[0, 0, 0], [10, 0, 0], [10, 10, 0], [0, 10, 0]],
    close_surface=True,        # Close the polyline
    name="MyPolyline"
)

# Create ellipse
ellipse = modeler.create_ellipse(
    cs_plane="XY",
    position=[0, 0, 0],
    major_radius=10,
    ratio=0.5,
    name="MyEllipse"
)
```

## Boolean Operations

```python
# Unite objects
modeler.unite([obj1, obj2])

# Subtract objects (obj1 = obj1 - obj2)
modeler.subtract(blank_list=[obj1], tool_list=[obj2])

# Intersect objects
modeler.intersect([obj1, obj2])

# Split object by plane
modeler.split(assignment=obj1, plane="XY")
```

## Transformations

```python
# Move object
modeler.move(assignment=obj, vector=[10, 0, 0])

# Rotate object
modeler.rotate(
    assignment=obj,
    cs_axis="Z",
    angle=45
)

# Mirror object
modeler.mirror(
    assignment=obj,
    position=[0, 0, 0],
    vector=[1, 0, 0]
)

# Scale object
modeler.scale(
    assignment=obj,
    scale_factor=2
)

# Duplicate along vector
new_objs = modeler.duplicate_along_line(
    assignment=obj,
    vector=[10, 0, 0],
    num_clones=5
)

# Duplicate and mirror
modeler.duplicate_and_mirror(
    assignment=obj,
    position=[0, 0, 0],
    vector=[1, 0, 0]
)
```

## Import CAD

```python
# Import STEP file
modeler.import_3d_cad(
    input_file="model.stp",
    healing=True,
    refresh_all_ids=True
)

# Import DXF (2D)
modeler.import_dxf(
    input_file="drawing.dxf",
    layers=["Layer1", "Layer2"]
)
```

## Working with Faces and Edges

```python
# Get face by position
face = modeler.get_face_by_position([5, 2.5, 2])

# Get all faces of object
faces = obj.faces

# Get edges
edges = obj.edges

# Get vertices
vertices = obj.vertices

# Create face list
face_list = modeler.get_faceid_from_position([0, 0, 1])
```

## Material Assignment

```python
# Assign existing material
modeler.assign_material(obj, "copper")

# Create custom material
mat = app.materials.add_material("MyMaterial")
mat.permittivity = 4.4
mat.conductivity = 5.8e7
mat.permeability = 1.0

# Assign custom material
modeler.assign_material(obj, "MyMaterial")
```
"""


def get_guidelines_for_mesh() -> str:
    """Get mesh setup guidelines for AEDT.

    Use this tool when explaining or generating mesh operations.

    Returns
    -------
    str
        Guidelines for mesh settings and operations in AEDT.
    """
    return """# Mesh Setup Guidelines in AEDT

Each AEDT application has specific mesh controls. HFSS uses adaptive meshing, while Icepak uses explicit mesh settings.

## HFSS Mesh Operations

```python
# Access mesh object
mesh = hfss.mesh

# Create mesh operation on object
mesh.assign_length_mesh(
    assignment=["MyBox"],
    inside_selection=True,
    maximum_length="1mm",
    maximum_elements=1000,
    name="LengthMesh1"
)

# Assign surface approximation
mesh.assign_surface_mesh(
    assignment=["CurvedSurface"],
    surface_deviation="0.1mm",
    normal_deviation="10deg",
    name="SurfMesh1"
)

# Assign curvature-based mesh
mesh.assign_curvature_extraction(
    assignment=["MyObject"],
    curvature_ratio=0.1
)

# Model resolution mesh operation
mesh.assign_model_resolution(
    assignment=["SmallFeature"],
    model_resolution=0.2
)

# Skin depth mesh for conductors
mesh.assign_skin_depth(
    assignment=["Conductor"],
    skin_depth="2um",
    maximum_elements=10000
)
```

## Maxwell Mesh Operations

```python
# Access mesh object
mesh = m3d.mesh

# Assign length-based mesh
mesh.assign_length_mesh(
    assignment=["Coil"],
    inside_selection=True,
    maximum_length="5mm"
)

# Assign surface approximation
mesh.assign_surface_mesh(
    assignment=["Rotor"],
    surface_deviation="0.5mm"
)

# Rotational symmetry mesh link
mesh.assign_rotational_layer(
    assignment=["Rotor"],
    total_layers=4
)

# TAU mesh for large structures
mesh.assign_tau_mesh(
    assignment=["AirGap"],
    number_of_layers=5
)
```

## Icepak Mesh Settings

```python
# Access mesh object
mesh = ipk.mesh

# Set global mesh level (1-5)
mesh.assign_mesh_level(mesh_level=3)

# Assign mesh region for local refinement
mesh.assign_mesh_region(
    assignment=["Die"],
    level=5,
    padding=[2, 2, 2, 2, 2, 2]
)

# Mesh settings for specific component
mesh.assign_mesh_to_component(
    component_name="IC",
    level=4
)

# Create mesh operation
mesh.assign_priority_mesh(
    assignment=["SmallFeature"],
    element_size="0.5mm"
)

# Generate mesh
mesh.generate_mesh()
```

## Q3D/Q2D Mesh Operations

```python
# Access mesh object
mesh = q3d.mesh

# Assign length-based mesh
mesh.assign_length_mesh(
    assignment=["Net1"],
    maximum_length="0.1mm"
)

# Skin depth for conductors
mesh.assign_skin_depth(
    assignment=["Signal"],
    skin_depth="1um"
)
```

## Mesh Quality Check

```python
# Get mesh statistics
stats = app.mesh.get_statistics()

# Print mesh info
print(f"Number of elements: {stats['Elements']}")
print(f"Minimum quality: {stats['Min Quality']}")

# Export mesh
app.mesh.export_mesh("mesh.msh")
```

## Adaptive Mesh Refinement (HFSS)

```python
# Configure adaptive mesh in setup
setup = hfss.create_setup("Setup1")
setup.props["MaximumPasses"] = 15
setup.props["MaxDeltaS"] = 0.02
setup.props["MinimumPasses"] = 2
setup.props["MinimumConvergedPasses"] = 2

# Enable broadband adaptive meshing
setup.props["UseAdaptiveSettings"] = True
setup.props["BroadbandMeshing"] = True
setup.props["BroadbandFrequencyRange"] = ["1GHz", "10GHz"]
```
"""


def get_guidelines_for_boundaries() -> str:
    """Get boundary and excitation guidelines for AEDT.

    Use this tool when explaining or generating boundary conditions.

    Returns
    -------
    str
        Guidelines for boundary conditions and excitations in AEDT.
    """
    return """# Boundary and Excitation Guidelines in AEDT

Each AEDT application has specific boundary conditions and excitation types.

## HFSS Boundaries

```python
# Radiation boundary (far-field analysis)
hfss.assign_radiation_boundary_to_objects("AirBox")

# PEC (Perfect Electric Conductor)
hfss.assign_perfecte_to_sheets("Ground")

# PMC (Perfect Magnetic Conductor)
hfss.assign_perfecth_to_sheets("Symmetry_Plane")

# Impedance boundary
hfss.assign_impedance_to_sheet(
    assignment="Surface",
    resistance=50,
    reactance=0,
    name="Impedance1"
)

# Finite conductivity
hfss.assign_finite_conductivity(
    assignment="Metal",
    conductivity=5.8e7,
    name="FiniteCond1"
)

# Symmetry boundary
hfss.assign_symmetry(
    assignment=["SymmetryFace"],
    symmetry_type="Perfect E",
    name="Sym1"
)
```

## HFSS Excitations

```python
# Wave port
hfss.wave_port(
    assignment="PortFace",
    reference="Ground",
    name="Port1",
    num_modes=1
)

# Lumped port
hfss.lumped_port(
    assignment="PortFace",
    reference="Ground",
    name="Port1",
    impedance=50
)

# Circuit port
hfss.circuit_port(
    assignment="Object1",
    reference="Object2",
    name="CircPort1"
)

# Plane wave excitation
hfss.plane_wave(
    assignment="PlaneWave1",
    vector_format="Spherical",
    theta=0,
    phi=0,
    polarization="Vertical"
)

# Voltage source
hfss.assign_voltage_source_to_sheet(
    assignment="SourceFace",
    name="VSrc1"
)

# Current source
hfss.assign_current_source_to_sheet(
    assignment="SourceFace",
    current_value="1A"
)
```

## Maxwell Boundaries

```python
# Symmetry boundary
m3d.assign_symmetry(
    assignment=["SymFace"],
    symmetry_type="Odd",
    name="Symmetry1"
)

# Insulating boundary
m3d.assign_insulating(
    assignment=["Surface"],
    name="Insulating1"
)

# Master/Slave (periodic)
m3d.assign_master_slave(
    independent=["Face1"],
    dependent=["Face2"],
    name="MasterSlave1"
)

# Zero tangential H field
m3d.assign_zero_tangential_h_field(
    assignment=["Face"],
    name="ZeroH"
)

# Radiation boundary
m3d.assign_radiation(
    assignment=["OuterSurface"],
    name="Radiation1"
)
```

## Maxwell Excitations

```python
# Current excitation
m3d.assign_current(
    assignment=["Conductor"],
    amplitude="10A",
    name="Current1"
)

# Voltage excitation
m3d.assign_voltage(
    assignment=["Conductor"],
    amplitude="100V",
    name="Voltage1"
)

# Winding (coil group)
m3d.assign_winding(
    assignment=["Coil1", "Coil2"],
    winding_type="Current",
    current_value="5A",
    name="Winding_A"
)

# External circuit
m3d.assign_winding(
    assignment=["Coil"],
    winding_type="External",
    name="ExternalWinding"
)

# Permanent magnet
m3d.assign_material(obj, "N42")
# Magnetization direction is set by coordinate system
```

## Icepak Boundaries

```python
# Opening (inlet/outlet)
ipk.assign_opening(
    assignment=face_id,
    temperature="25degC",
    flow_type="Velocity",
    velocity_magnitude="1m_per_sec"
)

# Pressure opening
ipk.assign_opening(
    assignment=face_id,
    flow_type="Pressure",
    total_pressure="0Pa"
)

# Wall boundary
ipk.assign_wall(
    assignment=face_id,
    wall_type="Heat Flux",
    heat_flux="100W/m2"
)

# Fixed temperature
ipk.assign_wall(
    assignment=face_id,
    wall_type="Temperature",
    temperature="85degC"
)

# Symmetry
ipk.assign_symmetry(
    assignment=face_id,
    name="Symmetry1"
)
```

## Icepak Sources

```python
# Solid block heat source
ipk.assign_solid_block(
    assignment="Component",
    power_assignment="5W",
    boundary_name="HeatSource1"
)

# Network block (junction-case model)
ipk.create_network_block(
    component_name="IC",
    power="10W",
    rjc=0.5,
    rjb=2.0
)

# Surface heat source
ipk.assign_surface_heat(
    assignment=face_id,
    heat_value="10W",
    name="SurfaceHeat1"
)

# Fan
ipk.assign_fan(
    assignment=face_id,
    flow_rate="0.01m3_per_sec",
    name="Fan1"
)
```
"""


def get_guidelines_for_postprocessing() -> str:
    """Get postprocessing guidelines for AEDT.

    Use this tool when explaining or generating postprocessing operations.

    Returns
    -------
    str
        Guidelines for postprocessing and results export in AEDT.
    """
    return """# Postprocessing Guidelines in AEDT

AEDT provides comprehensive postprocessing capabilities for all simulation types.

## HFSS Post-Processing

```python
# Access post-processor
post = hfss.post

# Create S-parameter report
post.create_report(
    expressions=["dB(S(1,1))", "dB(S(2,1))"],
    setup_sweep_name="Setup1 : Sweep1",
    primary_sweep_variable="Freq",
    report_category="Modal S Parameters"
)

# Create polar plot
post.create_report(
    expressions=["S(1,1)"],
    plot_type="Smith Chart",
    setup_sweep_name="Setup1 : Sweep1"
)

# Get solution data
s_data = post.get_solution_data(
    expressions=["S(1,1)", "S(2,1)"],
    setup_sweep_name="Setup1 : Sweep1"
)

# Access data
freq = s_data.primary_sweep_values
s11 = s_data.data_db20("S(1,1)")
s21 = s_data.data_db20("S(2,1)")

# Export Touchstone file
hfss.export_touchstone(
    setup="Setup1",
    sweep="Sweep1",
    output_file="result.s2p"
)

# Export field data
post.export_field_jpg(
    quantity="E",
    output_file="E_field.jpg",
    setup_name="Setup1",
    phase="0deg"
)

# Far-field radiation pattern
post.create_report(
    expressions=["GainTotal"],
    primary_sweep_variable="Theta",
    context="Far Field",
    setup_sweep_name="Setup1 : LastAdaptive"
)

# Export far-field data
hfss.export_antenna_metadata(
    frequencies=[2.4e9],
    setup="Setup1",
    output_file="antenna_pattern.csv"
)
```

## Maxwell Post-Processing

```python
# Access post-processor
post = m3d.post

# Plot B-field magnitude
post.create_fieldplot_surface(
    objects_list=["Rotor", "Stator"],
    quantity="Mag_B",
    plot_name="B_Field"
)

# Get torque data
post.create_report(
    expressions=["Torque.Torque"],
    primary_sweep_variable="Time",
    setup_sweep_name="Setup1 : Transient"
)

# Export torque values
torque_data = post.get_solution_data(
    expressions=["Torque.Torque"],
    primary_sweep_variable="Time"
)

# Export inductance matrix
m3d.export_matrix(
    matrix_name="Matrix1",
    output_file="inductance.csv"
)

# Get loss data
post.create_report(
    expressions=["CoreLoss", "SolidLoss"],
    primary_sweep_variable="Time"
)
```

## Icepak Post-Processing

```python
# Access post-processor
post = ipk.post

# Temperature contour plot
post.create_fieldplot_surface(
    objects_list=["Die", "Heatsink"],
    quantity="Temperature",
    plot_name="TempContour"
)

# Flow visualization
post.create_fieldplot_surface(
    quantity="Velocity_Magnitude",
    objects_list=["AirRegion"]
)

# Create monitor report
post.create_report(
    expressions=["MonitorPoint.Temperature"],
    primary_sweep_variable="Time"  # For transient
)

# Get max temperature
max_temp = post.get_solution_data(
    expressions=["MaximumTemperature(Die)"]
)

# Export summary
ipk.export_summary(
    output_file="thermal_summary.csv"
)
```

## Common Export Functions

```python
# Export all results
app.export_results(
    output_file="results",
    export_touchstone=True,
    export_profile=True,
    export_convergence=True
)

# Export profile
app.export_profile(
    setup="Setup1",
    output_file="profile.prof"
)

# Export convergence data
app.export_convergence(
    setup="Setup1",
    output_file="convergence.csv"
)

# Export mesh statistics
app.export_mesh_stats(
    setup="Setup1",
    output_file="mesh_stats.csv"
)

# Export design preview image
app.export_design_preview_to_jpg(
    output_file="preview.jpg"
)

# Export variables
app.export_variables_to_csv(
    output_file="variables.csv"
)
```

## Data Manipulation

```python
# Get solution data object
sol_data = post.get_solution_data(expressions=["S(1,1)"])

# Convert to different formats
magnitude_db = sol_data.data_db20("S(1,1)")
magnitude_linear = sol_data.data_magnitude("S(1,1)")
phase_deg = sol_data.data_phase("S(1,1)")
real_part = sol_data.data_real("S(1,1)")
imag_part = sol_data.data_imag("S(1,1)")

# Export to CSV
sol_data.export_to_csv("data.csv")

# Plot with matplotlib
import matplotlib.pyplot as plt
freq = sol_data.primary_sweep_values
s11_db = sol_data.data_db20("S(1,1)")
plt.plot(freq, s11_db)
plt.xlabel("Frequency (GHz)")
plt.ylabel("S11 (dB)")
plt.savefig("s11_plot.png")
```
"""


def get_guidelines_for_parametric() -> str:
    """Get parametric analysis and optimization guidelines for AEDT.

    Use this tool when explaining or generating parametric studies.

    Returns
    -------
    str
        Guidelines for parametric sweeps and optimization in AEDT.
    """
    return """# Parametric and Optimization Guidelines in AEDT

AEDT supports parametric sweeps, optimization, sensitivity analysis, and statistical analysis.

## Design Variables

```python
# Create design variable
hfss["patch_length"] = "30mm"
hfss["patch_width"] = "20mm"
hfss["substrate_height"] = "1.6mm"

# Use variable in geometry
patch = hfss.modeler.create_rectangle(
    cs_plane="XY",
    position=[0, 0, "substrate_height"],
    dimension_list=["patch_length", "patch_width"],
    name="Patch"
)

# Access existing variables
print(hfss.variable_manager.design_variables)

# Modify variable
hfss["patch_length"] = "32mm"

# Create dependent variable (expression)
hfss["half_length"] = "patch_length/2"
```

## Parametric Sweep

```python
# Create parametric sweep
sweep = hfss.parametrics.add(
    sweep_var="patch_length",
    start="25mm",
    stop="35mm",
    step="2mm",
    name="LengthSweep"
)

# Multi-variable sweep
sweep = hfss.parametrics.add(
    sweep_var=["patch_length", "patch_width"],
    start=["25mm", "15mm"],
    stop=["35mm", "25mm"],
    step=["2mm", "2mm"],
    name="MultiSweep"
)

# Analyze parametric
hfss.analyze_setup("Setup1", variations={"patch_length": ["25mm", "30mm", "35mm"]})

# Export parametric results
hfss.export_parametric_results(
    sweep="LengthSweep",
    filename="param_results.csv"
)
```

## Optimization

```python
# Access optimetrics
opt = hfss.optimizations

# Add optimization goal
opt.add_goal(
    expression="dB(S(1,1))",
    goal_value=-15,
    weight=1,
    goal_type="minimize",
    setup_sweep_name="Setup1 : Sweep1",
    condition="<="
)

# Add variable for optimization
opt.add_variable(
    variable="patch_length",
    min_value="25mm",
    max_value="35mm",
    starting_value="30mm"
)

# Configure optimizer
opt.optimizer = "SNLP"  # Sequential Non-Linear Programming
opt.max_iterations = 100

# Run optimization
opt.solve()

# Get optimized values
optimal_values = opt.get_optimal_values()
```

## Sensitivity Analysis

```python
# Create sensitivity analysis
sens = hfss.parametrics.add_sensitivity(
    variable="patch_length",
    min_value="28mm",
    max_value="32mm",
    name="SensAnalysis"
)

# Add output to track
sens.add_output(
    expression="dB(S(1,1))",
    setup_sweep_name="Setup1 : Sweep1"
)

# Run sensitivity analysis
sens.solve()

# Get sensitivity data
sens_data = sens.get_sensitivity_data()
```

## Statistical Analysis

```python
# Create statistical analysis
stat = hfss.parametrics.add_statistical(
    name="StatAnalysis"
)

# Add variable with tolerance
stat.add_variable(
    variable="patch_length",
    distribution="Gaussian",
    mean="30mm",
    tolerance="5%"  # 5% standard deviation
)

# Configure Monte Carlo settings
stat.sample_size = 100
stat.seed = 42

# Run statistical analysis
stat.solve()

# Get statistical results
results = stat.get_statistical_results()
print(f"Mean S11: {results['mean']}")
print(f"Std Dev: {results['std_dev']}")
```

## Design of Experiments (DOE)

```python
# Create DOE study
doe = hfss.parametrics.add_doe(
    name="DOE_Study"
)

# Add design variables
doe.add_variable("patch_length", "25mm", "35mm")
doe.add_variable("patch_width", "15mm", "25mm")
doe.add_variable("substrate_height", "1mm", "2mm")

# Configure DOE type
doe.doe_type = "Box-Behnken"  # or "Central Composite", "Full Factorial"

# Add response
doe.add_response(
    expression="dB(S(1,1))",
    setup_sweep_name="Setup1 : Sweep1"
)

# Run DOE
doe.solve()

# Get response surface
response_surface = doe.get_response_surface()
```

## Tuning Analysis

```python
# Activate variable for tuning
hfss.activate_variable_tuning(
    name="patch_length",
    min_value="25mm",
    max_value="35mm"
)

# Interactive tuning (in GUI)
# Variables can be adjusted in real-time with immediate results update

# Deactivate tuning
hfss.deactivate_variable_tuning("patch_length")
```

## Best Practices

1. **Use meaningful variable names** - Makes it easier to track parameters
2. **Set appropriate ranges** - Too wide ranges increase solve time
3. **Start with coarse sweeps** - Refine after identifying regions of interest
4. **Use symmetry** - Reduce model size to speed up parametric studies
5. **Monitor convergence** - Check that each variation converges properly
6. **Export results regularly** - Save data for post-processing
"""


_CONTENT_MAP = {
    "workflow": get_guidelines_for_workflow_overview,
    "hfss": get_guidelines_for_hfss,
    "maxwell": get_guidelines_for_maxwell,
    "icepak": get_guidelines_for_icepak,
    "circuit": get_guidelines_for_circuit,
    "geometry": get_guidelines_for_geometry,
    "mesh": get_guidelines_for_mesh,
    "boundaries": get_guidelines_for_boundaries,
    "postprocessing": get_guidelines_for_postprocessing,
    "parametric": get_guidelines_for_parametric,
}


@app.tool(tags={"pyaedt_context"})
def get_guidelines_for(content: GuidelinesContent) -> str:
    """Get PyAEDT/AEDT simulation guidelines for a specific topic.

    Use this tool before writing PyAEDT or Ansys AEDT scripting code to
    retrieve the relevant guidelines for the workflow step or solver you are
    about to use. Call it once per topic needed. You should call it before
    every code-generation task.

    Parameters
    ----------
    content : str
        Guideline topic to retrieve. Options follow:

        - ``"workflow"``: PyAEDT workflow overview
        - ``"hfss"``: HFSS (high-frequency electromagnetics)
        - ``"maxwell"``: Maxwell (low-frequency electromagnetics)
        - ``"icepak"``: Icepak (electronics thermal)
        - ``"circuit"``: Circuit / Twin Builder
        - ``"geometry"``: Geometry creation and modeling
        - ``"mesh"``: Mesh operations and refinement
        - ``"boundaries"``: Boundary conditions and excitations
        - ``"postprocessing"``: Reports, fields, and visualization
        - ``"parametric"``: Parametric sweeps and optimization

    Returns
    -------
    str
        Guideline text for the requested topic.
    """
    return _CONTENT_MAP[content]()
