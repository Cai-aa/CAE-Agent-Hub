import numpy as np
import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.tri as mtri
import pyvista as pv

ROOT = r"C:\Users\40285\Desktop\仿真"
d = np.load(ROOT + r"\fluent_paper_front_plane_data.npz")
p = d["vertices"]
offsets = d["face_offsets"]
nodes = d["face_nodes"]
speed = d["speed"]
pressure = d["pressure"]
temperature = d["temperature"]
cell_velocity = d["cell_velocity"]

mpl.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial"]
mpl.rcParams["axes.unicode_minus"] = False

# Longitudinal vertical mid-plane: outlet on the left, inlet/head on the right.
xx = p[:, 2].max() - p[:, 2]
yy = p[:, 1]
faces = [nodes[offsets[i]:offsets[i + 1]] for i in range(len(offsets) - 1)]
triangles = []
for face in faces:
    for j in range(1, len(face) - 1):
        triangles.append([face[0], face[j], face[j + 1]])
triangles = np.asarray(triangles, dtype=np.int64)
good = np.array([len(set(row.tolist())) == 3 for row in triangles])
triangles = triangles[good]
area2 = ((xx[triangles[:, 1]] - xx[triangles[:, 0]]) *
         (yy[triangles[:, 2]] - yy[triangles[:, 0]]) -
         (xx[triangles[:, 2]] - xx[triangles[:, 0]]) *
         (yy[triangles[:, 1]] - yy[triangles[:, 0]]))
triangles = triangles[np.abs(area2) > 1e-12]
_, keep = np.unique(np.sort(triangles, axis=1), axis=0, return_index=True)
triangles = triangles[np.sort(keep)]
triang = mtri.Triangulation(xx, yy, triangles)

def decorate(ax, title):
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlim(-0.35, xx.max() + 0.35)
    ax.set_ylim(yy.min() - 0.35, yy.max() + 0.35)
    ax.set_xlabel("轴向位置：出口 → 入口/椭圆封头")
    ax.set_ylabel("竖直方向（m）")
    ax.set_title(title, fontsize=14, pad=10)
    ax.text(0.05, yy.max() + 0.13, "出口", color="#2166ac", ha="left")
    ax.text(xx.max() - 0.05, yy.max() + 0.13, "入口/封头",
            color="#b2182b", ha="right")
    ax.spines[["top", "right"]].set_visible(False)

def contour(values, cmap, vmin, vmax, title, label, filename):
    fig, ax = plt.subplots(figsize=(15, 5.4), constrained_layout=True)
    cf = ax.tripcolor(triang, values, shading="gouraud", cmap=cmap,
                      norm=mpl.colors.Normalize(vmin=vmin, vmax=vmax))
    decorate(ax, title)
    cb = fig.colorbar(cf, ax=ax, pad=0.015, shrink=0.88)
    cb.set_label(label)
    fig.savefig(ROOT + "\\" + filename, dpi=300, bbox_inches="tight")
    plt.close(fig)

contour(speed, "turbo", 0.0, 6.1,
        "Fluent 速度云图（主视图中剖面，SA，t = 15 s）",
        "速度大小（m/s）", "fluent_paper_velocity_front.png")
contour(temperature, "inferno", 323.15, 333.15,
        "Fluent 温度云图（主视图中剖面，t = 15 s）",
        "温度（K）", "fluent_paper_temperature_front.png")
contour(pressure, "RdBu_r", float(np.percentile(pressure, 1)),
        float(np.percentile(pressure, 99)),
        "Fluent 静压云图（主视图中剖面，t = 15 s）",
        "表压（Pa）", "fluent_paper_pressure_front.png")

# Build a 2-D vector field on the same cut and integrate streamlines.
pv_points = np.column_stack([xx, yy, np.zeros_like(xx)])
pv_rows, pv_velocity = [], []
for i, face in enumerate(faces):
    if len(face) >= 3 and len(set(face.tolist())) == len(face):
        pv_rows.extend([len(face), *face.tolist()])
        pv_velocity.append([-cell_velocity[i, 2], cell_velocity[i, 1], 0.0])
surface = pv.PolyData(pv_points, np.asarray(pv_rows, dtype=np.int64))
surface.point_data["speed_m_s"] = speed
surface.cell_data["velocity_display"] = np.asarray(pv_velocity)
surface = surface.triangulate().clean().cell_data_to_point_data(pass_cell_data=True)
surface.set_active_vectors("velocity_display")
try:
    lines = surface.streamlines_evenly_spaced_2D(
        vectors="velocity_display", start_position=(15.7, 0.0, 0.0),
        integrator_type=4, step_length=0.025, step_unit="l", max_steps=5000,
        terminal_speed=0.01, separating_distance=0.18,
        separating_distance_ratio=0.55, compute_vorticity=False)
