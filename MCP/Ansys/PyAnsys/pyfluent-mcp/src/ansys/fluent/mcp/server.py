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

"""Lifespan and CLI entry for the MCP server with startup options."""

from __future__ import annotations

import argparse
import logging
from typing import Any, Optional

from ansys.fluent.mcp.common.config import ConfigError, validate_config
from ansys.fluent.mcp.solve import SolveMCP


def _argparser() -> argparse.ArgumentParser:
    """Build the command-line argument parser.

    Returns
    -------
    argparse.ArgumentParser
        argparse.ArgumentParser produced by the operation.
    """
    p = argparse.ArgumentParser(prog="ansys-fluent-mcp")
    p.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=0)
    p.add_argument(
        "--backend",
        default=None,
        metavar="KIND",
        help=(
            "Default backend kind until `connect` is called. Ships "
            "`pyfluent`; plugins may register others via the "
            "`ansys.fluent.mcp.solve_backends` entry point. Unknown "
            "kinds fall back to the only configured backend."
        ),
    )
    p.add_argument("--log-level", default="INFO")
    return p


def _build_server(args: argparse.Namespace) -> Any:
    """Build server.

    Parameters
    ----------
    args : argparse.Namespace
        Positional arguments forwarded to the callable.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    kwargs: dict[str, Any] = {
        "name": "ansys-fluent-mcp",
    }
    if args.backend is not None:
        kwargs["default_backend_kind"] = args.backend
    return SolveMCP(**kwargs)


def _run(server: Any, args: argparse.Namespace) -> None:
    """Run the command-line entry point.

    Parameters
    ----------
    server : Any
        Server instance to run from the command-line entry point.
    args : argparse.Namespace
        Positional arguments forwarded to the callable.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    try:
        cfg = validate_config()
    except ConfigError as exc:
        raise SystemExit(f"ansys-fluent-mcp: configuration error: {exc}") from exc
    log_level = args.log_level or cfg.log_level
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger = logging.getLogger("ansys.fluent.mcp.server")
    for w in cfg.warnings:
        logger.warning(w)
    if args.transport == "stdio":
        server.run(transport="stdio")
    else:
        server.run(transport="http", host=args.host, port=args.port or 8000)


def launcher(argv: Optional[list[str]] = None) -> None:
    """Launch the Fluent Solve MCP server (console entry point).

    Parameters
    ----------
    argv : Optional[list[str]]
        Argv to supply to the function.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    args = _argparser().parse_args(argv)
    server = _build_server(args)
    _run(server, args)


# Back-compat alias used by early integrations and tests.
run_solve = launcher
