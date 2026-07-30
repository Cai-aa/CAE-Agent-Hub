from pathlib import Path

from ovito.io import export_file, import_file


input_path = Path("outputs/trajectory.lammpstrj")
output_path = Path("exports/frame-0000.xyz")

pipeline = import_file(input_path)
export_file(pipeline, output_path, "xyz", frame=0, columns=["Particle Type", "Position.X", "Position.Y", "Position.Z"])
print("OVITO_PIPELINE_EXPORT_OK")
