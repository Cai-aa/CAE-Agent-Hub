"""Opt-in live MCP verification in a new project on an existing AEDT session.

Never edits an existing project. Retains a saved evidence project and JSON report.
Motion assignments are smoke-tested; the optional solve is a separate small 2D
magnetostatic model, not a motor benchmark or engineering validation.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time
import uuid

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def verify(args):
    root = Path(__file__).resolve().parents[1]
    output = Path(args.output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    project = "MCP_Maxwell_Verify_" + uuid.uuid4().hex[:10]
    target = {"pid": args.pid} if args.pid is not None else {"port": args.port}
    report = {
        "started_utc": datetime.now(timezone.utc).isoformat(), "project": project,
        "target": target, "solve_requested": args.solve, "operations": [],
        "motion_solve_validated": False, "engineering_validated": False,
    }
    env = {**os.environ, "AEDT_VERSION": "2026.1", "AEDT_INSTALL_DIR": args.install_dir,
           "AEDT_LOG_DIR": str(output / "logs")}
    # Discovery must succeed in the execution identity before a PyAEDT attach.
    # Otherwise Desktop(new_desktop=False, port=...) can still launch AEDT.
    from ansys.aedt.core.generic.general_methods import active_sessions

    sessions = active_sessions(version="2026.1", non_graphical=False)
    report["pyaedt_discovered_sessions"] = sessions
    known = args.pid in sessions if args.pid is not None else args.port in sessions.values()
    if not known:
        report.update(success=False, error="PyAEDT cannot discover the explicit existing session in this execution identity; no attach or launch attempted")
        (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"success": False, "error": report["error"]}), flush=True)
        return 1
    parameters = StdioServerParameters(command=sys.executable, args=[str(root / "mcp_server.py")], cwd=str(root), env=env)
    created = False
    original = {}
    async with stdio_client(parameters) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()

            async def call(name, arguments=None):
                arguments = dict(arguments or {})
                if name not in {"check_aedt_installed", "list_aedt_sessions", "get_guidelines_for"}:
                    arguments.update(target)
                result = await session.call_tool(name, arguments)
                data = result.structuredContent
                if data is None:
                    texts = [item.text for item in result.content if item.type == "text"]
                    data = json.loads(texts[0]) if texts and not result.isError else {"messages": texts}
                report["operations"].append({"tool": name, "arguments": arguments, "is_error": result.isError, "result": data})
                (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                print(json.dumps({"tool": name, "is_error": result.isError}, ensure_ascii=False), flush=True)
                if result.isError:
                    raise RuntimeError(f"{name}: {data}")
                return data

            async def maxwell(tool_name, design, **kwargs):
                return await call(tool_name, {"project_name": project, "design_name": design, **kwargs})

            async def code(design, body):
                prelude = (
                    "from ansys.aedt.core import get_pyaedt_app\n"
                    f"app = get_pyaedt_app(project_name={project!r}, design_name={design!r}, desktop=desktop)\n"
                )
                return await call("run_python_code", {"code": prelude + body})

            try:
                listed = await session.list_tools()
                names = {tool.name for tool in listed.tools}
                report["registered_tool_count"] = len(names)
                report["maxwell_tools"] = sorted(name for name in names if name.startswith("maxwell_"))
                if len(report["maxwell_tools"]) != 15:
                    raise RuntimeError("Expected 15 registered Maxwell tools")
                installed = await call("check_aedt_installed")
                if installed.get("pyaedt_version") != "1.5.0":
                    raise RuntimeError("Live verification requires pinned PyAEDT 1.5.0")
                await call("check_aedt_status", {})
                original = await call("get_project_info")
                idle = await call("run_python_code", {"code": "result = {'running': desktop.are_there_simulations_running}"})
                if idle["result"]["running"]:
                    raise RuntimeError("Existing AEDT session is busy; no test project created")
                await call("create_design", {"app_type": "Maxwell2d", "project_name": project, "design_name": "Rotation", "solution_type": "Transient"})
                created = True
                await code("Rotation", """app.modeler.model_units = 'mm'
