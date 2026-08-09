# encoding: utf-8
"""Workbench MCP queue processor for ANSYS Mechanical.

Run inside Mechanical from Automation > Scripting > Run Script.

This script is deliberately conservative:
- no socket server
- no Python/.NET background threads
- no long-running loop

It processes queued JSON request files once on Mechanical's script/main context
and writes JSON response files. Codex/Claude MCP tools write requests into the
queue directory, then you run this processor from Mechanical to execute them.
"""

from __future__ import print_function

import os
import sys
import time
import traceback

try:
    from StringIO import StringIO
except Exception:
    from io import StringIO


PLUGIN_DIR = os.path.abspath(os.path.dirname(__file__))
PROJECT_ROOT = os.environ.get("WORKBENCH_MCP_ROOT") or os.path.abspath(os.path.join(PLUGIN_DIR, ".."))
QUEUE_ROOT = os.environ.get("WORKBENCH_MCP_QUEUE_ROOT") or os.path.join(PROJECT_ROOT, "workbench_queue")
REQUEST_DIR = os.path.join(QUEUE_ROOT, "requests")
RESPONSE_DIR = os.path.join(QUEUE_ROOT, "responses")
ARCHIVE_DIR = os.path.join(QUEUE_ROOT, "archive")
LOG_FILE = os.path.join(QUEUE_ROOT, "mechanical_queue_processor.log")


def _ensure_dirs():
    for path in [QUEUE_ROOT, REQUEST_DIR, RESPONSE_DIR, ARCHIVE_DIR]:
        if not os.path.isdir(path):
            os.makedirs(path)


class JsonCompat(object):
    """JSON helper that avoids Mechanical IronPython's broken stdlib json."""

    def __init__(self):
        import clr
        clr.AddReference("System.Web.Extensions")
        from System.Web.Script.Serialization import JavaScriptSerializer
        self.serializer = JavaScriptSerializer()

    def dumps(self, value):
        return self.serializer.Serialize(self._to_builtin(value))

    def loads(self, text):
        return self._to_builtin(self.serializer.DeserializeObject(text))

    def _to_builtin(self, value):
        try:
            long_type = long
        except Exception:
            long_type = int
        if value is None or isinstance(value, (str, int, long_type, float, bool)):
            return value
        if isinstance(value, dict):
            return dict((str(k), self._to_builtin(v)) for k, v in value.items())
        if isinstance(value, (list, tuple)):
            return [self._to_builtin(v) for v in value]
        if hasattr(value, "Keys") and hasattr(value, "__getitem__"):
            return dict((str(k), self._to_builtin(value[k])) for k in value.Keys)
        try:
            return [self._to_builtin(v) for v in value]
        except Exception:
            return str(value)


JSON = JsonCompat()


def _log(message):
    line = "%s [WorkbenchMCPQueue] %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), message)
    try:
        with open(LOG_FILE, "a") as fp:
            fp.write(line + "\n")
    except Exception:
        pass
    try:
        ExtAPI.Log.WriteMessage(line)
    except Exception:
        print(line)


def _read_json(path):
    with open(path, "rb") as fp:
        raw = fp.read()
    try:
        text = raw.decode("utf-8")
    except Exception:
        try:
            text = raw.decode("utf-16")
        except Exception:
            # IronPython sometimes returns a byte-string object from rb reads.
            # Preserve ASCII JSON bytes and remove embedded NULs defensively.
            text = str(raw)
    text = text.replace("\x00", "").lstrip(u"\ufeff")
    return JSON.loads(text)


def _write_json(path, payload):
    text = JSON.dumps(payload)
    try:
        data = text.encode("utf-8")
    except Exception:
        data = text
    parent = os.path.dirname(path)
    if parent and not os.path.isdir(parent):
        _mkdirs(parent)
    with open(path, "wb") as fp:
        fp.write(data)


def _mkdirs(path):
    if not path or os.path.isdir(path):
        return
    parent = os.path.dirname(path)
    if parent and parent != path and not os.path.isdir(parent):
        _mkdirs(parent)
    if not os.path.isdir(path):
        os.mkdir(path)


