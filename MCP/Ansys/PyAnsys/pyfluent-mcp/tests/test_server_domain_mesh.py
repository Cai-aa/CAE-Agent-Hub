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

import asyncio
from types import SimpleNamespace
from typing import Optional

import pytest

from ansys.fluent.mcp import server
from ansys.fluent.mcp.common.domain_tools import schema_from_signature
from ansys.fluent.mcp.common.errors import BackendUnavailableError
from ansys.fluent.mcp.solve.lib import domain_tools as solve_domain_tools
from ansys.fluent.mcp.solve.lib.mesh_tools import _safe_mesh_counts, mesh_quality_impl


def test_argparser_defaults_and_http_options():
    """Verify that argparser defaults and http options.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    defaults = server._argparser().parse_args([])
    explicit = server._argparser().parse_args(
        ["--transport", "http", "--host", "0.0.0.0", "--port", "9000", "--backend", "pyfluent"]
    )

    assert defaults.transport == "stdio"
    assert defaults.host == "127.0.0.1"
    assert defaults.port == 0
    assert explicit.transport == "http"
    assert explicit.host == "0.0.0.0"
    assert explicit.port == 9000
    assert explicit.backend == "pyfluent"


def test_run_routes_stdio_and_http(monkeypatch):
    """Verify that run routes stdio and http.

    Parameters
    ----------
    monkeypatch : Any
        Pytest fixture used to patch environment variables or dependencies.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    calls = []

    class FakeServer:
        def run(self, **kwargs):
            """Run the command-line entry point.

            Parameters
            ----------
            kwargs : Any
                Keyword arguments forwarded to the callable.

            Returns
            -------
            None
                The function completes through its side effects.
            """
            calls.append(kwargs)

    monkeypatch.setattr(
        server, "validate_config", lambda: SimpleNamespace(log_level="WARNING", warnings=[])
    )

    server._run(
        FakeServer(), SimpleNamespace(transport="stdio", host="ignored", port=0, log_level="INFO")
    )
    server._run(
        FakeServer(), SimpleNamespace(transport="http", host="127.0.0.2", port=0, log_level=None)
    )

    assert calls == [
        {"transport": "stdio"},
        {"transport": "http", "host": "127.0.0.2", "port": 8000},
    ]


def test_run_converts_config_error_to_system_exit(monkeypatch):
    """Verify that run converts config error to system exit.

    Parameters
    ----------
    monkeypatch : Any
        Pytest fixture used to patch environment variables or dependencies.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    from ansys.fluent.mcp.common.config import ConfigError

    monkeypatch.setattr(
        server, "validate_config", lambda: (_ for _ in ()).throw(ConfigError("bad env"))
    )

    with pytest.raises(SystemExit, match="configuration error: bad env"):
        server._run(SimpleNamespace(run=lambda **kwargs: None), SimpleNamespace(log_level="INFO"))


def test_launcher_builds_and_runs_server(monkeypatch):
    """Verify that launcher builds and runs server.

    Parameters
    ----------
    monkeypatch : Any
        Pytest fixture used to patch environment variables or dependencies.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    seen = {}

    def fake_build(args):
        """Exercise the fake build test helper.

        Parameters
        ----------
        args : Any
            Positional arguments forwarded to the callable.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        seen["backend"] = args.backend
        return "server-object"

    def fake_run(server_object, args):
        """Exercise the fake run test helper.

        Parameters
        ----------
        server_object : Any
            Server object to supply to the function.
        args : Any
            Positional arguments forwarded to the callable.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        seen["server"] = server_object
        seen["transport"] = args.transport

    monkeypatch.setattr(server, "_build_server", fake_build)
    monkeypatch.setattr(server, "_run", fake_run)

    server.launcher(["--transport", "http", "--backend", "pyfluent"])

    assert seen == {"backend": "pyfluent", "server": "server-object", "transport": "http"}
    assert server.run_solve is server.launcher


