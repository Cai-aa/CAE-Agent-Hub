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

"""MCP-side session wrapper for a PyCFX PostProcessing (CFD-Post) session."""

from __future__ import annotations

import logging
from typing import Any

_LOG = logging.getLogger(__name__)


class PostSession:
    """Wrapper for a live PyCFX PostProcessing session."""

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
        results_file: str,
        *,
        ui_mode: str | None = None,
        product_version: str | None = None,
        cleanup_on_exit: bool = True,
    ) -> "PostSession":
        """Launch CFD-Post for a CFX results file and wrap the session.

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

        Returns
        -------
        'PostSession'
            Session wrapper connected to the requested CFX process.
        """
        import ansys.cfx.core as pycfx

        kwargs: dict[str, Any] = {
            "results_file_name": results_file,
            "cleanup_on_exit": cleanup_on_exit,
        }
        if ui_mode is not None:
            kwargs["ui_mode"] = ui_mode
        if product_version is not None:
            kwargs["product_version"] = product_version

        _LOG.info("Launching CFD-Post with results file: %s", results_file)
        pypost = pycfx.PostProcessing.from_install(**kwargs)
        return cls(pypost, mode="launch")

    @classmethod
    def attach(
        cls,
        *,
        ip: str | None = None,
        port: int | None = None,
        password: str | None = None,
        server_info_file: str | None = None,
    ) -> "PostSession":
        """Attach to an existing CFD-Post service and wrap the session.

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
        'PostSession'
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

        _LOG.info("Connecting to CFD-Post (ip=%s port=%s sinfo=%s)", ip, port, server_info_file)
        pypost = pycfx.connect_to_cfx(**kwargs)
        return cls(pypost, mode="attach")

    @classmethod
    def from_sinfo(cls, sinfo_path: str) -> "PostSession":
        """Attach to CFD-Post using a PyCFX server information file.

        Parameters
        ----------
        sinfo_path : str
            PyCFX server information file to use for attachment.

        Returns
        -------
        'PostSession'
            Session wrapper connected to the requested CFX process.
        """
        return cls.attach(server_info_file=sinfo_path)

    @property
    def raw(self) -> Any:
        """Underlying PyCFX CFD-Post session object.

        Returns
        -------
        Any
            Raw PyCFX postprocessing session used by generated code and backend helpers.
        """
        return self._session

    def load_results(self, file_path: str) -> None:
        """Load a CFX results file into the wrapped CFD-Post session.

        Parameters
        ----------
        file_path : str
            CFX ``.res`` file path to open in CFD-Post.

        Returns
        -------
        None
            No value is returned. The CFD-Post session loads the requested results file.
        """
        self._session.file.load_results(file_name=file_path)

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
