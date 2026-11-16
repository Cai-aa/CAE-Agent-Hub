"""Test the read-only part-mesh query without requiring Abaqus in CI."""
import asyncio
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import mcp_server
from part_mesh import mesh_query


class PartMeshTests(unittest.TestCase):
    def evaluate(self, part, *, name="Panel", limit=1, quality=True):
        model = SimpleNamespace(parts={name: part})
        modules = {
            "abaqus": SimpleNamespace(mdb=SimpleNamespace(models={"Demo": model})),
            "abaqusConstants": SimpleNamespace(SIZE="SIZE", ANALYSIS_CHECKS="ANALYSIS_CHECKS"),
        }
        env = {}
        with patch.dict(sys.modules, modules):
            exec(mesh_query("Demo", name, quality, limit), env)
        return env["result"]

    def test_reports_counts_and_bounded_labels(self):
        elements = [SimpleNamespace(type="CPS4R", label=i) for i in range(1, 4)]
        part = SimpleNamespace(elements=elements, nodes=range(8), cells=(), faces=(0,), edges=(),
                               getPartSeeds=lambda **kw: .25,
                               verifyMeshQuality=lambda **kw: {"numElements": 3, "failedElements": elements[:2]})
        result = self.evaluate(part)
        self.assertEqual(result["element_types"], {"CPS4R": 3})
        self.assertEqual(result["node_count"], 8)
        self.assertEqual(result["global_seed_size"], .25)
        self.assertEqual(result["analysis_checks"]["failed_count"], 2)
        self.assertEqual(result["analysis_checks"]["failed_labels"], [1])

    def test_empty_part_does_not_claim_quality_passed(self):
        part = SimpleNamespace(elements=(), nodes=(), cells=(), faces=(), edges=(), vertices=())
        result = self.evaluate(part)
        self.assertIsNone(result["global_seed_size"])
        self.assertEqual(result["element_count"], 0)
        self.assertEqual(result["analysis_checks"]["status"], "unmeshed")

    def test_name_is_data_and_not_python_code(self):
        part = SimpleNamespace(elements=(), nodes=(), cells=(), faces=(), edges=(), vertices=())
        result = self.evaluate(part, name='x"\nraise RuntimeError("test")\n#')
        self.assertIn("raise", result["part"])

    def test_mcp_wrapper_routes_a_single_bridge_query(self):
        with patch.object(mcp_server, "run_python", return_value={"return_value": {"node_count": 5}}) as call:
            result = asyncio.run(mcp_server.inspect_part_mesh("Demo", "Panel", timeout=2))
        self.assertEqual(result, {"node_count": 5})
        self.assertEqual(call.await_args.args[1], 2)
