from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

from .projects import ProjectService
from .settings import safe_filename, within


NAME_RE = re.compile(r"[A-Za-z0-9_. -]{1,80}\Z")


def _positive(value: Any, name: str, maximum: float = 1.0e20) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(result) or not 0.0 < result <= maximum:
        raise ValueError(f"{name} must be finite and in (0, {maximum}]")
    return result


def _dimensions(values: list[float]) -> tuple[float, float, float]:
    if not isinstance(values, list) or len(values) != 3:
        raise ValueError("dimensions must contain [length, width, height]")
    return tuple(_positive(value, f"dimensions[{index}]") for index, value in enumerate(values))


def _divisions(values: list[int]) -> tuple[int, int, int]:
    if not isinstance(values, list) or len(values) != 3:
        raise ValueError("divisions must contain [nx, ny, nz]")
    result = tuple(int(value) for value in values)
    if any(value < 1 or value > 200 for value in result):
        raise ValueError("Each mesh division must be between 1 and 200")
    if result[0] * result[1] * result[2] > 500000:
        raise ValueError("The structured mesh may contain at most 500000 elements")
    return result


def _direction(values: list[float]) -> tuple[float, float, float]:
    if not isinstance(values, list) or len(values) != 3:
        raise ValueError("force_direction must contain three values")
    try:
        result = tuple(float(value) for value in values)
    except (TypeError, ValueError) as exc:
        raise ValueError("force_direction must contain numeric values") from exc
    if not all(math.isfinite(value) for value in result):
        raise ValueError("force_direction must contain finite values")
    length = math.sqrt(sum(value * value for value in result))
    if length <= 1.0e-12:
        raise ValueError("force_direction must have non-zero length")
    return tuple(value / length for value in result)


def _field(value: float) -> str:
    return f"{value:.12g}"


def _rad_float(value: float) -> str:
    """Format one Radioss Block Format real field (20 columns)."""
    return f"{float(value):20.12g}"


def _rad_int(value: int) -> str:
    """Format one Radioss Block Format integer field (10 columns)."""
    return f"{int(value):10d}"


def _rad_block_mesh(
    origin: tuple[float, float, float],
    dimensions: tuple[float, float, float],
    divisions: tuple[int, int, int],
    part_id: int,
    first_node_id: int,
    first_element_id: int,
) -> tuple[list[str], list[str], list[int], int, int]:
    """Create a structured HEXA8 block using Radioss /NODE and /BRICK fields."""
    ox, oy, oz = origin
    lx, ly, lz = dimensions
    nx, ny, nz = divisions
    node_ids: dict[tuple[int, int, int], int] = {}
    node_lines: list[str] = []
    node_id = first_node_id
    for k in range(nz + 1):
        z = oz + lz * k / nz
        for j in range(ny + 1):
            y = oy + ly * j / ny
            for i in range(nx + 1):
                x = ox + lx * i / nx
                node_ids[(i, j, k)] = node_id
                node_lines.append(
                    _rad_int(node_id) + _rad_float(x) + _rad_float(y) + _rad_float(z)
                )
                node_id += 1

    element_lines: list[str] = []
    element_id = first_element_id
    for k in range(nz):
        for j in range(ny):
            for i in range(nx):
                connectivity = (
                    node_ids[(i, j, k)],
                    node_ids[(i + 1, j, k)],
                    node_ids[(i + 1, j + 1, k)],
                    node_ids[(i, j + 1, k)],
                    node_ids[(i, j, k + 1)],
                    node_ids[(i + 1, j, k + 1)],
                    node_ids[(i + 1, j + 1, k + 1)],
                    node_ids[(i, j + 1, k + 1)],
                )
                element_lines.append(
                    "".join(
                        [_rad_int(element_id), *(_rad_int(value) for value in connectivity)]
                    )
                )
                element_id += 1
    return node_lines, element_lines, list(node_ids.values()), node_id, element_id


