from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import re
import secrets
import sys
import threading
import time
from pathlib import Path
from typing import Any


BRIDGE_VERSION = "0.5.0"
MAX_ENTITY_TYPES = 30
MAX_FIELDS = 30
MAX_ENTITIES_PER_PAGE = 200
MAX_CHECK_ISSUES = 1000
MAX_WRITE_FIELDS = 20
MAX_OPERATION_RECORDS = 256
MAX_LIVE_STEP_HISTORY = 100
MAX_PYTHON_BYTES = 64 * 1024
MAX_PYTHON_RESULT_BYTES = 16 * 1024
MUTATING_METHODS = frozenset({
    "run_model_checks", "save_database", "create_entity",
    "set_entity_card_values", "refresh_view",
    "import_fixed_cantilever", "export_fixed_cantilever", "execute_python_step", "execute_operation",
})
FIXED_CANTILEVER_SHA256 = "aa7b763d488b454495f47ef056d32400e93798cd40e15143e28350a56c61d803"
RUN_ID_RE = re.compile(r"^[0-9a-f]{32}$")

ENTITY_TYPE_RE = re.compile(r"^[A-Za-z0-9_+./ -]{1,80}$")
FIELD_RE = re.compile(r"^[A-Za-z0-9_*:+./ |()\[\]-]{1,120}$")
OPERATION_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{8,128}$")
SESSION_NONCE_RE = re.compile(r"^[0-9a-fA-F]{32}$")

DEFAULT_ENTITY_TYPES = [
    "__MBCONTAINERS__",
    "__PROPERTIES__",
    "__MATERIALS__",
    "__ELEMENTS__",
    "NODE",
    "GRID",
    "SHELL",
    "SOLID",
    "FACE",
    "VOLUME",
]

DEFAULT_ENTITY_FIELDS = ("__id__", "__type__", "Name")

CHECKS = {
    "undefined_materials": ("general", "UndefinedMaterials"),
    "undefined_properties": ("general", "UndefinedProperties"),
    "free_nodes": ("general", "FreeNodes"),
    "duplicate_elements": ("general", "DuplicateElements"),
    "cracks": ("geometry", "Cracks"),
    "single_cons": ("geometry", "SingleCons"),
    "negative_volume": ("mesh", "NegativeVolume"),
    "mesh_quality": ("mesh", "MeshQuality"),
}


def _jsonable(value: Any, depth: int = 0) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if depth >= 5:
        return str(value)
    if isinstance(value, dict):
        return {
            str(key): _jsonable(item, depth + 1)
            for key, item in list(value.items())[:500]
        }
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item, depth + 1) for item in list(value)[:1000]]
    if hasattr(value, "_id"):
        return {
            "id": _jsonable(getattr(value, "_id"), depth + 1),
            "entity_type": str(getattr(value, "_name", value.__class__.__name__)),
        }
    return str(value)


def _validate_entity_type(value: str) -> str:
    if not isinstance(value, str) or not ENTITY_TYPE_RE.fullmatch(value):
        raise ValueError("entity_type contains unsupported characters or length")
    return value


def _validate_fields(fields: list[str] | None) -> list[str]:
    if fields is None:
        values = list(DEFAULT_ENTITY_FIELDS)
    elif not isinstance(fields, list):
        raise ValueError("fields must be a list")
    else:
        values = list(fields)
    if not values or len(values) > MAX_FIELDS:
        raise ValueError(f"fields must contain between 1 and {MAX_FIELDS} entries")
    for value in values:
        if not isinstance(value, str) or not FIELD_RE.fullmatch(value):
            raise ValueError(f"Invalid card field: {value!r}")
    return values


def _validate_scalar_fields(values: dict, *, write: bool) -> dict:
    if not isinstance(values, dict) or not values:
        raise ValueError("values must be a non-empty object")
    limit = MAX_WRITE_FIELDS if write else MAX_FIELDS
    if len(values) > limit:
        raise ValueError(f"At most {limit} fields may be supplied")
    cleaned = {}
    for key, value in values.items():
        if not isinstance(key, str) or not FIELD_RE.fullmatch(key):
            raise ValueError(f"Invalid card field: {key!r}")
        if write and key.startswith("__"):
            raise ValueError("Pseudo fields beginning with '__' are read-only")
        if value is not None and not isinstance(value, (str, int, float, bool)):
            raise ValueError(f"Field {key!r} must contain a JSON scalar value")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"Field {key!r} must be finite")
        if isinstance(value, str) and len(value) > 4096:
            raise ValueError(f"Field {key!r} exceeds 4096 characters")
        cleaned[key] = value
    return cleaned


def _normalized_database(value: str) -> str:
    if not value:
        return ""
    return os.path.normcase(os.path.abspath(value))


def _validate_bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean")
    return value


