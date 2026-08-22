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

"""Typed contracts shared by PyCFX-MCP.

These are the response shapes that MCP clients see. Keeping them small,
JSON-friendly, and stable is what makes orchestration reliable.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Status / connect
# ---------------------------------------------------------------------------


class CapabilityInfo(BaseModel):
    """Static description of one tool/feature exposed by a leaf."""

    name: str
    description: str
    available: bool = True
    requires_connection: bool = True


class SessionStatus(BaseModel):
    """Result of `session_status` - safe to call before `connect`."""

    leaf: str = Field(..., description="Leaf name, usually `cfx` for this package")
    connected: bool
    backend: Optional[str] = None
    backend_kind: Optional[Literal["pycfx"]] = None
    endpoint: Optional[str] = None
    capabilities: list[CapabilityInfo] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ConnectionTarget(BaseModel):
    """Minimal connection descriptor surfaced to clients for selection."""

    id: str
    label: str
    backend_kind: str
    endpoint: str
    extra: dict[str, Any] = Field(default_factory=dict)


class ConnectResult(BaseModel):
    """Result returned by the connection tool."""

    status: Literal["ok", "needs_selection", "error"]
    backend_kind: Optional[str] = None
    endpoint: Optional[str] = None
    candidates: list[ConnectionTarget] = Field(default_factory=list)
    message: Optional[str] = None
    error_code: Optional[str] = None


class RunCodeResult(BaseModel):
    """Result returned after validating or executing Python code."""

    status: Literal["ok", "error"]
    stdout: str = ""
    stderr: str = ""
    return_value: Any = None
    message: Optional[str] = None
    error_code: Optional[str] = None
    warnings: list[str] = []


class RemediationResult(BaseModel):
    """Markdown response from a remediation/help endpoint (e.g. Prime meshing)."""

    status: Literal["ok", "error"]
    markdown: str = ""
    message: Optional[str] = None
    error_code: Optional[str] = None


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class TypedError(BaseModel):
    """Generic error envelope used when a tool can't return its native shape."""

    status: Literal["error"] = "error"
    error_code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
