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

"""Tests for file-management MCP tools and resources."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from fastmcp.tools.base import ToolResult
import pytest

from ansys.mapdl.mcp.tools import (
    download_file,
    mapdl_db_path,
    mapdl_rst_path,
    mapdl_working_directory,
    open_results,
    resume_model,
    upload_file,
)

# ---------------------------------------------------------------------------
# upload_file
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUploadFile:
    """Tests for the upload_file tool."""

    def test_upload_success(self, mock_context, tmp_path):
        """Happy path: local file exists and upload succeeds."""
        local_file = tmp_path / "model.db"
        local_file.write_bytes(b"dummy content")

        mock_context.request_context.lifespan_context.mapdl.upload.return_value = "model.db"

        result = upload_file(mock_context, str(local_file))

        assert isinstance(result, ToolResult)
        assert "uploaded successfully" in result.content[0].text
        assert "model.db" in result.content[0].text
        mock_context.request_context.lifespan_context.mapdl.upload.assert_called_once_with(
            str(local_file), progress_bar=False
        )

    def test_upload_file_not_found(self, mock_context):
        """Error returned when the local file does not exist."""
        result = upload_file(mock_context, "/nonexistent/path/model.db")

        assert isinstance(result, ToolResult)
        assert "not found" in result.content[0].text.lower()

    def test_upload_no_mapdl(self, mock_context_no_mapdl, tmp_path):
        """Error returned when MAPDL is not connected."""
        local_file = tmp_path / "model.db"
        local_file.write_bytes(b"dummy content")

        result = upload_file(mock_context_no_mapdl, str(local_file))

        assert isinstance(result, ToolResult)
        assert "No MAPDL connection available" in result.content[0].text

    def test_upload_no_context(self, mock_context, tmp_path):
        """Error returned when request context is absent."""
        mock_context.request_context = None
        local_file = tmp_path / "model.db"
        local_file.write_bytes(b"dummy content")

        result = upload_file(mock_context, str(local_file))

        assert "No request context available" in result.content[0].text

    def test_upload_mapdl_raises(self, mock_context, tmp_path):
        """Error message returned when mapdl.upload raises an exception."""
        local_file = tmp_path / "model.db"
        local_file.write_bytes(b"dummy content")
        mock_context.request_context.lifespan_context.mapdl.upload.side_effect = IOError(
            "Transfer failed"
        )

        result = upload_file(mock_context, str(local_file))

        assert "Failed to upload" in result.content[0].text
        assert "Transfer failed" in result.content[0].text


# ---------------------------------------------------------------------------
# download_file
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDownloadFile:
    """Tests for the download_file tool."""

    def test_download_success(self, mock_context, tmp_path):
        """Happy path: download returns a list of files."""
        mock_context.request_context.lifespan_context.mapdl.download.return_value = [
            str(tmp_path / "file.rst")
        ]

        result = download_file(mock_context, "file.rst", str(tmp_path))

        assert isinstance(result, ToolResult)
        assert "Successfully downloaded 1 file" in result.content[0].text
        mock_context.request_context.lifespan_context.mapdl.download.assert_called_once_with(
            "file.rst", target_dir=str(tmp_path), progress_bar=False
        )

    def test_download_multiple_files(self, mock_context, tmp_path):
        """Happy path: glob pattern returns multiple files."""
        mock_context.request_context.lifespan_context.mapdl.download.return_value = [
            str(tmp_path / "file.rst"),
            str(tmp_path / "file.db"),
        ]

        result = download_file(mock_context, "file*")

        assert "2 file" in result.content[0].text

    def test_download_no_match(self, mock_context):
        """Empty list from MAPDL returns a 'no files matched' message."""
        mock_context.request_context.lifespan_context.mapdl.download.return_value = []

        result = download_file(mock_context, "missing.rst")

        assert "No files matched" in result.content[0].text

    def test_download_default_target_dir(self, mock_context):
        """When target_dir is None, it is passed through unchanged."""
        mock_context.request_context.lifespan_context.mapdl.download.return_value = ["file.rst"]

        download_file(mock_context, "file.rst")

        mock_context.request_context.lifespan_context.mapdl.download.assert_called_once_with(
            "file.rst", target_dir=None, progress_bar=False
        )

    def test_download_no_mapdl(self, mock_context_no_mapdl):
        """Error returned when MAPDL is not connected."""
        result = download_file(mock_context_no_mapdl, "file.rst")

        assert "No MAPDL connection available" in result.content[0].text

    def test_download_mapdl_raises(self, mock_context):
        """Error message returned when mapdl.download raises an exception."""
        mock_context.request_context.lifespan_context.mapdl.download.side_effect = Exception(
            "gRPC error"
        )

        result = download_file(mock_context, "file.rst")

        assert "Failed to download" in result.content[0].text
        assert "gRPC error" in result.content[0].text


# ---------------------------------------------------------------------------
# resume_model
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestResumeModel:
    """Tests for the resume_model tool."""

    def test_resume_db(self, mock_context):
        """Happy path: resume from a .db file using RESUME command."""
        mock_context.request_context.lifespan_context.mapdl.resume.return_value = ""

        result = resume_model(mock_context, "beam", "db")

        assert isinstance(result, ToolResult)
        assert "resumed successfully" in result.content[0].text.lower()
        mock_context.request_context.lifespan_context.mapdl.resume.assert_called_once_with(
            "beam", "db"
        )

    def test_resume_cdb(self, mock_context):
        """Happy path: resume from a .cdb file using CDREAD command."""
        mock_context.request_context.lifespan_context.mapdl.cdread.return_value = ""

        result = resume_model(mock_context, "model", "cdb")

        assert isinstance(result, ToolResult)
        assert "resumed successfully" in result.content[0].text.lower()
        mock_context.request_context.lifespan_context.mapdl.cdread.assert_called_once_with(
            "db", "model", "cdb"
        )

    def test_resume_db_with_output(self, mock_context):
        """MAPDL command output is returned verbatim when non-empty."""
        mock_context.request_context.lifespan_context.mapdl.resume.return_value = (
            "RESUME from beam.db"
        )

        result = resume_model(mock_context, "beam", "db")

        assert "RESUME from beam.db" in result.content[0].text

    def test_resume_db_default_extension(self, mock_context):
        """Default extension is 'db'."""
        mock_context.request_context.lifespan_context.mapdl.resume.return_value = ""

        resume_model(mock_context, "beam")

        mock_context.request_context.lifespan_context.mapdl.resume.assert_called_once_with(
            "beam", "db"
        )

    def test_resume_invalid_extension(self, mock_context):
        """Unsupported extension returns an error without calling MAPDL."""
        result = resume_model(mock_context, "beam", "rst")

        assert "Unsupported extension" in result.content[0].text
        mock_context.request_context.lifespan_context.mapdl.resume.assert_not_called()

    def test_resume_no_mapdl(self, mock_context_no_mapdl):
        """Error returned when MAPDL is not connected."""
        result = resume_model(mock_context_no_mapdl, "beam")

        assert "No MAPDL connection available" in result.content[0].text

    def test_resume_mapdl_raises(self, mock_context):
        """Error message returned when mapdl.resume raises an exception."""
        mock_context.request_context.lifespan_context.mapdl.resume.side_effect = RuntimeError(
            "File not in working directory"
        )

        result = resume_model(mock_context, "beam", "db")

        assert "Failed to resume" in result.content[0].text
        assert "File not in working directory" in result.content[0].text

    def test_resume_extension_with_dot_prefix(self, mock_context):
        """Extension provided with a leading dot is accepted."""
        mock_context.request_context.lifespan_context.mapdl.resume.return_value = ""

        result = resume_model(mock_context, "beam", ".db")

        assert "resumed successfully" in result.content[0].text.lower()


# ---------------------------------------------------------------------------
# open_results
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestOpenResults:
    """Tests for the open_results tool."""

    def test_open_results_no_file(self, mock_context):
        """Entering POST1 without specifying a file uses the current jobname."""
        result = open_results(mock_context)

        assert isinstance(result, ToolResult)
        assert "POST1" in result.content[0].text
        mock_context.request_context.lifespan_context.mapdl.post1.assert_called_once()
        mock_context.request_context.lifespan_context.mapdl.file.assert_not_called()

    def test_open_results_with_file(self, mock_context):
        """Specifying a file name calls mapdl.file with that name and 'rst'."""
        result = open_results(mock_context, "beam")

        assert isinstance(result, ToolResult)
        assert "POST1" in result.content[0].text
        assert "beam.rst" in result.content[0].text
        mock_context.request_context.lifespan_context.mapdl.post1.assert_called_once()
        mock_context.request_context.lifespan_context.mapdl.file.assert_called_once_with(
            "beam", "rst"
        )

    def test_open_results_no_mapdl(self, mock_context_no_mapdl):
        """Error returned when MAPDL is not connected."""
        result = open_results(mock_context_no_mapdl)

        assert "No MAPDL connection available" in result.content[0].text

    def test_open_results_post1_raises(self, mock_context):
        """Error message returned when mapdl.post1 raises an exception."""
        mock_context.request_context.lifespan_context.mapdl.post1.side_effect = RuntimeError(
            "Cannot enter POST1"
        )

        result = open_results(mock_context)

        assert "Failed to open results" in result.content[0].text
        assert "Cannot enter POST1" in result.content[0].text

    def test_open_results_file_raises(self, mock_context):
        """Error message returned when mapdl.file raises an exception."""
        mock_context.request_context.lifespan_context.mapdl.file.side_effect = RuntimeError(
            "RST file not found"
        )

        result = open_results(mock_context, "missing")

        assert "Failed to open results" in result.content[0].text
        assert "RST file not found" in result.content[0].text


# ---------------------------------------------------------------------------
# MCP resources
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFileResources:
    """Tests for the file-path MCP resources."""

    def _patch_app_context(self, mapdl):
        """Return a context manager that patches app.context with a mock holding mapdl."""
        from ansys.mapdl.mcp import server as _server_mod

        ctx = MagicMock()
        ctx.mapdl = mapdl
        return patch.object(_server_mod.app, "context", ctx, create=True)

    def test_working_directory_connected(self):
        """Returns the MAPDL directory when connected."""
        mock_mapdl = MagicMock()
        mock_mapdl.directory = "/ansys_work/job1"

        with self._patch_app_context(mock_mapdl):
            result = mapdl_working_directory()

        assert result == "/ansys_work/job1"

    def test_working_directory_not_connected(self):
        """Returns a 'not connected' message when MAPDL is absent."""
        with self._patch_app_context(None):
            result = mapdl_working_directory()

        assert "not connected" in result.lower()

    def test_rst_path_connected(self):
        """Returns <directory>/<jobname>.rst when connected."""
        mock_mapdl = MagicMock()
        mock_mapdl.directory = "/ansys_work/job1"
        mock_mapdl.jobname = "file"

        with self._patch_app_context(mock_mapdl):
            result = mapdl_rst_path()

        assert result == str(Path("/ansys_work/job1") / "file.rst")

    def test_rst_path_not_connected(self):
        """Returns a 'not connected' message when MAPDL is absent."""
        with self._patch_app_context(None):
            result = mapdl_rst_path()

        assert "not connected" in result.lower()

    def test_db_path_connected(self):
        """Returns <directory>/<jobname>.db when connected."""
        mock_mapdl = MagicMock()
        mock_mapdl.directory = "/ansys_work/job1"
        mock_mapdl.jobname = "file"

        with self._patch_app_context(mock_mapdl):
            result = mapdl_db_path()

        assert result == str(Path("/ansys_work/job1") / "file.db")

    def test_db_path_not_connected(self):
        """Returns a 'not connected' message when MAPDL is absent."""
        with self._patch_app_context(None):
            result = mapdl_db_path()

        assert "not connected" in result.lower()

    def test_rst_path_mapdl_raises(self):
        """Returns an error string when accessing mapdl attributes raises."""
        mock_mapdl = MagicMock()
        mock_mapdl.directory = "/some/dir"
        type(mock_mapdl).jobname = property(
            fget=lambda self: (_ for _ in ()).throw(RuntimeError("Connection lost"))
        )

        with self._patch_app_context(mock_mapdl):
            result = mapdl_rst_path()

        assert "Could not retrieve" in result

    def test_db_path_mapdl_raises(self):
        """Returns an error string when accessing mapdl attributes raises."""
        mock_mapdl = MagicMock()
        mock_mapdl.directory = "/some/dir"
        type(mock_mapdl).jobname = property(
            fget=lambda self: (_ for _ in ()).throw(RuntimeError("Connection lost"))
        )

        with self._patch_app_context(mock_mapdl):
            result = mapdl_db_path()

        assert "Could not retrieve" in result
