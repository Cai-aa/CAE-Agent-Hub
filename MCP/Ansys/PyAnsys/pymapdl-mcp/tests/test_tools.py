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

"""Tests for MCP tools functionality."""

import base64
import json
import os
from unittest.mock import MagicMock, Mock, patch

from fastmcp.tools.base import ToolResult
from mcp.types import ImageContent, TextContent
import pytest

from ansys.mapdl.mcp.tools import (
    check_mapdl_installed,
    check_mapdl_status,
    connect_to_mapdl,
    disconnect_from_mapdl,
    launch_mapdl_session,
    list_mapdl_instances,
    run_mapdl_command,
    run_multiple_mapdl_commands,
    screenshot,
)


@pytest.mark.unit
class TestCheckMapdlStatus:
    """Tests for check_mapdl_status tool."""

    def test_check_status_with_mapdl(self, mock_context):
        """Test checking MAPDL status when MAPDL is available."""
        result = check_mapdl_status(mock_context)

        assert isinstance(result, ToolResult)

        # Check for JSON structure
        data = json.loads(result.content[0].text)
        assert "connection" in data
        assert "information" in data
        assert "geometry" in data
        assert "post_processing" in data
        assert "mesh" in data
        assert "version" in data["connection"]

    def test_check_status_without_mapdl(self, mock_context_no_mapdl):
        """Test checking MAPDL status when MAPDL is not available."""
        result = check_mapdl_status(mock_context_no_mapdl)

        # Should return helpful error message instead of raising exception
        assert isinstance(result, ToolResult)
        assert "No MAPDL connection available" in result.content[0].text
        assert "connect_to_mapdl" in result.content[0].text

    def test_check_status_with_exited_mapdl(self, mock_context):
        """Test checking status when MAPDL has exited."""
        mock_context.request_context.lifespan_context.mapdl._exited = True

        result = check_mapdl_status(mock_context)

        assert isinstance(result, ToolResult)
        assert "exited or is exiting" in result.content[0].text

    def test_check_status_with_exiting_mapdl(self, mock_context):
        """Test checking status when MAPDL is exiting."""
        mock_context.request_context.lifespan_context.mapdl._exiting = True

        result = check_mapdl_status(mock_context)

        assert isinstance(result, ToolResult)
        assert "exited or is exiting" in result.content[0].text

    def test_check_status_missing_information_attributes(self, mock_context):
        """Test status extraction when information class attributes are missing."""
        # Remove some information attributes
        delattr(mock_context.request_context.lifespan_context.mapdl.info, "title")
        delattr(mock_context.request_context.lifespan_context.mapdl.info, "product")

        result = check_mapdl_status(mock_context)

        # Should still return valid JSON with default values
        data = json.loads(result.content[0].text)
        assert "information" in data
        assert data["information"]["title"] == ""
        assert data["information"]["product"] == ""

    def test_check_status_missing_geometry_attributes(self, mock_context):
        """Test status extraction when geometry class attributes are missing.

        When attributes are missing, the entire geometry block records an error
        (no partial defaults) since get_info uses direct attribute access.
        """
        delattr(mock_context.request_context.lifespan_context.mapdl.geometry, "n_keypoint")

        result = check_mapdl_status(mock_context)

        data = json.loads(result.content[0].text)
        assert "geometry" in data
        assert "error" in data["geometry"]

    def test_check_status_missing_mesh_attributes(self, mock_context):
        """Test status extraction when mesh class attributes are missing.

        When attributes are missing, the entire mesh block records an error
        since get_info uses direct attribute access without hasattr fallbacks.
        """
        delattr(mock_context.request_context.lifespan_context.mapdl.mesh, "n_node")

        result = check_mapdl_status(mock_context)

        data = json.loads(result.content[0].text)
        assert "mesh" in data
        assert "error" in data["mesh"]

    def test_check_status_missing_post_processing(self, mock_context):
        """Test status extraction when post_processing is not available."""
        # Remove post_processing attribute
        delattr(mock_context.request_context.lifespan_context.mapdl, "post_processing")

        result = check_mapdl_status(mock_context)

        # Should still return valid JSON
        data = json.loads(result.content[0].text)
        assert "post_processing" in data
        assert not data["post_processing"]["available"]

    def test_check_status_information_class_exception(self, mock_context):
        """Test status extraction when information class raises exception."""
        # Make information.title raise an exception
        type(mock_context.request_context.lifespan_context.mapdl.info).title = property(
            lambda self: (_ for _ in ()).throw(RuntimeError("Information error"))
        )

        result = check_mapdl_status(mock_context)

        # Should still return valid JSON with error field
        data = json.loads(result.content[0].text)
        assert "information" in data
        assert "error" in data["information"]

    def test_check_status_geometry_class_exception(self, mock_context):
        """Test status extraction when geometry class raises exception."""
        # Make geometry raise an exception
        type(mock_context.request_context.lifespan_context.mapdl.geometry).n_keypoint = property(
            lambda self: (_ for _ in ()).throw(RuntimeError("Geometry error"))
        )

        result = check_mapdl_status(mock_context)

        # Should still return valid JSON with error field
        data = json.loads(result.content[0].text)
        assert "geometry" in data
        assert "error" in data["geometry"]

    def test_check_status_mesh_class_exception(self, mock_context):
        """Test status extraction when mesh class raises exception."""
        # Make mesh raise an exception
        type(mock_context.request_context.lifespan_context.mapdl.mesh).n_node = property(
            lambda self: (_ for _ in ()).throw(RuntimeError("Mesh error"))
        )

        result = check_mapdl_status(mock_context)

        # Should still return valid JSON with error field
        data = json.loads(result.content[0].text)
        assert "mesh" in data
        assert "error" in data["mesh"]

    def test_check_status_post_processing_exception(self, mock_context):
        """Test status extraction when post_processing raises exception."""
        # Make post_processing.nsets raise an exception
        type(mock_context.request_context.lifespan_context.mapdl.post_processing).nsets = property(
            lambda self: (_ for _ in ()).throw(RuntimeError("Post error"))
        )

        result = check_mapdl_status(mock_context)

        # Should still return valid JSON with error field
        data = json.loads(result.content[0].text)
        assert "post_processing" in data
        assert "error" in data["post_processing"]

    def test_check_status_all_data_present(self, mock_context):
        """Test status extraction when all data is properly available."""
        result = check_mapdl_status(mock_context)

        data = json.loads(result.content[0].text)

        # Verify all sections are present
        assert "connection" in data
        assert "information" in data
        assert "geometry" in data
        assert "post_processing" in data
        assert "mesh" in data

        # Verify connection data
        assert data["connection"]["version"] == "2024 R2"
        assert "directory" in data["connection"]
        assert "port" in data["connection"]
        assert "ip" in data["connection"]

        # Verify information data
        assert "title" in data["information"]
        assert "jobname" in data["information"]
        assert "routine" in data["information"]

        # Verify geometry data
        assert "n_keypoint" in data["geometry"]
        assert "n_line" in data["geometry"]
        assert "n_area" in data["geometry"]
        assert "n_volu" in data["geometry"]

        # Verify mesh data
        assert "n_node" in data["mesh"]
        assert "n_elem" in data["mesh"]

        # Verify post_processing data
        assert "available" in data["post_processing"]

        # Verify new sections are present
        assert "components" in data
        assert "materials" in data
        assert "sections" in data
        assert "parts" in data

    def test_check_status_returns_image_when_screenshot_succeeds(self, mock_context, tmp_path):
        """Test that check_mapdl_status returns an ImageContent alongside JSON."""
        fake_image_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        screenshot_path = tmp_path / "status.png"
        screenshot_path.write_bytes(fake_image_data)

        mapdl = mock_context.request_context.lifespan_context.mapdl
        mapdl.screenshot.return_value = str(screenshot_path)
        mapdl.input_strings = MagicMock(return_value="")

        result = check_mapdl_status(mock_context)

        assert isinstance(result, ToolResult)
        assert len(result.content) == 2
        assert isinstance(result.content[0], TextContent)
        assert isinstance(result.content[1], ImageContent)
        # JSON is still in content[0]
        data = json.loads(result.content[0].text)
        assert "connection" in data
        # Image is base64-encoded PNG
        assert result.content[1].mimeType == "image/png"
        # Verify the window was restored after capture
        restore_call = mapdl.input_strings.call_args_list[-1][0][0]
        assert "/WINDOW,1,FULL" in restore_call

    def test_check_status_returns_only_json_when_screenshot_fails(self, mock_context):
        """Test that check_mapdl_status returns only JSON when screenshot fails."""
        mapdl = mock_context.request_context.lifespan_context.mapdl
        # Make screenshot raise so the image capture path is skipped
        mapdl.screenshot.side_effect = RuntimeError("no display")
        mapdl.input_strings = MagicMock(return_value="")

        result = check_mapdl_status(mock_context)

        assert isinstance(result, ToolResult)
        # Only JSON content — no image
        assert len(result.content) == 1
        assert isinstance(result.content[0], TextContent)
        data = json.loads(result.content[0].text)
        assert "connection" in data

    def test_check_status_components_present(self, mock_context):
        """Test that components section is present with correct structure."""
        result = check_mapdl_status(mock_context)

        data = json.loads(result.content[0].text)
        assert "components" in data
        assert "count" in data["components"]
        assert "items" in data["components"]
        assert data["components"]["count"] == 2
        assert "COMP_NODES" in data["components"]["items"]
        assert data["components"]["items"]["COMP_NODES"] == "NODES"
        assert "COMP_ELEMS" in data["components"]["items"]
        assert data["components"]["items"]["COMP_ELEMS"] == "ELEMS"

    def test_check_status_materials_present(self, mock_context):
        """Test that materials section is present with count and max_id."""
        result = check_mapdl_status(mock_context)

        data = json.loads(result.content[0].text)
        assert "materials" in data
        assert "count" in data["materials"]
        assert "max_id" in data["materials"]
        assert data["materials"]["count"] == 2
        assert data["materials"]["max_id"] == 2

    def test_check_status_sections_present(self, mock_context):
        """Test that sections section is present with count and max_id."""
        result = check_mapdl_status(mock_context)

        data = json.loads(result.content[0].text)
        assert "sections" in data
        assert "count" in data["sections"]
        assert "max_id" in data["sections"]
        assert data["sections"]["count"] == 2
        assert data["sections"]["max_id"] == 2

    def test_check_status_components_exception(self, mock_context):
        """Test graceful degradation when components access raises an exception."""
        mock_context.request_context.lifespan_context.mapdl.components = property(
            lambda self: (_ for _ in ()).throw(RuntimeError("Components error"))
        )

        result = check_mapdl_status(mock_context)

        data = json.loads(result.content[0].text)
        assert "components" in data
        assert "error" in data["components"]

    def test_check_status_materials_exception(self, mock_context):
        """Test graceful degradation when materials retrieval raises an exception."""
        mock_context.request_context.lifespan_context.mapdl.get_value = MagicMock(
            side_effect=RuntimeError("Materials error")
        )

        result = check_mapdl_status(mock_context)

        data = json.loads(result.content[0].text)
        assert "materials" in data
        assert "error" in data["materials"]

    def test_check_status_sections_exception(self, mock_context):
        """Test graceful degradation when sections retrieval raises an exception."""

        def _get_value_raise_for_secp(entity, entnum, item1, *args, **kwargs):
            if str(entity).upper() == "SECP":
                raise RuntimeError("Sections error")
            return 2  # normal return for MAT and PART

        mock_context.request_context.lifespan_context.mapdl.get_value = MagicMock(
            side_effect=_get_value_raise_for_secp
        )

        result = check_mapdl_status(mock_context)

        data = json.loads(result.content[0].text)
        assert "sections" in data
        assert "error" in data["sections"]

    def test_check_status_no_components(self, mock_context):
        """Test components section when no components are defined."""
        empty_comp = MagicMock()
        empty_comp.__len__ = MagicMock(return_value=0)
        empty_comp.items = MagicMock(return_value={}.items())
        mock_context.request_context.lifespan_context.mapdl.components = empty_comp

        result = check_mapdl_status(mock_context)

        data = json.loads(result.content[0].text)
        assert data["components"]["count"] == 0
        assert data["components"]["items"] == {}

    def test_check_status_no_materials(self, mock_context):
        """Test materials section when no materials are defined (count = 0)."""

        def _no_mats(entity, entnum, item1, *args, **kwargs):
            return 0  # all queries return 0

        mock_context.request_context.lifespan_context.mapdl.get_value = MagicMock(
            side_effect=_no_mats
        )

        result = check_mapdl_status(mock_context)

        data = json.loads(result.content[0].text)
        assert data["materials"]["count"] == 0
        assert data["materials"]["max_id"] == 0

    def test_check_status_no_sections(self, mock_context):
        """Test sections section when no sections are defined (count = 0)."""

        def _no_secs(entity, entnum, item1, *args, **kwargs):
            return 0  # all queries return 0

        mock_context.request_context.lifespan_context.mapdl.get_value = MagicMock(
            side_effect=_no_secs
        )

        result = check_mapdl_status(mock_context)

        data = json.loads(result.content[0].text)
        assert data["sections"]["count"] == 0
        assert data["sections"]["max_id"] == 0


