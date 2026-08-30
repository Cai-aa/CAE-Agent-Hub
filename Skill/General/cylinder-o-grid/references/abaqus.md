# Abaqus/CAE adapter

Use this adapter only for Abaqus/CAE execution. The generic topology and planning logic remain valid for other preprocessors, but the bundled builder, object names, element codes, mesh checks, and `.cae` output below are Abaqus-specific.

## New straight cylinder

Use `scripts/abaqus_build_ogrid.py` for a clean cylinder aligned with global Z. The script:

1. Extrudes a clean circular cylinder first.
2. Partitions one end face with the centered square and four diagonal connectors.
3. Extrudes the square edges through the solid to create the center cell and outer ring.
4. Extrudes the connector edges through the outer ring to create four outer cells.
5. Rejects the part unless Abaqus reports five cells.
6. Finds edges by geometric points rather than stored edge indices.
7. Seeds square/arc, connector, and axial edge families independently.
8. Applies `HEX` plus `STRUCTURED` controls and the requested brick element type.
9. Generates the mesh, verifies the analytical element count, and invokes Abaqus mesh-quality checks.

Run `--dry-run` first. Use `--replace-model` only when deletion of an existing model with the same name is intentional.

## Existing cylinder

Do not rebuild a production part merely to use the script.

1. Identify a planar circular end face and the full-length sweep direction.
2. Create a face-aligned sketch transform.
3. Draw the centered square and four vertex-to-circumference connectors.
4. Partition the end face by sketch.
5. Propagate the partition edges through the entire solid with an extrude/sweep cell partition operation.
6. Confirm one center cell plus four outer cells and no sliver cells.
7. Prefer structured hex controls on all five cells. If the adapted geometry requires Sweep, prove the source faces and axial sweep paths explicitly.
8. Seed matching topological edge families with equal counts.
9. Generate the mesh and check shared nodes across all partitions.

If the part contains fillets, holes, contacts, material interfaces, or changing radius, stop and redesign the multiblock topology. Do not force the five-block template through incompatible geometry.

## Element formulation

Map the generic `HEX8` family to an Abaqus formulation explicitly:

- Use `C3D8R` only when reduced integration is appropriate and hourglass/energy behavior will be audited.
- Use `C3D8` when full integration is required and locking is acceptable for the material/problem.
- Use `C3D8I` only for supported Abaqus/Standard use cases where incompatible modes are justified.
- Never silently substitute tetrahedra, wedges, or a different formulation.

For Explicit analyses, inspect stable time increment, mass scaling/added mass, hourglass energy, element distortion, and negative volume in addition to CAE mesh checks.

## Live automation discipline

Use registered Abaqus tools only. Prove the real session, set a controlled work directory, inspect model/part names, and save a checkpoint before mutation. Capture script output and CAE artifacts. If execution cannot be observed, report the script as prepared but unverified.
