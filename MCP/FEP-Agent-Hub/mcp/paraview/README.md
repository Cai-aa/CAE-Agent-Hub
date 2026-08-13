# ParaView MCP

Local STDIO MCP server with one persistent, MCP-owned `pvpython` worker per project session.

Tools cover environment/session state, dataset and pipeline inspection, filters, scalar coloring and ranges, camera control, rendering, PNG/CSV export, animation capability reporting, and PVSM state export.

The worker uses line-delimited structured JSON. It is stopped without touching user-launched ParaView GUI processes. Animation export is intentionally `BLOCKED` for the steady v0.1 benchmark because it has no verified time series.

Entry point:

```powershell
python -m paraview_mcp.server
```
