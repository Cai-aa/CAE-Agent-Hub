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

"""Basic tests for PyMAPDL MCP Server package."""

import pytest

import ansys.mapdl.mcp


@pytest.mark.unit
def test_version():
    """Test that version is defined and is a string."""
    assert hasattr(ansys.mapdl.mcp, "__version__")
    assert isinstance(ansys.mapdl.mcp.__version__, str)
    assert len(ansys.mapdl.mcp.__version__) > 0


@pytest.mark.unit
def test_package_imports():
    """Test that all expected functions and classes can be imported."""
    from ansys.mapdl.mcp import (
        app,
    )

    assert app is not None


@pytest.mark.unit
def test_all_exports():
    """Test that __all__ contains all expected exports."""
    from ansys.mapdl.mcp import __all__

    expected_exports = [
        "app",
        "launcher",
        "__version__",
    ]

    assert set(__all__) == set(expected_exports)


@pytest.mark.unit
def test_app_context_creation(app_context):
    """Test that PyMAPDLAppContext can be created with MAPDL instance."""
    assert app_context.mapdl is not None
    assert hasattr(app_context.mapdl, "version")


@pytest.mark.unit
def test_app_context_no_mapdl(app_context_no_mapdl):
    """Test that PyMAPDLAppContext can be created without MAPDL instance."""
    assert app_context_no_mapdl.mapdl is None
