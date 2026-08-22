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

"""Console entry point for standalone PyCFX-MCP."""

from __future__ import annotations

import argparse
import logging
from typing import Any, Optional

from ansys.cfx.mcp.cfx import CFXMCP


def _argparser() -> argparse.ArgumentParser:
    """Create the command-line parser for the PyCFX-MCP.

    Returns
    -------
    argparse.ArgumentParser
        Value computed by the helper for the requested PyCFX-MCP workflow.
    """
    parser = argparse.ArgumentParser(prog="ansys-cfx-mcp")
    parser.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument(
        "--backend",
        default=None,
        metavar="KIND",
        help="Default backend kind until connect is called. This package ships PyCFX.",
    )
    parser.add_argument("--log-level", default="INFO")
    return parser


def _build_server(args: argparse.Namespace) -> Any:
    """Create and configure the PyCFX-MCP instance from parsed CLI options.

    Parameters
    ----------
    args : argparse.Namespace
        Positional arguments forwarded to the wrapped callable.

    Returns
    -------
    Any
        Value computed by the helper for the requested PyCFX-MCP workflow.
    """
    default_backend_kind = args.backend or CFXMCP.default_backend_kind
    if default_backend_kind not in {"pycfx"}:
        raise SystemExit(f"ansys-cfx-mcp: unknown backend kind: {default_backend_kind}")
    kwargs: dict[str, Any] = {
        "name": "ansys-cfx-mcp",
    }
    return CFXMCP(**kwargs)


def _run(server: Any, args: argparse.Namespace) -> None:
    """Run PyCFX-MCP with the requested transport settings.

    Parameters
    ----------
    server : Any
        MCP server instance to run.
    args : argparse.Namespace
        Positional arguments forwarded to the wrapped callable.

    Returns
    -------
    None
        No value is returned. Side effects are applied to the relevant cache, session, or
        server.
    """
    logging.basicConfig(
        level=args.log_level or "INFO",
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if args.transport == "stdio":
        server.run(transport="stdio")
    else:
        server.run(transport="http", host=args.host, port=args.port or 8000)


def run_cfx(argv: Optional[list[str]] = None) -> None:
    """Run the PyCFX-MCP command-line entry point.

    Parameters
    ----------
    argv : Optional[list[str]], default: None
        Command-line arguments passed to the CLI entry point.

    Returns
    -------
    None
        No value is returned. Side effects are applied to the relevant cache, session, or
        server.
    """
    args = _argparser().parse_args(argv)
    server = _build_server(args)
    _run(server, args)


if __name__ == "__main__":  # pragma: no cover
    run_cfx()
