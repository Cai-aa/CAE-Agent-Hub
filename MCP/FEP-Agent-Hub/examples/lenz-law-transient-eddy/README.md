# Lenz-law transient eddy-current smoke

This example validates a real 2D transient `Az` solve with a copper conductor and a fixed four-ramp coil-current waveform.

Run it through the registered MCP servers:

```powershell
.\.venv\Scripts\python.exe .\scripts\mcp_lenz_eddy_smoke.py --variants full
```

The generated geometry, mesh, solver data, VTU sequence, PVD, images, CSV files, ParaView state, and MCP trace remain under the configured workspace project `lenz_eddy_current_smoke_v1`.

The compact numerical reference is stored in `expected_metrics.json`. See `docs/lenz-law-transient-eddy-current-validation-report.zh-CN.md` for definitions and limitations.

