from __future__ import annotations

import csv
import platform
import math
import re
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any


BRIDGE_VERSION = "0.9.1"
MAX_NODES_PER_CALL = 5000
MAX_ELEMENTS_PER_CALL = 5000
MAX_ELEMENT_NODES = 20
MAX_GEOMETRY_IDS_PER_CALL = 10000
MAX_CAD_OPTIONS = 20

CAD_TRANSLATORS = {
    ".step": "step_ct",
    ".stp": "step_ct",
    ".iges": "iges_altair",
    ".igs": "iges_altair",
    ".x_t": "parasolid_parasolid",
    ".x_b": "parasolid_parasolid",
}
ALLOWED_CAD_TRANSLATORS = set(CAD_TRANSLATORS.values())
SURFACE_ELEMENT_TYPES = {
    "tria": 0,
    "quad": 1,
    "mixed": 2,
    "right_tria": 3,
    "quad_only": 4,
}
SURFACE_MESH_TYPES = {
    "proximity_curvature": 34,
    "curvature": 35,
    "proximity_curvature_free_edge": 36,
    "curvature_free_edge": 37,
}


ENTITY_CLASS_NAMES = {
    "node": "Node",
    "element": "Element",
    "component": "Component",
    "material": "Material",
    "property": "Property",
    "loadcol": "Loadcol",
    "loadstep": "Loadstep",
    "set": "Set",
    "surface": "Surface",
    "solid": "Solid",
    "point": "Point",
    "line": "Line",
    "system": "System",
    "connector": "Connector",
    "assembly": "Assembly",
    "constraint": "Constraint",
    "contactbehavior": "Contactbehavior",
    "contactgroup": "Contactgroup",
    "contactsurf": "Contactsurf",
    "group": "Group",
}

DEFAULT_ATTRIBUTES = {
    "node": ["id", "x", "y", "z"],
    "element": ["id", "config", "type"],
    "component": ["id", "name", "cardimage"],
    "material": ["id", "name", "cardimage"],
    "property": ["id", "name", "cardimage"],
    "loadcol": ["id", "name", "cardimage"],
    "loadstep": ["id", "name"],
    "set": ["id", "name", "cardimage"],
    "surface": ["id"],
    "solid": ["id"],
    "point": ["id", "x", "y", "z"],
    "line": ["id"],
    "system": ["id", "name"],
    "connector": ["id", "name"],
    "assembly": ["id", "name"],
    "constraint": ["id", "name", "cardimage"],
    "contactbehavior": ["id", "name", "cardimage"],
    "contactgroup": ["id", "name", "cardimage"],
    "contactsurf": ["id", "name", "cardimage"],
    "group": ["id", "name", "cardimage"],
}

SOLVER_CARD_ENTITY_TYPES = {
    "property",
    "loadcol",
    "loadstep",
    "set",
    "constraint",
    "contactbehavior",
    "contactgroup",
    "contactsurf",
    "group",
}

NODAL_LOAD_CONFIGS = {
    "force": 1,
    "moment": 2,
    "constraint": 3,
    "temperature": 5,
    "flux": 6,
    "velocity": 8,
    "acceleration": 9,
}


def _jsonable(value: Any, depth: int = 0) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if depth >= 4:
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item, depth + 1) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item, depth + 1) for item in value]
    keys = getattr(value, "keys", None)
    if keys is not None and not callable(keys):
        try:
            return {
                str(key): _jsonable(value[key], depth + 1)
                for key in list(keys)
            }
        except Exception:
            pass
    if value.__class__.__name__.endswith("QueryResultList"):
        try:
            return [_jsonable(item, depth + 1) for item in value]
        except Exception:
            pass
    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        try:
            return _jsonable(tolist(), depth + 1)
        except Exception:
            pass
    if hasattr(value, "id"):
        return {
            "entity_class": value.__class__.__name__,
            "id": _jsonable(getattr(value, "id"), depth + 1),
        }
    for method_name in ("as_dict", "to_dict"):
        method = getattr(value, method_name, None)
        if callable(method):
            try:
                return _jsonable(method(), depth + 1)
            except Exception:
                pass
    return str(value)


def _unwrap_hm_call(value: Any) -> Any:
    """Unwrap HyperMesh's ``(hwReturnStatus, HmQueryResult)`` convention."""
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return _jsonable(value)

    status, payload = value
    if not all(hasattr(status, name) for name in ("status", "message")):
        return _jsonable(value)

    try:
        succeeded = bool(status)
    except Exception:
        succeeded = int(getattr(status, "status", 1)) == 0
    if not succeeded:
        message = str(getattr(status, "message", "") or "HyperMesh query failed")
        raise RuntimeError(message)

    result = _jsonable(payload)
    if isinstance(result, dict) and len(result) == 1:
        key, item = next(iter(result.items()))
        if key.lower() in {"value", "values", "result"}:
            return item
    return result


