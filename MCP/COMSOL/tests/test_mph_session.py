from __future__ import annotations

import sys
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.mph_session import ComsolMphSessionManager


class FakeModel:
    def __init__(self, name: str = "Model 1", file_path: str | None = None):
        self._name = name
        self._file = file_path
        self.params = {"L": "10[mm]"}
        self.solved = []
        self.saved = []

    def name(self):
        return self._name

    def file(self):
        return self._file

    def version(self):
        return "6.4"

    def parameters(self, evaluate=False):
        return dict(self.params)

    def descriptions(self):
        return {"L": "length"}

    def components(self):
        return ["comp1"]

    def physics(self):
        return ["ht"]

    def studies(self):
        return ["std1"]

    def datasets(self):
        return ["dset1"]

    def plots(self):
        return ["pg1"]

    def exports(self):
        return ["img1"]

    def parameter(self, name, value=None, evaluate=False):
        if value is None:
            return self.params[name]
        self.params[name] = value

    def description(self, name, text=None):
        return text or ""

    def solve(self, study=None):
        self.solved.append(study)

    def evaluate(self, expression, unit=None, dataset=None):
        return [1.0, 2.0]

    def export(self, node_name, file_path):
        return None

    def save(self, path=None, format=None):
        self.saved.append((path, format))


class FakeClient:
    created_count = 0
    delay_seconds = 0.0

    def __init__(self, **kwargs):
        type(self).created_count += 1
        if type(self).delay_seconds:
            time.sleep(type(self).delay_seconds)
        self.kwargs = kwargs
        self.version = "6.4"
        self.cores = kwargs.get("cores")
        self.standalone = True
        self.loaded = []

    def names(self):
        return [model.name() for model in self.loaded]

    def load(self, path):
        model = FakeModel("Loaded", path)
        self.loaded.append(model)
        return model

    def create(self, name=None):
        model = FakeModel(name or "Model 1")
        self.loaded.append(model)
        return model

    def clear(self):
        self.loaded.clear()


class MphSessionTests(unittest.TestCase):
    def test_remote_disconnect_preserves_server_models(self):
        from unittest.mock import Mock
        manager=ComsolMphSessionManager(); client=Mock(standalone=False); manager.client=client
        self.assertTrue(manager.disconnect()['success'])
        client.disconnect.assert_called_once(); client.clear.assert_not_called()

    def fake_mph_module(self):
        FakeClient.created_count = 0
        FakeClient.delay_seconds = 0.0
        module = types.SimpleNamespace()
        module.__version__ = "1.3.1"
        module.options = []
        module.Client = FakeClient
        module.option = lambda name, value: module.options.append((name, value))
        return module

    def test_start_uses_standalone_option_and_tracks_status(self):
        fake_mph = self.fake_mph_module()
        with patch.dict(sys.modules, {"mph": fake_mph}):
            manager = ComsolMphSessionManager()

            result = manager.start(cores=2, version="6.4", standalone=True)

            self.assertTrue(result["success"])
            self.assertEqual(fake_mph.options, [("session", "stand-alone")])
            self.assertEqual(manager.client.kwargs["cores"], 2)
            self.assertEqual(manager.client.kwargs["version"], "6.4")

    def test_start_async_completes_and_tracks_job(self):
        fake_mph = self.fake_mph_module()
        with patch.dict(sys.modules, {"mph": fake_mph}):
            manager = ComsolMphSessionManager()

            started = manager.start_async(cores=1, version="6.4", standalone=True)
            job_id = started["job"]["job_id"]

            deadline = time.time() + 5
            status = {}
            while time.time() < deadline:
                status = manager.start_session_status(job_id)
                if status["job"]["status"] == "connected":
                    break
                time.sleep(0.05)

            self.assertEqual(status["job"]["status"], "connected")
            self.assertTrue(status["session"]["connected"])

    def test_start_async_deduplicates_in_progress_start(self):
        fake_mph = self.fake_mph_module()
        FakeClient.delay_seconds = 0.2
        with patch.dict(sys.modules, {"mph": fake_mph}):
            manager = ComsolMphSessionManager()

            first = manager.start_async()
            second = manager.start_async()

            self.assertTrue(second["already_starting"])
            self.assertEqual(first["job"]["job_id"], second["job"]["job_id"])
            deadline = time.time() + 5
            while time.time() < deadline and manager.start_session_status()["job"]["status"] != "connected":
                time.sleep(0.05)
            self.assertEqual(FakeClient.created_count, 1)

    def test_open_model_reports_starting_session(self):
        fake_mph = self.fake_mph_module()
        FakeClient.delay_seconds = 0.2
        with patch.dict(sys.modules, {"mph": fake_mph}):
            manager = ComsolMphSessionManager()
            manager.start_async()

            result = manager.open_model(__file__)

            self.assertFalse(result["success"])
            self.assertEqual(result["status"], "session_starting")

    def test_open_set_solve_evaluate_and_save_model(self):
        fake_mph = self.fake_mph_module()
        with patch.dict(sys.modules, {"mph": fake_mph}):
            manager = ComsolMphSessionManager()
            manager.start()
            tmp = tempfile.NamedTemporaryFile(suffix=".mph", delete=False)
            tmp.close()
            model_path = Path(tmp.name)

            opened = manager.open_model(str(model_path))
            set_param = manager.set_parameter("L", "20[mm]")
            solved = manager.solve("std1")
            evaluated = manager.evaluate("T")
            saved = manager.save(str(model_path.with_suffix(".mph")))

            self.assertTrue(opened["success"])
            self.assertTrue(set_param["success"])
            self.assertTrue(solved["success"])
            self.assertTrue(evaluated["success"])
            self.assertTrue(saved["success"])
            self.assertEqual(manager.get_model().params["L"], "20[mm]")
            model_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
