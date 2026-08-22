# Copyright (C) 2025 - 2026 ANSYS, Inc. and/or its affiliates.
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

"""Lifespan and CLI entry for the MCP server with startup options."""

import argparse
from dataclasses import dataclass
import sys
from typing import Any, Optional, cast

from ansys.common.mcp import (
    PyAnsysBaseMCP,
)
from ansys.common.mcp.context import PyAnsysBaseAppContext
from ansys.common.mcp.helpers import PersistentPythonSession, logger


@dataclass
class PyMAPDLAppContext(PyAnsysBaseAppContext):
    """Application context with typed dependencies and CLI options.

    Attributes
    ----------
    mapdl : Optional[Any]
        MAPDL instance connection. Using Any to avoid type issues with MAPDL variants.
    transport_type : str
        Transport type for MCP server ('stdio' or 'http').
    mapdl_ip : Optional[str]
        IP address or hostname for MAPDL connection.
    mapdl_port : Optional[int]
        Port number for MAPDL connection.
    connect_on_startup : bool
        Whether to attempt MAPDL connection on MCP startup.
    http_host : str
        Host address for HTTP transport.
    http_port : int
        Port number for HTTP transport.
    cors_origins : Optional[list[str]]
        List of allowed CORS origins for HTTP transport.
    """

    mapdl: Any | None = None  # Using Any to avoid type issues with MAPDL variants
    transport_type: str = "stdio"
    mapdl_ip: str | None = None
    mapdl_port: int | None = None
    connect_on_startup: bool = False
    http_host: str = "127.0.0.1"
    http_port: int = 8080
    cors_origins: list[str] | None = None

    @property
    def product_instance(self) -> Optional[Any]:
        """Returns the default MAPDL instance for backward compatibility.

        Returns
        -------
        Optional[Any]
            The default MAPDL instance from the pool, or None if no pool exists.
        """
        return self.mapdl

    @product_instance.setter
    def product_instance(self, value: Any) -> None:
        """Setter for product_instance (no-op, use pool directly)."""
        pass


class PyMAPDLMCP(PyAnsysBaseMCP):
    """FastMCP server for managing MAPDL instances."""

    def __init__(self, name: str = "PyMAPDL MCP Server", *args, **kwargs):
        super().__init__(name=name, *args, **kwargs)

    def create_context(self) -> PyMAPDLAppContext:
        """
        Create a new application context.

        Returns
        -------
        PyMAPDLAppContext
            The application context for managing MAPDL instances.
        """
        startup_code = "from ansys.mapdl.mcp.python_helper.startup_code import *"
        python_session = PersistentPythonSession(
            python_executable=self.python_executable,
            working_directory=self.working_directory,
            startup_code=startup_code,
        )

        context = PyMAPDLAppContext(
            python_session=python_session,
            command_history=[],
        )

        # Populate context from CLI config if available
        cli_cfg = getattr(self, "_cli_config", None)

        if cli_cfg is not None:
            context.transport_type = cli_cfg.get("transport_type", context.transport_type)
            context.mapdl_ip = cli_cfg.get("mapdl_ip", context.mapdl_ip)
            context.mapdl_port = cli_cfg.get("mapdl_port", context.mapdl_port)
            context.connect_on_startup = cli_cfg.get(
                "connect_on_startup", context.connect_on_startup
            )
            context.http_host = cli_cfg.get("http_host", context.http_host)
            context.http_port = cli_cfg.get("http_port", context.http_port)
            context.cors_origins = cli_cfg.get("cors_origins", context.cors_origins)

        self.context = context
        return context

    def product_startup(self):
        """Allow PyMAPDL-MCP specific startup actions."""
        logger.info("PyMAPDL MCP server starting up...")

        context = cast(PyMAPDLAppContext, self.context)

        if context.connect_on_startup:
            from ansys.mapdl.core import Mapdl

            try:
                logger.info(
                    f"Attempting to connect to MAPDL at {context.mapdl_ip}:{context.mapdl_port}..."
                )
                _connect_kwargs: dict[str, Any] = {
                    "start_instance": False,
                    "ip": context.mapdl_ip,
                    "port": context.mapdl_port,
                    "cleanup_on_exit": False,
                }
                context.mapdl = Mapdl(**_connect_kwargs)
                logger.info("Successfully connected to MAPDL on startup.")

            except Exception as e:
                logger.error(f"Failed to connect to MAPDL on startup: {e}")
        else:
            logger.info("MCP Server initialized. Use connect_to_mapdl to establish a connection.")

    def product_cleanup(self):
        """Perform cleanup actions for MAPDL instances on shutdown."""
        context = cast(PyMAPDLAppContext, self.context)
        # Cleanup on shutdown
        if context.mapdl is not None:
            try:
                logger.info("Disconnecting from MAPDL...")
                context.mapdl.exit()
                logger.info("MAPDL disconnect complete")
            except Exception as e:
                logger.error(f"Error during MAPDL disconnect: {e}")


