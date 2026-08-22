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

"""Generate STEP geometry files for PyMechanical MCP examples."""

import cadquery as cq

# 1. Simple Cantilever Beam (200mm x 20mm x 10mm)
beam = cq.Workplane("XY").box(200, 20, 10)
cq.exporters.export(beam, "cantilever_beam/beam.step")
print("Created: cantilever_beam/beam.step")

# 2. L-Bracket for Modal Analysis
# Vertical plate: 100mm tall x 80mm wide x 5mm thick
# Horizontal plate: 60mm long x 80mm wide x 5mm thick
bracket = (
    cq.Workplane("XZ")
    .moveTo(0, 0)
    .lineTo(60, 0)  # horizontal leg
    .lineTo(60, 5)  # up thickness
    .lineTo(5, 5)  # back along top of horizontal
    .lineTo(5, 100)  # up vertical leg
    .lineTo(0, 100)  # across top of vertical
    .close()
    .extrude(80)  # 80mm wide (Y direction)
)
# Add mounting holes in horizontal leg
bracket = (
    bracket.faces("<Z")
    .workplane()
    .pushPoints([(15, 20), (15, 60)])
    .hole(8)  # 8mm diameter mounting holes
)
# Add a hole in the vertical plate (for visual interest)
bracket = (
    bracket.faces(">X")
    .workplane(centerOption="CenterOfBoundBox")
    .center(0, 25)
    .hole(15)  # 15mm diameter hole
)
cq.exporters.export(bracket, "bracket_modal/bracket.step")
print("Created: bracket_modal/bracket.step")

# 3. Plate with Circular Hole (stress concentration)
# 200mm x 100mm x 5mm plate with central hole
plate = cq.Workplane("XY").box(200, 100, 5).faces(">Z").workplane().hole(30)  # 30mm central hole
cq.exporters.export(plate, "plate_with_hole/plate.step")
print("Created: plate_with_hole/plate.step")

print("\nAll geometry files generated successfully!")