def build_radioss_block_impact_decks(
    name: str,
    impactor_dimensions: list[float],
    impactor_divisions: list[int],
    target_dimensions: list[float],
    target_divisions: list[int],
    initial_gap: float,
    initial_velocity: float,
    end_time: float,
    output_interval: float,
    youngs_modulus: float,
    poissons_ratio: float,
    density: float,
    yield_stress: float,
    hardening_modulus: float,
    hardening_exponent: float,
    friction: float = 0.1,
) -> tuple[str, str, dict[str, Any]]:
    """Build a compact LAW2 + SOLID + TYPE7 Radioss impact benchmark.

    Units are kg, mm, ms.  The impactor travels in +X toward a fully fixed
    target.  Both bodies use the same Johnson-Cook elastic-plastic material;
    the fixed target provides a stable regression fixture without a rigid-wall
    keyword dependency.
    """
    title = str(name).strip()
    if not NAME_RE.fullmatch(title):
        raise ValueError("name may contain only letters, numbers, spaces, dot, dash, and underscore")
    impactor_size = _dimensions(impactor_dimensions)
    impactor_mesh = _divisions(impactor_divisions)
    target_size = _dimensions(target_dimensions)
    target_mesh = _divisions(target_divisions)
    gap = _positive(initial_gap, "initial_gap", 1.0e9)
    velocity = _positive(initial_velocity, "initial_velocity", 1.0e9)
    termination = _positive(end_time, "end_time", 1.0e9)
    interval = _positive(output_interval, "output_interval", termination)
    if interval > termination:
        raise ValueError("output_interval must not exceed end_time")
    young = _positive(youngs_modulus, "youngs_modulus")
    poisson = float(poissons_ratio)
    if not math.isfinite(poisson) or not -0.99 < poisson < 0.4999:
        raise ValueError("poissons_ratio must be finite and in (-0.99, 0.4999)")
    rho = _positive(density, "density")
    sigma_y = _positive(yield_stress, "yield_stress")
    hardening = _positive(hardening_modulus, "hardening_modulus")
    exponent = _positive(hardening_exponent, "hardening_exponent", 10.0)
    mu = float(friction)
    if not math.isfinite(mu) or not 0.0 <= mu <= 2.0:
        raise ValueError("friction must be finite and in [0, 2]")

    ix, iy, iz = impactor_size
    tx, ty, tz = target_size
    impactor_origin = (0.0, (ty - iy) / 2.0, (tz - iz) / 2.0)
    target_origin = (ix + gap, 0.0, 0.0)
    impactor_nodes, impactor_elements, impactor_node_ids, next_node, next_element = (
        _rad_block_mesh(
            impactor_origin,
            impactor_size,
            impactor_mesh,
            part_id=1,
            first_node_id=1,
            first_element_id=1,
        )
    )
    target_first_node = next_node
    target_nodes, target_elements, target_node_ids, next_node, next_element = _rad_block_mesh(
        target_origin,
        target_size,
        target_mesh,
        part_id=2,
        first_node_id=next_node,
        first_element_id=next_element,
    )
    target_nx, target_ny, target_nz = target_mesh
    fixed_node_ids = [
        target_first_node
        + k * (target_ny + 1) * (target_nx + 1)
        + j * (target_nx + 1)
        + target_nx
        for k in range(target_nz + 1)
        for j in range(target_ny + 1)
    ]
    fixed_node_lines = [
        "".join(_rad_int(value) for value in fixed_node_ids[index : index + 10])
        for index in range(0, len(fixed_node_ids), 10)
    ]
    root_name = re.sub(r"[^A-Za-z0-9_-]+", "_", title).strip("_")[:48] or "impact"
    # /BRICK/<part_ID> assigns every following brick to that part.
    starter_lines = [
        "#RADIOSS STARTER",
        "# Generated by HyperWorks MCP 0.10.0",
        "/BEGIN",
        root_name,
        f"{2026:10d}{0:10d}",
        f"{'kg':>20}{'mm':>20}{'ms':>20}",
        f"{'kg':>20}{'mm':>20}{'ms':>20}",
        "/TITLE",
        title,
        "/MAT/PLAS_JOHNS/1",
        "Steel LAW2",
        _rad_float(rho),
        _rad_float(young) + _rad_float(poisson) + _rad_int(0),
        _rad_float(sigma_y)
        + _rad_float(hardening)
        + _rad_float(exponent)
        + _rad_float(0.0)
        + _rad_float(0.0),
        _rad_float(0.0) + _rad_float(1.0) + _rad_int(0) + _rad_int(0) + _rad_float(0.0) + _rad_float(0.0),
        _rad_float(0.0) + _rad_float(0.0) + _rad_float(0.0) + _rad_float(0.0),
        "/PROP/SOLID/1",
        "Solid property",
        f"{24:10d}{0:10d}{'':10s}{0:10d}{'':10s}{0:10d}{0:10d}{0:10d}{0.0:20.1f}",
        _rad_float(1.1) + _rad_float(0.05) + _rad_float(0.1) + _rad_float(0.0) + _rad_float(0.0),
        _rad_float(0.0)
        + _rad_float(0.0)
        + _rad_float(0.0)
        + _rad_float(0.0)
        + _rad_float(0.0),
        _rad_int(0) + _rad_int(0) + _rad_int(0),
        "/NODE",
        *impactor_nodes,
        *target_nodes,
        "/BRICK/1",
        *impactor_elements,
        "/BRICK/2",
        *target_elements,
        "/BCS/1",
        "Fixed target",
        f"{'111':>6}{'111':>4}{0:10d}{2:10d}",
        "/GRNOD/NODE/2",
        "Target back-face nodes",
        *fixed_node_lines,
        "/INIVEL/TRA/2",
        "Impactor velocity",
        _rad_float(velocity) + _rad_float(0.0) + _rad_float(0.0) + _rad_int(1) + _rad_int(0),
        _rad_float(0.0) + _rad_int(0),
        "/GRNOD/PART/1",
        "Impactor nodes",
        f"{1:10d}",
        "/INTER/TYPE7/1",
        "Impactor to fixed target",
        f"{3:10d}{4:10d}{4:10d}{0:10d}{0:10d}{'':10s}{0:10d}{0:10d}{0:10d}{0:10d}",
        _rad_float(0.0) + _rad_float(0.0) + _rad_float(0.0),
        _rad_float(0.0) + _rad_float(0.0) + f"{'':20s}" + _rad_float(0.0) + _rad_int(0) + _rad_int(0),
        _rad_float(1.0) + _rad_float(mu) + _rad_float(0.0) + _rad_float(0.0) + _rad_float(0.0),
        f"{'000':>10}{'':20s}{0:10d}" + _rad_float(0.0) + _rad_float(0.0) + _rad_float(0.0),
        _rad_int(0) + _rad_int(0) + _rad_float(0.0) + _rad_int(2) + _rad_int(0) + _rad_int(0) + _rad_float(0.0),
        "/GRNOD/PART/3",
        "Impactor contact nodes",
        f"{1:10d}",
        "/SURF/PART/EXT/4",
        "Target external surface",
        f"{2:10d}",
        "/PART/1",
        "Impactor",
        f"{1:10d}{1:10d}{0:10d}",
        "/PART/2",
        "Fixed target",
        f"{1:10d}{1:10d}{0:10d}",
        "/TH/PART/1",
        "Part energies",
        "DEF",
        f"{1:10d}{2:10d}",
        "/TH/INTER/2",
        "Contact history",
        "DEF",
        f"{1:10d}",
        "/END",
        "",
    ]
    engine_lines = [
        "/RUN/{}/1/".format(root_name),
        _rad_float(termination),
        "/DT",
        _rad_float(0.9) + _rad_float(0.0),
        "/MON/ON",
        "/PRINT/-100/0",
        "/TFILE/0",
        _rad_float(interval / 10.0),
        "/ANIM/DT",
        _rad_float(0.0) + _rad_float(interval),
        "/ANIM/VECT/DISP",
        "/ANIM/VECT/VEL",
        "/ANIM/ELEM/EPSP",
        "/ANIM/ELEM/VONM",
        "/H3D/DT",
        _rad_float(0.0) + _rad_float(interval),
        "/H3D/NODA/DIS",
        "/H3D/NODA/VEL",
        "/H3D/SOLID/VONM",
        "/H3D/SOLID/EPSP",
        "/H3D/SOLID/TENS/STRESS/NPT=ALL",
        "/H3D/COMPRESS",
        _rad_float(0.01),
        "/STOP",
        "# Emax Mmax Nmax NTH NANIM NERR_POSIT",
        "0 0 0 1 1 0",
        "",
    ]
    impactor_element_count = math.prod(impactor_mesh)
    target_element_count = math.prod(target_mesh)
    metadata = {
        "analysis_type": "explicit_block_impact",
        "solver": "radioss",
        "unit_system": {"mass": "kg", "length": "mm", "time": "ms"},
        "property_chain": {
            "material": "/MAT/LAW2 (PLAS_JOHNS)",
            "property": "/PROP/SOLID",
            "element": "/BRICK",
        },
        "load_chain": {
            "load": "/INIVEL/TRA",
            "velocity_mm_per_ms": velocity,
            "node_group": "/GRNOD/PART/1",
        },
        "constraint_chain": {
            "constraint": "/BCS",
            "target_part_id": 2,
            "node_count": len(fixed_node_ids),
            "fixed_node_ids": fixed_node_ids,
        },
        "contact_chain": {
            "type": "/INTER/TYPE7",
            "secondary_group_id": 3,
            "main_surface_id": 4,
            "friction": mu,
        },
        "control_chain": {
            "starter": "*_0000.rad",
            "engine": "*_0001.rad",
            "end_time_ms": termination,
            "output_interval_ms": interval,
            "h3d_requests": True,
            "time_history": ["/TH/PART", "/TH/INTER"],
        },
        "quality_gates": {
            "normal_termination_required": True,
            "maximum_absolute_energy_error_percent": 15.0,
            "maximum_added_mass_percent": 5.0,
            "negative_volume_allowed": False,
            "contact_penetration_error_allowed": False,
        },
        "node_count": next_node - 1,
        "impactor_node_count": len(impactor_node_ids),
        "target_node_count": len(target_node_ids),
        "solid_element_count": impactor_element_count + target_element_count,
        "impactor_element_count": impactor_element_count,
        "target_element_count": target_element_count,
        "initial_gap_mm": gap,
    }
    return "\n".join(starter_lines), "\n".join(engine_lines), metadata


