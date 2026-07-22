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
    def __init__(self, model, entity_id=None, **kwargs):
        self.id = int(entity_id) if entity_id is not None else 1
        self.name = kwargs.pop("name", f"entity-{self.id}")
        self.cardimage = kwargs.pop("cardimage", "TEST")
        for name, value in kwargs.items():
            setattr(self, name, value)


class Node(_Entity):
    def __init__(self, model, entity_id=None, **kwargs):
        if entity_id is None:
            entity_id = max((item.id for item in _Model.database.get(Node, [])), default=0) + 1
        super().__init__(model, entity_id, **kwargs)
        self.x = float(kwargs.get("x", entity_id))
        self.y = float(kwargs.get("y", 0.0))
        self.z = float(kwargs.get("z", 0.0))
        if model is not None and not any(
            item.id == self.id for item in _Model.database.get(Node, [])
        ):
            _Model.database.setdefault(Node, []).append(self)


class Element(_Entity):
    def __init__(self, model, entity_id=None, **kwargs):
        super().__init__(model, entity_id, **kwargs)
        self.config = int(kwargs.get("config", 104))
        self.type = int(kwargs.get("type", 1))
        self.volume = float(kwargs.get("volume", 1.0))
        self.jacobian = float(kwargs.get("jacobian", 0.9))
        self.aspect = float(kwargs.get("aspect", 1.2))
        self.skew = float(kwargs.get("skew", 0.1))


class _Generic(_Entity):
    def __init__(self, model, entity_id=None, **kwargs):
        entity_class = self.__class__
        if entity_id is None:
            entity_id = max(
                (item.id for item in _Model.database.get(entity_class, [])), default=0
            ) + 1
        super().__init__(model, entity_id, **kwargs)
        if model is not None and not any(
            item.id == self.id for item in _Model.database.get(entity_class, [])
        ):
            _Model.database.setdefault(entity_class, []).append(self)


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

    def createelement(self, config, type, entitylist, auto_order):
        entity_id = max(
            (item.id for item in self.database.get(Element, [])), default=0
        ) + 1
        element = Element(self, entity_id, config=config, type=type)
        element.node_ids = [item.id for item in entitylist]
        element.auto_order = auto_order
        self.database.setdefault(Element, []).append(element)
        return {"status": "ok"}

    def _add_connection_element(self, config):
        entity_id = max(
            (item.id for item in self.database.get(Element, [])), default=0
        ) + 1
        element = Element(self, entity_id, config=config)
        self.database.setdefault(Element, []).append(element)
        return element

    def rigidlink(self, independent, collection, dofs):
        element = self._add_connection_element(55)
        element.independent_node_id = independent.id
        element.dependent_node_ids = [node.id for node in collection]
        element.dofs = dofs
        return {"status": "ok"}

    def rbe3(
        self,
        collection,
        independent_dofs,
        independent_weights,
        dependent_node,
        dof,
        weight,
    ):
        if dependent_node is None:
            nodes = list(collection)
            dependent_node = Node(
                self,
                x=sum(node.x for node in nodes) / len(nodes),
                y=sum(node.y for node in nodes) / len(nodes),
                z=sum(node.z for node in nodes) / len(nodes),
            )
        element = self._add_connection_element(56)
        element.dependent_node_id = dependent_node.id
        element.independent_node_ids = [node.id for node in collection]
        return {"status": "ok"}

    def weld(self, independent, dependent, length, systems, movenode):
        element = self._add_connection_element(5)
        element.node_ids = [independent.id, dependent.id]
        element.length = length
        element.systems = systems
        element.movenode = movenode
        return {"status": "ok"}

    def createspotweld(
        self, independent, dependent, length_given, length, systems,
        movenode, remesh, configval, property,
    ):
        element = self._add_connection_element(configval)
        element.node_ids = [independent.id, dependent.id]
        element.property_name = property
        return {"status": "ok"}

    def CE_ConnectorCreateByList(self, **kwargs):
        connector_class = sys.modules["hm.entities"].Connector
        connector = connector_class(self)
        connector.style = kwargs["ce_style"]
        connector.location_ids = [item.id for item in kwargs["entitylist"]]
        connector.link_ids = [item.id for item in kwargs["link_collection"]]
        self.last_connector = kwargs
        return {"status": "ok"}

    def currentcollector(self, entity_type, name):
        self.current_collector = (entity_type, name)
        return {"status": "ok"}

    def loadcreateonentity(self, **kwargs):
        load_class = sys.modules["hm.entities"].Load
        load_class(self, **kwargs)
        self.last_nodal_load = kwargs
        return {"status": "ok"}

    def pressuresonentity(self, **kwargs):
        self.last_pressure = kwargs
        return {"status": "ok"}

    def solidblock(self, **kwargs):
        solid_class = sys.modules["hm.entities"].Solid
        solid_class(self)
        self.last_solidblock = kwargs
        return {"status": "ok"}

    def solidcone(self, **kwargs):
        solid_class = sys.modules["hm.entities"].Solid
        solid_class(self)
        self.last_solidcone = kwargs
        return {"status": "ok"}

    def geomimport(self, translator_type, input_file_name, options):
        entities = sys.modules["hm.entities"]
        entities.Component(self)
        entities.Surface(self)
        entities.Solid(self)
        self.last_geomimport = (translator_type, input_file_name, options)
        return {"status": "ok"}

    def defaultmeshsurf_growth(self, **kwargs):
        entity_id = max(
            (item.id for item in self.database.get(Element, [])), default=0
        ) + 1
        self.database.setdefault(Element, []).append(Element(self, entity_id, config=104))
        self.last_automesh = kwargs
        return {"status": "ok"}

    def solidmap_solids_begin3(self, **kwargs):
        self.last_solidmap_begin3 = kwargs

    def solidmap_solids_begin(self, **kwargs):
        self.last_solidmap_begin = kwargs

    def solidmap_solids_end(self):
        entity_id = max(
            (item.id for item in self.database.get(Element, [])), default=0
        ) + 1
        self.database.setdefault(Element, []).append(
            Element(self, entity_id, config=208, volume=2.0)
        )
        return {"status": "ok"}

    def tetmesh(self, **kwargs):
        for _ in range(4):
            entity_id = max(
                (item.id for item in self.database.get(Element, [])), default=0
            ) + 1
            self.database.setdefault(Element, []).append(
                Element(self, entity_id, config=204, volume=0.5)
            )
        self.last_tetmesh = kwargs
        return {"status": "ok"}

    def element_smooth_nodes(self, **kwargs):
        for element in kwargs["elementsCollection"]:
            element.aspect = max(1.0, element.aspect * 0.8)
        self.last_smoothing = kwargs
        return {"status": "ok"}

    def elementqualityshutdown(self, dontsaveflag):
        return {"status": "ok", "dontsaveflag": dontsaveflag}

    def readfile(self, filename, load_cad_geometry_as_graphics):
        self.loaded_file = filename
        self.load_cad_geometry_as_graphics = load_cad_geometry_as_graphics
        return {"status": "ok"}

    def writefile(self, filename, do_not_write_facets):
        Path(filename).write_text("fake hm", encoding="utf-8")

    def hm_answernext(self, answer):
        return answer


