from pathlib import Path
from types import SimpleNamespace

import pytest

from ansa_mcp_bridge.handlers import HandlerRegistry


@pytest.fixture
def setup(tmp_path):
    class Base:
        def __init__(self):
            self.deck = 1
            self.database = ""
            self.calls = 0
            self.entities = {1: SimpleNamespace(_id=1, card_fields=lambda deck: ["Name", "X1"])}

        def CurrentDeck(self): return self.deck
        def DataBaseName(self): return self.database
        def RedrawAll(self): return 1
        def GetEntity(self, deck, kind, identity): return self.entities.get(identity)
        def SetCurrentDeck(self, deck):
            """Switch solver environment, not convert a model."""
            self.calls += 1
            old, self.deck = self.deck, deck
            return old
        def DeleteEntity(self, entities, force, compress):
            assert not force and not compress
            self.calls += 1
            for e in entities: self.entities.pop(e._id)
            return 0
        def Or(self, entities): self.calls += 1; return 1
        def Not(self, entities): self.calls += 1; return 1
        def CurvesNew(self, points): self.calls += 1; return SimpleNamespace(_id=10)
        def Open(self, path): self.calls += 1; self.database = path; return 0
    base = Base()
    registry = HandlerRegistry([str(tmp_path)], modules={"base": base,
        "session": SimpleNamespace(DeckName=lambda d: str(d)), "checks": None,
        "constants": SimpleNamespace(NASTRAN=1, ABAQUS=8),
        "mesh": SimpleNamespace(SolidSmooth=lambda e, freeze_skin: 0, ReconstructShells=lambda e: 1)})
    expected = dict(expected_database="", expected_session_nonce=registry.session_nonce,
                    expected_deck=1, confirm=True, operation_id="generic-test-001")
    return registry, base, expected, tmp_path


def test_catalog_and_discovery_do_not_execute(setup):
    r, b, _, _ = setup
    catalog = r.get_capabilities()
    assert len(catalog["general_operations"]["operations"]) == 24
    assert not any("cantilever" in name for name in r.allowed_methods)
    assert {"CurrentDeck", "SetCurrentDeck"} <= set(r.dispatch("search_api", {"module": "base", "query": "Deck"})["names"])
    assert "Switch" in r.dispatch("get_api_help", {"module": "base", "name": "SetCurrentDeck"})["doc"]
    assert r.dispatch("get_entity_fields", {"entity_type": "GRID", "entity_id": 1})["fields"] == ["Name", "X1"]
    assert b.calls == 0


@pytest.mark.parametrize("operation,parameters", [
    ("set_deck", {"deck_name": "ABAQUS"}),
    ("isolate_entities", {"entity_type": "GRID", "entity_ids": [1]}),
    ("hide_entities", {"entity_type": "GRID", "entity_ids": [1]}),
    ("delete_entities", {"entity_type": "GRID", "entity_ids": [1]}),
    ("create_curve", {"points": [[0, 0, 0], [1, 1, 1]]}),
    ("smooth_solids", {"entity_type": "SOLID", "entity_ids": [1]}),
    ("reconstruct_shells", {"entity_type": "SHELL", "entity_ids": [1]}),
])
def test_operations_record_and_replay_without_executing_again(setup, operation, parameters):
    r, b, expected, _ = setup
    payload = dict(expected, operation=operation, parameters=parameters)
    result = r.dispatch("execute_operation", payload)
    assert result["live_step"]["sequence"] == 1
    before = b.calls
    assert r.dispatch("execute_operation", payload)["idempotent_replay"]
    assert b.calls == before
    assert len(r.get_step_history()["steps"]) == 1


def test_open_allowed_file_and_replay_after_database_changes(setup):
    r, b, expected, root = setup
    file = root / "part.ansa"
    file.write_bytes(b"test")
    args = dict(expected, operation="open_model", parameters={"path": str(file), "replace_current": True})
    assert r.dispatch("execute_operation", args)["database_after"] == str(file)
    assert r.dispatch("execute_operation", args)["idempotent_replay"]
    assert b.calls == 1


@pytest.mark.parametrize("update", [
    {"confirm": False}, {"confirm": 1}, {"expected_session_nonce": "0" * 32},
    {"expected_database": "different.ansa"}, {"expected_deck": 8}, {"expected_deck": True},
    {"parameters": {"entity_type": "GRID", "entity_ids": [True]}},
    {"parameters": {"entity_type": "GRID", "entity_ids": [1, 1]}},
    {"parameters": {"entity_type": "GRID", "entity_ids": [1, 9]}},
    {"parameters": {"entity_type": "GRID", "entity_ids": [1], "force": True}},
])
def test_invalid_or_stale_write_never_calls_native_api(setup, update):
    r, b, expected, _ = setup
    args = dict(expected, operation="delete_entities", parameters={"entity_type": "GRID", "entity_ids": [1]})
    args.update(update)
    with pytest.raises((ValueError, RuntimeError)):
        r.dispatch("execute_operation", args)
    assert b.calls == 0 and 1 in b.entities


def test_missing_module_is_reported_not_emulated(setup):
    r, b, expected, _ = setup
    r._modules_override.pop("mesh")
    assert not r.general.catalog()["operations"]["smooth_solids"]["available"]
    with pytest.raises(ValueError, match="UNSUPPORTED_CAPABILITY"):
        r.general.execute("smooth_solids", {"entity_type": "SOLID", "entity_ids": [1]}, **expected)
    assert not r._operation_results


def test_native_constants_can_be_parent_attribute_not_importable_module(setup, monkeypatch):
    import sys
    from types import ModuleType
    r, _, _, _ = setup
    r._modules_override = None
    parent = ModuleType("ansa")
    parent.constants = SimpleNamespace(NASTRAN=1)
    monkeypatch.setitem(sys.modules, "ansa", parent)
    monkeypatch.delitem(sys.modules, "ansa.constants", raising=False)
    assert r.general.module("constants").NASTRAN == 1


def test_failure_after_mutation_stays_unknown_and_blocks_retry(setup):
    r, b, expected, _ = setup
    def bad_delete(*args, **kwargs):
        b.calls += 1
        b.entities.clear()
        raise TypeError("post mutation failure")
    b.DeleteEntity = bad_delete
    args = dict(expected, operation="delete_entities", parameters={"entity_type": "GRID", "entity_ids": [1]})
    for _ in range(2):
        with pytest.raises(RuntimeError, match="OUTCOME_UNKNOWN"):
            r.dispatch("execute_operation", args)
    assert b.calls == 1


@pytest.mark.parametrize("module,name", [("os", "system"), ("base", "__dict__"), ("base", "a.b"), ("base", "NotInstalled")])
def test_api_help_rejects_private_expression_and_missing_api(setup, module, name):
    r, _, _, _ = setup
    with pytest.raises(ValueError): r.general.api_help(module, name)


@pytest.mark.parametrize("points", [[[0, 0, float("nan")], [1, 2, 3]], [[0, True, 0], [1, 2, 3]], [[0, 0, 0]], [[0, 0], [1, 2, 3]]])
def test_curve_validation_before_execution(setup, points):
    r, b, expected, _ = setup
    with pytest.raises(ValueError): r.general.execute("create_curve", {"points": points}, **expected)
    assert b.calls == 0
