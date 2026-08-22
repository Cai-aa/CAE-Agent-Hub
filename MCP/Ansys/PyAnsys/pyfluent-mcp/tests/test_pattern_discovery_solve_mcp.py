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
import logging

from ansys.fluent.mcp.solve import mcp as solve_mcp
from ansys.fluent.mcp.solve.lib.discovery_tools import list_fields_impl
from ansys.fluent.mcp.solve.lib.pattern import expand_pattern, is_pattern


class FieldsBackend:
    def __init__(self, *, connected=True, result=None, error=None):
        """Initialize the FieldsBackend instance.

        Parameters
        ----------
        connected : Any
            Whether the fake or test backend should report an active connection.
        result : Any
            Result object or payload to process.
        error : Any
            Error instance or message to convert.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        self.connected = connected
        self.result = result
        self.error = error
        self.scopes = []

    def is_connected(self):
        """Return whether connected.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        return self.connected

    async def list_fields(self, *, scope):
        """List fields entries.

        Parameters
        ----------
        scope : Any
            Scope to supply to the function.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        self.scopes.append(scope)
        if self.error:
            raise self.error
        return self.result


def test_pattern_detection_and_expansion():
    """Verify that pattern detection and expansion.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    candidates = ["wall-1", "wall-2", "inlet-a", "outlet", "wall-1"]

    assert is_pattern(None) is False
    assert is_pattern("wall-1") is False
    assert is_pattern("wall-*") is True
    assert expand_pattern("wall-1", candidates) == ["wall-1"]
    assert expand_pattern("missing", candidates) == []
    assert expand_pattern("wall-*|inlet-?", candidates) == ["wall-1", "wall-2", "inlet-a"]
    assert expand_pattern("|out*", candidates) == ["outlet"]


def test_list_fields_impl_handles_disconnected_empty_success_and_errors():
    """Verify that list fields impl handles disconnected empty success and errors.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    disconnected = asyncio.run(list_fields_impl(FieldsBackend(connected=False)))
    success_backend = FieldsBackend(result={"fields": ["pressure"], "scope": "cell"})
    success = asyncio.run(list_fields_impl(success_backend, scope=" cell "))
    empty_backend = FieldsBackend(result={})
    empty = asyncio.run(list_fields_impl(empty_backend, scope=" "))
    failed = asyncio.run(list_fields_impl(FieldsBackend(error=RuntimeError("boom"))))

    assert disconnected == {
        "connected": False,
        "fields": [],
        "note": "live session required to list solver fields",
    }
    assert success == {"connected": True, "fields": ["pressure"], "scope": "cell"}
    assert success_backend.scopes == ["cell"]
    assert empty["connected"] is True
    assert empty["scope"] == "any"
    assert "no field info available" in empty["note"]
    assert failed == {"error": "failed to list fields: boom"}


def test_discover_external_solve_backends_loads_good_plugins_and_skips_bad(monkeypatch, caplog):
    """Verify that discover external solve backends loads good plugins and skips bad.

    Parameters
    ----------
    monkeypatch : Any
        Pytest fixture used to patch environment variables or dependencies.
    caplog : Any
        Pytest fixture used to capture log records during the test.

    Returns
    -------
    None
        The function completes through its side effects.
    """

    class EntryPoint:
        def __init__(self, name, loader):
            """Initialize the EntryPoint instance.

            Parameters
            ----------
            name : Any
                Name of the object, module, or setting being processed.
            loader : Any
                Loader to supply to the function.

            Returns
            -------
            None
                The function completes through its side effects.
            """
            self.name = name
            self._loader = loader

        def load(self):
            """Load data required by the operation.

            Returns
            -------
            None
                The function completes through its side effects.
            """
            return self._loader

    good_backend = object()

    def fake_entry_points(group=None):
        """Return fake entry points for plugin discovery tests.

        Parameters
        ----------
        group : Any
            Group to supply to the function.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        assert group == solve_mcp._SOLVE_BACKENDS_ENTRY_POINT_GROUP
        return [
            EntryPoint("empty", lambda: {}),
            EntryPoint("good", lambda: {"custom": good_backend}),
            EntryPoint("bad", lambda: (_ for _ in ()).throw(RuntimeError("plugin broke"))),
        ]

    monkeypatch.setattr("importlib.metadata.entry_points", fake_entry_points)
    monkeypatch.setattr(solve_mcp.logger, "disabled", False)
    caplog.set_level(logging.WARNING, logger="ansys.fluent.mcp.solve.mcp")

    discovered = solve_mcp._discover_external_solve_backends()

    assert discovered == {"custom": good_backend}
    assert "Failed to load solve backend provider 'bad'" in caplog.text