def build_optistruct_cantilever_deck(
    name: str,
    dimensions: list[float],
    divisions: list[int],
    youngs_modulus: float,
    poissons_ratio: float,
    density: float,
    total_force: float,
    force_direction: list[float],
    gap_contacts: list[dict[str, Any]] | None = None,
) -> tuple[str, dict[str, Any]]:
    title = str(name).strip()
    if not NAME_RE.fullmatch(title):
        raise ValueError("name may contain only letters, numbers, spaces, dot, dash, and underscore")
    length, width, height = _dimensions(dimensions)
    nx, ny, nz = _divisions(divisions)
    young = _positive(youngs_modulus, "youngs_modulus")
    poisson = float(poissons_ratio)
    if not math.isfinite(poisson) or not -0.99 < poisson < 0.4999:
        raise ValueError("poissons_ratio must be finite and in (-0.99, 0.4999)")
    rho = _positive(density, "density")
    force = _positive(abs(float(total_force)), "total_force")
    if float(total_force) < 0.0:
        force = -force
    direction = _direction(force_direction)
    contacts = gap_contacts or []
    if not isinstance(contacts, list) or len(contacts) > 1000:
        raise ValueError("gap_contacts must contain at most 1000 items")

    node_ids: dict[tuple[int, int, int], int] = {}
    grids: list[str] = []
    node_id = 1
    for k in range(nz + 1):
        z = height * k / nz
        for j in range(ny + 1):
            y = width * j / ny
            for i in range(nx + 1):
                x = length * i / nx
                node_ids[(i, j, k)] = node_id
                grids.append(
                    f"GRID,{node_id},,{_field(x)},{_field(y)},{_field(z)}"
                )
                node_id += 1

    elements: list[str] = []
    element_id = 1
    for k in range(nz):
        for j in range(ny):
            for i in range(nx):
                connectivity = (
                    node_ids[(i, j, k)],
                    node_ids[(i + 1, j, k)],
                    node_ids[(i + 1, j + 1, k)],
                    node_ids[(i, j + 1, k)],
                    node_ids[(i, j, k + 1)],
                    node_ids[(i + 1, j, k + 1)],
                    node_ids[(i + 1, j + 1, k + 1)],
                    node_ids[(i, j + 1, k + 1)],
                )
                first = ",".join(str(value) for value in connectivity[:6])
                second = ",".join(str(value) for value in connectivity[6:])
                elements.append(f"CHEXA,{element_id},1,{first}")
                elements.append(f"+,{second}")
                element_id += 1

    fixed_nodes = [node_ids[(0, j, k)] for k in range(nz + 1) for j in range(ny + 1)]
    loaded_nodes = [node_ids[(nx, j, k)] for k in range(nz + 1) for j in range(ny + 1)]
    constraints = [f"SPC1,1,123456,{value}" for value in fixed_nodes]
    per_node_force = force / len(loaded_nodes)
    loads = [
        "FORCE,2,{node},0,{mag},{x},{y},{z}".format(
            node=value,
            mag=_field(per_node_force),
            x=_field(direction[0]),
            y=_field(direction[1]),
            z=_field(direction[2]),
        )
        for value in loaded_nodes
    ]

    contact_cards: list[str] = []
    contact_metadata: list[dict[str, Any]] = []
    for index, item in enumerate(contacts):
        if not isinstance(item, dict):
            raise ValueError(f"gap_contacts[{index}] must be an object")
        grid_index = item.get("grid_index")
        if not isinstance(grid_index, list) or len(grid_index) != 3:
            raise ValueError(f"gap_contacts[{index}].grid_index must contain [i, j, k]")
        key = tuple(int(value) for value in grid_index)
        if key not in node_ids:
            raise ValueError(f"gap_contacts[{index}].grid_index is outside the mesh")
        position = item.get("ground_position")
        if not isinstance(position, list) or len(position) != 3:
            raise ValueError(
                f"gap_contacts[{index}].ground_position must contain [x, y, z]"
            )
        coordinates = tuple(float(value) for value in position)
        if not all(math.isfinite(value) for value in coordinates):
            raise ValueError(f"gap_contacts[{index}].ground_position must be finite")
        stiffness = _positive(item.get("stiffness"), f"gap_contacts[{index}].stiffness")
        initial_gap = float(item.get("initial_gap", 0.0))
        if not math.isfinite(initial_gap):
            raise ValueError(f"gap_contacts[{index}].initial_gap must be finite")
        ground_node = node_id
        node_id += 1
        grids.append(
            f"GRID,{ground_node},,{_field(coordinates[0])},{_field(coordinates[1])},{_field(coordinates[2])}"
        )
        constraints.append(f"SPC1,1,123456,{ground_node}")
        property_id = 1000 + index
        gap_element_id = element_id
        element_id += 1
        contact_cards.extend(
            [
                f"PGAP,{property_id},{_field(initial_gap)},0.0,{_field(stiffness)}",
                f"CGAP,{gap_element_id},{property_id},{node_ids[key]},{ground_node}",
            ]
        )
        contact_metadata.append(
            {
                "element_id": gap_element_id,
                "property_id": property_id,
                "structure_node_id": node_ids[key],
                "ground_node_id": ground_node,
            }
        )

    lines = [
        f"$ Generated by HyperWorks MCP: {title}",
        "SOL 101",
        "CEND",
        f"TITLE = {title}",
        "ECHO = NONE",
        "DISPLACEMENT(H3D) = ALL",
        "STRESS(H3D) = ALL",
        "SPCFORCES(H3D) = ALL",
        "FORCE(H3D) = ALL",
        "SUBCASE 1",
        "  ANALYSIS = STATICS",
        "  SPC = 1",
        "  LOAD = 2",
        "BEGIN BULK",
        "PARAM,POST,-1",
        f"MAT1,1,{_field(young)},,{_field(poisson)},{_field(rho)}",
        "PSOLID,1,1",
        *grids,
        *elements,
        *contact_cards,
        *constraints,
        *loads,
        "ENDDATA",
        "",
    ]
    metadata = {
        "analysis_type": "linear_static",
        "solver": "optistruct",
        "property_chain": {"material": "MAT1", "property": "PSOLID", "element": "CHEXA"},
        "load_chain": {"load": "FORCE", "set_id": 2, "node_count": len(loaded_nodes)},
        "constraint_chain": {"constraint": "SPC1", "set_id": 1, "node_count": len(fixed_nodes)},
        "contact_chain": {"type": "CGAP/PGAP", "contacts": contact_metadata},
        "control_chain": {"solution": "SOL 101", "subcase": 1, "h3d_requests": True},
        "node_count": node_id - 1,
        "solid_element_count": nx * ny * nz,
        "gap_element_count": len(contact_metadata),
        "total_element_count": element_id - 1,
        "fixed_node_ids": fixed_nodes,
        "loaded_node_ids": loaded_nodes,
        "total_force": force,
        "force_direction": list(direction),
    }
    return "\n".join(lines), metadata


