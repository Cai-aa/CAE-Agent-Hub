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

"""Helper module to handle errors.

Typed error helpers and a guard decorator that converts unexpected
exceptions into a `TypedError` instead of crashing the MCP transport.
"""

from __future__ import annotations

import functools
import logging
import traceback
from typing import Any, Awaitable, Callable, TypeVar

from ansys.fluent.mcp.common.models import TypedError

logger = logging.getLogger("ansys.fluent.mcp.errors")

T = TypeVar("T")


class FluidsMCPError(Exception):
    """Base class for typed errors raised by leaves and backends."""

    error_code = "internal_error"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        """Initialize the FluidsMCPError instance.

        Parameters
        ----------
        message : str
            Message text to format, log, or return.
        details : dict[str, Any] | None
            Details to supply to the function.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_typed(self) -> TypedError:
        """Convert the error into a typed error payload.

        Returns
        -------
        TypedError
            TypedError produced by the operation.
        """
        return TypedError(error_code=self.error_code, message=self.message, details=self.details)


class BackendUnavailableError(FluidsMCPError):
    """Raised when a backend call fails because the backend is unavailable."""

    error_code = "backend_unavailable"


class NotConnectedError(FluidsMCPError):
    """Raised when a backend call fails because the backend is not connected."""

    error_code = "not_connected"


class InvalidArgumentsError(FluidsMCPError):
    """Raised when a backend call fails due to invalid arguments."""

    error_code = "invalid_arguments"


class UpstreamError(FluidsMCPError):
    """Raised when a backend call fails due to an upstream error (for example, a network issue)."""

    error_code = "upstream_error"


class DiscoveryError(FluidsMCPError):
    """Raised when a backend discovery operation fails."""

    error_code = "discovery_error"


def typed_guard(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T | TypedError]]:
    """Wrap an async tool handler so unexpected exceptions become `TypedError`.

    ``FluidsMCPError`` subclasses are converted to their typed form.
    Anything else is logged and wrapped as `internal_error`.

    Parameters
    ----------
    func : Callable[..., Awaitable[T]]
        Function supplied to the decorator.

    Returns
    -------
    Callable[..., Awaitable[T | TypedError]]
        Result produced by the function.
    """

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any):
        """Execute the nested helper for the enclosing operation.

        Parameters
        ----------
        args : Any
            Positional arguments forwarded to the callable.
        kwargs : Any
            Keyword arguments forwarded to the callable.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        try:
            return await func(*args, **kwargs)
        except FluidsMCPError as exc:
            logger.info("Typed error from %s: %s — %s", func.__name__, exc.error_code, exc.message)
            return exc.to_typed()
        except Exception as exc:  # boundary
            logger.exception("Unhandled error in %s", func.__name__)
            return TypedError(
                error_code="internal_error",
                message=str(exc),
                details={"trace": traceback.format_exc(limit=5)},
            )

    return wrapper
