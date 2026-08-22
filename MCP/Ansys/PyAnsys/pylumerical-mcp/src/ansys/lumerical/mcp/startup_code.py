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

"""Bootstrap code fed into the framework's persistent Python subprocess.

The framework's :class:`PersistentPythonSession` pipes startup code into a
``python -u -i`` stdin, whose line-oriented parser treats a blank line at
column 0 as the end of a compound statement, so multi-line ``def``/``try``
blocks can't be sent directly. Instead, the real helpers live in the normal,
lint-friendly :mod:`ansys.lumerical.mcp._subprocess_helpers` module. Its
source is read, base64-encoded, and shipped as a two-line wrapper that decodes
and executes it. (``exec`` parses the whole string as a module, so blank lines
and docstrings work.)

:mod:`_subprocess_helpers` is **never imported in this parent process**.
Its source is only read via :mod:`importlib.resources`, keeping the parent
free of its import-time side effects (``matplotlib.use('Agg')`` and the
``ansys.lumerical.core`` probe) and letting the subprocess run without
``ansys.lumerical.mcp`` installed (only built-in :mod:`base64` is needed).

Seeded subprocess globals: ``FDTD``/``MODE``/``DEVICE``/``INTERCONNECT``
(from ``ansys.lumerical.core``), the ``_lumerical_sessions`` registry, and
the ``_lum_*`` helpers. (See :mod:`ansys.lumerical.mcp._subprocess_helpers`.)
"""

from __future__ import annotations

import base64
from importlib.resources import files

_INNER_STARTUP_SOURCE: str = (
    files("ansys.lumerical.mcp").joinpath("_subprocess_helpers.py").read_text(encoding="utf-8")
)

_ENCODED_STARTUP = base64.b64encode(_INNER_STARTUP_SOURCE.encode("utf-8")).decode("ascii")

# Two simple top-level statements; no blank lines, no compound statements at
# the input layer -- safe to feed into ``python -u -i`` via stdin.
LUMERICAL_STARTUP_CODE = (
    "import base64 as _lum_b64\n"
    f"exec(compile(_lum_b64.b64decode('{_ENCODED_STARTUP}').decode('utf-8'), "
    "'<ansys_lumerical_mcp_startup>', 'exec'))\n"
)


__all__ = ["LUMERICAL_STARTUP_CODE"]
