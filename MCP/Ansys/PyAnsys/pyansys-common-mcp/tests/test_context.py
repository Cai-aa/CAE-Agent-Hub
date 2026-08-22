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

"""Tests for context module."""

from ansys.common.mcp.context import PyAnsysBaseAppContext
from ansys.common.mcp.helpers import PersistentPythonSession


class TestPyAnsysBaseAppContext:
    """Tests for PyAnsysBaseAppContext dataclass."""

    def test_context_initialization_defaults(self):
        """Test context initialization with default values."""
        context = PyAnsysBaseAppContext()

        assert context.product_instance is None
        assert context.python_executable is None
        assert context.python_session is None
        assert context.metadata == {}
        assert context.command_history == []

    def test_context_initialization_with_values(self):
        """Test context initialization with provided values."""
        session = PersistentPythonSession()
        metadata = {"key": "value"}
        history = ["cmd1", "cmd2"]

        context = PyAnsysBaseAppContext(
            product_instance="test_product",
            python_executable="/usr/bin/python",
            python_session=session,
            metadata=metadata,
            command_history=history,
        )

        assert context.product_instance == "test_product"
        assert context.python_executable == "/usr/bin/python"
        assert context.python_session is session
        assert context.metadata == metadata
        assert context.command_history == history

    def test_context_as_state_container(self):
        """Test using context to track session state."""
        context = PyAnsysBaseAppContext()

        # Add state
        context.metadata["session_id"] = "session_123"
        context.command_history.append("import numpy")
        context.command_history.append("x = 10")

        # Retrieve state
        assert context.metadata["session_id"] == "session_123"
        assert len(context.command_history) == 2
        assert context.command_history[0] == "import numpy"


class TestContextExtension:
    """Tests for extending PyAnsysBaseAppContext."""

    def test_context_subclass_creation(self):
        """Test creating a custom context subclass for product-specific use."""
        from dataclasses import dataclass
        from typing import Any, Optional

        @dataclass
        class CustomContext(PyAnsysBaseAppContext):
            custom_field: Optional[Any] = None
            custom_config: dict = None

            def __post_init__(self):
                if self.custom_config is None:
                    self.custom_config = {}

        context = CustomContext(custom_field="test_value")

        assert context.custom_field == "test_value"
        assert context.custom_config == {}
        assert context.product_instance is None  # Inherited from base
