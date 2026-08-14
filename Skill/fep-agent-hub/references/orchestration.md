# Three-MCP orchestration

## Stage 0: preflight

1. Read repository instructions and the case prompt/report.
2. Resolve `OPEN_CAE_CONFIG` and the workspace root.
3. Call `freecad_environment_probe`, `elmer_environment_probe`, and `paraview_environment_probe`.
4. Confirm the requested profile is present and the project path is workspace-contained.
5. Record software versions and tool inventories in evidence.

## Stage 1: FreeCAD geometry

Use the smallest auditable sequence:

1. `freecad_document_create` or `freecad_document_open`.
2. `freecad_feature_create` for named primitive/planar features.
3. `freecad_boolean` and `freecad_transform` only when required.
4. `freecad_object_inspect` and `freecad_document_inspect`.
5. `freecad_geometry_validate` for validity, dimensions, areas/volumes, and expected objects.
6. `freecad_document_save`.
7. `freecad_export_step` for STEP plus geometry manifest.

Assign deterministic `semantic_id` values such as `air`, `core`, `primary_pos`, `beam`, `inlet`, or `conductor`. Do not rely on object creation order. A headless FreeCAD screenshot can legitimately be `BLOCKED`; use ParaView for verified field images.

## Stage 2: Elmer case and semantic mesh

Use this dependency order:

1. `elmer_case_create(project, analysis_type=<profile>)`.
2. `elmer_geometry_import` with STEP and geometry manifest.
3. `elmer_mesh_generate` with explicit size/order.
4. `elmer_mesh_convert`.
5. `elmer_mesh_inspect`.
6. `elmer_case_inspect`.

Reject the mesh when coordinate units, topology dimension, physical groups, semantic body/boundary mapping, element counts, or expected boundaries are wrong. STEP is geometry, not a finite-element mesh; Elmer owns meshing and solver-format conversion.

## Stage 3: Elmer physics and native solve

1. Apply every material with `elmer_material_set`.
2. Apply the allowlisted solver profile with `elmer_equation_set`.
3. Apply body sources using `elmer_excitation_set` only where that profile permits them.
4. Apply geometry-derived conditions with `elmer_boundary_set`.
5. Run `elmer_sif_generate`, then `elmer_sif_validate`.
6. Run `elmer_solver_run` with bounded timeout and approved serial mode unless another mode has its own validation.
7. Check `elmer_job_status`, `elmer_log_inspect`, and `elmer_result_inspect`.

Require process exit code 0, `Elmer Solver: ALL DONE`, no fatal/unknown-keyword diagnostics, correct native step count, expected VTU/PVD files, expected arrays, finite values, and profile-specific gates. Preserve raw solver output when deterministic derived fields are added.

## Stage 4: ParaView postprocessing

1. `paraview_session_start` in headless mode.
2. `paraview_dataset_open` on the real VTU or PVD.
3. `paraview_dataset_inspect` before naming arrays in filters or color maps.
4. Create only allowlisted filters using `paraview_filter_create`.
5. Inspect scalar ranges with `paraview_scalar_range`; then use `paraview_color_by`.
6. Set/fit the camera, render, and export the required PNG/CSV/animation.
7. Save state with `paraview_state_save` and inspect it with `paraview_pipeline_inspect`.
8. Stop the session using `paraview_session_stop`.

Use actual field associations and names from inspection. For multi-step data, verify the time-value count equals the native result count. Never animate a one-step dataset by merely changing the camera and call it transient physics.

## Stage 5: evidence package

Store, at minimum:

- geometry and mesh manifests;
- structured case model and generated SIF;
- process/job metadata and solver log;
- result inspection, physics-gate summary, and sensitivity table;
- postprocessing pipeline inspection, plots, CSV, images, frames, and PVSM;
- MCP call trace and SHA-256 artifact hashes.

Keep full native artifacts under the configured project workspace. Copy only curated, license-safe, compact evidence into the Git repository.

## Failure attribution

- Geometry/semantic failure belongs to FreeCAD or the FreeCAD-to-mesh contract.
- Physical-group, conversion, SIF, or solve failure belongs to Elmer/Gmsh.
- Missing arrays, filters, rendering, or session loss belongs to ParaView.
- A report or video that overstates the underlying solve is a presentation failure even if every program exited successfully.

Do not make the servers call each other. Let the controlling agent coordinate their explicit artifacts and statuses.
