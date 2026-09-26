from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from ansa_mcp.cantilever_demo import (
    FIXED_CANTILEVER_SHA256,
    export_visible_cantilever,
    import_visible_cantilever,
    stage_visible_cantilever,
)
from ansa_mcp.settings import Settings
from ansa_mcp_bridge.handlers import HandlerRegistry


class FakeLiveBase:
    def __init__(self):
        self.database = ""
        self.deck = 1
        self.entities = {}
        self.imports = 0
        self.exports = 0
        self.saves = 0
        self.zoomed = 0
        self.redraws = 0

    def CurrentDeck(self):
        return self.deck

    def DataBaseName(self):
        return self.database

    def SetCurrentDeck(self, deck):
        self.deck = deck

    def CollectEntities(self, deck, parent, kind):
        return self.entities.get(kind, [])

    def InputAbaqus(self, path):
        assert Path(path).is_file()
        self.imports += 1
        self.entities = {
            "NODE": [object()] * 615,
            "__ELEMENTS__": [object()] * 320,
            "__MATERIALS__": [object()],
        }
        return 1

    def ZoomAll(self):
        self.zoomed += 1
        return 1

    def RedrawAll(self):
        self.redraws += 1
        return 1

    def SaveAs(self, path, silent=True):
        assert silent is True
        self.saves += 1
        Path(path).write_bytes(b"ANSA snapshot")
        return 0

    def OutputAbaqus(self, path, mode, disregard_includes):
        assert mode == "all" and disregard_includes == "on"
        self.exports += 1
        Path(path).write_text(
            "*NODE\n*ELEMENT\n*MATERIAL\n*SOLID SECTION\n*BOUNDARY\n*CLOAD\n*STATIC\n"
            + "** demo\n" * 150,
            encoding="ascii",
        )
        return 0


class FakeSession:
    @staticmethod
    def DeckName(deck):
        return "ABAQUS"


class FakeLiveClient:
    def __init__(self, registry):
        self.registry = registry

    def call(self, method, params=None):
        if method == "get_capabilities":
            return {
                "methods": self.registry.allowed_methods,
                "save_roots": [str(root) for root in self.registry.allowed_roots],
            }
        return self.registry.dispatch(method, params or {})

    def call_persistent_write(self, method, params, *, operation_id):
        assert params["operation_id"] == operation_id
        return self.registry.dispatch(method, params)


@pytest.fixture()
def visible_setup(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    base = FakeLiveBase()
    progress = []
    registry = HandlerRegistry(
        [str(workspace)],
        enable_examples=True,
        modules={
            "base": base,
            "constants": SimpleNamespace(ABAQUS=8),
            "session": FakeSession(),
            "checks": SimpleNamespace(),
        },
        progress_callback=lambda run_id, phase: progress.append((run_id, phase)),
    )
    settings = Settings(workspace=workspace, installation_root=None, executable=None)
    return settings, FakeLiveClient(registry), registry, base, progress


def test_visible_demo_stages_imports_and_exports_from_live_session(visible_setup):
    settings, live, registry, base, progress = visible_setup
    staged = stage_visible_cantilever(settings, live)
    source = Path(staged["source_deck"])
    assert hashlib.sha256(source.read_bytes()).hexdigest() == FIXED_CANTILEVER_SHA256

    args = (settings, live, staged["run_id"], base.database, registry.session_nonce)
    imported = import_visible_cantilever(*args, "live-import-0001")
    assert imported["ok"] is True
    assert imported["view_fit_and_redraw_returned_success"] is True
    assert (base.imports, base.zoomed, base.redraws) == (1, 1, 1)
    assert import_visible_cantilever(*args, "live-import-0001")["idempotent_replay"] is True
    assert base.imports == 1

    exported = export_visible_cantilever(*args, "live-export-0001")
    assert exported["ok"] is True
    assert (base.saves, base.exports) == (1, 1)
    stage = json.loads((source.parent / "ansa_stage.json").read_text(encoding="utf-8"))
    assert stage["mode"] == "visible_gui"
    assert stage["ok"] is True
    assert progress == [
        (staged["run_id"], "importing"),
        (staged["run_id"], "model_visible"),
        (staged["run_id"], "exported"),
    ]


def test_visible_import_rejects_nonempty_model_before_mutation(visible_setup):
    settings, live, registry, base, _ = visible_setup
    staged = stage_visible_cantilever(settings, live)
    base.entities["NODE"] = [object()]
    with pytest.raises(RuntimeError, match="new empty ANSA model"):
        import_visible_cantilever(
            settings, live, staged["run_id"], base.database,
            registry.session_nonce, "populated-model-0001",
        )
    assert base.imports == 0


def test_visible_import_rejects_changed_source_and_session(visible_setup):
    settings, live, registry, base, _ = visible_setup
    staged = stage_visible_cantilever(settings, live)
    with pytest.raises(RuntimeError, match="source deck is absent or has changed"):
        Path(staged["source_deck"]).write_text("not the fixed deck", encoding="ascii")
        import_visible_cantilever(
            settings, live, staged["run_id"], base.database,
            registry.session_nonce, "changed-source-0001",
        )
    assert base.imports == 0

    source = Path(staged["source_deck"])
    source.unlink()
    from ansa_mcp.cantilever_demo import _write_model
    _write_model(source)
    with pytest.raises(RuntimeError, match="SESSION_CHANGED"):
        import_visible_cantilever(
            settings, live, staged["run_id"], base.database,
            "0" * 32, "changed-session-0001",
        )
    assert base.imports == 0


def test_visible_export_rejects_other_run(visible_setup):
    settings, live, registry, base, _ = visible_setup
    first = stage_visible_cantilever(settings, live)
    second = stage_visible_cantilever(settings, live)
    import_visible_cantilever(
        settings, live, first["run_id"], base.database,
        registry.session_nonce, "first-run-import-001",
    )
    (Path(second["run_directory"]) / "live_import.json").write_text(
        json.dumps({"imported": True}), encoding="utf-8"
    )
    with pytest.raises(RuntimeError, match="did not import that run"):
        export_visible_cantilever(
            settings, live, second["run_id"], base.database,
            registry.session_nonce, "second-run-export-01",
        )
    assert base.exports == 0
