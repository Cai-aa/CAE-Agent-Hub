# encoding: utf-8
"""Workbench MCP socket bridge, v7.

Version marker: SOCKET_TIMER_V7_BACKGROUND_THREAD_2026_05_17

Start it once from the ACT toolbar, then Codex/Claude can send repeated socket
requests to the configured localhost port while Mechanical remains usable.

Architecture:
- a background daemon thread owns blocking accept();
- each request is handled synchronously inside that listener thread;
- every Start call force-restarts stale listeners from older v7 builds.

Use action="stop" or the ACT "Socket Timer Stop" button to shut it down.
"""

from __future__ import print_function

import os
import socket
import sys
import time
import traceback

try:
    import __builtin__ as _builtins
except Exception:
    import builtins as _builtins

PLUGIN_DIR = os.path.abspath(os.path.dirname(__file__))
PROJECT_ROOT = os.environ.get("WORKBENCH_MCP_ROOT") or os.path.abspath(os.path.join(PLUGIN_DIR, ".."))
QUEUE_ROOT = os.environ.get("WORKBENCH_MCP_QUEUE_ROOT") or os.path.join(PROJECT_ROOT, "workbench_queue")

HOST = os.environ.get("WORKBENCH_MCP_HOST", "127.0.0.1")
PORT = int(os.environ.get("WORKBENCH_MCP_PORT", "9885"))
VERSION = "SOCKET_TIMER_V7_DOTNET_THREAD_PORT_9885_QUEUE_ACTION_2026_05_18"
LOG_FILE = os.path.join(QUEUE_ROOT, "mechanical_socket_timer_v7.log")
QUEUE_PROCESSOR_PATH = os.path.join(PLUGIN_DIR, "mechanical_queue_processor.py")

RECV_TIMEOUT_SECONDS = 3.0
ACCEPT_TIMEOUT_SECONDS = 0.5


class JsonCompat(object):
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


def _new_state():
    return {
        "running": False,
        "server": None,
        "thread": None,
        "stop_requested": False,
        "request_count": 0,
        "started_at": None,
        "last_error": None,
    }


def _state():
    name = "_WORKBENCH_MCP_SOCKET_TIMER_V7_DOTNET_9885_STATE"
    if not hasattr(_builtins, name) or getattr(_builtins, name) is None:
        setattr(_builtins, name, _new_state())
    return getattr(_builtins, name)


def _log(message):
    line = "%s [WorkbenchMCPSocketTimerV7] %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), message)
    try:
        with open(LOG_FILE, "a") as fp:
            fp.write(line + "\n")
    except Exception:
        pass
    try:
        ExtAPI.Log.WriteMessage(line)
    except Exception:
        print(line)


def _encode_response(payload):
    text = JSON.dumps(payload) + "\0"
    try:
        return text.encode("utf-8")
    except Exception:
        return text


def _chunk_contains_nul(chunk):
    try:
        return "\0" in chunk
    except Exception:
        try:
            return "\0" in str(chunk)
        except Exception:
            return False


def _join_chunks(chunks):
    try:
        return "".join(chunks)
    except Exception:
        return "".join([str(c) for c in chunks])


def _to_text(raw):
    if raw is None:
        return ""
    try:
        if not isinstance(raw, str):
            return raw.decode("utf-8")
    except Exception:
        pass
    return str(raw)


def _is_would_block(exc):
    text = str(exc)
    if "10035" in text or "would block" in text.lower() or "non-blocking" in text.lower():
        return True
    try:
        for arg in exc.args:
            if arg in (11, 35, 10035):
                return True
    except Exception:
        pass
    return False


def _bridge_state_payload():
    st = _state()
    payload = {
        "ok": True,
        "app": "ANSYS Mechanical",
        "mode": "socket_timer_v7",
        "version": VERSION,
        "host": HOST,
        "port": PORT,
        "running": bool(st.get("running")),
        "request_count": int(st.get("request_count") or 0),
        "started_at": st.get("started_at"),
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "has_extapi": "ExtAPI" in globals(),
        "has_model_symbol": "Model" in globals(),
        "last_error": st.get("last_error"),
    }
    payload["project_available"] = False
    payload["model_available"] = False
    payload["analysis_collection_readable"] = False
    payload["analysis_count"] = 0
    payload["analyses"] = []
    try:
        project = ExtAPI.DataModel.Project
        payload["project_available"] = project is not None
        if project is not None:
            payload["project_directory"] = str(project.ProjectDirectory)
    except Exception as exc:
        payload["project_error"] = str(exc)
    try:
        model = globals().get("Model", None)
        payload["model_available"] = model is not None
        if model is not None:
            analyses = list(model.Analyses)
            payload["analysis_collection_readable"] = True
            payload["analysis_count"] = len(analyses)
            payload["analyses"] = [str(item.Name) for item in analyses]
    except Exception as exc:
        payload["analysis_error"] = str(exc)
    return payload


def _execute_python(code):
    try:
        from StringIO import StringIO
    except Exception:
        from io import StringIO

    stdout = StringIO()
    stderr = StringIO()
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    namespace = {}
    namespace.update(globals())
    try:
        sys.stdout = stdout
        sys.stderr = stderr
        exec(code, namespace, namespace)
        return {
            "ok": True,
            "stdout": stdout.getvalue(),
            "stderr": stderr.getvalue(),
            "result": JSON._to_builtin(namespace.get("_result", None)),
        }
    except Exception:
        return {
            "ok": False,
            "stdout": stdout.getvalue(),
            "stderr": stderr.getvalue(),
            "error": traceback.format_exc(),
        }
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr


