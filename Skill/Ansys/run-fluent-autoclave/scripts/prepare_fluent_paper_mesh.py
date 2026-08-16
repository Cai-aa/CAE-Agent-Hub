from collections import defaultdict
import json
import meshio
import numpy as np

ROOT = r"C:\Users\40285\Desktop\仿真"
SOURCE = ROOT + r"\autoclave_paper_open_mesh.msh"
TARGET = ROOT + r"\autoclave_paper_fluent.msh"
REPORT = ROOT + r"\paper_fluent_mesh_conversion.json"

def hx(value):
    return format(int(value), "x")

m = meshio.read(SOURCE)
points = np.asarray(m.points, dtype=float) / 1000.0
groups = {name: int(value[0]) for name, value in m.field_data.items()}
tets, boundary_zone = [], {}
zone_id_by_physical = {groups["inlet"]: 2, groups["outlet"]: 3,
                       groups["wall_adiabatic"]: 4,
                       groups["calorimeter_50c"]: 6}
for block, physical in zip(m.cells, m.cell_data["gmsh:physical"]):
    if block.type == "tetra":
        tets.append(np.asarray(block.data, dtype=np.int64))
    elif block.type == "triangle":
        zid = zone_id_by_physical.get(int(physical[0]))
        if zid is not None:
            for face in block.data:
                boundary_zone[tuple(sorted(map(int, face)))] = zid
tets = np.vstack(tets).astype(np.int64)
centers = points[tets].mean(axis=1)
flipped = 0
for i, tet in enumerate(tets):
    p0, p1, p2, p3 = points[tet]
    if np.dot(p1 - p0, np.cross(p2 - p0, p3 - p0)) < 0:
        tets[i, 2], tets[i, 3] = tets[i, 3], tets[i, 2]
        flipped += 1
face_to_cells = defaultdict(list)
for cell_index, (a, b, c, d) in enumerate(tets):
    for face in ((a, b, c), (a, b, d), (a, c, d), (b, c, d)):
        face_to_cells[tuple(sorted(map(int, face)))].append(cell_index)
zone_faces = defaultdict(list)
unmatched_boundary = nonmanifold = 0
for face, owners in face_to_cells.items():
    x, y, z = face
    p0, p1, p2 = points[[x, y, z]]
    fluent_normal = np.cross(p2 - p0, p1 - p0)
    if len(owners) == 1:
        owner = owners[0]
        zid = boundary_zone.get(face, 4)
        unmatched_boundary += int(face not in boundary_zone)
        desired = (p0 + p1 + p2) / 3.0 - centers[owner]
        nodes = (x, y, z) if np.dot(fluent_normal, desired) > 0 else (x, z, y)
        zone_faces[zid].append((*[n + 1 for n in nodes], owner + 1, 0))
    elif len(owners) == 2:
        left, right = sorted(owners)
        desired = centers[right] - centers[left]
        nodes = (x, y, z) if np.dot(fluent_normal, desired) > 0 else (x, z, y)
        zone_faces[5].append((*[n + 1 for n in nodes], left + 1, right + 1))
    else:
        nonmanifold += 1
lines = ['(0 "Autoclave paper-case mesh")', '(2 3)',
         f'(10 (0 1 {hx(len(points))} 1 3))', f'(10 (1 1 {hx(len(points))} 1 3)(']
lines.extend(f"{p[0]:.12e} {p[1]:.12e} {p[2]:.12e}" for p in points)
lines.extend(['))', f'(12 (0 1 {hx(len(tets))} 0))', f'(12 (1 1 {hx(len(tets))} 1 2)('])
lines.extend(' '.join(hx(n + 1) for n in tet) for tet in tets)
lines.append('))')
total_faces = sum(len(value) for value in zone_faces.values())
lines.append(f'(13 (0 1 {hx(total_faces)} 0))')
first = 1
bc_type = {2: 10, 3: 5, 4: 3, 5: 2, 6: 3}
for zid in (2, 3, 4, 6, 5):
    faces = zone_faces[zid]
    last = first + len(faces) - 1
    lines.append(f'(13 ({hx(zid)} {hx(first)} {hx(last)} {hx(bc_type[zid])} 3)(')
    lines.extend(' '.join(hx(value) for value in face) for face in faces)
    lines.append('))')
    first = last + 1
lines.extend(['(45 (1 fluid fluid)())', '(45 (2 velocity-inlet inlet)())',
              '(45 (3 pressure-outlet outlet)())',
              '(45 (4 wall wall-adiabatic)())',
              '(45 (6 wall calorimeter-50c)())',
              '(45 (5 interior interior)())'])
with open(TARGET, "w", encoding="ascii") as stream:
    stream.write("\n".join(lines) + "\n")
report = {"nodes": len(points), "tetrahedra": len(tets),
          "faces": {"inlet": len(zone_faces[2]), "outlet": len(zone_faces[3]),
                    "wall_adiabatic": len(zone_faces[4]),
                    "calorimeter_50c": len(zone_faces[6]),
                    "interior": len(zone_faces[5])},
          "flipped_tetrahedra": flipped,
          "unmatched_boundary_faces": unmatched_boundary,
          "nonmanifold_faces": nonmanifold, "target": TARGET}
with open(REPORT, "w", encoding="utf-8") as stream:
    json.dump(report, stream, ensure_ascii=False, indent=2)
print(json.dumps(report, ensure_ascii=False, indent=2))