def _optistruct_bulk_lines(deck: str) -> list[str]:
    lines = deck.splitlines()
    try:
        start = lines.index("BEGIN BULK") + 1
        end = lines.index("ENDDATA")
    except ValueError as exc:
        raise RuntimeError("Generated OptiStruct deck is missing BEGIN BULK/ENDDATA") from exc
    return lines[start:end]


def _optistruct_deck(
    title: str,
    solution: int,
    case_control: list[str],
    bulk: list[str],
    outputs: list[str] | None = None,
) -> str:
    return "\n".join(
        [
            f"$ Generated by HyperWorks MCP: {title}",
            f"SOL {solution}",
            "CEND",
            f"TITLE = {title}",
            "ECHO = NONE",
            *(outputs or ["DISPLACEMENT(H3D) = ALL", "STRESS(H3D) = ALL"]),
            *case_control,
            "BEGIN BULK",
            *bulk,
            "ENDDATA",
            "",
        ]
    )


def build_optistruct_modal_deck(
    name: str,
    dimensions: list[float],
    divisions: list[int],
    youngs_modulus: float,
    poissons_ratio: float,
    density: float,
    number_of_modes: int = 10,
) -> tuple[str, dict[str, Any]]:
    modes = int(number_of_modes)
    if not 1 <= modes <= 500:
        raise ValueError("number_of_modes must be between 1 and 500")
    base, metadata = build_optistruct_cantilever_deck(
        name, dimensions, divisions, youngs_modulus, poissons_ratio, density,
        1.0, [1.0, 0.0, 0.0],
    )
    bulk = [line for line in _optistruct_bulk_lines(base) if not line.startswith("FORCE,")]
    bulk.insert(-1 if bulk else 0, f"EIGRL,42,,,{modes}")
    deck = _optistruct_deck(
        str(name).strip(),
        103,
        ["SUBCASE 1", "  ANALYSIS = MODES", "  SPC = 1", "  METHOD = 42"],
        bulk,
        ["DISPLACEMENT(H3D) = ALL"],
    )
    metadata.update(
        analysis_type="normal_modes",
        load_chain={"load": None},
        control_chain={"solution": "SOL 103", "subcase": 1, "method": 42, "number_of_modes": modes, "h3d_requests": True},
    )
    for key in ("loaded_node_ids", "total_force", "force_direction"):
        metadata.pop(key, None)
    return deck, metadata


