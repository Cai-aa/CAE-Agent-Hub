# -*- coding: utf-8 -*-
"""
Abaqus MCP Plugin v6.0 - Optimized with compatibility layer.

This file runs inside Abaqus/CAE. It registers a Plug-ins menu, starts a local
TCP server, dispatches requests on the Abaqus GUI thread, and executes Python in
the Abaqus kernel through sendCommand.

v6.0 changes:
  - Uses abaqus_mcp_compat for ALL Python 2.7/3.x compatibility (single source)
  - Unified encoding strategy: safe_decode + ensure_ascii everywhere
  - Cleaner kernel template with compact inline compat shims
  - No scattered version checks throughout the code
"""
from __future__ import print_function

import base64
import json
import os
import platform
import sys
import tempfile
import threading
import time
import traceback
import uuid

# ============================================================================
# Import compatibility layer (handles Py2/Py3, encoding, queue, socketserver,
# TimeoutError, etc. in one place)
# ============================================================================
# The compat module lives alongside this file. When this plugin is loaded via
# exec() by mcp_control_plugin.py, __file__ is NOT set, so we use ABAQUS_MCP_HOME
# env var as the primary way to find our directory.
_PLUGIN_DIR = os.environ.get("ABAQUS_MCP_HOME", "").strip()
if not _PLUGIN_DIR:
    _PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
if _PLUGIN_DIR not in sys.path:
    sys.path.insert(0, _PLUGIN_DIR)

from abaqus_mcp_compat import (
    PY2,
    string_types,
    ensure_str,
    safe_decode,
    safe_json_dumps,
    redirect_stdout,
    redirect_stderr,
    cpu_count,
    get_traceback,
    format_traceback,
    ast_unparse,
    queue,
    socketserver,
    TimeoutError,
    jsonable,
    read_text_file,
    write_json_file,
)

from abaqusGui import (
    AFXForm,
    AFXMode,
    FXMAPFUNC,
    SEL_COMMAND,
    SEL_TIMEOUT,
    getAFXApp,
    sendCommand,
    showAFXErrorDialog,
)

__version__ = "6.0.0"

HOST = os.environ.get("ABAQUS_MCP_HOST", "127.0.0.1")
PORT = int(os.environ.get("ABAQUS_MCP_PORT", "48152"))
DEFAULT_TIMEOUT = float(os.environ.get("ABAQUS_MCP_TIMEOUT", "60"))
LOG_PATH = os.environ.get(
    "ABAQUS_MCP_LOG",
    os.path.join(tempfile.gettempdir(), "abaqus_mcp_socket_bridge.log"),
)


def _log(message):
    try:
        with open(LOG_PATH, "a") as handle:
            handle.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), message))
    except Exception:
        pass


def _announce(message):
    print(message)
    try:
        main_window = getAFXApp().getAFXMainWindow()
        if hasattr(main_window, "writeToMessageArea"):
            main_window.writeToMessageArea(message)
    except Exception:
        pass


def _send(sock, payload):
    """Send JSON payload over socket. Uses ensure_ascii=True to avoid encoding issues."""
    data = safe_json_dumps(payload, separators=(",", ":")).encode("utf-8")
    sock.sendall(data + b"\n")


def _recv(sock):
    """Receive JSON payload from socket."""
    chunks = []
    total = 0
    max_bytes = int(os.environ.get("ABAQUS_MCP_MAX_MESSAGE_BYTES", str(32 * 1024 * 1024)))
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            raise RuntimeError("socket closed before a complete message was received")
        newline = chunk.find(b"\n")
        if newline >= 0:
            chunks.append(chunk[:newline])
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > max_bytes:
            raise RuntimeError("message exceeded %d bytes" % max_bytes)
    return json.loads(b"".join(chunks).decode("utf-8"))


