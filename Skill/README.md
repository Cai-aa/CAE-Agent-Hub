# Finite Element Simulation Skills

This directory keeps reusable CAE simulation skills grouped by solver or domain.

The current layout is:

| Folder | Contents |
| --- | --- |
| `abaqus/core` | Main Abaqus workflow skill. |
| `abaqus/modeling` | Geometry, material, interaction, and mesh skills. |
| `abaqus/setup` | Loads, boundary conditions, steps, amplitudes, fields, outputs, and docs. |
| `abaqus/analysis` | Static, dynamic, modal, thermal, contact, coupled, and fatigue analysis skills. |
| `abaqus/execution` | Job submission and export skills. |
| `abaqus/postprocessing` | ODB/result post-processing skills. |
| `abaqus/optimization` | Topology, shape, and general optimization skills. |
| `abaqus/reference` | General FEA and FEniCS reference skills that are useful beside Abaqus workflows. |
| `CST` | CST Studio Suite electromagnetic simulation workflow skills for use with the CST MCP. |
| `fep-agent-hub` | Evidence-first FreeCAD, Elmer FEM, and ParaView orchestration with six verified CAE profiles. |

See [abaqus/README.md](abaqus/README.md) for the full skill index, upstream attribution, and client setup examples.
See [CST/README.md](CST/README.md) for CST workflow skills.
See [fep-agent-hub/SKILL.md](fep-agent-hub/SKILL.md) for the FEP orchestration workflow and its benchmark references.

Chinese version: [README.zh-CN.md](README.zh-CN.md).