class HandlerRegistry:
    def __init__(self, allowed_roots: list[str]):
        self.allowed_roots = [Path(item).resolve() for item in allowed_roots]
        self.methods = {
            "ping": self.ping,
            "get_capabilities": self.get_capabilities,
            "get_session_info": self.get_session_info,
            "get_model_summary": self.get_model_summary,
            "list_entities": self.list_entities,
            "get_entity": self.get_entity,
            "get_user_mark": self.get_user_mark,
            "interactive_select": self.interactive_select,
            "set_entity_attributes": self.set_entity_attributes,
            "create_nodes": self.create_nodes,
            "create_elements": self.create_elements,
            "create_material": self.create_material,
            "create_solver_card_entity": self.create_solver_card_entity,
            "create_nodal_load": self.create_nodal_load,
            "create_pressure_load": self.create_pressure_load,
            "create_loadstep": self.create_loadstep,
            "create_solid_block": self.create_solid_block,
            "create_solid_cylinder": self.create_solid_cylinder,
            "import_cad": self.import_cad,
            "automesh_surfaces": self.automesh_surfaces,
            "solid_map_mesh": self.solid_map_mesh,
            "tetra_mesh_solids": self.tetra_mesh_solids,
            "repair_mesh_quality": self.repair_mesh_quality,
            "create_cylindrical_ogrid": self.create_cylindrical_ogrid,
            "get_mesh_quality": self.get_mesh_quality,
            "get_connection_capabilities": self.get_connection_capabilities,
            "get_safety_airbag_capabilities": self.get_safety_airbag_capabilities,
            "create_rigid_link": self.create_rigid_link,
            "create_rbe3": self.create_rbe3,
            "create_weld": self.create_weld,
            "create_spot_weld": self.create_spot_weld,
            "create_connector": self.create_connector,
            "create_checkpoint": self.create_checkpoint,
            "rollback_checkpoint": self.rollback_checkpoint,
            "load_model": self.load_model,
            "refresh_view": self.refresh_view,
            "get_model_metrics": self.get_model_metrics,
            "postprocess_hyperview_result": self.postprocess_hyperview_result,
            "extract_hypergraph_time_history": self.extract_hypergraph_time_history,
            "save_model": self.save_model,
        }

    @property
    def allowed_methods(self) -> list[str]:
        return sorted(self.methods)

    def dispatch(self, method: str, params: dict[str, Any]) -> Any:
        handler = self.methods.get(method)
        if handler is None:
            raise ValueError(f"Method is not allowlisted: {method}")
        return handler(**params)

    @staticmethod
    def _imports():
        import hm
        import hm.entities as ent

        return hm, ent

    def _model(self, model_name: str | None = None):
        hm, _ = self._imports()
        if model_name:
            session = hm.Session()
            if not session.model_exists(model_name):
                raise ValueError(f"HyperMesh model not found: {model_name}")
            return hm.Model(model_name)
        return hm.Model()

    def _entity_class(self, entity_type: str):
        _, ent = self._imports()
        key = entity_type.strip().lower()
        class_name = ENTITY_CLASS_NAMES.get(key)
        if not class_name:
            raise ValueError(
                "Unsupported entity_type. Allowed values: "
                + ", ".join(sorted(ENTITY_CLASS_NAMES))
            )
        entity_class = getattr(ent, class_name, None)
        if entity_class is None:
            raise RuntimeError(f"Entity class is unavailable in this client: {class_name}")
        return key, entity_class

    @staticmethod
    def _attributes(entity_type: str, attributes: list[str] | None) -> list[str]:
        requested = attributes or DEFAULT_ATTRIBUTES[entity_type]
        if len(requested) > 30:
            raise ValueError("At most 30 attributes may be requested")
        clean = []
        for name in requested:
            if not isinstance(name, str) or not name or name.startswith("_"):
                raise ValueError(f"Invalid attribute name: {name!r}")
            clean.append(name)
        if "id" not in clean:
            clean.insert(0, "id")
        return clean

    @staticmethod
    def _serialize_entity(entity: Any, attributes: list[str]) -> dict[str, Any]:
        result: dict[str, Any] = {"entity_class": entity.__class__.__name__}
        unavailable = []
        for name in attributes:
            try:
                result[name] = _jsonable(getattr(entity, name))
            except Exception:
                unavailable.append(name)
        if unavailable:
            result["unavailable_attributes"] = unavailable
        return result

    def ping(self) -> dict[str, Any]:
        return {
            "bridge": "hyperworks-mcp-extension",
            "version": BRIDGE_VERSION,
            "python": sys.version,
            "platform": platform.platform(),
            "execution_thread": threading.current_thread().name,
        }

    def get_capabilities(self) -> dict[str, Any]:
        modules = {}
        for name in ("hm", "hw", "hw.hv", "hw.hg", "report", "hwx.gui"):
            try:
                __import__(name)
                modules[name] = True
            except Exception as exc:
                modules[name] = False
                modules[name + "_error"] = str(exc)
        return {
            "modules": modules,
            "methods": self.allowed_methods,
            "entity_types": sorted(ENTITY_CLASS_NAMES),
            "save_roots": [str(path) for path in self.allowed_roots],
            "modeling_limits": {
                "nodes_per_call": MAX_NODES_PER_CALL,
                "elements_per_call": MAX_ELEMENTS_PER_CALL,
                "element_nodes": MAX_ELEMENT_NODES,
                "load_extensions": [".hm"],
                "cad_import_extensions": sorted(CAD_TRANSLATORS),
                "cad_translators": sorted(ALLOWED_CAD_TRANSLATORS),
                "geometry_ids_per_call": MAX_GEOMETRY_IDS_PER_CALL,
                "automatic_checkpoints": True,
                "solid_map": "native HyperMesh multi-solid solid map",
                "tetra_mesh": "native HyperMesh structural tetmesh with bounded sizing",
                "quality_repair": "checkpointed element smoothing with before/after metrics",
                "cylindrical_ogrid": "radial Hex8 rings with a Penta6 core",
                "connections": "checkpointed rigid links, RBE3 spiders, node welds, property-backed spot welds, and unrealized connector intent",
                "solver_cards": sorted(SOLVER_CARD_ENTITY_TYPES),
                "nodal_loads": sorted(NODAL_LOAD_CONFIGS),
                "time_history": "HyperView frame query to CSV and HyperGraph XY/PNG",
            },
        }

    def get_connection_capabilities(
        self, model_name: str | None = None
    ) -> dict[str, Any]:
        """Audit connection APIs exposed by the active embedded HyperMesh client."""
        model = self._model(model_name)
        solver = None
        solver_error = None
        try:
            solver = _unwrap_hm_call(model.hm_getsolver())
        except Exception as exc:
            solver_error = str(exc)

        method_names = (
            "rigidlink",
            "rbe3",
            "weld",
            "createspotweld",
            "CE_ConnectorCreateByList",
            "CE_ConnectorCreateByMark",
            "CE_FE_RealizeWithDetails",
            "fastenercreation",
        )
        methods = {
            name: callable(getattr(model, name, None)) for name in method_names
        }
        solver_name = solver.get("solver") if isinstance(solver, dict) else solver
        solver_text = str(solver_name or "").lower()
        return {
            "model_name": model_name,
            "solver": solver_name,
            "solver_error": solver_error,
            "methods": methods,
            "exposed_operations": {
                "rigid_link": methods["rigidlink"],
                "rbe3": methods["rbe3"],
                "node_weld": methods["weld"],
                "property_backed_spot_weld": methods["createspotweld"],
                "connector_intent": methods["CE_ConnectorCreateByList"],
            },
            "audited_not_exposed": {
                "generic_connector_realization": (
                    "Connector intent creation is exposed; FE realization still requires "
                    "explicit solver-profile config, FE type, property, and controls."
                ),
                "fastener": {
                    "api_available": methods["fastenercreation"],
                    "supported_profile": "Abaqus",
                    "active_solver_appears_supported": "abaqus" in solver_text,
                },
            },
        }

    def get_safety_airbag_capabilities(
        self, model_name: str | None = None
    ) -> dict[str, Any]:
        """Audit safety-domain APIs without entering GUI contexts or changing the model."""
        model = self._model(model_name)
        try:
            raw_solver = _unwrap_hm_call(model.hm_getsolver())
            solver = raw_solver.get("solver") if isinstance(raw_solver, dict) else raw_solver
            solver_error = None
        except Exception as exc:
            solver = None
            solver_error = str(exc)
        exact_signature_methods = (
            "positiondummy",
            "rotatedummy",
            "relativerotatedummyjoint",
            "absoluterotatedummyjoint",
            "createseatbeltmesh",
            "createseatbelt",
            "create2dseatbeltwithmeshelementsize",
            "createairbag",
            "updateairbag",
            "reviewairbag",
        )
        context_or_opaque_methods = (
            "seatbelttensioning",
            "createflattenfold",
            "createtuckfold",
            "createzigzagfold",
            "createrollfold",
            "createsimplefold",
            "createfoldingtable",
            "createinflatorinsertfold",
            "createtargetfold",
            "createairbagsequence",
            "realizeairbagsequence",
            "airbagfoldpreview",
        )
        exact = {
            name: callable(getattr(model, name, None)) for name in exact_signature_methods
        }
        context = {
            name: callable(getattr(model, name, None))
            for name in context_or_opaque_methods
        }
        return {
            "model_name": model_name,
            "solver": solver,
            "solver_error": solver_error,
            "exact_signature_methods": exact,
            "context_or_opaque_methods": context,
            "exposure_state": "audit_only",
            "required_validation_fixtures": {
                "dummy_positioning": (
                    "A supported dummy collector with joint metadata and target points."
                ),
                "seatbelt_creation": (
                    "Routing nodes, three plane definitions, mesh settings, and validated "
                    "1D/2D output collectors for the active solver profile."
                ),
                "airbag_folding": (
                    "A closed airbag shell model plus initialized hwctx selections/options; "
                    "folding Python wrappers expose opaque signatures in 2026."
                ),
                "airbag_stitching": (
                    "Ordered edge paths and an initialized crash GUI context; the installed "
                    "workflow calls hwctx GenerateSprings."
                ),
            },
            "safe_next_step": (
                "Validate one solver-specific fixture per workflow before opening any "
                "model-changing safety operation through MCP."
            ),
        }

    def get_session_info(self) -> dict[str, Any]:
        hm, _ = self._imports()
        session = hm.Session()
        return {
            "current_model": session.get_current_model(),
            "models": list(session.get_all_models()),
            "model_count": len(session.get_all_models()),
            "execution_thread": threading.current_thread().name,
        }

    def get_model_summary(
        self,
        model_name: str | None = None,
        entity_types: list[str] | None = None,
    ) -> dict[str, Any]:
        hm, _ = self._imports()
        model = self._model(model_name)
        requested = entity_types or [
            "node",
            "element",
            "component",
            "material",
            "property",
            "loadcol",
            "loadstep",
        ]
        counts = {}
        errors = {}
        for raw_type in requested:
            key, entity_class = self._entity_class(raw_type)
            try:
                counts[key] = len(hm.Collection(model, entity_class))
            except Exception as exc:
                errors[key] = str(exc)
        return {
            "model_name": model_name,
            "counts": counts,
            "count_errors": errors,
        }

    def list_entities(
        self,
        entity_type: str,
        model_name: str | None = None,
        offset: int = 0,
        limit: int = 100,
        attributes: list[str] | None = None,
    ) -> dict[str, Any]:
        hm, _ = self._imports()
        key, entity_class = self._entity_class(entity_type)
        offset = max(0, int(offset))
        limit = max(1, min(int(limit), 1000))
        attrs = self._attributes(key, attributes)
        collection = hm.Collection(self._model(model_name), entity_class)
        total = len(collection)
        items = []
        for index, entity in enumerate(collection):
            if index < offset:
                continue
            if len(items) >= limit:
                break
            items.append(self._serialize_entity(entity, attrs))
        return {
            "entity_type": key,
            "model_name": model_name,
            "offset": offset,
            "limit": limit,
            "total": total,
            "entities": items,
        }

    def get_entity(
        self,
        entity_type: str,
        entity_id: int,
        model_name: str | None = None,
        attributes: list[str] | None = None,
    ) -> dict[str, Any]:
        key, entity_class = self._entity_class(entity_type)
        entity = entity_class(self._model(model_name), int(entity_id))
        return self._serialize_entity(entity, self._attributes(key, attributes))

    def get_user_mark(
        self, entity_type: str, model_name: str | None = None
    ) -> dict[str, Any]:
        key, _ = self._entity_class(entity_type)
        value = self._model(model_name).hm_getusermark(entity_type=key)
        return {"entity_type": key, "result": _jsonable(value)}

    def interactive_select(
        self,
        entity_type: str,
        message: str = "Select entities for Codex",
        highlight: bool = True,
    ) -> dict[str, Any]:
        hm, _ = self._imports()
        key, entity_class = self._entity_class(entity_type)
        model = self._model(None)
        collection = hm.CollectionByInteractiveSelection(
            model, entity_class, message=str(message)[:200], highlight=bool(highlight)
        )
        ids = [int(entity.id) for entity in collection]
        return {"entity_type": key, "ids": ids, "count": len(ids)}

    def set_entity_attributes(
        self,
        entity_type: str,
        entity_id: int,
        values: dict[str, Any],
        model_name: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(values, dict) or not values or len(values) > 20:
            raise ValueError("values must contain between 1 and 20 attributes")
        key, entity_class = self._entity_class(entity_type)
        entity = entity_class(self._model(model_name), int(entity_id))
        before = {}
        for name, value in values.items():
            if not isinstance(name, str) or name == "id" or name.startswith("_"):
                raise ValueError(f"Attribute cannot be modified: {name!r}")
            before[name] = _jsonable(getattr(entity, name))
            setattr(entity, name, value)
        after = {name: _jsonable(getattr(entity, name)) for name in values}
        return {
            "entity_type": key,
            "entity_id": int(entity_id),
            "before": before,
            "after": after,
        }

    def create_nodes(
        self,
        coordinates: list[list[float]],
        model_name: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(coordinates, list) or not coordinates:
            raise ValueError("coordinates must be a non-empty list of [x, y, z] triples")
        if len(coordinates) > MAX_NODES_PER_CALL:
            raise ValueError(f"At most {MAX_NODES_PER_CALL} nodes may be created per call")
        clean: list[tuple[float, float, float]] = []
        for index, point in enumerate(coordinates):
            if not isinstance(point, (list, tuple)) or len(point) != 3:
                raise ValueError(f"coordinates[{index}] must contain exactly three values")
            try:
                xyz = tuple(float(value) for value in point)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"coordinates[{index}] contains a non-numeric value") from exc
            if not all(math.isfinite(value) for value in xyz):
                raise ValueError(f"coordinates[{index}] must contain finite values")
            clean.append(xyz)

        _, ent = self._imports()
        model = self._model(model_name)
        created = [ent.Node(model, x=x, y=y, z=z) for x, y, z in clean]
        return {
            "created": True,
            "entity_type": "node",
            "model_name": model_name,
            "count": len(created),
            "ids": [int(node.id) for node in created],
            "nodes": [
                self._serialize_entity(node, ["id", "x", "y", "z"])
                for node in created
            ],
        }

    def create_elements(
        self,
        node_ids: list[list[int]],
        config: int,
        solver_type: int = 1,
        auto_order: bool = False,
        model_name: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(node_ids, list) or not node_ids:
            raise ValueError("node_ids must be a non-empty list of connectivity lists")
        if len(node_ids) > MAX_ELEMENTS_PER_CALL:
            raise ValueError(f"At most {MAX_ELEMENTS_PER_CALL} elements may be created per call")
        config = int(config)
        solver_type = int(solver_type)
        if config <= 0 or solver_type < 0:
            raise ValueError("config must be positive and solver_type must be non-negative")

        connectivities: list[list[int]] = []
        for index, connectivity in enumerate(node_ids):
            if not isinstance(connectivity, (list, tuple)):
                raise ValueError(f"node_ids[{index}] must be a list")
            if not 2 <= len(connectivity) <= MAX_ELEMENT_NODES:
                raise ValueError(
                    f"node_ids[{index}] must contain 2 to {MAX_ELEMENT_NODES} node IDs"
                )
            ids = [int(value) for value in connectivity]
            if any(value <= 0 for value in ids) or len(set(ids)) != len(ids):
                raise ValueError(f"node_ids[{index}] must contain unique positive node IDs")
            connectivities.append(ids)

        hm, ent = self._imports()
        model = self._model(model_name)
        existing_nodes = {int(node.id) for node in hm.Collection(model, ent.Node)}
        missing = sorted({value for ids in connectivities for value in ids} - existing_nodes)
        if missing:
            preview = missing[:20]
            suffix = "..." if len(missing) > len(preview) else ""
            raise ValueError(f"Referenced node IDs do not exist: {preview}{suffix}")

        before = {int(element.id) for element in hm.Collection(model, ent.Element)}
        call_results = []
        for connectivity in connectivities:
            nodes = [ent.Node(model, value) for value in connectivity]
            call_results.append(
                _unwrap_hm_call(
                    model.createelement(
                        config=config,
                        type=solver_type,
                        entitylist=nodes,
                        auto_order=1 if auto_order else 0,
                    )
                )
            )
        after = {int(element.id) for element in hm.Collection(model, ent.Element)}
        created_ids = sorted(after - before)
        if len(created_ids) != len(connectivities):
            raise RuntimeError(
                "HyperMesh completed element creation, but the created IDs could not be "
                f"identified reliably (expected {len(connectivities)}, found {len(created_ids)})"
            )
        return {
            "created": True,
            "entity_type": "element",
            "model_name": model_name,
            "count": len(created_ids),
            "ids": created_ids,
            "config": config,
            "solver_type": solver_type,
            "auto_order": bool(auto_order),
            "call_results": call_results,
        }

    def create_material(
        self,
        name: str,
        cardimage: str | None = None,
        values: dict[str, Any] | None = None,
        model_name: str | None = None,
    ) -> dict[str, Any]:
        name = str(name).strip()
        if not name or len(name) > 128:
            raise ValueError("name must contain between 1 and 128 characters")
        values = values or {}
        if not isinstance(values, dict) or len(values) > 30:
            raise ValueError("values must be an object containing at most 30 attributes")
        kwargs: dict[str, Any] = {"name": name}
        if cardimage is not None:
            cardimage = str(cardimage).strip()
            if not cardimage or len(cardimage) > 128:
                raise ValueError("cardimage must contain between 1 and 128 characters")
            kwargs["cardimage"] = cardimage
        for key, value in values.items():
            if (
                not isinstance(key, str)
                or not key
                or key.startswith("_")
                or key in {"id", "name", "cardimage"}
            ):
                raise ValueError(f"Material creation attribute is not allowed: {key!r}")
            kwargs[key] = value

        _, ent = self._imports()
        material = ent.Material(self._model(model_name), **kwargs)
        attributes = ["id", "name", "cardimage", *values.keys()]
        return {
            "created": True,
            "entity_type": "material",
            "model_name": model_name,
            "material": self._serialize_entity(material, attributes),
        }

    @staticmethod
    def _entity_kwargs(
        values: dict[str, Any] | None,
        reserved: set[str],
        maximum: int = 40,
    ) -> dict[str, Any]:
        values = values or {}
        if not isinstance(values, dict) or len(values) > maximum:
            raise ValueError(f"values must be an object containing at most {maximum} attributes")
        clean: dict[str, Any] = {}
        for key, value in values.items():
            if (
                not isinstance(key, str)
                or not key
                or key.startswith("_")
                or key in reserved
            ):
                raise ValueError(f"Entity creation attribute is not allowed: {key!r}")
            clean[key] = value
        return clean

    def create_solver_card_entity(
        self,
        entity_type: str,
        name: str,
        cardimage: str | None = None,
        values: dict[str, Any] | None = None,
        references: dict[str, dict[str, Any]] | None = None,
        model_name: str | None = None,
    ) -> dict[str, Any]:
        """Create one typed solver-card entity with explicit entity references."""
        key, entity_class = self._entity_class(entity_type)
        if key not in SOLVER_CARD_ENTITY_TYPES:
            raise ValueError(
                "entity_type must be one of: " + ", ".join(sorted(SOLVER_CARD_ENTITY_TYPES))
            )
        clean_name = str(name).strip()
        if not clean_name or len(clean_name) > 128:
            raise ValueError("name must contain between 1 and 128 characters")
        clean_values = self._entity_kwargs(values, {"id", "name", "cardimage"})
        references = references or {}
        if not isinstance(references, dict) or len(references) > 20:
            raise ValueError("references must contain at most 20 entity attributes")
        if set(clean_values).intersection(references):
            raise ValueError("An attribute cannot appear in both values and references")

        kwargs: dict[str, Any] = {"name": clean_name, **clean_values}
        if cardimage is not None:
            clean_card = str(cardimage).strip()
            if not clean_card or len(clean_card) > 128:
                raise ValueError("cardimage must contain between 1 and 128 characters")
            kwargs["cardimage"] = clean_card
        model = self._model(model_name)
        for attribute, spec in references.items():
            if not isinstance(attribute, str) or not attribute or attribute.startswith("_"):
                raise ValueError(f"Invalid reference attribute: {attribute!r}")
            if not isinstance(spec, dict):
                raise ValueError(f"references[{attribute!r}] must be an object")
            ref_key, ref_class = self._entity_class(str(spec.get("entity_type", "")))
            ref_id = int(spec.get("entity_id", 0))
            if ref_id <= 0:
                raise ValueError(f"references[{attribute!r}].entity_id must be positive")
            self._checked_collection(model, ref_key, [ref_id])
            kwargs[attribute] = ref_class(model, ref_id)

        checkpoint = self.create_checkpoint(f"before_{key}", model_name)
        try:
            entity = entity_class(model, **kwargs)
        except Exception as exc:
            self._rollback_after_failure(checkpoint, model_name, exc)
        attributes = ["id", "name", "cardimage", *clean_values, *references]
        return {
            "created": True,
            "entity_type": key,
            "model_name": model_name,
            "entity": self._serialize_entity(entity, attributes),
            "checkpoint": checkpoint,
        }

    def _set_current_loadcol(self, model: Any, ent: Any, loadcol_id: int | None) -> dict[str, Any] | None:
        if loadcol_id is None:
            return None
        clean_id = int(loadcol_id)
        self._checked_collection(model, "loadcol", [clean_id])
        loadcol = ent.Loadcol(model, clean_id)
        model.currentcollector(entity_type=ent.Loadcol, name=str(loadcol.name))
        return {"id": clean_id, "name": str(loadcol.name)}

    def create_nodal_load(
        self,
        node_ids: list[int],
        load_kind: str,
        components: list[float],
        solver_type: int = 1,
        loadcol_id: int | None = None,
        model_name: str | None = None,
    ) -> dict[str, Any]:
        """Create force, moment, SPC, temperature, flux, velocity, or acceleration loads."""
        kind = str(load_kind).strip().lower()
        if kind not in NODAL_LOAD_CONFIGS:
            raise ValueError("Unsupported load_kind: " + kind)
        expected = 6 if kind == "constraint" else 3
        if not isinstance(components, (list, tuple)) or len(components) != expected:
            raise ValueError(f"components must contain {expected} values for {kind}")
        clean_components = [float(value) for value in components]
        if not all(math.isfinite(value) for value in clean_components):
            raise ValueError("components must contain finite values")
        if kind == "constraint":
            # HyperMesh uses -999999.0 to mark an unconstrained DOF.
            clean_components = [
                -999999.0 if value == -999999.0 else value for value in clean_components
            ]
        else:
            clean_components.extend([0.0, 0.0, 0.0])
        hm, ent = self._imports()
        model = self._model(model_name)
        collection, clean_ids = self._checked_collection(model, "node", node_ids)
        current = self._set_current_loadcol(model, ent, loadcol_id)
        checkpoint = self.create_checkpoint(f"before_{kind}_load", model_name)
        load_class = getattr(ent, "Load", None)
        before = self._entity_ids(hm, model, load_class) if load_class is not None else set()
        try:
            result = _unwrap_hm_call(
                model.loadcreateonentity(
                    collection=collection,
                    config=NODAL_LOAD_CONFIGS[kind],
                    type=int(solver_type),
                    comp1=clean_components[0], comp2=clean_components[1],
                    comp3=clean_components[2], comp4=clean_components[3],
                    comp5=clean_components[4], comp6=clean_components[5],
                )
            )
            created_ids = (
                sorted(self._entity_ids(hm, model, load_class) - before)
                if load_class is not None else []
            )
        except Exception as exc:
            self._rollback_after_failure(checkpoint, model_name, exc)
        return {
            "created": True,
            "load_kind": kind,
            "node_ids": clean_ids,
            "components": clean_components[:expected],
            "solver_type": int(solver_type),
            "loadcol": current,
            "load_ids": created_ids,
            "checkpoint": checkpoint,
            "call_result": result,
        }

    def create_pressure_load(
        self,
        entity_type: str,
        entity_ids: list[int],
        magnitude: float,
        direction: list[float] | None = None,
        face_node_ids: list[int] | None = None,
        break_angle: float = 30.0,
        loadcol_id: int | None = None,
        model_name: str | None = None,
    ) -> dict[str, Any]:
        key = str(entity_type).strip().lower()
        if key not in {"surface", "element"}:
            raise ValueError("entity_type must be surface or element")
        pressure = self._nonnegative_float("magnitude", magnitude)
        vector = (0.0, 0.0, 0.0) if direction is None else self._finite_vector("direction", direction)
        angle = float(break_angle)
        if not math.isfinite(angle) or not 0.0 <= angle <= 180.0:
            raise ValueError("break_angle must be between 0 and 180 degrees")
        hm, ent = self._imports()
        model = self._model(model_name)
        collection, clean_ids = self._checked_collection(model, key, entity_ids)
        if face_node_ids:
            node_collection, clean_nodes = self._checked_collection(model, "node", face_node_ids)
        else:
            node_collection = hm.Collection(model, ent.Node, populate=False)
            clean_nodes = []
        current = self._set_current_loadcol(model, ent, loadcol_id)
        checkpoint = self.create_checkpoint("before_pressure_load", model_name)
        try:
            result = _unwrap_hm_call(
                model.pressuresonentity(
                    collection=collection,
                    nodes_collection=node_collection,
                    x=vector[0], y=vector[1], z=vector[2],
                    magnitude=pressure, breakangle=angle, onface=1,
                )
            )
        except Exception as exc:
            self._rollback_after_failure(checkpoint, model_name, exc)
        return {
            "created": True,
            "load_kind": "pressure",
            "entity_type": key,
            "entity_ids": clean_ids,
            "face_node_ids": clean_nodes,
            "magnitude": pressure,
            "direction": list(vector),
            "loadcol": current,
            "checkpoint": checkpoint,
            "call_result": result,
        }

    def create_loadstep(
        self,
        name: str,
        analysis_type_attribute: str,
        analysis_type: int | str,
        load_attribute: str | None = None,
        loadcol_id: int | None = None,
        spc_attribute: str | None = None,
        spc_loadcol_id: int | None = None,
        cardimage: str | None = None,
        values: dict[str, Any] | None = None,
        model_name: str | None = None,
    ) -> dict[str, Any]:
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,79}", str(analysis_type_attribute)):
            raise ValueError("Invalid analysis_type_attribute")
        clean_values = dict(values or {})
        clean_values[str(analysis_type_attribute)] = analysis_type
        references: dict[str, dict[str, Any]] = {}
        for attribute, entity_id in (
            (load_attribute, loadcol_id),
            (spc_attribute, spc_loadcol_id),
        ):
            if attribute is None and entity_id is None:
                continue
            if attribute is None or entity_id is None:
                raise ValueError("Load-step reference attribute and loadcol ID must be supplied together")
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,79}", str(attribute)):
                raise ValueError(f"Invalid load-step reference attribute: {attribute!r}")
            references[str(attribute)] = {"entity_type": "loadcol", "entity_id": int(entity_id)}
        return self.create_solver_card_entity(
            entity_type="loadstep",
            name=name,
            cardimage=cardimage,
            values=clean_values,
            references=references,
            model_name=model_name,
        )

    @staticmethod
    def _finite_vector(name: str, values: list[float], *, positive: bool = False) -> tuple[float, ...]:
        if not isinstance(values, (list, tuple)) or len(values) != 3:
            raise ValueError(f"{name} must contain exactly three numeric values")
        try:
            result = tuple(float(value) for value in values)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} contains a non-numeric value") from exc
        if not all(math.isfinite(value) for value in result):
            raise ValueError(f"{name} must contain finite values")
        if positive and not all(value > 0.0 for value in result):
            raise ValueError(f"{name} values must be positive")
        return result

    @staticmethod
    def _positive_float(name: str, value: float, maximum: float = 1.0e12) -> float:
        try:
            result = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} must be numeric") from exc
        if not math.isfinite(result) or not 0.0 < result <= maximum:
            raise ValueError(f"{name} must be finite and in the range (0, {maximum}]")
        return result

    @staticmethod
    def _unit_vector(values: list[float], name: str = "axis") -> tuple[float, float, float]:
        vector = HandlerRegistry._finite_vector(name, values)
        length = math.sqrt(sum(item * item for item in vector))
        if length <= 1.0e-12:
            raise ValueError(f"{name} must have non-zero length")
        return tuple(item / length for item in vector)

    @staticmethod
    def _cross(
        left: tuple[float, float, float], right: tuple[float, float, float]
    ) -> tuple[float, float, float]:
        return (
            left[1] * right[2] - left[2] * right[1],
            left[2] * right[0] - left[0] * right[2],
            left[0] * right[1] - left[1] * right[0],
        )

    @staticmethod
    def _entity_ids(hm: Any, model: Any, entity_class: Any) -> set[int]:
        return {int(entity.id) for entity in hm.Collection(model, entity_class)}

    def _checked_collection(
        self, model: Any, entity_type: str, ids: list[int]
    ) -> tuple[Any, list[int]]:
        hm, _ = self._imports()
        key, entity_class = self._entity_class(entity_type)
        if not isinstance(ids, list) or not ids:
            raise ValueError(f"{key}_ids must be a non-empty list")
        if len(ids) > MAX_GEOMETRY_IDS_PER_CALL:
            raise ValueError(
                f"At most {MAX_GEOMETRY_IDS_PER_CALL} {key} IDs may be used per call"
            )
        clean = [int(value) for value in ids]
        if any(value <= 0 for value in clean) or len(set(clean)) != len(clean):
            raise ValueError(f"{key}_ids must contain unique positive IDs")
        existing = self._entity_ids(hm, model, entity_class)
        missing = sorted(set(clean) - existing)
        if missing:
            raise ValueError(f"Referenced {key} IDs do not exist: {missing[:20]}")
        return hm.Collection(model, entity_class, clean), clean

    @staticmethod
    def _dof_code(name: str, value: int) -> int:
        try:
            code = str(int(value))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} must be an integer made from DOF digits 1 through 6") from exc
        if not code or any(char not in "123456" for char in code) or len(set(code)) != len(code):
            raise ValueError(
                f"{name} must contain unique DOF digits from 1 through 6, for example 123456"
            )
        return int(code)

    @staticmethod
    def _nonnegative_float(name: str, value: float, maximum: float = 1.0e12) -> float:
        try:
            result = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} must be numeric") from exc
        if not math.isfinite(result) or not 0.0 <= result <= maximum:
            raise ValueError(f"{name} must be finite and in the range [0, {maximum}]")
        return result

    def _checkpoint_root(self) -> Path:
        if not self.allowed_roots:
            raise RuntimeError("No save roots are configured for live-model checkpoints")
        root = self.allowed_roots[0] / ".hyperworks_mcp" / "checkpoints"
        root.mkdir(parents=True, exist_ok=True)
        return root

    def create_checkpoint(
        self, label: str = "manual", model_name: str | None = None
    ) -> dict[str, Any]:
        clean_label = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(label).strip())[:48]
        if not clean_label:
            clean_label = "checkpoint"
        path = self._checkpoint_root() / (
            time.strftime("%Y%m%d_%H%M%S")
            + "_"
            + clean_label
            + "_"
            + uuid.uuid4().hex[:8]
            + ".hm"
        )
        self._model(model_name).writefile(
            filename=path.as_posix(), do_not_write_facets=0
        )
        return {
            "created": True,
            "checkpoint_file": str(path),
            "model_name": model_name,
            "label": clean_label,
        }

    def rollback_checkpoint(
        self,
        checkpoint_file: str,
        confirm: bool = False,
        model_name: str | None = None,
    ) -> dict[str, Any]:
        if not confirm:
            raise ValueError(
                "Rollback replaces the current model state; set confirm=true after approval"
            )
        path = self._safe_input(checkpoint_file)
        try:
            path.relative_to(self._checkpoint_root())
        except ValueError as exc:
            raise ValueError("checkpoint_file is not a bridge-created checkpoint") from exc
        if path.suffix.lower() != ".hm":
            raise ValueError("checkpoint_file must use the .hm extension")
        model = self._model(model_name)
        model.hm_answernext(answer="yes")
        result = _unwrap_hm_call(
            model.readfile(filename=path.as_posix(), load_cad_geometry_as_graphics=0)
        )
        return {
            "rolled_back": True,
            "checkpoint_file": str(path),
            "model_name": model_name,
            "read_result": result,
        }

    def _rollback_after_failure(
        self, checkpoint: dict[str, Any], model_name: str | None, exc: Exception
    ) -> None:
        rollback_error = None
        try:
            self.rollback_checkpoint(
                checkpoint["checkpoint_file"], confirm=True, model_name=model_name
            )
        except Exception as rollback_exc:  # pragma: no cover - defensive live fallback
            rollback_error = str(rollback_exc)
        message = (
            f"{exc}. The live model was restored from checkpoint "
            f"{checkpoint['checkpoint_file']}"
        )
        if rollback_error:
            message += f"; rollback also reported: {rollback_error}"
        raise RuntimeError(message) from exc

    def create_rigid_link(
        self,
        independent_node_id: int,
        dependent_node_ids: list[int],
        dofs: int = 123456,
        model_name: str | None = None,
        refresh: bool = True,
    ) -> dict[str, Any]:
        """Create one solver-profile rigid link from existing live nodes."""
        independent_id = int(independent_node_id)
        if independent_id <= 0:
            raise ValueError("independent_node_id must be positive")
        dof_code = self._dof_code("dofs", dofs)
        hm, ent = self._imports()
        model = self._model(model_name)
        dependent_collection, dependent_ids = self._checked_collection(
            model, "node", dependent_node_ids
        )
        self._checked_collection(model, "node", [independent_id])
        if independent_id in dependent_ids:
            raise ValueError("independent_node_id must not also be a dependent node")

        checkpoint = self.create_checkpoint("before_rigid_link", model_name)
        before = self._entity_ids(hm, model, ent.Element)
        try:
            result = _unwrap_hm_call(
                model.rigidlink(
                    independent=ent.Node(model, independent_id),
                    collection=dependent_collection,
                    dofs=dof_code,
                )
            )
            created_ids = sorted(self._entity_ids(hm, model, ent.Element) - before)
            if not created_ids:
                raise RuntimeError("HyperMesh did not expose a newly created rigid-link element")
        except Exception as exc:
            self._rollback_after_failure(checkpoint, model_name, exc)

        refresh_result = None
        refresh_error = None
        if refresh:
            try:
                refresh_result = self.refresh_view(fit=False)
            except Exception as exc:  # pragma: no cover - graphics-only live failure
                refresh_error = str(exc)
        return {
            "created": True,
            "connection_type": "rigid_link",
            "model_name": model_name,
            "element_ids": created_ids,
            "independent_node_id": independent_id,
            "dependent_node_ids": dependent_ids,
            "dofs": dof_code,
            "checkpoint": checkpoint,
            "call_result": result,
            "refresh_result": refresh_result,
            "refresh_error": refresh_error,
        }

    def create_rbe3(
        self,
        independent_node_ids: list[int],
        dependent_node_id: int | None = None,
        independent_dofs: int = 123456,
        independent_weights: list[float] | None = None,
        dependent_dofs: list[bool] | None = None,
        dependent_weight: float = 1.0,
        model_name: str | None = None,
        refresh: bool = True,
    ) -> dict[str, Any]:
        """Create an RBE3 spider, optionally auto-creating its centroid dependent node."""
        dof_code = self._dof_code("independent_dofs", independent_dofs)
        hm, ent = self._imports()
        model = self._model(model_name)
        independent_collection, independent_ids = self._checked_collection(
            model, "node", independent_node_ids
        )
        if independent_weights is None:
            weights = [1.0] * len(independent_ids)
        else:
            if not isinstance(independent_weights, list) or len(independent_weights) != len(independent_ids):
                raise ValueError("independent_weights must contain one value per independent node")
            weights = [
                self._positive_float(f"independent_weights[{index}]", value)
                for index, value in enumerate(independent_weights)
            ]
        dof_flags = [True] * 6 if dependent_dofs is None else dependent_dofs
        if not isinstance(dof_flags, list) or len(dof_flags) != 6:
            raise ValueError("dependent_dofs must contain exactly six boolean values")
        if any(not isinstance(value, bool) for value in dof_flags) or not any(dof_flags):
            raise ValueError("dependent_dofs must contain booleans with at least one enabled DOF")
        dep_weight = self._positive_float("dependent_weight", dependent_weight)

        dependent_entity = None
        clean_dependent_id = None
        if dependent_node_id is not None:
            clean_dependent_id = int(dependent_node_id)
            if clean_dependent_id <= 0:
                raise ValueError("dependent_node_id must be positive")
            self._checked_collection(model, "node", [clean_dependent_id])
            if clean_dependent_id in independent_ids:
                raise ValueError("dependent_node_id must not also be an independent node")
            dependent_entity = ent.Node(model, clean_dependent_id)

        checkpoint = self.create_checkpoint("before_rbe3", model_name)
        before_elements = self._entity_ids(hm, model, ent.Element)
        before_nodes = self._entity_ids(hm, model, ent.Node)
        try:
            result = _unwrap_hm_call(
                model.rbe3(
                    collection=independent_collection,
                    independent_dofs=[dof_code] * len(independent_ids),
                    independent_weights=weights,
                    dependent_node=dependent_entity,
                    dof=list(dof_flags),
                    weight=dep_weight,
                )
            )
            created_element_ids = sorted(
                self._entity_ids(hm, model, ent.Element) - before_elements
            )
            created_node_ids = sorted(self._entity_ids(hm, model, ent.Node) - before_nodes)
            if not created_element_ids:
                raise RuntimeError("HyperMesh did not expose a newly created RBE3 element")
            if clean_dependent_id is None and not created_node_ids:
                raise RuntimeError("HyperMesh did not expose the auto-created RBE3 dependent node")
        except Exception as exc:
            self._rollback_after_failure(checkpoint, model_name, exc)

        refresh_result = None
        refresh_error = None
        if refresh:
            try:
                refresh_result = self.refresh_view(fit=False)
            except Exception as exc:  # pragma: no cover - graphics-only live failure
                refresh_error = str(exc)
        return {
            "created": True,
            "connection_type": "rbe3",
            "model_name": model_name,
            "element_ids": created_element_ids,
            "independent_node_ids": independent_ids,
            "dependent_node_id": clean_dependent_id,
            "auto_created_dependent_node_ids": created_node_ids,
            "independent_dofs": dof_code,
            "independent_weights": weights,
            "dependent_dofs": list(dof_flags),
            "dependent_weight": dep_weight,
            "checkpoint": checkpoint,
            "call_result": result,
            "refresh_result": refresh_result,
            "refresh_error": refresh_error,
        }

    def create_weld(
        self,
        independent_node_id: int,
        dependent_node_id: int,
        length: float = 0.0,
        create_systems: bool = False,
        move_node: bool = False,
        model_name: str | None = None,
        refresh: bool = True,
    ) -> dict[str, Any]:
        """Create a solver-profile weld element between two existing nodes."""
        independent_id = int(independent_node_id)
        dependent_id = int(dependent_node_id)
        if independent_id <= 0 or dependent_id <= 0:
            raise ValueError("node IDs must be positive")
        if independent_id == dependent_id:
            raise ValueError("independent and dependent node IDs must be different")
        weld_length = self._nonnegative_float("length", length)
        hm, ent = self._imports()
        model = self._model(model_name)
        self._checked_collection(model, "node", [independent_id, dependent_id])

        checkpoint = self.create_checkpoint("before_weld", model_name)
        before = self._entity_ids(hm, model, ent.Element)
        try:
            result = _unwrap_hm_call(
                model.weld(
                    independent=ent.Node(model, independent_id),
                    dependent=ent.Node(model, dependent_id),
                    length=weld_length,
                    systems=1 if create_systems else 0,
                    movenode=1 if move_node else 0,
                )
            )
            created_ids = sorted(self._entity_ids(hm, model, ent.Element) - before)
            if not created_ids:
                raise RuntimeError("HyperMesh did not expose a newly created weld element")
        except Exception as exc:
            self._rollback_after_failure(checkpoint, model_name, exc)

        refresh_result = None
        refresh_error = None
        if refresh:
            try:
                refresh_result = self.refresh_view(fit=False)
            except Exception as exc:  # pragma: no cover - graphics-only live failure
                refresh_error = str(exc)
        return {
            "created": True,
            "connection_type": "weld",
            "model_name": model_name,
            "element_ids": created_ids,
            "independent_node_id": independent_id,
            "dependent_node_id": dependent_id,
            "length": weld_length,
            "create_systems": bool(create_systems),
            "move_node": bool(move_node),
            "checkpoint": checkpoint,
            "call_result": result,
            "refresh_result": refresh_result,
            "refresh_error": refresh_error,
        }

    def create_spot_weld(
        self,
        independent_node_id: int,
        dependent_node_id: int,
        config: int,
        property_name: str,
        length: float = 0.0,
        create_system: bool = False,
        move_node: bool = False,
        remesh: bool = False,
        model_name: str | None = None,
        refresh: bool = True,
    ) -> dict[str, Any]:
        """Create a solver-profile spot weld with an explicit FE config and property."""
        independent_id = int(independent_node_id)
        dependent_id = int(dependent_node_id)
        config = int(config)
        prop_name = str(property_name).strip()
        if independent_id <= 0 or dependent_id <= 0 or independent_id == dependent_id:
            raise ValueError("Spot-weld node IDs must be different positive integers")
        if config <= 0:
            raise ValueError("config must be positive")
        if not prop_name or len(prop_name) > 128:
            raise ValueError("property_name must contain between 1 and 128 characters")
        weld_length = self._nonnegative_float("length", length)
        hm, ent = self._imports()
        model = self._model(model_name)
        self._checked_collection(model, "node", [independent_id, dependent_id])
        properties = [
            item for item in hm.Collection(model, ent.Property)
            if str(getattr(item, "name", "")) == prop_name
        ]
        if not properties:
            raise ValueError(f"Property does not exist: {prop_name}")
        checkpoint = self.create_checkpoint("before_spot_weld", model_name)
        before = self._entity_ids(hm, model, ent.Element)
        try:
            result = _unwrap_hm_call(
                model.createspotweld(
                    independent=ent.Node(model, independent_id),
                    dependent=ent.Node(model, dependent_id),
                    length_given=1 if weld_length > 0.0 else 0,
                    length=weld_length,
                    systems=1 if create_system else 0,
                    movenode=1 if move_node else 0,
                    remesh=1 if remesh else 0,
                    configval=config,
                    property=prop_name,
                )
            )
            created_ids = sorted(self._entity_ids(hm, model, ent.Element) - before)
            if not created_ids:
                raise RuntimeError("HyperMesh did not expose a newly created spot-weld element")
        except Exception as exc:
            self._rollback_after_failure(checkpoint, model_name, exc)
        view = self.refresh_view(fit=False) if refresh else None
        return {
            "created": True,
            "connection_type": "spot_weld",
            "element_ids": created_ids,
            "independent_node_id": independent_id,
            "dependent_node_id": dependent_id,
            "config": config,
            "property_name": prop_name,
            "length": weld_length,
            "checkpoint": checkpoint,
            "call_result": result,
            "view": view,
        }

    def create_connector(
        self,
        location_entity_type: str,
        location_ids: list[int],
        style: str,
        link_entity_type: str,
        link_ids: list[int],
        num_links: int = 2,
        tolerance: float = 0.0,
        model_name: str | None = None,
        refresh: bool = True,
    ) -> dict[str, Any]:
        """Create connector intent without solver-specific FE realization.

        HyperMesh connectors preserve assembly intent separately from the realized
        weld/bolt/bar elements.  Realization is intentionally a separate future
        operation because its FE type, property, and control choices are solver
        profile dependent.
        """
        location_type = str(location_entity_type).strip().lower()
        link_type = str(link_entity_type).strip().lower()
        connector_style = str(style).strip().lower()
        if location_type not in {"node", "line"}:
            raise ValueError("location_entity_type must be 'node' or 'line'")
        if link_type not in {"component", "surface"}:
            raise ValueError("link_entity_type must be 'component' or 'surface'")
        if connector_style not in {"spot", "seam", "area", "bolt"}:
            raise ValueError("style must be spot, seam, area, or bolt")
        try:
            link_count = int(num_links)
        except (TypeError, ValueError) as exc:
            raise ValueError("num_links must be an integer") from exc
        if not 1 <= link_count <= 100:
            raise ValueError("num_links must be in the range [1, 100]")
        connector_tolerance = self._nonnegative_float("tolerance", tolerance)

        hm, ent = self._imports()
        model = self._model(model_name)
        location_collection, clean_location_ids = self._checked_collection(
            model, location_type, location_ids
        )
        link_collection, clean_link_ids = self._checked_collection(
            model, link_type, link_ids
        )
        checkpoint = self.create_checkpoint("before_connector", model_name)
        before = self._entity_ids(hm, model, ent.Connector)
        try:
            result = _unwrap_hm_call(
                model.CE_ConnectorCreateByList(
                    entitylist=list(location_collection),
                    ce_style=connector_style,
                    num_links=link_count,
                    link_collection=link_collection,
                    tol_flag=1 if connector_tolerance > 0.0 else 0,
                    tol=connector_tolerance,
                )
            )
            created_ids = sorted(self._entity_ids(hm, model, ent.Connector) - before)
            if not created_ids:
                raise RuntimeError("HyperMesh did not expose a newly created connector ID")
        except Exception as exc:
            self._rollback_after_failure(checkpoint, model_name, exc)
        view = self.refresh_view(fit=False) if refresh else None
        return {
            "created": True,
            "connection_type": "connector_intent",
            "realized": False,
            "connector_ids": created_ids,
            "style": connector_style,
            "location_entity_type": location_type,
            "location_ids": clean_location_ids,
            "link_entity_type": link_type,
            "link_ids": clean_link_ids,
            "num_links": link_count,
            "tolerance": connector_tolerance,
            "checkpoint": checkpoint,
            "call_result": result,
            "view": view,
        }

    def create_solid_block(
        self,
        origin: list[float],
        dimensions: list[float],
        model_name: str | None = None,
    ) -> dict[str, Any]:
        base = self._finite_vector("origin", origin)
        size = self._finite_vector("dimensions", dimensions, positive=True)
        hm, ent = self._imports()
        model = self._model(model_name)
        checkpoint = self.create_checkpoint("before_solid_block", model_name)
        before = self._entity_ids(hm, model, ent.Solid)
        try:
            result = _unwrap_hm_call(
                model.solidblock(
                    base_x=base[0], base_y=base[1], base_z=base[2],
                    ivec_x=size[0], ivec_y=0.0, ivec_z=0.0,
                    jvec_x=0.0, jvec_y=size[1], jvec_z=0.0,
                    kvec_x=0.0, kvec_y=0.0, kvec_z=size[2],
                )
            )
            created = sorted(self._entity_ids(hm, model, ent.Solid) - before)
            if not created:
                raise RuntimeError("HyperMesh did not expose a newly created solid ID")
        except Exception as exc:
            self._rollback_after_failure(checkpoint, model_name, exc)
        return {
            "created": True,
            "primitive": "block",
            "solid_ids": created,
            "origin": list(base),
            "dimensions": list(size),
            "checkpoint": checkpoint,
            "call_result": result,
        }

    def create_solid_cylinder(
        self,
        base_center: list[float],
        axis: list[float],
        radius: float,
        height: float,
        model_name: str | None = None,
    ) -> dict[str, Any]:
        base = self._finite_vector("base_center", base_center)
        normal = self._unit_vector(axis)
        radius = self._positive_float("radius", radius)
        height = self._positive_float("height", height)
        reference = (1.0, 0.0, 0.0) if abs(normal[0]) < 0.9 else (0.0, 1.0, 0.0)
        major = self._unit_vector(list(self._cross(reference, normal)), "major_axis")
        hm, ent = self._imports()
        model = self._model(model_name)
        checkpoint = self.create_checkpoint("before_solid_cylinder", model_name)
        before = self._entity_ids(hm, model, ent.Solid)
        try:
            result = _unwrap_hm_call(
                model.solidcone(
                    base_x=base[0], base_y=base[1], base_z=base[2],
                    mvec_x=major[0], mvec_y=major[1], mvec_z=major[2],
                    nvec_x=normal[0], nvec_y=normal[1], nvec_z=normal[2],
                    base_radius=radius, top_radius=radius, aspect_ratio=1.0,
                    start_angle=0.0, end_angle=360.0, height=height,
                )
            )
            created = sorted(self._entity_ids(hm, model, ent.Solid) - before)
            if not created:
                raise RuntimeError("HyperMesh did not expose a newly created solid ID")
        except Exception as exc:
            self._rollback_after_failure(checkpoint, model_name, exc)
        return {
            "created": True,
            "primitive": "cylinder",
            "solid_ids": created,
            "base_center": list(base),
            "axis": list(normal),
            "radius": radius,
            "height": height,
            "checkpoint": checkpoint,
            "call_result": result,
        }

    def import_cad(
        self,
        input_file: str,
        translator: str | None = None,
        options: list[str] | None = None,
        model_name: str | None = None,
    ) -> dict[str, Any]:
        path = self._safe_input(input_file)
        default_translator = CAD_TRANSLATORS.get(path.suffix.lower())
        translator = str(translator or default_translator or "").strip().lower()
        if translator not in ALLOWED_CAD_TRANSLATORS:
            raise ValueError(
                "Unsupported CAD translator. Allowed values: "
                + ", ".join(sorted(ALLOWED_CAD_TRANSLATORS))
            )
        options = options or []
        if not isinstance(options, list) or len(options) > MAX_CAD_OPTIONS:
            raise ValueError(f"options must be a list with at most {MAX_CAD_OPTIONS} items")
        clean_options = []
        for item in options:
            value = str(item)
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]*=[^\r\n;]{0,200}", value):
                raise ValueError(f"Invalid CAD import option: {value!r}")
            clean_options.append(value)

        hm, ent = self._imports()
        model = self._model(model_name)
        checkpoint = self.create_checkpoint("before_cad_import", model_name)
        tracked = (ent.Solid, ent.Surface, ent.Component)
        before = {entity_class: self._entity_ids(hm, model, entity_class) for entity_class in tracked}
        try:
            result = _unwrap_hm_call(
                model.geomimport(
                    translator_type=translator,
                    input_file_name=path.as_posix(),
                    options=clean_options,
                )
            )
            created = {
                entity_class.__name__.lower() + "_ids": sorted(
                    self._entity_ids(hm, model, entity_class) - before[entity_class]
                )
                for entity_class in tracked
            }
            if not created["solid_ids"] and not created["surface_ids"]:
                raise RuntimeError("CAD import completed without exposing new solids or surfaces")
        except Exception as exc:
            self._rollback_after_failure(checkpoint, model_name, exc)
        return {
            "imported": True,
            "input_file": str(path),
            "translator": translator,
            "options": clean_options,
            **created,
            "checkpoint": checkpoint,
            "call_result": result,
        }

    def automesh_surfaces(
        self,
        surface_ids: list[int],
        element_size: float,
        element_type: str = "mixed",
        mesh_type: str = "proximity_curvature",
        min_size: float | None = None,
        max_size: float | None = None,
        chordal_deviation: float | None = None,
        max_angle: float = 30.0,
        growth_rate: float = 1.2,
        keep_existing_mesh: bool = True,
        model_name: str | None = None,
    ) -> dict[str, Any]:
        element_size = self._positive_float("element_size", element_size)
        min_size = self._positive_float("min_size", min_size or element_size * 0.2)
        max_size = self._positive_float("max_size", max_size or element_size)
        if min_size > max_size:
            raise ValueError("min_size must not exceed max_size")
        chordal_deviation = float(
            element_size * 0.05 if chordal_deviation is None else chordal_deviation
        )
        if not math.isfinite(chordal_deviation) or chordal_deviation < 0.0:
            raise ValueError("chordal_deviation must be finite and non-negative")
        max_angle = float(max_angle)
        growth_rate = float(growth_rate)
        if not 1.0 <= max_angle <= 180.0:
            raise ValueError("max_angle must be between 1 and 180 degrees")
        if not 1.0 <= growth_rate <= 5.0:
            raise ValueError("growth_rate must be between 1 and 5")
        if element_type not in SURFACE_ELEMENT_TYPES:
            raise ValueError("Unsupported element_type")
        if mesh_type not in SURFACE_MESH_TYPES:
            raise ValueError("Unsupported mesh_type")

        hm, ent = self._imports()
        model = self._model(model_name)
        collection, clean_ids = self._checked_collection(model, "surface", surface_ids)
        checkpoint = self.create_checkpoint("before_surface_automesh", model_name)
        before = self._entity_ids(hm, model, ent.Element)
        try:
            result = _unwrap_hm_call(
                model.defaultmeshsurf_growth(
                    collection=collection,
                    elem_size=element_size,
                    elem_type=SURFACE_ELEMENT_TYPES[element_type],
                    elem_type_2=SURFACE_ELEMENT_TYPES[element_type],
                    previous_settings=2,
                    comp_mode=1,
                    size_control=1,
                    skew_control=1,
                    mesh_type=SURFACE_MESH_TYPES[mesh_type],
                    keep_mesh=1 if keep_existing_mesh else 0,
                    min_size=min_size,
                    max_size=max_size,
                    chordal_dev=chordal_deviation,
                    max_angle=max_angle,
                    growth_rate=growth_rate,
                    id_array=[0, 0, 0],
                    size_array=[],
                )
            )
            created = sorted(self._entity_ids(hm, model, ent.Element) - before)
            if not created:
                raise RuntimeError("Surface automeshing did not expose newly created elements")
        except Exception as exc:
            self._rollback_after_failure(checkpoint, model_name, exc)
        return {
            "meshed": True,
            "surface_ids": clean_ids,
            "element_ids": created,
            "element_count": len(created),
            "element_size": element_size,
            "element_type": element_type,
            "mesh_type": mesh_type,
            "checkpoint": checkpoint,
            "call_result": result,
        }

    def solid_map_mesh(
        self,
        solid_ids: list[int],
        element_size: float,
        element_type: str = "mixed",
        organize_to_current_component: bool = False,
        extra_smoothing: bool = True,
        remesh_shell_mesh: bool = False,
        continue_on_negative_jacobian: bool = False,
        model_name: str | None = None,
    ) -> dict[str, Any]:
        element_size = self._positive_float("element_size", element_size)
        if element_type not in {"tria", "quad", "mixed"}:
            raise ValueError("element_type must be tria, quad, or mixed")
        hm, ent = self._imports()
        model = self._model(model_name)
        collection, clean_ids = self._checked_collection(model, "solid", solid_ids)
        checkpoint = self.create_checkpoint("before_solid_map", model_name)
        before = self._entity_ids(hm, model, ent.Element)
        elem_code = SURFACE_ELEMENT_TYPES[element_type]
        options = {"tria": 0, "quad": 512, "mixed": 1024}[element_type]
        if organize_to_current_component:
            options |= 2
        if extra_smoothing:
            options |= 256
        if remesh_shell_mesh:
            options |= 8192
        if continue_on_negative_jacobian:
            options |= 262144
        try:
            model.solidmap_solids_begin3(
                solidcollection=collection,
                elemsize=element_size,
                elem_type=elem_code,
                orthogonal_extrusion=0,
            )
            model.solidmap_solids_begin(
                collection=collection, options=options, elem_size=element_size
            )
            result = _unwrap_hm_call(model.solidmap_solids_end())
            created = sorted(self._entity_ids(hm, model, ent.Element) - before)
            if not created:
                raise RuntimeError(
                    "Solid Map did not create elements; confirm the selected solids are mappable"
                )
        except Exception as exc:
            self._rollback_after_failure(checkpoint, model_name, exc)
        return {
            "meshed": True,
            "method": "native_solid_map",
            "solid_ids": clean_ids,
            "element_ids": created,
            "element_count": len(created),
            "element_size": element_size,
            "element_type": element_type,
            "options": options,
            "checkpoint": checkpoint,
            "call_result": result,
        }

    def tetra_mesh_solids(
        self,
        solid_ids: list[int],
        element_size: float,
        min_size: float | None = None,
        max_size: float | None = None,
        growth_rate: float = 1.3,
        element_order: int = 1,
        use_existing_surface_mesh: bool = True,
        model_name: str | None = None,
        refresh: bool = True,
    ) -> dict[str, Any]:
        """Create a bounded structural tetra mesh on explicit solid IDs."""
        size = self._positive_float("element_size", element_size)
        minimum = self._positive_float("min_size", min_size or size * 0.2)
        maximum = self._positive_float("max_size", max_size or size)
        growth = float(growth_rate)
        order = int(element_order)
        if minimum > maximum:
            raise ValueError("min_size must not exceed max_size")
        if not 1.0 <= growth <= 3.0:
            raise ValueError("growth_rate must be between 1 and 3")
        if order not in {1, 2}:
            raise ValueError("element_order must be 1 or 2")
        hm, ent = self._imports()
        model = self._model(model_name)
        solid_collection, clean_ids = self._checked_collection(model, "solid", solid_ids)
        empty_elements = hm.Collection(model, ent.Element, populate=False)
        checkpoint = self.create_checkpoint("before_tetra_mesh", model_name)
        before = self._entity_ids(hm, model, ent.Element)
        strings = [
            f"pars: upd_shell fix_comp_bdr post_cln elem_order={order} delaunay el2comp=3 fill_void=1",
            f"tet: 35 {growth:.12g} -1 {maximum:.12g} {minimum:.12g} 0 0 1",
            f"2d: {order} 0 4 {size:.12g} {minimum:.12g} 30 {1 if use_existing_surface_mesh else 0}",
        ]
        try:
            result = _unwrap_hm_call(
                model.tetmesh(
                    collection1=solid_collection,
                    mode1=1,
                    collection2=empty_elements,
                    mode2=-1,
                    string_array=strings,
                )
            )
            created_ids = sorted(self._entity_ids(hm, model, ent.Element) - before)
            if not created_ids:
                raise RuntimeError("Tetra meshing completed without exposing new elements")
            quality = self.get_mesh_quality(created_ids, model_name=model_name)
            if quality["non_positive_volume_element_ids"]:
                raise RuntimeError(
                    "Tetra mesh contains non-positive-volume elements: "
                    + str(quality["non_positive_volume_element_ids"][:20])
                )
        except Exception as exc:
            self._rollback_after_failure(checkpoint, model_name, exc)
        view = self.refresh_view(fit=True) if refresh else None
        return {
            "meshed": True,
            "method": "native_tetmesh",
            "solid_ids": clean_ids,
            "element_ids": created_ids,
            "element_count": len(created_ids),
            "parameters": {
                "element_size": size,
                "min_size": minimum,
                "max_size": maximum,
                "growth_rate": growth,
                "element_order": order,
                "use_existing_surface_mesh": bool(use_existing_surface_mesh),
            },
            "quality": quality,
            "checkpoint": checkpoint,
            "call_result": result,
            "view": view,
        }

    def repair_mesh_quality(
        self,
        element_ids: list[int],
        anchor_node_ids: list[int] | None = None,
        iterations: int = 5,
        method: str = "AutoDecideWithQI_Params_locked",
        anchor_free_edges: bool = True,
        model_name: str | None = None,
        refresh: bool = True,
    ) -> dict[str, Any]:
        """Smooth selected elements with an automatic checkpoint and before/after metrics."""
        allowed_methods = {
            "Angle", "AutoDecideWithoutQI", "AutoDecideWithQI",
            "AutoDecideWithQI_Params_locked", "QI", "Shape", "Size",
        }
        if method not in allowed_methods:
            raise ValueError("Unsupported smoothing method")
        iteration_count = int(iterations)
        if not 1 <= iteration_count <= 100:
            raise ValueError("iterations must be between 1 and 100")
        hm, ent = self._imports()
        model = self._model(model_name)
        element_collection, clean_ids = self._checked_collection(model, "element", element_ids)
        if anchor_node_ids:
            node_collection, clean_anchors = self._checked_collection(model, "node", anchor_node_ids)
        else:
            node_collection = hm.Collection(model, ent.Node, populate=False)
            clean_anchors = []
        before_quality = self.get_mesh_quality(clean_ids, model_name=model_name)
        checkpoint = self.create_checkpoint("before_mesh_quality_repair", model_name)
        try:
            result = _unwrap_hm_call(
                model.element_smooth_nodes(
                    elementsCollection=element_collection,
                    nodeCollection=node_collection,
                    anchorFreeEdgeNodes=1 if anchor_free_edges else 0,
                    iterations=iteration_count,
                    smoothmethod=method,
                    timelimit=0,
                )
            )
            shutdown = _unwrap_hm_call(model.elementqualityshutdown(dontsaveflag=0))
            after_quality = self.get_mesh_quality(clean_ids, model_name=model_name)
            if after_quality["non_positive_volume_element_ids"]:
                raise RuntimeError(
                    "Quality repair produced non-positive-volume elements: "
                    + str(after_quality["non_positive_volume_element_ids"][:20])
                )
        except Exception as exc:
            self._rollback_after_failure(checkpoint, model_name, exc)
        view = self.refresh_view(fit=False) if refresh else None
        return {
            "repaired": True,
            "element_ids": clean_ids,
            "anchor_node_ids": clean_anchors,
            "method": method,
            "iterations": iteration_count,
            "quality_before": before_quality,
            "quality_after": after_quality,
            "checkpoint": checkpoint,
            "call_result": result,
            "shutdown_result": shutdown,
            "view": view,
        }

    def create_cylindrical_ogrid(
        self,
        base_center: list[float],
        axis: list[float],
        length: float,
        radius: float,
        axial_divisions: int = 4,
        circumferential_divisions: int = 12,
        radial_layers: int = 2,
        core_ratio: float = 0.4,
        model_name: str | None = None,
        refresh: bool = True,
    ) -> dict[str, Any]:
        base = self._finite_vector("base_center", base_center)
        normal = self._unit_vector(axis)
        length = self._positive_float("length", length)
        radius = self._positive_float("radius", radius)
        axial_divisions = int(axial_divisions)
        circumferential_divisions = int(circumferential_divisions)
        radial_layers = int(radial_layers)
        core_ratio = float(core_ratio)
        if not 1 <= axial_divisions <= 50:
            raise ValueError("axial_divisions must be between 1 and 50")
        if not 8 <= circumferential_divisions <= 128 or circumferential_divisions % 4:
            raise ValueError(
                "circumferential_divisions must be a multiple of 4 between 8 and 128"
            )
        if not 1 <= radial_layers <= 20:
            raise ValueError("radial_layers must be between 1 and 20")
        if not 0.1 <= core_ratio <= 0.8:
            raise ValueError("core_ratio must be between 0.1 and 0.8")
        plane_count = axial_divisions + 1
        ring_count = radial_layers + 1
        node_count = plane_count * (1 + ring_count * circumferential_divisions)
        penta_count = axial_divisions * circumferential_divisions
        hexa_count = axial_divisions * radial_layers * circumferential_divisions
        if node_count > MAX_NODES_PER_CALL:
            raise ValueError(f"Requested O-grid needs {node_count} nodes; limit is {MAX_NODES_PER_CALL}")
        if penta_count + hexa_count > MAX_ELEMENTS_PER_CALL:
            raise ValueError(
                f"Requested O-grid needs {penta_count + hexa_count} elements; "
                f"limit is {MAX_ELEMENTS_PER_CALL}"
            )

        reference = (1.0, 0.0, 0.0) if abs(normal[0]) < 0.9 else (0.0, 1.0, 0.0)
        radial_u = self._unit_vector(list(self._cross(reference, normal)), "radial_u")
        radial_v = self._cross(normal, radial_u)
        coordinates: list[list[float]] = []
        keys: list[tuple[int, int, int]] = []
        for plane in range(plane_count):
            axial_offset = length * plane / axial_divisions
            center = tuple(base[i] + normal[i] * axial_offset for i in range(3))
            coordinates.append(list(center))
            keys.append((plane, -1, 0))
            for ring in range(ring_count):
                ring_radius = radius * (
                    core_ratio + (1.0 - core_ratio) * ring / radial_layers
                )
                for sector in range(circumferential_divisions):
                    angle = 2.0 * math.pi * sector / circumferential_divisions
                    coordinates.append(
                        [
                            center[i]
                            + ring_radius
                            * (math.cos(angle) * radial_u[i] + math.sin(angle) * radial_v[i])
                            for i in range(3)
                        ]
                    )
                    keys.append((plane, ring, sector))

        checkpoint = self.create_checkpoint("before_cylindrical_ogrid", model_name)
        try:
            node_result = self.create_nodes(coordinates, model_name=model_name)
            node_map = dict(zip(keys, node_result["ids"]))

            def center_id(plane: int) -> int:
                return node_map[(plane, -1, 0)]

            def ring_id(plane: int, ring: int, sector: int) -> int:
                return node_map[(plane, ring, sector % circumferential_divisions)]

            penta_connectivity = []
            hexa_connectivity = []
            for plane in range(axial_divisions):
                for sector in range(circumferential_divisions):
                    penta_connectivity.append(
                        [
                            center_id(plane),
                            ring_id(plane, 0, sector),
                            ring_id(plane, 0, sector + 1),
                            center_id(plane + 1),
                            ring_id(plane + 1, 0, sector),
                            ring_id(plane + 1, 0, sector + 1),
                        ]
                    )
                    for ring in range(radial_layers):
                        hexa_connectivity.append(
                            [
                                ring_id(plane, ring, sector),
                                ring_id(plane, ring + 1, sector),
                                ring_id(plane, ring + 1, sector + 1),
                                ring_id(plane, ring, sector + 1),
                                ring_id(plane + 1, ring, sector),
                                ring_id(plane + 1, ring + 1, sector),
                                ring_id(plane + 1, ring + 1, sector + 1),
                                ring_id(plane + 1, ring, sector + 1),
                            ]
                        )
            penta_result = self.create_elements(
                penta_connectivity, config=206, solver_type=1,
                auto_order=True, model_name=model_name
            )
            hexa_result = self.create_elements(
                hexa_connectivity, config=208, solver_type=1,
                auto_order=True, model_name=model_name
            )
            element_ids = penta_result["ids"] + hexa_result["ids"]
            quality = self.get_mesh_quality(element_ids, model_name=model_name)
            if quality["non_positive_volume_element_ids"]:
                raise RuntimeError(
                    "O-grid contains non-positive-volume 3D elements: "
                    + str(quality["non_positive_volume_element_ids"][:20])
                )
            view = self.refresh_view(fit=True) if refresh else None
        except Exception as exc:
            self._rollback_after_failure(checkpoint, model_name, exc)
        return {
            "created": True,
            "method": "radial_ogrid_with_penta_core",
            "node_ids": node_result["ids"],
            "element_ids": element_ids,
            "node_count": node_result["count"],
            "penta6_count": penta_result["count"],
            "hex8_count": hexa_result["count"],
            "parameters": {
                "base_center": list(base), "axis": list(normal),
                "length": length, "radius": radius,
                "axial_divisions": axial_divisions,
                "circumferential_divisions": circumferential_divisions,
                "radial_layers": radial_layers, "core_ratio": core_ratio,
            },
            "quality": quality,
            "checkpoint": checkpoint,
            "view": view,
        }

    def get_mesh_quality(
        self,
        element_ids: list[int] | None = None,
        model_name: str | None = None,
    ) -> dict[str, Any]:
        hm, ent = self._imports()
        model = self._model(model_name)
        all_elements = list(hm.Collection(model, ent.Element))
        if element_ids is None:
            if len(all_elements) > MAX_ELEMENTS_PER_CALL:
                raise ValueError(
                    f"Model has more than {MAX_ELEMENTS_PER_CALL} elements; pass a bounded element_ids list"
                )
            elements = all_elements
            clean_ids = [int(element.id) for element in elements]
        else:
            _, clean_ids = self._checked_collection(model, "element", element_ids)
            by_id = {int(element.id): element for element in all_elements}
            elements = [by_id[value] for value in clean_ids]

        attribute_values: dict[str, list[tuple[int, float]]] = {
            "volume": [], "jacobian": [], "aspect": [], "skew": []
        }
        unavailable: dict[str, list[int]] = {name: [] for name in attribute_values}
        non_positive_volume = []
        for element in elements:
            entity_id = int(element.id)
            try:
                config = int(getattr(element, "config"))
            except Exception:
                config = -1
            for name in attribute_values:
                try:
                    value = float(getattr(element, name))
                    if math.isfinite(value):
                        attribute_values[name].append((entity_id, value))
                    else:
                        unavailable[name].append(entity_id)
                except Exception:
                    unavailable[name].append(entity_id)
            if 200 <= config < 300:
                volume = next(
                    (value for item_id, value in attribute_values["volume"] if item_id == entity_id),
                    None,
                )
                if volume is not None and volume <= 0.0:
                    non_positive_volume.append(entity_id)
        statistics = {}
        for name, values in attribute_values.items():
            numeric = [value for _, value in values]
            statistics[name] = {
                "available_count": len(numeric),
                "min": min(numeric) if numeric else None,
                "max": max(numeric) if numeric else None,
                "mean": sum(numeric) / len(numeric) if numeric else None,
            }
        return {
            "model_name": model_name,
            "element_ids": clean_ids,
            "element_count": len(clean_ids),
            "statistics": statistics,
            "unavailable_attribute_counts": {
                name: len(ids) for name, ids in unavailable.items()
            },
            "non_positive_volume_element_ids": non_positive_volume,
        }

    def _safe_input(self, raw_path: str) -> Path:
        path = self._safe_output(raw_path)
        if not path.is_file():
            raise ValueError(f"Input model does not exist: {path}")
        return path

    def load_model(
        self,
        input_file: str,
        replace_current: bool = False,
        load_cad_geometry_as_graphics: bool = False,
        model_name: str | None = None,
    ) -> dict[str, Any]:
        if not replace_current:
            raise ValueError(
                "Loading replaces the current model state; set replace_current=true after approval"
            )
        path = self._safe_input(input_file)
        if path.suffix.lower() != ".hm":
            raise ValueError("The controlled live loader currently accepts only .hm files")
        model = self._model(model_name)
        model.hm_answernext(answer="yes")
        result = _unwrap_hm_call(
            model.readfile(
                filename=path.as_posix(),
                load_cad_geometry_as_graphics=1 if load_cad_geometry_as_graphics else 0,
            )
        )
        session = self.get_session_info()
        return {
            "loaded": True,
            "input_file": str(path),
            "model_name": model_name,
            "read_result": result,
            "session": session,
        }

    def refresh_view(self, fit: bool = True) -> dict[str, Any]:
        import hw

        commands = []
        if fit:
            hw.evalTcl("hm_viewfit")
            commands.append("hm_viewfit")
        hw.evalTcl("hm_redraw")
        commands.append("hm_redraw")
        return {"refreshed": True, "fit": bool(fit), "commands": commands}

    def get_model_metrics(self, model_name: str | None = None) -> dict[str, Any]:
        model = self._model(model_name)
        calls = {
            "solver": "hm_getsolver",
            "total_mass": "hm_gettotalmass",
            "center_of_gravity": "hm_gettotalcog",
            "current_view": "hm_getcurrentview",
            "existing_entity_types": "hm_getexistingentitytypes",
        }
        result = {"model_name": model_name, "values": {}, "errors": {}}
        for label, method_name in calls.items():
            try:
                result["values"][label] = _unwrap_hm_call(
                    getattr(model, method_name)()
                )
            except Exception as exc:
                result["errors"][label] = str(exc)
        return result

    def _safe_output(self, raw_path: str) -> Path:
        if not self.allowed_roots:
            raise RuntimeError("No save roots are configured for the live bridge")
        path = Path(raw_path).expanduser().resolve()
        for root in self.allowed_roots:
            try:
                path.relative_to(root)
                return path
            except ValueError:
                continue
        raise ValueError(f"Output path is outside configured save roots: {path}")

    def _safe_input(self, raw_path: str) -> Path:
        path = self._safe_output(raw_path)
        if not path.is_file():
            raise ValueError(f"Input file does not exist: {path}")
        return path

    def postprocess_hyperview_result(
        self,
        model_file: str,
        result_file: str,
        output_file: str,
        data_type: str = "Displacement",
        data_component: str = "Mag",
        entity_type: str = "node",
        page_title: str = "MCP HyperView Results",
        query_limit: int = 20,
        simulation: str | int = "last",
        average_mode: str = "none",
    ) -> dict[str, Any]:
        """Load one result on a new page, contour it, query values, and capture evidence."""
        import hw
        import hw.hv as hv

        model_path = self._safe_input(model_file)
        result_path = self._safe_input(result_file)
        image_path = self._safe_output(output_file)
        if result_path.suffix.lower() not in {".h3d", ".op2", ".d3plot", ".h5", ".hdf5"}:
            raise ValueError("result_file must be an allowlisted HyperView result format")
        if model_path.suffix.lower() not in {".fem", ".bdf", ".dat", ".h3d", ".rad", ".key"}:
            raise ValueError("model_file must be an allowlisted solver model format")
        if image_path.suffix.lower() != ".png":
            raise ValueError("output_file must use the .png extension")
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9 _()/+&.-]{0,79}", data_type):
            raise ValueError("Invalid HyperView data_type")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _()/+.-]{0,79}", data_component):
            raise ValueError("Invalid HyperView data_component")
        entity_key = entity_type.strip().lower()
        if entity_key not in {"node", "element"}:
            raise ValueError("entity_type must be node or element")
        if not isinstance(page_title, str) or not page_title.strip() or len(page_title) > 100:
            raise ValueError("page_title must contain 1 to 100 characters")
        limit = max(1, min(int(query_limit), 100))
        normalized_average_mode = str(average_mode).strip().casefold()
        allowed_average_modes = {
            "none", "simple", "maximum", "minimum", "advanced", "difference"
        }
        if normalized_average_mode not in allowed_average_modes:
            raise ValueError(
                "average_mode must be none, simple, maximum, minimum, advanced, or difference"
            )

        image_path.parent.mkdir(parents=True, exist_ok=True)
        session = hw.Session()
        page = hw.Page(layout=1, title=page_title.strip())
        session.setActive(hw.Page, page=page)
        window = session.get(hw.Window, page=page)
        window.type = "animation"
        window.addModelAndResult(model=str(model_path), result=str(result_path))

        result = session.get(hv.Result, page=page, window=window)
        subcase_ids = _jsonable(result.getSubcaseIds())
        subcase_labels = _jsonable(result.getSubcaseLabels())
        if subcase_ids:
            result.subcase = int(subcase_ids[0])
        selected_subcase = int(subcase_ids[0]) if subcase_ids else 1
        data_types = _jsonable(result.getDataTypes(selected_subcase))
        resolved_data_type = data_type
        if isinstance(data_types, list):
            available_type_names = [str(item) for item in data_types]
            exact_type = next(
                (
                    item
                    for item in available_type_names
                    if item.casefold() == data_type.casefold()
                ),
                None,
            )
            if exact_type:
                resolved_data_type = exact_type
            elif data_type.casefold() == "stress":
                resolved_data_type = next(
                    (
                        item
                        for item in available_type_names
                        if "stress" in item.casefold()
                    ),
                    data_type,
                )
        data_components = None
        data_components_error = None
        try:
            data_components = _jsonable(
                result.getDataComponents(resolved_data_type, selected_subcase)
            )
        except Exception as exc:
            # Some HyperView readers accept the documented datatype/component
            # pair for plotting while rejecting getDataComponents() for that
            # same vector result.  Component enumeration is diagnostic only.
            data_components_error = str(exc)
        resolved_data_component = data_component
        if isinstance(data_components, list):
            normalized_component = re.sub(r"[^a-z0-9]", "", data_component.casefold())
            resolved_data_component = next(
                (
                    str(item)
                    for item in data_components
                    if re.sub(r"[^a-z0-9]", "", str(item).casefold())
                    == normalized_component
                ),
                data_component,
            )
        scalar = hv.ResultDefinitionScalar(
            dataType=resolved_data_type,
            dataComponent=resolved_data_component,
            page=page,
            window=window,
        )
        scalar.averageMode = normalized_average_mode
        result.plot(scalar, waitTillLoaded=True)
        simulation_ids = _jsonable(result.getSimulationIds(selected_subcase))
        if isinstance(simulation, bool):
            raise ValueError("simulation must be first, last, or an integer simulation ID")
        if isinstance(simulation, int):
            if isinstance(simulation_ids, list) and simulation_ids:
                normalized_ids = [int(value) for value in simulation_ids]
                if simulation not in normalized_ids:
                    raise ValueError(
                        f"simulation ID {simulation} is not available; choose from {normalized_ids}"
                    )
            selected_simulation: str | int = simulation
        elif isinstance(simulation, str) and simulation.strip().casefold() in {"first", "last"}:
            requested_simulation = simulation.strip().casefold()
            if requested_simulation == "first" and isinstance(simulation_ids, list) and simulation_ids:
                selected_simulation = int(simulation_ids[0])
            else:
                selected_simulation = "last"
        else:
            raise ValueError("simulation must be first, last, or an integer simulation ID")
        result.simulation = selected_simulation
        window.fit()
        window.draw()

        legend = session.get(hv.LegendScalar, page=page, window=window)
        legend.showMax = True
        legend.showMin = True
        window.draw()

        capture = hw.CaptureImageTool(type="png")
        capture.file = str(image_path)
        capture.width = 1600
        capture.height = 1000
        capture.area = "window"
        capture.capture()
        if not image_path.is_file():
            raise RuntimeError("HyperView capture did not create the requested image")

        query_rows = []
        numeric_rows = []
        query_error = None
        query_entity_count = 0
        query_data_source = None
        try:
            entity_class = hv.Node if entity_key == "node" else hv.Element
            collection = hv.Collection(
                entity_class,
                model=session.get(hv.Model, page=page, window=window),
            )
            # The 2026 constructor infers the default entity binding from the
            # active, fully-loaded contour.  Passing Page/Window explicitly can
            # bypass that inference and construct Collection(None).
            query_tool = hv.QueryResultsTool()
            query_tool.collection = collection
            query_tool.setDataSourceQuery(
                [[entity_key, "id"], ["contour", "value"]]
            )
            query_rows = _jsonable(query_tool.query())
            if not isinstance(query_rows, list):
                query_rows = [query_rows]
            query_entity_count = int(collection.getSize())
            query_data_source = _jsonable(query_tool.getDataSourceQuery())
            for row in query_rows:
                if isinstance(row, (list, tuple)) and len(row) >= 2:
                    try:
                        numeric_value = float(row[-1])
                        if math.isfinite(numeric_value):
                            numeric_rows.append((numeric_value, list(row)))
                    except (TypeError, ValueError):
                        pass
            numeric_rows.sort(key=lambda item: item[0], reverse=True)
        except Exception as exc:
            query_error = str(exc)

        legend_min_raw = _jsonable(legend.minValue)
        legend_max_raw = _jsonable(legend.maxValue)
        try:
            legend_minimum = float(legend_min_raw)
        except (TypeError, ValueError):
            legend_minimum = None
        try:
            legend_maximum = float(legend_max_raw)
        except (TypeError, ValueError):
            legend_maximum = None
        return {
            "postprocessed": True,
            "bridge_version": BRIDGE_VERSION,
            "page_id": int(page.id),
            "page_title": str(page.title),
            "model_file": str(model_path),
            "result_file": str(result_path),
            "subcase_ids": subcase_ids,
            "subcase_labels": subcase_labels,
            "simulation_ids": simulation_ids,
            "selected_simulation": selected_simulation,
            "available_data_types": data_types,
            "available_components": data_components,
            "available_components_error": data_components_error,
            "contour": {
                "requested_data_type": data_type,
                "requested_data_component": data_component,
                "data_type": resolved_data_type,
                "data_component": resolved_data_component,
                "average_mode": normalized_average_mode,
            },
            "legend": {
                "minimum": legend_minimum,
                "maximum": legend_maximum,
                "minimum_raw": legend_min_raw,
                "maximum_raw": legend_max_raw,
            },
            "query": {
                "entity_type": entity_key,
                "entity_count": query_entity_count,
                "row_count": len(query_rows),
                "minimum_row": numeric_rows[-1][1] if numeric_rows else None,
                "maximum_row": numeric_rows[0][1] if numeric_rows else None,
                "top_rows": [row for _, row in numeric_rows[:limit]],
                "data_source": query_data_source,
                "error": query_error,
            },
            "screenshot": {
                "path": str(image_path),
                "size_bytes": image_path.stat().st_size,
            },
        }

    def extract_hypergraph_time_history(
        self,
        model_file: str,
        result_file: str,
        csv_file: str,
        image_file: str,
        data_type: str = "Displacement",
        data_component: str = "Mag",
        entity_type: str = "node",
        entity_ids: list[int] | None = None,
        statistic: str = "maximum",
        curve_label: str = "MCP time history",
    ) -> dict[str, Any]:
        """Extract a frame history from HyperView and render it as a HyperGraph XY curve."""
        import hw
        import hw.hv as hv
        import hw.hg as hg

        model_path = self._safe_input(model_file)
        result_path = self._safe_input(result_file)
        csv_path = self._safe_output(csv_file)
        image_path = self._safe_output(image_file)
        if csv_path.suffix.lower() != ".csv":
            raise ValueError("csv_file must use the .csv extension")
        if image_path.suffix.lower() != ".png":
            raise ValueError("image_file must use the .png extension")
        if entity_type not in {"node", "element"}:
            raise ValueError("entity_type must be node or element")
        if statistic not in {"maximum", "minimum", "mean"}:
            raise ValueError("statistic must be maximum, minimum, or mean")
        selected_ids = None
        if entity_ids is not None:
            selected_ids = {int(value) for value in entity_ids}
            if not selected_ids or any(value <= 0 for value in selected_ids):
                raise ValueError("entity_ids must contain positive IDs")
            if len(selected_ids) > 5000:
                raise ValueError("At most 5000 entity IDs may be requested")
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9 _()/+&.-]{0,79}", data_type):
            raise ValueError("Invalid data_type")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _()/+.-]{0,79}", data_component):
            raise ValueError("Invalid data_component")
        if not isinstance(curve_label, str) or not curve_label.strip() or len(curve_label) > 100:
            raise ValueError("curve_label must contain 1 to 100 characters")

        csv_path.parent.mkdir(parents=True, exist_ok=True)
        image_path.parent.mkdir(parents=True, exist_ok=True)
        session = hw.Session()
        result_page = hw.Page(layout=1, title="MCP history source")
        session.setActive(hw.Page, page=result_page)
        result_window = session.get(hw.Window, page=result_page)
        result_window.type = "animation"
        result_window.addModelAndResult(model=str(model_path), result=str(result_path))
        result = session.get(hv.Result, page=result_page, window=result_window)
        subcases = _jsonable(result.getSubcaseIds())
        selected_subcase = int(subcases[0]) if subcases else 1
        result.subcase = selected_subcase
        scalar = hv.ResultDefinitionScalar(
            dataType=data_type,
            dataComponent=data_component,
            page=result_page,
            window=result_window,
        )
        result.plot(scalar, waitTillLoaded=True)
        simulation_ids = [int(value) for value in _jsonable(result.getSimulationIds(selected_subcase))]
        if not simulation_ids:
            raise RuntimeError("The result does not expose any simulation frames")
        entity_class = hv.Node if entity_type == "node" else hv.Element
        collection = hv.Collection(
            entity_class,
            model=session.get(hv.Model, page=result_page, window=result_window),
        )
        query_tool = hv.QueryResultsTool()
        query_tool.collection = collection
        query_tool.setDataSourceQuery([[entity_type, "id"], ["contour", "value"]])

        history = []
        for frame_index, simulation_id in enumerate(simulation_ids, start=1):
            result.simulation = simulation_id
            result_window.draw()
            rows = _jsonable(query_tool.query())
            values = []
            for row in rows if isinstance(rows, list) else [rows]:
                if not isinstance(row, (list, tuple)) or len(row) < 2:
                    continue
                try:
                    item_id = int(row[0])
                    value = float(row[-1])
                except (TypeError, ValueError):
                    continue
                if math.isfinite(value) and (selected_ids is None or item_id in selected_ids):
                    values.append(value)
            if not values:
                raise RuntimeError(f"Frame {simulation_id} returned no finite contour values")
            if statistic == "maximum":
                aggregate = max(values)
            elif statistic == "minimum":
                aggregate = min(values)
            else:
                aggregate = sum(values) / len(values)
            current_time = None
            try:
                current_time = float(hw.AnimationTool().currentTime)
                if not math.isfinite(current_time):
                    current_time = None
            except Exception:
                pass
            history.append(
                {
                    "frame_index": frame_index,
                    "simulation_id": simulation_id,
                    "time": current_time,
                    "value": aggregate,
                    "sample_count": len(values),
                }
            )

        with csv_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=["frame_index", "simulation_id", "time", "value", "sample_count"],
            )
            writer.writeheader()
            writer.writerows(history)

        graph_page = hw.Page(layout=1, title=curve_label.strip())
        session.setActive(hw.Page, page=graph_page)
        try:
            graph_window = session.get(hw.Window, page=graph_page)
            graph_window.type = "xy"
            curve = hg.CurveXY(label=curve_label.strip())
            x_values = [
                item["time"] if item["time"] is not None else float(item["simulation_id"])
                for item in history
            ]
            y_values = [float(item["value"]) for item in history]
            curve.xValues = x_values
            curve.yValues = y_values
            graph_window.update()
            graph_window.fit()
            capture = hw.CaptureImageTool(type="png")
            capture.file = str(image_path)
            capture.width = 1600
            capture.height = 1000
            capture.area = "window"
            capture.capture()
        finally:
            # The Extension is hosted by the HyperMesh/HyperView client. Leaving an
            # XY page active can trigger its unload hook when HyperWorks changes
            # clients after this request returns. Keep the HyperGraph page in the
            # session, but restore the result page so the localhost bridge remains
            # alive for the next MCP call.
            session.setActive(hw.Page, page=result_page)
        if not csv_path.is_file() or not image_path.is_file():
            raise RuntimeError("HyperGraph history export did not create all requested files")
        return {
            "extracted": True,
            "bridge_version": BRIDGE_VERSION,
            "model_file": str(model_path),
            "result_file": str(result_path),
            "data_type": data_type,
            "data_component": data_component,
            "entity_type": entity_type,
            "entity_ids": sorted(selected_ids) if selected_ids is not None else None,
            "statistic": statistic,
            "simulation_ids": simulation_ids,
            "history": history,
            "csv": {"path": str(csv_path), "size_bytes": csv_path.stat().st_size},
            "screenshot": {"path": str(image_path), "size_bytes": image_path.stat().st_size},
            "hypergraph_page_id": int(graph_page.id),
        }

    def save_model(
        self,
        output_file: str,
        model_name: str | None = None,
        overwrite: bool = False,
        do_not_write_facets: int = 0,
    ) -> dict[str, Any]:
        path = self._safe_output(output_file)
        if path.suffix.lower() != ".hm":
            raise ValueError("output_file must use the .hm extension")
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and not overwrite:
            raise ValueError("Output already exists; set overwrite=true after approval")
        model = self._model(model_name)
        if path.exists() and overwrite:
            model.hm_answernext(answer="yes")
        model.writefile(
            filename=path.as_posix(),
            do_not_write_facets=max(0, min(int(do_not_write_facets), 2)),
        )
        return {"saved": True, "output_file": str(path), "model_name": model_name}