def build_optistruct_buckling_deck(
    name: str,
    dimensions: list[float],
    divisions: list[int],
    youngs_modulus: float,
    poissons_ratio: float,
    density: float,
    reference_force: float,
    force_direction: list[float],
    number_of_modes: int = 5,
) -> tuple[str, dict[str, Any]]:
    modes = int(number_of_modes)
    if not 1 <= modes <= 100:
        raise ValueError("number_of_modes must be between 1 and 100")
    base, metadata = build_optistruct_cantilever_deck(
        name, dimensions, divisions, youngs_modulus, poissons_ratio, density,
        reference_force, force_direction,
    )
    bulk = _optistruct_bulk_lines(base)
    bulk.insert(-1 if bulk else 0, f"EIGRL,42,,,{modes}")
    deck = _optistruct_deck(
        str(name).strip(),
        105,
        [
            "SUBCASE 1", "  LABEL = Reference static load", "  ANALYSIS = STATICS",
            "  SPC = 1", "  LOAD = 2",
            "SUBCASE 2", "  LABEL = Linear buckling", "  ANALYSIS = BUCK",
            "  SPC = 1", "  METHOD = 42", "  STATSUB(BUCKLING) = 1",
        ],
        bulk,
        ["DISPLACEMENT(H3D) = ALL", "STRESS(H3D) = ALL"],
    )
    metadata.update(
        analysis_type="linear_buckling",
        control_chain={"solution": "SOL 105", "static_subcase": 1, "buckling_subcase": 2, "method": 42, "number_of_modes": modes, "h3d_requests": True},
        reference_force=float(reference_force),
    )
    return deck, metadata


