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

"""PyLumerical MCP server entry point.

Defines :class:`PyLumericalMCP`, a subclass of
:class:`ansys.common.mcp.PyAnsysBaseMCP` that:

- Replaces the framework's default subprocess startup code with one that does
  not assume Matplotlib/PyVista/PIL are installed (they aren't, in
  baseline dependencies), but seeds the Lumerical session registry and helpers.
- Registers the MCP tools declared in :mod:`ansys.lumerical.mcp.tools`.
- Cleans up any open Lumerical sessions on shutdown.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import logging
import os
import threading
from typing import AsyncIterator, Optional

from ansys.common.mcp import PyAnsysBaseMCP
from fastmcp import FastMCP

from ansys.lumerical.mcp.config import Config, load_config
from ansys.lumerical.mcp.context import PyLumericalContext
from ansys.lumerical.mcp.persistent_session import LumericalPersistentPythonSession
from ansys.lumerical.mcp.prompts import PYLUMERICAL_SYSTEM_PROMPT, pylumerical_system_prompt
from ansys.lumerical.mcp.startup_code import LUMERICAL_STARTUP_CODE

logger = logging.getLogger(__name__)
_CLOSE_ALL_JOIN_TIMEOUT_S = 5.0


def _sanitize_python_startup_env() -> None:
    """Remove interactive startup hooks that pollute subprocess stdout."""
    os.environ.pop("PYTHONSTARTUP", None)


def _set_lumerical_install_path(install_dir: str) -> None:
    """Best-effort: tell the lumapi where Lumerical lives."""
    try:
        from ansys.api.lumerical.lumapi import InteropPaths

        InteropPaths.setLumericalInstallPath(install_dir)
        logger.info("Set Lumerical install path: %s", install_dir)
    except Exception as exc:  # pragma: no cover - depends on installed lumapi
        logger.warning("Failed to set Lumerical install path %r: %s", install_dir, exc)


class PyLumericalMCP(PyAnsysBaseMCP):
    """MCP server exposing Ansys Lumerical (via PyLumerical) to LLM agents.

    Hosts a single :class:`PersistentPythonSession` subprocess that owns all
    live Lumerical handles. Multiple named sessions of any product type
    (FDTD/MODE/DEVICE/INTERCONNECT) live in that subprocess as
    ``_lumerical_sessions[name]``. The MCP server only tracks metadata.
    """

    def __init__(
        self,
        config: Optional[Config] = None,
        python_executable: Optional[str] = None,
        working_directory: Optional[str] = None,
        **kwargs,
    ):
        self._config: Config = config or load_config()
        if self._config.install_dir:
            _set_lumerical_install_path(self._config.install_dir)
        super().__init__(
            python_executable=python_executable,
            working_directory=working_directory,
            **kwargs,
        )

    def create_context(self) -> PyLumericalContext:
        """Build the typed app context with the Lumerical-aware subprocess.

        Uses :class:`LumericalPersistentPythonSession` so that long, silent
        Lumerical startup phases (``FDTD()`` / ``MODE()`` / ...). Don't trip
        the framework's 0.5 s no-data safety break and lose their output.
        """
        py_session = LumericalPersistentPythonSession(
            python_executable=self.python_executable,
            working_directory=self.working_directory,
            startup_code=LUMERICAL_STARTUP_CODE,
        )
        return PyLumericalContext(python_session=py_session, command_history=[])

    def product_startup(self) -> None:
        """Run framework startup logging after subprocess launch."""
        logger.info("PyLumericalMCP ready (sessions registry initialized).")

    def cleanup_python_session(self) -> None:
        """Close Lumerical handles *before* tearing down the subprocess.

        ``_lum_close_all()`` must run while the subprocess is still alive. It
        is flushed here (best-effort, bounded by ``_CLOSE_ALL_JOIN_TIMEOUT_S``
        via a daemon thread) before delegating to the base teardown. Running it
        in ``product_cleanup`` would be too late. The subprocess is gone by
        then, and lumapi's child processes are left orphaned.

        Stays synchronous so direct unit tests work without an event loop;
        :meth:`product_lifespan` offloads the call via :func:`asyncio.to_thread`.
        """
        ctx = getattr(self, "context", None)
        if ctx is None:
            return
        py = ctx.python_session
        if py is not None and py.is_running():
            close_error: Exception | None = None

            def _close_all() -> None:
                nonlocal close_error
                try:
                    py.execute("_lum_close_all()")
                except Exception as exc:  # pragma: no cover - best effort
                    close_error = exc

            try:
                # ``execute`` is intentionally unbounded. Run the close helper
                # in a daemon thread so teardown can still progress if close
                # wedges (for example, a stuck license-server handshake).
                close_thread = threading.Thread(target=_close_all, daemon=True)
                close_thread.start()
                close_thread.join(timeout=_CLOSE_ALL_JOIN_TIMEOUT_S)
                if close_thread.is_alive():
                    logger.warning(
                        "Timed out waiting %.1fs for _lum_close_all(); forcing subprocess stop.",
                        _CLOSE_ALL_JOIN_TIMEOUT_S,
                    )
                elif close_error is not None:
                    logger.warning("Error during Lumerical session cleanup: %s", close_error)
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Error during Lumerical session cleanup orchestration: %s", exc)
        super().cleanup_python_session()

    def product_cleanup(self) -> None:
        """No-op: Lumerical handle cleanup happens in ``cleanup_python_session``."""
        logger.debug("PyLumericalMCP shutdown complete.")

    @asynccontextmanager
    async def product_lifespan(self, server: FastMCP) -> AsyncIterator[PyLumericalContext]:
        """Lifespan wrapper that keeps the event loop responsive on shutdown.

        Identical to the base :meth:`PyAnsysBaseMCP.product_lifespan` except
        that the potentially slow :meth:`cleanup_python_session` (which runs
        ``_lum_close_all()`` against the live subprocess) is dispatched via
        :func:`asyncio.to_thread`, so the synchronous teardown can't freeze
        the event loop and block the STDIO transport from flushing its final
        JSON-RPC writes. Startup stays on the loop -- it's fast and runs
        before any tool traffic.
        """
        self.server = server  # type: ignore[attr-defined]
        self.context = self.create_context()  # type: ignore[attr-defined]

        try:
            self.start_python_session()
            self.product_startup()

            yield self.context  # type: ignore[attr-defined]

        finally:
            await asyncio.to_thread(self.cleanup_python_session)
            self.product_cleanup()


config = load_config()

app = PyLumericalMCP(
    name="pylumerical-mcp",
    config=config,
    instructions=PYLUMERICAL_SYSTEM_PROMPT,
)
app.prompt(
    name="pylumerical_system_prompt",
    description=(
        "System prompt for the PyLumerical MCP simulation assistant. "
        "Provides the product-agnostic Lumerical workflow order and the "
        "'call get_guidelines_for before writing Lumerical Python code' rule."
    ),
)(pylumerical_system_prompt)