def _validate_entity_id(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("entity_id must be an integer")
    if value < 0:
        raise ValueError("entity_id must be non-negative")
    return value


def _validate_integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return value


def _validate_write_expectations(
    expected_database: Any, expected_session_nonce: Any
) -> tuple[str, str]:
    if not isinstance(expected_database, str):
        raise ValueError("expected_database must be a string")
    if (
        not isinstance(expected_session_nonce, str)
        or not SESSION_NONCE_RE.fullmatch(expected_session_nonce)
    ):
        raise ValueError(
            "expected_session_nonce must contain exactly 32 hexadecimal characters"
        )
    return expected_database, expected_session_nonce


class HandlerRegistry:
    def __init__(
        self,
        allowed_roots: list[str],
        modules: dict[str, Any] | None = None,
        progress_callback=None,
        step_callback=None,
        enable_examples=False,
    ):
        self.allowed_roots = [Path(item).expanduser().resolve() for item in allowed_roots]
        self._modules_override = modules
        self._progress_callback = progress_callback
        self._step_callback = step_callback
        self._step_sequence = 0
        self._step_history: list[dict[str, Any]] = []
        self._live_cantilever_run: Path | None = None
        self.session_nonce = secrets.token_hex(16)
        self.bridge_main_thread_id = threading.get_ident()
        self._operation_results: dict[
            str, tuple[str, str, str, dict | None]
        ] = {}
        self.methods = {
            "ping": self.ping,
            "get_capabilities": self.get_capabilities,
            "get_session_info": self.get_session_info,
            "get_model_summary": self.get_model_summary,
            "list_entities": self.list_entities,
            "get_entity": self.get_entity,
            "run_model_checks": self.run_model_checks,
            "save_database": self.save_database,
            "create_entity": self.create_entity,
            "set_entity_card_values": self.set_entity_card_values,
            "refresh_view": self.refresh_view,
            "execute_python_step": self.execute_python_step,
            "get_step_history": self.get_step_history,
        }
        if enable_examples:
            self.methods.update({"import_fixed_cantilever": self.import_fixed_cantilever,
                                 "export_fixed_cantilever": self.export_fixed_cantilever,
                                 "set_fixed_cantilever_phase": self.set_fixed_cantilever_phase})
        from .operations import GeneralOperations
        self.general = GeneralOperations(self)
        self.methods.update({"search_api": self.general.search_api,
                             "get_api_help": self.general.api_help,
                             "get_entity_fields": self.general.entity_fields,
                             "execute_operation": self.general.execute})

    @property
    def allowed_methods(self) -> list[str]:
        return sorted(self.methods)

    def dispatch(self, method: str, params: dict[str, Any]) -> Any:
        handler = self.methods.get(method)
        if handler is None:
            raise ValueError(f"Method is not allowlisted: {method}")
        if method not in MUTATING_METHODS:
            return handler(**params)
        operation_id = params.get("operation_id")
        prior_record = self._operation_results.get(operation_id)
        try:
            result = handler(**params)
        except Exception as exc:
            if prior_record is not None and prior_record[2] == "pending":
                # A same-ID retry was rejected before re-execution. Keep the
                # original uncertain event rather than inventing a new step.
                raise
            # A post-mutation exception may leave changed model state. Redraw
            # best-effort, but preserve the original outcome-unknown error.
            redraw = self._redraw_step()
            self._append_step(method, operation_id, "outcome_unknown" if
                              "OUTCOME_UNKNOWN:" in str(exc) else "failed",
                              redraw, error=f"{exc.__class__.__name__}: {exc}"[:500],
                              label=params.get("step_name"))
            raise
        if result.get("idempotent_replay"):
            return result
        if method == "refresh_view":
            redraw = {"returned_success": result["refreshed"],
                      "return_code": result["return_code"]}
        elif method == "import_fixed_cantilever":
            redraw = {
                "returned_success": result["view_fit_and_redraw_returned_success"],
                "return_code": 1,
            }
        else:
            redraw = self._redraw_step()
        event = self._append_step(
            method, operation_id, "completed", redraw,
            label=params.get("step_name")
        )
        result["live_step"] = event
        if operation_id is not None:
            recorded = self._operation_results.get(operation_id)
            if recorded is not None and recorded[2] == "success":
                self._operation_results[operation_id] = (
                    recorded[0], recorded[1], recorded[2], dict(result)
                )
        return result

    def _redraw_step(self) -> dict:
        try:
            return_code = int(self._modules()["base"].RedrawAll())
            return {"returned_success": return_code == 1,
                    "return_code": return_code}
        except Exception as exc:
            return {"returned_success": False,
                    "error": f"{exc.__class__.__name__}: {exc}"[:500]}

    def _append_step(
        self, method: str, operation_id: str | None, status: str,
        redraw: dict, error: str | None = None, label: str | None = None,
    ) -> dict:
        self._step_sequence += 1
        event = {
            "sequence": self._step_sequence,
            "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "method": method,
            "label": label if isinstance(label, str) else method,
            "operation_id": operation_id,
            "status": status,
            "view_refresh": redraw,
        }
        if error is not None:
            event["error"] = error
        self._step_history.append(event)
        if len(self._step_history) > MAX_LIVE_STEP_HISTORY:
            del self._step_history[:-MAX_LIVE_STEP_HISTORY]
        if self._step_callback is not None:
            try:
                self._step_callback(dict(event))
            except Exception:
                # UI feedback cannot change an already committed write result.
                pass
        return event

    def get_step_history(self, limit: int = 20) -> dict:
        limit = _validate_integer(limit, "limit")
        if not 1 <= limit <= MAX_LIVE_STEP_HISTORY:
            raise ValueError(f"limit must be between 1 and {MAX_LIVE_STEP_HISTORY}")
        return {"session_nonce": self.session_nonce,
                "latest_sequence": self._step_sequence,
                "steps": [dict(item) for item in self._step_history[-limit:]]}

    def _modules(self) -> dict[str, Any]:
        if self._modules_override is not None:
            return self._modules_override
        from ansa import base, constants, session
        try:
            from ansa.base import checks
        except ImportError:
            checks = None

        return {
            "base": base,
            "constants": constants,
            "session": session,
            "checks": checks,
        }

    def _context(self):
        modules = self._modules()
        base = modules["base"]
        session = modules["session"]
        deck = base.CurrentDeck()
        return modules, base, session, deck

    @staticmethod
    def _entity_id(entity: Any) -> int | None:
        value = getattr(entity, "_id", None)
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _entity_type(base: Any, deck: int, entity: Any, fallback: str) -> str:
        try:
            return str(base.GetEntityType(deck, entity))
        except Exception:
            return str(getattr(entity, "_name", fallback))

    def _serialize_entity(
        self,
        base: Any,
        deck: int,
        entity: Any,
        entity_type: str,
        fields: list[str],
    ) -> dict:
        result = {
            "id": self._entity_id(entity),
            "entity_type": self._entity_type(base, deck, entity, entity_type),
        }
        try:
            result["card_values"] = _jsonable(
                base.GetEntityCardValues(deck, entity, tuple(fields))
            )
        except Exception as exc:
            result["card_values"] = None
            result["card_error"] = f"{exc.__class__.__name__}: {exc}"
        return result

    @staticmethod
    def _operation_id(value: str) -> str:
        if not isinstance(value, str) or not OPERATION_ID_RE.fullmatch(value):
            raise ValueError("operation_id must be 8-128 safe characters")
        return value

    @staticmethod
    def _operation_fingerprint(value: dict[str, Any]) -> str:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _cached_operation(
        self, operation_id: str, method: str, fingerprint: str
    ) -> dict | None:
        item = self._operation_results.get(operation_id)
        if item is None:
            return None
        recorded_method, recorded_fingerprint, state, result = item
        if recorded_method != method:
            raise ValueError("operation_id was already used for another method")
        if recorded_fingerprint != fingerprint:
            raise ValueError("operation_id was already used with different parameters")
        if state == "pending":
            raise RuntimeError(
                f"OUTCOME_UNKNOWN: operation_id={operation_id}; a prior mutation "
                "started but no verified result was recorded"
            )
        if state != "success" or result is None:
            raise RuntimeError("IDEMPOTENCY_STATE_ERROR: invalid operation ledger state")
        replay = dict(result)
        replay["idempotent_replay"] = True
        return replay

    def _reserve_operation(
        self, operation_id: str, method: str, fingerprint: str
    ) -> None:
        if operation_id in self._operation_results:
            raise RuntimeError("IDEMPOTENCY_STATE_ERROR: operation was not resolved")
        if len(self._operation_results) >= MAX_OPERATION_RECORDS:
            raise RuntimeError(
                "PRECONDITION_FAILED: operation ledger is full; refusing to "
                "start another mutation"
            )
        self._operation_results[operation_id] = (
            method,
            fingerprint,
            "pending",
            None,
        )

    def _record_operation(
        self, operation_id: str, method: str, fingerprint: str, result: dict
    ) -> dict:
        pending = self._operation_results.get(operation_id)
        if pending != (method, fingerprint, "pending", None):
            raise RuntimeError("IDEMPOTENCY_STATE_ERROR: pending operation is missing")
        self._operation_results[operation_id] = (
            method,
            fingerprint,
            "success",
            dict(result),
        )
        return result

    def _raise_outcome_unknown(
        self,
        operation_id: str,
        method: str,
        fingerprint: str,
        exc: Exception,
    ) -> None:
        """Fail closed after a durable mutation has been admitted.

        Once an operation is reserved, even a ValueError or TypeError can be a
        post-mutation API/readback/conversion failure.  Preserve the pending
        record so an identical retry cannot repeat the mutation, and expose a
        single error class/message that the bridge cannot mistake for bad
        request parameters.
        """
        self._operation_results[operation_id] = (
            method,
            fingerprint,
            "pending",
            None,
        )
        raise RuntimeError(
            f"OUTCOME_UNKNOWN: operation_id={operation_id}; mutation started "
            "but no verified result was recorded "
            f"({exc.__class__.__name__}: {exc})"
        ) from exc

    def _assert_session(self, expected_session_nonce: str) -> None:
        if expected_session_nonce != self.session_nonce:
            raise RuntimeError(
                "SESSION_CHANGED: bridge session does not match expected_session_nonce"
            )

    def _assert_database(self, base: Any, expected_database: str) -> str:
        actual = str(base.DataBaseName())
        if _normalized_database(actual) != _normalized_database(expected_database):
            raise RuntimeError(
                "SESSION_CHANGED: current database does not match expected_database"
            )
        return actual

    def _allowed_output(self, value: str) -> Path:
        target = Path(value).expanduser().resolve()
        for root in self.allowed_roots:
            try:
                target.relative_to(root)
                return target
            except ValueError:
                continue
        raise ValueError(f"PATH_NOT_ALLOWED: {target}")

    def _fixed_cantilever_source(self, value: str) -> Path:
        source = self._allowed_output(value)
        if (
            source.name != "cantilever_source.inp"
            or source.parent.parent.name != "cantilever_demo"
            or RUN_ID_RE.fullmatch(source.parent.name) is None
            or not source.is_file()
        ):
            raise ValueError("PRECONDITION_FAILED: invalid fixed cantilever source path")
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        if digest != FIXED_CANTILEVER_SHA256:
            raise ValueError("PRECONDITION_FAILED: fixed cantilever source hash differs")
        return source

    def _demo_progress(self, run_id: str, phase: str) -> None:
        if self._progress_callback is not None:
            self._progress_callback(run_id, phase)

    def import_fixed_cantilever(
        self,
        source_path: str,
        expected_database: str,
        expected_session_nonce: str,
        operation_id: str,
        confirm: bool = False,
    ) -> dict:
        """Import only the byte-identical fixed deck into an empty GUI model."""
        if confirm is not True:
            raise ValueError("confirm=true is required to import the live demo")
        expected_database, expected_session_nonce = _validate_write_expectations(
            expected_database, expected_session_nonce
        )
        operation_id = self._operation_id(operation_id)
        source = self._fixed_cantilever_source(source_path)
        fingerprint = self._operation_fingerprint({
            "source": str(source),
            "expected_database": _normalized_database(expected_database),
            "expected_session_nonce": expected_session_nonce,
        })
        cached = self._cached_operation(operation_id, "import_fixed_cantilever", fingerprint)
        if cached is not None:
            return cached
        modules, base, session, deck = self._context()
        self._assert_session(expected_session_nonce)
        database = self._assert_database(base, expected_database)
        if self._live_cantilever_run is not None:
            raise RuntimeError("PRECONDITION_FAILED: this bridge already imported a live demo")
        inspected_types = (
            "NODE", "__ELEMENTS__", "__MATERIALS__", "__PROPERTIES__",
            "FACE", "VOLUME", "SHELL", "SOLID",
        )
        nonempty = {}
        for kind in inspected_types:
            count = len(base.CollectEntities(deck, None, kind))
            if count:
                nonempty[kind] = count
        if nonempty:
            raise RuntimeError(
                "PRECONDITION_FAILED: open a new empty ANSA model before the live demo: "
                + str(nonempty)
            )
        self._reserve_operation(operation_id, "import_fixed_cantilever", fingerprint)
        try:
            self._demo_progress(source.parent.name, "importing")
            base.SetCurrentDeck(modules["constants"].ABAQUS)
            imported = base.InputAbaqus(str(source))
            abaqus = modules["constants"].ABAQUS
            nodes = len(base.CollectEntities(abaqus, None, "NODE"))
            elements = len(base.CollectEntities(abaqus, None, "__ELEMENTS__"))
            materials = len(base.CollectEntities(abaqus, None, "__MATERIALS__"))
            if (nodes, elements, materials) != (615, 320, 1):
                raise RuntimeError(
                    "ANSA live import counts differ from 615 nodes, 320 elements, 1 material"
                )
            if int(base.ZoomAll()) != 1:
                raise RuntimeError("ANSA did not fit the imported model in the GUI")
            if int(base.RedrawAll()) != 1:
                raise RuntimeError("ANSA did not redraw the imported model")
            self._live_cantilever_run = source.parent
            result = {
                "imported": True,
                "import_return": str(imported),
                "node_count": nodes,
                "element_count": elements,
                "material_count": materials,
                "source_sha256": FIXED_CANTILEVER_SHA256,
                "database": database,
                "run_id": source.parent.name,
                "view_fit_and_redraw_returned_success": True,
                "operation_id": operation_id,
                "idempotent_replay": False,
            }
            self._demo_progress(source.parent.name, "model_visible")
            return self._record_operation(
                operation_id, "import_fixed_cantilever", fingerprint, result
            )
        except Exception as exc:
            self._raise_outcome_unknown(
                operation_id, "import_fixed_cantilever", fingerprint, exc
            )

    def export_fixed_cantilever(
        self,
        source_path: str,
        expected_database: str,
        expected_session_nonce: str,
        operation_id: str,
        confirm: bool = False,
    ) -> dict:
        """Save and export the fixed demo from the currently visible ANSA model."""
        if confirm is not True:
            raise ValueError("confirm=true is required to export the live demo")
        expected_database, expected_session_nonce = _validate_write_expectations(
            expected_database, expected_session_nonce
        )
        operation_id = self._operation_id(operation_id)
        source = self._fixed_cantilever_source(source_path)
        fingerprint = self._operation_fingerprint({
            "source": str(source),
            "expected_database": _normalized_database(expected_database),
            "expected_session_nonce": expected_session_nonce,
        })
        cached = self._cached_operation(operation_id, "export_fixed_cantilever", fingerprint)
        if cached is not None:
            return cached
        modules, base, session, deck = self._context()
        self._assert_session(expected_session_nonce)
        database = self._assert_database(base, expected_database)
        if self._live_cantilever_run != source.parent:
            raise RuntimeError("PRECONDITION_FAILED: this session did not import that run")
        abaqus = modules["constants"].ABAQUS
        counts = (
            len(base.CollectEntities(abaqus, None, "NODE")),
            len(base.CollectEntities(abaqus, None, "__ELEMENTS__")),
            len(base.CollectEntities(abaqus, None, "__MATERIALS__")),
        )
        if counts != (615, 320, 1):
            raise RuntimeError("PRECONDITION_FAILED: live demo model counts changed")
        database_path = source.parent / "cantilever.ansa"
        exported = source.parent / "cantilever_ansa_export.inp"
        if database_path.exists() or exported.exists():
            raise FileExistsError("FILE_EXISTS: demo output already exists")
        self._reserve_operation(operation_id, "export_fixed_cantilever", fingerprint)
        try:
            base.SetCurrentDeck(abaqus)
            if int(base.SaveAs(str(database_path), silent=True)) != 0 or not database_path.is_file():
                raise RuntimeError("ANSA did not save a live model snapshot")
            base.OutputAbaqus(str(exported), mode="all", disregard_includes="on")
            if not exported.is_file() or exported.stat().st_size < 1000:
                raise RuntimeError("ANSA did not export a usable Abaqus deck")
            result = {
                "exported": True,
                "database": database,
                "snapshot": str(database_path),
                "exported_deck": str(exported),
                "exported_bytes": exported.stat().st_size,
                "run_id": source.parent.name,
                "operation_id": operation_id,
                "idempotent_replay": False,
            }
            self._demo_progress(source.parent.name, "exported")
            return self._record_operation(
                operation_id, "export_fixed_cantilever", fingerprint, result
            )
        except Exception as exc:
            self._raise_outcome_unknown(
                operation_id, "export_fixed_cantilever", fingerprint, exc
            )

    def set_fixed_cantilever_phase(self, run_id: str, phase: str) -> dict:
        if not isinstance(run_id, str) or RUN_ID_RE.fullmatch(run_id) is None:
            raise ValueError("invalid run_id")
        if self._live_cantilever_run is None or self._live_cantilever_run.name != run_id:
            raise RuntimeError("PRECONDITION_FAILED: run is not open in this ANSA session")
        if phase not in {"solving", "solved", "verified", "solver_failed"}:
            raise ValueError("invalid demo phase")
        self._demo_progress(run_id, phase)
        return {
            "run_id": run_id,
            "phase": phase,
            "displayed_in_bridge": self._progress_callback is not None,
        }

    def ping(self) -> dict:
        modules, base, session, deck = self._context()
        return {
            "bridge": "ansa-mcp-bridge",
            "bridge_version": BRIDGE_VERSION,
            "pid": os.getpid(),
            "python": sys.version,
            "platform": platform.platform(),
            "thread_name": threading.current_thread().name,
            "thread_id": threading.get_ident(),
            "bridge_main_thread_id": self.bridge_main_thread_id,
            "session_nonce": self.session_nonce,
            "deck": int(deck),
            "deck_name": str(session.DeckName(deck)),
            "database": str(base.DataBaseName()),
        }

    def get_capabilities(self) -> dict:
        modules, base, session, deck = self._context()
        available_checks = {}
        checks = modules["checks"]
        for name, (group_name, factory_name) in CHECKS.items():
            try:
                factory = getattr(getattr(checks, group_name), factory_name)
                check = factory()
                available_checks[name] = bool(check.is_available_in_deck(deck))
            except Exception:
                available_checks[name] = False
        return {
            "bridge_version": BRIDGE_VERSION,
            "methods": self.allowed_methods,
            "general_operations": self.general.catalog(),
            "current_deck": int(deck),
            "current_deck_name": str(session.DeckName(deck)),
            "checks": available_checks,
            "default_summary_entity_types": list(DEFAULT_ENTITY_TYPES),
            "entity_type_policy": (
                "bounded safe-name validation followed by ANSA current-deck validation"
            ),
            "card_field_policy": (
                "bounded safe-name/scalar validation followed by ANSA edit-card validation"
            ),
            "save_roots": [str(root) for root in self.allowed_roots],
            "limits": {
                "entity_types_per_summary": MAX_ENTITY_TYPES,
                "fields_per_entity": MAX_FIELDS,
                "entities_per_page": MAX_ENTITIES_PER_PAGE,
                "check_issues": MAX_CHECK_ISSUES,
                "write_fields": MAX_WRITE_FIELDS,
            },
            "arbitrary_python": True,
            "arbitrary_python_step": True,
            "python_step_limit_bytes": MAX_PYTHON_BYTES,
            "live_step_history_limit": MAX_LIVE_STEP_HISTORY,
            "official_listener_backend_enabled": False,
        }

    def get_session_info(self) -> dict:
        modules, base, session, deck = self._context()
        try:
            application = session.ApplicationInformation("dict")
        except Exception:
            application = session.ApplicationInformation("text")
        return {
            "application": _jsonable(application),
            "pid": os.getpid(),
            "python": sys.version,
            "deck": int(deck),
            "deck_name": str(session.DeckName(deck)),
            "database": str(base.DataBaseName()),
            "thread_name": threading.current_thread().name,
            "thread_id": threading.get_ident(),
            "bridge_main_thread_id": self.bridge_main_thread_id,
            "session_nonce": self.session_nonce,
        }

    def get_model_summary(
        self,
        entity_types: list[str] | None = None,
        visible_only: bool = False,
    ) -> dict:
        visible_only = _validate_bool(visible_only, "visible_only")
        if entity_types is None:
            requested = list(DEFAULT_ENTITY_TYPES)
        elif not isinstance(entity_types, list) or not entity_types:
            raise ValueError("entity_types must be a non-empty list")
        else:
            requested = entity_types
        if len(requested) > MAX_ENTITY_TYPES:
            raise ValueError(f"At most {MAX_ENTITY_TYPES} entity types may be queried")
        modules, base, session, deck = self._context()
        counts = {}
        errors = {}
        for raw in requested:
            entity_type = _validate_entity_type(raw)
            try:
                counts[entity_type] = len(
                    base.CollectEntities(
                        deck,
                        None,
                        entity_type,
                        recursive=False,
                        filter_visible=visible_only,
                    )
                )
            except Exception as exc:
                errors[entity_type] = f"{exc.__class__.__name__}: {exc}"
        return {
            "deck": int(deck),
            "deck_name": str(session.DeckName(deck)),
            "database": str(base.DataBaseName()),
            "visible_only": visible_only,
            "counts": counts,
            "errors": errors,
        }

    def list_entities(
        self,
        entity_type: str,
        fields: list[str] | None = None,
        limit: int = 100,
        offset: int = 0,
        visible_only: bool = False,
    ) -> dict:
        visible_only = _validate_bool(visible_only, "visible_only")
        entity_type = _validate_entity_type(entity_type)
        fields = _validate_fields(fields)
        limit = _validate_integer(limit, "limit")
        offset = _validate_integer(offset, "offset")
        if not 1 <= limit <= MAX_ENTITIES_PER_PAGE:
            raise ValueError(f"limit must be between 1 and {MAX_ENTITIES_PER_PAGE}")
        if offset < 0:
            raise ValueError("offset must be non-negative")
        modules, base, session, deck = self._context()
        entities = list(
            base.CollectEntities(
                deck,
                None,
                entity_type,
                recursive=False,
                filter_visible=visible_only,
            )
        )
        page = entities[offset : offset + limit]
        return {
            "entity_type": entity_type,
            "offset": offset,
            "limit": limit,
            "total": len(entities),
            "has_more": offset + len(page) < len(entities),
            "entities": [
                self._serialize_entity(base, deck, entity, entity_type, fields)
                for entity in page
            ],
        }

    def get_entity(
        self,
        entity_type: str,
        entity_id: int,
        fields: list[str] | None = None,
    ) -> dict:
        modules, base, session, deck = self._context()
        entity_type = _validate_entity_type(entity_type)
        fields = _validate_fields(fields)
        entity_id = _validate_entity_id(entity_id)
        entity = base.GetEntity(deck, entity_type, entity_id)
        if entity is None:
            raise ValueError(f"Entity not found: {entity_type} {entity_id}")
        return self._serialize_entity(base, deck, entity, entity_type, fields)

    def _serialize_report(self, report: Any, remaining: list[int], depth: int = 0) -> dict:
        if remaining[0] <= 0:
            return {"truncated": True}
        remaining[0] -= 1
        result = {
            "type": str(getattr(report, "type", "")),
            "status": str(getattr(report, "status", "")),
            "description": str(getattr(report, "description", "")),
            "has_fix": bool(getattr(report, "has_fix", False)),
            "entities": [],
        }
        for entity in list(getattr(report, "entities", []) or [])[:50]:
            result["entities"].append(
                {
                    "id": self._entity_id(entity),
                    "entity_type": str(
                        getattr(entity, "_name", entity.__class__.__name__)
                    ),
                }
            )
        if depth < 4:
            result["issues"] = [
                self._serialize_report(child, remaining, depth + 1)
                for child in list(getattr(report, "issues", []) or [])
                if remaining[0] > 0
            ]
        return result

    def run_model_checks(
        self,
        check_names: list[str] | None = None,
        max_issues: int = 200,
    ) -> dict:
        if check_names is None:
            requested = list(CHECKS)
        elif not isinstance(check_names, list) or not check_names:
            raise ValueError("check_names must be a non-empty list")
        else:
            requested = check_names
        if len(requested) > len(CHECKS):
            raise ValueError("Too many checks requested")
        max_issues = _validate_integer(max_issues, "max_issues")
        if not 1 <= max_issues <= MAX_CHECK_ISSUES:
            raise ValueError(f"max_issues must be between 1 and {MAX_CHECK_ISSUES}")
        unknown = sorted(set(requested) - set(CHECKS))
        if unknown:
            raise ValueError("Unsupported checks: " + ", ".join(unknown))

        modules, base, session, deck = self._context()
        results = {}
        checks = modules["checks"]
        total_remaining = [max_issues]
        for name in requested:
            group_name, factory_name = CHECKS[name]
            try:
                check = getattr(getattr(checks, group_name), factory_name)()
                if not check.is_available_in_deck(deck):
                    results[name] = {"available": False, "reports": []}
                    continue
                reports = check.execute(
                    exec_mode=base.Check.EXEC_ON_ALL,
                    report=base.Check.REPORT_NONE,
                    history=base.Check.KEEP_OLD,
                )
                serialized = []
                for report in list(reports or []):
                    if total_remaining[0] <= 0:
                        break
                    serialized.append(self._serialize_report(report, total_remaining))
                results[name] = {
                    "available": True,
                    "reports": serialized,
                    "truncated": total_remaining[0] <= 0,
                }
            except Exception as exc:
                results[name] = {
                    "available": True,
                    "error": f"{exc.__class__.__name__}: {exc}",
                    "reports": [],
                }
        return {
            "deck": int(deck),
            "deck_name": str(session.DeckName(deck)),
            "database": str(base.DataBaseName()),
            "requested": requested,
            "max_issues": max_issues,
            "results": results,
        }

    def save_database(
        self,
        path: str,
        expected_database: str,
        expected_session_nonce: str,
        operation_id: str,
        confirm: bool = False,
        overwrite: bool = False,
    ) -> dict:
        if confirm is not True:
            raise ValueError("confirm=true is required to save the live database")
        expected_database, expected_session_nonce = _validate_write_expectations(
            expected_database, expected_session_nonce
        )
        overwrite = _validate_bool(overwrite, "overwrite")
        operation_id = self._operation_id(operation_id)
        target = self._allowed_output(path)
        if target.suffix.lower() != ".ansa":
            raise ValueError("Only .ansa output is allowed")
        fingerprint = self._operation_fingerprint(
            {
                "path": str(target),
                "expected_database": _normalized_database(expected_database),
                "expected_session_nonce": expected_session_nonce,
                "overwrite": overwrite,
            }
        )
        cached = self._cached_operation(
            operation_id, "save_database", fingerprint
        )
        if cached is not None:
            return cached
        modules, base, session, deck = self._context()
        self._assert_session(expected_session_nonce)
        self._assert_database(base, expected_database)
        if target.exists() and not overwrite:
            raise FileExistsError(f"FILE_EXISTS: {target}")
        self._reserve_operation(operation_id, "save_database", fingerprint)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            previous = str(base.DataBaseName())
            # ANSA returns 0 on success and 1 on failure.  silent=True keeps the
            # active database pathname unchanged, so this is a verified snapshot
            # rather than a session rename.
            return_code = int(base.SaveAs(str(target), silent=True))
            if return_code != 0 or not target.is_file():
                raise RuntimeError(
                    "SaveAs did not produce a verified file "
                    f"(return_code={return_code})"
                )
            digest_builder = hashlib.sha256()
            with target.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest_builder.update(chunk)
            digest = digest_builder.hexdigest()
            result = {
                "saved": True,
                "silent_snapshot": True,
                "return_code": return_code,
                "previous_database": previous,
                "database": str(base.DataBaseName()),
                "path": str(target),
                "size": target.stat().st_size,
                "sha256": digest,
                "operation_id": operation_id,
                "idempotent_replay": False,
            }
            return self._record_operation(
                operation_id, "save_database", fingerprint, result
            )
        except Exception as exc:
            self._raise_outcome_unknown(
                operation_id, "save_database", fingerprint, exc
            )

    def create_entity(
        self,
        entity_type: str,
        fields: dict,
        expected_database: str,
        expected_session_nonce: str,
        operation_id: str,
        confirm: bool = False,
    ) -> dict:
        if confirm is not True:
            raise ValueError("confirm=true is required to create an entity")
        expected_database, expected_session_nonce = _validate_write_expectations(
            expected_database, expected_session_nonce
        )
        operation_id = self._operation_id(operation_id)
        entity_type = _validate_entity_type(entity_type)
        fields = _validate_scalar_fields(fields, write=True)
        fingerprint = self._operation_fingerprint(
            {
                "entity_type": entity_type,
                "fields": fields,
                "expected_database": _normalized_database(expected_database),
                "expected_session_nonce": expected_session_nonce,
            }
        )
        cached = self._cached_operation(
            operation_id, "create_entity", fingerprint
        )
        if cached is not None:
            return cached
        modules, base, session, deck = self._context()
        self._assert_session(expected_session_nonce)
        database = self._assert_database(base, expected_database)
        self._reserve_operation(operation_id, "create_entity", fingerprint)
        try:
            entity = base.CreateEntity(deck, entity_type, fields)
            if entity is None:
                raise RuntimeError("CreateEntity returned no entity")
            requested_fields = list(fields)
            actual_card_values = _jsonable(
                base.GetEntityCardValues(deck, entity, tuple(requested_fields))
            )
            card_values_verified = actual_card_values == fields
            if not card_values_verified:
                raise RuntimeError(
                    "CreateEntity card readback mismatch: "
                    f"expected {fields}, got {actual_card_values}"
                )
            entity_data = {
                "id": self._entity_id(entity),
                "entity_type": self._entity_type(base, deck, entity, entity_type),
                "card_values": actual_card_values,
            }
            result = {
                "created": True,
                "database": database,
                "entity": entity_data,
                "card_values_verified": card_values_verified,
                "card_values_expected": fields,
                "card_values_actual": actual_card_values,
                "operation_id": operation_id,
                "idempotent_replay": False,
            }
            return self._record_operation(
                operation_id, "create_entity", fingerprint, result
            )
        except Exception as exc:
            self._raise_outcome_unknown(
                operation_id, "create_entity", fingerprint, exc
            )

    def set_entity_card_values(
        self,
        entity_type: str,
        entity_id: int,
        values: dict,
        expected_values: dict,
        expected_database: str,
        expected_session_nonce: str,
        operation_id: str,
        confirm: bool = False,
    ) -> dict:
        if confirm is not True:
            raise ValueError("confirm=true is required to change entity card values")
        expected_database, expected_session_nonce = _validate_write_expectations(
            expected_database, expected_session_nonce
        )
        operation_id = self._operation_id(operation_id)
        entity_type = _validate_entity_type(entity_type)
        values = _validate_scalar_fields(values, write=True)
        expected_values = _validate_scalar_fields(expected_values, write=False)
        if set(values) != set(expected_values):
            raise ValueError("expected_values must contain exactly the fields being changed")
        entity_id = _validate_entity_id(entity_id)
        fingerprint = self._operation_fingerprint(
            {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "values": values,
                "expected_values": expected_values,
                "expected_database": _normalized_database(expected_database),
                "expected_session_nonce": expected_session_nonce,
            }
        )
        cached = self._cached_operation(
            operation_id, "set_entity_card_values", fingerprint
        )
        if cached is not None:
            return cached
        modules, base, session, deck = self._context()
        self._assert_session(expected_session_nonce)
        database = self._assert_database(base, expected_database)
        entity = base.GetEntity(deck, entity_type, entity_id)
        if entity is None:
            raise ValueError(f"Entity not found: {entity_type} {entity_id}")
        before = _jsonable(
            base.GetEntityCardValues(deck, entity, tuple(values.keys()))
        )
        if before != expected_values:
            raise RuntimeError(
                f"PRECONDITION_FAILED: current values differ from expected_values: {before}"
            )
        self._reserve_operation(
            operation_id, "set_entity_card_values", fingerprint
        )
        try:
            return_code = base.SetEntityCardValues(deck, entity, values)
            if isinstance(return_code, tuple):
                failures = int(return_code[0])
            else:
                failures = int(return_code)
            if failures != 0:
                raise RuntimeError(
                    f"SetEntityCardValues rejected {failures} field(s): {return_code}"
                )
            after = _jsonable(
                base.GetEntityCardValues(deck, entity, tuple(values.keys()))
            )
            if after != values:
                raise RuntimeError(
                    f"Entity card readback mismatch: expected {values}, got {after}"
                )
            result = {
                "updated": True,
                "database": database,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "before": before,
                "after": after,
                "operation_id": operation_id,
                "idempotent_replay": False,
            }
            return self._record_operation(
                operation_id, "set_entity_card_values", fingerprint, result
            )
        except Exception as exc:
            self._raise_outcome_unknown(
                operation_id, "set_entity_card_values", fingerprint, exc
            )

    def refresh_view(self, confirm: bool = False) -> dict:
        if confirm is not True:
            raise ValueError("confirm=true is required to refresh the ANSA view")
        modules, base, session, deck = self._context()
        result = int(base.RedrawAll())
        return {"refreshed": result > 0, "return_code": result}

    def execute_python_step(
        self,
        step_name: str,
        code: str,
        expected_database: str,
        expected_session_nonce: str,
        expected_deck: int,
        operation_id: str,
        confirm: bool = False,
    ) -> dict:
        """Execute one explicitly authorized Python step on ANSA's GUI thread.

        This is intentionally *not* a sandbox. It has the same local authority
        as ANSA's embedded Python interpreter. Each MCP call should represent
        one observable operation; a long script cannot yield GUI frames here.
        """
        if confirm is not True:
            raise ValueError("confirm=true is required for arbitrary ANSA Python")
        expected_database, expected_session_nonce = _validate_write_expectations(
            expected_database, expected_session_nonce
        )
        expected_deck = _validate_integer(expected_deck, "expected_deck")
        operation_id = self._operation_id(operation_id)
        if (not isinstance(step_name, str) or not 1 <= len(step_name) <= 120
                or any(ord(char) < 32 for char in step_name)):
            raise ValueError("step_name must be 1-120 printable characters")
        if not isinstance(code, str) or not code.strip():
            raise ValueError("code must be non-empty Python source")
        source = code.encode("utf-8")
        if len(source) > MAX_PYTHON_BYTES:
            raise ValueError(f"code exceeds {MAX_PYTHON_BYTES} UTF-8 bytes")
        compiled = compile(code, f"<ansa-mcp:{operation_id}>", "exec")
        code_sha256 = hashlib.sha256(source).hexdigest()
        fingerprint = self._operation_fingerprint({
            "step_name": step_name,
            "code_sha256": code_sha256,
            "expected_database": _normalized_database(expected_database),
            "expected_session_nonce": expected_session_nonce,
            "expected_deck": expected_deck,
        })
        cached = self._cached_operation(operation_id, "execute_python_step", fingerprint)
        if cached is not None:
            return cached
        modules, base, session, deck = self._context()
        self._assert_session(expected_session_nonce)
        database_before = self._assert_database(base, expected_database)
        if int(deck) != expected_deck:
            raise RuntimeError("SESSION_CHANGED: current deck does not match expected_deck")
        self._reserve_operation(operation_id, "execute_python_step", fingerprint)
        try:
            globals_for_step = {
                "__name__": "__ansa_mcp_step__",
                "base": base,
                "session": session,
                "constants": modules["constants"],
                "deck": deck,
                "result": None,
            }
            exec(compiled, globals_for_step)
            output = _jsonable(globals_for_step.get("result"))
            output_bytes = json.dumps(output, ensure_ascii=False).encode("utf-8")
            if len(output_bytes) > MAX_PYTHON_RESULT_BYTES:
                output = {"truncated": True, "byte_count": len(output_bytes)}
            result = {
                "execution_returned": True,
                "model_effect_verified": False,
                "step_name": step_name,
                "code_sha256": code_sha256,
                "python_result": output,
                "database_before": database_before,
                "database_after": str(base.DataBaseName()),
                "deck_before": int(deck),
                "deck_after": int(base.CurrentDeck()),
                "operation_id": operation_id,
                "idempotent_replay": False,
            }
            return self._record_operation(
                operation_id, "execute_python_step", fingerprint, result
            )
        except Exception as exc:
            self._raise_outcome_unknown(
                operation_id, "execute_python_step", fingerprint, exc
            )