def _move_file_best_effort(src, dst):
    try:
        parent = os.path.dirname(dst)
        if parent and not os.path.isdir(parent):
            _mkdirs(parent)
        with open(src, "rb") as fp:
            data = fp.read()
        with open(dst, "wb") as fp:
            fp.write(data)
        try:
            os.remove(src)
        except Exception:
            pass
        return True
    except Exception:
        _log("Archive move failed:\n" + traceback.format_exc())
        return False


def _state_payload():
    payload = {
        "app": "ANSYS Mechanical",
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "queue_root": QUEUE_ROOT,
        "project_available": False,
        "model_available": False,
        "analysis_collection_readable": False,
    }
    try:
        project = ExtAPI.DataModel.Project
        payload["project_available"] = project is not None
        if project is not None:
            payload["project_directory"] = str(project.ProjectDirectory)
    except Exception as exc:
        payload["project_directory_error"] = str(exc)
    try:
        payload["model_available"] = Model is not None
        analyses = list(Model.Analyses)
        payload["analysis_collection_readable"] = True
        payload["analysis_count"] = len(analyses)
        payload["analyses"] = [a.Name for a in analyses]
    except Exception as exc:
        payload["analysis_error"] = str(exc)
    try:
        ns = getattr(Model, "NamedSelections", None)
        children = getattr(ns, "Children", None)
        if children is None:
            payload["named_selections"] = []
        else:
            payload["named_selections"] = [obj.Name for obj in children]
    except Exception as exc:
        payload["named_selections_error"] = str(exc)
    try:
        payload["tree_active"] = [obj.Name for obj in Tree.ActiveObjects]
    except Exception:
        payload["tree_active"] = []
    return payload


def _execute_python(code):
    stdout = StringIO()
    stderr = StringIO()
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    sys.stdout = stdout
    sys.stderr = stderr
    try:
        env = {
            "ExtAPI": ExtAPI,
            "Model": Model,
            "DataModel": DataModel,
            "Tree": Tree,
        }
        exec(code, env, env)
        return {
            "ok": True,
            "stdout": stdout.getvalue(),
            "stderr": stderr.getvalue(),
        }
    except Exception:
        return {
            "ok": False,
            "stdout": stdout.getvalue(),
            "stderr": stderr.getvalue(),
            "traceback": traceback.format_exc(),
        }
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr


def _handle_request(request):
    action = request.get("action", "ping")
    if action == "ping":
        return {"ok": True, "message": "pong", "state": _state_payload()}
    if action == "get_state":
        return {"ok": True, "state": _state_payload()}
    if action == "execute_python":
        code = request.get("code", "")
        if not code:
            return {"ok": False, "error": "Missing code"}
        return _execute_python(code)
    return {"ok": False, "error": "Unknown action: " + str(action)}


def process_queue_once():
    _ensure_dirs()
    request_files = [
        name for name in os.listdir(REQUEST_DIR)
        if name.lower().endswith(".json")
    ]
    request_files.sort()
    processed = 0
    _log("Processing %d queued request(s)" % len(request_files))

    for name in request_files:
        request_path = os.path.join(REQUEST_DIR, name)
        request_id = os.path.splitext(name)[0]
        response_path = os.path.join(RESPONSE_DIR, request_id + ".json")
        archive_path = os.path.join(ARCHIVE_DIR, name)
        try:
            request = _read_json(request_path)
            response = _handle_request(request)
            response["request_id"] = request_id
            response["processed_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            _write_json(response_path, response)
            _move_file_best_effort(request_path, archive_path)
            processed += 1
        except Exception:
            error_response = {
                "ok": False,
                "request_id": request_id,
                "traceback": traceback.format_exc(),
                "processed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            _write_json(response_path, error_response)
            _move_file_best_effort(request_path, archive_path)

    _log("Queue processor completed; processed=%d" % processed)
    return processed


try:
    process_queue_once()
except Exception:
    _ensure_dirs()
    _log("Top-level queue processor error:\n" + traceback.format_exc())
