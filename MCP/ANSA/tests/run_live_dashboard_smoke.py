"""Explicit opt-in: native package install + authenticated isolated GUI smoke."""
import argparse
import asyncio
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))
from ansa_mcp.bridge_client import LiveBridgeClient, BridgeError


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--bpkg", type=Path, required=True)
    parser.add_argument("--ansa-launcher", type=Path, required=True)
    parser.add_argument("--accepted-license-profile", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    profile = root / "profile"
    profile.mkdir()
    # Copy only previously accepted local license state, never accept a new EULA.
    accepted = args.accepted_license_profile / ".BETA/ANSA/.ANSA_license"
    if not accepted.is_file():
        raise RuntimeError("Previously accepted ANSA license state not found; no EULA will be accepted automatically")
    license_target = profile / ".BETA/ANSA/.ANSA_license"
    license_target.parent.mkdir(parents=True)
    shutil.copy2(accepted, license_target)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    entry = root / "bridge_entry"
    entry.mkdir()
    shutil.copy2(PROJECT / "ansa_plugin/ansa_mcp_plugin.py", entry)
    config_path = root / "bridge.json"
    config_path.write_text(json.dumps({"version": 1, "host": "127.0.0.1", "port": port,
        "token": secrets.token_hex(32), "plugin_root": str(entry), "allowed_roots": [str(root)],
        "request_timeout_seconds": 30}), encoding="utf-8")
    (entry / "bridge_config_path.txt").write_text(str(config_path), encoding="utf-8")
    env = dict(os.environ, ANSA_MCP_DASHBOARD_TEST_ROOT=str(root),
               ANSA_MCP_BRIDGE_CONFIG=str(config_path),
               ANSA_MCP_TEST_PACKAGER_API=str(args.ansa_launcher.parent / "config/plugins/PackagerInstaller/docs/no_gui_execution.py"),
               ANSA_MCP_TEST_BPKG=str(args.bpkg.resolve()))
    command = [str(args.ansa_launcher), "-uh", str(profile), "-exec", "load_script:" + str(PROJECT / "tests/live_dashboard_host.py")]
    with (root / "install.log").open("wb") as log:
        install = subprocess.run(command[:1] + ["-nogui"] + command[1:], cwd=root,
            env=dict(env, ANSA_MCP_DASHBOARD_TEST_MODE="install"), stdout=log, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW, timeout=90)
    assert install.returncode == 0, "Native installation failed; inspect install.log"
    assert json.loads((root / "install_report.json").read_text())["ok"]
    with (root / "gui.log").open("wb") as log:
        process = subprocess.Popen(command[:1] + ["--batch-mode"] + command[1:], cwd=root,
            env=dict(env, ANSA_MCP_DASHBOARD_TEST_MODE="gui"), stdout=log, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            deadline = time.monotonic() + 65
            while not (root / "ready.json").is_file():
                if process.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError("Isolated GUI failed to become ready; inspect gui.log")
                time.sleep(0.2)
            client = LiveBridgeClient(config_path)
            info = client.call("get_session_info")
            client.call("get_model_summary")
            expected = {"expected_database": info["database"], "expected_session_nonce": info["session_nonce"],
                        "expected_deck": info["deck"], "confirm": True}
            # Empty disposable process only: a single node proves real count change.
            assert not info["database"]
            created = client.call("execute_python_step", dict(expected,
                step_name="Dashboard validation - create one node", operation_id="dashboard-smoke-create-001",
                code="entity = base.CreateEntity(deck, 'GRID', {'X1': 0., 'X2': 0., 'X3': 0.})\nassert entity is not None\nresult = {'created_id': entity._id}"))
            assert created["execution_returned"]
            client.call("get_model_summary")
            capabilities = client.call("get_capabilities")
            assert capabilities["bridge_version"] == "0.5.0"
            assert not any("cantilever" in m for m in capabilities["methods"])
            assert "CurvesNew" in client.call("search_api", {"module": "base", "query": "CurvesNew"})["names"]
            assert client.call("get_api_help", {"module": "base", "name": "CurvesNew"})["doc"]
            assert client.call("get_entity_fields", {"entity_type": "GRID", "entity_id": created["python_result"]["created_id"]})["fields"]
            operation_results = []
            def operation(name, parameters):
                current = client.call("get_session_info")
                payload = dict(operation=name, parameters=parameters,
                    expected_database=current["database"], expected_session_nonce=current["session_nonce"],
                    expected_deck=current["deck"], confirm=True, operation_id="general-smoke-%03d" % len(operation_results))
                value = client.call("execute_operation", payload)
                assert client.call("execute_operation", payload)["idempotent_replay"]
                operation_results.append(value)
                return value
            curve = operation("create_curve", {"points": [[0., 0., 0.], [10., 0., 0.], [20., 5., 0.]]})
            curve_id = curve["created_entity"]["id"]
            operation("isolate_entities", {"entity_type": "CURVE", "entity_ids": [curve_id]})
            operation("hide_entities", {"entity_type": "CURVE", "entity_ids": [curve_id]})
            operation("delete_entities", {"entity_type": "CURVE", "entity_ids": [curve_id]})
            operation("set_deck", {"deck_name": "ABAQUS"})
            operation("set_deck", {"deck_name": "NASTRAN"})
            # Real FastMCP tool protocol -> persistent authenticated bridge ->
            # bundled plugin in the isolated GUI; no fake native calls here.
            os.environ['ANSA_MCP_BRIDGE_CONFIG'] = str(config_path)
            os.environ['ANSA_MCP_WORKSPACE'] = str(root)
            import ansa_mcp.server as server
            from fastmcp import Client
            async def check_mcp():
                async with Client(server.mcp) as mcp_client:
                    assert len(await mcp_client.list_tools()) == 18
                    caps = await mcp_client.call_tool('get_live_capabilities', {})
                    assert len(caps.data['general_operations']['operations']) == 24
                    current = await mcp_client.call_tool('get_live_session_info', {})
                    value = current.data
                    payload = dict(operation='create_isotropic_material', parameters=dict(name='MCP_PROTOCOL_TEST',
                        young_modulus=210000., poisson_ratio=.3, density=7.85e-9, unit_system='mm-N-tonne'),
                        expected_database=value['database'], expected_session_nonce=value['session_nonce'],
                        expected_deck=value['deck'], confirm=True, operation_id='mcp-native-material-001')
                    created_material = await mcp_client.call_tool('execute_live_ansa_operation', payload)
                    assert created_material.data['model_effect_verified']
                    replay = await mcp_client.call_tool('execute_live_ansa_operation', payload)
                    assert replay.data['idempotent_replay']
                    (root / 'mcp_engineering_report.json').write_text(json.dumps(created_material.data, indent=2), encoding='utf-8')
            asyncio.run(check_mcp())
            snapshot = root / "snapshot.ansa"
            client.call("save_database", {"path": str(snapshot), "expected_database": "",
                "expected_session_nonce": info["session_nonce"], "operation_id": "general-smoke-save",
                "confirm": True, "overwrite": False})
            operation("open_model", {"path": str(snapshot), "replace_current": True})
            (root / "general_operations_report.json").write_text(json.dumps(operation_results, indent=2), encoding="utf-8")
            current = client.call("get_session_info")
            expected.update(expected_database=current["database"], expected_deck=current["deck"])
            try:
                client.call("execute_python_step", dict(expected,
                    step_name="Dashboard validation - expected error", operation_id="dashboard-smoke-error-001",
                    code="raise RuntimeError('Intentional dashboard error; no model change')"))
            except BridgeError:
                pass
            else:
                raise AssertionError("Expected error was not propagated")
        finally:
            (root / "finish").touch()
            process.wait(timeout=45)
    report = json.loads((root / "gui_report.json").read_text(encoding="utf-8"))
    assert process.returncode == 0 and report["ok"], report.get("error")
    events = report["monitor"]["events"]
    created_event = next(e for e in events if e["parameters"].get("operation_id") == "dashboard-smoke-create-001")
    assert created_event["model_change"]["counts"]["GRID"]["delta"] == 1
    assert events[-1]["status"] == "outcome_unknown"
    assert report["gui_mode"] and "0.5.0" in report["context_label"]
    assert report["checkbox_callback_verified"] and report["selection_callback_verified"]
    assert [e["source"] for e in report["monitor"]["diagnostics"]] == ["execute_python_step"]
    print(json.dumps({"ok": True, "root": str(root), "pid": report["pid"], "events": len(events),
                      "real_node_delta": 1, "native_install_and_start": True}, indent=2))


if __name__ == "__main__":
    main()
