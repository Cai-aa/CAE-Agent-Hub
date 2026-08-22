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

"""Unit tests for tools module."""

import json
from unittest.mock import MagicMock

from mcp.types import ImageContent, TextContent
import pytest

from ansys.common.mcp.tools import create_custom_plot, execute_python_code

# ============================================================================
# execute_python_code Tests
# ============================================================================


class TestExecutePythonCodeBasic:
    """Test suite for basic execute_python_code functionality."""

    @pytest.mark.asyncio
    async def test_execute_simple_code_success(self):
        """Test executing simple Python code successfully."""
        # Setup mock context
        mock_context = MagicMock()
        mock_session = MagicMock()
        mock_session.execute.return_value = {
            "success": True,
            "stdout": "42",
            "stderr": "",
        }
        mock_context.request_context.lifespan_context.python_session = mock_session

        # Execute code
        code = "print(42)"
        result = await execute_python_code(mock_context, code)

        # Verify result
        assert isinstance(result, str)
        result_dict = json.loads(result)
        assert result_dict["success"] is True
        assert "42" in result_dict["stdout"]
        mock_session.execute.assert_called_once_with(code, timeout=60)

    @pytest.mark.asyncio
    async def test_execute_code_with_custom_timeout(self):
        """Test executing code with custom timeout."""
        # Setup mock context
        mock_context = MagicMock()
        mock_session = MagicMock()
        mock_session.execute.return_value = {
            "success": True,
            "stdout": "done",
            "stderr": "",
        }
        mock_context.request_context.lifespan_context.python_session = mock_session

        # Execute with custom timeout
        code = "print('test')"
        timeout = 120
        result = await execute_python_code(mock_context, code, timeout=timeout)

        # Verify timeout was passed
        mock_session.execute.assert_called_once_with(code, timeout=timeout)
        result_dict = json.loads(result)
        assert result_dict["success"] is True

    @pytest.mark.asyncio
    async def test_execute_code_no_session(self):
        """Test executing code when no Python session is available."""
        # Setup mock context with no session
        mock_context = MagicMock()
        mock_context.request_context.lifespan_context.python_session = None

        # Execute code
        code = "print('test')"
        result = await execute_python_code(mock_context, code)

        # Verify error response
        result_dict = json.loads(result)
        assert result_dict["success"] is False
        assert "No Python session available" in result_dict["error"]

    @pytest.mark.asyncio
    async def test_execute_code_with_error(self):
        """Test executing code that produces an error."""
        # Setup mock context
        mock_context = MagicMock()
        mock_session = MagicMock()
        mock_session.execute.return_value = {
            "success": False,
            "stdout": "",
            "stderr": "ZeroDivisionError: division by zero",
            "error": "ZeroDivisionError: division by zero",
        }
        mock_context.request_context.lifespan_context.python_session = mock_session

        # Execute code that will fail
        code = "1/0"
        result = await execute_python_code(mock_context, code)

        # Verify error is returned
        result_dict = json.loads(result)
        assert result_dict["success"] is False
        assert "ZeroDivisionError" in result_dict["error"]

    @pytest.mark.asyncio
    async def test_execute_code_with_stdout_and_stderr(self):
        """Test executing code that produces both stdout and stderr."""
        # Setup mock context
        mock_context = MagicMock()
        mock_session = MagicMock()
        mock_session.execute.return_value = {
            "success": True,
            "stdout": "output message",
            "stderr": "warning message",
        }
        mock_context.request_context.lifespan_context.python_session = mock_session

        # Execute code
        code = "import sys; print('output message'); sys.stderr.write('warning message')"
        result = await execute_python_code(mock_context, code)

        # Verify both outputs are included
        result_dict = json.loads(result)
        assert result_dict["success"] is True
        assert "output message" in result_dict["stdout"]
        assert "warning message" in result_dict["stderr"]