@pytest.mark.unit
class TestFourViewScreenshot:
    """Tests for screenshot tool with four_view=True."""

    def test_four_view_no_request_context(self):
        """Test screenshot(four_view=True) with no request context."""
        ctx = MagicMock()
        ctx.request_context = None

        result = screenshot(ctx, four_view=True)

        assert isinstance(result, ToolResult)
        assert "No request context available" in result.content[0].text

    def test_four_view_no_mapdl(self, mock_context_no_mapdl):
        """Test screenshot(four_view=True) when MAPDL is not connected."""
        result = screenshot(mock_context_no_mapdl, four_view=True)

        assert isinstance(result, ToolResult)
        assert "No MAPDL connection available" in result.content[0].text

    def test_four_view_success(self, mock_context, tmp_path):
        """Test capturing a four-view screenshot successfully."""
        fake_image_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        screenshot_path = tmp_path / "4view.png"
        screenshot_path.write_bytes(fake_image_data)

        mapdl = mock_context.request_context.lifespan_context.mapdl
        mapdl.screenshot.return_value = str(screenshot_path)
        mapdl.input_strings = MagicMock(return_value="")

        result = screenshot(mock_context, four_view=True)

        assert isinstance(result, ToolResult)
        assert len(result.content) == 2
        assert isinstance(result.content[0], TextContent)
        assert isinstance(result.content[1], ImageContent)
        assert "Screenshot saved to" in result.content[0].text
        assert result.content[1].mimeType == "image/png"

        # Verify setup commands + restore were both called
        assert mapdl.input_strings.call_count >= 2

        # Verify the setup call contains four-window and view commands
        setup_call_args = mapdl.input_strings.call_args_list[0][0][0]
        assert "/WINDOW,1,LTOP" in setup_call_args
        assert "/WINDOW,2,RTOP" in setup_call_args
        assert "/WINDOW,3,LBOT" in setup_call_args
        assert "/WINDOW,4,RBOT" in setup_call_args
        assert "/VIEW,1,0,0,1" in setup_call_args
        assert "/VIEW,4,1,1,1" in setup_call_args

    def test_four_view_custom_plot_command(self, mock_context, tmp_path):
        """Test screenshot(four_view=True) uses commands as the plot command."""
        fake_image_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        screenshot_path = tmp_path / "4view_aplot.png"
        screenshot_path.write_bytes(fake_image_data)

        mapdl = mock_context.request_context.lifespan_context.mapdl
        mapdl.screenshot.return_value = str(screenshot_path)
        mapdl.input_strings = MagicMock(return_value="")

        result = screenshot(mock_context, commands="APLOT", four_view=True)

        assert isinstance(result, ToolResult)
        setup_call_args = mapdl.input_strings.call_args_list[0][0][0]
        assert "APLOT" in setup_call_args

    def test_four_view_default_plot_command_is_eplot(self, mock_context, tmp_path):
        """Test that EPLOT is used when commands is empty with four_view=True."""
        fake_image_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        screenshot_path = tmp_path / "4view_eplot.png"
        screenshot_path.write_bytes(fake_image_data)

        mapdl = mock_context.request_context.lifespan_context.mapdl
        mapdl.screenshot.return_value = str(screenshot_path)
        mapdl.input_strings = MagicMock(return_value="")

        screenshot(mock_context, four_view=True)

        setup_call_args = mapdl.input_strings.call_args_list[0][0][0]
        assert "EPLOT" in setup_call_args

    def test_four_view_restores_single_window(self, mock_context, tmp_path):
        """Test that screenshot(four_view=True) restores the single-window layout."""
        fake_image_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        screenshot_path = tmp_path / "4view_restore.png"
        screenshot_path.write_bytes(fake_image_data)

        mapdl = mock_context.request_context.lifespan_context.mapdl
        mapdl.screenshot.return_value = str(screenshot_path)
        mapdl.input_strings = MagicMock(return_value="")

        screenshot(mock_context, four_view=True)

        # The last input_strings call should restore the single-window layout
        restore_call_args = mapdl.input_strings.call_args_list[-1][0][0]
        assert "/WINDOW,1,FULL" in restore_call_args
        assert "/WINDOW,2,OFF" in restore_call_args
        assert "/WINDOW,3,OFF" in restore_call_args
        assert "/WINDOW,4,OFF" in restore_call_args

    def test_four_view_screenshot_not_found(self, mock_context, tmp_path):
        """Test screenshot(four_view=True) when the screenshot file is not created."""
        mapdl = mock_context.request_context.lifespan_context.mapdl
        mapdl.screenshot.return_value = str(tmp_path / "nonexistent.png")
        mapdl.input_strings = MagicMock(return_value="")

        result = screenshot(mock_context, four_view=True)

        assert isinstance(result, ToolResult)
        assert "Failed to capture screenshot" in result.content[0].text

    def test_four_view_exception_handling(self, mock_context):
        """Test screenshot(four_view=True) graceful error handling."""
        mapdl = mock_context.request_context.lifespan_context.mapdl
        mapdl.input_strings = MagicMock(side_effect=RuntimeError("MAPDL error"))

        result = screenshot(mock_context, four_view=True)

        assert isinstance(result, ToolResult)
        assert "Failed to capture screenshot" in result.content[0].text

    def test_four_view_false_does_not_use_window_commands(self, mock_context, tmp_path):
        """Test that four_view=False does not emit window setup commands."""
        fake_image_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        screenshot_path = tmp_path / "normal.png"
        screenshot_path.write_bytes(fake_image_data)

        mapdl = mock_context.request_context.lifespan_context.mapdl
        mapdl.screenshot.return_value = str(screenshot_path)
        mapdl.input_strings = MagicMock(return_value="")

        screenshot(mock_context, four_view=False)

        # No input_strings calls (commands="" so nothing is run)
        assert mapdl.input_strings.call_count == 0


@pytest.mark.unit
class TestCheckMapdlInstalled:
    """Tests for check_mapdl_installed tool."""

    def test_check_installed_single(self):
        """Test checking MAPDL installation when one installation is found."""
        installations = {242: "/usr/ansys_inc/v242"}
        with patch(
            "ansys.tools.common.path.get_available_ansys_installations",
            return_value=installations,
        ):
            result = check_mapdl_installed(MagicMock())

            assert isinstance(result, ToolResult)
            assert "MAPDL is installed" in result.content[0].text
            assert "1 installation" in result.content[0].text
            assert "242" in result.content[0].text
            assert "ansys242" in result.content[0].text

    def test_check_installed_multiple(self):
        """Test that all installations are listed when multiple are found."""
        installations = {
            251: "/usr/ansys_inc/v251",
            242: "/usr/ansys_inc/v242",
        }
        with patch(
            "ansys.tools.common.path.get_available_ansys_installations",
            return_value=installations,
        ):
            result = check_mapdl_installed(MagicMock())

            assert isinstance(result, ToolResult)
            assert "MAPDL is installed" in result.content[0].text
            assert "2 installation" in result.content[0].text
            assert "251" in result.content[0].text
            assert "242" in result.content[0].text
            assert "ansys251" in result.content[0].text
            assert "ansys242" in result.content[0].text

    def test_check_installed_student(self):
        """Test that student installations are labelled correctly."""
        installations = {
            251: "/usr/ansys_inc/v251",
            -242: "/usr/ansys_inc/ANSYS Student/v242",
        }
        with patch(
            "ansys.tools.common.path.get_available_ansys_installations",
            return_value=installations,
        ):
            result = check_mapdl_installed(MagicMock())

            assert isinstance(result, ToolResult)
            assert "Student" in result.content[0].text
            assert "ansys251" in result.content[0].text
            assert "ansys242" in result.content[0].text

    def test_check_installed_false(self):
        """Test checking MAPDL installation when no installation is found."""
        with patch(
            "ansys.tools.common.path.get_available_ansys_installations",
            return_value={},
        ):
            result = check_mapdl_installed(MagicMock())

            assert isinstance(result, ToolResult)
            assert "MAPDL is not installed" in result.content[0].text
            assert "cannot be found" in result.content[0].text
            assert "properly installed" in result.content[0].text

    def test_check_installed_exception(self):
        """Test error handling when checking MAPDL installation fails."""
        with patch(
            "ansys.tools.common.path.get_available_ansys_installations",
            side_effect=Exception("System error"),
        ):
            result = check_mapdl_installed(MagicMock())

            assert isinstance(result, ToolResult)
            assert "Error checking MAPDL installation" in result.content[0].text
            assert "System error" in result.content[0].text

    def test_check_installed_no_ansys_env(self):
        """Test checking installation when ANSYS environment variables not set."""
        with patch(
            "ansys.tools.common.path.get_available_ansys_installations",
            side_effect=EnvironmentError("ANSYS environment not configured"),
        ):
            result = check_mapdl_installed(MagicMock())

            assert isinstance(result, ToolResult)
            assert "Error checking MAPDL installation" in result.content[0].text
            assert "ANSYS environment not configured" in result.content[0].text

    def test_check_installed_import_error(self):
        """Test handling import errors gracefully."""
        with patch(
            "ansys.tools.common.path.get_available_ansys_installations",
            side_effect=ImportError("Failed to import MAPDL module"),
        ):
            result = check_mapdl_installed(MagicMock())
            assert isinstance(result, ToolResult)
            assert "Error checking MAPDL installation" in str(result)
            assert "Failed to import MAPDL module" in str(result)

    def test_check_installed_with_custom_path(self):
        """Test checking installation with custom ANSYS path."""
        custom_path = "/opt/ansys/v251/ansys/bin/ansys251"
        win_path = custom_path.replace("/bin/ansys251", "/bin/winx64/ansys251.exe")
        installations = {251: "/opt/ansys/v251"}
        with patch(
            "ansys.tools.common.path.get_available_ansys_installations",
            return_value=installations,
        ):
            result = check_mapdl_installed(MagicMock())

            text = result.content[0].text.replace("\\", "/")
            assert "MAPDL is installed" in text
            if os.name == "nt":
                assert "ansys251.exe" in text
                assert win_path in text
            else:
                assert custom_path in text

    def test_check_installed_logging(self):
        """Test that check_mapdl_installed logs messages."""
        installations = {242: "/usr/ansys_inc/v242"}
        with patch(
            "ansys.tools.common.path.get_available_ansys_installations",
            return_value=installations,
        ):
            output = check_mapdl_installed(MagicMock())

            # Verify logging messages
            text = output.content[0].text.replace("\\", "/")
            assert "MAPDL is installed on this system" in text
            if os.name == "nt":
                assert "/usr/ansys_inc/v242/ansys/bin/winx64/ansys242.exe" in text
            else:
                assert "/usr/ansys_inc/v242/ansys/bin/ansys242" in text

    def test_check_not_installed_logging(self):
        """Test that check_mapdl_installed logs when not installed."""
        with patch(
            "ansys.tools.common.path.get_available_ansys_installations",
            return_value={},
        ):
            output = check_mapdl_installed(MagicMock())

            assert (
                "MAPDL is not installed on this system or cannot be found in the "
                in output.content[0].text
            )
            assert (
                "standard locations. Please ensure ANSYS/MAPDL is properly installed "
                in output.content[0].text
            )
            assert "and the installation path is correct." in output.content[0].text


@pytest.mark.unit
class TestRunMapdlCommand:
    """Tests for run_mapdl_command tool."""

    def test_run_command_success(self, mock_context):
        """Test running a MAPDL command successfully."""
        command = "/PREP7"
        result = run_mapdl_command(mock_context, command)

        assert isinstance(result, ToolResult)
        assert "MAPDL command executed successfully" in result.content[0].text

        # Verify that MAPDL's run method was called
        mock_context.request_context.lifespan_context.mapdl.run.assert_called_once_with(command)

    def test_run_command_with_arguments(self, mock_context):
        """Test running a MAPDL command with arguments."""
        command = "K,1,0,0,0"
        result = run_mapdl_command(mock_context, command)

        assert isinstance(result, ToolResult)
        assert "MAPDL command executed successfully" in result.content[0].text

    def test_run_command_without_mapdl(self, mock_context_no_mapdl):
        """Test running a command when MAPDL is not available."""
        result = run_mapdl_command(mock_context_no_mapdl, "/PREP7")

        # Should return helpful error message instead of raising exception
        assert isinstance(result, ToolResult)
        assert "No MAPDL connection available" in result.content[0].text
        assert "connect_to_mapdl" in result.content[0].text

    def test_run_multiple_mapdl_commands(self, mock_context):
        """Test running multiple MAPDL commands sequentially."""
        commands = ["/PREP7", "ET,1,SOLID185", "MP,EX,1,200E9"]

        for cmd in commands:
            result = run_mapdl_command(mock_context, cmd)
            assert "MAPDL command executed successfully" in result.content[0].text

        # Verify all commands were called
        assert mock_context.request_context.lifespan_context.mapdl.run.call_count == len(commands)

    def test_run_command_with_header(self, mock_context):
        """Test running a MAPDL command with header."""
        command = "/PREP7"
        header = "Preprocessing setup"
        result = run_mapdl_command(mock_context, command, header=header)

        assert isinstance(result, ToolResult)
        assert "MAPDL command executed successfully" in result.content[0].text

        # Verify that header was written as a comment
        mock_context.request_context.lifespan_context.mapdl.com.assert_called_with(
            f"# {header}", mute=True
        )

    def test_run_command_with_comment(self, mock_context):
        """Test running a MAPDL command with comment."""
        command = "/PREP7"
        comment = "Setting up the model"
        result = run_mapdl_command(mock_context, command, comment=comment)

        assert isinstance(result, ToolResult)
        assert "MAPDL command executed successfully" in result.content[0].text

        # Verify that comment was written
        mock_context.request_context.lifespan_context.mapdl.com.assert_called_with(
            comment, mute=True
        )

    def test_run_command_with_header_and_comment(self, mock_context):
        """Test running a MAPDL command with both header and comment."""
        command = "/PREP7"
        header = "Setup Phase"
        comment = "Initializing model parameters"
        result = run_mapdl_command(mock_context, command, comment=comment, header=header)

        assert isinstance(result, ToolResult)
        assert "MAPDL command executed successfully" in result.content[0].text

        # Verify that both header and comment were written
        calls = mock_context.request_context.lifespan_context.mapdl.com.call_args_list
        assert any(f"# {header}" in str(call) for call in calls)
        assert any(comment in str(call) for call in calls)

    def test_run_command_with_multiline_comment(self, mock_context):
        """Test running a MAPDL command with multiline comment."""
        command = "/PREP7"
        comment = "Line 1\nLine 2\nLine 3"
        result = run_mapdl_command(mock_context, command, comment=comment)

        assert isinstance(result, ToolResult)
        assert "MAPDL command executed successfully" in result.content[0].text

        # Verify that each line of the comment was written
        calls = mock_context.request_context.lifespan_context.mapdl.com.call_args_list
        assert any("Line 1" in str(call) for call in calls)
        assert any("Line 2" in str(call) for call in calls)
        assert any("Line 3" in str(call) for call in calls)

    def test_run_command_with_empty_header(self, mock_context):
        """Test running a MAPDL command with empty header."""
        command = "/PREP7"
        result = run_mapdl_command(mock_context, command, header="")

        assert isinstance(result, ToolResult)
        assert "MAPDL command executed successfully" in result.content[0].text

        # Verify that com was only called for the command execution, not for empty header
        # (since header is empty, it shouldn't call com for header)
        mock_context.request_context.lifespan_context.mapdl.com.assert_not_called()

    def test_run_command_with_empty_comment(self, mock_context):
        """Test running a MAPDL command with empty comment."""
        command = "/PREP7"
        result = run_mapdl_command(mock_context, command, comment="")

        assert isinstance(result, ToolResult)
        assert "MAPDL command executed successfully" in result.content[0].text

        # Verify that com was not called for empty comment
        mock_context.request_context.lifespan_context.mapdl.com.assert_not_called()


