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

"""Additional unit tests for helper and startup modules."""

import json
import runpy
import sys
from types import ModuleType
from unittest.mock import MagicMock

import psutil

from ansys.mechanical.mcp import helpers


class _Proc:
    def __init__(
        self, name, status, pid, cmdline, cwd="C:/work", children_count=0, cwd_raises=False
    ):
        self._name = name
        self._status = status
        self.pid = pid
        self._cmdline = cmdline
        self._cwd = cwd
        self._children_count = children_count
        self._cwd_raises = cwd_raises

    def cmdline(self):
        return self._cmdline

    def status(self):
        return self._status

    def name(self):
        return self._name

    def children(self, recursive=True):
        return [object()] * self._children_count

    def cwd(self):
        if self._cwd_raises:
            raise psutil.AccessDenied(pid=self.pid)
        return self._cwd


def test_probe_grpc_endpoint_unreachable(monkeypatch):
    def _raise(*args, **kwargs):
        raise OSError("unreachable")

    monkeypatch.setattr(helpers.socket, "create_connection", _raise)

    result = helpers._probe_grpc_endpoint("127.0.0.1", 60000)

    assert result["reachable"] is False
    assert "unreachable" in result["error"]


def test_list_instances_variants(monkeypatch):
    import psutil

    running = _Proc(
        name="AnsysWBU.exe",
        status=psutil.STATUS_RUNNING,
        pid=101,
        cmdline=["AnsysWBU.exe", "--port", "10000", "-grpc"],
        children_count=3,
    )
    sleeping = _Proc(
        name="mechanical",
        status=psutil.STATUS_SLEEPING,
        pid=102,
        cmdline=["mechanical", "--foo"],
        cwd_raises=True,
    )
    other = _Proc(
        name="python",
        status=psutil.STATUS_RUNNING,
        pid=103,
        cmdline=["python", "script.py"],
    )

    monkeypatch.setattr(psutil, "process_iter", lambda: [running, sleeping, other])

    table_all = helpers.list_instances(instances=False, cmd=True, location=True)
    assert "AnsysWBU.exe" in table_all
    assert "10000" in table_all
    assert "N/A" in table_all

    table_instances_only = helpers.list_instances(instances=True)
    assert "AnsysWBU.exe" in table_instances_only
    assert "mechanical" not in table_instances_only


def test_get_info_success():
    mechanical = MagicMock()
    mechanical.version = "252"
    mechanical.project_directory = "C:/project"
    mechanical.is_alive = True
    mechanical.name = "Mech"
    mechanical.busy = False
    mechanical.exited = False
    mechanical.get_product_info.return_value = {"product": "Mechanical"}
    mechanical.run_python_script.return_value = json.dumps(
        {"product_version": "252", "model_name": "Model"}
    )

    info = helpers.get_info(mechanical)

    assert info["connection"]["version"] == "252"
    assert info["product_info"]["raw"]["product"] == "Mechanical"
    assert info["model"]["model_name"] == "Model"


class _BrokenMechanical:
    @property
    def version(self):
        raise RuntimeError("version unavailable")

    def get_product_info(self):
        raise RuntimeError("product info unavailable")

    def run_python_script(self, script):
        raise RuntimeError("script failed")


def test_get_info_error_paths():
    info = helpers.get_info(_BrokenMechanical())

    assert "error" in info["connection"]
    assert "error" in info["product_info"]
    assert "error" in info["model"]


def test_sanitize_output_replacements():
    from ansys.mechanical.mcp import tools

    text = "\u2713 ok \u2717 bad \u2022 bullet \u00a0space \u2588block"

    result = tools._sanitize_output(text)

    assert "[OK]" in result
    assert "[X]" in result
    assert "*" in result
    assert "space" in result
    assert "#" in result


def test_startup_code_error_paths(monkeypatch):
    from ansys.mechanical.mcp.mechanical_helper import startup_code

    monkeypatch.setattr(startup_code, "MATPLOTLIB_AVAILABLE", False)
    assert startup_code.save_matplotlib_plot() == "Error: matplotlib is not available"

    monkeypatch.setattr(startup_code, "PYVISTA_AVAILABLE", False)
    assert startup_code.save_plot(MagicMock()) == "Error: PyVista is not available"


def test_startup_code_save_matplotlib_plot_success(monkeypatch):
    from ansys.mechanical.mcp.mechanical_helper import startup_code

    buffer = MagicMock()
    buffer.read.return_value = b"png-bytes"
    fake_plot = MagicMock()
    fake_plot.savefig.return_value = None
    fake_plt = MagicMock()
    fake_plt.savefig.side_effect = fake_plot.savefig
    fake_plt.close.return_value = None

    monkeypatch.setattr(startup_code, "MATPLOTLIB_AVAILABLE", True)
    monkeypatch.setattr(startup_code, "plt", fake_plt)
    monkeypatch.setattr(startup_code, "BytesIO", lambda: buffer)

    result = startup_code.save_matplotlib_plot(dpi=200)

    assert result.startswith("data:image/png;base64,")
    fake_plt.savefig.assert_called_once_with(buffer, format="png", dpi=200, bbox_inches="tight")
    fake_plt.close.assert_called_once()


def test_startup_code_save_plot_success(monkeypatch):
    from ansys.mechanical.mcp.mechanical_helper import startup_code

    image = MagicMock()
    image.save.return_value = None
    buffer = MagicMock()
    buffer.read.return_value = b"plot-bytes"
    fake_image_module = MagicMock()
    fake_image_module.fromarray.return_value = image
    fake_plotter = MagicMock()
    fake_plotter.screenshot.return_value = [1, 2, 3]
    fake_plotter.close.return_value = None

    monkeypatch.setattr(startup_code, "PYVISTA_AVAILABLE", True)
    monkeypatch.setattr(startup_code, "Image", fake_image_module)
    monkeypatch.setattr(startup_code, "BytesIO", lambda: buffer)
    monkeypatch.setattr(startup_code.base64, "b64encode", lambda data: b"encoded")

    result = startup_code.save_plot(fake_plotter)

    assert result == "data:image/png;base64,encoded"
    fake_plotter.screenshot.assert_called_once_with(return_img=True, transparent_background=False)
    image.save.assert_called_once_with(buffer, format="PNG")
    fake_plotter.close.assert_called_once()


def test_module_entrypoint_invokes_launcher(monkeypatch):
    fake_server = ModuleType("ansys.mechanical.mcp.server")
    launcher = MagicMock()
    fake_server.launcher = launcher

    monkeypatch.setitem(sys.modules, "ansys.mechanical.mcp.server", fake_server)
    runpy.run_module("ansys.mechanical.mcp.__main__", run_name="__main__")

    launcher.assert_called_once()