class TestExecutePythonCodeSanitization:
    """Test suite for Unicode sanitization in execute_python_code."""

    @pytest.mark.asyncio
    async def test_sanitize_input_code(self):
        """Test that input code is sanitized for problematic Unicode."""
        # Setup mock context
        mock_context = MagicMock()
        mock_session = MagicMock()
        mock_session.execute.return_value = {
            "success": True,
            "stdout": "done",
            "stderr": "",
        }
        mock_context.request_context.lifespan_context.python_session = mock_session

        # Code with problematic Unicode
        code = "print('✓ checkmark')"
        await execute_python_code(mock_context, code)

        # Verify sanitized code was passed to execute
        called_code = mock_session.execute.call_args[0][0]
        assert "\u2713" not in called_code  # Checkmark should be replaced

    @pytest.mark.asyncio
    async def test_sanitize_output(self):
        """Test that stdout/stderr are sanitized in response."""
        # Setup mock context
        mock_context = MagicMock()
        mock_session = MagicMock()
        mock_session.execute.return_value = {
            "success": True,
            "stdout": "output with ✓ checkmark",
            "stderr": "error with ✗ cross",
        }
        mock_context.request_context.lifespan_context.python_session = mock_session

        # Execute code
        result = await execute_python_code(mock_context, "print('test')")

        # Verify output is sanitized
        result_dict = json.loads(result)
        assert "\u2713" not in result_dict["stdout"]  # Checkmark replaced
        assert "\u2717" not in result_dict["stderr"]  # Cross replaced


class TestExecutePythonCodeExceptionHandling:
    """Test suite for exception handling in execute_python_code."""

    @pytest.mark.asyncio
    async def test_timeout_error(self):
        """Test handling of timeout error."""
        # Setup mock context
        mock_context = MagicMock()
        mock_session = MagicMock()
        mock_session.execute.side_effect = TimeoutError("Timed out")
        mock_context.request_context.lifespan_context.python_session = mock_session

        # Execute code
        result = await execute_python_code(mock_context, "while True: pass", timeout=30)

        # Verify timeout error is returned
        result_dict = json.loads(result)
        assert result_dict["success"] is False
        assert "timed out" in result_dict["error"].lower()
        assert "30 seconds" in result_dict["error"]

    @pytest.mark.asyncio
    async def test_general_exception(self):
        """Test handling of general exceptions."""
        # Setup mock context
        mock_context = MagicMock()
        mock_session = MagicMock()
        mock_session.execute.side_effect = RuntimeError("Unexpected error")
        mock_context.request_context.lifespan_context.python_session = mock_session

        # Execute code
        result = await execute_python_code(mock_context, "print('test')")

        # Verify exception is caught and returned
        result_dict = json.loads(result)
        assert result_dict["success"] is False
        assert "Error executing Python code" in result_dict["error"]
        assert "Unexpected error" in result_dict["error"]

    @pytest.mark.asyncio
    async def test_non_dict_result(self):
        """Test handling when session returns non-dict result."""
        # Setup mock context
        mock_context = MagicMock()
        mock_session = MagicMock()
        mock_session.execute.return_value = "unexpected string result"
        mock_context.request_context.lifespan_context.python_session = mock_session

        # Execute code
        result = await execute_python_code(mock_context, "print('test')")

        # Verify fallback handling
        result_dict = json.loads(result)
        assert result_dict["success"] is True
        assert "unexpected string result" in result_dict["stdout"]


class TestExecutePythonCodeJSONFormatting:
    """Test suite for JSON response formatting."""

    @pytest.mark.asyncio
    async def test_json_structure_success(self):
        """Test JSON structure for successful execution."""
        # Setup mock context
        mock_context = MagicMock()
        mock_session = MagicMock()
        mock_session.execute.return_value = {
            "success": True,
            "stdout": "test output",
            "stderr": "",
        }
        mock_context.request_context.lifespan_context.python_session = mock_session

        # Execute code
        result = await execute_python_code(mock_context, "print('test')")

        # Verify JSON structure
        result_dict = json.loads(result)
        assert "success" in result_dict
        assert "stdout" in result_dict
        assert "stderr" in result_dict
        assert "message" in result_dict
        assert result_dict["success"] is True

    @pytest.mark.asyncio
    async def test_json_structure_failure(self):
        """Test JSON structure for failed execution."""
        # Setup mock context
        mock_context = MagicMock()
        mock_session = MagicMock()
        mock_session.execute.return_value = {
            "success": False,
            "stdout": "",
            "stderr": "Error message",
            "error": "Error message",
        }
        mock_context.request_context.lifespan_context.python_session = mock_session

        # Execute code
        result = await execute_python_code(mock_context, "invalid code")

        # Verify JSON structure
        result_dict = json.loads(result)
        assert "success" in result_dict
        assert "stdout" in result_dict
        assert "stderr" in result_dict
        assert "error" in result_dict
        assert result_dict["success"] is False

    @pytest.mark.asyncio
    async def test_json_ensure_ascii_false(self):
        """Test that JSON is generated with ensure_ascii=False."""
        # Setup mock context
        mock_context = MagicMock()
        mock_session = MagicMock()
        mock_session.execute.return_value = {
            "success": True,
            "stdout": "über test",  # Non-ASCII characters
            "stderr": "",
        }
        mock_context.request_context.lifespan_context.python_session = mock_session

        # Execute code
        result = await execute_python_code(mock_context, "print('über test')")

        # Verify result can be parsed and contains proper characters
        result_dict = json.loads(result)
        assert result_dict["success"] is True


