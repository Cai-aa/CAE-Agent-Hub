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

"""Lifespan and CLI entry for PyAEDT-MCP with startup options."""

import argparse
from dataclasses import dataclass
import importlib
import sys
from typing import Any, Optional

from ansys.common.mcp import PyAnsysBaseMCP, get_logger
from ansys.common.mcp.context import PyAnsysBaseAppContext
from ansys.common.mcp.helpers import PersistentPythonSession

logger = get_logger(__name__)


@dataclass
class PyAEDTAppContext(PyAnsysBaseAppContext):
    """Application context with typed dependencies and CLI options.

    Attributes
    ----------
    desktop : Optional[Any]
        AEDT instance connection. Using ``Any`` avoids type issues.
    transport_type : str
        Transport type for MCP server. Options are ``"stdio"`` or ``"http"``.
    aedt_machine : Optional[str]
        Machine name or IP address for the AEDT connection.
    aedt_port : Optional[int]
        Port number for the AEDT gRPC connection.
    aedt_version : Optional[str]
        Version of AEDT to use.
    non_graphical : bool
        Whether to run AEDT in non-graphical mode.
    connect_on_startup : bool
        Whether to attempt AEDT connection on MCP startup.
    include_context_tools : bool
        Whether to register optional context helper tools.
    dynamic_tool_discovery : bool
        Whether tool visibility should be dynamically gated by AEDT connection state.
    http_host : str
        Host address for HTTP transport.
    http_port : int
        Port number for HTTP transport.
    cors_origins : Optional[list[str]]
        List of allowed CORS origins for HTTP transport.
    """

    desktop: Any | None = None  # Using 'Any' to avoid type issues with AEDT variants
    transport_type: str = "stdio"
    aedt_machine: str | None = None
    aedt_port: int | None = None
    aedt_version: str | None = None
    non_graphical: bool = True
    connect_on_startup: bool = False
    include_context_tools: bool = False
    dynamic_tool_discovery: bool = False
    http_host: str = "127.0.0.1"
    http_port: int = 8080
    cors_origins: list[str] | None = None

    @property
    def product_instance(self) -> Optional[Any]:
        """Default AEDT instance for backward compatibility.

        Returns
        -------
        Optional[Any]
            Default AEDT instance or ``None`` if not connected.
        """
        return self.desktop

    @product_instance.setter
    def product_instance(self, value: Any) -> None:
        """Setter for product_instance."""
        self.desktop = value


class PyAEDTMCP(PyAnsysBaseMCP):
    """FastMCP server for managing AEDT instances."""

    def __init__(self, name: str = "PyAEDT-MCP", *args, **kwargs):
        super().__init__(name=name, *args, **kwargs)

    def create_context(self) -> PyAEDTAppContext:
        """
        Create a new application context.

        Returns
        -------
        PyAEDTAppContext
            Application context for managing AEDT instances.
        """
        startup_code = "from ansys.aedt.mcp.aedt_helper.startup_code import *"
        python_session = PersistentPythonSession(
            python_executable=self.python_executable,
            working_directory=self.working_directory,
            startup_code=startup_code,
        )

        context = PyAEDTAppContext(
            python_session=python_session,
            command_history=[],
        )

        # Populate context from CLI config if available
        cli_cfg = getattr(self, "_cli_config", None)

        if cli_cfg is not None:
            context.transport_type = cli_cfg.get("transport_type", context.transport_type)
            context.aedt_machine = cli_cfg.get("aedt_machine", context.aedt_machine)
            context.aedt_port = cli_cfg.get("aedt_port", context.aedt_port)
            context.aedt_version = cli_cfg.get("aedt_version", context.aedt_version)
            context.non_graphical = cli_cfg.get("non_graphical", context.non_graphical)
            context.connect_on_startup = cli_cfg.get(
                "connect_on_startup", context.connect_on_startup
            )
            context.include_context_tools = cli_cfg.get(
                "include_context_tools", context.include_context_tools
            )
            context.dynamic_tool_discovery = cli_cfg.get(
                "dynamic_tool_discovery", context.dynamic_tool_discovery
            )
            context.http_host = cli_cfg.get("http_host", context.http_host)
            context.http_port = cli_cfg.get("http_port", context.http_port)
            context.cors_origins = cli_cfg.get("cors_origins", context.cors_origins)

        self.context = context
        return context

    def product_startup(self):
        """Allow PyAEDT-MCP specific startup actions."""
        logger.info("PyAEDT-MCP starting up...")

        context = self.context

        if context.connect_on_startup:
            try:
                from ansys.aedt.core import Desktop
                from ansys.aedt.core.generic.settings import settings

                # Enable gRPC API
                settings.use_grpc_api = True

                logger.info(
                    "Attempting to connect to AEDT at "
                    f"{context.aedt_machine}:{context.aedt_port}..."
                )

                # Connect to running AEDT instance
                context.desktop = Desktop(
                    version=context.aedt_version,
                    non_graphical=context.non_graphical,
                    new_desktop=False,
                    machine=context.aedt_machine,
                    port=context.aedt_port,
                )
                logger.info("Successfully connected to AEDT on startup.")

            except Exception as e:
                logger.error(f"Failed to connect to AEDT on startup: {e}")
        else:
            logger.info("MCP Server initialized. Use connect_to_aedt to establish a connection.")

    def product_cleanup(self):
        """Perform cleanup actions for AEDT instances on shutdown."""
        context = self.context
        # Cleanup on shutdown
        if context.desktop is not None:
            try:
                logger.info("Disconnecting from AEDT...")
                context.desktop.release_desktop(close_projects=False)
                logger.info("AEDT disconnect complete")
            except Exception as e:
                logger.error(f"Error during AEDT disconnect: {e}")


