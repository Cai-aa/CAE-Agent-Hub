"""Version-probed operations, independent of any demonstration model."""
from __future__ import annotations

import importlib
import inspect
import math
import re
import sys
from pathlib import Path

from .handlers import (
    _jsonable, _validate_bool, _validate_entity_id, _validate_entity_type,
    _validate_integer, _validate_write_expectations,
)
from .engineering import EngineeringOperations, SPECS

API_MODULES = ("base", "mesh", "morph", "connections", "session", "constants")
# These describe parameter contracts, not blanket compatibility claims.
OPERATIONS = {
    "open_model": ("base", "Open", {"path": "absolute existing file inside allowed_roots", "replace_current": "true (discards current in-memory model; save first)"}),
    "set_deck": ("base", "SetCurrentDeck", {"deck_name": "NASTRAN|ABAQUS|LSDYNA|RADIOSS|PAMCRASH|FLUENT|OPENFOAM"}),
    "isolate_entities": ("base", "Or", {"entity_type": "exact current-deck type", "entity_ids": "1..200 unique integer IDs"}),
    "hide_entities": ("base", "Not", {"entity_type": "exact current-deck type", "entity_ids": "1..200 unique integer IDs"}),
    "delete_entities": ("base", "DeleteEntity", {"entity_type": "exact current-deck type", "entity_ids": "1..200 unique integer IDs; force=false, compress=false"}),
    "create_curve": ("base", "CurvesNew", {"points": "2..200 finite XYZ triples (smooth interpolating curve, not polyline)"}),
    "smooth_solids": ("mesh", "SolidSmooth", {"entity_type": "SOLID", "entity_ids": "1..200 unique integer IDs; skin frozen"}),
    "reconstruct_shells": ("mesh", "ReconstructShells", {"entity_type": "SHELL", "entity_ids": "1..200 unique integer IDs; uses current ANSA mesh settings"}),
}
OPERATIONS.update(SPECS)
DECK_NAMES = ("NASTRAN", "ABAQUS", "LSDYNA", "RADIOSS", "PAMCRASH", "FLUENT", "OPENFOAM")


