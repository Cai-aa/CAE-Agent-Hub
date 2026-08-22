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

"""Tests for PyExample MCP tools.

These tests validate the MCP tool implementations and their interaction
with the PyExample instance and context.
"""

import asyncio
import json
from unittest.mock import MagicMock

from pyexample_mcp import PyExampleContext, app
from pyexample_mcp.mock_pyexample import PyExample
from pyexample_mcp.tools import (
    create_model,
    execute_command,
    execute_python_code,
    get_command_history,
    list_tool_sets,
    run_simulation,
)
import pytest


@pytest.fixture
def app_context():
    """Fixture providing a mock context with PyExample instance."""
    context = PyExampleContext(
        python_session=MagicMock(),
        command_history=[],
    )
    context.example_instance = PyExample()
    return context


@pytest.fixture
def mock_fastmcp_context(app_context):
    """Fixture providing a mock FastMCP context."""
    context = MagicMock()
    context.request_context = MagicMock()
    context.fastmcp._lifespan_result = app_context
    return context


class TestExecuteCommandTool:
    """Tests for the execute_command tool."""

    def test_execute_command_success(self, mock_fastmcp_context):
        """Test successful command execution."""
        result = execute_command(ctx=mock_fastmcp_context, command="CREATE MODEL test")

        assert "created successfully" in result
        assert "test" in result

    def test_execute_command_updates_history(self, mock_fastmcp_context):
        """Test that commands are added to history."""
        execute_command(ctx=mock_fastmcp_context, command="CREATE MODEL test1")
        execute_command(ctx=mock_fastmcp_context, command="CREATE MODEL test2")

        context = mock_fastmcp_context.fastmcp._lifespan_result
        assert len(context.command_history) == 2
        assert "CREATE MODEL test1" in context.command_history
        assert "CREATE MODEL test2" in context.command_history

    def test_execute_command_no_connection(self, mock_fastmcp_context):
        """Test execute_command when PyExample not connected."""
        context = mock_fastmcp_context.fastmcp._lifespan_result
        context.example_instance = None

        result = execute_command(ctx=mock_fastmcp_context, command="STATUS")

        assert "Error: PyExample not connected" in result


class TestCreateModelTool:
    """Tests for the create_model tool."""

    def test_create_model_basic(self, mock_fastmcp_context):
        """Test basic model creation."""
        result = create_model(ctx=mock_fastmcp_context, name="my_model")

        assert "my_model" in result
        assert "created successfully" in result

    def test_create_model_with_type(self, mock_fastmcp_context):
        """Test model creation with specific type."""
        result = create_model(ctx=mock_fastmcp_context, name="thermal_model", model_type="thermal")

        assert "thermal_model" in result
        assert "created successfully" in result

    def test_create_model_updates_active_model(self, mock_fastmcp_context):
        """Test that creating a model updates the active model."""
        create_model(ctx=mock_fastmcp_context, name="active_model")

        context = mock_fastmcp_context.fastmcp._lifespan_result
        assert context.example_instance.active_model == "active_model"

    def test_create_model_updates_history(self, mock_fastmcp_context):
        """Test that create_model updates command history."""
        create_model(ctx=mock_fastmcp_context, name="test")

        context = mock_fastmcp_context.fastmcp._lifespan_result
        assert len(context.command_history) > 0

    def test_create_model_no_connection(self, mock_fastmcp_context):
        """Test create_model when PyExample not connected."""
        context = mock_fastmcp_context.fastmcp._lifespan_result
        context.example_instance = None

        result = create_model(ctx=mock_fastmcp_context, name="test")

        assert "Error: PyExample not connected" in result

    def test_create_model_with_parameters(self, mock_fastmcp_context):
        """Test model creation with additional parameters."""
        result = create_model(
            ctx=mock_fastmcp_context,
            name="param_model",
            model_type="structural",
            parameters={"mesh_size": 0.1, "material": "steel"},
        )

        assert "param_model" in result
        assert "created successfully" in result
        assert "CREATE MODEL" in mock_fastmcp_context.fastmcp._lifespan_result.command_history[-1]


