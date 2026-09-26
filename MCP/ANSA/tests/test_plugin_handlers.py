from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from ansa_mcp_bridge.handlers import MAX_OPERATION_RECORDS, HandlerRegistry


@dataclass
class _Entity:
    _id: int
    _name: str
    cards: dict[str, Any]


class _FakeBase:
    class Check:
        EXEC_ON_ALL = 1
        REPORT_NONE = 2
        DO_NOT_SHOW_RESULTS = 4
        CLEAR_OLD = 8
        KEEP_OLD = 16

    def __init__(self, database: Path):
        self.database = str(database)
        self.entities = {
            "NODE": [
                _Entity(1, "NODE", {"Name": "N1", "X1": 1.0}),
                _Entity(2, "NODE", {"Name": "N2", "X1": 2.0}),
            ]
        }
        self.set_calls = 0
        self.create_calls = 0
        self.save_calls = 0
        self.redraw_calls = 0

    def CurrentDeck(self) -> int:
        return 7

    def DataBaseName(self) -> str:
        return self.database

    def CollectEntities(self, deck, parent, entity_type, **kwargs):
        return list(self.entities.get(entity_type, []))

    def GetEntityType(self, deck, entity) -> str:
        return entity._name

    def GetEntityCardValues(self, deck, entity, fields):
        return {
            field: (
                entity._id
                if field == "__id__"
                else entity._name
                if field == "__type__"
                else entity.cards.get(field)
            )
            for field in fields
        }

    def GetEntity(self, deck, entity_type, entity_id):
        return next(
            (
                entity
                for entity in self.entities.get(entity_type, [])
                if entity._id == entity_id
            ),
            None,
        )

    def SetEntityCardValues(self, deck, entity, values):
        self.set_calls += 1
        entity.cards.update(values)
        return 0

    def CreateEntity(self, deck, entity_type, fields):
        self.create_calls += 1
        entity = _Entity(100 + self.create_calls, entity_type, dict(fields))
        self.entities.setdefault(entity_type, []).append(entity)
        return entity

    def SaveAs(self, path, silent=True):
        self.save_calls += 1
        target = Path(path)
        target.write_bytes(b"fake-ansa-database")
        return 0

    def RedrawAll(self):
        self.redraw_calls += 1
        return 1


class _FakeSession:
    @staticmethod
    def DeckName(deck: int) -> str:
        return "NASTRAN"

    @staticmethod
    def ApplicationInformation(mode: str):
        return {"version": "25.1.2", "mode": mode}


class _FakeCheck:
    execute_calls: list[dict[str, Any]] = []

    @staticmethod
    def is_available_in_deck(deck: int) -> bool:
        return True

    @classmethod
    def execute(cls, **kwargs):
        cls.execute_calls.append(dict(kwargs))
        return []


class _FakeCheckGroup:
    def __getattr__(self, name: str):
        return _FakeCheck