# ============================================================================
# Kernel code template
# This code runs inside the Abaqus KERNEL process (separate from GUI).
# It must be self-contained - cannot import abaqus_mcp_compat.
# The template below has a compact inline compat section.
# ============================================================================
_KERNEL_TEMPLATE = r'''
import ast
import base64
import difflib
import inspect
import io
import json
import os
import re
import sys
import traceback

code = base64.b64decode("__ABAQUS_MCP_CODE__").decode("utf-8")
response_path = base64.b64decode("__ABAQUS_MCP_RESPONSE__").decode("utf-8")
MAX_OUTPUT = 4000
_PY2 = sys.version_info[0] == 2

# --- Compact inline compatibility shims (self-contained for kernel) ---
def _safe_decode(s):
    """Decode bytes trying UTF-8, GBK, latin-1."""
    if not isinstance(s, str):
        return s
    for enc in ("utf-8", "gbk", "gb2312", "latin-1"):
        try:
            return s.decode(enc)
        except (UnicodeDecodeError, UnicodeEncodeError):
            continue
    return s.decode("latin-1", errors="replace")

def _jsonable(value):
    if isinstance(value, str):
        value = _safe_decode(value)
    try:
        json.dumps(value, ensure_ascii=True)
        return value
    except Exception:
        return {"repr": repr(value), "type": "%s.%s" % (type(value).__module__, type(value).__name__)}

def _ast_unparse(node):
    try:
        if hasattr(ast, "unparse"):
            return ast.unparse(node)
        import _ast
        if isinstance(node, _ast.Name):
            return node.id
        if isinstance(node, _ast.Attribute):
            return _ast_unparse(node.value) + "." + node.attr
        if isinstance(node, _ast.Subscript):
            return _ast_unparse(node.value) + "[" + repr(node.slice) + "]"
        if isinstance(node, _ast.Call):
            return _ast_unparse(node.func)
        return None
    except Exception:
        return None

def _get_tb(exc):
    tb = getattr(exc, "__traceback__", None)
    if tb is None:
        try:
            tb = sys.exc_info()[2]
        except Exception:
            tb = None
    return tb

def _extract_lineno(exc):
    if hasattr(exc, "lineno") and getattr(exc, "lineno") is not None:
        return getattr(exc, "lineno")
    tb = _get_tb(exc)
    while tb is not None:
        if tb.tb_frame.f_code.co_filename == "<abaqus-mcp>":
            return tb.tb_lineno
        tb = tb.tb_next
    return None

def _extract_excerpt(source, lineno, radius=2):
    if lineno is None:
        return None
    lines = source.splitlines()
    idx = lineno - 1
    if idx < 0 or idx >= len(lines):
        return None
    start = max(0, idx - radius)
    end = min(len(lines), idx + radius + 1)
    out = []
    for i in range(start, end):
        prefix = ">>" if i == idx else "  "
        out.append("%s %4d | %s" % (prefix, i + 1, lines[i]))
    return "\n".join(out)

def _resolve_expr(expr, namespace):
    def _eval_node(node):
        if isinstance(node, ast.Name):
            return namespace[node.id]
        if isinstance(node, ast.Attribute):
            return getattr(_eval_node(node.value), node.attr)
        if isinstance(node, ast.Subscript):
            base = _eval_node(node.value)
            try:
                key = ast.literal_eval(node.slice)
            except Exception:
                if hasattr(ast, "Index") and isinstance(node.slice, ast.Index):
                    key = ast.literal_eval(node.slice.value)
                else:
                    raise
            return base[key]
        raise ValueError("unsupported expression")
    return _eval_node(ast.parse(expr, mode="eval").body)

def _parent_expr_for_subscript(source, lineno):
    try:
        tree = ast.parse(source)
    except Exception:
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript) and getattr(node, "lineno", None) == lineno:
            return _ast_unparse(node.value)
    return None

def _parent_expr_for_attribute(source, attr_name):
    try:
        tree = ast.parse(source)
    except Exception:
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == attr_name:
            return _ast_unparse(node.value)
    return None

def _call_target(source, lineno):
    try:
        tree = ast.parse(source)
    except Exception:
        return None
    calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            start = getattr(node, "lineno", None)
            end = getattr(node, "end_lineno", start)
            if start is not None and end is not None and start <= lineno <= end:
                calls.append(node)
    if not calls:
        return None
    calls.sort(key=lambda n: getattr(n, "end_lineno", getattr(n, "lineno", 0)) - getattr(n, "lineno", 0))
    return _ast_unparse(calls[0].func)

def _summarize_error(source, exc, namespace):
    tb = traceback.format_exc()
    tb = _safe_decode(tb)
    tb_lines = [line for line in tb.strip().splitlines() if line.strip()]
    lineno = _extract_lineno(exc)
    core_error = tb_lines[-1] if tb_lines else str(exc)
    core_error = _safe_decode(core_error)
    error_type = "%s.%s" % (type(exc).__module__, type(exc).__name__)
    recovery = {}

    if isinstance(exc, KeyError):
        missing = exc.args[0] if exc.args else None
        parent = _parent_expr_for_subscript(source, lineno)
        recovery = {"missing_key": _jsonable(missing), "parent_object_path": parent}
        if parent:
            try:
                obj = _resolve_expr(parent, namespace)
                keys = [str(k) for k in list(obj.keys())]
                recovery["available_keys_sample"] = keys
                recovery["possible_keys"] = difflib.get_close_matches(str(missing), keys, n=8, cutoff=0.45)
            except Exception:
                pass
    elif isinstance(exc, AttributeError):
        missing_attr = getattr(exc, "name", None)
        parent = _parent_expr_for_attribute(source, missing_attr) if missing_attr else None
        recovery = {"missing_attribute": missing_attr, "parent_object_path": parent}
        if parent:
            try:
                obj = _resolve_expr(parent, namespace)
                members = [name for name in dir(obj) if not name.startswith("_")]
                recovery["possible_members"] = difflib.get_close_matches(str(missing_attr), members, n=10, cutoff=0.45)
            except Exception:
                pass
    elif type(exc).__name__ == "NameError":
        missing = getattr(exc, "name", None)
        if not missing:
            match = re.search(r"name '(\w+)' is not defined", str(exc))
            if match:
                missing = match.group(1)
        recovery = {"missing_variable": missing}
        if missing and (missing.isupper() or missing in ("mesh", "part", "material", "assembly", "step", "interaction", "load", "section", "job")):
            recovery["import_suggestion"] = "from abaqusConstants import *"
    elif isinstance(exc, TypeError):
        target_expr = _call_target(source, lineno)
        recovery = {"call_target": target_expr}
        if target_expr:
            try:
                target = _resolve_expr(target_expr, namespace)
                try:
                    recovery["callable_signature"] = "%s%s" % (getattr(target, "__name__", target_expr), inspect.signature(target))
                except Exception:
                    recovery["callable_signature"] = getattr(target, "__doc__", None)
            except Exception:
                pass

    return {
        "ok": False,
        "core_error": core_error,
        "error_type": error_type,
        "error_line": lineno,
        "code_excerpt": _extract_excerpt(source, lineno),
        "traceback_tail": tb_lines[-8:],
        "recovery": recovery,
    }

# --- redirect_stdout/stderr (Py2.7 fallback) ---
if hasattr(__import__("contextlib"), "redirect_stdout"):
    _redirect_stdout = __import__("contextlib").redirect_stdout
    _redirect_stderr = __import__("contextlib").redirect_stderr
else:
    class _redirect_stdout(object):
        def __init__(self, new_target):
            self.new_target = new_target
        def __enter__(self):
            self.old_target = sys.stdout
            sys.stdout = self.new_target
            return self.new_target
        def __exit__(self, exc_type, exc_val, exc_tb):
            sys.stdout = self.old_target
    class _redirect_stderr(object):
        def __init__(self, new_target):
            self.new_target = new_target
        def __enter__(self):
            self.old_target = sys.stderr
            sys.stderr = self.new_target
            return self.new_target
        def __exit__(self, exc_type, exc_val, exc_tb):
            sys.stderr = self.old_target

# --- Execute user code ---
try:
    from abaqus import mdb, session
except Exception:
    mdb = globals().get("mdb")
    session = globals().get("session")

namespace = globals().setdefault("_ABAQUS_MCP_GLOBALS", {"__name__": "__abaqus_mcp_exec__", "__doc__": None})
namespace.update({"mdb": mdb, "session": session})

stdout = io.StringIO()
stderr = io.StringIO()
returned = None
error_response = None

try:
    with _redirect_stdout(stdout), _redirect_stderr(stderr):
        try:
            try:
                parsed = ast.parse(code, mode="eval")
            except SyntaxError:
                parsed = ast.parse(code, mode="exec")
                compiled = compile(parsed, "<abaqus-mcp>", "exec")
                exec(compiled, namespace, namespace)
                returned = namespace.get("result")
            else:
                compiled = compile(parsed, "<abaqus-mcp>", "eval")
                returned = eval(compiled, namespace, namespace)
        except Exception as exc:
            error_response = _summarize_error(code, exc, namespace)
except Exception as exc:
    error_response = _summarize_error(code, exc, namespace)

captured_stdout = _safe_decode(stdout.getvalue())
captured_stderr = _safe_decode(stderr.getvalue())
if len(captured_stdout) > MAX_OUTPUT:
    captured_stdout = captured_stdout[:MAX_OUTPUT] + "\n... (truncated)"
if len(captured_stderr) > MAX_OUTPUT:
    captured_stderr = captured_stderr[:MAX_OUTPUT] + "\n... (truncated)"

if error_response is not None:
    error_response["stdout"] = captured_stdout
    error_response["stderr"] = captured_stderr
    payload = error_response
else:
    payload = {
        "ok": True,
        "return_value": _jsonable(returned),
        "stdout": captured_stdout,
        "stderr": captured_stderr,
    }

_data = json.dumps(payload, ensure_ascii=True)
if isinstance(_data, unicode):
    _data = _data.encode("ascii")
with open(response_path, "wb") as handle:
    handle.write(_data)
'''