# ============================================================================
# create_custom_plot Tests
# ============================================================================


class TestCreateCustomPlotBasic:
    """Test suite for basic create_custom_plot functionality."""

    def test_create_matplotlib_plot_success(self):
        """Test creating a matplotlib plot successfully."""
        # Setup mock context
        mock_context = MagicMock()
        mock_session = MagicMock()
        base64_data = (
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwAD"
            "hgGAWjR9awAAAABJRU5ErkJggg=="
        )
        mock_session.execute.return_value = {
            "success": True,
            "stdout": f"data:image/png;base64,{base64_data}",
            "stderr": "",
        }
        mock_context.request_context.lifespan_context.python_session = mock_session

        # Create plot
        plot_code = "import matplotlib.pyplot as plt; plt.plot([1,2,3])"
        result = create_custom_plot(mock_context, plot_code)

        # Verify result
        assert isinstance(result, list)
        assert len(result) == 2
        assert isinstance(result[0], TextContent)
        assert isinstance(result[1], ImageContent)
        assert result[1].mimeType == "image/png"
        assert result[1].data == base64_data

    def test_create_pyvista_plot_success(self):
        """Test creating a pyvista plot successfully."""
        # Setup mock context
        mock_context = MagicMock()
        mock_session = MagicMock()
        base64_data = (
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwAD"
            "hgGAWjR9awAAAABJRU5ErkJggg=="
        )
        mock_session.execute.return_value = {
            "success": True,
            "stdout": f"data:image/png;base64,{base64_data}",
            "stderr": "",
        }
        mock_context.request_context.lifespan_context.python_session = mock_session

        # Create plot
        plot_code = "import pyvista as pv; pv.Sphere()"
        result = create_custom_plot(mock_context, plot_code, plot_type="pyvista")

        # Verify result
        assert isinstance(result, list)
        assert len(result) == 2
        assert "pyvista" in result[0].text.lower()

    def test_create_plot_no_session(self):
        """Test creating plot when no Python session is available."""
        # Setup mock context with no session
        mock_context = MagicMock()
        mock_context.request_context.lifespan_context.python_session = None

        # Create plot
        plot_code = "plt.plot([1,2,3])"
        result = create_custom_plot(mock_context, plot_code)

        # Verify error response
        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], TextContent)
        assert "No Python session available" in result[0].text

    def test_create_plot_with_custom_timeout(self):
        """Test creating plot with custom timeout."""
        # Setup mock context
        mock_context = MagicMock()
        mock_session = MagicMock()
        mock_session.execute.return_value = {
            "success": True,
            "stdout": "data:image/png;base64,abc123",
            "stderr": "",
        }
        mock_context.request_context.lifespan_context.python_session = mock_session

        # Create plot with custom timeout
        plot_code = "plt.plot([1,2,3])"
        timeout = 120
        create_custom_plot(mock_context, plot_code, timeout=timeout)

        # Verify timeout was passed
        mock_session.execute.assert_called_once()
        assert mock_session.execute.call_args[1]["timeout"] == timeout


