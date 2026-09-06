# Ansys AEDT MCP

This module lets MCP clients such as Codex control Ansys Electronics Desktop through PyAEDT. AEDT 2026 R1 is the default and live-tested target.

## Architecture

```text
Codex -> FastMCP stdio server -> external PyAEDT broker -> explicit AEDT PID or gRPC port
```

No MCP script, socket server, extension, or background thread runs inside AEDT. The MCP server creates one external broker for each selected target and reuses that PyAEDT connection across commands. The broker calls `release_desktop(close_projects=False, close_on_exit=False)` only when `release_connection` is called, the MCP process exits, or its stdin closes.

This lifecycle is required for AEDT 2026 R1 gRPC sessions: ending the PyAEDT client after every command also ends that session's gRPC listener. Keeping the connection in an external broker avoids rebuilding AEDT for each tool call without leaving Toolkit/Automation code running in AEDT.

On Windows, the broker watches only its target AEDT process. If the AEDT busy dialog appears, or the main window changes from visible to closed, the broker interprets that as an explicit user close request and calls AEDT `QuitApplication()` through the existing PyAEDT session. The broker then exits. This prevents a connected broker from leaving a hidden AEDT process behind.

## Install

Use Python 3.10 or newer:

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -e .
```

The package pins PyAEDT 1.5.0, matching the official PyAEDT MCP capability baseline used for this adapter. Set `AEDT_INSTALL_DIR` to the directory containing `ansysedt.exe` when using `launch_aedt`.

## MCP Configuration

Use `examples/mcp_config.example.json` and replace `<repo>` with this directory's absolute path.

## Explicit Targeting

There is no implicit AEDT session.

1. Call `check_aedt_installed` and `check_aedt_status`.
2. Call `list_aedt_sessions`, `connect_to_aedt`, or `launch_aedt`.
3. Choose one PID or one gRPC port.
4. Pass exactly one of `pid` or `port` to every targeted tool.

The server never chooses the newest or foreground AEDT window. A successful probe records the returned PID and port as aliases for the same broker, so either explicit identifier continues to address that same session.

## Lifecycle

- `connect_to_aedt` or `check_aedt_connection` creates the broker on first use and performs a real PyAEDT probe.
- Project and analysis tools reuse that broker.
- `disconnect_from_aedt` explicitly chooses whether AEDT stays open; `release_connection` always keeps it open.
- MCP shutdown and broker stdin EOF also release all connections.
- Closing the AEDT window triggers `QuitApplication()` and terminates that target's broker.
- A timed-out broker is terminated; the AEDT process is never force-terminated.

For an MCP-launched session, prefer the port returned by `launch_aedt`. For a user-opened AEDT window, select its PID from `list_aedt_sessions`.

## Tools

Official PyAEDT MCP-compatible names:

- Lifecycle and diagnostics: `check_aedt_installed`, `check_aedt_status`, `launch_aedt`, `connect_to_aedt`, `disconnect_from_aedt`, `clear_aedt`, and `get_pyaedt_logs`.
- Projects and designs: `list_projects`, `list_designs`, `open_project`, `save_project`, and `create_design`.
- Automation: `run_python_code` and `run_python_script`.
- Simulation and evidence: `validate_design`, `analyze_design`, `export_results`, `export_config`, `get_model_info`, `screenshot`, and `get_guidelines_for`.

`create_design` supports `Hfss`, `Maxwell2d`, `Maxwell3d`, `Q3d`, `Q2d`, `Icepak`, `Circuit`, `TwinBuilder`, `Mechanical`, `Emit`, `RMXprt`, and `Hfss3dLayout`.

Local extensions retained from this MCP:

- `list_aedt_sessions`, `check_aedt_connection`, and `release_connection` expose explicit-target broker control.
- `get_project_info` and `close_projects` provide structured project inspection and scoped cleanup.
- `create_hfss_design`, `start_analysis`, and `get_analysis_status` preserve the original HFSS workflow.
- `build_wr90_waveguide` builds, validates, solves, and exports the dedicated WR-90 TE10 case.

## Icepak example

1. Connect with an explicit `pid` or `port`.
2. Call `create_design(app_type="Icepak", project_name="Cooling", design_name="BoardThermal")`.
3. Use `run_python_code` for Icepak geometry, materials, sources, openings, fans, mesh operations, monitors, and setup creation.
4. Call `validate_design`, then `analyze_design`.
5. Confirm solver state and inspect logs, monitor stabilization, maximum temperature, mass-flow conservation, heat balance, mesh/convergence data, and plots.

`analyze_design` is non-blocking for a design-level solve. A returned `started=true` is submission evidence, not proof of solver completion or engineering validity.

For Icepak, `analyze_design` defaults to `icepak_safe_mode=true` when no custom ACF file is supplied. This reliability mode submits one core, disables GPU allocation and automatic DSO settings, and returns both `requested_resources` and `effective_resources`. Set `icepak_safe_mode=false` only after validating the intended parallel configuration on the target AEDT installation; a caller-supplied `acf_file` also takes precedence over safe mode.

For solved Icepak designs, `export_results(export_type="convergence")` exports the residual monitor history from the native `.sd` result files to CSV. `export_results(export_type="mesh")` exports a solution profile and derives node, face, cell, and normal-completion evidence into CSV. The response records `export_method`, source file, and parsed details. These Icepak-specific paths avoid the generic `ExportConvergence` and `ExportMeshStats` calls that are unavailable in some AEDT releases.

Resources `aedt://status` and `aedt://agent-instructions` never attach implicitly.

## Remove Legacy Toolbar

The old `Start AEDT MCP Bridge` and `Stop AEDT MCP Bridge` buttons are not used. Remove only those known entries with:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\remove_legacy_aedt_mcp_toolbar.ps1" -AedtRoot "G:\ANSYS206\ANSYS Inc\v261\AnsysEM"
```

## Verification

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\scripts\run_live_acceptance.ps1 -Mode both
```

Live acceptance covers explicit PID and port targeting, repeated commands on one broker, disposable HFSS project save, and normal AEDT close while the broker is still connected. It fails if the "being used by another application, script or extension wizard" dialog appears.
