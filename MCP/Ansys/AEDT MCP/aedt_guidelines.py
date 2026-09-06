from __future__ import annotations

GUIDELINE_TOPICS = (
    "workflow",
    "hfss",
    "maxwell",
    "icepak",
    "circuit",
    "geometry",
    "mesh",
    "boundaries",
    "postprocessing",
    "parametric",
)


_GUIDELINES = {
    "workflow": """
AEDT/PyAEDT workflow:
1. Check installation and list sessions.
2. Launch or connect to one explicit PID or gRPC port.
3. Create or open a project and design, then read back design type and settings.
4. Build geometry, materials, excitations, boundaries, mesh operations, setup, and sweeps.
5. Run validate_design before analyze_design.
6. Treat asynchronous submission as started, not solved. Poll solver state and inspect AEDT messages.
7. Export configuration, convergence, mesh, numerical results, and screenshots as evidence.
8. Check solver-specific physical balances and convergence before accepting engineering results.
""",
    "hfss": """
HFSS workflow:
- Select the correct solution type (Modal, Terminal, Eigenmode, SBR+, or Transient).
- Verify units, conductor/dielectric assignments, radiation or PML region, ports, integration lines, and reference conductors.
- Use a frequency-appropriate adaptive setup and sweep; inspect adaptive convergence and port mode fields.
- Review S-parameters, energy or loss balance, mesh statistics, and field plots. A successful solve alone is not proof of a valid EM model.
""",
    "maxwell": """
Maxwell workflow:
- Choose 2D/3D and magnetostatic, eddy-current, transient, or electrostatic physics deliberately.
- Verify nonlinear material curves, winding polarity/turns, motion bands, symmetry, return paths, and initial conditions.
- Check force/torque consistency, energy balance, time-step convergence, mesh refinement in gaps, and demagnetization or saturation where relevant.
""",
    "icepak": """
Icepak workflow:
- Create an Icepak design and verify model units, gravity direction, ambient/reference pressure, and steady or transient formulation.
- Define the fluid region/enclosure, openings, walls, fans or blowers, flow resistances, radiation settings, and turbulence model.
- Assign solid/fluid materials and temperature-dependent properties; represent electronics losses with block, surface, network, or volumetric sources.
- Refine mesh at heat sources, thin gaps, boundary layers, jets, fans, and recirculation regions. Check mesh quality before solving.
- Validate the design, solve, then inspect residual histories, monitor stabilization, maximum component temperature, pressure drop, mass-flow conservation, and heat balance.
- Export mesh/convergence evidence and temperature/velocity/pressure plots. Solver completion does not independently validate thermal assumptions or product limits.
""",
    "circuit": """
Circuit workflow:
- Confirm component models, pin mapping, reference nodes, sources, terminations, analysis type, and parameter units.
- Validate linked field-solver blocks and model-file paths.
- Inspect convergence, passivity/causality where relevant, time/frequency resolution, and expected conservation or limiting behavior.
""",
    "geometry": """
Geometry guidance:
- Set model units before creating objects and use deterministic object names.
- Prefer parameterized primitives and explicit coordinate systems.
- Read back dimensions, positions, topology counts, materials, and boolean results after construction.
- Remove unintended slivers, overlaps, duplicates, and disconnected volumes before meshing.
""",
    "mesh": """
Mesh guidance:
- Start from physics-driven length scales, skin depth, gaps, boundary layers, wavelengths, and gradients.
- Add local operations at ports, interfaces, losses, narrow passages, and high-field or high-gradient regions.
- Check element quality/statistics and perform a mesh-convergence study for decision-critical outputs.
""",
    "boundaries": """
Boundary and excitation guidance:
- Use named selections or stable object/face identities where possible.
- Confirm assignment targets, orientation, polarity, reference conductor, magnitude, phase, units, and coordinate system.
- Read assignments back from AEDT and check for missing, duplicated, or conflicting conditions before solving.
""",
    "postprocessing": """
Postprocessing guidance:
- Request quantities tied to the engineering question and record setup, sweep, variation, phase/time, and coordinate system.
- Export numerical data in addition to screenshots.
- Check convergence, balances, extrema locations, interpolation choices, and units; retain AEDT/PyAEDT logs and solver messages.
""",
    "parametric": """
Parametric guidance:
- Parameterize only controlled inputs with explicit units and bounds.
- Define outputs and feasibility checks before launching a sweep.
- Use reproducible sampling, retain failed points, and verify optimum candidates with an independent refinement or confirmation solve.
""",
}


def get_guidelines(content: str) -> str:
    normalized = content.strip().lower()
    if normalized not in _GUIDELINES:
        raise ValueError(
            f"unsupported guideline topic: {content}; supported: "
            + ", ".join(GUIDELINE_TOPICS)
        )
    return _GUIDELINES[normalized].strip()
