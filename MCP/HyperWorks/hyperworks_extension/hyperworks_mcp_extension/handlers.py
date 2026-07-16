from __future__ import annotations

import platform
import sys
import threading
from pathlib import Path
from typing import Any


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
            "get_model_metrics": self.get_model_metrics,
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
            "version": "0.2.0",
            "python": sys.version,
            "platform": platform.platform(),
            "execution_thread": threading.current_thread().name,
        }

    def get_capabilities(self) -> dict[str, Any]:
        modules = {}
        for name in ("hm", "hw", "hw.hv", "hwx.gui"):
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