except Exception:
    lines = surface.streamlines(
        vectors="velocity_display", source_center=(15.6, 0.0, 0.0),
        source_radius=2.25, n_points=240, integration_direction="both",
        max_steps=5000, terminal_speed=0.01)

pv.global_theme.background = "white"
pv.global_theme.font.color = "black"
plotter = pv.Plotter(off_screen=True, window_size=(1900, 760))
plotter.add_mesh(surface, scalars="speed_m_s", cmap="turbo", clim=(0.0, 6.1),
                 show_edges=False, scalar_bar_args={"title": "Speed (m/s)",
                 "vertical": True, "position_x": 0.04, "position_y": 0.21,
                 "height": 0.58, "width": 0.08})
plotter.add_mesh(lines, color="white", line_width=1.1)
plotter.view_xy()
plotter.enable_parallel_projection()
plotter.camera.zoom(1.07)
plotter.add_text("Fluent streamlines - vertical longitudinal mid-plane, t = 15 s",
                 position="upper_left", font_size=13, color="black")
plotter.add_text("Outlet  <-  flow direction  <-  annular inlet / ellipsoidal head",
                 position="lower_left", font_size=10, color="black")
plotter.show(screenshot=ROOT + r"\fluent_paper_streamlines_front.png")
plotter.close()

# A dense, evenly seeded main-view streamline figure.  Interpolate the
# face-centred Fluent velocity to nodes and then to a masked regular grid.
vsum = np.zeros((len(p), 3), dtype=float)
vcount = np.zeros(len(p), dtype=float)
for i, face in enumerate(faces):
    vsum[face] += cell_velocity[i]
    vcount[face] += 1.0
vnode = vsum / np.maximum(vcount[:, None], 1.0)
u_node = -vnode[:, 2]
v_node = vnode[:, 1]
gx = np.linspace(xx.min(), xx.max(), 850)
gy = np.linspace(yy.min(), yy.max(), 260)
GX, GY = np.meshgrid(gx, gy)
from PIL import Image, ImageDraw
query = pv.PolyData(np.column_stack([GX.ravel(), GY.ravel(),
                                    np.zeros(GX.size)]))
sampled = query.interpolate(surface, radius=0.35, sharpness=2.0,
                            strategy="closest_point")
grid_velocity = np.asarray(sampled.point_data["velocity_display"]).reshape(
    len(gy), len(gx), 3)
u_grid = grid_velocity[:, :, 0]
v_grid = grid_velocity[:, :, 1]
# Rasterize the actual Fluent cut polygons so streamlines do not leak into the
# white space outside the outlet neck or ellipsoidal head.
mask_image = Image.new("1", (len(gx), len(gy)), 0)
draw = ImageDraw.Draw(mask_image)
for tri in triangles:
    poly = []
    for idx in tri:
        px = (xx[idx] - gx[0]) / (gx[-1] - gx[0]) * (len(gx) - 1)
        py = (yy[idx] - gy[0]) / (gy[-1] - gy[0]) * (len(gy) - 1)
        poly.append((int(round(px)), len(gy) - 1 - int(round(py))))
    draw.polygon(poly, fill=1)
inside = np.flipud(np.asarray(mask_image, dtype=bool))
outside = ~inside | ~np.isfinite(u_grid) | ~np.isfinite(v_grid)
u_grid = np.ma.array(u_grid, mask=outside)
v_grid = np.ma.array(v_grid, mask=outside)

fig, ax = plt.subplots(figsize=(15, 5.4), constrained_layout=True)
cf = ax.tripcolor(triang, speed, shading="gouraud", cmap="turbo",
                  norm=mpl.colors.Normalize(vmin=0.0, vmax=6.1))
dx = (gx[-1] - gx[0]) / (len(gx) - 1)
dy = (gy[-1] - gy[0]) / (len(gy) - 1)
stream_transform = (mpl.transforms.Affine2D().scale(dx, dy)
                    .translate(gx[0], gy[0]) + ax.transData)
ax.streamplot(np.arange(len(gx)), np.arange(len(gy)),
              u_grid / dx, v_grid / dy, transform=stream_transform,
              color="white", density=(3.0, 1.8),
              linewidth=0.55, arrowsize=0.65, maxlength=5.0,
              integration_direction="both", broken_streamlines=True)
decorate(ax, "Fluent 流线图（主视图中剖面，SA，t = 15 s）")
cb = fig.colorbar(cf, ax=ax, pad=0.015, shrink=0.88)
cb.set_label("速度大小（m/s）")
fig.savefig(ROOT + r"\fluent_paper_streamlines_front.png", dpi=300,
            bbox_inches="tight")
plt.close(fig)

print({"plane_speed_max": float(speed.max()),
       "plane_temperature_min": float(temperature.min()),
       "plane_temperature_max": float(temperature.max())})
