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

"""Typed error helpers and typed-guard helpers.

Convert unexpected exceptions into a `TypedError` instead of crashing the
MCP transport.
"""

from __future__ import annotations

import functools
import logging
import traceback
from typing import Any, Awaitable, Callable, TypeVar

from ansys.cfx.mcp.common.models import TypedError

logger = logging.getLogger("ansys.cfx.mcp.errors")

T = TypeVar("T")


class FluidsMCPError(Exception):
    """Base class for typed errors raised by leaves and backends."""

    error_code = "internal_error"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        """Initialize this object with the dependencies required for later operations.

        Parameters
        ----------
        message : str
            Human-readable error message returned to the MCP caller.
        details : dict[str, Any] | None, optional
            Optional structured error details returned to the caller. Default is ``None``.

        Returns
        -------
        None
            No value is returned; side effects are applied to the relevant cache, session, or
            server.
        """
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_typed(self) -> TypedError:
        """Convert this domain error into the shared typed-error response model.

        Returns
        -------
        TypedError
            Value computed by the helper for the requested CFX workflow.
        """
        return TypedError(error_code=self.error_code, message=self.message, details=self.details)


class BackendUnavailableError(FluidsMCPError):
    """Error raised when the requested backend cannot be used."""

    error_code = "backend_unavailable"


class NotConnectedError(FluidsMCPError):
    """Error raised when an operation requires an active connection."""

    error_code = "not_connected"


class InvalidArgumentsError(FluidsMCPError):
    """Error raised when a tool receives invalid arguments."""

    error_code = "invalid_arguments"


class UpstreamError(FluidsMCPError):
    """Error raised when an upstream CFX or provider call fails."""

    error_code = "upstream_error"


class DiscoveryError(FluidsMCPError):
    """Error raised when API or model discovery fails."""

    error_code = "discovery_error"


def typed_guard(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T | TypedError]]:
    """Wrap an MCP tool so domain errors are returned as typed payloads.

    Parameters
    ----------
    func : Callable[..., Awaitable[T]]
        Callable being wrapped or invoked.

    Returns
    -------
    Callable[..., Awaitable[T | TypedError]]
        Value computed by the helper for the requested CFX workflow.
    """

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any):
        """Execute the guarded MCP tool and convert known errors to typed responses.

        Parameters
        ----------
        args : Any
            Positional arguments forwarded to the wrapped callable.
        kwargs : Any
            Keyword arguments forwarded to the wrapped callable.

        Returns
        -------
        Any
            Value computed by the helper for the requested CFX workflow.
        """
        try:
            return await func(*args, **kwargs)
        except FluidsMCPError as exc:
            logger.info("Typed error from %s: %s — %s", func.__name__, exc.error_code, exc.message)
            return exc.to_typed()
        except Exception as exc:
            logger.exception("Unhandled error in %s", func.__name__)
            return TypedError(
                error_code="internal_error",
                message=str(exc),
                details={"trace": traceback.format_exc(limit=5)},
            )

    return wrapper


# ---------------------------------------------------------------------------
# Backward-compatible short aliases.
#
# The ``*Error``-suffixed spellings above are canonical (they match the
# spellings imported by the shared agent engine and the legacy sibling
# package). CFX's own code historically used the
# shorter spelling, so keep it working. These are the SAME class objects —
# ``except BackendUnavailable`` and ``except BackendUnavailableError`` are
# interchangeable.
# ---------------------------------------------------------------------------
BackendUnavailable = BackendUnavailableError
NotConnected = NotConnectedError
InvalidArguments = InvalidArgumentsError
