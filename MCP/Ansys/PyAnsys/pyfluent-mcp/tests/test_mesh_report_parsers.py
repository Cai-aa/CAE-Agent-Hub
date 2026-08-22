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

from ansys.fluent.mcp.solve.backends.mesh_report_parsers import parse_mesh_check, parse_mesh_quality


def test_parse_mesh_quality_extracts_headline_values():
    """Verify that parse mesh quality extracts headline values.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    parsed = parse_mesh_quality(
        """
        Minimum Orthogonal Quality = 1.234e-02 cell 10 on zone 2
        Maximum Ortho Skew = 9.876e-01 cell 11 on zone 2
        Maximum Aspect Ratio = 42.5 cell 12 on zone 3
        """
    )

    assert parsed == {
        "min_orthogonal_quality": 0.01234,
        "max_ortho_skew": 0.9876,
        "max_aspect_ratio": 42.5,
    }


def test_parse_mesh_quality_returns_none_for_missing_values():
    """Verify that parse mesh quality returns none for missing values.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    assert parse_mesh_quality(None) == {
        "min_orthogonal_quality": None,
        "max_ortho_skew": None,
        "max_aspect_ratio": None,
    }


def test_parse_mesh_check_extracts_numbers_and_filters_scheme_noise():
    """Verify that parse mesh check extracts numbers and filters scheme noise.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    parsed = parse_mesh_check(
        """
(before)
(api-get-attr noisy internal trace)
Checking mesh...
Domain Extents:
  x-coordinate: min (m) = -1.0, max (m) = 1.0
  y-coordinate: min (m) = 0.0, max (m) = 2.0
  z-coordinate: min (m) = 3.0e-01, max (m) = 4.0e-01
 Volume statistics:
  minimum volume (m3): 1.0e-09
  maximum volume (m3): 2.0e-03
  total volume (m3): 3.0e-01
 Face area statistics:
  minimum face area (m2): 4.0e-06
  maximum face area (m2): 5.0e-02
Warning: left handed face detected
Error: negative volume detected
Done.
        """
    )

    assert parsed["domain_extents"] == {"x": (-1.0, 1.0), "y": (0.0, 2.0), "z": (0.3, 0.4)}
    assert parsed["volume_min"] == 1.0e-09
    assert parsed["volume_max"] == 2.0e-03
    assert parsed["volume_total"] == 3.0e-01
    assert parsed["face_area_min"] == 4.0e-06
    assert parsed["face_area_max"] == 5.0e-02
    assert parsed["warnings"] == ["left handed face detected"]
    assert parsed["errors"] == ["negative volume detected"]
    assert "api-get-attr" not in parsed["raw"]
    assert "Checking mesh" in parsed["raw"]


def test_parse_mesh_check_empty_output_shape():
    """Verify that parse mesh check empty output shape.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    parsed = parse_mesh_check(None)

    assert parsed["domain_extents"] == {"x": None, "y": None, "z": None}
    assert parsed["warnings"] == []
    assert parsed["errors"] == []
    assert parsed["raw"] == ""
