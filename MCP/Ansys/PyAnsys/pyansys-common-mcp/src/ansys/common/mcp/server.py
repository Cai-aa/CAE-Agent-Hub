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

"""Base MCP server infrastructure for PyAnsys libraries.

This module provides the ``PyAnsysBaseMCP`` class that product-specific MCP
servers can extend to create their own MCP implementations.
"""

from abc import ABC, abstractmethod
import argparse
import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator, List, Optional

from fastmcp import FastMCP

from ansys.common.mcp.context import PyAnsysBaseAppContext
from ansys.common.mcp.helpers import PersistentPythonSession, logger


def _validate_port(value: str) -> int:
    """Validate that *value* is an integer in the valid port range 1-65535.

    Parameters
    ----------
    value : str
        String representation of the port number to validate.

    Returns
    -------
    int
        The validated port number.

    Raises
    ------
    argparse.ArgumentTypeError
        If the value is not a valid integer or is outside the range 1-65535.

    """
    try:
        port = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"Port must be an integer, got: {value!r}")
    if port < 1 or port > 65535:
        raise argparse.ArgumentTypeError(f"Port must be between 1 and 65535, got: {port}")
    return port


class PyAnsysBaseMCP(FastMCP, ABC):
    """Base MCP server for PyAnsys libraries."""

    def __init__(
        self,
        python_executable: Optional[str] = None,
        working_directory: Optional[str] = None,
        need_python: bool = True,
        *args,
        **kwargs,
    ):  # noqa: D403
        """PyAnsys Base MCP server for PyAnsys libraries.

        Parameters
        ----------
        python_executable : str, default: None
            Path to the Python executable to use for running the generated code.
            If ``None``, the current Python interpreter (sys.executable) is used.
        working_directory : str, default: None
            Working directory to use for the Python session.
        need_python : bool, default: True
            Whether to start a persistent Python session during server initialization.
            Set to ``False`` if your MCP server does not need to execute Python code.
        *args : tuple
            Additional positional arguments passed to FastMCP
        **kwargs : dict
            Additional keyword arguments passed to FastMCP

        """
        # Store parameters before calling super().__init__
        self.python_executable = python_executable
        self.working_directory = working_directory
        self._need_python = need_python
        self._cli_config: dict = {}

        super().__init__(*args, lifespan=self.product_lifespan, **kwargs)

    @abstractmethod
    def product_cleanup(self):
        """Cleanup routine before shutting down the server.

        This abstract method must be implemented by subclasses to handle product-specific cleanup.
        """
        pass

    @abstractmethod
    def product_startup(self):
        """Startup routine to initialize resources when the server starts.

        This abstract method must be implemented by subclasses to handle
        product-specific initialization.
        """
        pass

    def create_context(self) -> PyAnsysBaseAppContext:
        """Create product-specific context.

        Override this method in subclasses to return custom context types
        (such as in ``PyMAPDLContext`` with an MAPDL field).

        Returns
        -------
        PyAnsysBaseAppContext
            Context instance for this server. The default implementation
            creates a base context with Python session support.

        Examples
        --------
        Override in a product-specific server:

        >>> class PyMAPDLMCP(PyAnsysBaseMCP):
        ...     def create_context(self) -> PyMAPDLContext:
        ...         return PyMAPDLContext(
        ...             python_session=PersistentPythonSession(self.python_executable),
        ...             command_history=[],
        ...         )

        """
        startup_code = """
import matplotlib
# Use non-interactive backend to prevent blocking on plot displays
matplotlib.use('Agg')

import matplotlib.pyplot as plt
import pyvista as pv
import base64
from io import BytesIO
from PIL import Image

# Enable off-screen rendering globally
pv.OFF_SCREEN = True

# Set a clean default theme
pv.set_plot_theme('document')

def save_plot(plotter, filename='plot.png', return_base64=False):
    '''
    Save a PyVista plot to file and optionally return as base64.

    Parameters
    ----------
    plotter : pv.Plotter
        PyVista plotter to save
    filename : str, default: ``'plot.png'``
        Output filename
    return_base64 : bool, default: False
        Whether to return base64-encoded image data. If ``False``, saves to file
        and returns file path message.

    Returns
    -------
    str
        File path or base64 data URI.
    '''
    if return_base64:
        img_array = plotter.screenshot(return_img=True, transparent_background=False)
        plotter.close()

        img = Image.fromarray(img_array)
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)

        img_base64 = base64.b64encode(buffer.read()).decode('utf-8')
        return f"data:image/png;base64,{img_base64}"
    else:
        plotter.screenshot(filename, transparent_background=False)
        plotter.close()
        return f"Plot saved to {filename}"

def save_matplotlib_plot(filename='plot.png', return_base64=False, dpi=150):
    '''
    Save the current Matplotlib plot to file and optionally return as base64.

    Parameters
    ----------
    filename : str, default: ``'plot.png'``
        Output filename.
    return_base64 : bool, default: False
        Whether to return base64-encoded image data. If ``False``, saves to
        file and returns file path message.
    dpi : int, default: 150
        Resolution in dots per inch.

    Returns
    -------
    str
        File path or base64 data URI.
    '''
    if return_base64:
        buffer = BytesIO()
        plt.savefig(buffer, format='png', dpi=dpi, bbox_inches='tight')
        plt.close()
        buffer.seek(0)

        img_base64 = base64.b64encode(buffer.read()).decode('utf-8')
        return f"data:image/png;base64,{img_base64}"
    else:
        plt.savefig(filename, dpi=dpi, bbox_inches='tight')
        plt.close()
        return f"Plot saved to {filename}"

# Print confirmation
print("Matplotlib configured with non-interactive backend (Agg).")
print("PyVista configured for off-screen rendering.")
"""
        python_session = PersistentPythonSession(
            python_executable=self.python_executable,
            working_directory=self.working_directory,
            startup_code=startup_code,
        )
        return PyAnsysBaseAppContext(
            python_session=python_session,
            command_history=[],
        )

    def start_python_session(self):
        """Start a persistent Python session for executing generated code."""
        logger.info("Server initialized.")
        if self.context.python_executable:
            logger.info(f"Using Python executable: {self.context.python_executable}")

        # Start the persistent session
        start_result = self.context.python_session.start()
        if start_result["success"]:
            logger.info("Persistent Python session started.")
            logger.info(f"Startup output: {start_result.get('stdout', '')}")
        else:
            logger.warning(f"Failed to start Python session: {start_result.get('error')}")

    def cleanup_python_session(self):
        """Clean up the persistent Python session."""
        if self.context.python_session and self.context.python_session.is_running():
            try:
                logger.info("Stopping persistent Python session...")
                self.context.python_session.stop()
                logger.info("Persistent Python session stopped.")
            except Exception as e:
                logger.error(f"Error stopping Python session: {e}")

    @asynccontextmanager
    async def product_lifespan(self, server: FastMCP) -> AsyncIterator[PyAnsysBaseAppContext]:
        """Define default lifespan for PyAnsys MCP servers.

        Product-specific servers can override this method if needed.

        Parameters
        ----------
        server : FastMCP
            MCP server instance.

        Yields
        ------
        AsyncIterator[PyAnsysBaseAppContext]
            Application context for the MCP server.

        Notes
        -----
        This method orchestrates the complete lifecycle:
        1. Creates context (via factory method - extensible by subclasses).
        2. Initializes Python session (managed by base class).
        3. Calls product-specific startup.
        4. Yields context to the application.
        5. Cleans up in reverse order on shutdown.

        """
        # Use factory method to create context (subclasses can override)
        self.server = server
        self.context = self.create_context()

        try:
            if self._need_python:
                self.start_python_session()
            self.product_startup()

            yield self.context

        finally:
            if self._need_python:
                self.cleanup_python_session()
            self.product_cleanup()

    def run_cli(self, argv: Optional[List[str]] = None) -> None:
        """Parse CLI arguments and run the MCP server with the selected transport.

        This method provides a ready-to-use entry point for product-specific MCP
        servers, handling transport selection and HTTP configuration so that
        downstream packages do not need to duplicate this boilerplate.

        The method follows the **template method pattern**: two hooks let subclasses
        extend the CLI without rewriting the transport dispatch logic:

        - :meth:`_add_cli_arguments` — add product-specific arguments to the parser.
        - :meth:`_configure_from_cli` — process parsed product-specific arguments
          (for example, store them in ``_cli_config`` so ``create_context`` can read them).

        Parameters
        ----------
        argv : list[str] or None, default: None
            Argument list to parse. If ``None``, ``sys.argv[1:]`` is used.
            Pass an explicit list in tests to avoid reading the real command line.

        Examples
        --------
        Minimal usage — call from a product's ``__main__.py``:

        >>> app.run_cli()

        Product with extra CLI arguments:

        >>> class PyMAPDLMCP(PyAnsysBaseMCP):
        ...     def _add_cli_arguments(self, parser):
        ...         parser.add_argument("--ip", dest="mapdl_ip", default="127.0.0.1")
        ...         parser.add_argument("--port", dest="mapdl_port", type=int, default=50052)
        ...
        ...     def _configure_from_cli(self, args):
        ...         self._cli_config = {"mapdl_ip": args.mapdl_ip, "mapdl_port": args.mapdl_port}

        """
        parser = argparse.ArgumentParser(
            description="Run the MCP server.",
            formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        )
        parser.add_argument(
            "--transport",
            dest="transport",
            choices=["stdio", "http"],
            default="stdio",
            help="Transport protocol for the MCP server.",
        )
        parser.add_argument(
            "--http-host",
            dest="http_host",
            default="127.0.0.1",
            help="Host address for HTTP transport.",
        )
        parser.add_argument(
            "--http-port",
            dest="http_port",
            type=_validate_port,
            default=8080,
            help="Port number for HTTP transport (1-65535).",
        )
        parser.add_argument(
            "--cors-origins",
            dest="cors_origins",
            default=None,
            help="Comma-separated list of allowed CORS origins for HTTP transport.",
        )

        # Let subclasses inject product-specific arguments
        self._add_cli_arguments(parser)

        args = parser.parse_args(argv)

        # Let subclasses process their own parsed arguments
        self._configure_from_cli(args)

        cors_origins = None
        if args.cors_origins:
            cors_origins = [origin.strip() for origin in args.cors_origins.split(",")]

        if args.transport == "stdio":
            asyncio.run(self.run_async())
        elif args.transport == "http":
            middleware = None
            if cors_origins is not None:
                from starlette.middleware import Middleware
                from starlette.middleware.cors import CORSMiddleware

                middleware = [Middleware(CORSMiddleware, allow_origins=cors_origins)]
            asyncio.run(
                self.run_http_async(
                    transport="http",
                    host=args.http_host,
                    port=args.http_port,
                    middleware=middleware,
                )
            )

    def _add_cli_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Add product-specific CLI arguments to the argument parser.

        Override this method in subclasses to extend the CLI provided by
        :meth:`run_cli` with arguments specific to your product, without
        rewriting transport dispatch logic.

        Parameters
        ----------
        parser : argparse.ArgumentParser
            The argument parser already populated with the standard transport
            arguments (``--transport``, ``--http-host``, ``--http-port``,
            ``--cors-origins``). Add your own arguments directly to it.

        Examples
        --------
        >>> class PyMAPDLMCP(PyAnsysBaseMCP):
        ...     def _add_cli_arguments(self, parser):
        ...         parser.add_argument(
        ...             "--ip",
        ...             dest="mapdl_ip",
        ...             default="127.0.0.1",
        ...             help="MAPDL IP or hostname",
        ...         )
        ...         parser.add_argument(
        ...             "--port",
        ...             dest="mapdl_port",
        ...             type=int,
        ...             default=50052,
        ...             help="MAPDL gRPC port",
        ...         )
        ...         parser.add_argument(
        ...             "--connect-on-startup",
        ...             dest="connect_on_startup",
        ...             action="store_true",
        ...             help="Connect to MAPDL during MCP startup",
        ...         )

        """

    def _configure_from_cli(self, args: argparse.Namespace) -> None:
        """Process parsed CLI arguments before the server starts.

        Override this method in subclasses to react to product-specific
        arguments added via :meth:`_add_cli_arguments`. Typical uses include
        storing values in ``self._cli_config`` so that :meth:`create_context`
        can read them, or disabling tools based on the parsed flags.

        Parameters
        ----------
        args : argparse.Namespace
            The fully parsed namespace, containing both the standard transport
            arguments and any product-specific arguments added by
            :meth:`_add_cli_arguments`.

        Examples
        --------
        >>> class PyMAPDLMCP(PyAnsysBaseMCP):
        ...     def _configure_from_cli(self, args):
        ...         self._cli_config = {
        ...             "mapdl_ip": args.mapdl_ip,
        ...             "mapdl_port": args.mapdl_port,
        ...             "connect_on_startup": args.connect_on_startup,
        ...         }

        """
