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

"""MCP-side session wrapper for a PyCFX PreProcessing (CFX-Pre) session."""

from __future__ import annotations

import logging
from typing import Any

_LOG = logging.getLogger(__name__)


class PreSession:
    """Wrapper for a live PyCFX PreProcessing session."""

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
        self.mode = mode  # "launch" | "attach"

    @classmethod
    def launch(
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
    ) -> "PreSession":
        """Launch a new PyCFX CFX-Pre session and wrap it for MCP use.

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
            Additional command-line arguments passed to the CFX launcher.
        container_dict : dict[str, Any] | None, default: None
            Container-launch configuration passed to PyCFX.
        cleanup_on_exit : bool, default: True
            Whether PyCFX should clean up the launched process on exit.

        Returns
        -------
        'PreSession'
            Session wrapper connected to the requested CFX process.
        """
        import ansys.cfx.core as pycfx

        if launcher not in {"from_install", "from_container"}:
            raise ValueError("launcher must be 'from_install' or 'from_container'")
        if launcher == "from_container" and case_file_name is not None:
            raise ValueError("case_file_name is only supported with launcher='from_install'")

        kwargs: dict[str, Any] = {
            "cleanup_on_exit": cleanup_on_exit,
            "start_timeout": start_timeout,
            "additional_arguments": additional_arguments,
        }
        if ui_mode is not None:
            kwargs["ui_mode"] = ui_mode
        if product_version is not None:
            kwargs["product_version"] = product_version
        if case_file_name is not None:
            kwargs["case_file_name"] = case_file_name
        if container_dict is not None:
            kwargs["container_dict"] = container_dict

        _LOG.info("Launching new CFX-Pre session with %s kwargs=%s", launcher, kwargs)
        try:
            launch = getattr(pycfx.PreProcessing, launcher)
            pypre = launch(**kwargs)
        except Exception as exc:
            _LOG.exception("CFX-Pre launch failed (PyCFX raised an exception)")

            # PyCFX typically wraps launcher errors in LaunchCFXError
            cause = getattr(exc, "__cause__", None)
            context = getattr(exc, "__context__", None)

            if cause:
                _LOG.error("Underlying launcher cause: %s: %s", type(cause).__name__, cause)
                # Some LaunchCFXError causes include the actual command used
                for attr in ("command", "args", "cmd"):
                    val = getattr(cause, attr, None)
                    if val:
                        _LOG.error("Launcher %s: %s", attr, val)

            if context and context is not cause:
                _LOG.error("Additional context: %s: %s", type(context).__name__, context)

            # Print environment info helpful for diagnosing ANSYS launches
            try:
                import os

                _LOG.error("ANSYS installation env snapshot:")
                for k, v in sorted(os.environ.items()):
                    if k.startswith("ANSYS") or "CFX" in k:
                        _LOG.error("%s=%s", k, v)
            except Exception:
                _LOG.exception("Failed dumping environment variables")

            raise RuntimeError(f"Failed to start CFX-Pre: {exc}") from exc

        if case_file_name is None:
            try:
                pypre.file.new_case()
                _LOG.info("Initialized new CFX case")
            except Exception:
                _LOG.exception("CFX-Pre launched but failed to initialize new case")
        else:
            _LOG.info("Launched CFX-Pre with case file: %s", case_file_name)

        return cls(pypre, mode=launcher)

    @classmethod
    def attach(
        cls,
        *,
        ip: str | None = None,
        port: int | None = None,
        password: str | None = None,
        server_info_file: str | None = None,
    ) -> "PreSession":
        """Attach to an existing CFX-Pre service and wrap the session.

        Parameters
        ----------
        ip : str | None, default: None
            IP address of the running CFX service to attach to.
        port : int | None, default: None
            Port of the running CFX service to attach to.
        password : str | None, default: None
            Password for the running CFX service, when required.
        server_info_file : str | None, default: None
            PyCFX server information file to use for attachment.

        Returns
        -------
        'PreSession'
            Session wrapper connected to the requested CFX process.
        """
        import ansys.cfx.core as pycfx

        kwargs: dict[str, Any] = {}
        if server_info_file:
            kwargs["server_info_file_name"] = server_info_file
        if ip:
            kwargs["ip"] = ip
        if port:
            kwargs["port"] = port
        if password:
            kwargs["password"] = password
        _LOG.info("Connecting to CFX-Pre (ip=%s port=%s sinfo=%s)", ip, port, server_info_file)
        pypre = pycfx.connect_to_cfx(**kwargs)
        return cls(pypre, mode="attach")

    @classmethod
    def from_sinfo(cls, sinfo_path: str) -> "PreSession":
        """Attach to CFX-Pre using a PyCFX server information file.

        Parameters
        ----------
        sinfo_path : str
            PyCFX server information file to use for attachment.

        Returns
        -------
        'PreSession'
            Session wrapper connected to the requested CFX process.
        """
        return cls.attach(server_info_file=sinfo_path)

    @property
    def raw(self) -> Any:
        """Underlying PyCFX CFX-Pre session object.

        Returns
        -------
        Any
            Raw PyCFX preprocessing session used by generated code and backend helpers.
        """
        return self._session

    def import_mesh(self, file_path: str) -> None:
        """Import a mesh file into the wrapped CFX-Pre session.

        Parameters
        ----------
        file_path : str
            Mesh file path to import into CFX-Pre.

        Returns
        -------
        None
            No value is returned. The mesh is loaded into the active CFX-Pre case.
        """
        self._session.file.import_mesh(file_name=file_path)

    def open_case(self, file_path: str) -> None:
        """Open an existing CFX case in the wrapped CFX-Pre session.

        Parameters
        ----------
        file_path : str
            CFX case file path to open.

        Returns
        -------
        None
            No value is returned. The active CFX-Pre case is replaced by the requested case.
        """
        self._session.file.open_case(file_name=file_path)

    def write_solver_input(self, file_path: str) -> None:
        """Write a CFX-Solver input file from the current CFX-Pre setup.

        Parameters
        ----------
        file_path : str
            Destination ``.def`` file path for the solver input.

        Returns
        -------
        None
            No value is returned. The solver input file is written on disk.
        """
        self._session.file.write_solver_input(file_name=file_path)

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
        """Whether the wrapped CFX session still appears active.

        Returns
        -------
        bool
            Whether the wrapped session appears to still be usable.
        """
        return self._session is not None
