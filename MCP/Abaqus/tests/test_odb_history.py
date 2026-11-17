"""Exercise the ODB history tool with test doubles for the Abaqus kernel."""
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import mcp_server


class OdbHistoryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.odb_path = str(Path.cwd() / "case '曲线'.odb")
        self.history = SimpleNamespace(data=((0.0, 0.0), (0.2, -4.5), (0.6, 11.0), (1.0, 12.0)))
        self.region_name = "Node ANCHOR.'左'"
        self.step = SimpleNamespace(
            domain="TIME",
            frames=[],
            historyRegions={
                self.region_name: SimpleNamespace(historyOutputs={"RF2": self.history}),
                "Node OTHER.1": SimpleNamespace(historyOutputs={"U2": SimpleNamespace(data=())}),
            },
        )
        self.odb = SimpleNamespace(steps={"Compression": self.step}, close=Mock())
        self.open_odb = Mock(return_value=self.odb)

    async def run_kernel(self, code, timeout):
        with patch.dict(sys.modules, {"odbAccess": SimpleNamespace(openOdb=self.open_odb)}):
            namespace = {}
            try:
                exec(code, namespace)
            except (KeyError, ValueError) as exc:
                # The real run_python reports kernel failures as RuntimeError.
                raise RuntimeError(str(exc)) from exc
            return {"return_value": namespace["result"]}

    async def call(self, *, error=None, **overrides):
        tool = getattr(mcp_server, "read_odb_history", None)
        self.assertIsNotNone(tool, "read_odb_history is missing")
        params = dict(odb_path=self.odb_path, step_name="Compression", region_name=self.region_name, variable="RF2")
        params.update(overrides)
        with patch.object(mcp_server, "run_python", side_effect=self.run_kernel) as bridge:
            result = (await tool(**params)).model_dump(by_alias=True)
        bridge.assert_awaited_once()
        if error is not None:
            self.assertTrue(result["isError"])
            self.assertRegex(result["content"][0]["text"], error)
        else:
            self.assertFalse(result["isError"], result["content"])
            return result["structuredContent"]

    async def test_inspect_lists_history_regions_without_field_frames(self):
        with patch.object(mcp_server, "run_python", side_effect=self.run_kernel):
            result = await mcp_server.inspect_odb(self.odb_path)
        self.assertEqual(result["steps"][0]["frame_count"], 0)
        self.assertIn(self.region_name, result["steps"][0]["historyRegions"])

    async def test_exact_samples_and_continuation(self):
        page = await self.call(limit=2)
        self.open_odb.assert_called_once_with(path=self.odb_path, readOnly=True)
        self.odb.close.assert_called_once_with()
        self.assertEqual(page["domain"], "TIME")
        self.assertEqual(page["variable"], "RF2")
        self.assertEqual(page["total_points"], 4)
        self.assertEqual(page["points"], [[0.0, 0.0], [0.2, -4.5]])
        self.assertEqual(page["next_offset"], 2)

        final = await self.call(offset=page["next_offset"], limit=2)
        self.assertEqual(final["points"], [[0.6, 11.0], [1.0, 12.0]])
        self.assertIsNone(final["next_offset"])

    async def test_missing_variable_lists_names_and_closes_odb(self):
        await self.call(variable="unknown", error=r"History variable.*RF2")
        self.odb.close.assert_called_once_with()

    async def test_missing_step_and_region_list_names(self):
        await self.call(step_name="Other", error=r"Step.*Compression")
        await self.call(region_name="Other", error=r"History region.*OTHER")

    async def test_empty_history_and_end_of_series(self):
        empty = await self.call(region_name="Node OTHER.1", variable="U2")
        self.assertEqual(empty["points"], [])
        self.assertEqual(empty["total_points"], 0)
        self.assertIsNone(empty["next_offset"])

        end = await self.call(offset=4)
        self.assertEqual(end["points"], [])
        self.assertIsNone(end["next_offset"])
        await self.call(offset=5, error="offset")

    async def test_invalid_request_before_bridge(self):
        tool = mcp_server.read_odb_history
        with patch.object(mcp_server, "run_python") as bridge:
            for offset, limit in [(-1, 1), (0, 0), (0, 10001)]:
                with self.subTest(offset=offset, limit=limit):
                    reply = await tool(self.odb_path, "Compression", self.region_name, "RF2",
                                       offset=offset, limit=limit)
                    self.assertTrue(reply.model_dump(by_alias=True)["isError"])
            bridge.assert_not_called()

    async def test_non_time_domain_preserves_native_axis(self):
        self.step.domain = "FREQUENCY"
        data = await self.call()
        self.assertEqual(data["domain"], "FREQUENCY")
        self.assertEqual(data["points"][1], [0.2, -4.5])

    async def test_complex_history_reports_unsupported_data(self):
        self.history.conjugateData = ((0.0, 0.1),)
        await self.call(error="Complex history")

    async def test_non_finite_data_reports_sample(self):
        self.history.data = ((0.0, float("nan")),)
        await self.call(error="Non-finite.*0")

    async def test_relative_path_is_rejected_at_kernel(self):
        await self.call(odb_path="relative.odb", error="absolute")
        self.open_odb.assert_not_called()


if __name__ == "__main__":
    unittest.main()
