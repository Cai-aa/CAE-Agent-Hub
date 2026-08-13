from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP
from open_cae_core import load_config

from .service import ParaViewService


mcp = FastMCP("OpenCAE ParaView")
service = ParaViewService(load_config())


def result(response):
    return response.to_dict()


@mcp.tool()
def paraview_environment_probe(refresh: bool = False) -> dict[str, Any]:
    """Detect ParaView GUI, pvpython, optional pvbatch, actual version, and headless capability."""
    return result(service.environment_probe())


@mcp.tool()
def paraview_session_start(project: str, mode: str = "headless") -> dict[str, Any]:
    """Start one persistent MCP-owned pvpython worker for the named workspace project."""
    return result(service.session_start(project, mode))


@mcp.tool()
def paraview_session_status(project: str) -> dict[str, Any]:
    """Report READY, STOPPED, or SESSION_LOST without touching a user-launched GUI."""
    return result(service.session_status(project))


@mcp.tool()
def paraview_session_stop(project: str) -> dict[str, Any]:
    """Stop only the pvpython worker created by this MCP process."""
    return result(service.session_stop(project))


@mcp.tool()
def paraview_dataset_open(project: str, path: str = "results/case.vtu", alias: str = "result") -> dict[str, Any]:
    """Open a workspace VTK dataset and immediately return arrays, bounds, points, and cells."""
    return result(service.dataset_open(project, path, alias))


@mcp.tool()
def paraview_dataset_inspect(project: str, proxy: str = "result") -> dict[str, Any]:
    """Inspect actual arrays and ranges before choosing a visualization field."""
    return result(service.dataset_inspect(project, proxy))


@mcp.tool()
def paraview_pipeline_inspect(project: str) -> dict[str, Any]:
    """Return the persistent worker's current source/filter registry."""
    return result(service.pipeline_inspect(project))


@mcp.tool()
def paraview_filter_create(project: str, input_proxy: str, filter_type: str, parameters: dict[str, Any], alias: str | None = None) -> dict[str, Any]:
    """Create a whitelisted slice, clip, contour, glyph, line sample, stream tracer, warp, threshold, or calculator."""
    return result(service.filter_create(project, input_proxy, filter_type, parameters, alias))


@mcp.tool()
def paraview_color_by(project: str, proxy: str, array: str, association: str = "POINTS", preset: str | None = None) -> dict[str, Any]:
    """Color a visible proxy by an existing array; nonexistent fields are rejected."""
    return result(service.color_by(project, proxy, array, association, preset))


@mcp.tool()
def paraview_scalar_range(project: str, proxy: str, array: str, association: str = "POINTS", mode: str = "data") -> dict[str, Any]:
    """Read the actual finite data range; v0.1 does not invent or clip ranges."""
    return result(service.scalar_range(project, proxy, array, association, mode))


@mcp.tool()
def paraview_camera_set(project: str, camera: dict[str, Any]) -> dict[str, Any]:
    """Set camera position, focal point, view-up, or parallel scale in the headless view."""
    return result(service.camera_set(project, camera))


@mcp.tool()
def paraview_camera_fit(project: str) -> dict[str, Any]:
    """Fit the active visible pipeline in the render view."""
    return result(service.camera_fit(project))


@mcp.tool()
def paraview_render(project: str) -> dict[str, Any]:
    """Render the active headless view without exporting an artifact."""
    return result(service.render(project))


@mcp.tool()
def paraview_export_image(project: str, output: str = "post/field.png", resolution: list[int] | None = None, background: list[float] | None = None) -> dict[str, Any]:
    """Export and validate a PNG, including exact pixel dimensions and non-empty content."""
    return result(service.export_image(project, output, resolution, background))


@mcp.tool()
def paraview_export_csv(project: str, proxy: str = "result", output: str = "post/result.csv") -> dict[str, Any]:
    """Export the selected pipeline proxy to a non-empty workspace CSV."""
    return result(service.export_csv(project, proxy, output))


@mcp.tool()
def paraview_export_animation(
    project: str,
    proxy: str = "result",
    output: str = "post/animation/frame.png",
    resolution: list[int] | None = None,
    frame_rate: int = 10,
    background: list[float] | None = None,
) -> dict[str, Any]:
    """Export validated PNG frames only when the opened dataset exposes two or more real time steps."""
    return result(service.export_animation(project, proxy, output, resolution, frame_rate, background))


@mcp.tool()
def paraview_state_save(project: str, output: str = "post/state.pvsm") -> dict[str, Any]:
    """Save the current verified headless pipeline as a ParaView state file."""
    return result(service.state_save(project, output))


@mcp.resource("paraview://environment")
def paraview_environment_resource() -> str:
    return json.dumps(service.environment_probe().to_dict(), ensure_ascii=False, indent=2)


@mcp.resource("paraview://project/{project}/session")
def paraview_session_resource(project: str) -> str:
    return json.dumps(service.session_status(project).to_dict(), ensure_ascii=False, indent=2)


@mcp.resource("paraview://project/{project}/pipeline")
def paraview_pipeline_resource(project: str) -> str:
    return json.dumps(service.pipeline_inspect(project).to_dict(), ensure_ascii=False, indent=2)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
