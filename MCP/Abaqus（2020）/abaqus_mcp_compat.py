# -*- coding: utf-8 -*-
"""
Abaqus MCP Python 2.7/3.x Compatibility Layer v1.0

This module is loaded ONCE at plugin startup. It detects the Python version
and injects ALL necessary compatibility shims in a single pass, eliminating
the need for scattered version checks throughout the codebase.

Usage (at the top of any Abaqus plugin file):
    from abaqus_mcp_compat import *
"""
from __future__ import print_function

import sys
import os
import io
import json
import contextlib
import traceback as _traceback

# ============================================================================
# Version detection
# ============================================================================
PY2 = sys.version_info[0] == 2
PY3 = sys.version_info[0] >= 3

# ============================================================================
# 1. String types: basestring only exists in Py2; str works everywhere but
#    Py2 needs basestring to accept both str and unicode.
# ============================================================================
if PY2:
    string_types = (str, unicode)
    text_type = unicode
    binary_type = str
else:
    string_types = (str,)
    text_type = str
    binary_type = bytes


def ensure_str(s, encoding="utf-8"):
    """Convert any string-like value to native str type.

    In Python 2.7, sendCommand requires str (bytes), not unicode.
    In Python 3, we need str (text), not bytes.
    """
    if PY2:
        if isinstance(s, unicode):
            return s.encode(encoding)
        return s
    else:
        if isinstance(s, bytes):
            return s.decode(encoding)
        return s


def ensure_text(s, encoding="utf-8"):
    """Convert any string-like value to unicode/str (text type)."""
    if isinstance(s, bytes):
        return s.decode(encoding)
    return s


# ============================================================================
# 2. Safe multi-encoding string decoder
#    Abaqus on Chinese Windows outputs GBK bytes; we need to try UTF-8 first,
#    then GBK, then latin-1 as last resort.
# ============================================================================
def safe_decode(s):
    """Safely decode bytes to text, trying UTF-8, GBK, then latin-1.

    Handles the common case where Abaqus 2020 on Chinese Windows outputs
    GBK-encoded bytes that fail UTF-8 decoding.
    """
    if not isinstance(s, bytes):
        return s
    for enc in ("utf-8", "gbk", "gb2312", "latin-1"):
        try:
            return s.decode(enc)
        except (UnicodeDecodeError, UnicodeEncodeError):
            continue
    return s.decode("latin-1", errors="replace")


def safe_json_dumps(obj, **kwargs):
    """JSON dumps with ensure_ascii=True by default.

    Using ensure_ascii=True avoids all GBK/UTF-8 encoding conflicts
    on Chinese Windows + Python 2.7, because the output is pure ASCII.
    """
    kwargs.setdefault("ensure_ascii", True)
    return json.dumps(obj, **kwargs)


def safe_json_dump(obj, fp, **kwargs):
    """JSON dump to file with ensure_ascii=True."""
    kwargs.setdefault("ensure_ascii", True)
    data = json.dumps(obj, **kwargs)
    if PY2 and isinstance(data, unicode):
        data = data.encode("ascii")
    if hasattr(fp, "write"):
        fp.write(data)
    return data


# ============================================================================
# 3. contextlib.redirect_stdout / redirect_stderr
#    Missing in Python 2.7; provide custom context managers.
# ============================================================================
if hasattr(contextlib, "redirect_stdout"):
    redirect_stdout = contextlib.redirect_stdout
    redirect_stderr = contextlib.redirect_stderr
else:
    class redirect_stdout(object):
        """Context manager for redirecting stdout (Py2.7 fallback)."""
        def __init__(self, new_target):
            self.new_target = new_target
            self.old_target = None

        def __enter__(self):
            self.old_target = sys.stdout
            sys.stdout = self.new_target
            return self.new_target

        def __exit__(self, exc_type, exc_val, exc_tb):
            sys.stdout = self.old_target

    class redirect_stderr(object):
        """Context manager for redirecting stderr (Py2.7 fallback)."""
        def __init__(self, new_target):
            self.new_target = new_target
            self.old_target = None

        def __enter__(self):
            self.old_target = sys.stderr
            sys.stderr = self.new_target
            return self.new_target

        def __exit__(self, exc_type, exc_val, exc_tb):
            sys.stderr = self.old_target


# ============================================================================
# 4. os.cpu_count()
#    Missing in Python 2.7; use multiprocessing.cpu_count() as fallback.
# ============================================================================
def cpu_count():
    """Return the number of CPUs in the system."""
    if hasattr(os, "cpu_count"):
        return os.cpu_count()
    try:
        import multiprocessing
        return multiprocessing.cpu_count()
    except Exception:
        return 1