@pytest.mark.unit
class TestRunMultipleCommands:
    """Tests for run_multiple_mapdl_commands tool."""

    def test_run_multiple_mapdl_commands_success(self, mock_context):
        """Test running multiple MAPDL commands successfully."""
        commands = ["/PREP7", "ET,1,SOLID185", "MP,EX,1,200E9"]
        mock_context.request_context.lifespan_context.mapdl.input_strings.return_value = (
            "Commands executed"
        )

        result = run_multiple_mapdl_commands(mock_context, commands)

        assert isinstance(result, ToolResult)
        assert "Successfully executed 3 MAPDL commands" in result.content[1].text
        assert "/PREP7" in result.content[1].text
        assert "ET,1,SOLID185" in result.content[1].text
        assert "MP,EX,1,200E9" in result.content[1].text

        # Verify that MAPDL's input_strings method was called
        mock_context.request_context.lifespan_context.mapdl.input_strings.assert_called_once_with(
            commands
        )

    def test_run_multiple_mapdl_commands_with_output(self, mock_context):
        """Test running multiple commands with MAPDL output."""
        commands = ["/PREP7", "ET,1,SOLID185"]
        output = "Element type 1 defined"
        mock_context.request_context.lifespan_context.mapdl.input_strings.return_value = output

        result = run_multiple_mapdl_commands(mock_context, commands)

        assert "Successfully executed 2 MAPDL commands" in result.content[1].text
        assert "Output:" in result.content[1].text
        assert output in result.content[1].text

    def test_run_multiple_mapdl_commands_empty_list(self, mock_context):
        """Test running multiple commands with an empty list."""
        result = run_multiple_mapdl_commands(mock_context, [])

        assert "No commands provided" in result.content[0].text

    def test_run_multiple_mapdl_commands_not_list(self, mock_context):
        """Test running multiple commands with non-list input."""
        result = run_multiple_mapdl_commands(mock_context, "not a list")

        assert "Commands must be provided as a list" in result.content[0].text

    def test_run_multiple_mapdl_commands_with_empty_strings(self, mock_context):
        """Test running multiple commands with some empty strings."""
        commands = ["/PREP7", "", "ET,1,SOLID185", "  ", "MP,EX,1,200E9"]
        mock_context.request_context.lifespan_context.mapdl.input_strings.return_value = ""

        result = run_multiple_mapdl_commands(mock_context, commands)

        # Should only execute non-empty commands
        assert "Successfully executed 3 MAPDL commands" in result.content[1].text
        assert "/PREP7" in result.content[1].text
        assert "ET,1,SOLID185" in result.content[1].text
        assert "MP,EX,1,200E9" in result.content[1].text

        # Verify input_strings was called with filtered commands
        call_args = mock_context.request_context.lifespan_context.mapdl.input_strings.call_args[0][
            0
        ]
        assert len(call_args) == 3
        assert "" not in call_args
        assert "  " not in call_args

    def test_run_multiple_mapdl_commands_all_empty(self, mock_context):
        """Test running multiple commands when all are empty."""
        commands = ["", "  ", "\t", "\n"]

        result = run_multiple_mapdl_commands(mock_context, commands)

        assert "No valid commands found" in result.content[0].text

    def test_run_multiple_mapdl_commands_without_mapdl(self, mock_context_no_mapdl):
        """Test running multiple commands when MAPDL is not available."""
        commands = ["/PREP7", "ET,1,SOLID185"]
        result = run_multiple_mapdl_commands(mock_context_no_mapdl, commands)

        # Should return helpful error message instead of raising exception
        assert isinstance(result, ToolResult)
        assert "No MAPDL connection available" in result.content[0].text
        assert "connect_to_mapdl" in result.content[0].text

    def test_run_multiple_mapdl_commands_single_command(self, mock_context):
        """Test running a single command through multiple commands."""
        commands = ["/PREP7"]
        mock_context.request_context.lifespan_context.mapdl.input_strings.return_value = ""

        result = run_multiple_mapdl_commands(mock_context, commands)

        assert "Successfully executed 1 MAPDL commands" in result.content[1].text
        assert "/PREP7" in result.content[1].text

    def test_run_multiple_mapdl_commands_with_whitespace(self, mock_context):
        """Test running commands with leading/trailing whitespace."""
        commands = ["  /PREP7  ", "\tET,1,SOLID185\n", " MP,EX,1,200E9 "]
        mock_context.request_context.lifespan_context.mapdl.input_strings.return_value = ""

        result = run_multiple_mapdl_commands(mock_context, commands)

        assert "Successfully executed 3 MAPDL commands" in result.content[1].text

        # Verify whitespace was stripped
        call_args = mock_context.request_context.lifespan_context.mapdl.input_strings.call_args[0][
            0
        ]
        assert call_args[0] == "/PREP7"
        assert call_args[1] == "ET,1,SOLID185"
        assert call_args[2] == "MP,EX,1,200E9"

    def test_run_multiple_mapdl_commands_error_handling(self, mock_context):
        """Test error handling when command execution fails."""
        commands = ["/PREP7", "INVALID_COMMAND", "ET,1,SOLID185"]
        mock_context.request_context.lifespan_context.mapdl.input_strings.side_effect = Exception(
            "Invalid command syntax"
        )

        result = run_multiple_mapdl_commands(mock_context, commands)

        assert "Error executing commands" in result.content[0].text
        assert "Invalid command syntax" in result.content[0].text
        assert "Commands that were attempted:" in result.content[0].text
        assert "/PREP7" in result.content[0].text
        assert "INVALID_COMMAND" in result.content[0].text
        assert "ET,1,SOLID185" in result.content[0].text

    def test_run_multiple_mapdl_commands_large_batch(self, mock_context):
        """Test running a large batch of commands."""
        # Create 100 commands
        commands = [f"K,{i},0,0,0" for i in range(1, 101)]
        mock_context.request_context.lifespan_context.mapdl.input_strings.return_value = ""

        result = run_multiple_mapdl_commands(mock_context, commands)

        assert "Successfully executed 100 MAPDL commands" in result.content[1].text
        # Verify input_strings was called with all commands
        call_args = mock_context.request_context.lifespan_context.mapdl.input_strings.call_args[0][
            0
        ]
        assert len(call_args) == 100

    def test_run_multiple_mapdl_commands_with_comments(self, mock_context):
        """Test running multiple commands including comments."""
        commands = [
            "/COM, Starting analysis",
            "/PREP7",
            "/COM, Define element",
            "ET,1,SOLID185",
        ]
        mock_context.request_context.lifespan_context.mapdl.input_strings.return_value = ""

        result = run_multiple_mapdl_commands(mock_context, commands)

        assert "Successfully executed 4 MAPDL commands" in result.content[1].text
        assert all(cmd in result.content[1].text for cmd in commands)

    def test_run_multiple_mapdl_commands_special_characters(self, mock_context):
        """Test running commands with special characters."""
        commands = [
            "/PREP7",
            "MP,EX,1,2.0E11",
            "MP,PRXY,1,0.3",
            "R,1,0.01,0.01,0.01",
        ]
        mock_context.request_context.lifespan_context.mapdl.input_strings.return_value = ""

        result = run_multiple_mapdl_commands(mock_context, commands)

        assert "Successfully executed 4 MAPDL commands" in result.content[1].text
        assert all(cmd in result.content[1].text for cmd in commands)

    def test_run_multiple_mapdl_commands_sequential_execution(self, mock_context):
        """Test that commands are executed in the correct sequence."""
        commands = ["CMD1", "CMD2", "CMD3"]
        mock_context.request_context.lifespan_context.mapdl.input_strings.return_value = ""

        run_multiple_mapdl_commands(mock_context, commands)

        # Verify input_strings was called with commands in correct order
        call_args = mock_context.request_context.lifespan_context.mapdl.input_strings.call_args[0][
            0
        ]
        assert call_args == commands

    def test_run_multiple_mapdl_commands_no_output(self, mock_context):
        """Test running commands that produce no output."""
        commands = ["/PREP7", "ET,1,SOLID185"]
        mock_context.request_context.lifespan_context.mapdl.input_strings.return_value = ""

        result = run_multiple_mapdl_commands(mock_context, commands)

        assert "Successfully executed 2 MAPDL commands" in result.content[1].text
        # Should not have "Output:" section when result is empty
        assert result.content[1].text.count("Output:") == 0

    def test_run_multiple_mapdl_commands_none_output(self, mock_context):
        """Test running commands that return None."""
        commands = ["/PREP7", "ET,1,SOLID185"]
        mock_context.request_context.lifespan_context.mapdl.input_strings.return_value = None

        result = run_multiple_mapdl_commands(mock_context, commands)

        assert "Successfully executed 2 MAPDL commands" in result.content[1].text
        # Should not have "Output:" section when result is None
        assert "Output:" not in result.content[1].text

    def test_run_multiple_mapdl_commands_stderr_logging(self, mock_context):
        """Test that run_multiple_mapdl_commands logs messages."""
        commands = ["/PREP7", "ET,1,SOLID185"]
        mock_context.request_context.lifespan_context.mapdl.input_strings.return_value = ""

        output = run_multiple_mapdl_commands(mock_context, commands)

        # Verify logging messages
        assert "Successfully executed 2 MAPDL commands" in output.content[1].text

    def test_run_multiple_mapdl_commands_with_header(self, mock_context):
        """Test running multiple MAPDL commands with header."""
        commands = ["/PREP7", "ET,1,SOLID185"]
        header = "Model Setup Phase"
        mock_context.request_context.lifespan_context.mapdl.input_strings.return_value = ""

        result = run_multiple_mapdl_commands(mock_context, commands, header=header)

        assert isinstance(result, ToolResult)
        assert "Successfully executed 2 MAPDL commands" in result.content[1].text

        # Verify that header was written as a comment
        mock_context.request_context.lifespan_context.mapdl.com.assert_called_with(
            f"# {header}", mute=True
        )

    def test_run_multiple_mapdl_commands_with_comment(self, mock_context):
        """Test running multiple MAPDL commands with comment."""
        commands = ["/PREP7", "ET,1,SOLID185"]
        comment = "Building finite element model"
        mock_context.request_context.lifespan_context.mapdl.input_strings.return_value = ""

        result = run_multiple_mapdl_commands(mock_context, commands, comment=comment)

        assert isinstance(result, ToolResult)
        assert "Successfully executed 2 MAPDL commands" in result.content[1].text

        # Verify that comment was written
        mock_context.request_context.lifespan_context.mapdl.com.assert_called_with(
            comment, mute=True
        )

    def test_run_multiple_mapdl_commands_with_header_and_comment(self, mock_context):
        """Test running multiple MAPDL commands with both header and comment."""
        commands = ["/PREP7", "ET,1,SOLID185"]
        header = "Initialization"
        comment = "Setting up element types and material properties"
        mock_context.request_context.lifespan_context.mapdl.input_strings.return_value = ""

        result = run_multiple_mapdl_commands(mock_context, commands, comment=comment, header=header)

        assert isinstance(result, ToolResult)
        assert "Successfully executed 2 MAPDL commands" in result.content[1].text

        # Verify that both header and comment were written
        calls = mock_context.request_context.lifespan_context.mapdl.com.call_args_list
        assert any(f"# {header}" in str(call) for call in calls)
        assert any(comment in str(call) for call in calls)

    def test_run_multiple_mapdl_commands_with_multiline_comment(self, mock_context):
        """Test running multiple MAPDL commands with multiline comment."""
        commands = ["/PREP7", "ET,1,SOLID185"]
        comment = "Creating model\nDefining elements\nSetting parameters"
        mock_context.request_context.lifespan_context.mapdl.input_strings.return_value = ""

        result = run_multiple_mapdl_commands(mock_context, commands, comment=comment)

        assert isinstance(result, ToolResult)
        assert "Successfully executed 2 MAPDL commands" in result.content[1].text

        # Verify that each line of the comment was written
        calls = mock_context.request_context.lifespan_context.mapdl.com.call_args_list
        assert any("Creating model" in str(call) for call in calls)
        assert any("Defining elements" in str(call) for call in calls)
        assert any("Setting parameters" in str(call) for call in calls)

    def test_run_multiple_mapdl_commands_with_empty_header(self, mock_context):
        """Test running multiple commands with empty header."""
        commands = ["/PREP7", "ET,1,SOLID185"]
        mock_context.request_context.lifespan_context.mapdl.input_strings.return_value = ""

        result = run_multiple_mapdl_commands(mock_context, commands, header="")

        assert isinstance(result, ToolResult)
        assert "Successfully executed 2 MAPDL commands" in result.content[1].text

        # Verify that com was not called for empty header
        mock_context.request_context.lifespan_context.mapdl.com.assert_not_called()

    def test_run_multiple_mapdl_commands_with_empty_comment(self, mock_context):
        """Test running multiple commands with empty comment."""
        commands = ["/PREP7", "ET,1,SOLID185"]
        mock_context.request_context.lifespan_context.mapdl.input_strings.return_value = ""

        result = run_multiple_mapdl_commands(mock_context, commands, comment="")

        assert isinstance(result, ToolResult)
        assert "Successfully executed 2 MAPDL commands" in result.content[1].text

        # Verify that com was not called for empty comment
        mock_context.request_context.lifespan_context.mapdl.com.assert_not_called()

    def test_run_multiple_mapdl_commands_header_called_before_input_strings(self, mock_context):
        """Test that header/comment are written before input_strings is called."""
        commands = ["/PREP7", "ET,1,SOLID185"]
        header = "Setup"
        mock_context.request_context.lifespan_context.mapdl.input_strings.return_value = ""

        run_multiple_mapdl_commands(mock_context, commands, header=header)

        # Verify that com was called before input_strings
        com_call_count = mock_context.request_context.lifespan_context.mapdl.com.call_count
        input_strings_called = (
            mock_context.request_context.lifespan_context.mapdl.input_strings.called
        )

        assert com_call_count > 0
        assert input_strings_called

        # Get the order of calls
        all_calls = mock_context.request_context.lifespan_context.mapdl.method_calls
        com_indices = [i for i, call in enumerate(all_calls) if call[0] == "com"]
        input_strings_indices = [
            i for i, call in enumerate(all_calls) if call[0] == "input_strings"
        ]

        # com should be called before input_strings
        if com_indices and input_strings_indices:
            assert max(com_indices) < min(input_strings_indices)


