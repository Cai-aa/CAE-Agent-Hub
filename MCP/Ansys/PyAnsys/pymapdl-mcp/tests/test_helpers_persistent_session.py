# Copyright (C) 2025 - 2026 ANSYS, Inc. and/or its affiliates.
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

"""Tests for helpers related to the persistent Python session."""

from unittest.mock import MagicMock, patch

import pytest

from ansys.mapdl.mcp.helpers import connect_to_mapdl_in_persistent_python


@pytest.mark.unit
class TestConnectToMapdlInPersistentPython:
    def test_no_python_session(self, mock_context):
        setattr(mock_context.request_context.lifespan_context, "python_session", None)
        out = connect_to_mapdl_in_persistent_python(mock_context)
        assert isinstance(out, str)
        assert "persistent Python session was not initialized" in out

    def test_already_connected_returns_message(self, mock_context):
        # Prepare python_session and existing mapdl
        session = MagicMock()
        session.metadata = {"mapdl": MagicMock(_ip="127.0.0.1", _port=50052)}
        mock_context.request_context.lifespan_context.python_session = session

        msg = connect_to_mapdl_in_persistent_python(mock_context)
        assert "Already connected to persistent PyMAPDL session" in msg

    def test_no_mapdl_in_lifespan_context(self, mock_context_no_mapdl):
        session = MagicMock()
        session.metadata = {}
        mock_context_no_mapdl.request_context.lifespan_context.python_session = session

        msg = connect_to_mapdl_in_persistent_python(mock_context_no_mapdl)
        assert "No MAPDL instance available in lifespan context" in msg

    def test_successful_connection_stores_metadata(self, mock_context, mock_mapdl):
        # mock_mapdl fixture gives a MagicMock with _ip and _port via attributes set in conftest
        session = MagicMock()
        session.metadata = {}
        mock_context.request_context.lifespan_context.python_session = session

        with patch("ansys.mapdl.mcp.helpers.logger"):
            out = connect_to_mapdl_in_persistent_python(mock_context)

        # Should return the stored mapdl instance
        assert out is mock_context.request_context.lifespan_context.mapdl
        assert session.metadata["mapdl"] is mock_context.request_context.lifespan_context.mapdl
        # Verify execute was invoked to create connection inside the session
        session.execute.assert_called_once()

    def test_execute_failure_logs_and_falls_back(self, mock_context):
        session = MagicMock()
        session.metadata = {}
        session.execute.side_effect = RuntimeError("boom")
        mock_context.request_context.lifespan_context.python_session = session

        with patch("ansys.mapdl.mcp.helpers.logger"):
            out = connect_to_mapdl_in_persistent_python(mock_context)

        # On failure, function returns whatever is in metadata (likely None)
        assert out is None