def _Collection(model, entity_class, ids=None, populate=True):
    values = list(_Model.database.get(entity_class, []))
    if ids is not None:
        wanted = {int(value) for value in ids}
        values = [item for item in values if item.id in wanted]
    return values


def _interactive(model, entity_class, message, highlight):
    return _Collection(model, entity_class)


class ExtensionHandlerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.old_hm = sys.modules.get("hm")
        self.old_entities = sys.modules.get("hm.entities")
        self.old_hw = sys.modules.get("hw")
        self.old_hv = sys.modules.get("hw.hv")
        _Model.database = {
            Node: [Node(None, 1), Node(None, 2)],
            Element: [Element(None, 10)],
        }
        hm = types.ModuleType("hm")
        entities = types.ModuleType("hm.entities")
        hw = types.ModuleType("hw")
        hw.commands = []
        hw.evalTcl = lambda command: hw.commands.append(command)
        hm.Session = _Session
        hm.Model = _Model
        hm.Collection = _Collection
        hm.CollectionByInteractiveSelection = _interactive
        generated = {}
        for name in (
            "Component",
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
            "Constraint",
            "Contactbehavior",
            "Contactgroup",
            "Contactsurf",
            "Group",
            "Load",
        ):
            generated[name] = type(name, (_Generic,), {})
            setattr(entities, name, generated[name])
        entities.Material = type("Material", (_Generic,), {})
        entities.Node = Node
        entities.Element = Element
        hm.entities = entities
        sys.modules["hm"] = hm
        sys.modules["hm.entities"] = entities
        sys.modules["hw"] = hw

    def tearDown(self) -> None:
        if self.old_hm is None:
            sys.modules.pop("hm", None)
        else:
            sys.modules["hm"] = self.old_hm
        if self.old_entities is None:
            sys.modules.pop("hm.entities", None)
        else:
            sys.modules["hm.entities"] = self.old_entities
        if self.old_hw is None:
            sys.modules.pop("hw", None)
        else:
            sys.modules["hw"] = self.old_hw
        if self.old_hv is None:
            sys.modules.pop("hw.hv", None)
        else:
            sys.modules["hw.hv"] = self.old_hv

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

    def test_controlled_live_creation_and_refresh(self) -> None:
        registry = HandlerRegistry([])
        nodes = registry.create_nodes([[1.5, 2.5, 3.5], [4.0, 5.0, 6.0]])
        self.assertEqual(nodes["ids"], [3, 4])
        elements = registry.create_elements([[1, 2, 3, 4]], config=104)
        self.assertEqual(elements["ids"], [11])
        material = registry.create_material(
            "Steel", cardimage="MAT1", values={"E": 210000.0, "Nu": 0.3}
        )
        self.assertEqual(material["material"]["name"], "Steel")
        self.assertEqual(material["material"]["E"], 210000.0)
        refreshed = registry.refresh_view(fit=True)
        self.assertEqual(refreshed["commands"], ["hm_viewfit", "hm_redraw"])

    def test_creation_validation_and_controlled_model_load(self) -> None:
        registry = HandlerRegistry([])
        with self.assertRaisesRegex(ValueError, "finite"):
            registry.create_nodes([[float("nan"), 0.0, 0.0]])
        with self.assertRaisesRegex(ValueError, "do not exist"):
            registry.create_elements([[1, 999]], config=100)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "allowed"
            root.mkdir()
            model_file = root / "source.hm"
            model_file.write_text("fake hm", encoding="utf-8")
            registry = HandlerRegistry([str(root)])
            with self.assertRaisesRegex(ValueError, "replace_current=true"):
                registry.load_model(str(model_file))
            loaded = registry.load_model(str(model_file), replace_current=True)
            self.assertTrue(loaded["loaded"])

    def test_save_is_restricted_to_configured_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "allowed"
            root.mkdir()
            registry = HandlerRegistry([str(root)])
            result = registry.save_model(str(root / "model.hm"))
            self.assertTrue(Path(result["output_file"]).is_file())
            with self.assertRaisesRegex(ValueError, "outside"):
                registry.save_model(str(Path(tmp) / "outside.hm"))

    def test_geometry_cad_and_native_meshing_are_checkpointed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "allowed"
            root.mkdir()
            cad = root / "part.step"
            cad.write_text("fake step", encoding="utf-8")
            registry = HandlerRegistry([str(root)])

            block = registry.create_solid_block([0, 0, 0], [10, 20, 30])
            self.assertEqual(block["primitive"], "block")
            cylinder = registry.create_solid_cylinder([0, 0, 0], [1, 0, 0], 5, 20)
            self.assertEqual(cylinder["primitive"], "cylinder")
            imported = registry.import_cad(str(cad))
            self.assertEqual(imported["translator"], "step_ct")
            self.assertTrue(imported["surface_ids"])

            surface_mesh = registry.automesh_surfaces(
                imported["surface_ids"], element_size=2.0
            )
            self.assertEqual(surface_mesh["element_count"], 1)
            solid_mesh = registry.solid_map_mesh(
                imported["solid_ids"], element_size=2.0, element_type="quad"
            )
            self.assertEqual(solid_mesh["element_count"], 1)
            self.assertTrue(Path(block["checkpoint"]["checkpoint_file"]).is_file())

    def test_cylindrical_ogrid_quality_and_rollback_guard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "allowed"
            root.mkdir()
            registry = HandlerRegistry([str(root)])
            result = registry.create_cylindrical_ogrid(
                base_center=[0, 0, 0],
                axis=[1, 0, 0],
                length=10,
                radius=5,
                axial_divisions=1,
                circumferential_divisions=8,
                radial_layers=1,
                refresh=False,
            )
            self.assertEqual(result["node_count"], 34)
            self.assertEqual(result["penta6_count"], 8)
            self.assertEqual(result["hex8_count"], 8)
            self.assertEqual(result["quality"]["non_positive_volume_element_ids"], [])
            checkpoint = registry.create_checkpoint("manual test")
            with self.assertRaisesRegex(ValueError, "confirm=true"):
                registry.rollback_checkpoint(checkpoint["checkpoint_file"])
            rolled_back = registry.rollback_checkpoint(
                checkpoint["checkpoint_file"], confirm=True
            )
            self.assertTrue(rolled_back["rolled_back"])

    def test_new_modeling_validation_rejects_unsafe_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "allowed"
            root.mkdir()
            cad = root / "part.step"
            cad.write_text("fake step", encoding="utf-8")
            registry = HandlerRegistry([str(root)])
            with self.assertRaisesRegex(ValueError, "Invalid CAD import option"):
                registry.import_cad(str(cad), options=["foo=bar;bad"])
            with self.assertRaisesRegex(ValueError, "multiple of 4"):
                registry.create_cylindrical_ogrid(
                    [0, 0, 0], [1, 0, 0], 10, 5,
                    circumferential_divisions=10,
                )

    def test_connection_audit_and_checkpointed_creation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "allowed"
            root.mkdir()
            registry = HandlerRegistry([str(root)])
            registry.create_nodes(
                [[0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]]
            )

            audit = registry.get_connection_capabilities()
            self.assertEqual(audit["solver"], "OptiStruct")
            self.assertTrue(audit["exposed_operations"]["rbe3"])
            self.assertFalse(
                audit["audited_not_exposed"]["fastener"][
                    "active_solver_appears_supported"
                ]
            )
            safety = registry.get_safety_airbag_capabilities()
            self.assertEqual(safety["exposure_state"], "audit_only")
            self.assertEqual(safety["solver"], "OptiStruct")
            self.assertIn("airbag_folding", safety["required_validation_fixtures"])

            rigid = registry.create_rigid_link(1, [2, 3], refresh=False)
            self.assertEqual(rigid["connection_type"], "rigid_link")
            self.assertTrue(rigid["element_ids"])

            rbe3 = registry.create_rbe3([3, 4, 5, 6], refresh=False)
            self.assertEqual(rbe3["connection_type"], "rbe3")
            self.assertEqual(len(rbe3["auto_created_dependent_node_ids"]), 1)

            weld = registry.create_weld(1, 2, length=2.5, refresh=False)
            self.assertEqual(weld["connection_type"], "weld")
            self.assertTrue(weld["element_ids"])
            self.assertTrue(
                Path(weld["checkpoint"]["checkpoint_file"]).is_file()
            )

    def test_connection_validation_rejects_invalid_topology(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "allowed"
            root.mkdir()
            registry = HandlerRegistry([str(root)])
            with self.assertRaisesRegex(ValueError, "unique DOF"):
                registry.create_rigid_link(1, [2], dofs=112)
            with self.assertRaisesRegex(ValueError, "must not also"):
                registry.create_rigid_link(1, [1, 2])
            with self.assertRaisesRegex(ValueError, "six boolean"):
                registry.create_rbe3([1, 2], dependent_dofs=[True, False])
            with self.assertRaisesRegex(ValueError, "must be different"):
                registry.create_weld(1, 1)

    def test_solver_cards_loads_loadstep_and_spot_weld_are_checkpointed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            registry = HandlerRegistry([tmp])
            loadcol = registry.create_solver_card_entity(
                "loadcol", "FORCE", values={"color": 4}
            )
            loadcol_id = loadcol["entity"]["id"]
            prop = registry.create_solver_card_entity(
                "property", "PWELD", cardimage="PWELD", values={"D": 5.0}
            )
            force = registry.create_nodal_load(
                [1, 2], "force", [10.0, 0.0, 0.0], loadcol_id=loadcol_id
            )
            step = registry.create_loadstep(
                "STEP", "OS_TYPE", 1, load_attribute="OS_LOADID",
                loadcol_id=loadcol_id
            )
            weld = registry.create_spot_weld(
                1, 2, 21, "PWELD", refresh=False
            )
        self.assertEqual(prop["entity"]["name"], "PWELD")
        self.assertEqual(force["load_kind"], "force")
        self.assertEqual(step["entity_type"], "loadstep")
        self.assertTrue(weld["element_ids"])

    def test_connector_intent_is_created_but_not_claimed_as_realized(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            registry = HandlerRegistry([tmp])
            line_class = sys.modules["hm.entities"].Line
            component_class = sys.modules["hm.entities"].Component
            line = line_class(_Model())
            first_component = component_class(_Model())
            second_component = component_class(_Model())
            connector = registry.create_connector(
                "line",
                [line.id],
                "seam",
                "component",
                [first_component.id, second_component.id],
                num_links=2,
                tolerance=5.0,
                refresh=False,
            )
        self.assertTrue(connector["connector_ids"])
        self.assertFalse(connector["realized"])
        self.assertEqual(connector["style"], "seam")

    def test_connector_validation_rejects_unsupported_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            registry = HandlerRegistry([tmp])
            with self.assertRaisesRegex(ValueError, "node.*line"):
                registry.create_connector(
                    "element", [10], "spot", "component", [1], refresh=False
                )

    def test_tetra_mesh_and_quality_repair_return_before_after_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            registry = HandlerRegistry([tmp])
            solid_class = sys.modules["hm.entities"].Solid
            solid = solid_class(_Model())
            meshed = registry.tetra_mesh_solids(
                [solid.id], element_size=2.0, refresh=False
            )
            repaired = registry.repair_mesh_quality(
                meshed["element_ids"], iterations=2, refresh=False
            )
        self.assertEqual(meshed["method"], "native_tetmesh")
        self.assertEqual(meshed["element_count"], 4)
        self.assertTrue(repaired["repaired"])
        self.assertIn("quality_before", repaired)
        self.assertIn("quality_after", repaired)

    def test_hyperview_postprocess_returns_evidence_and_unpacks_query(self) -> None:
        class Page:
            def __init__(self, layout=1, title=""):
                self.layout = layout
                self.title = title
                self.id = 2

        class Window:
            def addModelAndResult(self, model, result):
                self.loaded = (model, result)

            def fit(self):
                pass

            def draw(self):
                pass

        class HVModel:
            pass

        class Result:
            def __init__(self):
                self.subcase = 1
                self.simulation = 1

            def getSubcaseIds(self):
                return [1]

            def getSubcaseLabels(self):
                return ["Linear Static"]

            def getDataTypes(self, subcase):
                return ["Displacement", "Stress"]

            def getDataComponents(self, data_type, subcase):
                return ["Mag", "X", "Y", "Z"]

            def getSimulationIds(self, subcase):
                return [1]

            def plot(self, scalar, waitTillLoaded=False):
                self.scalar = scalar

        class LegendScalar:
            minValue = 0.0
            maxValue = 1.25

        class Entity:
            pass

        class Collection:
            def __init__(self, entity_type, model=None):
                self.entity_type = entity_type

            def getSize(self):
                return 3

        class QueryResultsTool:
            def __init__(self, **kwargs):
                self.collection = None

            def setDataSourceQuery(self, query):
                self.source = query

            def getDataSourceQuery(self):
                return self.source

            def query(self):
                return [[1, 0.25], [2, 1.25], [3, 0.5], [4, float("nan")]]

        class ResultDefinitionScalar:
            def __init__(self, **kwargs):
                self.values = kwargs

        window = Window()
        result = Result()
        legend = LegendScalar()
        model = HVModel()

        class Session:
            def setActive(self, tag, page=None):
                self.page = page

            def get(self, tag, **kwargs):
                return {
                    Window: window,
                    Result: result,
                    LegendScalar: legend,
                    HVModel: model,
                }[tag]

        class CaptureImageTool:
            def __init__(self, **kwargs):
                self.file = None

            def capture(self):
                Path(self.file).write_bytes(b"fake png")

        hw = types.ModuleType("hw")
        hv = types.ModuleType("hw.hv")
        hw.Page = Page
        hw.Window = Window
        hw.Session = Session
        hw.CaptureImageTool = CaptureImageTool
        hw.hv = hv
        hv.Result = Result
        hv.LegendScalar = LegendScalar
        hv.Model = HVModel
        hv.Node = Entity
        hv.Element = Entity
        hv.Collection = Collection
        hv.QueryResultsTool = QueryResultsTool
        hv.ResultDefinitionScalar = ResultDefinitionScalar
        sys.modules["hw"] = hw
        sys.modules["hw.hv"] = hv

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model_file = root / "case.fem"
            result_file = root / "case.h3d"
            image_file = root / "output" / "displacement.png"
            model_file.write_text("deck", encoding="utf-8")
            result_file.write_bytes(b"h3d")
            registry = HandlerRegistry([str(root)])
            post = registry.postprocess_hyperview_result(
                str(model_file), str(result_file), str(image_file),
                simulation="first", average_mode="simple"
            )

        self.assertTrue(post["postprocessed"])
        self.assertEqual(post["bridge_version"], "0.9.1")
        self.assertEqual(post["legend"]["maximum"], 1.25)
        self.assertEqual(post["query"]["maximum_row"], [2, 1.25])
        self.assertEqual(post["query"]["minimum_row"], [1, 0.25])
        self.assertEqual(post["query"]["row_count"], 4)
        self.assertEqual(post["selected_simulation"], 1)
        self.assertEqual(post["contour"]["average_mode"], "simple")
        self.assertEqual(result.scalar.averageMode, "simple")
        self.assertGreater(post["screenshot"]["size_bytes"], 0)


if __name__ == "__main__":
    unittest.main()
