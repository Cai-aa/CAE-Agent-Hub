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

"""Tests for tools that use the persistent Python session."""

import base64
import json
from unittest.mock import MagicMock, patch

from fastmcp.tools.base import ToolResult
from mcp.types import ImageContent, TextContent
import pytest

from ansys.mapdl.mcp.tools import custom_plot, run_python_code


@pytest.fixture
def mock_python_session():
    session = MagicMock()
    session.metadata = {}
    return session


@pytest.mark.unit
class TestRunPythonCode:
    @pytest.mark.asyncio
    async def test_no_python_session(self, mock_context_no_mapdl):
        # Ensure no python_session attribute or explicit None
        setattr(
            mock_context_no_mapdl.request_context.lifespan_context,
            "python_session",
            None,
        )

        result = await run_python_code(mock_context_no_mapdl, code="print('hi')")

        data = json.loads(result.content[0].text)
        assert data["success"] is False
        assert "persistent Python session was not initialized" in data["error"]

    @pytest.mark.asyncio
    async def test_connect_failure_returns_error_string(self, mock_context, mock_python_session):
        mock_context.request_context.lifespan_context.python_session = mock_python_session

        # Mock the connection function to raise an exception on the second try
        with patch(
            "ansys.mapdl.mcp.tools.connect_to_mapdl_in_persistent_python",
            side_effect=["Failed to connect to MAPDL", Exception("Connection failed")],
        ):
            result = await run_python_code(mock_context, code="print('x')")

        data = json.loads(result.content[0].text)
        assert data["success"] is False
        assert "Failed to connect to MAPDL" in data["error"]
        assert "Connection failed" in data["error"]

    @pytest.mark.asyncio
    async def test_success_with_dict_result(self, mock_context, mock_python_session):
        mock_context.request_context.lifespan_context.python_session = mock_python_session
        mock_python_session.metadata["mapdl"] = MagicMock()
        mock_python_session.execute.return_value = {
            "success": True,
            "stdout": "ok\n",
            "stderr": "",
        }

        result = await run_python_code(mock_context, code="print('ok')")
        data = json.loads(result.content[0].text)
        assert data["success"] is True
        assert data["stdout"].strip() == "ok"
        assert data["stderr"] == ""

    @pytest.mark.asyncio
    async def test_failure_with_error_message(self, mock_context, mock_python_session):
        mock_context.request_context.lifespan_context.python_session = mock_python_session
        mock_python_session.metadata["mapdl"] = MagicMock()
        mock_python_session.execute.return_value = {
            "success": False,
            "stdout": "",
            "stderr": "Traceback...",
            "error": "Boom!",
        }

        result = await run_python_code(mock_context, code="raise SystemExit")
        data = json.loads(result.content[0].text)
        assert data["success"] is False
        assert data["error"].startswith("Boom!")

    @pytest.mark.asyncio
    async def test_non_dict_result_is_wrapped(self, mock_context, mock_python_session):
        mock_context.request_context.lifespan_context.python_session = mock_python_session
        mock_python_session.metadata["mapdl"] = MagicMock()
        mock_python_session.execute.return_value = "SOME OUTPUT"

        result = await run_python_code(mock_context, code="'SOME OUTPUT'")
        data = json.loads(result.content[0].text)
        assert data["success"] is True
        assert data["stdout"] == "SOME OUTPUT"
        assert data["stderr"] == ""

    @pytest.mark.asyncio
    async def test_timeout(self, mock_context, mock_python_session):
        mock_context.request_context.lifespan_context.python_session = mock_python_session
        mock_python_session.metadata["mapdl"] = MagicMock()
        mock_python_session.execute.side_effect = TimeoutError("too slow")

        result = await run_python_code(mock_context, code="while True: pass", timeout=1)
        data = json.loads(result.content[0].text)
        assert data["success"] is False
        assert "timed out" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_code_is_sanitized_before_execute(self, mock_context, mock_python_session):
        mock_context.request_context.lifespan_context.python_session = mock_python_session
        mock_python_session.metadata["mapdl"] = MagicMock()
        mock_python_session.execute.return_value = {
            "success": True,
            "stdout": "",
            "stderr": "",
        }

        dirty = "print('bullet:\u2022 and check:\u2713 and nbsp:\u00a0')"
        await run_python_code(mock_context, code=dirty)

        passed_code = mock_python_session.execute.call_args[0][0]
        assert "\u2022" not in passed_code
        assert "\u2713" not in passed_code
        assert "\u00a0" not in passed_code

    @pytest.mark.asyncio
    async def test_stdout_is_sanitized(self, mock_context, mock_python_session):
        mock_context.request_context.lifespan_context.python_session = mock_python_session
        mock_python_session.metadata["mapdl"] = MagicMock()

        # stdout includes characters that should be sanitized by _sanitize_output
        raw_stdout = "\u2713 ok | box \u2514\u2502\u2500 | block \u2588 | nb\u00a0sp"
        mock_python_session.execute.return_value = {
            "success": True,
            "stdout": raw_stdout,
            "stderr": "",
        }

        result = await run_python_code(mock_context, code="print('irrelevant')")
        data = json.loads(result.content[0].text)
        assert data["success"] is True
        # Confirm mapped replacements are present and problematic chars gone
        assert "[OK]" in data["stdout"]
        assert "\\|" in data["stdout"] or "|" in data["stdout"]
        assert "#" in data["stdout"] or "|" in data["stdout"]
        assert "nb sp" in data["stdout"] or "nb  sp" in data["stdout"]

    @pytest.mark.asyncio
    async def test_stderr_is_sanitized(self, mock_context, mock_python_session):
        mock_context.request_context.lifespan_context.python_session = mock_python_session
        mock_python_session.metadata["mapdl"] = MagicMock()

        raw_stderr = "\u2717 error | box \u2514\u2502\u2500 | nb\u00a0sp"
        mock_python_session.execute.return_value = {
            "success": False,
            "stdout": "",
            "stderr": raw_stderr,
            "error": "boom",
        }

        result = await run_python_code(mock_context, code="raise SystemExit")
        data = json.loads(result.content[0].text)
        assert data["success"] is False
        assert "[X]" in data["stderr"]
        assert "|" in data["stderr"]
        assert "nb sp" in data["stderr"] or "nb  sp" in data["stderr"]


