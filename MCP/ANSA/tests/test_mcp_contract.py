from __future__ import annotations

import asyncio

import pytest


fastmcp = pytest.importorskip("fastmcp")

from fastmcp import Client

import ansa_mcp.server as server_module
from ansa_mcp.server import mcp


EXPECTED_TOOLS = {
    "get_environment",
    "get_live_bridge_status",
    "get_live_capabilities",
    "get_live_session_info",
    "get_live_model_summary",
    "list_live_entities",
    "get_live_entity",
    "run_live_model_checks",
    "save_live_database",
    "create_live_entity",
    "set_live_entity_card_values",
    "refresh_live_view",
    "get_live_step_history",
    "execute_live_ansa_python_step",
    "search_live_ansa_api",
    "get_live_ansa_api_help",
    "get_live_entity_fields",
    "execute_live_ansa_operation",
}


class _RecordingLive:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict, str | None]] = []

    def call(self, method, params=None, **kwargs):
        del kwargs
        payload = params or {}
        self.calls.append(("call", method, payload, None))
        return {"method": method, "params": payload}

    def call_persistent_write(
        self, method, params, *, operation_id, timeout=None
    ):
        del timeout
        self.calls.append(("persistent", method, params, operation_id))
        return {
            "method": method,
            "params": params,
            "operation_id": operation_id,
        }


def _error_text(result) -> str:
    return "\n".join(
        item.text for item in result.content if hasattr(item, "text")
    )


def _property_names(tool) -> set[str]:
    schema = getattr(tool, "inputSchema", None) or getattr(tool, "input_schema", None)
    assert isinstance(schema, dict)
    return set(schema.get("properties", {}))


def test_tools_resource_and_write_schemas_are_discoverable() -> None:
    async def inspect_contract():
        async with Client(mcp) as client:
            tools = await client.list_tools()
            resources = await client.list_resources()
            return tools, resources

    tools, resources = asyncio.run(inspect_contract())
    by_name = {tool.name: tool for tool in tools}

    assert EXPECTED_TOOLS == set(by_name)
    assert "ansa://environment" in {str(item.uri) for item in resources}
    assert {
        "relative_path",
        "expected_database",
        "expected_session_nonce",
        "operation_id",
        "confirm",
        "overwrite",
    } <= _property_names(by_name["save_live_database"])
    assert {
        "entity_type",
        "fields",
        "expected_database",
        "expected_session_nonce",
        "operation_id",
        "confirm",
    } <= _property_names(by_name["create_live_entity"])
    assert {
        "entity_type",
        "entity_id",
        "values",
        "expected_values",
        "expected_database",
        "expected_session_nonce",
        "operation_id",
        "confirm",
    } <= _property_names(by_name["set_live_entity_card_values"])
    assert {
        "operation", "parameters", "expected_database", "expected_session_nonce",
        "expected_deck", "operation_id", "confirm",
    } <= _property_names(by_name["execute_live_ansa_operation"])
    assert {
        "step_name", "code", "expected_database", "expected_session_nonce",
        "expected_deck", "operation_id", "confirm",
    } <= _property_names(by_name["execute_live_ansa_python_step"])


def test_fastmcp_uses_strict_input_validation() -> None:
    assert mcp.strict_input_validation is True


def test_fastmcp_rejects_coercible_scalar_inputs_before_tool_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_live = _RecordingLive()
    monkeypatch.setattr(server_module, "live", fake_live)

    save_args = {
        "relative_path": "strict-contract.ansa",
        "expected_database": "database.ansa",
        "expected_session_nonce": "0" * 32,
        "operation_id": "save-strict-contract",
        "confirm": True,
        "overwrite": False,
    }
    invalid_calls = [
        ("save_live_database", {**save_args, "confirm": 1}),
        ("save_live_database", {**save_args, "confirm": "true"}),
        ("save_live_database", {**save_args, "overwrite": 1}),
        ("save_live_database", {**save_args, "overwrite": "false"}),
        ("get_live_model_summary", {"visible_only": 1}),
        ("get_live_model_summary", {"visible_only": "true"}),
        ("get_live_entity", {"entity_type": "NODE", "entity_id": True}),
        ("get_live_entity", {"entity_type": "NODE", "entity_id": "1"}),
        (
            "list_live_entities",
            {"entity_type": "NODE", "limit": True, "offset": 0},
        ),
        (
            "list_live_entities",
            {"entity_type": "NODE", "limit": "100", "offset": 0},
        ),
        (
            "list_live_entities",
            {"entity_type": "NODE", "limit": 100, "offset": False},
        ),
        (
            "list_live_entities",
            {"entity_type": "NODE", "limit": 100, "offset": "0"},
        ),
        ("run_live_model_checks", {"max_issues": True}),
        ("run_live_model_checks", {"max_issues": "200"}),
    ]

    async def invoke_invalid_calls():
        async with Client(mcp) as client:
            return [
                await client.call_tool(
                    tool_name,
                    arguments,
                    raise_on_error=False,
                )
                for tool_name, arguments in invalid_calls
            ]

    results = asyncio.run(invoke_invalid_calls())

    assert len(results) == len(invalid_calls)
    assert all(result.is_error for result in results)
    assert all("Input validation error" in _error_text(result) for result in results)
    assert fake_live.calls == []


