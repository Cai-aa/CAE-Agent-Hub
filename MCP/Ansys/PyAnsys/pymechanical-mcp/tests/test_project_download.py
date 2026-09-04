# Copyright (C) 2026 Synopsys, Inc. and ANSYS, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for project download tool behavior."""

import json
from unittest.mock import ANY

from ansys.mechanical.mcp.tools import download_project


def test_download_project_success(mock_context):
    mechanical = mock_context.request_context.lifespan_context.mechanical
    mechanical.download_project.return_value = ["C:/output/project.mechdb"]

    result = json.loads(
        download_project(mock_context, extensions=["mechdb"], target_dir="C:/output")
    )

    assert result == {
        "success": True,
        "downloaded_files": ["C:/output/project.mechdb"],
        "file_count": 1,
    }
    mechanical.download_project.assert_called_once_with(
        extensions=["mechdb"], target_dir="C:/output", progress_bar=False
    )


def test_download_project_requires_connection(mock_context_no_mechanical):
    result = json.loads(download_project(mock_context_no_mechanical))

    assert result["error_code"] == "not_connected"


def test_download_project_defaults_target_dir_to_cwd(mock_context):
    """Mechanical.download_project() raises AttributeError when target_dir is None.

    Regression test: the tool must resolve a concrete local directory before
    calling the underlying PyMechanical API instead of forwarding ``None``.
    """
    mechanical = mock_context.request_context.lifespan_context.mechanical
    mechanical.download_project.return_value = ["C:/cwd/project.mechdb"]

    result = json.loads(download_project(mock_context))

    assert result["success"] is True
    mechanical.download_project.assert_called_once_with(
        extensions=[], target_dir=ANY, progress_bar=False
    )
    called_target_dir = mechanical.download_project.call_args.kwargs["target_dir"]
    assert called_target_dir is not None


def test_download_project_rejects_empty_extension(mock_context):
    result = json.loads(download_project(mock_context, extensions=["mechdb", " "]))

    assert result["error_code"] == "invalid_arguments"


def test_download_project_returns_upstream_error(mock_context):
    mechanical = mock_context.request_context.lifespan_context.mechanical
    mechanical.download_project.side_effect = RuntimeError("transfer failed")

    result = json.loads(download_project(mock_context))

    assert result["error_code"] == "upstream_error"
    assert "transfer failed" in result["error"]