@pytest.mark.unit
class TestListMapdlInstances:
    """Tests for list_mapdl_instances tool."""

    def test_list_instances_success(self, mock_context_no_mapdl):
        """Test list_mapdl_instances with successful instance discovery."""
        # Mock the list_instances function to return sample instances
        mock_output = """Name      Is Instance    Status      gRPC port    PID    Command line                Working directory
------  -------------  --------  -----------  -----  -------------------------  -------------------
ansys     True          running         50052  12345  ansys242 -grpc -port 50052  /tmp/ansys_tmp
ansys     True          running         50053  12346  ansys242 -grpc -port 50053  /tmp/ansys_tmp2"""  # noqa: E501

        with patch("ansys.mapdl.mcp.helpers.list_instances", return_value=mock_output):
            result = list_mapdl_instances(mock_context_no_mapdl)

            # Verify the function returns the output from list_instances
            assert result.content[0].text == mock_output
            assert "ansys" in result.content[0].text
            assert "50052" in result.content[0].text

    def test_list_instances_no_instances(self, mock_context_no_mapdl):
        """Test list_mapdl_instances when no instances are found."""
        # Mock the list_instances function to return empty table
        mock_output = """Name    Is Instance    Status    gRPC port    PID    Command line    Working directory
------  -------------  --------  -----------  -----  --------------  -------------------"""  # noqa: E501

        with patch("ansys.mapdl.mcp.helpers.list_instances", return_value=mock_output):
            result = list_mapdl_instances(mock_context_no_mapdl)

            # Verify appropriate message is returned
            assert result.content[0].text == mock_output

    def test_list_instances_calls_with_long_flag(self, mock_context_no_mapdl):
        """Test that list_mapdl_instances calls list_instances with long=True."""
        mock_list_instances = Mock(return_value="Sample output")

        with patch("ansys.mapdl.mcp.helpers.list_instances", mock_list_instances):
            result = list_mapdl_instances(mock_context_no_mapdl)

            # Verify list_instances was called with long=True
            mock_list_instances.assert_called_once_with(long=True, instances=True)
            assert result.content[0].text == "Sample output"

    def test_list_instances_multiple_instances(self, mock_context_no_mapdl):
        """Test list_mapdl_instances with multiple running instances."""
        # Mock the list_instances function with multiple instances
        mock_output = """Name      Is Instance    Status      gRPC port    PID    Command line                Working directory
------  -------------  --------  -----------  -----  -------------------------  ------------------------------------
ansys     True          running         50052  12345  ansys242 -grpc -port 50052  /tmp/ansys_workdir1
ansys     True          running         50053  12346  ansys242 -grpc -port 50053  /tmp/ansys_workdir2
ansys     True          running         50054  12347  ansys242 -grpc -port 50054  /tmp/ansys_workdir3"""  # noqa: E501

        with patch("ansys.mapdl.mcp.helpers.list_instances", return_value=mock_output):
            result = list_mapdl_instances(mock_context_no_mapdl)

            # Verify all instances are included in output
            assert "ansys" in result.content[0].text
            assert "50052" in result.content[0].text

    def test_list_instances_return_value_propagation(self, mock_context_no_mapdl):
        """Test that list_mapdl_instances correctly propagates the return value from helpers.list_instances."""  # noqa: E501
        mock_output = "Sample output with instance information"
        with patch("ansys.mapdl.mcp.helpers.list_instances", return_value=mock_output) as mock_list:
            result = list_mapdl_instances(mock_context_no_mapdl)

            # Verify the helper function was called with correct parameters
            mock_list.assert_called_once_with(long=True, instances=True)

            # Verify the result is correctly propagated
            assert result.content[0].text == mock_output

    def test_list_instances_output_format(self, mock_context_no_mapdl):
        """Test that list_mapdl_instances returns properly formatted output with table headers."""
        # Mock output with all expected headers
        mock_output = """Name      Status      gRPC port    PID    Command line                Working directory
------  --------  -----------  -----  -------------------------  -------------------
ansys     True          running         50052  12345  ansys242 -grpc -port 50052  /tmp/ansys_tmp"""  # noqa: E501

        with patch("ansys.mapdl.mcp.helpers.list_instances", return_value=mock_output):
            result = list_mapdl_instances(mock_context_no_mapdl)

            # Verify all expected headers are present
            assert "Name" in result.content[0].text
            assert "Status" in result.content[0].text
            assert "gRPC port" in result.content[0].text
            assert "PID" in result.content[0].text

    def test_list_instances_no_crash(self, mock_context_no_mapdl):
        """Test that list_mapdl_instances never crashes even if helper raises exception."""
        # Mock the list_instances to return a valid string even in error cases
        mock_output = "Error: Unable to list instances"
        with patch("ansys.mapdl.mcp.helpers.list_instances", return_value=mock_output):
            result = list_mapdl_instances(mock_context_no_mapdl)

            # Should return a string, not raise exception
            assert isinstance(result, ToolResult)
            assert result is not None

    def test_list_instances_consistent_calls(self, mock_context_no_mapdl):
        """Test that multiple calls to list_mapdl_instances return consistent format."""
        mock_output = """Name      Status      gRPC port    PID    Command line                Working directory
------  --------  -----------  -----  -------------------------  -------------------"""  # noqa: E501

        with patch("ansys.mapdl.mcp.helpers.list_instances", return_value=mock_output):
            result1 = list_mapdl_instances(mock_context_no_mapdl)
            result2 = list_mapdl_instances(mock_context_no_mapdl)

            # Both should be strings with same format
            assert isinstance(result1, ToolResult)
            assert isinstance(result2, ToolResult)
            assert result1.content[0].text == result2.content[0].text

    def test_list_instances_includes_remote_connected_instance(self, mock_context_no_mapdl):
        """Test that list_mapdl_instances includes remotely connected instances from context."""
        mock_local_output = """Name    Status    gRPC port    PID    Command line    Working directory
------  --------  -----------  -----  --------------  -------------------"""  # noqa: E501

        # Set up a remote MAPDL instance in the context
        remote_mapdl = MagicMock()
        remote_mapdl.is_local = False
        remote_mapdl.ip = "192.168.1.100"
        remote_mapdl.port = 50052
        remote_mapdl.check_status = "RUNNING"
        remote_mapdl.version = "2024 R2"
        remote_mapdl.directory = "/remote/workdir"
        mock_context_no_mapdl.request_context.lifespan_context.mapdl = remote_mapdl

        with patch("ansys.mapdl.mcp.helpers.list_instances", return_value=mock_local_output):
            result = list_mapdl_instances(mock_context_no_mapdl)

        assert "Remotely connected instance" in result.content[0].text
        assert "192.168.1.100" in result.content[0].text
        assert "50052" in result.content[0].text
        assert "RUNNING" in result.content[0].text
        assert "2024 R2" in result.content[0].text
        assert "/remote/workdir" in result.content[0].text

    def test_list_instances_local_connected_instance_not_duplicated(self, mock_context):
        """Test that a locally connected instance is not added as a remote section."""
        mock_local_output = """Name    Status    gRPC port    PID
------  --------  -----------  -----
ansys   running   50052        12345"""

        # mock_context has a local MAPDL instance (is_local=True)
        assert mock_context.request_context.lifespan_context.mapdl.is_local is True

        with patch("ansys.mapdl.mcp.helpers.list_instances", return_value=mock_local_output):
            result = list_mapdl_instances(mock_context)

        assert "Remotely connected instance" not in result.content[0].text
        assert result.content[0].text == mock_local_output