# Pass lifespan to server
app = PyAEDTMCP(name="PyAEDT-MCP")


@dataclass
class SessionContext:
    """Session context for storing CLI options."""

    connect_on_startup: bool = False

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
        Optional list of arguments for testing. If ``None``, ``"sys.argv[1:]"`` is used.
    """
    if argv is None:
        argv = sys.argv[1:]

    parser = argparse.ArgumentParser(prog="ansys.aedt.mcp")
    parser.add_argument(
        "--transport",
        dest="transport_type",
        choices=["stdio", "http"],
        default="stdio",
        help="Transport type. Allowed: stdio, http",
    )
    parser.add_argument(
        "--machine",
        dest="aedt_machine",
        default="localhost",
        help="AEDT machine hostname or IP (default: localhost)",
    )
    parser.add_argument(
        "--port",
        dest="aedt_port",
        type=lambda v: _validate_port(int(v)),
        default=50051,
        help="AEDT gRPC port (default: 50051)",
    )
    parser.add_argument(
        "--version",
        dest="aedt_version",
        default=None,
        help="AEDT version to use (e.g., '2026.1' or '261')",
    )
    parser.add_argument(
        "--non-graphical",
        dest="non_graphical",
        action="store_true",
        default=True,
        help="Run AEDT in non-graphical mode (default: True)",
    )
    parser.add_argument(
        "--graphical",
        dest="non_graphical",
        action="store_false",
        help="Run AEDT in graphical mode",
    )
    parser.add_argument(
        "--connect",
        dest="connect_on_startup",
        action="store_true",
        help="Attempt to connect to AEDT on startup",
    )
    parser.add_argument(
        "--include-context",
        dest="include_context_tools",
        action="store_true",
        help="Register optional AEDT context helper tools",
    )
    parser.add_argument(
        "--dynamic-tool-discovery",
        dest="dynamic_tool_discovery",
        action="store_true",
        help="Dynamically hide AEDT-only tools until a connection is established",
    )
    parser.add_argument(
        "--http-host",
        dest="http_host",
        default="127.0.0.1",
        help="HTTP transport host (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--http-port",
        dest="http_port",
        type=lambda v: _validate_port(int(v)),
        default=8080,
        help="HTTP transport port (default: 8080)",
    )
    parser.add_argument(
        "--cors-origins",
        dest="cors_origins",
        nargs="+",
        default=None,
        help="Allowed CORS origins for HTTP transport",
    )
    args = parser.parse_args(argv)

    # Parse CORS origins if provided
    cors_origins = None
    if args.cors_origins:
        cors_origins = args.cors_origins

    # Attach CLI config to server so lifespan can read it
    session.connect_on_startup = bool(args.connect_on_startup)

    if session.connect_on_startup:
        logger.info(
            f"MCP will attempt to connect to AEDT at "
            f"{args.aedt_machine}:{args.aedt_port} on startup. "
            "The tools 'launch_aedt', 'connect_to_aedt' and "
            "'disconnect_from_aedt' will be disabled."
        )

    setattr(
        app,
        "_cli_config",
        {
            "transport_type": args.transport_type,
            "aedt_machine": args.aedt_machine,
            "aedt_port": args.aedt_port,
            "aedt_version": args.aedt_version,
            "non_graphical": args.non_graphical,
            "connect_on_startup": session.connect_on_startup,
            "include_context_tools": bool(args.include_context_tools),
            "dynamic_tool_discovery": bool(args.dynamic_tool_discovery),
            "http_host": args.http_host,
            "http_port": args.http_port,
            "cors_origins": cors_origins,
        },
    )

    # Run server using selected transport
    import asyncio

    # Import required modules so their registrations are applied to the app.
    prompts = importlib.import_module("ansys.aedt.mcp.prompts")
    importlib.import_module("ansys.aedt.mcp.tools")
    importlib.import_module("ansys.aedt.mcp.contexts")
    importlib.import_module("ansys.aedt.mcp.toolsets")

    if args.include_context_tools:
        app.enable(tags={"pyaedt_context"})
    else:
        app.disable(tags={"pyaedt_context"})

    # Guarantee the system prompt is delivered during the MCP initialize handshake
    app.instructions = prompts.build_system_prompt(bool(args.dynamic_tool_discovery))

    # Optionally disable tools that require an active AEDT connection until one is
    # established. Static exposure remains the default surface for compatibility.
    if args.dynamic_tool_discovery and not session.connect_on_startup:
        from ansys.aedt.mcp.tools import REQUIRES_AEDT_TAG

        app.disable(tags={REQUIRES_AEDT_TAG})

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
