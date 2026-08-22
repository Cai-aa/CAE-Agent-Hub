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

"""Lifespan and CLI entry for PyMechanical-MCP server with startup options."""

import argparse
from dataclasses import dataclass
import os
import sys
from typing import Any, Optional

from ansys.common.mcp import (
    PyAnsysBaseMCP,
    get_logger,
)
from ansys.common.mcp.context import PyAnsysBaseAppContext
from ansys.common.mcp.helpers import PersistentPythonSession

logger = get_logger(__name__)


@dataclass
class PyMechanicalAppContext(PyAnsysBaseAppContext):
    """Application context with typed dependencies and CLI options.

    Attributes
    ----------
    mechanical : Optional[Any]
        Mechanical instance connection.
    transport_type : str
        Transport type for PyMechanical-MCP. Options are ``'stdio'`` and ``'http'``.
    mechanical_ip : Optional[str]
        IP address or hostname for Mechanical connection.
    mechanical_port : Optional[int]
        Port number for Mechanical connection.
    connect_on_startup : bool
        Whether to attempt Mechanical connection on PyMechanical-MCP startup.
    static_tools : bool
        Whether to expose all tools from startup instead of dynamically hiding
        tools that require an active Mechanical connection. When ``False``
        (default), tools tagged ``requires_mechanical`` stay hidden until
        ``launch_mechanical`` or ``connect_to_mechanical`` succeeds.
    http_host : str
        Host address for HTTP transport.
    http_port : int
        Port number for HTTP transport.
    cors_origins : Optional[list[str]]
        List of allowed CORS origins for HTTP transport.
    grpc_transport_mode : Optional[str]
        gRPC transport mode for Mechanical connections. Options are ``'auto'``, ``'insecure'``,
        ``'mtls'``, and ``'wnua'``. When set to ``'auto'`` (default), the mode is
        determined automatically based on the platform and certificate
        availability.
    certs_dir : Optional[str]
        Path to directory containing mTLS certificate files (``ca.crt``,
        ``client.crt``, and ``client.key``). Used when ``grpc_transport_mode`` is ``'mtls'``.
    """

    mechanical: Any | None = None
    transport_type: str = "stdio"
    mechanical_ip: str | None = None
    mechanical_port: int | None = None
    connect_on_startup: bool = False
    static_tools: bool = False
    http_host: str = "127.0.0.1"
    http_port: int = 8080
    cors_origins: list[str] | None = None
    grpc_transport_mode: str | None = None
    certs_dir: str | None = None

    @property
    def product_instance(self) -> Optional[Any]:
        """Returns the Mechanical instance for backward compatibility.

        Returns
        -------
        Optional[Any]
            Mechanical instance or ``None`` if not connected.
        """
        return self.mechanical

    @product_instance.setter
    def product_instance(self, value: Any) -> None:
        """Setter for product_instance (no-op, use mechanical directly)."""
        pass