app.modeler.create_rectangle(origin=[4, -1, 0], sizes=[1, 2], name='TerminalA', material='copper')
app.modeler.create_rectangle(origin=[-5, -1, 0], sizes=[1, 2], name='TerminalB', material='copper')
app.modeler.create_circle(origin=[0, 0, 0], radius=1, name='Rotor', material='aluminum')
app.modeler.create_circle(origin=[0, 0, 0], radius=3, name='Band', material='vacuum')
region = app.modeler.create_region(100)
app.assign_balloon([edge.id for edge in region.edges])
result = {'objects': app.modeler.object_names, 'solution_type': app.solution_type}
""")
                for name, polarity in [("A", "Positive"), ("B", "Negative")]:
                    await maxwell("maxwell_assign_coil", "Rotation", assignment=["Terminal" + name], name="Coil" + name, conductors_number=10, polarity=polarity)
                await maxwell("maxwell_assign_winding", "Rotation", name="PhaseA", current="1A", is_solid=False)
                await maxwell("maxwell_add_winding_coils", "Rotation", winding_name="PhaseA", coils=["CoilA", "CoilB"])
                await maxwell("maxwell_assign_rotate_motion", "Rotation", band_object="Band", angular_velocity="100rpm")
                await maxwell("maxwell_assign_force", "Rotation", assignment=["Rotor"], name="RotorForce")
                await maxwell("maxwell_assign_torque", "Rotation", assignment=["Rotor"], name="RotorTorque")
                await maxwell("maxwell_set_eddy_effects", "Rotation", assignment=["Rotor"])
                await maxwell("maxwell_assign_length_mesh", "Rotation", assignment=["Rotor"], name="RotorMesh", maximum_length="0.5mm")
                await maxwell("maxwell_create_setup", "Rotation", name="TransientSetup", properties={"StopTime": "1ms", "TimeStep": "0.1ms"})
                await maxwell("maxwell_get_design_info", "Rotation")
                await call("create_design", {"app_type": "Maxwell2d", "project_name": project, "design_name": "Translation", "solution_type": "Transient"})
                await code("Translation", """app.modeler.model_units = 'mm'
app.modeler.create_rectangle(origin=[-1, -1, 0], sizes=[2, 2], name='Mover', material='aluminum')
app.modeler.create_rectangle(origin=[-3, -3, 0], sizes=[6, 6], name='TravelBand', material='vacuum')
result = {'objects': app.modeler.object_names}
""")
                await maxwell("maxwell_assign_translate_motion", "Translation", band_object="TravelBand", motion_name="Travel", velocity="0.1m_per_sec", negative_limit="-1mm", positive_limit="1mm")
                if args.solve:
                    await call("create_design", {"app_type": "Maxwell2d", "project_name": project, "design_name": "StaticSolve", "solution_type": "Magnetostatic"})
                    await code("StaticSolve", """app.modeler.model_units = 'mm'
