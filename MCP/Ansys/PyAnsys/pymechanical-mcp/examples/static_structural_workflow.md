# Static Structural Analysis Workflow

This example demonstrates a complete Mechanical FEA workflow using the
pymechanical-mcp tools. All steps were validated live against
ANSYS Mechanical 2026 R1 on April 21, 2026.

> **GUI Mode:** Launch Mechanical with `batch=false` so the GUI is visible
> and you can see geometry, mesh, and result contour plots interactively.

## Tool Visibility Model

`pymechanical-mcp` uses a connection-aware visibility model so the LLM
client sees a small, focused tool surface up front and additional tools
unlock once a Mechanical session is connected.

| Stage                       | Tools available                                                                                  |
|-----------------------------|--------------------------------------------------------------------------------------------------|
| Server start (no Mechanical)| `check_mechanical_installed`, `launch_mechanical`, `connect_to_mechanical`, `get_guidelines_for` |
| After `launch_mechanical` / | + `check_mechanical_status`, `run_python_script`,                                                    |
|     `connect_to_mechanical` | &nbsp;&nbsp; `screenshot`, `save_project`, `get_model_info`, `export_results`, ...               |

> The single `get_guidelines_for(content="workflow"|"materials"|"meshing"|...)`
> tool replaces the older 10 separate `get_guidelines_for_*` tools.

## 1. Check Mechanical Installation

**Tool:** `check_mechanical_installed`

```
Response: Mechanical is installed on this system.
```

## 2. Launch Mechanical (GUI Mode)

**Tool:** `launch_mechanical`

| Parameter | Value |
|-----------|-------|
| batch     | false |

> Set `batch=false` to launch Mechanical in interactive/GUI mode.
> The Mechanical window will be visible on the desktop.

```
Response:
  Successfully launched Mechanical
  Version: 261
  Project Directory: C:\Users\...\Project_Mech_Files\
```

## 3. Check Connection Status

**Tool:** `check_mechanical_status`

```json
{
  "connection": {
    "version": "261",
    "is_alive": true,
    "busy": false
  },
  "product_info": {
    "raw": "Ansys Mechanical [Ansys Mechanical Enterprise]\nProduct Version:261"
  },
  "model": {
    "model_name": "Model",
    "product_version": "2026 R1"
  }
}
```

## 4. Create Analysis

**Tool:** `run_python_script`

```python
analysis = Model.AddStaticStructuralAnalysis()
"Static Structural analysis added: {0}".format(analysis.Name)
```

```
Response: Static Structural analysis added: Static Structural
```

## 5. Import Geometry

**Tool:** `run_python_script`

> Replace the file path with your actual STEP/IGES geometry file.

```python
geometry_import = Model.GeometryImportGroup.AddGeometryImport()
geometry_file = r"examples\cantilever_beam\beam.step"
geometry_import_format = Ansys.Mechanical.DataModel.Enums.GeometryImportPreference.Format.Automatic
geometry_import_prefs = Ansys.ACT.Mechanical.Utilities.GeometryImportPreferences()
geometry_import_prefs.ProcessNamedSelections = True
geometry_import.Import(geometry_file, geometry_import_format, geometry_import_prefs)
"Geometry imported: {0} bodies".format(
    Model.Geometry.GetChildren(DataModelObjectCategory.Body, True).Count
)
```

```
Response: Geometry imported: 1 bodies
```

## 6. Assign Material

**Tool:** `run_python_script`

```python
body = Model.Geometry.GetChildren(DataModelObjectCategory.Body, True)[0]
body.Material = "Structural Steel"
"Material assigned: {0}".format(body.Material)
```

```
Response: Material assigned: Structural Steel
```

## 7. Generate Mesh

**Tool:** `run_python_script`

> **Unit format:** Use `Quantity("5 [mm]")` with square brackets for Mechanical.

```python
mesh = Model.Mesh
mesh.ElementSize = Quantity("5 [mm]")
mesh.GenerateMesh()
"Mesh generated. Nodes: {0}, Elements: {1}".format(mesh.Nodes, mesh.Elements)
```

```
Response: Mesh generated. Nodes: 1424, Elements: 667
```

## 8. Get Model Info

**Tool:** `get_model_info`

```json
{
  "geometry": { "body_count": 1 },
  "mesh": { "node_count": 1424, "element_count": 667 },
  "analyses_count": 1,
  "project": { "product_version": "2026 R1", "name": "Project" },
  "model": { "name": "Model" }
}
```

## 9. Create Named Selections for Boundary Conditions

**Tool:** `run_python_script`

> Always use Named Selections to scope loads and supports to specific geometry.