def build_optistruct_multicase_static_deck(
    name: str,
    dimensions: list[float],
    divisions: list[int],
    youngs_modulus: float,
    poissons_ratio: float,
    density: float,
    load_cases: list[dict[str, Any]],
) -> tuple[str, dict[str, Any]]:
    if not isinstance(load_cases, list) or not 2 <= len(load_cases) <= 50:
        raise ValueError("load_cases must contain between 2 and 50 cases")
    first = load_cases[0]
    if not isinstance(first, dict):
        raise ValueError("load_cases[0] must be an object")
    base, metadata = build_optistruct_cantilever_deck(
        name, dimensions, divisions, youngs_modulus, poissons_ratio, density,
        first.get("total_force"), first.get("force_direction"),
    )
    bulk = [line for line in _optistruct_bulk_lines(base) if not line.startswith("FORCE,")]
    case_control: list[str] = []
    case_metadata = []
    loaded_nodes = list(metadata["loaded_node_ids"])
    new_loads: list[str] = []
    for index, item in enumerate(load_cases, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"load_cases[{index - 1}] must be an object")
        label = str(item.get("name", f"Load case {index}")).strip()
        if not NAME_RE.fullmatch(label):
            raise ValueError(f"load_cases[{index - 1}].name is invalid")
        total = float(item.get("total_force"))
        if not math.isfinite(total) or abs(total) <= 0.0:
            raise ValueError(f"load_cases[{index - 1}].total_force must be finite and non-zero")
        direction = _direction(item.get("force_direction"))
        sid = 100 + index
        per_node = total / len(loaded_nodes)
        for node in loaded_nodes:
            new_loads.append(
                f"FORCE,{sid},{node},0,{_field(per_node)},{_field(direction[0])},{_field(direction[1])},{_field(direction[2])}"
            )
        case_control.extend(
            [f"SUBCASE {index}", f"  LABEL = {label}", "  ANALYSIS = STATICS", "  SPC = 1", f"  LOAD = {sid}"]
        )
        case_metadata.append({"subcase": index, "name": label, "load_set_id": sid, "total_force": total, "force_direction": list(direction)})
    bulk.extend(new_loads)
    deck = _optistruct_deck(
        str(name).strip(), 101, case_control, bulk,
        ["DISPLACEMENT(H3D) = ALL", "STRESS(H3D) = ALL", "SPCFORCES(H3D) = ALL", "FORCE(H3D) = ALL"],
    )
    metadata.update(
        analysis_type="multi_case_linear_static",
        load_chain={"load": "FORCE", "cases": case_metadata, "node_count_per_case": len(loaded_nodes)},
        control_chain={"solution": "SOL 101", "subcase_count": len(case_metadata), "h3d_requests": True},
    )
    return deck, metadata


