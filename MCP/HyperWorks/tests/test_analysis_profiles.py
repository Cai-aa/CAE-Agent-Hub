from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hyperworks_mcp.analysis_profiles import (
    AnalysisProfileService,
    build_optistruct_buckling_deck,
    build_optistruct_cantilever_deck,
    build_optistruct_modal_deck,
    build_optistruct_multicase_static_deck,
    build_optistruct_thermal_stress_deck,
    build_radioss_block_impact_decks,
)
from hyperworks_mcp.projects import ProjectService
from hyperworks_mcp.settings import Settings


class AnalysisProfileTests(unittest.TestCase):
    def test_builds_complete_radioss_explicit_chain(self) -> None:
        starter, engine, metadata = build_radioss_block_impact_decks(
            "Impact regression",
            [5.0, 6.0, 6.0],
            [2, 2, 2],
            [2.0, 10.0, 10.0],
            [1, 2, 2],
            1.0,
            5.0,
            1.0,
            0.1,
            210.0,
            0.3,
            7.85e-6,
            0.25,
            0.5,
            0.5,
        )
        for token in (
            "#RADIOSS STARTER",
            "/MAT/PLAS_JOHNS/1",
            "/PROP/SOLID/1",
            "/BRICK/1",
            "/BCS/1",
            "/INIVEL/TRA/2",
            "/INTER/TYPE7/1",
            "/TH/PART/1",
            "/TH/INTER/2",
        ):
            self.assertIn(token, starter)
        for token in ("/RUN/", "/H3D/DT", "/H3D/SOLID/VONM", "/STOP"):
            self.assertIn(token, engine)
        self.assertEqual(metadata["solid_element_count"], 12)
        self.assertEqual(metadata["constraint_chain"]["node_count"], 9)
        self.assertEqual(metadata["quality_gates"]["maximum_absolute_energy_error_percent"], 15.0)

    def test_builds_complete_optistruct_chain_with_gap(self) -> None:
        deck, metadata = build_optistruct_cantilever_deck(
            "Cantilever baseline",
            [100.0, 20.0, 10.0],
            [4, 2, 1],
            210000.0,
            0.3,
            7.85e-9,
            -1000.0,
            [0.0, 0.0, 1.0],
            [
                {
                    "grid_index": [4, 1, 1],
                    "ground_position": [100.0, 10.0, 12.0],
                    "stiffness": 1.0e6,
                    "initial_gap": 2.0,
                }
            ],
        )
        for token in ("MAT1,", "PSOLID,", "CHEXA,", "SPC1,", "FORCE,", "PGAP,", "CGAP,", "SUBCASE 1"):
            self.assertIn(token, deck)
        self.assertEqual(metadata["solid_element_count"], 8)
        self.assertEqual(metadata["gap_element_count"], 1)
        self.assertEqual(metadata["control_chain"]["solution"], "SOL 101")

    def test_builds_modal_buckling_multicase_and_thermal_profiles(self) -> None:
        common = ([100.0, 10.0, 10.0], [5, 1, 1], 210000.0, 0.3, 7.85e-9)
        modal, modal_meta = build_optistruct_modal_deck("Modal", *common, 8)
        self.assertIn("SOL 103", modal)
        self.assertIn("ANALYSIS = MODES", modal)
        self.assertIn("EIGRL,42,,,8", modal)
        self.assertNotIn("EIGVEC(H3D)", modal)
        self.assertNotIn("FORCE,", modal)
        self.assertEqual(modal_meta["analysis_type"], "normal_modes")
        self.assertNotIn("total_force", modal_meta)

        buckling, buckling_meta = build_optistruct_buckling_deck(
            "Buckling", *common, -1000.0, [-1, 0, 0], 4
        )
        self.assertIn("SOL 105", buckling)
        self.assertIn("STATSUB(BUCKLING) = 1", buckling)
        self.assertIn("ANALYSIS = BUCK", buckling)
        self.assertNotIn("EIGVEC(H3D)", buckling)
        self.assertEqual(buckling_meta["control_chain"]["number_of_modes"], 4)

        multicase, multicase_meta = build_optistruct_multicase_static_deck(
            "Multicase", *common,
            [
                {"name": "Vertical", "total_force": -1000, "force_direction": [0, 0, 1]},
                {"name": "Lateral", "total_force": 500, "force_direction": [0, 1, 0]},
            ],
        )
        self.assertIn("SUBCASE 2", multicase)
        self.assertIn("LOAD = 102", multicase)
        self.assertEqual(multicase_meta["control_chain"]["subcase_count"], 2)

        thermal, thermal_meta = build_optistruct_thermal_stress_deck(
            "Thermal", *common, 1.2e-5, 20.0, 120.0
        )
        self.assertIn("TEMP(LOAD) = 2", thermal)
        self.assertIn("TEMP,2,", thermal)
        self.assertIn("OLOAD(H3D) = ALL", thermal)
        self.assertNotIn("TEMPERATURE(H3D)", thermal)
        self.assertIn("MAT1,1,210000", thermal)
        self.assertEqual(thermal_meta["analysis_type"], "linear_thermal_stress")
        self.assertNotIn("total_force", thermal_meta)

    def test_prepares_project_scoped_deck_and_validates_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings(Path(tmp) / "workspace", None, 4, 32)
            settings.ensure()
            projects = ProjectService(settings)
            project = projects.create("analysis")
            service = AnalysisProfileService(projects)
            result = service.prepare_optistruct_cantilever(
                project["project_id"],
                "Cantilever",
                [10, 2, 1],
                [2, 1, 1],
                70000,
                0.33,
                2.7e-9,
                100,
                [0, 0, -1],
            )
            self.assertTrue(Path(result["deck_file"]).is_file())
            with self.assertRaisesRegex(ValueError, "division"):
                service.prepare_optistruct_cantilever(
                    project["project_id"], "bad", [1, 1, 1], [0, 1, 1],
                    1, 0.3, 1, 1, [1, 0, 0], output_name="bad.fem"
                )

    def test_prepares_paired_radioss_decks_and_validates_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings(Path(tmp) / "workspace", None, 4, 32)
            settings.ensure()
            projects = ProjectService(settings)
            project = projects.create("radioss-analysis")
            service = AnalysisProfileService(projects)
            result = service.prepare_radioss_block_impact(
                project["project_id"],
                "Impact",
                [5, 6, 6],
                [2, 2, 2],
                [2, 10, 10],
                [1, 2, 2],
                1,
                5,
                1,
                0.1,
            )
            self.assertEqual(Path(result["starter_file"]).name, "block_impact_0000.rad")
            self.assertEqual(Path(result["engine_file"]).name, "block_impact_0001.rad")
            with self.assertRaisesRegex(ValueError, "must end with _0000.rad"):
                service.prepare_radioss_block_impact(
                    project["project_id"],
                    "Bad name",
                    [1, 1, 1],
                    [1, 1, 1],
                    [1, 1, 1],
                    [1, 1, 1],
                    1,
                    1,
                    1,
                    0.1,
                    output_name="bad.rad",
                )


if __name__ == "__main__":
    unittest.main()