class PyMechanicalMCP(PyAnsysBaseMCP):
    """FastMCP server for managing Mechanical instances."""

    def __init__(self, name: str = "PyMechanical MCP Server", *args, **kwargs):
        super().__init__(name=name, *args, **kwargs)

    def create_context(self) -> PyMechanicalAppContext:
        """
        Create a new application context.

        Returns
        -------
        PyMechanicalAppContext
            Application context for managing Mechanical instances.
        """
        startup_code = "from ansys.mechanical.mcp.mechanical_helper.startup_code import *"
        python_session = PersistentPythonSession(
            python_executable=self.python_executable,
            working_directory=self.working_directory,
            startup_code=startup_code,
        )

        context = PyMechanicalAppContext(
            python_session=python_session,
            command_history=[],
        )

        # Populate context from CLI config if available
        cli_cfg = getattr(self, "_cli_config", None)

        if cli_cfg is not None:
            context.transport_type = cli_cfg.get("transport_type", context.transport_type)
            context.mechanical_ip = cli_cfg.get("mechanical_ip", context.mechanical_ip)
            context.mechanical_port = cli_cfg.get("mechanical_port", context.mechanical_port)
            context.connect_on_startup = cli_cfg.get(
                "connect_on_startup", context.connect_on_startup
            )
            context.static_tools = cli_cfg.get("static_tools", context.static_tools)
            context.http_host = cli_cfg.get("http_host", context.http_host)
            context.http_port = cli_cfg.get("http_port", context.http_port)
            context.cors_origins = cli_cfg.get("cors_origins", context.cors_origins)
            context.grpc_transport_mode = cli_cfg.get(
                "grpc_transport_mode", context.grpc_transport_mode
            )
            context.certs_dir = cli_cfg.get("certs_dir", context.certs_dir)

        self.context = context
        return context

    def product_startup(self):
        """Allow PyMechanical-MCP specific startup actions."""
        logger.info("PyMechanical-MCP starting up...")

        context = self.context

        if context.connect_on_startup:
            from ansys.mechanical.core import connect_to_mechanical

            from ansys.mechanical.mcp.helpers import resolve_transport_mode

            try:
                # Resolve transport mode (auto-detect if not explicitly set)
                resolved_mode, resolved_certs = resolve_transport_mode(
                    transport_mode=context.grpc_transport_mode,
                    certs_dir=context.certs_dir,
                )

                logger.info(
                    f"Attempting to connect to Mechanical at "
                    f"{context.mechanical_ip}:{context.mechanical_port} "
                    f"(transport_mode={resolved_mode!r})..."
                )

                connect_kwargs: dict[str, Any] = {
                    "ip": context.mechanical_ip,
                    "port": context.mechanical_port,
                    "cleanup_on_exit": False,
                }
                if resolved_mode is not None:
                    connect_kwargs["transport_mode"] = resolved_mode
                if resolved_certs is not None:
                    connect_kwargs["certs_dir"] = resolved_certs

                context.mechanical = connect_to_mechanical(**connect_kwargs)
                logger.info("Successfully connected to Mechanical on startup.")

            except Exception as e:
                logger.error(f"Failed to connect to Mechanical on startup: {e}")
        else:
            logger.info(
                "MCP Server initialized. Use connect_to_mechanical to establish a connection."
            )

    def product_cleanup(self):
        """Perform cleanup actions for Mechanical instances on shutdown."""
        context = self.context
        # Cleanup on shutdown
        if context.mechanical is not None:
            try:
                logger.info("Disconnecting from Mechanical...")
                context.mechanical.exit()
                logger.info("Mechanical disconnect complete")
            except Exception as e:
                logger.error(f"Error during Mechanical disconnect: {e}")


# Pass lifespan to server
app = PyMechanicalMCP(name="PyMechanical-MCP")


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
        raise argparse.ArgumentTypeError("Port must be in range 1 to 65535.")
    return port


