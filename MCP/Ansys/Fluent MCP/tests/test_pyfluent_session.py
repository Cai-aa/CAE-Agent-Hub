from __future__ import annotations

import types
import unittest
from unittest import mock

from tools import pyfluent_session


class FakeTui:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, command: str) -> str:
        self.calls.append(command)
        return f"tui:{command}"


class FakeSession:
    def __init__(self) -> None:
        self.tui = FakeTui()
        self.closed = False

    def get_fluent_version(self) -> str:
        return "25.2.0"

    def scheme_eval(self, expression: str) -> str:
        return f"scheme:{expression}"

    def exit(self) -> None:
        self.closed = True


class PyFluentSessionTests(unittest.TestCase):
    def test_launch_session_uses_pyfluent_defaults(self) -> None:
        calls: list[dict[str, object]] = []
        fake_session = FakeSession()

        def fake_launch_fluent(**kwargs: object) -> FakeSession:
            calls.append(kwargs)
            return fake_session

        fake_core = types.SimpleNamespace(launch_fluent=fake_launch_fluent)
        with mock.patch.object(pyfluent_session, "_import_pyfluent_core", lambda: fake_core):
            manager = pyfluent_session.PyFluentSessionManager()
            result = manager.launch_session(session_id="main")

        self.assertIs(result["ok"], True)
        self.assertEqual(result["session_id"], "main")
        self.assertEqual(calls[0]["dimension"], 3)
        self.assertEqual(calls[0]["precision"], "double")
        self.assertEqual(calls[0]["ui_mode"], "hidden_gui")
        self.assertEqual(calls[0]["processor_count"], 2)

    def test_execute_scheme_requires_existing_session(self) -> None:
        manager = pyfluent_session.PyFluentSessionManager()

        with self.assertRaisesRegex(KeyError, "missing"):
            manager.execute_scheme("missing", "(+ 2 3)")

    def test_execute_scheme_delegates_to_session(self) -> None:
        fake_session = FakeSession()
        manager = pyfluent_session.PyFluentSessionManager()
        manager.sessions["main"] = fake_session

        result = manager.execute_scheme("main", "(+ 2 3)")

        self.assertEqual(result, {"ok": True, "session_id": "main", "result": "scheme:(+ 2 3)"})

    def test_close_session_calls_exit(self) -> None:
        fake_session = FakeSession()
        manager = pyfluent_session.PyFluentSessionManager()
        manager.sessions["main"] = fake_session

        result = manager.close_session("main")

        self.assertIs(result["ok"], True)
        self.assertIs(fake_session.closed, True)
        self.assertNotIn("main", manager.sessions)


if __name__ == "__main__":
    unittest.main()