# Pass lifespan to server
app = PyMAPDLMCP(name="PyMAPDL MCP Server")


@dataclass
class SessionContext:
    """Session context for storing CLI options."""

    connect_on_startup: bool = False
    on_aali: bool = False

    @property
    def locked_connection(self) -> bool:
        """Whether to lock the connection on startup."""
        return self.connect_on_startup


session = SessionContext()


def _validate_port(port: int) -> int:
    if port < 1 or port > 65535:
        raise argparse.ArgumentTypeError("Port must be in range 1-65535")
    return port


def launcher(argv: list[str] | None = None) -> None:
    """Entry point for the MCP server.

    Parameters
    ----------
    argv : list[str] | None
        Optional list of arguments for testing. Defaults to `sys.argv[1:]`.
    """
    if argv is None:
        argv = sys.argv[1:]

    parser = argparse.ArgumentParser(prog="ansys.mapdl.mcp")
    parser.add_argument(
        "--transport",
        dest="transport_type",
        choices=["stdio", "http"],
        default="stdio",
        help="Transport type. Allowed: stdio, http",
    )
    parser.add_argument("--ip", dest="mapdl_ip", default="127.0.0.1", help="MAPDL IP or hostname")
    parser.add_argument(
        "--port",
        dest="mapdl_port",
        type=lambda v: _validate_port(int(v)),
        default=50052,
        help="MAPDL gRPC port (1-65535)",
    )
    parser.add_argument(
        "--connect-on-startup",
        dest="connect_on_startup",
        action="store_true",
        help="Attempt to connect to MAPDL during MCP startup",
    )
    parser.add_argument(
        "--http-host",
        dest="http_host",
        default="127.0.0.1",
        help="HTTP server host address (for http transport, default: 127.0.0.1)",
    )
    parser.add_argument(
        "--http-port",
        dest="http_port",
        type=lambda v: _validate_port(int(v)),
        default=8080,
        help="HTTP server port (for http transport, default: 8080, range: 1-65535)",
    )
    parser.add_argument(
        "--cors-origins",
        dest="cors_origins",
        default=None,
        help="Allowed CORS origins (comma-separated URLs, for http transport)",
    )
    parser.add_argument(
        "--on-aali",
        dest="on_aali",
        action="store_true",
        help="To specify whether the MCP server is running on an AALI environment.",
    )

    args = parser.parse_args(argv)

    # Parse CORS origins if provided
    cors_origins = None
    if args.cors_origins:
        cors_origins = [origin.strip() for origin in args.cors_origins.split(",")]

    # Attach CLI config to server so lifespan can read it
    session.connect_on_startup = bool(args.connect_on_startup)
    session.on_aali = bool(args.on_aali)

    if session.connect_on_startup:
        logger.info(
            f"MCP will attempt to connect to an MAPDL in {args.mapdl_ip}:{args.mapdl_port} on startup. "  # noqa: E501
            "The tools 'launch_mapdl_session', 'connect_to_mapdl' and 'disconnect_from_mapdl' will be disabled."  # noqa: E501
        )

    setattr(
        app,
        "_cli_config",
        {
            "transport_type": args.transport_type,
            "mapdl_ip": args.mapdl_ip,
            "mapdl_port": args.mapdl_port,
            "connect_on_startup": session.connect_on_startup,
            "http_host": args.http_host,
            "http_port": args.http_port,
            "cors_origins": cors_origins,
            "on_aali": session.on_aali,
        },
    )

    # Run server using selected transport
    import asyncio

    # import tools, contexts, and prompts to register them
    if not session.on_aali:
        from ansys.mapdl.mcp import contexts  # noqa: F401
    from ansys.mapdl.mcp import (
        prompts,  # noqa: F401
        tools,  # noqa: F401
    )

    # Guarantee the system prompt is delivered during the MCP initialize handshake
    app.instructions = prompts.PYMAPDL_SYSTEM_PROMPT

    # Disable tools that require an active MAPDL connection until one is established.
    # When connect_on_startup is True, MAPDL will be connected during server startup,
    # so these tools are available immediately and should not be disabled here.
    if not session.connect_on_startup:
        from ansys.mapdl.mcp.tools import REQUIRES_MAPDL_TAG

        app.disable(tags={REQUIRES_MAPDL_TAG})

    # Disable the connect and disconnect tools when on AALI or when connection is locked,
    # since they won't work in those environments and can cause confusion.
    # The tools will still be visible but will return a message indicating they are not available
    # in the current environment.

    if session.on_aali:
        app.disable(tags={"aali"})
    if session.locked_connection:
        app.disable(tags={"locked_connection"})

    if args.transport_type == "stdio":
        asyncio.run(app.run_stdio_async())
    elif args.transport_type == "http":
        asyncio.run(
            app.run_http_async(
                transport="http",  # Use streamable HTTP (default)
                host=args.http_host,
                port=args.http_port,
            )
        )