def build_optistruct_thermal_stress_deck(
    name: str,
    dimensions: list[float],
    divisions: list[int],
    youngs_modulus: float,
    poissons_ratio: float,
    density: float,
    thermal_expansion: float,
    reference_temperature: float,
    applied_temperature: float,
) -> tuple[str, dict[str, Any]]:
    alpha = float(thermal_expansion)
    tref = float(reference_temperature)
    temperature = float(applied_temperature)
    if not all(math.isfinite(value) for value in (alpha, tref, temperature)):
        raise ValueError("thermal expansion and temperatures must be finite")
    if alpha == 0.0:
        raise ValueError("thermal_expansion must be non-zero")
    base, metadata = build_optistruct_cantilever_deck(
        name, dimensions, divisions, youngs_modulus, poissons_ratio, density,
        1.0, [1.0, 0.0, 0.0],
    )
    bulk = []
    for line in _optistruct_bulk_lines(base):
        if line.startswith("FORCE,"):
            continue
        if line.startswith("MAT1,1,"):
            bulk.append(f"MAT1,1,{_field(float(youngs_modulus))},,{_field(float(poissons_ratio))},{_field(float(density))},{_field(alpha)},{_field(tref)}")
        else:
            bulk.append(line)
    structural_nodes = int(metadata["node_count"])
    bulk.extend(f"TEMP,2,{node},{_field(temperature)}" for node in range(1, structural_nodes + 1))
    deck = _optistruct_deck(
        str(name).strip(),
        101,
        ["SUBCASE 1", "  LABEL = Thermal stress", "  ANALYSIS = STATICS", "  SPC = 1", "  TEMP(LOAD) = 2"],
        bulk,
        ["DISPLACEMENT(H3D) = ALL", "STRESS(H3D) = ALL", "OLOAD(H3D) = ALL", "SPCFORCES(H3D) = ALL"],
    )
    metadata.update(
        analysis_type="linear_thermal_stress",
        load_chain={"load": "TEMP", "set_id": 2, "node_count": structural_nodes, "applied_temperature": temperature},
        control_chain={"solution": "SOL 101", "subcase": 1, "temperature_selector": "TEMP(LOAD)", "h3d_requests": True},
        thermal_expansion=alpha,
        reference_temperature=tref,
    )
    for key in ("loaded_node_ids", "total_force", "force_direction"):
        metadata.pop(key, None)
    return deck, metadata