class TestRunSimulationTool:
    """Tests for the run_simulation tool."""

    def test_run_simulation_explicit_model(self, mock_fastmcp_context):
        """Test running simulation on explicit model."""
        create_model(ctx=mock_fastmcp_context, name="test_model")
        result = run_simulation(ctx=mock_fastmcp_context, model_name="test_model")

        assert "Simulation completed" in result
        assert "test_model" in result

    def test_run_simulation_active_model(self, mock_fastmcp_context):
        """Test running simulation on active model."""
        create_model(ctx=mock_fastmcp_context, name="active_model")
        result = run_simulation(ctx=mock_fastmcp_context)

        assert "Simulation completed" in result
        assert "active_model" in result

    def test_run_simulation_saves_results(self, mock_fastmcp_context):
        """Test that simulation results are saved in context."""
        create_model(ctx=mock_fastmcp_context, name="model_with_results")
        run_simulation(ctx=mock_fastmcp_context, model_name="model_with_results", save_results=True)

        context = mock_fastmcp_context.fastmcp._lifespan_result
        assert "model_with_results" in context.simulation_results
        assert context.simulation_results["model_with_results"]["status"] == "completed"

    def test_run_simulation_no_save_results(self, mock_fastmcp_context):
        """Test simulation without saving results."""
        create_model(ctx=mock_fastmcp_context, name="temp_model")
        run_simulation(ctx=mock_fastmcp_context, model_name="temp_model", save_results=False)

        context = mock_fastmcp_context.fastmcp._lifespan_result
        assert "temp_model" not in context.simulation_results

    def test_run_simulation_no_model(self, mock_fastmcp_context):
        """Test simulation with no model specified or active."""
        result = run_simulation(ctx=mock_fastmcp_context)

        assert "Error: No model specified or active" in result

    def test_run_simulation_updates_history(self, mock_fastmcp_context):
        """Test that run_simulation updates command history."""
        create_model(ctx=mock_fastmcp_context, name="sim_model")
        run_simulation(ctx=mock_fastmcp_context, model_name="sim_model")

        context = mock_fastmcp_context.fastmcp._lifespan_result
        # Should have at least 2 commands (create + solve)
        assert len(context.command_history) >= 2

    def test_run_simulation_no_connection(self, mock_fastmcp_context):
        """Test run_simulation when PyExample not connected."""
        context = mock_fastmcp_context.fastmcp._lifespan_result
        context.example_instance = None

        result = run_simulation(ctx=mock_fastmcp_context, model_name="test")

        assert "Error: PyExample not connected" in result


class TestGetCommandHistoryTool:
    """Tests for the get_command_history tool."""

    def test_get_history_list_format(self, mock_fastmcp_context):
        """Test getting history in list format."""
        context = mock_fastmcp_context.fastmcp._lifespan_result
        context.command_history = ["CMD1", "CMD2", "CMD3"]

        result = get_command_history(ctx=mock_fastmcp_context, format="list")

        assert "CMD1" in result
        assert "CMD2" in result
        assert "CMD3" in result

    def test_get_history_numbered_format(self, mock_fastmcp_context):
        """Test getting history in numbered format."""
        context = mock_fastmcp_context.fastmcp._lifespan_result
        context.command_history = ["CMD1", "CMD2"]

        result = get_command_history(ctx=mock_fastmcp_context, format="numbered")

        assert "1. CMD1" in result
        assert "2. CMD2" in result

    def test_get_history_json_format(self, mock_fastmcp_context):
        """Test getting history in JSON format."""
        context = mock_fastmcp_context.fastmcp._lifespan_result
        context.command_history = ["CMD1", "CMD2"]

        result = get_command_history(ctx=mock_fastmcp_context, format="json")

        # Should be valid JSON
        parsed = json.loads(result)
        assert parsed == ["CMD1", "CMD2"]

    def test_get_history_empty(self, mock_fastmcp_context):
        """Test getting history when no commands executed."""
        result = get_command_history(ctx=mock_fastmcp_context)

        assert "No commands executed" in result


class TestExecutePythonCodeTool:
    """Tests for the execute_python_code tool."""

    def test_execute_python_code_success(self, mock_fastmcp_context):
        """Test successful Python code execution."""
        context = mock_fastmcp_context.fastmcp._lifespan_result
        context.python_session.execute = MagicMock(
            return_value={
                "success": True,
                "stdout": "42\n",
                "stderr": "",
            }
        )

        result = execute_python_code(ctx=mock_fastmcp_context, code="print(42)")

        assert "42" in result

    def test_execute_python_code_with_warnings(self, mock_fastmcp_context):
        """Test Python code execution with warnings."""
        context = mock_fastmcp_context.fastmcp._lifespan_result
        context.python_session.execute = MagicMock(
            return_value={
                "success": True,
                "stdout": "Result\n",
                "stderr": "Warning: deprecated\n",
            }
        )

        result = execute_python_code(ctx=mock_fastmcp_context, code="some_code()")

        assert "Result" in result
        assert "Warning" in result
        assert "deprecated" in result

    def test_execute_python_code_error(self, mock_fastmcp_context):
        """Test Python code execution with error."""
        context = mock_fastmcp_context.fastmcp._lifespan_result
        context.python_session.execute = MagicMock(
            return_value={
                "success": False,
                "error": "NameError: name 'undefined' is not defined",
            }
        )

        result = execute_python_code(ctx=mock_fastmcp_context, code="undefined()")

        assert "Error:" in result
        assert "NameError" in result