def test_solve_domain_tool_catalog_has_expected_tools():
    """Verify that solve domain tool catalog has expected tools.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    tools = solve_domain_tools.get_solve_domain_tools()

    assert [tool.spec.name for tool in tools] == [
        "mesh_quality",
        "list_fields",
        "compare_files",
        "probe_path",
        "get_active_status",
        "get_allowed_values",
        "describe_named_object_template",
        "describe_path",
    ]
    assert all(callable(tool.handler) for tool in tools)
    assert all(tool.requires_live_session is False for tool in tools)
    assert "mesh quality" in tools[0].spec.description.lower()


def test_schema_from_signature_handles_optional_and_required_types():
    """Verify that schema from signature handles optional and required types.

    Returns
    -------
    None
        The function completes through its side effects.
    """

    async def handler(
        backend,
        *,
        name: str,
        count: int,
        ratio: float = 1.0,
        enabled: bool = False,
        values: list | None = None,
        options: Optional[dict] = None,
        loose=None,
    ):
        """Execute the nested test handler.

        Parameters
        ----------
        backend : Any
            Backend instance used to perform the operation.
        name : str
            Name of the object, module, or setting being processed.
        count : int
            Count to supply to the function.
        ratio : float
            Ratio to supply to the function.
        enabled : bool
            Whether to enable or apply enabled.
        values : list | None
            Values to supply to the function.
        options : Optional[dict]
            Options to supply to the function.
        loose : Any
            Loose to supply to the function.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        return {}

    schema = schema_from_signature(handler)

    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["name", "count"]
    assert schema["properties"]["name"] == {"type": "string"}
    assert schema["properties"]["count"] == {"type": "integer"}
    assert schema["properties"]["ratio"] == {"type": "number"}
    assert schema["properties"]["enabled"] == {"type": "boolean"}
    assert schema["properties"]["values"] == {"type": "array"}
    assert schema["properties"]["options"] == {"type": "object"}
    assert schema["properties"]["loose"] == {}


class FakeMeshBackend:
    def __init__(
        self,
        *,
        connected=True,
        counts=None,
        counts_error=None,
        quality=None,
        quality_error=None,
        check=None,
        check_error=None,
    ):
        """Initialize the FakeMeshBackend instance.

        Parameters
        ----------
        connected : Any
            Whether the fake or test backend should report an active connection.
        counts : Any
            Counts to supply to the function.
        counts_error : Any
            Counts error to supply to the function.
        quality : Any
            Quality to supply to the function.
        quality_error : Any
            Quality error to supply to the function.
        check : Any
            Check to supply to the function.
        check_error : Any
            Check error to supply to the function.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        self.connected = connected
        self.counts = counts
        self.counts_error = counts_error
        self.quality = quality or {"min_orthogonal_quality": 0.11}
        self.quality_error = quality_error
        self.check = check or {"warnings": ["warn"]}
        self.check_error = check_error

    def is_connected(self):
        """Return whether connected.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        return self.connected

    async def mesh_counts(self):
        """Return mesh entity counts.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        if self.counts_error:
            raise self.counts_error
        return self.counts

    async def mesh_quality(self):
        """Return mesh quality information from the backend.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        if self.quality_error:
            raise self.quality_error
        return self.quality

    async def mesh_check(self):
        """Run the backend mesh check operation.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        if self.check_error:
            raise self.check_error
        return self.check


def test_safe_mesh_counts_returns_values_or_empty_payloads():
    """Verify that safe mesh counts returns values or empty payloads.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    good = FakeMeshBackend(
        counts={"cell_count": 10, "face_count": 20, "node_count": 30, "extra": 99}
    )
    unavailable = FakeMeshBackend(counts_error=BackendUnavailableError("no counts"))
    failing = FakeMeshBackend(counts_error=RuntimeError("boom"))
    bad_shape = FakeMeshBackend(counts="not dict")

    assert asyncio.run(_safe_mesh_counts(good)) == {
        "cell_count": 10,
        "face_count": 20,
        "node_count": 30,
    }
    assert asyncio.run(_safe_mesh_counts(unavailable)) == {
        "cell_count": None,
        "face_count": None,
        "node_count": None,
    }
    assert asyncio.run(_safe_mesh_counts(failing)) == {
        "cell_count": None,
        "face_count": None,
        "node_count": None,
    }
    assert asyncio.run(_safe_mesh_counts(bad_shape)) == {
        "cell_count": None,
        "face_count": None,
        "node_count": None,
    }


def test_mesh_quality_impl_disconnected_success_and_error_paths():
    """Verify that mesh quality impl disconnected success and error paths.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    disconnected = FakeMeshBackend(connected=False)
    connected = FakeMeshBackend(counts={"cell_count": 1, "face_count": 2, "node_count": 3})
    no_quality = FakeMeshBackend(
        counts={"cell_count": 1},
        quality_error=BackendUnavailableError("quality unavailable"),
    )
    no_check = FakeMeshBackend(
        counts={"cell_count": 1, "face_count": 2, "node_count": 3},
        check_error=BackendUnavailableError("check unavailable"),
    )

    assert asyncio.run(mesh_quality_impl(disconnected))["connected"] is False
    assert asyncio.run(mesh_quality_impl(connected, include_check=True)) == {
        "connected": True,
        "cell_count": 1,
        "face_count": 2,
        "node_count": 3,
        "quality": {"min_orthogonal_quality": 0.11},
        "check": {"warnings": ["warn"]},
    }
    assert asyncio.run(mesh_quality_impl(no_quality))["error"] == "backend_unavailable"
    checked = asyncio.run(mesh_quality_impl(no_check, include_check=True))
    assert checked["check"] is None
    assert checked["check_error"] == "check unavailable"
