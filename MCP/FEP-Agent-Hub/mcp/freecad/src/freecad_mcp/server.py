from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP
from open_cae_core import load_config

from .service import FreeCADService


mcp = FastMCP("OpenCAE FreeCAD")
service = FreeCADService(load_config())


def result(response):
    return response.to_dict()


@mcp.tool()
def freecad_environment_probe(refresh: bool = False) -> dict[str, Any]:
    """Detect FreeCAD GUI/headless executables and the real runtime version. No model is modified."""
    return result(service.environment_probe())


@mcp.tool()
def freecad_session_status() -> dict[str, Any]:
    """Report whether the headless adapter is available. This v0.1 server does not claim a live GUI bridge."""
    return result(service.session_status())


@mcp.tool()
def freecad_document_create(project: str, path: str = "geometry/model.FCStd", label: str = "OpenCAE", overwrite: bool = False) -> dict[str, Any]:
    """Create a FreeCAD document inside the named workspace project; refuses overwrite by default."""
    return result(service.document_create(project, path, label, overwrite))


@mcp.tool()
def freecad_document_open(project: str, path: str = "geometry/model.FCStd") -> dict[str, Any]:
    """Open and inspect a workspace FCStd document in an isolated FreeCADCmd process."""
    return result(service.document_inspect(project, path))


@mcp.tool()
def freecad_document_save(project: str, path: str = "geometry/model.FCStd", output: str | None = None, overwrite: bool = False) -> dict[str, Any]:
    """Save or save-as a workspace FCStd document; source files outside the workspace are rejected."""
    return result(service.document_save(project, path, output, overwrite))


@mcp.tool()
def freecad_document_inspect(project: str, path: str = "geometry/model.FCStd") -> dict[str, Any]:
    """Return the object tree and geometric summaries without changing the model."""
    return result(service.document_inspect(project, path))


@mcp.tool()
def freecad_object_inspect(project: str, name: str, path: str = "geometry/model.FCStd") -> dict[str, Any]:
    """Inspect one named object, including topology, volume, and bounding box."""
    return result(service.object_inspect(project, name, path))


@mcp.tool()
def freecad_feature_create(project: str, feature_type: str, name: str, parameters: dict[str, Any], placement: dict[str, Any] | None = None, path: str = "geometry/model.FCStd") -> dict[str, Any]:
    """Create a whitelisted solid primitive or planar rectangle Face. Arbitrary Python is never accepted."""
    return result(service.feature_create(project, feature_type, name, parameters, placement, path))


@mcp.tool()
def freecad_feature_update(project: str, name: str, patch: dict[str, Any], placement: dict[str, Any] | None = None, path: str = "geometry/model.FCStd") -> dict[str, Any]:
    """Patch whitelisted primitive properties, then recompute and persist the document."""
    return result(service.feature_update(project, name, patch, placement, path))


@mcp.tool()
def freecad_feature_delete(project: str, name: str, force: bool = False, path: str = "geometry/model.FCStd") -> dict[str, Any]:
    """Delete an object; downstream dependents block deletion unless force is explicit."""
    return result(service.feature_delete(project, name, force, path))


@mcp.tool()
def freecad_boolean(project: str, operation: str, base: str, tools: list[str], result_name: str, path: str = "geometry/model.FCStd") -> dict[str, Any]:
    """Apply a whitelisted cut, fuse, or common operation and save the resulting model."""
    return result(service.boolean(project, operation, base, tools, result_name, path))


@mcp.tool()
def freecad_transform(project: str, name: str, placement: dict[str, Any], path: str = "geometry/model.FCStd") -> dict[str, Any]:
    """Set a named object's translation and axis-angle rotation in the workspace model."""
    return result(service.transform(project, name, placement, path))


@mcp.tool()
def freecad_geometry_validate(project: str, objects: list[str] | None = None, path: str = "geometry/model.FCStd") -> dict[str, Any]:
    """Validate non-null shapes with positive volume (3D) or area (2D) and report topology evidence."""
    return result(service.geometry_validate(project, objects, path))


@mcp.tool()
def freecad_export_step(project: str, objects: list[str] | None = None, output: str = "geometry/model.step", also_export_parts: bool = False, semantic_ids: dict[str, str] | None = None, path: str = "geometry/model.FCStd") -> dict[str, Any]:
    """Export selected solids/Faces to STEP and generate geometry_manifest.json with fingerprints."""
    return result(service.export_step(project, objects, output, also_export_parts, semantic_ids, path))


@mcp.tool()
def freecad_capture_view(project: str) -> dict[str, Any]:
    """Report headless screenshot capability; v0.1 never fabricates an image when rendering is unavailable."""
    return result(service.capture_view(project))


@mcp.resource("freecad://environment")
def freecad_environment_resource() -> str:
    return json.dumps(service.environment_probe().to_dict(), ensure_ascii=False, indent=2)


@mcp.resource("freecad://project/{project}/document")
def freecad_document_resource(project: str) -> str:
    return json.dumps(service.document_inspect(project).to_dict(), ensure_ascii=False, indent=2)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