def _kernel_wrapper(code, response_path):
    """Build kernel code template. Returns str (not unicode) for Python 2.7."""
    encoded_code = base64.b64encode(code.encode("utf-8"))
    encoded_path = base64.b64encode(response_path.encode("utf-8"))
    # Ensure str type in both Py2 and Py3
    encoded_code = ensure_str(encoded_code)
    encoded_path = ensure_str(encoded_path)

    result = _KERNEL_TEMPLATE.replace("__ABAQUS_MCP_CODE__", encoded_code).replace("__ABAQUS_MCP_RESPONSE__", encoded_path)
    # CRITICAL: Ensure result is str, not unicode, for Python 2.7 sendCommand
    return ensure_str(result)


def _run_kernel_code(code, timeout):
    response_path = os.path.join(tempfile.gettempdir(), "abaqus_mcp_%s.json" % uuid.uuid4().hex)
    command = _kernel_wrapper(code, response_path)
    command = ensure_str(command)
    _log("sendCommand start response_path=%s command_type=%s" % (response_path, type(command).__name__))
    sendCommand(command, False, False)

    deadline = time.time() + timeout
    while time.time() < deadline:
        if os.path.exists(response_path):
            # Read with explicit UTF-8 encoding (Python 2.7 defaults to GBK on Chinese Windows)
            import io
            with io.open(response_path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            try:
                os.remove(response_path)
            except Exception:
                pass
            _log("kernel response ok=%s" % payload.get("ok"))
            return payload
        time.sleep(0.03)

    raise TimeoutError("timed out waiting for Abaqus kernel response")


class GuiRequest(object):
    def __init__(self, method, params):
        self.method = method
        self.params = params
        self.event = threading.Event()
        self.result = None
        self.error = None


class McpGuiHandler(socketserver.BaseRequestHandler):
    def handle(self):
        request_id = None
        try:
            message = _recv(self.request)
            request_id = message.get("id")
            method = message.get("method")
            params = message.get("params") or {}
            _log("request method=%s id=%s" % (method, request_id))

            if _DISPATCHER is None:
                raise RuntimeError("Abaqus MCP GUI dispatcher is not initialized")

            wait_timeout = float(params.get("timeout") or DEFAULT_TIMEOUT) + 5.0
            item = GuiRequest(method, params)
            _REQUESTS.put(item)

            if not item.event.wait(wait_timeout):
                raise TimeoutError("timed out waiting for Abaqus GUI dispatcher")
            if item.error is not None:
                raise item.error

            _send(self.request, {"id": request_id, "ok": True, "result": item.result})
        except Exception as exc:
            _log("response error id=%s error=%s" % (request_id, exc))
            _send(
                self.request,
                {
                    "id": request_id,
                    "ok": False,
                    "error": {
                        "message": str(exc),
                        "type": "%s.%s" % (type(exc).__module__, type(exc).__name__),
                        "traceback": format_traceback(),
                    },
                },
            )


class McpGuiServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


_SERVER = None
_SERVER_THREAD = None
_DISPATCHER = None
_REQUESTS = queue.Queue()
_PROCESSED = 0
_START_TIME = None


def _handle_on_gui_thread(item):
    method = item.method
    params = item.params
    timeout = float(params.get("timeout") or DEFAULT_TIMEOUT)

    if method == "ping":
        code = (
            "import os, sys, platform\n"
            "from abaqus import mdb, session\n"
            "try:\n"
            "    _ncpu = os.cpu_count()\n"
            "except AttributeError:\n"
            "    import multiprocessing\n"
            "    _ncpu = multiprocessing.cpu_count()\n"
            "result = {'python': sys.version, 'executable': sys.executable, "
            "'platform': platform.platform(), 'pid': os.getpid(), "
            "'cpu_count': _ncpu, 'cwd': os.getcwd(), "
            "'abaqus_version': getattr(session, 'version', None), "
            "'models': list(mdb.models.keys()), "
            "'viewports': list(session.viewports.keys())}"
        )
        payload = _run_kernel_code(code, timeout)
        result = payload.get("return_value") if payload.get("ok") else payload
        if isinstance(result, dict):
            result["bridge"] = {
                "version": __version__,
                "host": HOST,
                "port": PORT,
                "transport": "socket",
                "processed": _PROCESSED,
                "uptime_seconds": int(time.time() - _START_TIME) if _START_TIME else 0,
                "gui_python": sys.version,
                "gui_platform": platform.platform(),
                "log": LOG_PATH,
            }
        return result

    if method == "execute":
        code = params.get("code")
        if not isinstance(code, string_types) or not code.strip():
            raise ValueError("params.code must be a non-empty string")
        return _run_kernel_code(code, timeout)

    if method == "stop":
        threading.Thread(target=stop_gui_agent, name="AbaqusMcpStopper").start()
        return {"success": True, "message": "stop requested"}

    raise ValueError("unknown method: %r" % method)


def start_gui_agent():
    global _SERVER, _SERVER_THREAD, _START_TIME
    if _SERVER is not None:
        return "Abaqus MCP socket bridge is already running on %s:%s" % (HOST, PORT)

    _log("starting socket bridge on %s:%s" % (HOST, PORT))
    _SERVER = McpGuiServer((HOST, PORT), McpGuiHandler)
    _SERVER_THREAD = threading.Thread(target=_SERVER.serve_forever, name="AbaqusMcpSocketBridge")
    _SERVER_THREAD.daemon = True
    _SERVER_THREAD.start()
    _START_TIME = time.time()
    return "Abaqus MCP socket bridge listening on %s:%s" % (HOST, PORT)


def stop_gui_agent():
    global _SERVER, _SERVER_THREAD
    server = _SERVER
    if server is None:
        return "Abaqus MCP socket bridge is not running."
    try:
        server.shutdown()
        server.server_close()
    finally:
        _SERVER = None
        _SERVER_THREAD = None
    _log("stopped socket bridge")
    return "Abaqus MCP socket bridge stopped."


def mcp_start():
    message = start_gui_agent()
    try:
        if _DISPATCHER is not None:
            _DISPATCHER.schedule_poll()
    except Exception:
        pass
    _announce(message)
    _announce("Abaqus MCP log: %s" % LOG_PATH)
    return message


def mcp_stop():
    message = stop_gui_agent()
    _announce(message)
    return message


def mcp_status():
    status = {
        "version": __version__,
        "transport": "socket",
        "endpoint": "%s:%s" % (HOST, PORT),
        "running": _SERVER is not None,
        "processed": _PROCESSED,
        "uptime_seconds": int(time.time() - _START_TIME) if _START_TIME else 0,
        "log": LOG_PATH,
    }
    _announce(safe_json_dumps(status, indent=2))
    return status

class McpGuiActionForm(AFXForm):
    ID_START = AFXForm.ID_LAST + 1
    ID_STOP = AFXForm.ID_LAST + 2
    ID_STATUS = AFXForm.ID_LAST + 3
    ID_POLL = AFXForm.ID_LAST + 4

    def __init__(self, owner, action):
        global _DISPATCHER
        AFXForm.__init__(self, owner)
        self.action = action
        FXMAPFUNC(self, SEL_COMMAND, AFXMode.ID_ACTIVATE, McpGuiActionForm.onCmdActivate)
        FXMAPFUNC(self, SEL_COMMAND, self.ID_START, McpGuiActionForm.onCmdStart)
        FXMAPFUNC(self, SEL_COMMAND, self.ID_STOP, McpGuiActionForm.onCmdStop)
        FXMAPFUNC(self, SEL_COMMAND, self.ID_STATUS, McpGuiActionForm.onCmdStatus)
        FXMAPFUNC(self, SEL_TIMEOUT, self.ID_POLL, McpGuiActionForm.onTimeout)
        _DISPATCHER = self

    def getFirstDialog(self):
        return None

    def schedule_poll(self):
        try:
            getAFXApp().addTimeout(50, self, self.ID_POLL)
        except Exception as exc:
            _log("schedule poll failed: %s" % exc)

    def onCmdActivate(self, sender, sel, ptr):
        if self.action == "start":
            return self.onCmdStart(sender, sel, ptr)
        if self.action == "stop":
            return self.onCmdStop(sender, sel, ptr)
        return self.onCmdStatus(sender, sel, ptr)

    def onCmdStart(self, sender, sel, ptr):
        try:
            mcp_start()
            self.schedule_poll()
        except Exception as exc:
            message = "Abaqus MCP socket bridge failed: %s" % exc
            _log(message)
            showAFXErrorDialog(getAFXApp().getAFXMainWindow(), message)
        return 1

    def onCmdStop(self, sender, sel, ptr):
        try:
            mcp_stop()
        except Exception as exc:
            message = "Abaqus MCP socket bridge stop failed: %s" % exc
            _log(message)
            showAFXErrorDialog(getAFXApp().getAFXMainWindow(), message)
        return 1

    def onCmdStatus(self, sender, sel, ptr):
        try:
            mcp_status()
        except Exception as exc:
            message = "Abaqus MCP status failed: %s" % exc
            _log(message)
            showAFXErrorDialog(getAFXApp().getAFXMainWindow(), message)
        return 1

    def onTimeout(self, sender, sel, ptr):
        global _PROCESSED
        processed = 0
        while processed < 10:
            try:
                item = _REQUESTS.get_nowait()
            except queue.Empty:
                break
            try:
                item.result = _handle_on_gui_thread(item)
                _PROCESSED += 1
            except Exception as exc:
                item.error = exc
                _log("GUI handler error method=%s error=%s" % (item.method, exc))
            finally:
                item.event.set()
            processed += 1

        if _SERVER is not None:
            self.schedule_poll()
        return 1


def _register_menu():
    try:
        main_window = getAFXApp().getAFXMainWindow()
        toolset = main_window.getPluginToolset()
        modules = ["Part", "Property", "Assembly", "Step", "Interaction", "Load", "Mesh", "Job", "Visualization"]
        toolset.registerGuiMenuButton(
            object=McpGuiActionForm(toolset, "start"),
            buttonText="Abaqus MCP|Start Socket Bridge",
            version=__version__,
            applicableModules=modules,
            description="Start the low-latency TCP bridge for MCP clients.",
        )
        toolset.registerGuiMenuButton(
            object=McpGuiActionForm(toolset, "status"),
            buttonText="Abaqus MCP|Bridge Status",
            version=__version__,
            applicableModules=modules,
            description="Print Abaqus MCP bridge status.",
        )
        toolset.registerGuiMenuButton(
            object=McpGuiActionForm(toolset, "stop"),
            buttonText="Abaqus MCP|Stop Socket Bridge",
            version=__version__,
            applicableModules=modules,
            description="Stop the low-latency TCP bridge.",
        )
        _log("registered Abaqus MCP GUI menu")
    except Exception as exc:
        _log("menu registration failed: %s" % exc)
        raise


if not globals().get("_ABAQUS_MCP_MENU_REGISTERED"):
    _register_menu()
    globals()["_ABAQUS_MCP_MENU_REGISTERED"] = True

_announce("Abaqus MCP Plugin v%s loaded (optimized with compat layer). Use Plug-ins > Abaqus MCP > Start Socket Bridge." % __version__)
