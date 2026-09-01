from __future__ import annotations

import argparse
import tempfile
import unittest
from pathlib import Path

from tools.prepare_beam_import_smoke import prepare
from tools.validate_beam_import_contract import validate


def make_args(tmp_path: Path, step: Path, **overrides):
    values = {
        "step": str(step),
        "project": str(tmp_path / "beam.wbpj"),
        "output_dir": str(tmp_path / "prepared"),
        "units": "mm",
        "system_name": "Fixture",
        "allow_overwrite": False,
        "open_spaceclaim": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


class BeamImportTemplateTests(unittest.TestCase):
    def test_prepare_renders_guarded_journal_and_valid_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            step = tmp_path / "tube.step"
            step.write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="ascii")
            payload = prepare(make_args(tmp_path, step))
            self.assertEqual(validate(payload), [])
            journal = Path(payload["evidence"]["journal_path"])
            text = journal.read_text(encoding="utf-8")
            self.assertNotIn("__STEP_PATH_PY__", text)
            self.assertNotIn("__UNITS_PY__", text)
            self.assertIn(repr(str(step.resolve())), text)
            compile("\n".join(text.splitlines()[2:]), str(journal), "exec")
            self.assertEqual(payload["status"], "NOT_RUN")
            self.assertIsNone(payload["gates"]["workbench_step_import"])

    def test_prepare_refuses_existing_project_without_authorization(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            step = tmp_path / "tube.step"
            step.write_text("STEP", encoding="ascii")
            project = tmp_path / "beam.wbpj"
            project.write_text("existing", encoding="ascii")
            with self.assertRaises(FileExistsError):
                prepare(make_args(tmp_path, step, project=str(project)))

    def test_contract_rejects_unobserved_pass(self):
        payload = {
            "schema_version": 1,
            "workflow": "fusion_step_to_beam_smoke",
            "phase": "PREPARED",
            "status": "PASS",
            "ok": True,
            "source_step": "tube.step",
            "units": "mm",
            "gates": {gate: None for gate in ("step_file_check", "workbench_step_import", "spaceclaim_beam_idealization", "mechanical_line_body_import")},
            "warnings": [],
            "errors": [],
            "evidence": {},
        }
        self.assertIn("PASS requires every smoke gate=true", validate(payload))


if __name__ == "__main__":
    unittest.main()