@pytest.mark.unit
class TestConnectToMapdl:
    """Tests for connect_to_mapdl tool."""

    @pytest.mark.asyncio
    async def test_connect_default_parameters(self, mock_context_no_mapdl):
        """Test connecting to MAPDL with default parameters."""
        # Create a mock MAPDL instance
        mock_mapdl = MagicMock()
        mock_mapdl.version = "2024 R2"
        mock_mapdl._ip = "localhost"
        mock_mapdl._port = 50052

        with patch("ansys.mapdl.core.Mapdl", return_value=mock_mapdl):
            result = await connect_to_mapdl(mock_context_no_mapdl)

            # Verify successful connection
            assert isinstance(result, ToolResult)
            assert "Successfully connected to MAPDL" in result.content[0].text
            assert "localhost:50052" in result.content[0].text
            assert "2024 R2" in result.content[0].text

            # Verify MAPDL was stored in context
            assert mock_context_no_mapdl.request_context.lifespan_context.mapdl == mock_mapdl

    @pytest.mark.asyncio
    async def test_connect_custom_port(self, mock_context_no_mapdl):
        """Test connecting to MAPDL with custom port."""
        mock_mapdl = MagicMock()
        mock_mapdl.version = "2024 R1"
        mock_mapdl._ip = "localhost"
        mock_mapdl._port = 50053

        with patch("ansys.mapdl.core.Mapdl", return_value=mock_mapdl) as mock_mapdl_class:
            result = await connect_to_mapdl(mock_context_no_mapdl, port=50053)

            # Verify connection with custom port
            assert "Successfully connected to MAPDL" in result.content[0].text
            assert "localhost:50053" in result.content[0].text

            # Verify Mapdl was called with correct parameters
            mock_mapdl_class.assert_called_once_with(
                start_instance=False,
                ip="localhost",
                port=50053,
                cleanup_on_exit=False,
                loglevel="INFO",
            )

    @pytest.mark.asyncio
    async def test_connect_custom_ip(self, mock_context_no_mapdl):
        """Test connecting to MAPDL with custom IP address."""
        mock_mapdl = MagicMock()
        mock_mapdl.version = "2024 R2"
        mock_mapdl._ip = "192.168.1.100"
        mock_mapdl._port = 50052

        with patch("ansys.mapdl.core.Mapdl", return_value=mock_mapdl) as mock_mapdl_class:
            result = await connect_to_mapdl(mock_context_no_mapdl, ip="192.168.1.100")

            # Verify connection with custom IP
            assert "Successfully connected to MAPDL" in result.content[0].text
            assert "192.168.1.100:50052" in result.content[0].text

            # Verify Mapdl was called with correct parameters
            mock_mapdl_class.assert_called_once()
            call_args = mock_mapdl_class.call_args[1]

            assert "start_instance" in call_args and not call_args["start_instance"]
            assert "ip" in call_args and call_args["ip"] == "192.168.1.100"
            assert "port" in call_args and call_args["port"] is not None
            assert "cleanup_on_exit" in call_args and not call_args["cleanup_on_exit"]
            assert "loglevel" in call_args and call_args["loglevel"] == "INFO"

    @pytest.mark.asyncio
    async def test_connect_custom_ip_and_port(self, mock_context_no_mapdl):
        """Test connecting to MAPDL with both custom IP and port."""
        mock_mapdl = MagicMock()
        mock_mapdl.version = "2024 R2"
        mock_mapdl._ip = "10.0.0.50"
        mock_mapdl._port = 50099

        with patch("ansys.mapdl.core.Mapdl", return_value=mock_mapdl) as mock_mapdl_class:
            result = await connect_to_mapdl(mock_context_no_mapdl, port=50099, ip="10.0.0.50")

            # Verify connection with custom parameters
            assert "Successfully connected to MAPDL" in result.content[0].text
            assert "10.0.0.50:50099" in result.content[0].text

            # Verify Mapdl was called with correct parameters
            mock_mapdl_class.assert_called_once_with(
                start_instance=False,
                ip="10.0.0.50",
                port=50099,
                cleanup_on_exit=False,
                loglevel="INFO",
            )

    @pytest.mark.asyncio
    async def test_connect_already_connected(self, mock_context):
        """Test connecting when already connected."""
        # Context already has a MAPDL connection
        result = await connect_to_mapdl(mock_context)

        # Verify appropriate error message
        assert "Already connected to MAPDL" in result.content[0].text
        assert "disconnect first" in result.content[0].text

    @pytest.mark.asyncio
    async def test_connect_with_crashed_mapdl(self, mock_context):
        """Test connecting when cached MAPDL instance has crashed (_exited=True)."""
        mock_context.request_context.lifespan_context.mapdl._exited = True

        mock_new_mapdl = MagicMock()
        mock_new_mapdl.version = "2024 R2"
        mock_new_mapdl._ip = "127.0.0.1"
        mock_new_mapdl._port = 50052

        with patch("ansys.mapdl.core.Mapdl", return_value=mock_new_mapdl):
            result = await connect_to_mapdl(mock_context)

        # Should succeed, not return "Already connected" error
        assert "Successfully connected" in result.content[0].text
        assert mock_context.request_context.lifespan_context.mapdl is mock_new_mapdl

    @pytest.mark.asyncio
    async def test_connect_with_exiting_mapdl(self, mock_context):
        """Test connecting when cached MAPDL instance is exiting (_exiting=True)."""
        mock_context.request_context.lifespan_context.mapdl._exiting = True

        mock_new_mapdl = MagicMock()
        mock_new_mapdl.version = "2024 R2"
        mock_new_mapdl._ip = "127.0.0.1"
        mock_new_mapdl._port = 50052

        with patch("ansys.mapdl.core.Mapdl", return_value=mock_new_mapdl):
            result = await connect_to_mapdl(mock_context)

        # Should succeed, not return "Already connected" error
        assert "Successfully connected" in result.content[0].text
        assert mock_context.request_context.lifespan_context.mapdl is mock_new_mapdl

    @pytest.mark.asyncio
    async def test_connect_connection_error(self, mock_context_no_mapdl):
        """Test handling connection errors."""
        with patch("ansys.mapdl.core.Mapdl", side_effect=Exception("Connection refused")):
            result = await connect_to_mapdl(mock_context_no_mapdl, port=50052, ip="localhost")

            # Verify error message is returned
            assert "Failed to connect to MAPDL" in result.content[0].text
            assert "Connection refused" in result.content[0].text

            # Verify context remains empty
            assert mock_context_no_mapdl.request_context.lifespan_context.mapdl is None

    @pytest.mark.asyncio
    async def test_connect_network_error(self, mock_context_no_mapdl):
        """Test handling network errors during connection."""
        with patch("ansys.mapdl.core.Mapdl", side_effect=ConnectionError("Network unreachable")):
            result = await connect_to_mapdl(mock_context_no_mapdl, port=50052, ip="192.168.1.999")

            # Verify error message
            assert "Failed to connect to MAPDL" in result.content[0].text
            assert "Network unreachable" in result.content[0].text

    @pytest.mark.asyncio
    async def test_connect_timeout_error(self, mock_context_no_mapdl):
        """Test handling timeout errors during connection."""
        with patch("ansys.mapdl.core.Mapdl", side_effect=TimeoutError("Connection timed out")):
            result = await connect_to_mapdl(mock_context_no_mapdl)

            # Verify timeout error is handled
            assert "Failed to connect to MAPDL" in result.content[0].text
            assert "Connection timed out" in result.content[0].text

    @pytest.mark.asyncio
    async def test_connect_stores_mapdl_in_context(self, mock_context_no_mapdl):
        """Test that connected MAPDL instance is properly stored in context."""
        mock_mapdl = MagicMock()
        mock_mapdl.version = "2024 R2"
        mock_mapdl._ip = "localhost"
        mock_mapdl._port = 50052

        # Verify context starts with no MAPDL
        assert mock_context_no_mapdl.request_context.lifespan_context.mapdl is None

        with patch("ansys.mapdl.core.Mapdl", return_value=mock_mapdl):
            result = await connect_to_mapdl(mock_context_no_mapdl)

            # Verify successful connection
            assert "Successfully connected" in result.content[0].text

            # Verify MAPDL is stored in context
            assert mock_context_no_mapdl.request_context.lifespan_context.mapdl is not None
            assert mock_context_no_mapdl.request_context.lifespan_context.mapdl == mock_mapdl

    @pytest.mark.asyncio
    async def test_connect_result_message(self, mock_context_no_mapdl):
        """Test that connect_to_mapdl returns informative success message."""
        mock_mapdl = MagicMock()
        mock_mapdl.version = "2024 R2"
        mock_mapdl._ip = "localhost"
        mock_mapdl._port = 50052

        with patch("ansys.mapdl.core.Mapdl", return_value=mock_mapdl):
            result = await connect_to_mapdl(mock_context_no_mapdl)

            # Verify the result contains connection information
            assert isinstance(result, ToolResult)
            assert "Successfully connected to MAPDL at localhost:50052" in result.content[0].text
            assert "2024 R2" in result.content[0].text


@pytest.mark.unit
class TestDisconnectFromMapdl:
    """Tests for disconnect_from_mapdl tool."""

    @pytest.mark.asyncio
    async def test_disconnect_success(self, mock_context):
        """Test disconnecting from MAPDL successfully."""
        # Set up IP and port attributes on mock MAPDL
        mock_context.request_context.lifespan_context.mapdl._ip = "localhost"
        mock_context.request_context.lifespan_context.mapdl._port = 50052

        # Store reference to check exit was called
        mapdl_ref = mock_context.request_context.lifespan_context.mapdl

        result = await disconnect_from_mapdl(mock_context)

        # Verify successful disconnection
        assert isinstance(result, ToolResult)
        assert "Successfully disconnected from MAPDL" in result.content[0].text
        assert "localhost:50052" in result.content[0].text

        # Verify exit was called on the original object
        mapdl_ref.exit.assert_called_once()

        # Verify MAPDL was removed from context
        assert mock_context.request_context.lifespan_context.mapdl is None

    @pytest.mark.asyncio
    async def test_disconnect_no_connection(self, mock_context_no_mapdl):
        """Test disconnecting when no connection exists."""
        result = await disconnect_from_mapdl(mock_context_no_mapdl)

        # Verify appropriate message
        assert "No MAPDL connection to disconnect" in result.content[0].text

    @pytest.mark.asyncio
    async def test_disconnect_clears_context(self, mock_context):
        """Test that disconnect properly clears the context."""
        mock_context.request_context.lifespan_context.mapdl._ip = "localhost"
        mock_context.request_context.lifespan_context.mapdl._port = 50052

        # Verify MAPDL exists before disconnect
        assert mock_context.request_context.lifespan_context.mapdl is not None

        await disconnect_from_mapdl(mock_context)

        # Verify MAPDL is cleared after disconnect
        assert mock_context.request_context.lifespan_context.mapdl is None

    @pytest.mark.asyncio
    async def test_disconnect_error_during_exit(self, mock_context):
        """Test handling errors during disconnection."""
        mock_context.request_context.lifespan_context.mapdl._ip = "localhost"
        mock_context.request_context.lifespan_context.mapdl._port = 50052
        mock_context.request_context.lifespan_context.mapdl.exit.side_effect = Exception(
            "Disconnection error"
        )

        result = await disconnect_from_mapdl(mock_context)

        # Verify error message is returned
        assert "Error during disconnect" in result.content[0].text
        assert "Disconnection error" in result.content[0].text

        # Verify context is still cleared even on error
        assert mock_context.request_context.lifespan_context.mapdl is None

    @pytest.mark.asyncio
    async def test_disconnect_connection_lost(self, mock_context):
        """Test disconnecting when connection is already lost."""
        mock_context.request_context.lifespan_context.mapdl._ip = "localhost"
        mock_context.request_context.lifespan_context.mapdl._port = 50052
        mock_context.request_context.lifespan_context.mapdl.exit.side_effect = ConnectionError(
            "Connection already closed"
        )

        result = await disconnect_from_mapdl(mock_context)

        # Verify error is handled gracefully
        assert "Error during disconnect" in result.content[0].text
        assert "Connection already closed" in result.content[0].text

        # Context should still be cleared
        assert mock_context.request_context.lifespan_context.mapdl is None

    @pytest.mark.asyncio
    async def test_disconnect_return_message(self, mock_context):
        """Test that disconnect_from_mapdl returns informative message."""
        mock_context.request_context.lifespan_context.mapdl._ip = "localhost"
        mock_context.request_context.lifespan_context.mapdl._port = 50052

        result = await disconnect_from_mapdl(mock_context)

        # Verify the result contains disconnection information
        assert isinstance(result, ToolResult)
        assert "Successfully disconnected from MAPDL at localhost:50052" in result.content[0].text

    @pytest.mark.asyncio
    async def test_disconnect_custom_ip_port(self, mock_context):
        """Test disconnecting from MAPDL with custom IP and port."""
        mock_context.request_context.lifespan_context.mapdl._ip = "192.168.1.100"
        mock_context.request_context.lifespan_context.mapdl._port = 50053

        result = await disconnect_from_mapdl(mock_context)

        # Verify disconnection message includes custom IP and port
        assert (
            "Successfully disconnected from MAPDL at 192.168.1.100:50053" in result.content[0].text
        )


