# Composite Curing Simulation Skill

A comprehensive Abaqus simulation skill for composite material curing with mold contact, friction, temperature-dependent material states, and Model Change springback analysis.

## Overview

This skill provides a complete workflow for simulating the composite curing process in Abaqus, including:

- **Mold contact** with temperature-dependent friction (0.45 → 0.2 → 0.169)
- **4-step curing process**: viscous → rubbery → glassy → springback
- **Model Change demolding** for realistic springback physics
- **UMAT subroutine** (Threestep.for) for three-state composite material
- **Batch dataset generation** from template INP files
- **Automated ODB extraction** to CSV with spring-in angle calculation

## Critical: P8_mold vs P8_only

| Feature | P8_mold (Correct) | P8_only (Incorrect) |
|---------|-------------------|---------------------|
| Mold part | TOOL-1 present | Absent |
| Contact | S1↔S4+S6, HARD, friction | None |
| Curing constraint | Mold contact (friction) | ENCASTRE (full fixity) |
| Demolding | Model Change in sp step | None |
| Springback contour | **Asymmetric** (correct) | **Center-symmetric** (wrong) |
| Spring-in angle | Positive (0.5°-1.6°) | Unphysical |

**Always use `P8_mold_V2.inp` as the template.** See `SKILL.md` for detailed explanation.

## Skill Architecture

```
composite-curing-simulation/
├── SKILL.md                           # Master router
├── README.md                          # This file
├── README.zh-CN.md                    # Chinese version
├── core/
│   └── composite-curing/              # Main routing logic
├── modeling/
│   ├── composite-layup/               # Ply angles, thickness, count
│   ├── mold-geometry/                 # Tool/mold part setup
│   └── composite-mesh/                # C3D8 mesh, through-thickness
├── setup/
│   ├── curing-material/               # UMAT, COM/TOOL materials
│   ├── curing-contact/                # Contact pairs, friction ★
│   ├── curing-bc/                     # Boundary conditions ★
│   ├── curing-load/                   # Pressure on inner surface
│   └── curing-temperature/            # Temperature fields
├── analysis/
│   ├── curing-steps/                  # 4-step process (vis/rub/glassy/sp)
│   └── springback-analysis/           # Model Change, mold removal
├── execution/
│   ├── curing-job/                    # Job submission with UMAT
│   └── socket-bridge/                 # Socket bridge connection
├── postprocessing/
│   ├── odb-extraction/                # ODB field output reading
│   └── csv-export/                    # CSV with coords + displacement
└── reference/
    └── curing-parameters/             # Complete parameter tables
```

★ = Strengthened with mold constraint details

## Related Skill

**[abaqus-odb-extraction](../abaqus-odb-extraction/SKILL.md)** — Standalone skill for batch ODB extraction, spring-in angle calculation (SVD dual-arm plane fit), and standardized contour screenshots with mold hidden. Includes complete API reference, filesystem isolation guide, and error troubleshooting table.

## Key Parameters

| Parameter | Value |
|-----------|-------|
| Template INP | P8_mold_V2.inp |
| UMAT | Threestep.for (4434 bytes) |
| Ply count | 8 |
| Ply thickness | 0.250 mm |
| Angle options | {-45, 0, 45, 90} |
| Nodes per case | 5445 (P8-1 instance) |
| ODB size | ~122.4 MB/case |
| Friction | vis=0.45, rub=0.2, glassy=0.169 |
| Pressure | 0.6 MPa on S2 (inner surface) |
| Springback step | sp (Model Change + Set-2 BC) |

## Dataset Statistics (100 cases)

| Statistic | Value |
|-----------|-------|
| Total cases | 100 |
| Success rate | 100% |
| Spring-in mean | 1.22° |
| Spring-in std | 0.20° |
| Spring-in range | 0.51° - 1.64° |
| All positive | Yes (physically correct) |

## Quick Start

1. **Single case**: Use `core/composite-curing` to route to appropriate sub-skills
2. **Batch dataset**: Follow the "Dataset Generation" section in `SKILL.md`
3. **ODB extraction**: Use the standalone `abaqus-odb-extraction` skill
4. **Screenshots**: Use `abq2020.bat cae noGUI` with `LeafFromPartInstance` to hide mold

## Files

- `P8_mold_V2.inp` — Correct template (with mold)
- `P8_only_recipe_1.inp` — Incorrect template (archived, do NOT use)
- `Threestep.for` — UMAT subroutine
- `abaqusis.env` — Environment configuration

## Version

Updated: 2026-07-14
