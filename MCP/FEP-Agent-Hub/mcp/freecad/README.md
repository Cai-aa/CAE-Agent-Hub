# FreeCAD MCP

Local STDIO MCP server for deterministic FreeCAD headless operations.

Tools: environment probe, session status, document create/open/save/inspect, object inspect, primitive create/update/delete, boolean, transform, geometry validation, STEP export, and explicit capture capability reporting.

The server accepts structured parameters only. FreeCAD runs a fixed staged `.FCMacro`/Python runner; arbitrary Python is not exposed. `freecad_capture_view` is intentionally `BLOCKED` in v0.1 when a verified headless renderer is unavailable.

Entry point:

```powershell
python -m freecad_mcp.server
```