class GeneralOperations:
    def __init__(self, registry):
        self.r = registry
        self.engineering = EngineeringOperations(self)

    def module(self, name):
        if name not in API_MODULES:
            raise ValueError("Unsupported module; use " + ", ".join(API_MODULES))
        if self.r._modules_override is not None:
            module = self.r._modules_override.get(name)
            if module is None:
                raise ValueError("UNSUPPORTED_CAPABILITY: ansa." + name)
            return module
        try:
            # Some releases expose constants as an attribute of the extension
            # module, not as an importable ansa.constants Python submodule.
            parent = importlib.import_module("ansa")
            exposed = getattr(parent, name, None)
            if exposed is not None:
                return exposed
            return importlib.import_module("ansa." + name)
        except ImportError as exc:
            raise ValueError("UNSUPPORTED_CAPABILITY: ansa." + name) from exc

    def api(self, module, name):
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,100}", name):
            raise ValueError("API name must be one public identifier, not an expression or dotted path")
        value = getattr(self.module(module), name, None)
        if not callable(value):
            raise ValueError("UNSUPPORTED_CAPABILITY: ansa.%s.%s" % (module, name))
        return value

    def catalog(self):
        operations = {}
        for name, (module, api, parameters) in OPERATIONS.items():
            details = {}
            try:
                self.api(module, api)
                available = True
                if name in SPECS:
                    details = self.engineering.availability(name)
                    available = details['available']
            except ValueError:
                available = False
            operations[name] = {"api": module + "." + api, "available": available,
                                "parameters": parameters, "validation": "runtime_symbol_probe_only", **details}
        return {"operations": operations, "api_modules": list(API_MODULES),
                "compatibility": {"platform": sys.platform, "embedded_python": sys.version,
                                  "minimum_python": "3.9", "other_ansa_versions": "unverified",
                                  "policy": "Probe symbols, reject missing APIs; presence does not prove signature or behavior compatibility."}}

    def search_api(self, module: str, query: str = "", offset: int = 0, limit: int = 50):
        if not isinstance(query, str) or len(query) > 100:
            raise ValueError("query must be at most 100 characters")
        _validate_integer(offset, "offset")
        _validate_integer(limit, "limit")
        if offset < 0 or not 1 <= limit <= 100:
            raise ValueError("offset >= 0 and 1 <= limit <= 100 required")
        obj = self.module(module)
        names = sorted(n for n in dir(obj) if not n.startswith("_") and query.lower() in n.lower())
        return {"module": module, "total": len(names), "names": names[offset:offset + limit],
                "next_offset": offset + limit if offset + limit < len(names) else None,
                "source": "current ANSA process; symbols are not execution guarantees"}

    def api_help(self, module: str, name: str):
        value = self.api(module, name)
        try:
            signature = str(inspect.signature(value))
        except (TypeError, ValueError):
            signature = None
        doc = inspect.getdoc(value) or "No runtime docstring. Consult this ANSA installation's Python API documentation."
        return {"module": module, "name": name, "signature": signature,
                "doc": doc[:20000], "truncated": len(doc) > 20000,
                "source": "current ANSA runtime", "executed": False}

    def entity_fields(self, entity_type: str, entity_id: int):
        _validate_entity_type(entity_type)
        _validate_entity_id(entity_id)
        _, base, _, deck = self.r._context()
        entity = base.GetEntity(deck, entity_type, entity_id)
        if entity is None:
            raise ValueError("Entity not found")
        getter = getattr(entity, "card_fields", None)
        if not callable(getter):
            raise ValueError("UNSUPPORTED_CAPABILITY: Entity.card_fields")
        fields = list(getter(deck))
        return {"deck": int(deck), "entity_type": entity_type, "entity_id": entity_id,
                "fields": fields[:500], "truncated": len(fields) > 500}

    def execute(self, operation: str, parameters: dict, expected_database: str,
                expected_session_nonce: str, expected_deck: int, operation_id: str,
                confirm: bool = False):
        if _validate_bool(confirm, "confirm") is not True:
            raise ValueError("Explicit confirm=true required")
        if not isinstance(operation, str) or operation not in OPERATIONS:
            raise ValueError("Unknown operation; read get_live_capabilities.general_operations")
        if not isinstance(parameters, dict):
            raise ValueError("parameters must be an object")
        module, api_name, schema = OPERATIONS[operation]
        if set(parameters) != set(schema):
            raise ValueError("Exact parameter keys required: " + ", ".join(schema))
        _validate_write_expectations(expected_database, expected_session_nonce)
        _validate_integer(expected_deck, "expected_deck")
        r = self.r
        operation_id = r._operation_id(operation_id)
        fingerprint = r._operation_fingerprint({"operation": operation, "parameters": parameters,
                "database": expected_database, "nonce": expected_session_nonce, "deck": expected_deck})
        r._assert_session(expected_session_nonce)
        cached = r._cached_operation(operation_id, "execute_operation", fingerprint)
        if cached is not None:
            return cached
        _, base, session, deck = r._context()
        r._assert_database(base, expected_database)
        if deck != expected_deck:
            raise RuntimeError("SESSION_CHANGED: current deck differs")
        function = self.api(module, api_name)
        if operation in SPECS:
            run = self.engineering.prepare(operation, parameters, base, deck)
            r._reserve_operation(operation_id, "execute_operation", fingerprint)
            try:
                evidence = run()
                result = {"operation": operation, "api": module + "." + api_name,
                          "operation_id": operation_id, "database_after": str(base.DataBaseName()),
                          "engineering_validation": "not_performed; native completion is not a solver/quality certificate",
                          **evidence}
                return r._record_operation(operation_id, "execute_operation", fingerprint, result)
            except Exception as exc:
                r._raise_outcome_unknown(operation_id, "execute_operation", fingerprint, exc)
        args, kwargs = (), {}
        entity_ids = None
        if "entity_ids" in parameters:
            entity_type = _validate_entity_type(parameters["entity_type"])
            entity_ids = parameters["entity_ids"]
            if not isinstance(entity_ids, list) or not 1 <= len(entity_ids) <= 200:
                raise ValueError("entity_ids must contain 1..200 IDs")
            for identity in entity_ids:
                _validate_entity_id(identity)
            if len(set(entity_ids)) != len(entity_ids):
                raise ValueError("Duplicate entity IDs")
            if operation in ("smooth_solids", "reconstruct_shells"):
                required = "SOLID" if operation == "smooth_solids" else "SHELL"
                if entity_type != required:
                    raise ValueError("This operation requires entity_type=" + required)
            entities = [base.GetEntity(deck, entity_type, identity) for identity in entity_ids]
            if any(entity is None for entity in entities):
                raise ValueError("One or more target entities do not exist; nothing executed")
            args = (entities,)
            if operation == "delete_entities":
                kwargs = {"force": False, "compress": False}
            elif operation == "smooth_solids":
                kwargs = {"freeze_skin": True}
        elif operation == "open_model":
            if parameters["replace_current"] is not True:
                raise ValueError("replace_current=true required; save the current model first")
            path = parameters["path"]
            if not isinstance(path, str) or not Path(path).is_absolute():
                raise ValueError("path must be absolute")
            source = r._allowed_output(path)
            if not source.is_file():
                raise ValueError("Input file does not exist")
            # Only Open-supported database/CAD inputs, never executable scripts.
            if source.suffix.lower() not in (".ansa", ".stp", ".step", ".igs", ".iges", ".x_t", ".x_b", ".prt", ".sldprt", ".sldasm", ".catpart", ".catproduct"):
                raise ValueError("Unsupported Open file suffix; use documented import APIs for solver decks")
            args = (str(source),)
        elif operation == "set_deck":
            name = parameters["deck_name"]
            if name not in DECK_NAMES:
                raise ValueError("Unsupported deck name")
            target_deck = getattr(self.module("constants"), name, None)
            if not isinstance(target_deck, int):
                raise ValueError("UNSUPPORTED_CAPABILITY: constants." + name)
            args = (target_deck,)
        elif operation == "create_curve":
            points = parameters["points"]
            if not isinstance(points, list) or not 2 <= len(points) <= 200:
                raise ValueError("points must contain 2..200 XYZ triples")
            for point in points:
                if not isinstance(point, list) or len(point) != 3 or any(
                    isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in point):
                    raise ValueError("Every point must contain three finite numbers")
            args = (points,)
        r._reserve_operation(operation_id, "execute_operation", fingerprint)
        try:
            returned = function(*args, **kwargs)
            evidence = {"model_effect_verified": False}
            if operation == "set_deck":
                if base.CurrentDeck() != target_deck:
                    raise RuntimeError("Deck readback mismatch")
                evidence = {"model_effect_verified": True, "deck": int(target_deck), "deck_name": str(session.DeckName(target_deck))}
            elif operation == "delete_entities":
                remaining = [i for i in entity_ids if base.GetEntity(deck, entity_type, i) is not None]
                if returned != 0 or remaining:
                    raise RuntimeError("Deletion incomplete; inspect remaining IDs: " + str(remaining))
                evidence = {"model_effect_verified": True, "deleted_ids": list(entity_ids)}
            elif operation == "create_curve":
                if returned is None:
                    raise RuntimeError("CurvesNew returned no entity")
                evidence["created_entity"] = _jsonable(returned)
            elif operation == "open_model" and returned != 0:
                raise RuntimeError("ANSA Open failed with return code " + str(returned))
            elif operation in ("hide_entities", "isolate_entities") and returned != 1:
                raise RuntimeError("Visibility API returned failure")
            result = {"operation": operation, "api": module + "." + api_name,
                      "operation_id": operation_id, "api_return": _jsonable(returned),
                      "database_after": str(base.DataBaseName()), **evidence,
                      "engineering_validation": "not_performed; mesh API returns do not establish mesh quality"}
            return r._record_operation(operation_id, "execute_operation", fingerprint, result)
        except Exception as exc:
            r._raise_outcome_unknown(operation_id, "execute_operation", fingerprint, exc)
