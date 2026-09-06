import unittest

from mcp.types import ImageContent

import mcp_server


class FakeWorker:
    def __init__(self):
        self.calls = []
        self.releases = []

    async def execute_async(self, target, command, arguments, timeout=None):
        self.calls.append((target, command, arguments, timeout))
        if command == "screenshot":
            return {
                "target": {"kind": target.kind, "value": target.value},
                "path": "C:/view.jpg",
                "mime_type": "image/jpeg",
                "data_base64": "ZmFrZQ==",
            }
        return {
            "target": {"kind": target.kind, "value": target.value},
            "command": command,
            **arguments,
        }

    async def release_async(self, target, timeout=None):
        self.releases.append((target, timeout))
        return {"released": True}


class FakeDiscovery:
    def __init__(self, sessions=None):
        self.sessions = sessions or []

    def list_sessions(self):
        return list(self.sessions)


class OfficialMcpToolTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.original_worker = mcp_server.worker_client
        self.original_discovery = mcp_server.session_discovery
        self.original_installation = mcp_server.check_aedt_installation
        self.worker = FakeWorker()
        mcp_server.worker_client = self.worker
        mcp_server.session_discovery = FakeDiscovery(
            [{"pid": 101, "version": "2026.1", "listening_ports": [50051]}]
        )
        mcp_server.check_aedt_installation = lambda: {
            "installed": True,
            "version": "2026.1",
            "pyaedt_version": "1.5.0",
        }

    def tearDown(self):
        mcp_server.worker_client = self.original_worker
        mcp_server.session_discovery = self.original_discovery
        mcp_server.check_aedt_installation = self.original_installation

    async def test_installation_and_discovery_checks_do_not_attach(self):
        installed = await mcp_server.check_aedt_installed()
        status = await mcp_server.check_aedt_status()

        self.assertTrue(installed["installed"])
        self.assertEqual(status["session_count"], 1)
        self.assertEqual(self.worker.calls, [])

    async def test_all_official_tool_names_are_registered(self):
        expected = {
            "analyze_design",
            "check_aedt_installed",
            "check_aedt_status",
            "clear_aedt",
            "connect_to_aedt",
            "create_design",
            "disconnect_from_aedt",
            "export_config",
            "export_results",
            "get_guidelines_for",
            "get_model_info",
            "get_pyaedt_logs",
            "launch_aedt",
            "list_designs",
            "list_projects",
            "open_project",
            "run_python_code",
            "run_python_script",
            "save_project",
            "screenshot",
            "validate_design",
        }
        registered = {tool.name for tool in await mcp_server.mcp.list_tools()}

        self.assertTrue(expected.issubset(registered))
        self.assertEqual(len(registered), 30)

    async def test_targeted_status_and_connect_use_explicit_target(self):
        status = await mcp_server.check_aedt_status(pid=101)
        connected = await mcp_server.connect_to_aedt(
            port=50051,
            project_name="Cooling",
            design_name="BoardThermal",
        )

        self.assertEqual(status["command"], "ping")
        self.assertEqual(connected["command"], "connect_to_aedt")
        self.assertEqual(self.worker.calls[0][0].key, "pid:101")
        self.assertEqual(self.worker.calls[1][0].key, "port:50051")

    async def test_connect_rejects_remote_machine_before_worker(self):
        with self.assertRaisesRegex(ValueError, "local sessions"):
            await mcp_server.connect_to_aedt(
                port=50051,
                machine="remote-host",
            )
        self.assertEqual(self.worker.calls, [])

    async def test_create_icepak_validate_and_analyze_forward_official_arguments(self):
        created = await mcp_server.create_design(
            app_type="Icepak",
            project_name="Cooling",
            design_name="BoardThermal",
            port=50051,
        )
        validated = await mcp_server.validate_design(
            project_name="Cooling",
            design_name="BoardThermal",
            port=50051,
        )
        analyzed = await mcp_server.analyze_design(
            project_name="Cooling",
            design_name="BoardThermal",
            setup_name="Setup1",
            num_cores=8,
            port=50051,
        )

        self.assertEqual(created["app_type"], "Icepak")
        self.assertEqual(validated["command"], "validate_design")
        self.assertEqual(analyzed["num_cores"], 8)
        self.assertTrue(analyzed["icepak_safe_mode"])
        self.assertEqual(
            [call[1] for call in self.worker.calls],
            ["create_design", "validate_design", "analyze_design"],
        )

    async def test_project_script_export_and_model_tools_are_forwarded(self):
        await mcp_server.list_projects(pid=101)
        await mcp_server.list_designs(project_name="Cooling", pid=101)
        await mcp_server.run_python_code(code="result = 1", pid=101)
        await mcp_server.run_python_script(script_path="C:/demo.py", pid=101)
        await mcp_server.export_config(output="C:/config.json", pid=101)
        await mcp_server.export_results(
            output_path="C:/mesh.txt", export_type="mesh", pid=101
        )
        await mcp_server.get_model_info(pid=101)
        await mcp_server.get_pyaedt_logs(pid=101)
        await mcp_server.clear_aedt(close_projects=False, pid=101)

        self.assertEqual(
            [call[1] for call in self.worker.calls],
            [
                "list_projects",
                "list_designs",
                "run_python_code",
                "run_python_script",
                "export_config",
                "export_results",
                "get_model_info",
                "get_pyaedt_logs",
                "clear_aedt",
            ],
        )

    async def test_screenshot_returns_native_mcp_image_content(self):
        result = await mcp_server.screenshot(pid=101, open_viewer=False)

        self.assertEqual(len(result), 2)
        self.assertIsInstance(result[1], ImageContent)
        self.assertEqual(result[1].data, "ZmFrZQ==")

    async def test_disconnect_requires_choice_then_stops_broker(self):
        choice = await mcp_server.disconnect_from_aedt(pid=101)
        disconnected = await mcp_server.disconnect_from_aedt(
            pid=101,
            close_desktop=False,
        )

        self.assertTrue(choice["choice_required"])
        self.assertEqual(disconnected["command"], "disconnect_from_aedt")
        self.assertEqual(len(self.worker.releases), 1)
        self.assertEqual(self.worker.releases[0][0].key, "pid:101")

    def test_icepak_guidelines_include_thermal_acceptance_checks(self):
        guidance = mcp_server.get_guidelines_for("icepak")

        self.assertIn("mass-flow conservation", guidance)
        self.assertIn("heat balance", guidance)
        self.assertIn("Solver completion", guidance)


if __name__ == "__main__":
    unittest.main()
