# Copyright (C) 2026 Synopsys, Inc. and ANSYS, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Helpers seeded into the PyLumerical MCP server's persistent subprocess.

This module is read as **text** by :mod:`ansys.lumerical.mcp.startup_code`,
base64-wrapped, and ``exec``'d in the framework's ``python -u -i`` child to
define the ``_lum_*`` helpers and the ``_lumerical_sessions`` registry used
by the MCP tools.

The parent (server) process must **not** import this file -- doing so would
run ``matplotlib.use("Agg")`` and the ``ansys.lumerical.core`` import probe
in the wrong process. Tests are the documented exception.

Names seeded as subprocess globals: ``FDTD``/``MODE``/``DEVICE``/
``INTERCONNECT`` (from ``ansys.lumerical.core``), the ``_lumerical_sessions``
registry, and ``_lum_open`` / ``_lum_close`` / ``_lum_get`` / ``_lum_list``
/ ``_lum_print_json`` / ``_lum_close_all``. Prefer the ``open_session`` MCP
tool over calling ``_lum_open`` directly.
"""

import json as _lum_json
import sys as _lum_sys

# Force a non-interactive renderer in this headless subprocess: an interactive
# default (TkAgg/QtAgg/MacOSX/Wx) would either fail with no $DISPLAY (headless
# Linux/CI/containers) or pop a window and block on plt.show() until timeout
# (desktop Linux/Windows/macOS). Agg is built into matplotlib core, requires no
# display, and behaves identically across platforms.
try:
    import matplotlib as _lum_matplotlib

    _lum_matplotlib.use("Agg")
except Exception as _lum_mpl_exc:
    print(
        "[pylumerical-mcp] matplotlib backend not configured "
        f"(continuing without Agg): {_lum_mpl_exc!r}",
        file=_lum_sys.stderr,
    )

try:
    from ansys.lumerical.core import DEVICE, FDTD, INTERCONNECT, MODE

    _LUM_IMPORT_ERROR = None
except Exception as _e:
    FDTD = MODE = DEVICE = INTERCONNECT = None
    _LUM_IMPORT_ERROR = repr(_e)

_LUM_PRODUCTS = {
    "fdtd": FDTD,
    "mode": MODE,
    "device": DEVICE,
    "interconnect": INTERCONNECT,
}
_lumerical_sessions: dict = {}


def _lum_open(name, product, filename=None, hide=False):
    """Open a Lumerical session and register it under ``name``."""
    if _LUM_IMPORT_ERROR is not None:
        raise RuntimeError("ansys.lumerical.core failed to import: " + _LUM_IMPORT_ERROR)
    if name in _lumerical_sessions:
        raise ValueError("Session " + repr(name) + " already exists")
    key = product.lower()
    if key not in _LUM_PRODUCTS or _LUM_PRODUCTS[key] is None:
        raise ValueError(
            "Unknown product "
            + repr(product)
            + ". Expected one of: fdtd, mode, device, interconnect."
        )
    cls = _LUM_PRODUCTS[key]
    kwargs = {"hide": bool(hide)}
    if filename:
        kwargs["filename"] = filename
    _lumerical_sessions[name] = cls(**kwargs)
    return {
        "name": name,
        "product": key,
        "filename": filename,
        "hide": bool(hide),
    }


def _lum_close(name):
    """Close and de-register a session."""
    sess = _lumerical_sessions.pop(name, None)
    if sess is None:
        raise KeyError("No session " + repr(name))
    try:
        sess.close()
    except Exception as _exc:
        # Session is already de-registered; report the close error to stderr but
        # still return success so the MCP tool envelope reflects the registry.
        print(
            f"[pylumerical-mcp] warning: close({name!r}) raised: {_exc!r}",
            file=_lum_sys.stderr,
        )
    return {"closed": name}


def _lum_get(name):
    """Return the live Lumerical handle for ``name`` (raises KeyError)."""
    if name not in _lumerical_sessions:
        raise KeyError("No session " + repr(name) + ". Open one with open_session().")
    return _lumerical_sessions[name]


def _lum_list():
    """List currently open sessions (name + product class name)."""
    return [{"name": k, "product": type(v).__name__} for k, v in _lumerical_sessions.items()]


def _lum_print_json(obj, *, max_array_size=200_000, indent=None):
    """Serialize an arbitrary Lumerical/Python object and print as JSON.

    Handles numpy arrays (with size guard), complex numbers, dicts, lists,
    tuples, and nested combinations thereof. Anything else falls through to
    ``json.dumps(default=str)``.
    """
    try:
        import numpy as _np
    except Exception:
        _np = None

    def _conv(o):
        if _np is not None and isinstance(o, _np.ndarray):
            if o.size > max_array_size:
                return {
                    "__truncated__": True,
                    "shape": list(o.shape),
                    "dtype": str(o.dtype),
                    "preview": _conv(o.flatten()[:50].tolist()),
                }
            # Recurse so nested complex / numpy scalars get structured handling.
            return _conv(o.tolist())
        if _np is not None and isinstance(o, _np.generic):
            # numpy scalar (e.g. np.float64, np.complex128) -> Python scalar.
            return _conv(o.item())
        if isinstance(o, complex):
            return {"real": o.real, "imag": o.imag}
        if isinstance(o, dict):
            return {str(k): _conv(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [_conv(v) for v in o]
        return o

    print(_lum_json.dumps(_conv(obj), indent=indent, default=str))


def _lum_close_all():
    """Close every open session (used during server shutdown)."""
    for _n in list(_lumerical_sessions):
        try:
            _lum_close(_n)
        except Exception as _exc:
            # Keep tearing down the rest even if one session refuses to close.
            print(
                f"[pylumerical-mcp] warning: close_all dropped {_n!r}: {_exc!r}",
                file=_lum_sys.stderr,
            )


print("[pylumerical-mcp] startup helpers loaded; import_error=" + repr(_LUM_IMPORT_ERROR))
