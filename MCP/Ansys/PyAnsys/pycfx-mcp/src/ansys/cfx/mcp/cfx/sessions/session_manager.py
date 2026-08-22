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

"""Process-local manager for active PyCFX sessions."""

from __future__ import annotations

import logging
from typing import Any, ClassVar, cast

from ansys.cfx.mcp.cfx.sessions.pre_session import PreSession
from ansys.cfx.mcp.cfx.sessions.solver_session import SolverSession

_LOG = logging.getLogger(__name__)


class SessionManager:
    """Track active CFX sessions and artifacts for the backend namespace."""

    _pre: ClassVar[Any | None] = None
    _solver: ClassVar[Any | None] = None
    _post: ClassVar[Any | None] = None
    _solver_input_file: ClassVar[str | None] = None
    _results_file: ClassVar[str | None] = None

    @classmethod
    def launch_pre(
        cls,
        *,
        launcher: str = "from_install",
        ui_mode: str | None = None,
        product_version: str | None = None,
        case_file_name: str | None = None,
        start_timeout: int = 60,
        additional_arguments: str = "",
        container_dict: dict[str, Any] | None = None,
        cleanup_on_exit: bool = True,
    ) -> PreSession:
        """Launch and remember a new CFX-Pre session.

        Parameters
        ----------
        launcher : str, default: ``'from_install'``
            PyCFX launcher method to call.
        ui_mode : str | None, default: None
            Optional CFX UI mode for the launched process.
        product_version : str | None, default: None
            Optional Ansys product version to launch.
        case_file_name : str | None, default: None
            CFX case file to open when launching CFX-Pre.
        start_timeout : int, default: 60
            Maximum number of seconds to wait for a launched CFX process.
        additional_arguments : str, default: ``''``
            Additional command-line arguments to pass to the CFX launcher.
        container_dict : dict[str, Any] | None, default: None
            Container-launch configuration to pass to PyCFX.
        cleanup_on_exit : bool, default: True
            Whether PyCFX should clean up the launched process on exit.

        Returns
        -------
        PreSession | None
            Session wrapper connected to the requested CFX process.
        """
        if case_file_name and cls._is_active(cls._pre):
            cls._close_session(cls._pre)
            cls._pre = None

        if cls._is_active(cls._pre):
            return cast(PreSession, cls._pre)

        cls._pre = PreSession.launch(
            launcher=launcher,
            ui_mode=ui_mode,
            product_version=product_version,
            case_file_name=case_file_name,
            start_timeout=start_timeout,
            additional_arguments=additional_arguments,
            container_dict=container_dict,
            cleanup_on_exit=cleanup_on_exit,
        )
        if cls._pre is None:
            raise RuntimeError("Failed to initialize the CFX pre-session.")
        return cls._pre

    @classmethod
    def attach_pre(
        cls,
        *,
        ip: str | None = None,
        port: int | None = None,
        password: str | None = None,
        server_info_file: str | None = None,
        **_: Any,
    ) -> PreSession:
        """Attach to an existing CFX-Pre session and remember it.

        Parameters
        ----------
        ip : str | None, default: None
            IP address of the running CFX service to attach to.
        port : int | None, default: None
            Port of the running CFX service to attach to.
        password : str | None, default: None
            Password for the running CFX service, when required.
        server_info_file : str | None, default: None
            PyCFX server information file used for attachment.
        _ : Any
            Optional connection value forwarded to PyCFX when provided.

        Returns
        -------
        PreSession
            Session wrapper connected to the requested CFX process.
        """
        if cls._is_active(cls._pre):
            cls._close_session(cls._pre)
        cls._pre = PreSession.attach(
            ip=ip,
            port=port,
            password=password,
            server_info_file=server_info_file,
        )
        return cls._pre

    @classmethod
    def launch_solver(
        cls,
        solver_input_file: str,
        *,
        product_version: str | None = None,
        cleanup_on_exit: bool = True,
        **_: Any,
    ) -> SolverSession:
        """Launch and remember a CFX-Solver session from a solver input file.

        Parameters
        ----------
        solver_input_file : str
            CFX ``.def`` file used to start the solver session.
        product_version : str | None, default: None
            Optional Ansys product version to launch.
        cleanup_on_exit : bool, default: True
            Whether PyCFX should clean up the launched process on exit.
        _ : Any
            Optional connection value forwarded to PyCFX when provided.

        Returns
        -------
        SolverSession
            Session wrapper connected to the requested CFX process.
        """
        if cls._is_active(cls._solver):
            cls._close_session(cls._solver)
        cls._solver_input_file = solver_input_file
        cls._solver = SolverSession.launch(
            solver_input_file,
            product_version=product_version,
            cleanup_on_exit=cleanup_on_exit,
        )
        return cls._solver

    @classmethod
    def launch_post(
        cls,
        results_file: str,
        *,
        ui_mode: str | None = None,
        product_version: str | None = None,
        cleanup_on_exit: bool = True,
        **_: Any,
    ):
        """Launch and remember a CFD-Post session for an optional results file.

        Parameters
        ----------
        results_file : str
            Cached or requested CFX results-file path.
        ui_mode : str | None, default: None
            Optional CFX UI mode for the launched process.
        product_version : str | None, default: None
            Optional Ansys product version to launch.
        cleanup_on_exit : bool, default: True
            Whether PyCFX should clean up the launched process on exit.
        _ : Any
            Optional connection value forwarded to PyCFX when provided.

        Returns
        -------
        Any
            Session wrapper connected to the requested CFX process.
        """
        from ansys.cfx.mcp.cfx.sessions.post_session import PostSession

        if cls._is_active(cls._post):
            cls._close_session(cls._post)
        cls._results_file = results_file
        cls._post = PostSession.launch(
            results_file,
            ui_mode=ui_mode,
            product_version=product_version,
            cleanup_on_exit=cleanup_on_exit,
        )
        return cls._post

    @classmethod
    def attach_post(
        cls,
        *,
        ip: str | None = None,
        port: int | None = None,
        password: str | None = None,
        server_info_file: str | None = None,
        **_: Any,
    ):
        """Attach to an existing CFD-Post session and remember it.

        Parameters
        ----------
        ip : str | None, default: None
            IP address of the running CFX service to attach to.
        port : int | None, default: None
            Port of the running CFX service to attach to.
        password : str | None, default: None
            Password for the running CFX service, when required.
        server_info_file : str | None, default: None
            PyCFX server information file used for attachment.
        _ : Any
            Optional connection value forwarded to PyCFX when provided.

        Returns
        -------
        Any
            Session wrapper connected to the requested CFX process.
        """
        from ansys.cfx.mcp.cfx.sessions.post_session import PostSession

        if cls._is_active(cls._post):
            cls._close_session(cls._post)
        cls._post = PostSession.attach(
            ip=ip,
            port=port,
            password=password,
            server_info_file=server_info_file,
        )
        return cls._post

    @classmethod
    def get_pre(cls):
        """Get the active CFX-Pre session wrapper, if one is available.

        Returns
        -------
        Any
            Requested CFX data or metadata for the active session.
        """
        return cls._pre if cls._is_active(cls._pre) else None

    @classmethod
    def get_solver(cls):
        """Get the active CFX-Solver session wrapper, if one is available.

        Returns
        -------
        Any
            Requested CFX data or metadata for the active session.
        """
        return cls._solver if cls._is_active(cls._solver) else None

    @classmethod
    def get_post(cls):
        """Get the active CFD-Post session wrapper, if one is available.

        Returns
        -------
        Any
            Requested CFX data or metadata for the active session.
        """
        return cls._post if cls._is_active(cls._post) else None

    @classmethod
    def get_solver_input_file(cls) -> str | None:
        """Get the cached CFX solver input-file path.

        Returns
        -------
        str | None
            Requested CFX data or metadata for the active session.
        """
        return cls._solver_input_file

    @classmethod
    def get_results_file(cls) -> str | None:
        """Get the cached CFX solver results-file path.

        Returns
        -------
        str | None
            Requested CFX data or metadata for the active session.
        """
        return cls._results_file

    @classmethod
    def set_results_file(cls, results_file: str | None) -> None:
        """Store the latest CFX solver results-file path.

        Parameters
        ----------
        results_file : str | None
            Cached or requested CFX results-file path.

        Returns
        -------
        None
            No value is returned. Side effects are applied to the relevant cache, session, or
            server.
        """
        cls._results_file = results_file

    @classmethod
    def status(cls) -> dict[str, Any]:
        """Return a structured status summary for the active CFX backend or session manager.

        Returns
        -------
        dict[str, Any]
            Structured status payload for the active backend or session manager.
        """
        pre_active = cls.get_pre() is not None
        solver_active = cls.get_solver() is not None
        post_active = cls.get_post() is not None
        return {
            "pre": pre_active,
            "solver": solver_active,
            "post": post_active,
            "cfx_pre": pre_active,
            "cfx_solver": solver_active,
            "cfx_post": post_active,
            "solver_input_file": cls._solver_input_file,
            "def_file": cls._solver_input_file,
            "results_file": cls._results_file,
            "res_file": cls._results_file,
        }

    @classmethod
    def disconnect(cls) -> None:
        """Disconnect this backend from its active CFX runtime or service.

        Returns
        -------
        None
            No value is returned. Side effects are applied to the relevant cache, session, or
            server.
        """
        for session in (cls._post, cls._solver, cls._pre):
            cls._close_session(session)
        cls._pre = None
        cls._solver = None
        cls._post = None
        cls._solver_input_file = None
        cls._results_file = None

    @classmethod
    def cleanup(cls) -> None:
        """Close inactive remembered sessions and clear stale session references.

        Returns
        -------
        None
            No value is returned. Side effects are applied to the relevant cache, session, or
            server.
        """
        cls.disconnect()

    @classmethod
    def close_all(cls) -> None:
        """Close every remembered CFX session wrapper.

        Returns
        -------
        None
            No value is returned. Side effects are applied to the relevant cache, session, or
            server.
        """
        cls.disconnect()

    @staticmethod
    def _is_active(session: Any | None) -> bool:
        """Whether a session wrapper reports itself as active.

        Parameters
        ----------
        session : Any | None
            PyCFX session or wrapper object managed by this helper.

        Returns
        -------
        bool
            Boolean answer for the requested condition.
        """
        if session is None:
            return False
        active = getattr(session, "is_active", True)
        if callable(active):
            try:
                return bool(active())
            except Exception:
                return False
        return bool(active)

    @staticmethod
    def _close_session(session: Any | None) -> None:
        """Close one session wrapper while suppressing cleanup-time errors.

        Parameters
        ----------
        session : Any | None
            PyCFX session or wrapper object managed by this helper.

        Returns
        -------
        None
            No value is returned. Side effects are applied to the relevant cache, session, or
            server.
        """
        if session is None:
            return
        close = getattr(session, "exit", None)
        if not callable(close):
            return
        try:
            close()
        except Exception:
            _LOG.exception("Failed to close CFX session")
