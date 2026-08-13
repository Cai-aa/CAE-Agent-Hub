from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP
from open_cae_core import load_config

from .service import ElmerService


mcp = FastMCP("OpenCAE Elmer")
service = ElmerService(load_config())


def result(response):
    return response.to_dict()


@mcp.tool()
def elmer_environment_probe(refresh: bool = False) -> dict[str, Any]:
    """Detect the actual ElmerSolver, ElmerGrid, Gmsh, GUI, and optional MPI capabilities."""
    return result(service.environment_probe())


@mcp.tool()
def elmer_case_create(project: str, analysis_type: str = "heat_steady_v1", overwrite: bool = False) -> dict[str, Any]:
    """Create a structured case for verified steady/transient heat, magnetic, elasticity, or flow profiles."""
    return result(service.case_create(project, analysis_type, overwrite))


@mcp.tool()
def elmer_case_inspect(project: str) -> dict[str, Any]:
    """Read bodies, materials, boundaries, solver configuration, and current case state."""
    return result(service.case_inspect(project))


@mcp.tool()
def elmer_geometry_import(project: str, step: str = "geometry/model.step", manifest: str = "geometry/geometry_manifest.json") -> dict[str, Any]:
    """Accept a workspace STEP plus geometry manifest; never guesses from a bare STEP alone."""
    return result(service.geometry_import(project, step, manifest))


@mcp.tool()
def elmer_mesh_generate(project: str, global_size_mm: float = 2.0, order: int = 1, algorithm: str = "default", output_format: str = "msh2", timeout: float = 300, dimension: int = 3, coordinate_scale: float = 1.0) -> dict[str, Any]:
    """Generate a whitelisted 3D thermal or SI-scaled conformal 2D electromagnetic/elasticity/flow mesh."""
    return result(service.mesh_generate(project, global_size_mm, order, algorithm, output_format, timeout, dimension, coordinate_scale))


@mcp.tool()
def elmer_mesh_convert(project: str, timeout: float = 180) -> dict[str, Any]:
    """Convert MSH2 with ElmerGrid and record coordinate-derived semantic boundary evidence."""
    return result(service.mesh_convert(project, timeout))


@mcp.tool()
def elmer_mesh_inspect(project: str) -> dict[str, Any]:
    """Summarize Elmer nodes, elements, bodies, boundaries, bounds, and semantic face mapping."""
    return result(service.mesh_inspect(project))


@mcp.tool()
def elmer_material_set(project: str, body: str, material: dict[str, Any]) -> dict[str, Any]:
    """Set a profile-validated thermal, electromagnetic, elastic, or Newtonian-fluid material."""
    return result(service.material_set(project, body, material))


@mcp.tool()
def elmer_equation_set(project: str, profile: str = "heat_steady_v1", settings: dict[str, Any] | None = None) -> dict[str, Any]:
    """Select a verified SIF keyword profile; unknown profiles are blocked instead of emitted raw."""
    return result(service.equation_set(project, profile, settings))


@mcp.tool()
def elmer_excitation_set(project: str, body: str, excitation: dict[str, Any]) -> dict[str, Any]:
    """Set finite real/imaginary current density on a semantic body; raw SIF is never accepted."""
    return result(service.excitation_set(project, body, excitation))


@mcp.tool()
def elmer_boundary_set(project: str, selector: dict[str, Any], condition: dict[str, Any]) -> dict[str, Any]:
    """Set a semantic thermal, magnetic, structural, or flow boundary; raw IDs are not accepted."""
    return result(service.boundary_set(project, selector, condition))


@mcp.tool()
def elmer_sif_generate(project: str) -> dict[str, Any]:
    """Generate case.sif from a structured verified profile and semantic mesh map."""
    return result(service.sif_generate(project))


@mcp.tool()
def elmer_sif_validate(project: str) -> dict[str, Any]:
    """Validate required SIF blocks, references, profile procedure, and boundary count."""
    return result(service.sif_validate(project))


@mcp.tool()
def elmer_solver_run(project: str, mode: str = "serial", processes: int = 1, timeout: float = 600) -> dict[str, Any]:
    """Run the real Elmer solver after SIF validation; serial is the v0.1 acceptance mode."""
    return result(service.solver_run(project, mode, processes, timeout))


@mcp.tool()
def elmer_job_status(project: str, job_id: str) -> dict[str, Any]:
    """Read cached job state without repeatedly streaming the complete solver log."""
    return result(service.job_status(project, job_id))


@mcp.tool()
def elmer_log_inspect(project: str, last_n_lines: int = 80) -> dict[str, Any]:
    """Return bounded errors, warnings, and log tail plus the full workspace log path."""
    return result(service.log_inspect(project, last_n_lines))


@mcp.tool()
def elmer_result_inspect(project: str) -> dict[str, Any]:
    """Validate profile-specific VTU fields, finite values, and physics acceptance metrics."""
    return result(service.result_inspect(project))


@mcp.resource("elmer://environment")
def elmer_environment_resource() -> str:
    return json.dumps(service.environment_probe().to_dict(), ensure_ascii=False, indent=2)


@mcp.resource("elmer://project/{project}/case")
def elmer_case_resource(project: str) -> str:
    return json.dumps(service.case_inspect(project).to_dict(), ensure_ascii=False, indent=2)


@mcp.resource("elmer://project/{project}/mesh")
def elmer_mesh_resource(project: str) -> str:
    return json.dumps(service.mesh_inspect(project).to_dict(), ensure_ascii=False, indent=2)


@mcp.resource("elmer://project/{project}/result")
def elmer_result_resource(project: str) -> str:
    return json.dumps(service.result_inspect(project).to_dict(), ensure_ascii=False, indent=2)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
