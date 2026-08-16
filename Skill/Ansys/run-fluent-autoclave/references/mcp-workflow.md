# Fluent MCP workflow

## Session sequence

1. Call Fluent detection.
2. List existing sessions.
3. Launch a 3-D double-precision solver session with a resource-appropriate processor count.
4. Validate session metadata and evaluate a small Scheme expression.
5. Read the mesh through the PyFluent file settings interface.
6. Run the Fluent mesh check and print domain extents and zone names.
7. Configure model, material, boundaries, methods, and transient controls in separate Python chunks.
8. Hybrid initialize and run one time step.
9. Save an initial case/data pair.
10. Use an asynchronous journal for the long solve; poll status and stdout/stderr.
11. Load the final case/data into a retained post-processing session.

## Chinese Windows paths

Fluent 24.2 may report a valid file under a Chinese path as not found. Map the job directory to an ASCII drive letter with `subst`, then use paths such as `V:/case.cas.h5`. Record the mapping and keep it while the Fluent session is active.

## Required reports

- Inlet and outlet mass-flow rates.
- Inlet and outlet area-average speeds.
- Outlet facet maximum speed.
- Global volume maximum and average speed.
- Global maximum-speed cell centroid.
- Inlet and outlet area-average gauge pressure.
- Outlet average and global min/max temperature.
- Final residuals and local outlet reverse-flow percentage.

Compute mass imbalance as `abs(inlet + outlet) / abs(inlet) * 100` when Fluent's sign convention gives positive inlet and negative outlet values.

## Main-view convention

Use the vertical longitudinal mid-plane. Display axial position horizontally with outlet on the left and inlet/ellipsoidal head on the right. Plot truthful computed limits; do not force the reference image maximum onto a different geometry.
