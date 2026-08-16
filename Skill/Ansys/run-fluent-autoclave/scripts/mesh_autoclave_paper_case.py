import json
import gmsh

STEP = r"C:\Users\40285\Desktop\仿真\autoclave_geometry.step"
MSH = r"C:\Users\40285\Desktop\仿真\autoclave_paper_open_mesh.msh"
VTK = r"C:\Users\40285\Desktop\仿真\autoclave_paper_open_mesh.vtk"
REPORT = r"C:\Users\40285\Desktop\仿真\paper_mesh_report.json"

gmsh.initialize()
gmsh.option.setNumber("General.Terminal", 1)
gmsh.model.add("autoclave_paper_case")
gmsh.model.occ.importShapes(STEP)
gmsh.model.occ.synchronize()

# Three touching gas passages form the open autoclave fluid domain.  The
# sixteen internal solids are removed so their exposed surfaces become walls.
fluid_parts = [(3, 1), (3, 2), (3, 3)]
internals = [(3, tag) for tag in range(4, 20)]
fused, _ = gmsh.model.occ.fuse([fluid_parts[0]], fluid_parts[1:],
                               removeObject=True, removeTool=True)
fluid, _ = gmsh.model.occ.cut(fused, internals,
                              removeObject=True, removeTool=True)
gmsh.model.occ.synchronize()

fluid_vols = [tag for dim, tag in fluid if dim == 3]
if not fluid_vols:
    raise RuntimeError("No fluid volume remained after Boolean operations")

surfaces = sorted({tag for dim, tag in gmsh.model.getBoundary(
    [(3, tag) for tag in fluid_vols], oriented=False, recursive=False)
    if dim == 2})
inlet, outlet, wall_adiabatic, calorimeter_50c = [], [], [], []
tol = 1e-3
for tag in surfaces:
    xmin, ymin, zmin, xmax, ymax, zmax = gmsh.model.getBoundingBox(2, tag)
    area = gmsh.model.occ.getMass(2, tag)
    # Two annular-clearance faces at the ellipsoidal-head shoulder.
    if abs(zmin - 1350.0) < tol and abs(zmax - 1350.0) < tol and area > 1e5:
        inlet.append(tag)
    elif abs(zmin - 16950.0) < tol and abs(zmax - 16950.0) < tol:
        outlet.append(tag)
    elif (abs(ymax - ymin) < tol and 5.7e4 < area < 5.9e4
          and 4000.0 < zmin < 14000.0):
        # Eight exposed 240 x 240 mm aluminium calorimeter faces.
        calorimeter_50c.append(tag)
    else:
        wall_adiabatic.append(tag)

pg_fluid = gmsh.model.addPhysicalGroup(3, fluid_vols)
gmsh.model.setPhysicalName(3, pg_fluid, "fluid")
for name, tags in (("inlet", inlet), ("outlet", outlet),
                   ("wall_adiabatic", wall_adiabatic),
                   ("calorimeter_50c", calorimeter_50c)):
    pg = gmsh.model.addPhysicalGroup(2, tags)
    gmsh.model.setPhysicalName(2, pg, name)

# About 0.3-0.5 million tetrahedra on this geometry: enough to resolve the
# head turning and upper-wall jet while remaining practical on this workstation.
gmsh.option.setNumber("Mesh.MeshSizeMin", 50.0)
gmsh.option.setNumber("Mesh.MeshSizeMax", 220.0)
gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 24)
gmsh.option.setNumber("Mesh.Algorithm", 6)
gmsh.option.setNumber("Mesh.Algorithm3D", 10)
gmsh.option.setNumber("Mesh.Optimize", 1)
gmsh.model.mesh.generate(3)
gmsh.model.mesh.optimize("Netgen")

node_tags, _, _ = gmsh.model.mesh.getNodes()
types, elem_tags, _ = gmsh.model.mesh.getElements(3)
element_counts = {str(t): len(tags) for t, tags in zip(types, elem_tags)}
quality = []
for tags in elem_tags:
    if len(tags):
        quality.extend(gmsh.model.mesh.getElementQualities(tags, "minSICN"))

report = {
    "length_unit": "mm",
    "fluid_volume_tags": fluid_vols,
    "fluid_volume_mm3": sum(gmsh.model.occ.getMass(3, t) for t in fluid_vols),
    "surface_counts": {"inlet": len(inlet), "outlet": len(outlet),
                       "wall_adiabatic": len(wall_adiabatic),
                       "calorimeter_50c": len(calorimeter_50c)},
    "surface_tags": {"inlet": inlet, "outlet": outlet},
    "nodes": len(node_tags),
    "volume_elements_by_gmsh_type": element_counts,
    "quality_minSICN": {
        "min": float(min(quality)) if quality else None,
        "mean": float(sum(quality) / len(quality)) if quality else None,
        "max": float(max(quality)) if quality else None,
    },
}
gmsh.option.setNumber("Mesh.MshFileVersion", 4.1)
gmsh.write(MSH)
gmsh.write(VTK)
with open(REPORT, "w", encoding="utf-8") as stream:
    json.dump(report, stream, ensure_ascii=False, indent=2)
print(json.dumps(report, ensure_ascii=False, indent=2))
gmsh.finalize()
