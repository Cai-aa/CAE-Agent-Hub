from __future__ import annotations

import sys
import tempfile
import types
import unittest
from pathlib import Path


EXTENSION_ROOT = Path(__file__).resolve().parents[1] / "hyperworks_extension"
sys.path.insert(0, str(EXTENSION_ROOT))

from hyperworks_mcp_extension.handlers import HandlerRegistry  # noqa: E402


class _Entity:
    def __init__(self, model, entity_id):
        self.id = entity_id
        self.name = f"entity-{entity_id}"
        self.cardimage = "TEST"


class Node(_Entity):
    def __init__(self, model, entity_id):
        super().__init__(model, entity_id)
        self.x = float(entity_id)
        self.y = 0.0
        self.z = 0.0


class Element(_Entity):
    def __init__(self, model, entity_id):
        super().__init__(model, entity_id)
        self.config = 104
        self.type = 1


class _Generic(_Entity):
    pass


class _ReturnStatus:
    def __init__(self, ok=True, message=""):
        self.status = 0 if ok else 1
        self.message = message
        self.ok = ok

    def __bool__(self):
        return self.ok


class _QueryResult:
    def __init__(self, **values):
        self.values = values

    @property
    def keys(self):
        return list(self.values)

    def __getitem__(self, key):
        return self.values[key]


class HmQueryResultList(list):
    pass


class _Session:
    def get_current_model(self):
        return "Model-1"

    def get_all_models(self):
        return ["Model-1"]

    def model_exists(self, name):
        return name == "Model-1"


class _Model:
    database = {
        Node: [Node(None, 1), Node(None, 2)],
        Element: [Element(None, 10)],
    }

    def __init__(self, name=None):
        self.name = name or "Model-1"

    def hm_getsolver(self):
        return "OptiStruct"

    def hm_gettotalmass(self):
        return [12.5]

    def hm_gettotalcog(self):
        return [1.0, 2.0, 3.0]

    def hm_getcurrentview(self):
        return [1.0] * 16

    def hm_getexistingentitytypes(self):
        return ["nodes", "elements"]

    def hm_getusermark(self, entity_type):
        return [1, 2]

    def writefile(self, filename, do_not_write_facets):
        Path(filename).write_text("fake hm", encoding="utf-8")

    def hm_answernext(self, answer):
        return answer


def _Collection(model, entity_class):
    return list(_Model.database.get(entity_class, []))


def _interactive(model, entity_class, message, highlight):
    return _Collection(model, entity_class)


class ExtensionHandlerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.old_hm = sys.modules.get("hm")
        self.old_entities = sys.modules.get("hm.entities")
        hm = types.ModuleType("hm")
        entities = types.ModuleType("hm.entities")
        hm.Session = _Session
        hm.Model = _Model
        hm.Collection = _Collection
        hm.CollectionByInteractiveSelection = _interactive
        for name in (
            "Component",
            "Material",
            "Property",
            "Loadcol",
            "Loadstep",
            "Set",
            "Surface",
            "Solid",
            "Point",
            "Line",
            "System",
            "Connector",
            "Assembly",
        ):
            setattr(entities, name, type(name, (_Generic,), {}))
        entities.Node = Node
        entities.Element = Element
        hm.entities = entities
        sys.modules["hm"] = hm
        sys.modules["hm.entities"] = entities

    def tearDown(self) -> None:
        if self.old_hm is None:
            sys.modules.pop("hm", None)
        else:
            sys.modules["hm"] = self.old_hm
        if self.old_entities is None:
            sys.modules.pop("hm.entities", None)
        else:
            sys.modules["hm.entities"] = self.old_entities

    def test_session_summary_and_entity_listing(self) -> None:
        registry = HandlerRegistry([])
        self.assertEqual(registry.get_session_info()["current_model"], "Model-1")
        summary = registry.get_model_summary(entity_types=["node", "element"])
        self.assertEqual(summary["counts"], {"node": 2, "element": 1})
        listed = registry.list_entities("node", limit=1)
        self.assertEqual(listed["total"], 2)
        self.assertEqual(listed["entities"][0]["x"], 1.0)

    def test_attribute_update_and_interactive_selection(self) -> None:
        registry = HandlerRegistry([])
        updated = registry.set_entity_attributes("node", 1, {"x": 9.0})
        self.assertEqual(updated["after"]["x"], 9.0)
        selected = registry.interactive_select("element")
        self.assertEqual(selected["ids"], [10])

    def test_model_metrics_unwraps_hypermesh_query_results(self) -> None:
        registry = HandlerRegistry([])
        model = _Model()
        model.hm_getsolver = lambda: (
            _ReturnStatus(),
            _QueryResult(value="Radioss"),
        )
        model.hm_gettotalmass = lambda: (
            _ReturnStatus(),
            _QueryResult(value=12.5),
        )
        model.hm_gettotalcog = lambda: (
            _ReturnStatus(),
            _QueryResult(x=1.0, y=2.0, z=3.0),
        )
        model.hm_getcurrentview = lambda: (
            _ReturnStatus(),
            _QueryResult(values=HmQueryResultList([1.0, 2.0])),
        )
        model.hm_getexistingentitytypes = lambda: (
            _ReturnStatus(),
            _QueryResult(values=HmQueryResultList(["nodes", "elements"])),
        )
        registry._model = lambda model_name=None: model

        metrics = registry.get_model_metrics()

        self.assertEqual(metrics["values"]["solver"], "Radioss")
        self.assertEqual(metrics["values"]["total_mass"], 12.5)
        self.assertEqual(
            metrics["values"]["center_of_gravity"],
            {"x": 1.0, "y": 2.0, "z": 3.0},
        )
        self.assertEqual(metrics["values"]["current_view"], [1.0, 2.0])
        self.assertEqual(
            metrics["values"]["existing_entity_types"],
            ["nodes", "elements"],
        )

    def test_save_is_restricted_to_configured_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "allowed"
            root.mkdir()
            registry = HandlerRegistry([str(root)])
            result = registry.save_model(str(root / "model.hm"))
            self.assertTrue(Path(result["output_file"]).is_file())
            with self.assertRaisesRegex(ValueError, "outside"):
                registry.save_model(str(Path(tmp) / "outside.hm"))


if __name__ == "__main__":
    unittest.main()