@pytest.mark.unit
class TestLaunchMapdl:
    """Tests for launch_mapdl_session tool."""

    @pytest.mark.asyncio
    async def test_launch_default_parameters(self, mock_context_no_mapdl):
        """Test launching MAPDL with default parameters."""
        # Create a mock MAPDL instance
        mock_mapdl = MagicMock()
        mock_mapdl.version = "2024 R2"
        mock_mapdl._ip = "127.0.0.1"
        mock_mapdl._port = 50052
        mock_mapdl.ip = "127.0.0.1"
        mock_mapdl.port = 50052
        mock_mapdl.directory = "/tmp/ansys_mapdl_1234"

        with patch("ansys.mapdl.core.launch_mapdl", return_value=mock_mapdl) as mock_launch:
            result = await launch_mapdl_session(ctx=mock_context_no_mapdl)

            # Verify successful launch
            assert isinstance(result, ToolResult)
            assert "Successfully launched MAPDL" in result.content[0].text
            assert "127.0.0.1:50052" in result.content[0].text
            assert "2024 R2" in result.content[0].text
            assert "/tmp/ansys_mapdl_1234" in result.content[0].text

            # Verify launch_mapdl was called with correct parameters
            mock_launch.assert_called_once_with(nproc=None, loglevel="INFO", port=None)

            # Verify MAPDL was stored in context
            assert mock_context_no_mapdl.request_context.lifespan_context.mapdl == mock_mapdl

    @pytest.mark.asyncio
    async def test_launch_custom_nproc(self, mock_context_no_mapdl):
        """Test launching MAPDL with custom number of processors."""
        mock_mapdl = MagicMock()
        mock_mapdl.version = "2024 R2"
        mock_mapdl._ip = "127.0.0.1"
        mock_mapdl._port = 50052
        mock_mapdl.ip = "127.0.0.1"
        mock_mapdl.port = 50052
        mock_mapdl.directory = "/tmp/ansys_mapdl_1234"

        with patch("ansys.mapdl.core.launch_mapdl", return_value=mock_mapdl) as mock_launch:
            result = await launch_mapdl_session(ctx=mock_context_no_mapdl, nproc=4)

            # Verify successful launch
            assert "Successfully launched MAPDL" in result.content[0].text

            # Verify launch_mapdl was called with correct nproc
            mock_launch.assert_called_once_with(nproc=4, loglevel="INFO", port=None)

    @pytest.mark.asyncio
    async def test_launch_custom_exec_file(self, mock_context_no_mapdl):
        """Test launching MAPDL with custom executable path."""
        mock_mapdl = MagicMock()
        mock_mapdl.version = "2024 R2"
        mock_mapdl._ip = "127.0.0.1"
        mock_mapdl._port = 50052
        mock_mapdl.ip = "127.0.0.1"
        mock_mapdl.port = 50052
        mock_mapdl.directory = "/tmp/ansys_mapdl_1234"

        exec_path = "/usr/ansys_inc/v242/ansys/bin/ansys242"

        with patch("ansys.mapdl.core.launch_mapdl", return_value=mock_mapdl) as mock_launch:
            result = await launch_mapdl_session(ctx=mock_context_no_mapdl, exec_file=exec_path)

            # Verify successful launch
            assert "Successfully launched MAPDL" in result.content[0].text

            # Verify launch_mapdl was called with exec_file
            mock_launch.assert_called_once_with(
                nproc=None, loglevel="INFO", port=None, exec_file=exec_path
            )

    @pytest.mark.asyncio
    async def test_launch_custom_run_location(self, mock_context_no_mapdl):
        """Test launching MAPDL with custom working directory."""
        mock_mapdl = MagicMock()
        mock_mapdl.version = "2024 R2"
        mock_mapdl._ip = "127.0.0.1"
        mock_mapdl._port = 50052
        mock_mapdl.ip = "127.0.0.1"
        mock_mapdl.port = 50052
        mock_mapdl.directory = "/custom/working/dir"

        run_loc = "/custom/working/dir"

        with patch("ansys.mapdl.core.launch_mapdl", return_value=mock_mapdl) as mock_launch:
            result = await launch_mapdl_session(ctx=mock_context_no_mapdl, run_location=run_loc)

            # Verify successful launch
            assert "Successfully launched MAPDL" in result.content[0].text
            assert "/custom/working/dir" in result.content[0].text

            # Verify launch_mapdl was called with run_location
            mock_launch.assert_called_once_with(
                nproc=None, loglevel="INFO", port=None, run_location=run_loc
            )

    @pytest.mark.asyncio
    async def test_launch_with_additional_switches(self, mock_context_no_mapdl):
        """Test launching MAPDL with additional command line switches."""
        mock_mapdl = MagicMock()
        mock_mapdl.version = "2024 R2"
        mock_mapdl._ip = "127.0.0.1"
        mock_mapdl._port = 50052
        mock_mapdl.ip = "127.0.0.1"
        mock_mapdl.port = 50052
        mock_mapdl.directory = "/tmp/ansys_mapdl_1234"

        switches = "-smp"

        with patch("ansys.mapdl.core.launch_mapdl", return_value=mock_mapdl) as mock_launch:
            result = await launch_mapdl_session(
                ctx=mock_context_no_mapdl, additional_switches=switches
            )

            # Verify successful launch
            assert "Successfully launched MAPDL" in result.content[0].text

            # Verify launch_mapdl was called with additional_switches
            mock_launch.assert_called_once_with(
                nproc=None, loglevel="INFO", port=None, additional_switches=switches
            )

    @pytest.mark.asyncio
    async def test_launch_all_custom_parameters(self, mock_context_no_mapdl):
        """Test launching MAPDL with all custom parameters."""
        mock_mapdl = MagicMock()
        mock_mapdl.version = "2024 R1"
        mock_mapdl._ip = "127.0.0.1"
        mock_mapdl._port = 50053
        mock_mapdl.ip = "127.0.0.1"
        mock_mapdl.port = 50053
        mock_mapdl.directory = "/custom/work/dir"

        exec_path = "/usr/ansys_inc/v241/ansys/bin/ansys241"
        run_loc = "/custom/work/dir"
        switches = "-smp -db 1024"

        with patch("ansys.mapdl.core.launch_mapdl", return_value=mock_mapdl) as mock_launch:
            result = await launch_mapdl_session(
                ctx=mock_context_no_mapdl,
                exec_file=exec_path,
                run_location=run_loc,
                nproc=8,
                additional_switches=switches,
            )

            # Verify successful launch
            assert "Successfully launched MAPDL" in result.content[0].text
            assert "127.0.0.1:50053" in result.content[0].text
            assert "2024 R1" in result.content[0].text

            # Verify launch_mapdl was called with all parameters
            mock_launch.assert_called_once_with(
                nproc=8,
                loglevel="INFO",
                port=None,
                exec_file=exec_path,
                run_location=run_loc,
                additional_switches=switches,
            )

    @pytest.mark.asyncio
    async def test_launch_already_connected(self, mock_context):
        """Test launching when already connected to MAPDL."""
        # Context already has a MAPDL connection
        result = await launch_mapdl_session(ctx=mock_context)

        # Verify appropriate error message
        assert "Already connected to MAPDL" in result.content[0].text
        assert "disconnect first" in result.content[0].text

    @pytest.mark.asyncio
    async def test_launch_with_crashed_mapdl(self, mock_context):
        """Test launching when cached MAPDL instance has crashed (_exited=True)."""
        mock_context.request_context.lifespan_context.mapdl._exited = True

        mock_new_mapdl = MagicMock()
        mock_new_mapdl.version = "2024 R2"
        mock_new_mapdl.ip = "127.0.0.1"
        mock_new_mapdl.port = 50052
        mock_new_mapdl.directory = "/tmp"

        with patch("ansys.mapdl.core.launch_mapdl", return_value=mock_new_mapdl):
            result = await launch_mapdl_session(ctx=mock_context)

        # Should succeed, not return "Already connected" error
        assert "Successfully launched MAPDL" in result.content[0].text
        assert mock_context.request_context.lifespan_context.mapdl is mock_new_mapdl

    @pytest.mark.asyncio
    async def test_launch_with_exiting_mapdl(self, mock_context):
        """Test launching when cached MAPDL instance is exiting (_exiting=True)."""
        mock_context.request_context.lifespan_context.mapdl._exiting = True

        mock_new_mapdl = MagicMock()
        mock_new_mapdl.version = "2024 R2"
        mock_new_mapdl.ip = "127.0.0.1"
        mock_new_mapdl.port = 50052
        mock_new_mapdl.directory = "/tmp"

        with patch("ansys.mapdl.core.launch_mapdl", return_value=mock_new_mapdl):
            result = await launch_mapdl_session(ctx=mock_context)

        # Should succeed, not return "Already connected" error
        assert "Successfully launched MAPDL" in result.content[0].text
        assert mock_context.request_context.lifespan_context.mapdl is mock_new_mapdl

    @pytest.mark.asyncio
    async def test_launch_error(self, mock_context_no_mapdl):
        """Test handling launch errors."""
        with patch(
            "ansys.mapdl.core.launch_mapdl",
            side_effect=Exception("MAPDL executable not found"),
        ):
            result = await launch_mapdl_session(ctx=mock_context_no_mapdl)

            # Verify error message is returned
            assert "Failed to launch MAPDL" in result.content[0].text
            assert "MAPDL executable not found" in result.content[0].text

            # Verify context remains empty
            assert mock_context_no_mapdl.request_context.lifespan_context.mapdl is None

    @pytest.mark.asyncio
    async def test_launch_license_error(self, mock_context_no_mapdl):
        """Test handling license errors during launch."""
        with patch(
            "ansys.mapdl.core.launch_mapdl",
            side_effect=Exception("No ANSYS license available"),
        ):
            result = await launch_mapdl_session(ctx=mock_context_no_mapdl)

            # Verify error message
            assert "Failed to launch MAPDL" in result.content[0].text
            assert "No ANSYS license available" in result.content[0].text

    @pytest.mark.asyncio
    async def test_launch_stores_mapdl_in_context(self, mock_context_no_mapdl):
        """Test that launched MAPDL instance is properly stored in context."""
        mock_mapdl = MagicMock()
        mock_mapdl.version = "2024 R2"
        mock_mapdl._ip = "127.0.0.1"
        mock_mapdl._port = 50052
        mock_mapdl.ip = "127.0.0.1"
        mock_mapdl.port = 50052
        mock_mapdl.directory = "/tmp/ansys_mapdl_1234"

        # Verify context starts with no MAPDL
        assert mock_context_no_mapdl.request_context.lifespan_context.mapdl is None

        with patch("ansys.mapdl.core.launch_mapdl", return_value=mock_mapdl):
            result = await launch_mapdl_session(ctx=mock_context_no_mapdl)

            # Verify successful launch
            assert "Successfully launched MAPDL" in result.content[0].text

            # Verify MAPDL is stored in context
            assert mock_context_no_mapdl.request_context.lifespan_context.mapdl is not None
            assert mock_context_no_mapdl.request_context.lifespan_context.mapdl == mock_mapdl

    @pytest.mark.asyncio
    async def test_launch_result_message(self, mock_context_no_mapdl):
        """Test that launch_mapdl_session returns informative success message."""
        mock_mapdl = MagicMock()
        mock_mapdl.version = "2024 R2"
        mock_mapdl._ip = "127.0.0.1"
        mock_mapdl._port = 50052
        mock_mapdl.ip = "127.0.0.1"
        mock_mapdl.port = 50052
        mock_mapdl.directory = "/tmp/ansys_mapdl_1234"

        with patch("ansys.mapdl.core.launch_mapdl", return_value=mock_mapdl):
            result = await launch_mapdl_session(ctx=mock_context_no_mapdl)

            # Verify the result contains launch information
            assert isinstance(result, ToolResult)
            assert "Successfully launched MAPDL at 127.0.0.1:50052" in result.content[0].text
            assert "2024 R2" in result.content[0].text
            assert "/tmp/ansys_mapdl_1234" in result.content[0].text

    @pytest.mark.asyncio
    async def test_launch_with_port_parameter(self, mock_context_no_mapdl):
        """Test launching MAPDL with specific port parameter."""
        mock_mapdl = MagicMock()
        mock_mapdl.version = "2024 R2"
        mock_mapdl._ip = "127.0.0.1"
        mock_mapdl._port = 50060
        mock_mapdl.ip = "127.0.0.1"
        mock_mapdl.port = 50060
        mock_mapdl.directory = "/tmp/ansys_mapdl_1234"

        with patch("ansys.mapdl.core.launch_mapdl", return_value=mock_mapdl) as mock_launch:
            result = await launch_mapdl_session(ctx=mock_context_no_mapdl, port=50060)

            # Verify successful launch
            assert isinstance(result, ToolResult)
            assert "Successfully launched MAPDL" in result.content[0].text
            assert "50060" in result.content[0].text

            # Verify launch_mapdl was called with port
            mock_launch.assert_called_once_with(nproc=None, loglevel="INFO", port=50060)

    @pytest.mark.asyncio
    async def test_launch_connection_info_in_result(self, mock_context_no_mapdl):
        """Test that launch result contains all connection info."""
        mock_mapdl = MagicMock()
        mock_mapdl.version = "2024 R2"
        mock_mapdl._ip = "192.168.1.50"
        mock_mapdl._port = 50055
        mock_mapdl.ip = "192.168.1.50"
        mock_mapdl.port = 50055
        mock_mapdl.directory = "/home/user/mapdl_work"

        with patch("ansys.mapdl.core.launch_mapdl", return_value=mock_mapdl):
            result = await launch_mapdl_session(ctx=mock_context_no_mapdl)

            # Verify all connection details are in result
            assert "192.168.1.50:50055" in result.content[0].text
            assert "MAPDL Version: 2024 R2" in result.content[0].text
            assert "Working Directory: /home/user/mapdl_work" in result.content[0].text


@pytest.mark.unit
class TestConnectionLifecycle:
    """Tests for the full connection lifecycle."""

    @pytest.mark.asyncio
    async def test_connect_use_disconnect_workflow(self, mock_context_no_mapdl):
        """Test complete workflow: connect, use, disconnect."""
        # Create mock MAPDL
        mock_mapdl = MagicMock()
        mock_mapdl.name = "MAPDL"
        mock_mapdl.status = "Running"
        mock_mapdl.version = 24.2
        mock_mapdl._ip = "localhost"
        mock_mapdl._port = 50052
        mock_mapdl.is_alive = True
        mock_mapdl.is_local = True
        mock_mapdl.port = 50052
        mock_mapdl.ip = "localhost"
        mock_mapdl.directory = "/tmp/test"
        mock_mapdl.platform = "linux"
        mock_mapdl.jobname = "file"
        mock_mapdl.check_status = "running"
        mock_mapdl._exited = False
        mock_mapdl._exiting = False

        mock_mapdl.com = MagicMock(return_value="Comment written")
        mock_mapdl.run = MagicMock(return_value="Command executed")
        # Add required class mocks
        mock_mapdl.info = MagicMock()
        mock_mapdl.info.title = ""
        mock_mapdl.info.jobname = ""
        mock_mapdl.info.routine = ""
        mock_mapdl.info.units = ""
        mock_mapdl.info.revision = ""
        mock_mapdl.info.product = ""
        mock_mapdl.geometry = MagicMock()
        mock_mapdl.geometry.n_keypoint = 0
        mock_mapdl.geometry.n_line = 0
        mock_mapdl.geometry.n_area = 0
        mock_mapdl.geometry.n_volu = 0
        mock_mapdl.post_processing = MagicMock()
        mock_mapdl.post_processing.nsets = 0
        mock_mapdl.mesh = MagicMock()
        mock_mapdl.mesh.n_node = 0
        mock_mapdl.mesh.n_elem = 0

        # Step 1: Connect
        with patch("ansys.mapdl.core.Mapdl", return_value=mock_mapdl):
            result = await connect_to_mapdl(mock_context_no_mapdl)
            assert "Successfully connected" in result.content[0].text

        # Step 2: Use MAPDL
        status = check_mapdl_status(mock_context_no_mapdl)
        status_data = json.loads(status.content[0].text)
        assert "connection" in status_data
        assert status_data["connection"]["version"] == 24.2

        command_result = run_mapdl_command(mock_context_no_mapdl, "/PREP7")
        assert "MAPDL command executed successfully" in command_result.content[0].text

        # Step 3: Disconnect
        result = await disconnect_from_mapdl(mock_context_no_mapdl)
        assert "Successfully disconnected" in result.content[0].text

        # Step 4: Verify connection is cleared
        status_after = check_mapdl_status(mock_context_no_mapdl)
        assert "No MAPDL connection available" in status_after.content[0].text

    @pytest.mark.asyncio
    async def test_reconnect_after_disconnect(self, mock_context_no_mapdl):
        """Test that we can reconnect after disconnecting."""
        mock_mapdl1 = MagicMock()
        mock_mapdl1.version = "2024 R2"
        mock_mapdl1._ip = "localhost"
        mock_mapdl1._port = 50052

        mock_mapdl2 = MagicMock()
        mock_mapdl2.version = "2024 R1"
        mock_mapdl2._ip = "localhost"
        mock_mapdl2._port = 50053

        # First connection
        with patch("ansys.mapdl.core.Mapdl", return_value=mock_mapdl1):
            result = await connect_to_mapdl(mock_context_no_mapdl, port=50052)
            assert "Successfully connected" in result.content[0].text
            assert "50052" in result.content[0].text

        # Disconnect
        await disconnect_from_mapdl(mock_context_no_mapdl)

        # Second connection with different parameters
        with patch("ansys.mapdl.core.Mapdl", return_value=mock_mapdl2):
            result = await connect_to_mapdl(mock_context_no_mapdl, port=50053)
            assert "Successfully connected" in result.content[0].text
            assert "50053" in result.content[0].text

    @pytest.mark.asyncio
    async def test_tools_without_connection(self, mock_context_no_mapdl):
        """Test that tools return appropriate messages without connection."""
        # Check status without connection
        status = check_mapdl_status(mock_context_no_mapdl)
        assert "No MAPDL connection available" in status.content[0].text

        # Try to run command without connection
        command_result = run_mapdl_command(mock_context_no_mapdl, "/PREP7")
        assert "No MAPDL connection available" in command_result.content[0].text