def _process_queue_once_from_socket():
    namespace = {}
    namespace.update(globals())
    with open(QUEUE_PROCESSOR_PATH, "r") as stream:
        code = stream.read()
    exec(compile(code, QUEUE_PROCESSOR_PATH, "exec"), namespace, namespace)
    return {"ok": True, "message": "queue processor executed", "processor": QUEUE_PROCESSOR_PATH}


def _read_request(conn):
    chunks = []
    total = 0
    conn.settimeout(RECV_TIMEOUT_SECONDS)
    while True:
        try:
            chunk = conn.recv(4096)
        except BaseException:
            break
        if not chunk:
            break
        total += len(chunk)
        chunks.append(chunk)
        if _chunk_contains_nul(chunk):
            break
    text = _to_text(_join_chunks(chunks)).split("\0", 1)[0]
    if not text:
        return {"action": "ping", "read_bytes": total}
    try:
        return JSON.loads(text)
    except Exception:
        _log("request parse failed:\n" + traceback.format_exc())
        return {"action": "ping", "raw": text, "read_bytes": total}


def _handle_request(request):
    action = "ping"
    try:
        action = str(request.get("action", "ping"))
    except Exception:
        pass

    if action == "ping":
        return {"ok": True, "message": "pong", "request": request, "state": _bridge_state_payload()}
    if action in ("get_state", "state"):
        return {"ok": True, "request": request, "state": _bridge_state_payload()}
    if action == "execute_python":
        code = ""
        try:
            code = request.get("code", "")
        except Exception:
            pass
        return {"ok": True, "request": request, "execution": _execute_python(str(code)), "state": _bridge_state_payload()}
    if action in ("process_queue", "process_mcp_queue"):
        try:
            result = _process_queue_once_from_socket()
            return {"ok": True, "request": request, "queue": result, "state": _bridge_state_payload()}
        except BaseException:
            return {"ok": False, "request": request, "error": traceback.format_exc(), "state": _bridge_state_payload()}
    if action == "stop":
        response = {"ok": True, "message": "stop requested", "request": request, "state": _bridge_state_payload()}
        stop_socket_timer_bridge()
        return response
    return {"ok": False, "error": "Unknown action: %s" % action, "request": request, "state": _bridge_state_payload()}


def _serve_connection(conn, addr):
    st = _state()
    try:
        request = _read_request(conn)
        st["request_count"] = int(st.get("request_count") or 0) + 1
        _log("Request %d from %s: %s" % (st["request_count"], addr, repr(request)))
        try:
            response = _handle_request(request)
        except BaseException:
            response = {"ok": False, "error": "handle_request failed", "traceback": traceback.format_exc()}
            st["last_error"] = response["traceback"]
            _log("handle_request failed:\n" + response["traceback"])
        conn.sendall(_encode_response(response))
    finally:
        try:
            conn.close()
        except BaseException:
            pass


def _accept_loop():
    st = _state()
    _log("Accept loop entered")
    while bool(st.get("running")) and not bool(st.get("stop_requested")):
        server = st.get("server")
        if server is None:
            break
        conn = None
        try:
            conn, addr = server.accept()
        except BaseException as exc:
            if _is_would_block(exc):
                continue
            text = str(exc)
            if "timed out" in text.lower() or "timeout" in text.lower():
                continue
            if bool(st.get("running")) and not bool(st.get("stop_requested")):
                st["last_error"] = traceback.format_exc()
                _log("accept failed:\n" + st["last_error"])
            break
        try:
            _serve_connection(conn, addr)
        except BaseException:
            st["last_error"] = traceback.format_exc()
            _log("connection handling failed:\n" + st["last_error"])
        finally:
            try:
                if conn is not None:
                    conn.close()
            except BaseException:
                pass
    _log("Accept loop exited")


def _close_existing_listener():
    st = _state()
    st["stop_requested"] = True
    st["running"] = False
    server = st.get("server")
    try:
        if server is not None:
            server.close()
    except BaseException:
        pass
    st["server"] = None


def _start_background_thread():
    import clr
    clr.AddReference("System")
    from System.Threading import Thread, ThreadStart

    thread = Thread(ThreadStart(_accept_loop))
    thread.IsBackground = True
    thread.Start()
    return thread


def start_socket_timer_bridge():
    st = _state()
    if st.get("running"):
        _log("Restarting existing/stale bridge on %s:%d" % (HOST, PORT))
        _close_existing_listener()
        time.sleep(0.1)

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(10)
    server.settimeout(ACCEPT_TIMEOUT_SECONDS)

    st["server"] = server
    st["running"] = True
    st["stop_requested"] = False
    st["request_count"] = 0
    st["started_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    st["last_error"] = None

    st["thread"] = _start_background_thread()

    _log("Started %s on %s:%d background_thread=True" % (VERSION, HOST, PORT))
    return _bridge_state_payload()


def stop_socket_timer_bridge():
    st = _state()
    _close_existing_listener()
    st["thread"] = None
    _log("Stopped %s" % VERSION)
    return _bridge_state_payload()


def socket_timer_bridge_status():
    return _bridge_state_payload()


if not globals().get("WORKBENCH_MCP_LOAD_ONLY", False):
    try:
        _auto_state = start_socket_timer_bridge()
        _log("Auto-start state: %s" % str(_auto_state))
    except BaseException:
        _log("Auto-start failed:\n" + traceback.format_exc())
