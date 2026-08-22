# Copyright (C) 2026 Synopsys, Inc. and ANSYS, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Real-AEDT integration tests for the PyAEDT-MCP tool surface.

These tests require AEDT to be installed and are intended to run against real
desktop instances only. No AEDT connection is mocked in this module.
"""

from __future__ import annotations

import json
from pathlib import Path
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ansys.aedt.mcp.server import PyAEDTAppContext
from ansys.aedt.mcp.tools import (
    analyze_design,
    check_aedt_installed,
    check_aedt_status,
    clear_aedt,
    connect_to_aedt,
    create_design,
    disconnect_from_aedt,
    export_config,
    export_results,
    get_model_info,
    get_pyaedt_logs,
    launch_aedt,
    list_designs,
    list_projects,
    open_project,
    run_python_code,
    run_python_script,
    save_project,
    screenshot,
)

pytestmark = [pytest.mark.integration, pytest.mark.system, pytest.mark.general]


ANALYZE_KWARGS = {
    "num_cores": 1,
    "num_tasks": 1,
    "use_auto_settings": False,
}

_LIVE_ANALYZE_TIMEOUT_SECONDS = 900


def _wait_for_simulation_completion(active_app) -> None:
    deadline = time.monotonic() + _LIVE_ANALYZE_TIMEOUT_SECONDS
    while active_app.are_there_simulations_running:
        if time.monotonic() >= deadline:
            pytest.fail("AEDT simulation did not finish before the export timeout.")
        time.sleep(1)


def _configure_live_settings() -> None:
    try:
        from ansys.aedt.core import settings
    except Exception:
        from ansys.aedt.core.generic.settings import settings

    settings.use_grpc_api = True
    settings.release_on_exception = False


def _build_tool_context() -> SimpleNamespace:
    app_context = PyAEDTAppContext()
    return SimpleNamespace(
        request_context=SimpleNamespace(lifespan_context=app_context),
        enable_components=AsyncMock(),
        disable_components=AsyncMock(),
    )


def _release_desktop(ctx: SimpleNamespace) -> None:
    desktop = ctx.request_context.lifespan_context.desktop
    if desktop is None:
        return

    try:
        desktop.release_desktop(close_projects=False)
    except Exception:
        pass
    finally:
        ctx.request_context.lifespan_context.desktop = None


def _start_desktop():
    from ansys.aedt.core import Desktop

    _configure_live_settings()

    kwargs = {
        "non_graphical": True,
        "new_desktop": True,
    }

    desktop = Desktop(**kwargs)
    if getattr(desktop, "port", None) is None:
        try:
            desktop.release_desktop(close_projects=False)
        except Exception:
            pass
        pytest.skip("Launched AEDT session did not expose a gRPC port.")

    return desktop


def _create_hfss_project(ctx: SimpleNamespace, project_path: Path, design_name: str = "LiveHfss"):
    from ansys.aedt.core import Hfss

    hfss = Hfss(
        project=str(project_path),
        design=design_name,
        solution_type="Terminal",
        new_desktop=False,
        port=ctx.request_context.lifespan_context.aedt_port,
    )

    substrate = hfss.modeler.create_box(
        origin=[0, 0, 0],
        sizes=["40mm", "40mm", "1.6mm"],
        name="Substrate",
        material="FR4_epoxy",
    )
    ground = hfss.modeler.create_rectangle(
        orientation="XY",
        origin=[0, 0, 0],
        sizes=["40mm", "40mm"],
        name="Ground",
    )
    patch = hfss.modeler.create_rectangle(
        orientation="XY",
        origin=["8mm", "8mm", "1.6mm"],
        sizes=["24mm", "24mm"],
        name="Patch",
    )
    hfss.assign_perfecte_to_sheets(ground.name)
    hfss.assign_perfecte_to_sheets(patch.name)

    feed_x = (40 - 3) / 2
    feed = hfss.modeler.create_rectangle(
        orientation="XY",
        origin=[f"{feed_x:.1f}mm", "0mm", "1.6mm"],
        sizes=["3mm", "8mm"],
        name="FeedLine",
    )
    hfss.assign_perfecte_to_sheets(feed.name)

    feed_port = hfss.modeler.create_rectangle(
        orientation="YZ",
        origin=[f"{feed_x:.1f}mm", "0mm", "0mm"],
        sizes=["1.6mm", "3mm"],
        name="FeedPort",
    )
    hfss.lumped_port(
        assignment=feed_port.name,
        name="Port1",
        reference=[ground.name],
        integration_line=1,
    )

    airbox = hfss.modeler.create_box(
        origin=["-15mm", "-15mm", "-15mm"],
        sizes=["70mm", "70mm", "31.6mm"],
        name="AirBox",
        material="vacuum",
    )
    hfss.assign_radiation_boundary_to_objects(airbox.name)

    setup = hfss.create_setup(name="Setup1")
    setup.props["Frequency"] = "2.4GHz"
    setup.props["MaximumPasses"] = 2
    setup.props["MinimumPasses"] = 1
    setup.props["MaxDeltaS"] = 0.1
    setup.update()

    sweep = hfss.create_linear_step_sweep(
        setup=setup.name,
        unit="GHz",
        start_frequency=1.0,
        stop_frequency=4.0,
        step_size=0.25,
        name="Sweep1",
    )

    hfss.save_project()
    ctx.request_context.lifespan_context.desktop = hfss.desktop_class
    ctx.request_context.lifespan_context.aedt_port = hfss.desktop_class.port

    return {
        "project_name": hfss.project_name,
        "design_name": hfss.design_name,
        "design_type": hfss.design_type,
        "setup_name": setup.name,
        "sweep_name": getattr(sweep, "name", "Sweep1"),
        "project_path": project_path,
        "active_app": hfss,
        "geometry": [
            substrate.name,
            ground.name,
            patch.name,
            feed.name,
            feed_port.name,
            airbox.name,
        ],
    }


@pytest.fixture
def empty_ctx():
    return _build_tool_context()


@pytest.fixture
def connected_ctx():
    ctx = _build_tool_context()
    desktop = _start_desktop()
    ctx.request_context.lifespan_context.desktop = desktop
    ctx.request_context.lifespan_context.aedt_port = desktop.port
    try:
        yield ctx
    finally:
        _release_desktop(ctx)


@pytest.fixture
def live_project_env(test_tmp_dir):
    ctx = _build_tool_context()
    desktop = _start_desktop()
    ctx.request_context.lifespan_context.desktop = desktop
    ctx.request_context.lifespan_context.aedt_port = desktop.port

    project_path = test_tmp_dir / "live_tool_surface.aedt"
    saved_project_path = project_path

    try:
        env = _create_hfss_project(ctx, project_path)
        env["ctx"] = ctx
        env["saved_project_path"] = saved_project_path
        yield env
    finally:
        _release_desktop(ctx)


@pytest.fixture
def running_aedt_session():
    desktop = _start_desktop()
    try:
        yield desktop
    finally:
        try:
            desktop.release_desktop(close_projects=False)
        except Exception:
            pass


def test_check_aedt_installed_real_instance(empty_ctx):
    result = check_aedt_installed(empty_ctx)
    assert "AEDT is installed" in result or "is reachable" in result


def test_check_aedt_status_disconnected(empty_ctx):
    data = json.loads(check_aedt_status(empty_ctx))
    assert data["connected"] is False
    assert "available_sessions" in data
    assert "connectable_sessions" in data


@pytest.mark.asyncio
async def test_launch_aedt_real_instance(empty_ctx):
    try:
        result = await launch_aedt(empty_ctx, non_graphical=True, confirm_new_session=True)
        assert "Successfully launched AEDT" in result
        status = json.loads(check_aedt_status(empty_ctx))
        assert status["connected"] is True
    finally:
        _release_desktop(empty_ctx)


def test_check_aedt_status_connected(live_project_env):
    data = json.loads(check_aedt_status(live_project_env["ctx"]))
    assert data["connected"] is True
    assert data["connection"]["is_grpc"] is True


def test_get_pyaedt_logs(live_project_env):
    logs = json.loads(get_pyaedt_logs(live_project_env["ctx"], tail_lines=50, max_chars=10000))
    assert Path(logs["log_file"]).exists()
    assert "returned_lines" in logs


def test_run_python_code(live_project_env):
    result = run_python_code(
        live_project_env["ctx"],
        code=f"""