@pytest.mark.unit
class TestLaunchWorkflow:
    """Tests for launch and usage workflow."""

    @pytest.mark.asyncio
    async def test_launch_use_disconnect_workflow(self, mock_context_no_mapdl):
        """Test complete workflow: launch, use, disconnect."""
        # Create mock MAPDL
        mock_mapdl = MagicMock()
        mock_mapdl.name = "MAPDL"
        mock_mapdl.check_status = "Running"
        mock_mapdl.version = "2024 R2"
        mock_mapdl.ip = "127.0.0.1"
        mock_mapdl.port = 50052
        mock_mapdl.jobname = "file"
        mock_mapdl.directory = "/tmp/ansys_mapdl_1234"
        mock_mapdl.is_alive = True
        mock_mapdl.is_local = True
        mock_mapdl._exited = False
        mock_mapdl._exiting = False
        mock_mapdl.platform = "linux"

        mock_mapdl.com = MagicMock(return_value="Comment written")
        mock_mapdl.run = MagicMock(return_value="Command executed")
        # Add required class mocks
        mock_mapdl.info = MagicMock()
        mock_mapdl.info.title = ""
        mock_mapdl.info.jobname = ""
        mock_mapdl.info.routine = ""
        mock_mapdl.info.units = ""
        mock_mapdl.info.revision = ""
        mock_mapdl.info.product = ""
        mock_mapdl.geometry = MagicMock()
        mock_mapdl.geometry.n_keypoint = 0
        mock_mapdl.geometry.n_line = 0
        mock_mapdl.geometry.n_area = 0
        mock_mapdl.geometry.n_volu = 0
        mock_mapdl.post_processing = MagicMock()
        mock_mapdl.post_processing.nsets = 0
        mock_mapdl.mesh = MagicMock()
        mock_mapdl.mesh.n_node = 0
        mock_mapdl.mesh.n_elem = 0

        # Step 1: Launch
        with patch("ansys.mapdl.core.launch_mapdl", return_value=mock_mapdl):
            result = await launch_mapdl_session(ctx=mock_context_no_mapdl, nproc=4)
            assert "Successfully launched MAPDL" in result.content[0].text

        # Step 2: Use MAPDL
        status = check_mapdl_status(mock_context_no_mapdl)
        status_data = json.loads(status.content[0].text)
        assert "connection" in status_data
        assert status_data["connection"]["version"] == "2024 R2"

        command_result = run_mapdl_command(mock_context_no_mapdl, "/PREP7")
        assert "MAPDL command executed successfully" in command_result.content[0].text

        # Step 3: Disconnect
        result = await disconnect_from_mapdl(mock_context_no_mapdl)
        assert "Successfully disconnected" in result.content[0].text

        # Step 4: Verify connection is cleared
        status_after = check_mapdl_status(mock_context_no_mapdl)
        assert "No MAPDL connection available" in status_after.content[0].text

    @pytest.mark.asyncio
    async def test_launch_after_disconnect(self, mock_context_no_mapdl):
        """Test that we can launch after disconnecting."""
        mock_mapdl1 = MagicMock()
        mock_mapdl1.version = "2024 R2"
        mock_mapdl1._ip = "127.0.0.1"
        mock_mapdl1._port = 50052
        mock_mapdl1.ip = "127.0.0.1"
        mock_mapdl1.port = 50052
        mock_mapdl1.directory = "/tmp/ansys_mapdl_1234"

        mock_mapdl2 = MagicMock()
        mock_mapdl2.version = "2024 R1"
        mock_mapdl2._ip = "127.0.0.1"
        mock_mapdl2._port = 50053
        mock_mapdl2.ip = "127.0.0.1"
        mock_mapdl2.port = 50053
        mock_mapdl2.directory = "/tmp/ansys_mapdl_5678"

        # First launch
        with patch("ansys.mapdl.core.launch_mapdl", return_value=mock_mapdl1):
            result = await launch_mapdl_session(ctx=mock_context_no_mapdl, nproc=None)
            assert "Successfully launched MAPDL" in result.content[0].text
            assert "50052" in result.content[0].text

        # Disconnect
        await disconnect_from_mapdl(mock_context_no_mapdl)

        # Second launch
        with patch("ansys.mapdl.core.launch_mapdl", return_value=mock_mapdl2):
            result = await launch_mapdl_session(ctx=mock_context_no_mapdl, nproc=4)
            assert "Successfully launched MAPDL" in result.content[0].text
            assert "50053" in result.content[0].text

    @pytest.mark.asyncio
    async def test_cannot_launch_when_connected(self, mock_context_no_mapdl):
        """Test that launching fails when already connected."""
        # First, connect to an existing instance
        mock_mapdl = MagicMock()
        mock_mapdl.version = "2024 R2"
        mock_mapdl._ip = "localhost"
        mock_mapdl._port = 50052

        with patch("ansys.mapdl.core.Mapdl", return_value=mock_mapdl):
            connect_result = await connect_to_mapdl(mock_context_no_mapdl)
            assert "Successfully connected" in connect_result.content[0].text

        # Now try to launch - should fail
        launch_result = await launch_mapdl_session(ctx=mock_context_no_mapdl)
        assert "Already connected to MAPDL" in launch_result.content[0].text
        assert "disconnect first" in launch_result.content[0].text


