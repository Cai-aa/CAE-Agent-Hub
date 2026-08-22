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

"""MCP-side session wrapper for a PyCFX Solver session."""

from __future__ import annotations

import logging
from typing import Any

_LOG = logging.getLogger(__name__)


class SolverSession:
    """Wrapper for a live PyCFX Solver session.

    Consumes a DEF file from CFX-Pre and produces an RES results file
    for CFD-Post.

    .. note::
        The CFX Solver does not support IP address/port/password attachment.
        It can only be launched from a DEF file with ``from_install()``.
    """

    def __init__(self, session: Any, *, mode: str = "launch") -> None:
        """Initialize this object with the dependencies required for later operations.

        Parameters
        ----------
        session : Any
            PyCFX session or wrapper object managed by this helper.
        mode : str, default: ``'launch'``
            Mode that controls how the operation runs.

        Returns
        -------
        None
            No value is returned. Side effects are applied to the relevant cache, session, or
            server.
        """
        self._session = session
        self.mode = mode

    @classmethod
    def launch(
        cls,
        solver_input_file: str,
        *,
        product_version: str | None = None,
        cleanup_on_exit: bool = True,
    ) -> "SolverSession":
        """Launch the CFX-Solver from a solver input file and wrap the session.

        Parameters
        ----------
        solver_input_file : str
            CFX DEF file for starting the solver session.
        product_version : str | None, default: None
            Optional Ansys product version to launch.
        cleanup_on_exit : bool, default: ``True``
            Whether PyCFX should clean up the launched process on exit.

        Returns
        -------
        'SolverSession'
            Session wrapper connected to the requested CFX process.
        """
        import ansys.cfx.core as pycfx

        kwargs: dict[str, Any] = {
            "solver_input_file_name": solver_input_file,
            "cleanup_on_exit": cleanup_on_exit,
        }
        if product_version is not None:
            kwargs["product_version"] = product_version
        _LOG.info("Launching solver with input: %s", solver_input_file)
        pysolve = pycfx.Solver.from_install(**kwargs)
        return cls(pysolve, mode="launch")

    @property
    def raw(self) -> Any:
        """Underlying PyCFX CFX-Solver session object.

        Returns
        -------
        Any
            Raw PyCFX solver session used by generated code and backend helpers.
        """
        return self._session

    def start_run(self) -> None:
        """Start the solver run for the wrapped CFX-Solver session.

        Returns
        -------
        None
            No value is returned. The solver session begins running asynchronously.
        """
        _LOG.info("Starting solver run...")
        self._session.solution.start_run()

    def stop_run(self, wait: bool = True) -> None:
        """Stop the active CFX-Solver run.

        Parameters
        ----------
        wait : bool, default: True
            Whether to wait until the solver acknowledges the stop request.

        Returns
        -------
        None
            No value is returned. The solver run is requested to stop.
        """
        _LOG.info("Stopping solver run (wait=%s)...", wait)
        self._session.solution.stop_run(wait_for_run=wait)

    def wait_for_run(self, interval: int = 10, timeout: int = 86400) -> None:
        """Wait for the active CFX-Solver run to finish.

        Parameters
        ----------
        interval : int, default: 10
            Polling interval in seconds while waiting for completion.
        timeout : int, default: 86400
            Maximum number of seconds to wait for the solver.

        Returns
        -------
        None
            No value is returned. The call blocks until completion or timeout.
        """
        _LOG.info("Waiting for solver run (timeout=%ds)...", timeout)
        self._session.solution.wait_for_run(interval=interval, timeout=timeout)

    def get_results_file_name(self) -> str | None:
        """Return the results file produced by the wrapped solver session.

        Returns
        -------
        str | None
            Results-file path reported by PyCFX, or ``None`` if no result is available yet.
        """
        result = self._session.solution.get_results_file_name()
        return str(result) if result is not None else None

    def is_running(self) -> bool:
        """Check whether the wrapped CFX-Solver run is still running.

        Returns
        -------
        bool
            Whether the wrapped solver run is still active.
        """
        return bool(self._session.solution.is_running())

    def exit(self) -> None:
        """Exit the wrapped CFX session and release its resources.

        Returns
        -------
        None
            No value is returned. Side effects are applied to the relevant cache, session, or
            server.
        """
        if self._session:
            self._session.exit()
            self._session = None

    @property
    def is_active(self) -> bool:
        """Check whether the wrapped CFX session still appears active.

        Returns
        -------
        bool
            Whether the wrapped session appears to still be usable.
        """
        return self._session is not None