@pytest.mark.unit
class TestCreateCustomPlot:
    @pytest.mark.asyncio
    async def test_no_python_session(self, mock_context):
        # Explicitly remove python_session
        setattr(mock_context.request_context.lifespan_context, "python_session", None)

        result = custom_plot(mock_context, plot_code="import matplotlib.pyplot as plt")

        assert isinstance(result, ToolResult)
        assert isinstance(result.content[0], TextContent)
        assert "persistent Python session was not initialized" in result.content[0].text

    def test_connect_failure(self, mock_context, mock_python_session):
        mock_context.request_context.lifespan_context.python_session = mock_python_session

        with patch(
            "ansys.mapdl.mcp.tools.connect_to_mapdl_in_persistent_python",
            return_value="No MAPDL instance available in lifespan context.",
        ):
            out = custom_plot(mock_context, plot_code="print('x')")
            assert isinstance(out, ToolResult)
            assert isinstance(out.content[0], TextContent)
            assert "No MAPDL instance available" in out.content[0].text

    def test_success_returns_image_content(self, mock_context, mock_python_session):
        mock_context.request_context.lifespan_context.python_session = mock_python_session
        mock_python_session.metadata["mapdl"] = MagicMock()

        payload = base64.b64encode(b"img").decode()
        mock_python_session.execute.return_value = {
            "success": True,
            "stdout": f"data:image/png;base64,{payload}",
            "stderr": "",
        }

        result = custom_plot(
            mock_context,
            plot_code="print(save_matplotlib_plot())",
            plot_type="matplotlib",
        )

        assert isinstance(result, ToolResult)
        assert isinstance(result.content[0], TextContent)
        assert isinstance(result.content[1], ImageContent)
        assert result.content[1].mimeType == "image/png"
        assert result.content[1].data == payload

    def test_success_returns_text_when_saved_to_file(self, mock_context, mock_python_session):
        mock_context.request_context.lifespan_context.python_session = mock_python_session
        mock_python_session.metadata["mapdl"] = MagicMock()
        mock_python_session.execute.return_value = {
            "success": True,
            "stdout": "Plot saved to C:/tmp/plot.png",
            "stderr": "",
        }

        result = custom_plot(mock_context, plot_code="print('Plot saved to x')")
        assert isinstance(result, ToolResult)
        assert isinstance(result.content[0], TextContent)
        assert "Plot saved to" in result.content[0].text

    def test_unexpected_output_format(self, mock_context, mock_python_session):
        mock_context.request_context.lifespan_context.python_session = mock_python_session
        mock_python_session.metadata["mapdl"] = MagicMock()
        mock_python_session.execute.return_value = {
            "success": True,
            "stdout": "not an image or path",
            "stderr": "",
        }

        result = custom_plot(mock_context, plot_code="print('weird')")
        assert isinstance(result, ToolResult)
        assert isinstance(result.content[0], TextContent)
        assert "unexpected output format" in result.content[0].text

    def test_pyvista_plot_branch(self, mock_context, mock_python_session):
        mock_context.request_context.lifespan_context.python_session = mock_python_session
        mock_python_session.metadata["mapdl"] = MagicMock()

        payload = base64.b64encode(b"pvimg").decode()
        mock_python_session.execute.return_value = {
            "success": True,
            "stdout": f"data:image/png;base64,{payload}",
            "stderr": "",
        }

        result = custom_plot(
            mock_context,
            plot_code="print('data:image/png;base64,'+ '" + payload + "')",
            plot_type="pyvista",
        )

        assert isinstance(result, ToolResult)
        assert isinstance(result.content[0], TextContent)
        assert isinstance(result.content[1], ImageContent)
        assert result.content[1].mimeType == "image/png"
        assert result.content[1].data == payload

    def test_error_branch_includes_message(self, mock_context, mock_python_session):
        mock_context.request_context.lifespan_context.python_session = mock_python_session
        mock_python_session.metadata["mapdl"] = MagicMock()
        mock_python_session.execute.return_value = {
            "success": False,
            "stdout": "",
            "stderr": "error stream",
            "error": "Something bad",
        }

        result = custom_plot(mock_context, plot_code="raise SystemExit")
        assert isinstance(result, ToolResult)
        assert isinstance(result.content[0], TextContent)
        assert "Error creating custom" in result.content[0].text
        assert "Something bad" in result.content[0].text

    def test_timeout(self, mock_context, mock_python_session):
        mock_context.request_context.lifespan_context.python_session = mock_python_session
        mock_python_session.metadata["mapdl"] = MagicMock()
        mock_python_session.execute.side_effect = TimeoutError("too slow")

        result = custom_plot(mock_context, plot_code="while True: pass", timeout=1)
        assert isinstance(result, ToolResult)
        assert isinstance(result.content[0], TextContent)
        assert "Plot creation timed out after" in result.content[0].text
