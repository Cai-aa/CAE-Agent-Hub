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

"""Shared photonic-integrated-circuit guidance for optical solvers."""

from __future__ import annotations


def get_guidelines_for_pic() -> str:
    """Shared PIC simulation hygiene for FDTD, MODE, and FEEM optical tasks."""
    return """# PIC Simulation Basics

This topic covers shared guided-wave photonic simulation rules for
optical elements such as waveguides, bends, couplers, tapers, and
fiber-coupled structures. It is meant to complement solver-specific
topics such as ``fdtd_workflow``, ``mode_fde_workflow``,
``mode_eme_workflow``, and ``mode_varfdtd_workflow``.

Read ``workflow`` first for the generic MCP execution model. Fetch this
topic whenever the task is an optical simulation of a photonic element
using FDTD, MODE, or FEEM.

## Extend Guided Structures Through PML

When an FDTD-family simulation uses PML boundaries, geometries through
which the guided optical mode propagates should typically continue
through the PML boundary instead of ending abruptly at the edge of the
interior simulation region.

- This applies to structures such as straight waveguides, bent
  waveguides, substrates, and claddings when they are intended to keep
  continuing past the modeled device.
- Waveguides should not terminate abruptly near the propagation-axis PML
  unless the reflection is intentional.
- Extending the guided structure through the PML reduces artificial back
  reflection from the truncated geometry.
- Apply this along the propagation direction only. Do not invent extra
  extension in transverse directions that are physically finite.

## Solver Window and Port Span Hygiene

For FDTD ports, EME ports, varFDTD ports, FDE solver regions, and FEEM
mode-solver windows, the solver cross-section should typically extend
about ``0.5`` to ``1`` times the simulation wavelength beyond the edge
of the geometry that confines the optical mode.

- Use the optical confinement boundary, such as the waveguide core or
  fiber core, not the full chip outline.
- This padding is usually needed on both sides of the confined region so
  the modal fields decay before reaching the solver boundary.
- If a design has a substrate below the waveguide, include only the part
  of the substrate that the user explicitly asks for or that the mode
  analysis actually requires. (note that in most cases substrate should
  not be included in the mode calculation, to avoid accidentally
  selecting substrate modes instead of guided modes)
- Do not silently make the solver window enormous just because the full
  substrate is large.

## Avoid Selecting Substrate Modes By Accident

If substrate is included in a mode calculation, check that the injected,
collected, or reported TE/TM modes are actually supported by the main
waveguide geometry rather than by the substrate, unless the user
explicitly intends a substrate mode.

- Do not assume a raw mode index or the first reported TE/TM-like mode is
  automatically the desired guided mode.
- Inspect confinement and polarization to confirm that the chosen mode is
  localized to the intended guiding structure.
- If the solver finds substrate-supported modes, adjust the solver window
  or explicitly select the mode family that belongs to the main
  waveguide.

See also: ``workflow``, ``geometry``, ``fdtd_workflow``,
``mode_fde_workflow``, ``mode_fde_results``, ``mode_eme_workflow``,
``mode_varfdtd_workflow``.
"""


__all__ = ["get_guidelines_for_pic"]
