from __future__ import annotations

import os
import importlib.metadata
import importlib.util
import threading
import time
import uuid
from pathlib import Path
from typing import Any


def _json_value(value: Any) -> Any:
    if hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, dict):
        return {key: _json_value(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def mph_availability() -> dict[str, Any]:
    try:
        spec = importlib.util.find_spec("mph")
        if spec is None:
            return {"available": False, "module": "mph", "error": "Module not found"}
        try:
            version = importlib.metadata.version("mph")
        except Exception:
            version = None
        return {
            "available": True,
            "module": "mph",
            "version": version,
            "origin": spec.origin,
        }
    except Exception as exc:
        return {
            "available": False,
            "module": "mph",
            "error": str(exc),
        }


class ComsolMphSessionManager:
    def __init__(self) -> None:
        self.client: Any | None = None
        self.models: dict[str, Any] = {}
        self.current_model: str | None = None
        self._lock = threading.RLock()
        self._start_job: dict[str, Any] | None = None
        self._start_thread: threading.Thread | None = None

    @property
    def is_connected(self) -> bool:
        return self.client is not None

    def _mph(self) -> Any:
        import mph

        return mph

    def start(
        self,
        cores: int | None = 1,
        version: str | None = None,
        standalone: bool | None = None,
        products: list[str] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            if self.client is not None:
                return {"success": True, "already_connected": True, **self.status()}
            if self._start_job and self._start_job.get("status") in {"queued", "starting", "cancel_requested"}:
                return {
                    "success": False,
                    "status": "already_starting",
                    "message": "COMSOL session startup is already in progress.",
                    "job": self.start_session_status().get("job"),
                }

        return self._start_blocking(cores=cores, version=version, standalone=standalone, products=products)

    def _start_blocking(
        self,
        cores: int | None = 1,
        version: str | None = None,
        standalone: bool | None = None,
        products: list[str] | None = None,
    ) -> dict[str, Any]:
        try:
            mph = self._mph()
            use_standalone = standalone
            if use_standalone is None:
                mode = os.environ.get("COMSOL_MCP_SESSION_MODE", "stand-alone").strip().lower()
                use_standalone = mode in {"stand-alone", "standalone", "local", "true", "1", "yes"}
            if use_standalone:
                mph.option("session", "stand-alone")

            kwargs: dict[str, Any] = {}
            if cores is not None:
                kwargs["cores"] = int(cores)
            if version:
                kwargs["version"] = version
            if products:
                kwargs["products"] = products
            client = mph.Client(**kwargs)
            with self._lock:
                self.client = client
            return {"success": True, "already_connected": False, **self.status()}
        except Exception as exc:
            return {"success": False, "error": str(exc), "mph": mph_availability()}

    def start_async(
        self,
        cores: int | None = 1,
        version: str | None = None,
        standalone: bool | None = None,
        products: list[str] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            if self.client is not None:
                return {"success": True, "already_connected": True, "job": None, "session": self.status()}
            if self._start_job and self._start_job.get("status") in {"queued", "starting", "cancel_requested"}:
                return {"success": True, "already_starting": True, "job": self._job_snapshot(self._start_job)}

            job = {
                "job_id": "comsol_start_" + uuid.uuid4().hex[:12],
                "status": "queued",
                "stage": "queued",
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "params": {
                    "cores": cores,
                    "version": version,
                    "standalone": standalone,
                    "products": products,
                },
                "cancel_requested": False,
                "result": None,
                "error": None,
            }
            self._start_job = job
            thread = threading.Thread(
                target=self._run_start_job,
                args=(job["job_id"], cores, version, standalone, products),
                daemon=True,
                name="comsol-mph-start",
            )
            self._start_thread = thread
            thread.start()
            return {"success": True, "already_starting": False, "job": self._job_snapshot(job)}

    def _run_start_job(
        self,
        job_id: str,
        cores: int | None,
        version: str | None,
        standalone: bool | None,
        products: list[str] | None,
    ) -> None:
        self._update_start_job(job_id, status="starting", stage="initializing_mph_client")
        result = self._start_blocking(cores=cores, version=version, standalone=standalone, products=products)
        with self._lock:
            job = self._start_job
            if not job or job.get("job_id") != job_id:
                return
            if job.get("cancel_requested") and result.get("success"):
                self.disconnect()
                job["status"] = "cancelled"
                job["stage"] = "cancelled_after_start"
                job["result"] = result
                job["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                return
            if result.get("success"):
                job["status"] = "connected"
                job["stage"] = "connected"
                job["result"] = result
                job["error"] = None
            else:
                job["status"] = "failed"
                job["stage"] = "failed"
                job["result"] = None
                job["error"] = result.get("error") or result
            job["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

    def _update_start_job(self, job_id: str, **updates: Any) -> None:
        with self._lock:
            if self._start_job and self._start_job.get("job_id") == job_id:
                self._start_job.update(updates)
                self._start_job["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

    def _job_snapshot(self, job: dict[str, Any]) -> dict[str, Any]:
        return dict(job)

    def start_session_status(self, job_id: str | None = None) -> dict[str, Any]:
        with self._lock:
            if not self._start_job:
                return {"success": True, "job": None, "session": self.status()}
            if job_id is not None and self._start_job.get("job_id") != job_id:
                return {
                    "success": False,
                    "error": f"Unknown COMSOL start job: {job_id}",
                    "job": self._job_snapshot(self._start_job),
                    "session": self.status(),
                }
            return {"success": True, "job": self._job_snapshot(self._start_job), "session": self.status()}

    def cancel_start_session(self, job_id: str | None = None) -> dict[str, Any]:
        with self._lock:
            if not self._start_job:
                return {"success": True, "cancelled": False, "message": "No start job is recorded."}
            if job_id is not None and self._start_job.get("job_id") != job_id:
                return {"success": False, "error": f"Unknown COMSOL start job: {job_id}"}
            if self._start_job.get("status") not in {"queued", "starting"}:
                return {"success": True, "cancelled": False, "job": self._job_snapshot(self._start_job)}
            self._start_job["cancel_requested"] = True
            self._start_job["status"] = "cancel_requested"
            self._start_job["stage"] = "cancel_requested"
            self._start_job["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            return {
                "success": True,
                "cancelled": False,
                "message": "Cancel requested. If COMSOL finishes starting, the session will be disconnected.",
                "job": self._job_snapshot(self._start_job),
            }

    def connect(self, port: int, host: str = "localhost") -> dict[str, Any]:
        if self.client is not None:
            return {"success": False, "error": "COMSOL MPh session already running. Disconnect first."}
        try:
            mph = self._mph()
            self.client = mph.Client(port=int(port), host=host)
            return {"success": True, **self.status()}
        except Exception as exc:
            return {"success": False, "error": str(exc), "mph": mph_availability()}

    def disconnect(self) -> dict[str, Any]:
        if self.client is None:
            return {"success": True, "was_connected": False}
        try:
            if getattr(self.client, "standalone", True):
                self.client.clear()
            else:
                self.client.disconnect()
        except Exception:
            pass
        self.client = None
        self.models.clear()
        self.current_model = None
        return {"success": True, "was_connected": True}

    def status(self) -> dict[str, Any]:
        if self.client is None:
            return {"connected": False, "message": "No active MPh/COMSOL session."}

        model_names: list[str] = []
        try:
            model_names = list(self.client.names())
        except Exception:
            model_names = list(self.models)
        return {
            "connected": True,
            "version": getattr(self.client, "version", None),
            "cores": getattr(self.client, "cores", None),
            "standalone": getattr(self.client, "standalone", None),
            "session_mode": "stand-alone" if getattr(self.client, "standalone", True) else "shared-server",
            "models": model_names,
            "tracked_models": list(self.models),
            "current_model": self.current_model,
        }

    def _track_model(self, model: Any, set_current: bool = True) -> str:
        name = model.name()
        self.models[name] = model
        if set_current or self.current_model is None:
            self.current_model = name
        return name

    def get_model(self, model_name: str | None = None) -> Any | None:
        if model_name is None:
            model_name = self.current_model
        if model_name is None:
            return None
        return self.models.get(model_name)

    def open_model(self, path: str, set_current: bool = True) -> dict[str, Any]:
        if self.client is None:
            if self._start_job and self._start_job.get("status") in {"queued", "starting", "cancel_requested"}:
                return {
                    "success": False,
                    "status": "session_starting",
                    "error": "COMSOL session is still starting. Call comsol_start_session_status_tool and retry after status is connected.",
                    "job": self.start_session_status().get("job"),
                }
            return {"success": False, "error": "No active MPh/COMSOL session. Call comsol_start_session_tool first."}
        model_path = Path(path).expanduser().resolve()
        if not model_path.exists():
            return {"success": False, "error": f"File not found: {model_path}"}
        if model_path.suffix.lower() != ".mph":
            return {"success": False, "error": f"Expected a .mph file: {model_path}"}
        try:
            model = self.client.load(str(model_path))
            name = self._track_model(model, set_current=set_current)
            return {"success": True, "model": self.model_summary(name)}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def new_model(self, name: str | None = None, set_current: bool = True) -> dict[str, Any]:
        if self.client is None:
            return {"success": False, "error": "No active MPh/COMSOL session. Call comsol_start_session_tool first."}
        try:
            model = self.client.create(name)
            tracked_name = self._track_model(model, set_current=set_current)
            return {"success": True, "model": self.model_summary(tracked_name)}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def model_summary(self, model_name: str | None = None) -> dict[str, Any]:
        model = self.get_model(model_name)
        if model is None:
            return {"success": False, "error": f"Model not found: {model_name or 'current model'}"}

        summary: dict[str, Any] = {
            "name": None,
            "file": None,
            "comsol_version": None,
            "parameters": {},
            "components": [],
            "physics": [],
            "studies": [],
            "datasets": [],
            "plots": [],
            "exports": [],
        }
        getters = {
            "name": model.name,
            "file": model.file,
            "comsol_version": model.version,
            "parameters": model.parameters,
            "components": model.components,
            "physics": model.physics,
            "studies": model.studies,
            "datasets": model.datasets,
            "plots": model.plots,
            "exports": model.exports,
        }
        for key, getter in getters.items():
            try:
                summary[key] = _json_value(getter())
            except Exception:
                pass
        return summary

    def list_parameters(self, model_name: str | None = None, evaluate: bool = False) -> dict[str, Any]:
        model = self.get_model(model_name)
        if model is None:
            return {"success": False, "error": f"Model not found: {model_name or 'current model'}"}
        try:
            params = model.parameters(evaluate=evaluate)
            descriptions = model.descriptions()
            return {
                "success": True,
                "parameters": [
                    {"name": name, "value": value, "description": descriptions.get(name, "")}
                    for name, value in params.items()
                ],
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def set_parameter(
        self,
        name: str,
        value: str,
        model_name: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        model = self.get_model(model_name)
        if model is None:
            return {"success": False, "error": f"Model not found: {model_name or 'current model'}"}
        try:
            model.parameter(name, value)
            if description:
                model.description(name, description)
            return {"success": True, "parameter": name, "value": value, "description": description}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def solve(self, study: str | None = None, model_name: str | None = None) -> dict[str, Any]:
        model = self.get_model(model_name)
        if model is None:
            return {"success": False, "error": f"Model not found: {model_name or 'current model'}"}
        try:
            model.solve(study)
            return {"success": True, "model": model.name(), "study": study, "message": "Solve completed."}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def evaluate(
        self,
        expression: Any,
        unit: str | None = None,
        dataset: str | None = None,
        model_name: str | None = None,
    ) -> dict[str, Any]:
        model = self.get_model(model_name)
        if model is None:
            return {"success": False, "error": f"Model not found: {model_name or 'current model'}"}
        try:
            value = model.evaluate(expression, unit=unit, dataset=dataset)
            return {
                "success": True,
                "expression": expression,
                "unit": unit,
                "dataset": dataset,
                "value": _json_value(value),
                "shape": getattr(value, "shape", None),
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def export(self, file_path: str, node_name: str | None = None, model_name: str | None = None) -> dict[str, Any]:
        model = self.get_model(model_name)
        if model is None:
            return {"success": False, "error": f"Model not found: {model_name or 'current model'}"}
        path = Path(file_path).expanduser().resolve()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            model.export(node_name, str(path))
            return {"success": True, "model": model.name(), "node": node_name, "file": str(path)}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def save(
        self,
        file_path: str | None = None,
        model_name: str | None = None,
        format: str | None = None,
    ) -> dict[str, Any]:
        model = self.get_model(model_name)
        if model is None:
            return {"success": False, "error": f"Model not found: {model_name or 'current model'}"}
        try:
            model.save(path=file_path, format=format)
            return {"success": True, "model": model.name(), "file": file_path or model.file(), "format": format or "Comsol"}
        except Exception as exc:
            return {"success": False, "error": str(exc)}