class AnalysisProfileService:
    def __init__(self, projects: ProjectService):
        self.projects = projects

    def prepare_optistruct_cantilever(
        self,
        project_id: str,
        name: str,
        dimensions: list[float],
        divisions: list[int],
        youngs_modulus: float,
        poissons_ratio: float,
        density: float,
        total_force: float,
        force_direction: list[float],
        gap_contacts: list[dict[str, Any]] | None = None,
        output_name: str = "cantilever.fem",
    ) -> dict[str, Any]:
        deck, metadata = build_optistruct_cantilever_deck(
            name,
            dimensions,
            divisions,
            youngs_modulus,
            poissons_ratio,
            density,
            total_force,
            force_direction,
            gap_contacts,
        )
        root = self.projects.root(project_id)
        filename = safe_filename(output_name, ".fem")
        target = within(root / "input" / filename, root)
        if target.exists():
            raise ValueError(f"Output deck already exists: {filename}")
        target.write_text(deck, encoding="utf-8")
        return {
            "project_id": project_id,
            "input_file": filename,
            "deck_file": str(target),
            "size_bytes": target.stat().st_size,
            **metadata,
        }

    def _write_optistruct_profile(
        self,
        project_id: str,
        output_name: str,
        deck: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        root = self.projects.root(project_id)
        filename = safe_filename(output_name, ".fem")
        target = within(root / "input" / filename, root)
        if target.exists():
            raise ValueError(f"Output deck already exists: {filename}")
        target.write_text(deck, encoding="utf-8")
        return {
            "project_id": project_id,
            "input_file": filename,
            "deck_file": str(target),
            "size_bytes": target.stat().st_size,
            **metadata,
        }

    def prepare_optistruct_modal(
        self, project_id: str, name: str, dimensions: list[float], divisions: list[int],
        youngs_modulus: float, poissons_ratio: float, density: float,
        number_of_modes: int = 10, output_name: str = "modal.fem",
    ) -> dict[str, Any]:
        deck, metadata = build_optistruct_modal_deck(
            name, dimensions, divisions, youngs_modulus, poissons_ratio, density,
            number_of_modes,
        )
        return self._write_optistruct_profile(project_id, output_name, deck, metadata)

    def prepare_optistruct_buckling(
        self, project_id: str, name: str, dimensions: list[float], divisions: list[int],
        youngs_modulus: float, poissons_ratio: float, density: float,
        reference_force: float, force_direction: list[float], number_of_modes: int = 5,
        output_name: str = "buckling.fem",
    ) -> dict[str, Any]:
        deck, metadata = build_optistruct_buckling_deck(
            name, dimensions, divisions, youngs_modulus, poissons_ratio, density,
            reference_force, force_direction, number_of_modes,
        )
        return self._write_optistruct_profile(project_id, output_name, deck, metadata)

    def prepare_optistruct_multicase_static(
        self, project_id: str, name: str, dimensions: list[float], divisions: list[int],
        youngs_modulus: float, poissons_ratio: float, density: float,
        load_cases: list[dict[str, Any]], output_name: str = "multicase_static.fem",
    ) -> dict[str, Any]:
        deck, metadata = build_optistruct_multicase_static_deck(
            name, dimensions, divisions, youngs_modulus, poissons_ratio, density,
            load_cases,
        )
        return self._write_optistruct_profile(project_id, output_name, deck, metadata)

    def prepare_optistruct_contact_static(
        self, project_id: str, name: str, dimensions: list[float], divisions: list[int],
        youngs_modulus: float, poissons_ratio: float, density: float,
        total_force: float, force_direction: list[float],
        gap_contacts: list[dict[str, Any]], output_name: str = "contact_static.fem",
    ) -> dict[str, Any]:
        if not gap_contacts:
            raise ValueError("gap_contacts must contain at least one contact definition")
        result = self.prepare_optistruct_cantilever(
            project_id, name, dimensions, divisions, youngs_modulus, poissons_ratio,
            density, total_force, force_direction, gap_contacts, output_name,
        )
        result["analysis_type"] = "linear_gap_contact_static"
        result["template_note"] = "CGAP/PGAP small-displacement contact fixture"
        return result

    def prepare_optistruct_thermal_stress(
        self, project_id: str, name: str, dimensions: list[float], divisions: list[int],
        youngs_modulus: float, poissons_ratio: float, density: float,
        thermal_expansion: float, reference_temperature: float,
        applied_temperature: float, output_name: str = "thermal_stress.fem",
    ) -> dict[str, Any]:
        deck, metadata = build_optistruct_thermal_stress_deck(
            name, dimensions, divisions, youngs_modulus, poissons_ratio, density,
            thermal_expansion, reference_temperature, applied_temperature,
        )
        return self._write_optistruct_profile(project_id, output_name, deck, metadata)

    def prepare_radioss_block_impact(
        self,
        project_id: str,
        name: str,
        impactor_dimensions: list[float],
        impactor_divisions: list[int],
        target_dimensions: list[float],
        target_divisions: list[int],
        initial_gap: float,
        initial_velocity: float,
        end_time: float,
        output_interval: float,
        youngs_modulus: float = 210.0,
        poissons_ratio: float = 0.3,
        density: float = 7.85e-6,
        yield_stress: float = 0.25,
        hardening_modulus: float = 0.5,
        hardening_exponent: float = 0.5,
        friction: float = 0.1,
        output_name: str = "block_impact_0000.rad",
    ) -> dict[str, Any]:
        starter, engine, metadata = build_radioss_block_impact_decks(
            name,
            impactor_dimensions,
            impactor_divisions,
            target_dimensions,
            target_divisions,
            initial_gap,
            initial_velocity,
            end_time,
            output_interval,
            youngs_modulus,
            poissons_ratio,
            density,
            yield_stress,
            hardening_modulus,
            hardening_exponent,
            friction,
        )
        root = self.projects.root(project_id)
        starter_name = safe_filename(output_name, ".rad")
        if not starter_name.lower().endswith("_0000.rad"):
            raise ValueError("Radioss Starter output_name must end with _0000.rad")
        engine_name = starter_name[:-9] + "_0001.rad"
        starter_path = within(root / "input" / starter_name, root)
        engine_path = within(root / "input" / engine_name, root)
        if starter_path.exists() or engine_path.exists():
            raise ValueError("Starter or Engine output deck already exists")
        starter_path.write_text(starter, encoding="utf-8", newline="\n")
        engine_path.write_text(engine, encoding="utf-8", newline="\n")
        return {
            "project_id": project_id,
            "input_file": starter_name,
            "starter_file": str(starter_path),
            "engine_file": str(engine_path),
            "starter_size_bytes": starter_path.stat().st_size,
            "engine_size_bytes": engine_path.stat().st_size,
            **metadata,
        }

    def prepare_radioss_solid_impact_scenario(
        self,
        project_id: str,
        scenario: str,
        name: str,
        impactor_dimensions: list[float],
        impactor_divisions: list[int],
        target_dimensions: list[float],
        target_divisions: list[int],
        initial_gap: float,
        initial_velocity: float,
        end_time: float,
        output_interval: float,
        youngs_modulus: float = 210.0,
        poissons_ratio: float = 0.3,
        density: float = 7.85e-6,
        yield_stress: float = 0.25,
        hardening_modulus: float = 0.5,
        hardening_exponent: float = 0.5,
        friction: float = 0.1,
        output_name: str = "solid_impact_0000.rad",
    ) -> dict[str, Any]:
        allowed = {"drop_weight_surrogate", "plate_impact", "solid_axial_collision"}
        scenario_key = str(scenario).strip().lower()
        if scenario_key not in allowed:
            raise ValueError("Unsupported solid impact scenario: " + scenario_key)
        result = self.prepare_radioss_block_impact(
            project_id, name, impactor_dimensions, impactor_divisions,
            target_dimensions, target_divisions, initial_gap, initial_velocity,
            end_time, output_interval, youngs_modulus, poissons_ratio, density,
            yield_stress, hardening_modulus, hardening_exponent, friction, output_name,
        )
        result["scenario"] = scenario_key
        result["geometry_fidelity"] = "two_structured_solid_parts"
        result["template_note"] = (
            "Initial-velocity solid impact fixture; gravity, shell walls, supports, "
            "and vehicle assembly details require a dedicated geometry fixture."
        )
        return result