def launcher(argv: list[str] | None = None) -> None:
    """Launch PyMechanical-MCP.

    Parameters
    ----------
    argv : list[str] | None
        Optional list of arguments for testing. If ``None``, ``sys.argv[1:]`` is used.
    """
    if argv is None:
        argv = sys.argv[1:]

    parser = argparse.ArgumentParser(prog="ansys.mechanical.mcp")
    parser.add_argument(
        "--transport",
        dest="transport_type",
        choices=["stdio", "http"],
        default="stdio",
        help="Transport type. Allowed: stdio, http",
    )
    parser.add_argument(
        "--ip",
        dest="mechanical_ip",
        default="127.0.0.1",
        help="Mechanical server IP or hostname",
    )
    parser.add_argument(
        "--port",
        dest="mechanical_port",
        type=lambda v: _validate_port(int(v)),
        default=10000,
        help="Mechanical gRPC port (1-65535, default: 10000)",
    )
    parser.add_argument(
        "--connect-on-startup",
        dest="connect_on_startup",
        action="store_true",
        help="Attempt to connect to Mechanical during MCP startup",
    )
    parser.add_argument(
        "--static-tools",
        dest="static_tools",
        action="store_true",
        help=(
            "Expose all tools from startup instead of dynamically hiding "
            "tools that require an active Mechanical connection until "
            "launch_mechanical or connect_to_mechanical succeeds."
        ),
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
        help="To specify whether PyMechanical-MCP server is running in an AALI environment.",
    )
    parser.add_argument(
        "--transport-mode",
        dest="grpc_transport_mode",
        choices=["auto", "insecure", "mtls", "wnua"],
        default=None,
        help=(
            "gRPC transport mode for Mechanical connections. "
            "'auto' (default) detects the best mode based on platform and "
            "certificate availability. 'insecure' uses plaintext gRPC. "
            "'mtls' uses mutual TLS (requires certificates). "
            "'wnua' uses Windows Named User Authentication (Windows only). "
            "Can also be set via the PYMECHANICAL_TRANSPORT_MODE env var."
        ),
    )
    parser.add_argument(
        "--certs-dir",
        dest="certs_dir",
        default=None,
        help=(
            "Path to directory containing mTLS certificate files "
            "(ca.crt, client.crt, and client.key). "
            "Can also be set via the ANSYS_GRPC_CERTIFICATES env var."
        ),
    )

    args = parser.parse_args(argv)

    # Resolve gRPC transport mode: CLI flag > env var > auto
    grpc_transport_mode = args.grpc_transport_mode
    if grpc_transport_mode is None:
        grpc_transport_mode = os.environ.get("PYMECHANICAL_TRANSPORT_MODE", None)

    # Resolve certs dir: CLI flag > env var (ANSYS_GRPC_CERTIFICATES handled
    # inside resolve_transport_mode, but we also accept it here for
    # explicit pass-through)
    certs_dir = args.certs_dir
    if certs_dir is None:
        certs_dir = os.environ.get("ANSYS_GRPC_CERTIFICATES", None)

    # Parse CORS origins if provided
    cors_origins = None
    if args.cors_origins:
        cors_origins = [origin.strip() for origin in args.cors_origins.split(",")]

    # Attach CLI config to server so lifespan can read it
    session.connect_on_startup = bool(args.connect_on_startup)
    session.on_aali = bool(args.on_aali)

    if session.connect_on_startup:
        logger.info(
            f"MCP will attempt to connect to Mechanical at "
            f"{args.mechanical_ip}:{args.mechanical_port} on startup. "
            "The tools 'launch_mechanical', 'connect_to_mechanical' and "
            "'disconnect_from_mechanical' will be disabled."
        )

    if args.static_tools:
        logger.info(
            "Static tool exposure enabled (--static-tools): all tools will be "
            "visible from startup instead of being hidden until a Mechanical "
            "connection is established."
        )

    setattr(
        app,
        "_cli_config",
        {
            "transport_type": args.transport_type,
            "mechanical_ip": args.mechanical_ip,
            "mechanical_port": args.mechanical_port,
            "connect_on_startup": session.connect_on_startup,
            "static_tools": bool(args.static_tools),
            "http_host": args.http_host,
            "http_port": args.http_port,
            "cors_origins": cors_origins,
            "on_aali": session.on_aali,
            "grpc_transport_mode": grpc_transport_mode,
            "certs_dir": certs_dir,
        },
    )

    # Run server using selected transport
    import asyncio

    # import tools, contexts, and prompts to register them
    if not session.on_aali:
        from ansys.mechanical.mcp import contexts  # noqa: F401
    from ansys.mechanical.mcp import (
        prompts,  # noqa: F401
        tools,  # noqa: F401
        toolsets,  # noqa: F401
    )

    # Guarantee the system prompt is delivered during the MCP initialize handshake
    app.instructions = prompts.build_system_prompt(bool(args.static_tools))

    # Disable tools that require an active Mechanical connection until one is established.
    # When connect_on_startup is True, Mechanical is connected during PyMechanical-MCP startup,
    # so these tools are available immediately and should not be disabled here. Likewise,
    # when static_tools is True, the full tool surface stays visible from startup by request.
    if not session.connect_on_startup and not args.static_tools:
        from ansys.mechanical.mcp.tools import REQUIRES_MECHANICAL_TAG

        app.disable(tags={REQUIRES_MECHANICAL_TAG})

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