class TestCreateCustomPlotOutputFormats:
    """Test suite for different output formats from create_custom_plot."""

    def test_plot_with_file_path_output(self):
        """Test when plot returns a file path instead of base64."""
        # Setup mock context
        mock_context = MagicMock()
        mock_session = MagicMock()
        mock_session.execute.return_value = {
            "success": True,
            "stdout": "Plot saved to /tmp/plot.png",
            "stderr": "",
        }
        mock_context.request_context.lifespan_context.python_session = mock_session

        # Create plot
        plot_code = "save_plot('/tmp/plot.png')"
        result = create_custom_plot(mock_context, plot_code)

        # Verify file path is returned in text
        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], TextContent)
        assert "Plot saved to" in result[0].text

    def test_plot_with_unexpected_output(self):
        """Test when plot returns unexpected output format."""
        # Setup mock context
        mock_context = MagicMock()
        mock_session = MagicMock()
        mock_session.execute.return_value = {
            "success": True,
            "stdout": "unexpected output format",
            "stderr": "",
        }
        mock_context.request_context.lifespan_context.python_session = mock_session

        # Create plot
        plot_code = "print('test')"
        result = create_custom_plot(mock_context, plot_code)

        # Verify unexpected format is handled
        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], TextContent)
        assert "unexpected output format" in result[0].text.lower()

    def test_plot_execution_error(self):
        """Test when plot execution fails."""
        # Setup mock context
        mock_context = MagicMock()
        mock_session = MagicMock()
        mock_session.execute.return_value = {
            "success": False,
            "stdout": "",
            "stderr": "NameError: name 'plt' is not defined",
            "error": "NameError: name 'plt' is not defined",
        }
        mock_context.request_context.lifespan_context.python_session = mock_session

        # Create plot
        plot_code = "plt.plot([1,2,3])"
        result = create_custom_plot(mock_context, plot_code)

        # Verify error is returned
        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], TextContent)
        assert "Error creating custom" in result[0].text
        assert "NameError" in result[0].text


class TestCreateCustomPlotSanitization:
    """Test suite for Unicode sanitization in create_custom_plot."""

    def test_sanitize_plot_code(self):
        """Test that plot code is sanitized for problematic Unicode."""
        # Setup mock context
        mock_context = MagicMock()
        mock_session = MagicMock()
        mock_session.execute.return_value = {
            "success": True,
            "stdout": "data:image/png;base64,abc123",
            "stderr": "",
        }
        mock_context.request_context.lifespan_context.python_session = mock_session

        # Plot code with problematic Unicode
        plot_code = "plt.title('✓ Success')"
        create_custom_plot(mock_context, plot_code)

        # Verify sanitized code was passed to execute
        called_code = mock_session.execute.call_args[0][0]
        assert "\u2713" not in called_code  # Checkmark should be replaced

    def test_sanitize_stdout_output(self):
        """Test that stdout is sanitized in plot results."""
        # Setup mock context
        mock_context = MagicMock()
        mock_session = MagicMock()
        mock_session.execute.return_value = {
            "success": True,
            "stdout": "output with ✓ checkmark",
            "stderr": "",
        }
        mock_context.request_context.lifespan_context.python_session = mock_session

        # Create plot
        result = create_custom_plot(mock_context, "plt.plot([1,2,3])")

        # Verify output is sanitized
        assert isinstance(result, list)
        assert len(result) == 1
        text_content = result[0].text
        assert "\u2713" not in text_content  # Checkmark replaced

    def test_sanitize_error_messages(self):
        """Test that error messages are sanitized."""
        # Setup mock context
        mock_context = MagicMock()
        mock_session = MagicMock()
        mock_session.execute.return_value = {
            "success": False,
            "stdout": "",
            "stderr": "Error with ✗ cross",
            "error": "Error with ✗ cross",
        }
        mock_context.request_context.lifespan_context.python_session = mock_session

        # Create plot
        result = create_custom_plot(mock_context, "invalid code")

        # Verify error is sanitized
        assert isinstance(result, list)
        text_content = result[0].text
        assert "\u2717" not in text_content  # Cross replaced


class TestCreateCustomPlotExceptionHandling:
    """Test suite for exception handling in create_custom_plot."""

    def test_timeout_error(self):
        """Test handling of timeout error."""
        # Setup mock context
        mock_context = MagicMock()
        mock_session = MagicMock()
        mock_session.execute.side_effect = TimeoutError("Timed out")
        mock_context.request_context.lifespan_context.python_session = mock_session

        # Create plot
        result = create_custom_plot(mock_context, "plt.plot([1]*1000000)", timeout=30)

        # Verify timeout error is returned
        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], TextContent)
        assert "timed out" in result[0].text.lower()
        assert "30 seconds" in result[0].text

    def test_general_exception(self):
        """Test handling of general exceptions."""
        # Setup mock context
        mock_context = MagicMock()
        mock_session = MagicMock()
        mock_session.execute.side_effect = RuntimeError("Unexpected error")
        mock_context.request_context.lifespan_context.python_session = mock_session

        # Create plot
        result = create_custom_plot(mock_context, "plt.plot([1,2,3])")

        # Verify exception is caught and returned
        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], TextContent)
        assert "Error creating custom plot" in result[0].text
        assert "Unexpected error" in result[0].text

    def test_non_dict_result(self):
        """Test handling when session returns non-dict result."""
        # Setup mock context
        mock_context = MagicMock()
        mock_session = MagicMock()
        mock_session.execute.return_value = "unexpected string result"
        mock_context.request_context.lifespan_context.python_session = mock_session

        # Create plot
        result = create_custom_plot(mock_context, "plt.plot([1,2,3])")

        # Verify fallback handling
        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], TextContent)
        assert "Unexpected result format" in result[0].text