class TestToolsIntegration:
    """Integration tests for multiple tools working together."""

    def test_complete_workflow(self, mock_fastmcp_context):
        """Test complete workflow using multiple tools."""
        context = mock_fastmcp_context.fastmcp._lifespan_result
        context.python_session.execute = MagicMock(
            return_value={
                "success": True,
                "stdout": "Analysis complete\n",
                "stderr": "",
            }
        )

        # Create models
        create_model(ctx=mock_fastmcp_context, name="model1", model_type="structural")
        create_model(ctx=mock_fastmcp_context, name="model2", model_type="thermal")

        # Run simulations
        run_simulation(ctx=mock_fastmcp_context, model_name="model1")
        run_simulation(ctx=mock_fastmcp_context, model_name="model2")

        # Check history
        history = get_command_history(ctx=mock_fastmcp_context, format="numbered")
        assert "CREATE MODEL" in history
        assert "SOLVE MODEL" in history

        # Execute Python code
        code_result = execute_python_code(
            ctx=mock_fastmcp_context, code="print('Analysis complete')"
        )
        assert "Analysis complete" in code_result

        # Verify context state
        assert len(context.simulation_results) == 2
        assert "model1" in context.simulation_results
        assert "model2" in context.simulation_results


class TestToolSets:
    """Tests for the tool sets resource and tool tag assignments."""

    def test_list_tool_sets_returns_list(self):
        """Test that list_tool_sets returns a list."""
        result = list_tool_sets()

        assert isinstance(result, list)

    def test_list_tool_sets_contains_expected_names(self):
        """Test that all expected tool set names are present."""
        result = list_tool_sets()
        names = [item["name"] for item in result]

        assert "structures" in names
        assert "post_processing" in names

    def test_list_tool_sets_items_have_required_keys(self):
        """Test that each tool set item has name, description, skill, and tools keys."""
        result = list_tool_sets()

        for item in result:
            assert "name" in item, f"Item {item} is missing 'name'"
            assert "description" in item, f"Item {item} is missing 'description'"
            assert "skill" in item, f"Item {item} is missing 'skill'"
            assert "tools" in item, f"Item {item} is missing 'tools'"

    def test_list_tool_sets_string_fields_are_non_empty(self):
        """Test that name, description, and skill fields are non-empty strings."""
        result = list_tool_sets()

        for item in result:
            for field in ("name", "description", "skill"):
                assert isinstance(item[field], str), (
                    f"'{field}' in '{item['name']}' must be a string"
                )
                assert item[field], f"'{field}' in '{item['name']}' must not be empty"

    def test_list_tool_sets_tools_field_is_list_of_strings(self):
        """Test that the tools field is a non-empty list of strings."""
        result = list_tool_sets()

        for item in result:
            assert isinstance(item["tools"], list), f"'tools' in '{item['name']}' must be a list"
            assert item["tools"], f"'tools' in '{item['name']}' must not be empty"
            for tool_name in item["tools"]:
                assert isinstance(tool_name, str), f"Tool names in '{item['name']}' must be strings"

    def test_structures_tools_have_correct_tag(self):
        """Test that structural tools are tagged with 'structures'."""
        tools = {t.name: t for t in asyncio.run(app.list_tools())}

        assert "structures" in tools["create_model"].tags
        assert "structures" in tools["run_simulation"].tags

    def test_post_processing_tools_have_correct_tag(self):
        """Test that post-processing tools are tagged with 'post_processing'."""
        tools = {t.name: t for t in asyncio.run(app.list_tools())}

        assert "post_processing" in tools["get_command_history"].tags
        assert "post_processing" in tools["execute_python_code"].tags

    def test_untagged_tools_have_no_tags(self):
        """Test that tools without a tag assignment have an empty tag set."""
        tools = {t.name: t for t in asyncio.run(app.list_tools())}

        assert tools["execute_command"].tags == set()

    def test_toolset_resource_is_registered(self):
        """Test that the toolsets://definition resource is registered on the app."""
        resources = asyncio.run(app.list_resources())
        uris = [str(r.uri) for r in resources]

        assert "toolsets://definition" in uris

    def test_toolset_names_match_used_tags(self):
        """Test that every tag used by a tool has an entry in list_tool_sets."""
        tool_sets = list_tool_sets()
        tool_set_names = {item["name"] for item in tool_sets}
        tools = asyncio.run(app.list_tools())
        all_tags = {tag for t in tools for tag in t.tags}

        for tag in all_tags:
            assert tag in tool_set_names, f"Tag '{tag}' is used but not described in list_tool_sets"