# ============================================================================
# 5. Exception traceback access
#    Python 2.7 exceptions don't have __traceback__; use sys.exc_info().
# ============================================================================
def get_traceback(exc=None):
    """Get the traceback object from an exception, Py2/Py3 compatible."""
    if exc is not None and hasattr(exc, "__traceback__") and exc.__traceback__ is not None:
        return exc.__traceback__
    return sys.exc_info()[2]


def format_traceback(exc=None):
    """Format the current or given exception's traceback as a string."""
    if exc is not None:
        return "".join(_traceback.format_exception(type(exc), exc, get_traceback(exc)))
    return _traceback.format_exc()


# ============================================================================
# 6. ast.unparse
#    Missing in Python 2.7; provide a minimal fallback for common AST nodes.
# ============================================================================
def ast_unparse(node):
    """Unparse an AST node to source code string.

    Uses ast.unparse if available (Python 3.9+), otherwise falls back
    to a manual implementation covering common node types.
    """
    import ast
    if hasattr(ast, "unparse"):
        return ast.unparse(node)
    return _ast_unparse_py2(node)


def _ast_unparse_py2(node):
    """Manual AST unparser for Python 2.7 (covers common cases)."""
    import ast
    import _ast
    if node is None:
        return None
    if isinstance(node, _ast.Name):
        return node.id
    if isinstance(node, _ast.Attribute):
        return _ast_unparse_py2(node.value) + "." + node.attr
    if isinstance(node, _ast.Subscript):
        base = _ast_unparse_py2(node.value)
        if hasattr(ast, "Index") and isinstance(node.slice, ast.Index):
            return base + "[" + _ast_unparse_py2(node.slice.value) + "]"
        return base + "[" + repr(node.slice) + "]"
    if isinstance(node, _ast.Call):
        return _ast_unparse_py2(node.func)
    if isinstance(node, _ast.Constant):
        return repr(node.value)
    if isinstance(node, _ast.Str):
        return repr(node.s)
    if isinstance(node, _ast.Num):
        return repr(node.n)
    return None


# ============================================================================
# 7. File I/O helpers
#    Always use io.open with explicit encoding to avoid GBK default on
#    Chinese Windows + Python 2.7.
# ============================================================================
def read_text_file(path, encoding="utf-8"):
    """Read a text file with explicit encoding."""
    with io.open(path, "r", encoding=encoding) as f:
        return f.read()


def write_text_file(path, content, encoding="utf-8"):
    """Write a text file with explicit encoding."""
    with io.open(path, "w", encoding=encoding) as f:
        f.write(content)


def read_json_file(path, encoding="utf-8"):
    """Read and parse a JSON file with explicit encoding."""
    with io.open(path, "r", encoding=encoding) as f:
        return json.load(f)


def write_json_file(path, obj, encoding="utf-8", **kwargs):
    """Write an object as JSON with explicit encoding and ensure_ascii=True."""
    kwargs.setdefault("ensure_ascii", True)
    data = json.dumps(obj, **kwargs)
    if PY2 and isinstance(data, unicode):
        data = data.encode("ascii")
    with open(path, "wb") as f:
        f.write(data)


# ============================================================================
# 8. Queue module name difference
# ============================================================================
try:
    import queue
except ImportError:
    import Queue as queue

try:
    import socketserver
except ImportError:
    import SocketServer as socketserver


# ============================================================================
# 9. TimeoutError
#    Doesn't exist in Python 2.7.
# ============================================================================
if PY2:
    class TimeoutError(Exception):
        pass
else:
    # Python 3 has TimeoutError as a builtin
    TimeoutError = TimeoutError  # noqa: F821 - references builtin


# ============================================================================
# 10. JSON-serializable converter with safe decoding
# ============================================================================
def jsonable(value):
    """Convert a value to a JSON-serializable form, handling GBK bytes."""
    if isinstance(value, bytes):
        value = safe_decode(value)
    try:
        json.dumps(value, ensure_ascii=True)
        return value
    except Exception:
        return {
            "repr": repr(value),
            "type": "%s.%s" % (type(value).__module__, type(value).__name__),
        }


# ============================================================================
# Export all public names
# ============================================================================
__all__ = [
    # Version
    "PY2", "PY3",
    # String types
    "string_types", "text_type", "binary_type",
    "ensure_str", "ensure_text",
    # Encoding
    "safe_decode", "safe_json_dumps", "safe_json_dump",
    # Context managers
    "redirect_stdout", "redirect_stderr",
    # System
    "cpu_count",
    # Traceback
    "get_traceback", "format_traceback",
    # AST
    "ast_unparse",
    # File I/O
    "read_text_file", "write_text_file", "read_json_file", "write_json_file",
    # Modules
    "queue", "socketserver",
    # Exceptions
    "TimeoutError",
    # JSON
    "jsonable",
]