```python
# Fixed end: face at x=0 (left face of beam)
ns_group = Model.AddNamedSelection()
ns_group.ScopingMethod = GeometryDefineByType.Worksheet
worksheet = ns_group.GenerationCriteria
criterion = Ansys.ACT.Automation.Mechanical.NamedSelectionCriterion()
criterion.Active = True
criterion.Action = SelectionActionType.Add
criterion.EntityType = SelectionType.GeoFace
criterion.Criterion = SelectionCriterionType.LocationX
criterion.Operator = SelectionOperatorType.Equal
criterion.Value = Quantity("0 [mm]")
worksheet.Add(criterion)
ns_group.Generate()
ns_group.Name = "FixedEnd"

# Force end: face at x=200 (right face of beam)
ns_force = Model.AddNamedSelection()
ns_force.ScopingMethod = GeometryDefineByType.Worksheet
worksheet2 = ns_force.GenerationCriteria
criterion2 = Ansys.ACT.Automation.Mechanical.NamedSelectionCriterion()
criterion2.Active = True
criterion2.Action = SelectionActionType.Add
criterion2.EntityType = SelectionType.GeoFace
criterion2.Criterion = SelectionCriterionType.LocationX
criterion2.Operator = SelectionOperatorType.Equal
criterion2.Value = Quantity("200 [mm]")
worksheet2.Add(criterion2)
ns_force.Generate()
ns_force.Name = "ForceEnd"

"Named Selections created: FixedEnd, ForceEnd"
```

```
Response: Named Selections created: FixedEnd, ForceEnd
```

## 10. Apply Boundary Conditions

**Tool:** `run_python_script`

> **Force components:** Use `force.YComponent.Output.DiscreteValues = [Quantity("-1000 [N]")]`
> because `YComponent` is a read-only property; you must set its values via the output table.

```python
analysis = Model.Analyses[0]

# Fixed support on FixedEnd
fixed = analysis.AddFixedSupport()
ns_fixed = [ns for ns in Model.NamedSelections.Children if ns.Name == "FixedEnd"][0]
fixed.Location = ns_fixed

# Force on ForceEnd (-Y direction, 1000 N)
force = analysis.AddForce()
ns_force = [ns for ns in Model.NamedSelections.Children if ns.Name == "ForceEnd"][0]
force.Location = ns_force
force.DefineBy = LoadDefineBy.Components
force.YComponent.Output.DiscreteValues = [Quantity("-1000 [N]")]

"BCs applied: {0} on FixedEnd, {1} on ForceEnd (Y = -1000 N)".format(fixed.Name, force.Name)
```

```
Response: BCs applied: Fixed Support on FixedEnd, Force on ForceEnd (Y = -1000 N)
```

## 11. Add Result Objects

**Tool:** `run_python_script`

```python
solution = Model.Analyses[0].Solution

total_deform = solution.AddTotalDeformation()
equiv_stress = solution.AddEquivalentStress()

"Results added: {0}, {1}".format(total_deform.Name, equiv_stress.Name)
```

```
Response: Results added: Total Deformation, Equivalent Stress
```

## 12. Solve and Evaluate Results

**Tool:** `run_python_script`

```python
analysis = Model.Analyses[0]
analysis.Solve(True)

solution = analysis.Solution
solution.EvaluateAllResults()

td = None
es = None
for i in range(solution.Children.Count):
    c = solution.Children[i]
    if c.Name == "Total Deformation":
        td = c
    elif c.Name == "Equivalent Stress":
        es = c

"Solved! Deformation Max: {0}, Stress Max: {1}".format(
    str(td.Maximum) if td else "N/A",
    str(es.Maximum) if es else "N/A"
)
```

```
Response: Solved! Deformation Max: 0.00402 [m], Stress Max: 599447794.58 [Pa]
```

## 13. Activate Result in GUI

**Tool:** `run_python_script`

> Activating a result object displays its contour plot in the Mechanical GUI.

```python
solution = Model.Analyses[0].Solution
for i in range(solution.Children.Count):
    c = solution.Children[i]
    if c.Name == "Total Deformation":
        c.Activate()
        break
"Total Deformation contour plot displayed in GUI"
```

## 14. Screenshot

**Tool:** `screenshot`

Returns a PNG image of the Mechanical viewport showing the result contour plot.

## 15. Clear and Disconnect

**Tool:** `clear_mechanical`

```
Response: Mechanical database cleared successfully.
```

**Tool:** `disconnect_from_mechanical`

```
Response: Successfully disconnected from Mechanical
```

---

## Important Notes

1. **GUI Mode:** `launch_mechanical` prefers a visible GUI session by default.
  Use `batch=true` only when you explicitly want headless/batch mode.
2. **Use `.format()` instead of f-strings**: Mechanical versions before 2026 R1
  use IronPython 2.7, which does not support f-string syntax.
3. **Script return values:** The last expression in a `run_python_script` call is
   returned as the result. Do NOT assign to `result =`; instead end with a bare
   string expression like `"message: {0}".format(value)`.
4. **Use `run_python_script`** for Mechanical API scripting (ExtAPI, Model, etc.).
   Use `run_python_code` only for external Python calculations (NumPy, Pandas, etc.).
5. **Units:** Use `Quantity("5 [mm]")` with square brackets for Mechanical unit strings.
6. **Read-only properties:** Force/moment component properties (e.g. `YComponent`) are
   read-only. Set values via: `force.YComponent.Output.DiscreteValues = [Quantity("-1000 [N]")]`
7. **Scoping:** Always use Named Selections (worksheet-based) for boundary conditions
   and results to ensure geometry is properly targeted.