def test_fastmcp_accepts_exact_boolean_and_integer_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_live = _RecordingLive()
    monkeypatch.setattr(server_module, "live", fake_live)

    async def invoke_valid_calls():
        async with Client(mcp) as client:
            return [
                await client.call_tool(
                    "save_live_database",
                    {
                        "relative_path": "strict-contract.ansa",
                        "expected_database": "database.ansa",
                        "expected_session_nonce": "0" * 32,
                        "operation_id": "save-strict-contract",
                        "confirm": True,
                        "overwrite": False,
                    },
                ),
                await client.call_tool(
                    "get_live_model_summary",
                    {"visible_only": True},
                ),
                await client.call_tool(
                    "get_live_entity",
                    {"entity_type": "NODE", "entity_id": 7},
                ),
                await client.call_tool(
                    "list_live_entities",
                    {
                        "entity_type": "NODE",
                        "limit": 5,
                        "offset": 0,
                        "visible_only": False,
                    },
                ),
                await client.call_tool(
                    "run_live_model_checks",
                    {"max_issues": 8},
                ),
            ]

    results = asyncio.run(invoke_valid_calls())

    assert all(not result.is_error for result in results)
    assert len(fake_live.calls) == 5
    _, _, save_params, _ = fake_live.calls[0]
    _, _, summary_params, _ = fake_live.calls[1]
    _, _, entity_params, _ = fake_live.calls[2]
    _, _, list_params, _ = fake_live.calls[3]
    _, _, check_params, _ = fake_live.calls[4]
    assert type(save_params["confirm"]) is bool
    assert type(save_params["overwrite"]) is bool
    assert type(summary_params["visible_only"]) is bool
    assert type(entity_params["entity_id"]) is int
    assert type(list_params["limit"]) is int
    assert type(list_params["offset"]) is int
    assert type(list_params["visible_only"]) is bool
    assert type(check_params["max_issues"]) is int


def test_persistent_write_tools_use_outcome_aware_bridge_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Live:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict, str]] = []

        def call(self, method, params=None, **kwargs):
            raise AssertionError("persistent writes must not use the read call path")

        def call_persistent_write(
            self, method, params, *, operation_id, timeout=None
        ):
            self.calls.append((method, params, operation_id))
            return {"confirmed": True, "operation_id": operation_id}

    fake_live = _Live()
    monkeypatch.setattr(server_module, "live", fake_live)

    save_result = server_module.save_live_database.fn(
        relative_path="contract-test.ansa",
        expected_database="database.ansa",
        expected_session_nonce="session-1",
        operation_id="save-contract-001",
        confirm=True,
        overwrite=False,
    )
    create_result = server_module.create_live_entity.fn(
        entity_type="NODE",
        fields={"X1": 0.0},
        expected_database="database.ansa",
        expected_session_nonce="session-1",
        operation_id="create-contract-001",
        confirm=True,
    )
    update_result = server_module.set_live_entity_card_values.fn(
        entity_type="NODE",
        entity_id=1,
        values={"X1": 1.0},
        expected_values={"X1": 0.0},
        expected_database="database.ansa",
        expected_session_nonce="session-1",
        operation_id="update-contract-001",
        confirm=True,
    )
    python_result = server_module.execute_live_ansa_python_step.fn(
        step_name="Inspect model",
        code="result = 1",
        expected_database="database.ansa",
        expected_session_nonce="session-1",
        expected_deck=7,
        operation_id="python-contract-001",
        confirm=True,
    )

    assert save_result == {
        "confirmed": True,
        "operation_id": "save-contract-001",
    }
    assert create_result == {
        "confirmed": True,
        "operation_id": "create-contract-001",
    }
    assert update_result == {
        "confirmed": True,
        "operation_id": "update-contract-001",
    }
    assert python_result == {
        "confirmed": True,
        "operation_id": "python-contract-001",
    }
    assert [(method, operation_id) for method, _, operation_id in fake_live.calls] == [
        ("save_database", "save-contract-001"),
        ("create_entity", "create-contract-001"),
        ("set_entity_card_values", "update-contract-001"),
        ("execute_python_step", "python-contract-001"),
    ]
    assert all(
        params["operation_id"] == operation_id
        for _, params, operation_id in fake_live.calls
    )