@pytest.mark.unit
class TestScreenshot:
    """Tests for screenshot tool."""

    def test_screenshot_success_png(self, mock_context, tmp_path):
        """Test capturing a screenshot successfully with PNG format."""
        # Create a fake PNG image file
        screenshot_path = tmp_path / "screenshot.png"
        fake_image_data = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        screenshot_path.write_bytes(fake_image_data)

        # Mock MAPDL screenshot method
        mock_context.request_context.lifespan_context.mapdl.screenshot.return_value = str(
            screenshot_path
        )

        result = screenshot(mock_context)

        # Verify result is a list
        assert isinstance(result, ToolResult)
        assert len(result.content) == 2

        # Verify text content
        text_content = result.content[0]
        assert isinstance(text_content, TextContent)
        assert text_content.type == "text"
        assert "Screenshot saved to:" in text_content.text
        assert str(screenshot_path) in text_content.text

        # Verify image content
        image_content = result.content[1]
        assert isinstance(image_content, ImageContent)
        assert image_content.type == "image"
        assert image_content.mimeType == "image/png"
        assert image_content.data is not None
        assert len(image_content.data) > 0

        decoded_data = base64.b64decode(image_content.data)
        assert decoded_data == fake_image_data

    def test_screenshot_success_jpeg(self, mock_context, tmp_path):
        """Test capturing a screenshot with JPEG format."""
        # Create a fake JPEG image file
        screenshot_path = tmp_path / "screenshot.jpg"
        fake_image_data = b"\xff\xd8\xff\xe0\x00\x10JFIF"
        screenshot_path.write_bytes(fake_image_data)

        # Mock MAPDL screenshot method
        mock_context.request_context.lifespan_context.mapdl.screenshot.return_value = str(
            screenshot_path
        )

        result = screenshot(mock_context)

        # Verify result structure
        assert isinstance(result, ToolResult)
        assert len(result.content) == 2

        # Verify MIME type is correct for JPEG
        image_content = result.content[1]
        assert isinstance(image_content, ImageContent)
        assert image_content.mimeType == "image/jpeg"

    def test_screenshot_success_jpeg_extension(self, mock_context, tmp_path):
        """Test capturing a screenshot with .jpeg extension."""
        # Create a fake image file with .jpeg extension
        screenshot_path = tmp_path / "screenshot.jpeg"
        fake_image_data = b"\xff\xd8\xff\xe0\x00\x10JFIF"
        screenshot_path.write_bytes(fake_image_data)

        # Mock MAPDL screenshot method
        mock_context.request_context.lifespan_context.mapdl.screenshot.return_value = str(
            screenshot_path
        )

        result = screenshot(mock_context)

        # Verify MIME type is correct for .jpeg extension
        image_content = result.content[1]
        assert isinstance(image_content, ImageContent)
        assert image_content.mimeType == "image/jpeg"

    def test_screenshot_success_bmp(self, mock_context, tmp_path):
        """Test capturing a screenshot with BMP format."""
        # Create a fake BMP image file
        screenshot_path = tmp_path / "screenshot.bmp"
        fake_image_data = b"BM\x00\x00\x00\x00\x00\x00\x00\x00"
        screenshot_path.write_bytes(fake_image_data)

        # Mock MAPDL screenshot method
        mock_context.request_context.lifespan_context.mapdl.screenshot.return_value = str(
            screenshot_path
        )

        result = screenshot(mock_context)

        # Verify MIME type is correct for BMP
        image_content = result.content[1]
        assert isinstance(image_content, ImageContent)
        assert image_content.mimeType == "image/bmp"

    def test_screenshot_success_gif(self, mock_context, tmp_path):
        """Test capturing a screenshot with GIF format."""
        # Create a fake GIF image file
        screenshot_path = tmp_path / "screenshot.gif"
        fake_image_data = b"GIF89a\x00\x00\x00\x00"
        screenshot_path.write_bytes(fake_image_data)

        # Mock MAPDL screenshot method
        mock_context.request_context.lifespan_context.mapdl.screenshot.return_value = str(
            screenshot_path
        )

        result = screenshot(mock_context)

        # Verify MIME type is correct for GIF
        image_content = result.content[1]
        assert isinstance(image_content, ImageContent)
        assert image_content.mimeType == "image/gif"

    def test_screenshot_without_mapdl(self, mock_context_no_mapdl):
        """Test screenshot when MAPDL is not available."""

        result = screenshot(mock_context_no_mapdl)

        # Verify error message is returned
        assert isinstance(result, ToolResult)
        assert len(result.content) == 1
        assert isinstance(result.content[0], TextContent)
        assert "No MAPDL connection available" in result.content[0].text
        assert "connect_to_mapdl" in result.content[0].text

    def test_screenshot_file_not_found(self, mock_context):
        """Test screenshot when the generated file is not found."""

        # Mock MAPDL screenshot to return a non-existent path
        nonexistent_path = "/tmp/nonexistent_screenshot.png"
        mock_context.request_context.lifespan_context.mapdl.screenshot.return_value = (
            nonexistent_path
        )

        result = screenshot(mock_context)

        # Verify error message is returned
        assert isinstance(result, ToolResult)
        assert len(result.content) == 1
        assert isinstance(result.content[0], TextContent)
        assert "Screenshot file not found" in result.content[0].text
        assert nonexistent_path in result.content[0].text

    def test_screenshot_mapdl_error(self, mock_context):
        """Test screenshot when MAPDL raises an error."""

        # Mock MAPDL screenshot to raise an exception
        mock_context.request_context.lifespan_context.mapdl.screenshot.side_effect = Exception(
            "Graphics window not available"
        )

        result = screenshot(mock_context)

        # Verify error message is returned
        assert isinstance(result, ToolResult)
        assert len(result.content) == 1
        assert isinstance(result.content[0], TextContent)
        assert "Failed to capture screenshot" in result.content[0].text
        assert "Graphics window not available" in result.content[0].text

    def test_screenshot_permission_error(self, mock_context, tmp_path):
        """Test screenshot when file cannot be read due to permissions."""

        # Create a screenshot file
        screenshot_path = tmp_path / "screenshot.png"
        screenshot_path.write_bytes(b"fake image data")

        # Mock MAPDL screenshot method
        mock_context.request_context.lifespan_context.mapdl.screenshot.return_value = str(
            screenshot_path
        )

        # Mock the file open to raise PermissionError
        with patch("builtins.open", side_effect=PermissionError("Permission denied")):
            result = screenshot(mock_context)

            # Verify error message is returned
            assert isinstance(result, ToolResult)
            assert len(result.content) == 1
            assert isinstance(result.content[0], TextContent)
            assert "Failed to capture screenshot" in result.content[0].text
            assert "Permission denied" in result.content[0].text

    def test_screenshot_base64_encoding(self, mock_context, tmp_path):
        """Test that screenshot data is properly base64 encoded."""
        # Create a fake image with known content
        screenshot_path = tmp_path / "screenshot.png"
        original_data = b"This is test image data with special chars: \x00\x01\x02\xff"
        screenshot_path.write_bytes(original_data)

        # Mock MAPDL screenshot method
        mock_context.request_context.lifespan_context.mapdl.screenshot.return_value = str(
            screenshot_path
        )

        result = screenshot(mock_context)

        # Get the image content
        image_content = result.content[1]
        assert isinstance(image_content, ImageContent)

        # Verify base64 encoding
        decoded_data = base64.b64decode(image_content.data)
        assert decoded_data == original_data

    def test_screenshot_large_image(self, mock_context, tmp_path):
        """Test screenshot with a large image file."""

        # Create a larger fake image (1MB)
        screenshot_path = tmp_path / "screenshot.png"
        large_image_data = b"\x89PNG" + b"\x00" * (1024 * 1024)
        screenshot_path.write_bytes(large_image_data)

        # Mock MAPDL screenshot method
        mock_context.request_context.lifespan_context.mapdl.screenshot.return_value = str(
            screenshot_path
        )

        result = screenshot(mock_context)

        # Verify screenshot succeeds with large file
        assert isinstance(result, ToolResult)
        assert len(result.content) == 2
        image_content = result.content[1]
        assert isinstance(image_content, ImageContent)
        assert len(image_content.data) > 0

    def test_screenshot_empty_file(self, mock_context, tmp_path):
        """Test screenshot with an empty file."""
        # Create an empty file
        screenshot_path = tmp_path / "screenshot.png"
        screenshot_path.write_bytes(b"")

        # Mock MAPDL screenshot method
        mock_context.request_context.lifespan_context.mapdl.screenshot.return_value = str(
            screenshot_path
        )

        result = screenshot(mock_context)

        # Verify screenshot handles empty file
        assert isinstance(result, ToolResult)
        assert len(result.content) == 2
        image_content = result.content[1]
        assert isinstance(image_content, ImageContent)
        # Empty file should produce empty base64 string
        assert image_content.data == ""

    def test_screenshot_calls_mapdl_method(self, mock_context, tmp_path):
        """Test that screenshot actually calls MAPDL's screenshot method."""
        # Create a fake image file
        screenshot_path = tmp_path / "screenshot.png"
        screenshot_path.write_bytes(b"fake image")

        # Mock MAPDL screenshot method
        mock_context.request_context.lifespan_context.mapdl.screenshot.return_value = str(
            screenshot_path
        )

        screenshot(mock_context)

        # Verify MAPDL's screenshot method was called
        mock_context.request_context.lifespan_context.mapdl.screenshot.assert_called_once()

    def test_screenshot_unknown_extension_defaults_to_png(self, mock_context, tmp_path):
        """Test that unknown file extensions default to PNG MIME type."""
        # Create a file with unknown extension
        screenshot_path = tmp_path / "screenshot.xyz"
        screenshot_path.write_bytes(b"fake image data")

        # Mock MAPDL screenshot method
        mock_context.request_context.lifespan_context.mapdl.screenshot.return_value = str(
            screenshot_path
        )

        result = screenshot(mock_context)

        # Verify it defaults to PNG
        image_content = result.content[1]
        assert isinstance(image_content, ImageContent)
        assert image_content.mimeType == "image/png"

    def test_screenshot_case_insensitive_extension(self, mock_context, tmp_path):
        """Test that file extension matching is case-insensitive."""
        # Create files with uppercase extensions
        for ext, expected_mime in [
            (".PNG", "image/png"),
            (".JPG", "image/jpeg"),
            (".JPEG", "image/jpeg"),
            (".BMP", "image/bmp"),
            (".GIF", "image/gif"),
        ]:
            screenshot_path = tmp_path / f"screenshot{ext}"
            screenshot_path.write_bytes(b"fake image")

            mock_context.request_context.lifespan_context.mapdl.screenshot.return_value = str(
                screenshot_path
            )

            result = screenshot(mock_context)
            image_content = result.content[1]
            assert isinstance(image_content, ImageContent)
            assert image_content.mimeType == expected_mime

    def test_screenshot_result_structure(self, mock_context, tmp_path):
        """Test that screenshot returns proper result structure."""
        # Create a fake image file
        screenshot_path = tmp_path / "screenshot.png"
        screenshot_path.write_bytes(b"fake image")

        # Mock MAPDL screenshot method
        mock_context.request_context.lifespan_context.mapdl.screenshot.return_value = str(
            screenshot_path
        )

        result = screenshot(mock_context)

        # Verify result structure
        assert isinstance(result, ToolResult)
        assert len(result.content) == 2
        assert isinstance(result.content[0], TextContent)
        assert isinstance(result.content[1], ImageContent)
        assert str(screenshot_path) in result.content[0].text

    def test_screenshot_error_message(self, mock_context):
        """Test that screenshot returns proper error message on failure."""
        # Mock MAPDL screenshot to raise an exception
        mock_context.request_context.lifespan_context.mapdl.screenshot.side_effect = Exception(
            "Test error"
        )

        result = screenshot(mock_context)

        # Verify error is in the return value
        assert isinstance(result, ToolResult)
        assert len(result.content) == 1
        assert isinstance(result.content[0], TextContent)
        assert "Failed to capture screenshot" in result.content[0].text
        assert "Test error" in result.content[0].text

    def test_screenshot_with_commands(self, mock_context, tmp_path):
        """Test that commands are executed via input_strings before taking screenshot."""
        screenshot_path = tmp_path / "screenshot.png"
        screenshot_path.write_bytes(b"fake image data")

        mock_context.request_context.lifespan_context.mapdl.screenshot.return_value = str(
            screenshot_path
        )

        result = screenshot(mock_context, commands="EPLOT")

        mock_context.request_context.lifespan_context.mapdl.input_strings.assert_called_once_with(
            "EPLOT"
        )
        assert isinstance(result, ToolResult)
        assert len(result.content) == 2

    def test_screenshot_with_multiple_commands(self, mock_context, tmp_path):
        """Test that multiple commands passed as a single string are forwarded to input_strings."""
        screenshot_path = tmp_path / "screenshot.png"
        screenshot_path.write_bytes(b"fake image data")

        mock_context.request_context.lifespan_context.mapdl.screenshot.return_value = str(
            screenshot_path
        )

        commands = "EPLOT\nPLNSOL,U,SUM"
        result = screenshot(mock_context, commands=commands)

        mock_context.request_context.lifespan_context.mapdl.input_strings.assert_called_once_with(
            commands
        )
        assert isinstance(result, ToolResult)
        assert len(result.content) == 2

    def test_screenshot_without_commands_does_not_call_input_string(self, mock_context, tmp_path):
        """Test that input_strings is NOT called when commands is empty."""
        screenshot_path = tmp_path / "screenshot.png"
        screenshot_path.write_bytes(b"fake image data")

        mock_context.request_context.lifespan_context.mapdl.screenshot.return_value = str(
            screenshot_path
        )

        screenshot(mock_context)

        mock_context.request_context.lifespan_context.mapdl.input_strings.assert_not_called()

    def test_screenshot_commands_error_is_caught(self, mock_context):
        """Test that an error raised by input_strings is caught and returned as an error message."""
        mock_context.request_context.lifespan_context.mapdl.input_strings.side_effect = Exception(
            "command failed"
        )

        result = screenshot(mock_context, commands="BADCMD")

        assert isinstance(result, ToolResult)
        assert len(result.content) == 1
        assert isinstance(result.content[0], TextContent)
        assert "Failed to capture screenshot" in result.content[0].text
        assert "command failed" in result.content[0].text

    @patch("ansys.mapdl.mcp.tools._open_image_in_viewer")
    def test_screenshot_show_plot_on_popup_calls_viewer(
        self, mock_open_viewer, mock_context, tmp_path
    ):
        """Test that show_plot_on_popup=True opens the image in the system viewer."""
        screenshot_path = tmp_path / "screenshot.png"
        screenshot_path.write_bytes(b"fake image data")

        mock_context.request_context.lifespan_context.mapdl.screenshot.return_value = str(
            screenshot_path
        )

        result = screenshot(mock_context, show_plot_on_popup=True)

        assert isinstance(result, ToolResult)
        assert len(result.content) == 2
        mock_open_viewer.assert_called_once_with(str(screenshot_path))

    @patch("ansys.mapdl.mcp.tools._open_image_in_viewer")
    def test_screenshot_no_popup_by_default(self, mock_open_viewer, mock_context, tmp_path):
        """Test that show_plot_on_popup defaults to False and no viewer is opened."""
        screenshot_path = tmp_path / "screenshot.png"
        screenshot_path.write_bytes(b"fake image data")

        mock_context.request_context.lifespan_context.mapdl.screenshot.return_value = str(
            screenshot_path
        )

        result = screenshot(mock_context)

        assert isinstance(result, ToolResult)
        mock_open_viewer.assert_not_called()

    """Tests for MAPDL-connection-aware tool visibility."""

    @pytest.mark.asyncio
    async def test_connect_to_mapdl_enables_requires_mapdl_tools(self, mock_context_no_mapdl):
        """Successful connect_to_mapdl should call ctx.enable_components for requires_mapdl tag."""
        mock_mapdl = MagicMock()
        mock_mapdl.version = "2024 R2"
        mock_mapdl._ip = "localhost"
        mock_mapdl._port = 50052

        with patch("ansys.mapdl.core.Mapdl", return_value=mock_mapdl):
            await connect_to_mapdl(mock_context_no_mapdl)
            mock_context_no_mapdl.enable_components.assert_called_once_with(tags={"requires_mapdl"})

    @pytest.mark.asyncio
    async def test_connect_to_mapdl_does_not_enable_on_failure(self, mock_context_no_mapdl):
        """Failed connect_to_mapdl should not call ctx.enable_components."""
        with patch("ansys.mapdl.core.Mapdl", side_effect=Exception("Connection refused")):
            await connect_to_mapdl(mock_context_no_mapdl)
            mock_context_no_mapdl.enable_components.assert_not_called()

    @pytest.mark.asyncio
    async def test_launch_mapdl_session_enables_requires_mapdl_tools(self, mock_context_no_mapdl):
        """Successful launch_mapdl_session should call ctx.enable_components for requires_mapdl."""
        mock_mapdl = MagicMock()
        mock_mapdl.version = "2024 R2"
        mock_mapdl.ip = "127.0.0.1"
        mock_mapdl.port = 50052
        mock_mapdl.directory = "/tmp"

        with patch("ansys.mapdl.core.launch_mapdl", return_value=mock_mapdl):
            await launch_mapdl_session(ctx=mock_context_no_mapdl)
            mock_context_no_mapdl.enable_components.assert_called_once_with(tags={"requires_mapdl"})

    @pytest.mark.asyncio
    async def test_launch_mapdl_session_does_not_enable_on_failure(self, mock_context_no_mapdl):
        """Failed launch_mapdl_session should not call ctx.enable_components."""
        with patch("ansys.mapdl.core.launch_mapdl", side_effect=Exception("Launch failed")):
            await launch_mapdl_session(ctx=mock_context_no_mapdl)
            mock_context_no_mapdl.enable_components.assert_not_called()

    @pytest.mark.asyncio
    async def test_disconnect_from_mapdl_disables_requires_mapdl_tools(self, mock_context):
        """Successful disconnect_from_mapdl should call ctx.disable_components."""
        mock_context.request_context.lifespan_context.mapdl._ip = "localhost"
        mock_context.request_context.lifespan_context.mapdl._port = 50052

        await disconnect_from_mapdl(mock_context)
        mock_context.disable_components.assert_called_once_with(tags={"requires_mapdl"})

    @pytest.mark.asyncio
    async def test_disconnect_from_mapdl_no_connection_does_not_disable(
        self, mock_context_no_mapdl
    ):
        """disconnect_from_mapdl with no connection should not change visibility."""
        await disconnect_from_mapdl(mock_context_no_mapdl)
        mock_context_no_mapdl.disable_components.assert_not_called()

    def test_requires_mapdl_tag_present_on_correct_tools(self):
        """Tools that need MAPDL should have the requires_mapdl tag."""
        import asyncio

        from ansys.mapdl.mcp import app as mapdl_app

        # Use the local provider's unfiltered list to avoid visibility-state interference
        async def _check():
            return {t.name: t for t in await mapdl_app._local_provider._list_tools()}

        tool_registry = asyncio.run(_check())

        expected_tagged = {
            "check_mapdl_status",
            "run_mapdl_command",
            "run_multiple_mapdl_commands",
            "disconnect_from_mapdl",
            "screenshot",
            "run_python_code",
            "custom_plot",
        }
        for tool_name in expected_tagged:
            assert tool_name in tool_registry, f"Tool '{tool_name}' not found in registry"
            assert "requires_mapdl" in (tool_registry[tool_name].tags or set()), (
                f"Tool '{tool_name}' missing 'requires_mapdl' tag"
            )

    def test_pre_mapdl_tools_do_not_have_requires_mapdl_tag(self):
        """Tools available before MAPDL connects must not have the requires_mapdl tag."""
        import asyncio

        from ansys.mapdl.mcp import app as mapdl_app

        # Use the local provider's unfiltered list to avoid visibility-state interference
        async def _check():
            return {t.name: t for t in await mapdl_app._local_provider._list_tools()}

        tool_registry = asyncio.run(_check())

        always_available = {
            "check_mapdl_installed",
            "connect_to_mapdl",
            "launch_mapdl_session",
            "list_mapdl_instances",
        }
        for tool_name in always_available:
            assert tool_name in tool_registry, f"Tool '{tool_name}' not found in registry"
            assert "requires_mapdl" not in (tool_registry[tool_name].tags or set()), (
                f"Tool '{tool_name}' should not have 'requires_mapdl' tag"
            )
