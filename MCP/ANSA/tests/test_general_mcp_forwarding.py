import asyncio

from fastmcp import Client

import ansa_mcp.server as server


def test_general_operation_uses_persistent_write_and_exact_preconditions(monkeypatch):
    calls = []
    class Live:
        def call_persistent_write(self, method, params, *, operation_id):
            calls.append((method, params, operation_id))
            return {"forwarded": True}
    monkeypatch.setattr(server, "live", Live())
    args = {"operation": "set_deck", "parameters": {"deck_name": "NASTRAN"},
            "expected_database": "", "expected_session_nonce": "a" * 32,
            "expected_deck": 1, "operation_id": "forward-operation-001", "confirm": True}
    async def run():
        async with Client(server.mcp) as client:
            result = await client.call_tool("execute_live_ansa_operation", args)
            assert not result.is_error
    asyncio.run(run())
    assert calls == [("execute_operation", args, args["operation_id"])]