from ansys.aedt.core import Hfss

hfss = Hfss(
    project=r"{live_project_env["project_path"]}",
    design="{live_project_env["design_name"]}",
    new_desktop=False,
    port=aedt_port,
)
result = f"{{hfss.design_type}}|{{hfss.project_name}}|{{hfss.design_name}}"
""",
    )
    assert live_project_env["design_name"] in result
    assert live_project_env["project_name"] in result
    assert "HFSS" in result.upper()


def test_list_projects(live_project_env):
    data = json.loads(list_projects(live_project_env["ctx"]))
    assert live_project_env["project_name"] in data["open_projects"]
    assert data["count"] >= 1


def test_create_design(live_project_env):
    isolated_ctx = _build_tool_context()
    desktop = _start_desktop()
    isolated_ctx.request_context.lifespan_context.desktop = desktop
    isolated_ctx.request_context.lifespan_context.aedt_port = desktop.port
    try:
        env = _create_hfss_project(
            isolated_ctx,
            live_project_env["project_path"].with_name("create_design_target.aedt"),
        )
        result = create_design(
            isolated_ctx,
            "Hfss",
            design_name="LiveHfssExtra",
            project_name=env["project_name"],
        )
        assert "Successfully created Hfss design" in result
    finally:
        _release_desktop(isolated_ctx)


def test_list_designs(live_project_env):
    data = json.loads(
        list_designs(live_project_env["ctx"], project_name=live_project_env["project_name"])
    )
    assert any(live_project_env["design_name"] in design for design in data["designs"])
    assert data["count"] >= 1


def test_get_model_info(live_project_env):
    data = json.loads(
        get_model_info(live_project_env["ctx"], design_name=live_project_env["design_name"])
    )
    assert data["design_name"] == live_project_env["design_name"]
    assert "HFSS" in data["design_type"].upper()


def test_run_python_script(live_project_env, test_tmp_dir):
    script_path = test_tmp_dir / "touch_aedt_script.py"
    script_marker = test_tmp_dir / "script_marker.txt"
    script_path.write_text(
        'with open(r"' + str(script_marker) + '", "w") as file_handle:\n'
        '    file_handle.write("script executed")\n',
        encoding="utf-8",
    )

    result = run_python_script(live_project_env["ctx"], str(script_path))
    assert "Script executed successfully" in result
    assert script_marker.exists()


def test_save_project(live_project_env, test_tmp_dir):
    isolated_ctx = _build_tool_context()
    desktop = _start_desktop()
    isolated_ctx.request_context.lifespan_context.desktop = desktop
    isolated_ctx.request_context.lifespan_context.aedt_port = desktop.port
    try:
        _create_hfss_project(
            isolated_ctx, test_tmp_dir / "save_project_source.aedt", design_name="SaveHfss"
        )
        save_path = test_tmp_dir / "live_tool_surface_copy.aedt"
        result = save_project(isolated_ctx, save_as=str(save_path))
        assert result == f"Project saved to: {save_path}"
        assert save_path.exists()
    finally:
        _release_desktop(isolated_ctx)


def test_open_project(connected_ctx, live_project_env):
    result = open_project(
        connected_ctx,
        str(live_project_env["saved_project_path"]),
        design_name=live_project_env["design_name"],
    )
    assert "Successfully opened project" in result
    data = json.loads(list_projects(connected_ctx))
    assert live_project_env["saved_project_path"].stem in data["open_projects"]


@pytest.mark.timeout(_LIVE_ANALYZE_TIMEOUT_SECONDS)
def test_analyze_design(live_project_env):
    result = analyze_design(
        live_project_env["ctx"],
        project_name=live_project_env["project_name"],
        design_name=live_project_env["design_name"],
        setup_name=live_project_env["setup_name"],
        **ANALYZE_KWARGS,
    )
    assert "Analysis started successfully and is running asynchronously" in result


@pytest.mark.timeout(_LIVE_ANALYZE_TIMEOUT_SECONDS)
def test_export_results(live_project_env, test_tmp_dir):
    touchstone_path = test_tmp_dir / "live_tools.s2p"
    analyze_design(
        live_project_env["ctx"],
        project_name=live_project_env["project_name"],
        design_name=live_project_env["design_name"],
        setup_name=live_project_env["setup_name"],
        **ANALYZE_KWARGS,
    )
    _wait_for_simulation_completion(live_project_env["active_app"])
    result = export_results(
        live_project_env["ctx"],
        output_path=str(touchstone_path),
        export_type="touchstone",
        setup_name=live_project_env["setup_name"],
    )
    assert "Touchstone exported" in result
    assert touchstone_path.exists()


def test_screenshot(live_project_env, test_tmp_dir):
    screenshot_path = test_tmp_dir / "design_preview.jpg"
    result = screenshot(
        live_project_env["ctx"],
        path=str(screenshot_path),
        project=live_project_env["project_name"],
        design=live_project_env["design_name"],
        open_viewer=False,
    )
    assert len(result) == 2
    assert screenshot_path.exists()


def test_export_config(live_project_env, test_tmp_dir):
    config_path = test_tmp_dir / "design_config.json"
    result = json.loads(
        export_config(
            live_project_env["ctx"],
            output=str(config_path),
            project=live_project_env["project_name"],
            design=live_project_env["design_name"],
            overwrite=True,
        )
    )
    assert Path(result["config_file"]).exists()


def test_clear_aedt(connected_ctx, test_tmp_dir):
    env = _create_hfss_project(
        connected_ctx, test_tmp_dir / "clear_target.aedt", design_name="ClearHfss"
    )
    result = clear_aedt(connected_ctx, close_projects=True)
    assert "AEDT state is cleared" in result
    data = json.loads(list_projects(connected_ctx))
    assert env["project_name"] not in data["open_projects"]


@pytest.mark.asyncio
async def test_connect_to_existing_live_session(running_aedt_session):
    ctx = _build_tool_context()

    try:
        result = await connect_to_aedt(
            ctx,
            machine="localhost",
            port=running_aedt_session.port,
            non_graphical=True,
        )
        assert "Successfully connected to AEDT" in result

        status = json.loads(check_aedt_status(ctx))
        assert status["connected"] is True
        assert status["connection"]["port"] == running_aedt_session.port
    finally:
        _release_desktop(ctx)


@pytest.mark.asyncio
async def test_disconnect_from_aedt(empty_ctx):
    launch_result = await launch_aedt(empty_ctx, non_graphical=True, confirm_new_session=True)
    assert "Successfully launched AEDT" in launch_result

    result = await disconnect_from_aedt(empty_ctx, close_desktop=True)
    assert result == "Successfully disconnected from AEDT and closed the desktop session."
    assert empty_ctx.request_context.lifespan_context.desktop is None