@pytest.fixture()
def fake_registry(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    base = _FakeBase(tmp_path / "source.ansa")
    modules = {
        "base": base,
        "constants": SimpleNamespace(),
        "session": _FakeSession(),
        "checks": SimpleNamespace(
            general=_FakeCheckGroup(),
            geometry=_FakeCheckGroup(),
            mesh=_FakeCheckGroup(),
        ),
    }
    return HandlerRegistry([str(workspace)], modules=modules), base, workspace


def test_read_summary_list_and_exact_entity(fake_registry) -> None:
    registry, _, _ = fake_registry

    summary = registry.get_model_summary(["NODE"])
    page = registry.list_entities("NODE", fields=["Name", "X1"], limit=1)
    entity = registry.get_entity("NODE", 2, fields=["Name", "X1"])

    assert summary["counts"] == {"NODE": 2}
    assert summary["database"].endswith("source.ansa")
    assert page["total"] == 2
    assert page["has_more"] is True
    assert page["entities"][0]["card_values"] == {"Name": "N1", "X1": 1.0}
    assert entity["id"] == 2
    assert entity["card_values"]["Name"] == "N2"


def test_dispatch_records_and_redraws_each_mutating_step(fake_registry) -> None:
    registry, base, _ = fake_registry
    params = {
        "entity_type": "NODE", "fields": {"Name": "N3"},
        "expected_database": base.database,
        "expected_session_nonce": registry.session_nonce,
        "operation_id": "visible-create-01", "confirm": True,
    }
    first = registry.dispatch("create_entity", params)
    replay = registry.dispatch("create_entity", params)
    history = registry.dispatch("get_step_history", {"limit": 20})

    assert first["created"] is True
    assert first["live_step"]["sequence"] == 1
    assert first["live_step"]["view_refresh"]["returned_success"] is True
    assert replay["idempotent_replay"] is True
    assert base.create_calls == 1
    assert base.redraw_calls == 1
    assert len(history["steps"]) == 1


def test_arbitrary_python_step_runs_on_live_registry_and_records_view(fake_registry) -> None:
    registry, base, _ = fake_registry
    result = registry.dispatch("execute_python_step", {
        "step_name": "Rename one node",
        "code": "base.entities['NODE'][0].cards['Name'] = 'AI node'\nresult = {'id': 1}",
        "expected_database": base.database,
        "expected_session_nonce": registry.session_nonce,
        "expected_deck": 7,
        "operation_id": "python-step-001",
        "confirm": True,
    })
    assert base.entities["NODE"][0].cards["Name"] == "AI node"
    assert result["python_result"] == {"id": 1}
    assert result["model_effect_verified"] is False
    assert result["live_step"]["label"] == "Rename one node"
    assert result["live_step"]["view_refresh"]["returned_success"] is True
    assert base.redraw_calls == 1


def test_python_step_exception_is_outcome_unknown_and_redraws(fake_registry) -> None:
    registry, base, _ = fake_registry
    params = {
        "step_name": "Fault after change",
        "code": "base.entities['NODE'][0].cards['Name'] = 'changed'\nraise RuntimeError('stop')",
        "expected_database": base.database,
        "expected_session_nonce": registry.session_nonce,
        "expected_deck": 7,
        "operation_id": "python-fault-01",
        "confirm": True,
    }
    with pytest.raises(RuntimeError, match="^OUTCOME_UNKNOWN:"):
        registry.dispatch("execute_python_step", params)
    assert registry.get_step_history()["latest_sequence"] == 1
    assert base.entities["NODE"][0].cards["Name"] == "changed"
    assert base.redraw_calls == 1
    assert registry.get_step_history()["steps"][-1]["status"] == "outcome_unknown"
    with pytest.raises(RuntimeError, match="^OUTCOME_UNKNOWN:"):
        registry.dispatch("execute_python_step", params)
    assert registry.get_step_history()["latest_sequence"] == 1


def test_redraw_failure_does_not_reexecute_committed_python(fake_registry) -> None:
    registry, base, _ = fake_registry
    base.RedrawAll = lambda: 0
    params = {
        "step_name": "Rename node once",
        "code": "base.entities['NODE'][0].cards['Name'] = 'once'",
        "expected_database": base.database,
        "expected_session_nonce": registry.session_nonce,
        "expected_deck": 7,
        "operation_id": "python-redraw-01",
        "confirm": True,
    }
    first = registry.dispatch("execute_python_step", params)
    replay = registry.dispatch("execute_python_step", params)
    assert first["live_step"]["view_refresh"]["returned_success"] is False
    assert replay["idempotent_replay"] is True
    assert registry.get_step_history()["latest_sequence"] == 1


def test_python_step_requires_confirmation_and_current_session(fake_registry) -> None:
    registry, base, _ = fake_registry
    params = {
        "step_name": "Do not run",
        "code": "base.entities['NODE'][0].cards['Name'] = 'unsafe'",
        "expected_database": base.database,
        "expected_session_nonce": registry.session_nonce,
        "expected_deck": 7,
        "operation_id": "python-guard-01",
        "confirm": False,
    }
    with pytest.raises(ValueError, match="confirm=true"):
        registry.dispatch("execute_python_step", params)
    params["confirm"] = True
    params["expected_deck"] = 8
    with pytest.raises(RuntimeError, match="SESSION_CHANGED"):
        registry.dispatch("execute_python_step", params)
    params["expected_deck"] = 7
    params["expected_session_nonce"] = "0" * 32
    with pytest.raises(RuntimeError, match="SESSION_CHANGED"):
        registry.dispatch("execute_python_step", params)
    assert base.entities["NODE"][0].cards["Name"] == "N1"


def test_only_none_selects_default_collections_and_fields(fake_registry) -> None:
    registry, _, _ = fake_registry

    summary = registry.get_model_summary()
    page = registry.list_entities("NODE")
    checks = registry.run_model_checks()

    assert "NODE" in summary["counts"]
    assert page["entities"][0]["card_values"] == {
        "__id__": 1,
        "__type__": "NODE",
        "Name": "N1",
    }
    assert checks["requested"]

    with pytest.raises(ValueError, match="entity_types must be a non-empty list"):
        registry.get_model_summary([])
    with pytest.raises(ValueError, match="entity_types must be a non-empty list"):
        registry.get_model_summary("NODE")
    with pytest.raises(ValueError, match="check_names must be a non-empty list"):
        registry.run_model_checks([])
    with pytest.raises(ValueError, match="check_names must be a non-empty list"):
        registry.run_model_checks("free_nodes")
    with pytest.raises(ValueError, match="fields must contain between"):
        registry.list_entities("NODE", fields=[])
    with pytest.raises(ValueError, match="fields must be a list"):
        registry.get_entity("NODE", 1, fields="Name")


@pytest.mark.parametrize("value", [True, 1.5, "1"])
def test_paging_and_check_limits_require_non_boolean_integers(
    fake_registry, value
) -> None:
    registry, _, _ = fake_registry

    with pytest.raises(ValueError, match="limit must be an integer"):
        registry.list_entities("NODE", limit=value)
    with pytest.raises(ValueError, match="offset must be an integer"):
        registry.list_entities("NODE", offset=value)
    with pytest.raises(ValueError, match="max_issues must be an integer"):
        registry.run_model_checks(["free_nodes"], max_issues=value)


def test_model_checks_preserve_existing_history(fake_registry) -> None:
    registry, base, _ = fake_registry
    _FakeCheck.execute_calls.clear()

    result = registry.run_model_checks(["free_nodes"])

    assert result["results"]["free_nodes"]["available"] is True
    assert _FakeCheck.execute_calls == [
        {
            "exec_mode": base.Check.EXEC_ON_ALL,
            "report": base.Check.REPORT_NONE,
            "history": base.Check.KEEP_OLD,
        }
    ]


def test_cas_update_requires_expected_state_and_is_idempotent(fake_registry) -> None:
    registry, base, _ = fake_registry
    operation_id = "update-node-0001"
    args = {
        "entity_type": "NODE",
        "entity_id": 1,
        "values": {"X1": 4.5},
        "expected_values": {"X1": 1.0},
        "expected_database": base.database,
        "expected_session_nonce": registry.session_nonce,
        "operation_id": operation_id,
        "confirm": True,
    }

    first = registry.set_entity_card_values(**args)
    replay = registry.set_entity_card_values(**args)

    assert first["before"] == {"X1": 1.0}
    assert first["after"] == {"X1": 4.5}
    assert first["idempotent_replay"] is False
    assert replay["idempotent_replay"] is True
    assert base.set_calls == 1


def test_cas_update_rejects_stale_value_and_database(fake_registry) -> None:
    registry, base, _ = fake_registry
    common = {
        "entity_type": "NODE",
        "entity_id": 1,
        "values": {"X1": 4.5},
        "expected_database": base.database,
        "expected_session_nonce": registry.session_nonce,
        "confirm": True,
    }
    with pytest.raises(RuntimeError, match="PRECONDITION_FAILED"):
        registry.set_entity_card_values(
            **common,
            expected_values={"X1": 99.0},
            operation_id="stale-value-0001",
        )
    with pytest.raises(RuntimeError, match="SESSION_CHANGED"):
        registry.set_entity_card_values(
            **{**common, "expected_database": "different.ansa"},
            expected_values={"X1": 1.0},
            operation_id="wrong-database-01",
        )
    assert base.set_calls == 0


@pytest.mark.parametrize("entity_id", [True, 1.9, "1"])
def test_entity_handlers_reject_non_integer_entity_ids(
    fake_registry, entity_id
) -> None:
    registry, base, _ = fake_registry

    with pytest.raises(ValueError, match="entity_id must be an integer"):
        registry.get_entity("NODE", entity_id)
    with pytest.raises(ValueError, match="entity_id must be an integer"):
        registry.set_entity_card_values(
            entity_type="NODE",
            entity_id=entity_id,
            values={"X1": 4.5},
            expected_values={"X1": 1.0},
            expected_database=base.database,
            expected_session_nonce=registry.session_nonce,
            operation_id=f"invalid-entity-{type(entity_id).__name__}",
            confirm=True,
        )

    assert base.set_calls == 0


def test_writes_reject_a_stale_bridge_session(fake_registry) -> None:
    registry, base, _ = fake_registry
    with pytest.raises(RuntimeError, match="SESSION_CHANGED"):
        registry.create_entity(
            entity_type="NODE",
            fields={"Name": "N3"},
            expected_database=base.database,
            expected_session_nonce="0" * 32,
            operation_id="stale-session-01",
            confirm=True,
        )
    assert base.create_calls == 0


def test_operation_id_prevents_duplicate_create_and_cross_method_reuse(
    fake_registry,
) -> None:
    registry, base, _ = fake_registry
    operation_id = "create-node-0001"
    args = {
        "entity_type": "NODE",
        "fields": {"Name": "N3", "X1": 3.0},
        "expected_database": base.database,
        "expected_session_nonce": registry.session_nonce,
        "operation_id": operation_id,
        "confirm": True,
    }

    first = registry.create_entity(**args)
    replay = registry.create_entity(**args)

    assert first["created"] is True
    assert first["card_values_verified"] is True
    assert first["card_values_expected"] == {"Name": "N3", "X1": 3.0}
    assert first["card_values_actual"] == {"Name": "N3", "X1": 3.0}
    assert first["entity"]["card_values"] == first["card_values_actual"]
    assert replay["idempotent_replay"] is True
    assert base.create_calls == 1
    with pytest.raises(ValueError, match="different parameters"):
        registry.create_entity(**{**args, "fields": {"Name": "different"}})
    with pytest.raises(ValueError, match="already used for another method"):
        registry.set_entity_card_values(
            entity_type="NODE",
            entity_id=1,
            values={"X1": 2.0},
            expected_values={"X1": 1.0},
            expected_database=base.database,
            expected_session_nonce=registry.session_nonce,
            operation_id=operation_id,
            confirm=True,
        )


def test_writes_require_explicit_confirmation(fake_registry) -> None:
    registry, base, _ = fake_registry
    with pytest.raises(ValueError, match="confirm=true"):
        registry.create_entity(
            entity_type="NODE",
            fields={"Name": "N3"},
            expected_database=base.database,
            expected_session_nonce=registry.session_nonce,
            operation_id="create-node-0002",
        )
    assert base.create_calls == 0


@pytest.mark.parametrize(
    ("field", "invalid", "message"),
    [
        ("expected_database", None, "expected_database must be a string"),
        ("expected_database", 123, "expected_database must be a string"),
        (
            "expected_session_nonce",
            None,
            "expected_session_nonce must contain exactly 32 hexadecimal characters",
        ),
        (
            "expected_session_nonce",
            "short",
            "expected_session_nonce must contain exactly 32 hexadecimal characters",
        ),
        (
            "expected_session_nonce",
            "g" * 32,
            "expected_session_nonce must contain exactly 32 hexadecimal characters",
        ),
    ],
)
def test_all_persistent_writes_validate_expected_context_before_mutation(
    fake_registry, field: str, invalid, message: str
) -> None:
    registry, base, workspace = fake_registry
    expected = {
        "expected_database": base.database,
        "expected_session_nonce": registry.session_nonce,
    }
    expected[field] = invalid

    with pytest.raises(ValueError, match=message):
        registry.save_database(
            str(workspace / "invalid-context.ansa"),
            operation_id="invalid-save-context",
            confirm=True,
            **expected,
        )
    with pytest.raises(ValueError, match=message):
        registry.create_entity(
            entity_type="NODE",
            fields={"Name": "N3"},
            operation_id="invalid-create-context",
            confirm=True,
            **expected,
        )
    with pytest.raises(ValueError, match=message):
        registry.set_entity_card_values(
            entity_type="NODE",
            entity_id=1,
            values={"X1": 4.5},
            expected_values={"X1": 1.0},
            operation_id="invalid-update-context",
            confirm=True,
            **expected,
        )

    assert base.save_calls == 0
    assert base.create_calls == 0
    assert base.set_calls == 0


def test_persistent_writes_allow_an_explicit_empty_expected_database(
    fake_registry,
) -> None:
    registry, base, workspace = fake_registry
    base.database = ""

    saved = registry.save_database(
        str(workspace / "unsaved-session.ansa"),
        expected_database="",
        expected_session_nonce=registry.session_nonce,
        operation_id="empty-db-save-01",
        confirm=True,
    )
    created = registry.create_entity(
        entity_type="NODE",
        fields={"Name": "N3"},
        expected_database="",
        expected_session_nonce=registry.session_nonce,
        operation_id="empty-db-create-01",
        confirm=True,
    )
    updated = registry.set_entity_card_values(
        entity_type="NODE",
        entity_id=1,
        values={"X1": 4.5},
        expected_values={"X1": 1.0},
        expected_database="",
        expected_session_nonce=registry.session_nonce,
        operation_id="empty-db-update-01",
        confirm=True,
    )

    assert saved["saved"] is True
    assert created["card_values_verified"] is True
    assert updated["updated"] is True
    assert (base.save_calls, base.create_calls, base.set_calls) == (1, 1, 1)


def test_save_is_workspace_scoped_verified_and_idempotent(fake_registry) -> None:
    registry, base, workspace = fake_registry
    target = workspace / "runs" / "saved.ansa"

    first = registry.save_database(
        str(target),
        expected_database=base.database,
        expected_session_nonce=registry.session_nonce,
        operation_id="save-database-01",
        confirm=True,
    )
    replay = registry.save_database(
        str(target),
        expected_database=base.database,
        expected_session_nonce=registry.session_nonce,
        operation_id="save-database-01",
        confirm=True,
    )

    assert first["saved"] is True
    assert first["silent_snapshot"] is True
    assert first["database"] == base.database
    assert first["path"] == str(target.resolve())
    assert first["size"] > 0
    assert len(first["sha256"]) == 64
    assert replay["idempotent_replay"] is True
    assert base.save_calls == 1


def test_save_rejects_outside_root_wrong_suffix_and_existing_file(
    fake_registry, tmp_path: Path
) -> None:
    registry, base, workspace = fake_registry
    with pytest.raises(ValueError, match="PATH_NOT_ALLOWED"):
        registry.save_database(
            str(tmp_path / "outside.ansa"),
            expected_database=base.database,
            expected_session_nonce=registry.session_nonce,
            operation_id="save-outside-001",
            confirm=True,
        )
    with pytest.raises(ValueError, match="Only .ansa"):
        registry.save_database(
            str(workspace / "model.txt"),
            expected_database=base.database,
            expected_session_nonce=registry.session_nonce,
            operation_id="save-bad-suffix",
            confirm=True,
        )
    existing = workspace / "existing.ansa"
    existing.write_bytes(b"do-not-overwrite")
    with pytest.raises(FileExistsError, match="FILE_EXISTS"):
        registry.save_database(
            str(existing),
            expected_database=base.database,
            expected_session_nonce=registry.session_nonce,
            operation_id="save-existing-1",
            confirm=True,
        )
    assert base.save_calls == 0


@pytest.mark.parametrize("overwrite", ["false", 0, 1])
def test_save_rejects_non_boolean_overwrite(fake_registry, overwrite) -> None:
    registry, base, workspace = fake_registry
    target = workspace / "strict-overwrite.ansa"
    target.write_bytes(b"original")

    with pytest.raises(ValueError, match="overwrite must be a boolean"):
        registry.save_database(
            str(target),
            expected_database=base.database,
            expected_session_nonce=registry.session_nonce,
            operation_id=f"strict-overwrite-{overwrite!s}",
            confirm=True,
            overwrite=overwrite,
        )

    assert target.read_bytes() == b"original"
    assert base.save_calls == 0


def test_save_requires_explicit_true_to_overwrite_existing_file(fake_registry) -> None:
    registry, base, workspace = fake_registry
    target = workspace / "explicit-overwrite.ansa"
    target.write_bytes(b"original")

    with pytest.raises(FileExistsError, match="FILE_EXISTS"):
        registry.save_database(
            str(target),
            expected_database=base.database,
            expected_session_nonce=registry.session_nonce,
            operation_id="overwrite-false-01",
            confirm=True,
            overwrite=False,
        )

    result = registry.save_database(
        str(target),
        expected_database=base.database,
        expected_session_nonce=registry.session_nonce,
        operation_id="overwrite-true-001",
        confirm=True,
        overwrite=True,
    )

    assert result["saved"] is True
    assert target.read_bytes() == b"fake-ansa-database"
    assert base.save_calls == 1


@pytest.mark.parametrize("exception_type", [ValueError, TypeError])
def test_save_post_mutation_exception_remains_pending_and_blocks_retry(
    fake_registry, exception_type: type[Exception]
) -> None:
    registry, base, workspace = fake_registry
    target = workspace / "uncertain-save.ansa"
    operation_id = "uncertain-save-01"
    args = {
        "path": str(target),
        "expected_database": base.database,
        "expected_session_nonce": registry.session_nonce,
        "operation_id": operation_id,
        "confirm": True,
    }

    def uncertain_save(path, silent=True):
        base.save_calls += 1
        Path(path).write_bytes(b"possibly-complete")
        raise exception_type("synthetic post-save failure")

    base.SaveAs = uncertain_save

    with pytest.raises(RuntimeError) as first_error:
        registry.save_database(**args)
    with pytest.raises(RuntimeError) as retry_error:
        registry.save_database(**args)

    assert str(first_error.value).startswith(
        f"OUTCOME_UNKNOWN: operation_id={operation_id};"
    )
    assert exception_type.__name__ in str(first_error.value)
    assert isinstance(first_error.value.__cause__, exception_type)
    assert str(retry_error.value).startswith(
        f"OUTCOME_UNKNOWN: operation_id={operation_id};"
    )
    assert registry._operation_results[operation_id][2:] == ("pending", None)
    assert base.save_calls == 1
    assert target.read_bytes() == b"possibly-complete"


def test_create_readback_failure_remains_pending_and_blocks_retry(
    fake_registry,
) -> None:
    registry, base, _ = fake_registry
    args = {
        "entity_type": "NODE",
        "fields": {"Name": "expected"},
        "expected_database": base.database,
        "expected_session_nonce": registry.session_nonce,
        "operation_id": "uncertain-create-01",
        "confirm": True,
    }

    def create_with_mismatched_readback(deck, entity_type, fields):
        base.create_calls += 1
        entity = _Entity(100 + base.create_calls, entity_type, {"Name": "actual"})
        base.entities.setdefault(entity_type, []).append(entity)
        return entity

    base.CreateEntity = create_with_mismatched_readback

    with pytest.raises(RuntimeError) as first_error:
        registry.create_entity(**args)
    with pytest.raises(RuntimeError, match="^OUTCOME_UNKNOWN:"):
        registry.create_entity(**args)

    assert str(first_error.value).startswith(
        "OUTCOME_UNKNOWN: operation_id=uncertain-create-01;"
    )
    assert "card readback mismatch" in str(first_error.value)
    assert registry._operation_results["uncertain-create-01"][2:] == (
        "pending",
        None,
    )
    assert base.create_calls == 1


@pytest.mark.parametrize("exception_type", [ValueError, TypeError])
def test_create_post_mutation_exception_remains_pending_and_blocks_retry(
    fake_registry, exception_type: type[Exception]
) -> None:
    registry, base, _ = fake_registry
    operation_id = "uncertain-create-api"
    args = {
        "entity_type": "NODE",
        "fields": {"Name": "possibly-created"},
        "expected_database": base.database,
        "expected_session_nonce": registry.session_nonce,
        "operation_id": operation_id,
        "confirm": True,
    }

    def uncertain_create(deck, entity_type, fields):
        base.create_calls += 1
        entity = _Entity(100 + base.create_calls, entity_type, dict(fields))
        base.entities.setdefault(entity_type, []).append(entity)
        raise exception_type("synthetic post-create failure")

    base.CreateEntity = uncertain_create

    with pytest.raises(RuntimeError) as first_error:
        registry.create_entity(**args)
    with pytest.raises(RuntimeError) as retry_error:
        registry.create_entity(**args)

    assert str(first_error.value).startswith(
        f"OUTCOME_UNKNOWN: operation_id={operation_id};"
    )
    assert exception_type.__name__ in str(first_error.value)
    assert isinstance(first_error.value.__cause__, exception_type)
    assert str(retry_error.value).startswith(
        f"OUTCOME_UNKNOWN: operation_id={operation_id};"
    )
    assert registry._operation_results[operation_id][2:] == ("pending", None)
    assert base.create_calls == 1
    assert base.entities["NODE"][-1].cards == {"Name": "possibly-created"}


@pytest.mark.parametrize("exception_type", [ValueError, TypeError])
def test_update_post_mutation_exception_remains_pending_and_blocks_retry(
    fake_registry, exception_type: type[Exception]
) -> None:
    registry, base, _ = fake_registry
    operation_id = "uncertain-update-01"
    args = {
        "entity_type": "NODE",
        "entity_id": 1,
        "values": {"X1": 4.5},
        "expected_values": {"X1": 1.0},
        "expected_database": base.database,
        "expected_session_nonce": registry.session_nonce,
        "operation_id": operation_id,
        "confirm": True,
    }

    def uncertain_update(deck, entity, values):
        base.set_calls += 1
        entity.cards.update(values)
        raise exception_type("synthetic post-update failure")

    base.SetEntityCardValues = uncertain_update

    with pytest.raises(RuntimeError) as first_error:
        registry.set_entity_card_values(**args)
    with pytest.raises(RuntimeError) as retry_error:
        registry.set_entity_card_values(**args)

    assert str(first_error.value).startswith(
        f"OUTCOME_UNKNOWN: operation_id={operation_id};"
    )
    assert exception_type.__name__ in str(first_error.value)
    assert isinstance(first_error.value.__cause__, exception_type)
    assert str(retry_error.value).startswith(
        f"OUTCOME_UNKNOWN: operation_id={operation_id};"
    )
    assert registry._operation_results[operation_id][2:] == ("pending", None)
    assert base.set_calls == 1
    assert base.entities["NODE"][0].cards["X1"] == 4.5


def test_full_operation_ledger_fails_closed_without_evicting_or_mutating(
    fake_registry,
) -> None:
    registry, base, _ = fake_registry
    for index in range(MAX_OPERATION_RECORDS):
        registry._operation_results[f"record-{index:04d}"] = (
            "create_entity",
            f"fingerprint-{index:04d}",
            "success",
            {"operation_id": f"record-{index:04d}"},
        )

    with pytest.raises(RuntimeError, match="^PRECONDITION_FAILED: operation ledger"):
        registry.create_entity(
            entity_type="NODE",
            fields={"Name": "must-not-be-created"},
            expected_database=base.database,
            expected_session_nonce=registry.session_nonce,
            operation_id="ledger-full-create",
            confirm=True,
        )

    assert len(registry._operation_results) == MAX_OPERATION_RECORDS
    assert "record-0000" in registry._operation_results
    assert base.create_calls == 0


@pytest.mark.parametrize("visible_only", ["false", 0, 1])
def test_read_handlers_reject_non_boolean_visible_only(
    fake_registry, visible_only
) -> None:
    registry, _, _ = fake_registry

    with pytest.raises(ValueError, match="visible_only must be a boolean"):
        registry.get_model_summary(["NODE"], visible_only=visible_only)
    with pytest.raises(ValueError, match="visible_only must be a boolean"):
        registry.list_entities("NODE", visible_only=visible_only)
