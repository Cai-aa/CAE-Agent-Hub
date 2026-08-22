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

"""Basic tests for PyMechanical MCP Server package."""

import pytest

import ansys.mechanical.mcp


@pytest.mark.unit
def test_version():
    """Test that version is defined and is a string."""
    assert hasattr(ansys.mechanical.mcp, "__version__")
    assert isinstance(ansys.mechanical.mcp.__version__, str)
    assert len(ansys.mechanical.mcp.__version__) > 0


@pytest.mark.unit
def test_package_imports():
    """Test that all expected functions and classes can be imported."""
    from ansys.mechanical.mcp import (
        app,
    )

    assert app is not None


@pytest.mark.unit
def test_all_exports():
    """Test that __all__ contains all expected exports."""
    from ansys.mechanical.mcp import __all__

    expected_exports = [
        "app",
        "launcher",
        "__version__",
    ]

    assert set(__all__) == set(expected_exports)


@pytest.mark.unit
def test_app_context_creation(app_context):
    """Test that PyMechanicalAppContext can be created with Mechanical instance."""
    assert app_context.mechanical is not None
    assert hasattr(app_context.mechanical, "version")


@pytest.mark.unit
def test_app_context_no_mechanical(app_context_no_mechanical):
    """Test that PyMechanicalAppContext can be created without Mechanical instance."""
    assert app_context_no_mechanical.mechanical is None