class TestCreateCustomPlotTypes:
    """Test suite for different plot types."""

    def test_matplotlib_plot_type(self):
        """Test explicitly specifying matplotlib plot type."""
        # Setup mock context
        mock_context = MagicMock()
        mock_session = MagicMock()
        mock_session.execute.return_value = {
            "success": True,
            "stdout": "data:image/png;base64,abc123",
            "stderr": "",
        }
        mock_context.request_context.lifespan_context.python_session = mock_session

        # Create matplotlib plot
        result = create_custom_plot(mock_context, "plt.plot([1,2,3])", plot_type="matplotlib")

        # Verify matplotlib is mentioned
        assert isinstance(result, list)
        assert "matplotlib" in result[0].text.lower()

    def test_pyvista_plot_type(self):
        """Test explicitly specifying pyvista plot type."""
        # Setup mock context
        mock_context = MagicMock()
        mock_session = MagicMock()
        mock_session.execute.return_value = {
            "success": True,
            "stdout": "data:image/png;base64,abc123",
            "stderr": "",
        }
        mock_context.request_context.lifespan_context.python_session = mock_session

        # Create pyvista plot
        result = create_custom_plot(mock_context, "pv.Sphere()", plot_type="pyvista")

        # Verify pyvista is mentioned
        assert isinstance(result, list)
        assert "pyvista" in result[0].text.lower()

    def test_default_plot_type(self):
        """Test default plot type is matplotlib."""
        # Setup mock context
        mock_context = MagicMock()
        mock_session = MagicMock()
        mock_session.execute.return_value = {
            "success": True,
            "stdout": "data:image/png;base64,abc123",
            "stderr": "",
        }
        mock_context.request_context.lifespan_context.python_session = mock_session

        # Create plot without specifying type
        result = create_custom_plot(mock_context, "plt.plot([1,2,3])")

        # Verify matplotlib is the default
        assert isinstance(result, list)
        assert "matplotlib" in result[0].text.lower()


class TestCreateCustomPlotImageContent:
    """Test suite for ImageContent generation."""

    def test_image_content_structure(self):
        """Test that ImageContent has correct structure."""
        # Setup mock context
        mock_context = MagicMock()
        mock_session = MagicMock()
        base64_data = "abc123xyz"
        mock_session.execute.return_value = {
            "success": True,
            "stdout": f"data:image/png;base64,{base64_data}",
            "stderr": "",
        }
        mock_context.request_context.lifespan_context.python_session = mock_session

        # Create plot
        result = create_custom_plot(mock_context, "plt.plot([1,2,3])")

        # Verify ImageContent structure
        assert len(result) == 2
        image_content = result[1]
        assert image_content.type == "image"
        assert image_content.data == base64_data
        assert image_content.mimeType == "image/png"

    def test_base64_data_extraction(self):
        """Test that base64 data is correctly extracted from data URI."""
        # Setup mock context
        mock_context = MagicMock()
        mock_session = MagicMock()
        base64_data = "VeryLongBase64String=="
        mock_session.execute.return_value = {
            "success": True,
            "stdout": f"data:image/png;base64,{base64_data}",
            "stderr": "",
        }
        mock_context.request_context.lifespan_context.python_session = mock_session

        # Create plot
        result = create_custom_plot(mock_context, "plt.plot([1,2,3])")

        # Verify base64 data extraction
        image_content = result[1]
        assert image_content.data == base64_data
        assert "data:image/png;base64," not in image_content.data

    def test_base64_with_whitespace(self):
        """Test that base64 data with whitespace is properly trimmed."""
        # Setup mock context
        mock_context = MagicMock()
        mock_session = MagicMock()
        base64_data = "abc123"
        mock_session.execute.return_value = {
            "success": True,
            "stdout": f"  data:image/png;base64,{base64_data}  \n",
            "stderr": "",
        }
        mock_context.request_context.lifespan_context.python_session = mock_session

        # Create plot
        result = create_custom_plot(mock_context, "plt.plot([1,2,3])")

        # Verify whitespace is trimmed
        image_content = result[1]
        assert image_content.data == base64_data
