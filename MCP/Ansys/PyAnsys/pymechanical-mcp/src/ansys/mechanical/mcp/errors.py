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

"""Structured errors returned by PyMechanical MCP tools."""

from typing import Any


class MechanicalMCPError(Exception):
    """Base error carrying a stable machine-readable error code."""

    error_code = "internal_error"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        """Initialize the error with a user-safe message and optional details."""
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable error payload."""
        return {
            "success": False,
            "error_code": self.error_code,
            "error": self.message,
            "details": self.details,
        }


class NotConnectedError(MechanicalMCPError):
    """Raised when an operation requires an active Mechanical connection."""

    error_code = "not_connected"


class InvalidArgumentsError(MechanicalMCPError):
    """Raised when tool arguments are invalid or unusable."""

    error_code = "invalid_arguments"


class UpstreamError(MechanicalMCPError):
    """Raised when Mechanical or a dependent service cannot complete an operation."""

    error_code = "upstream_error"