app.modeler.create_rectangle(origin=[-1, -1, 0], sizes=[2, 2], name='Conductor', material='copper')
region = app.modeler.create_region(300)
app.assign_balloon([edge.id for edge in region.edges])
result = {'objects': app.modeler.object_names}
""")
                    await maxwell("maxwell_assign_current", "StaticSolve", assignment=["Conductor"], name="Current1", amplitude="1A")
                    await maxwell("maxwell_assign_force", "StaticSolve", assignment=["Conductor"], name="ConductorForce")
                    await maxwell("maxwell_create_setup", "StaticSolve", name="StaticSetup", properties={"MaximumPasses": 6, "MinimumPasses": 2, "MinimumConvergedPasses": 1, "PercentError": 2})
                    validation = await call("validate_design", {"project_name": project, "design_name": "StaticSolve"})
                    if not validation.get("valid"):
                        raise RuntimeError("Live static design failed validation")
                    baseline = await maxwell("maxwell_get_analysis_status", "StaticSolve", setup_name="StaticSetup")
                    if baseline["solution_data_available"] is True:
                        raise RuntimeError("Unexpected pre-existing solution in the unique test design")
                    submission = await call("analyze_design", {"project_name": project, "design_name": "StaticSolve", "setup_name": "StaticSetup"})
                    if not submission.get("started"):
                        raise RuntimeError("Live static solve was not submitted")
                    deadline = time.monotonic() + args.solve_timeout
                    while time.monotonic() < deadline:
                        await asyncio.sleep(2)
                        status = await maxwell("maxwell_get_analysis_status", "StaticSolve", setup_name="StaticSetup")
                        if not status["desktop_simulations_running"] and status["solution_data_available"] is True:
                            break
                    else:
                        raise TimeoutError("Static solve has not produced data within solve timeout")
                    available = await code("StaticSolve", "result = {'sweep': app.nominal_adaptive, 'quantities': app.post.available_report_quantities(solution=app.nominal_adaptive)}")
                    quantities = available["result"]["quantities"]
                    if not quantities:
                        raise RuntimeError("No numerical quantities available after solve")
                    sweep = available["result"]["sweep"]
                    numeric = await maxwell("maxwell_get_solution_data", "StaticSolve", expressions=[quantities[0]], setup_sweep_name=sweep)
                    report["static_numerical_data_obtained"] = bool(numeric["curves"])
                    await maxwell("maxwell_create_field_plot", "StaticSolve", assignment=["Conductor"], quantity="Mag_B", setup_sweep_name=sweep, name="B_Conductor", plot_type="surface")
                    await call("export_results", {"output_path": str(output / "static_profile.prof"), "export_type": "profile", "setup_name": "StaticSetup"})
                    await call("export_results", {"output_path": str(output / "static_convergence.conv"), "export_type": "convergence", "setup_name": "StaticSetup"})
                saved = await call("save_project", {"project_name": project, "save_as": str(output / f"{project}.aedt")})
                report["saved"] = saved
                report["success"] = True
            except Exception as exc:
                report["success"] = False
                report["error"] = str(exc)
                if created:
                    try:
                        await call("save_project", {"project_name": project, "save_as": str(output / f"{project}.aedt")})
                    except Exception as save_error:
                        report["save_error"] = str(save_error)
            finally:
                try:
                    report["logs"] = await call("get_pyaedt_logs", {"tail_lines": 100, "max_chars": 20000})
                    running = await call("run_python_code", {"code": "result = {'running': desktop.are_there_simulations_running}"})
                    if created and not running["result"]["running"]:
                        await call("close_projects", {"project_names": [project], "save": False})
                        report["test_project_closed"] = True
                    if original.get("active_project"):
                        restore = f"p = odesktop.SetActiveProject({original['active_project']!r})\n"
                        if original.get("active_design"):
                            restore += f"p.SetActiveDesign({original['active_design']!r})\n"
                        await call("run_python_code", {"code": restore + "result = True"})
                    await call("release_connection")
                except Exception as cleanup_error:
                    report["cleanup_error"] = str(cleanup_error)
                report["finished_utc"] = datetime.now(timezone.utc).isoformat()
                (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"success": report.get("success"), "error": report.get("error"), "report": str(output / "report.json")}), flush=True)
    return 0 if report.get("success") else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    targets = parser.add_mutually_exclusive_group(required=True)
    targets.add_argument("--pid", type=int)
    targets.add_argument("--port", type=int)
    parser.add_argument("--install-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--solve", action="store_true")
    parser.add_argument("--solve-timeout", type=float, default=180)
    args = parser.parse_args()
    return asyncio.run(verify(args))


if __name__ == "__main__":
    raise SystemExit(main())
