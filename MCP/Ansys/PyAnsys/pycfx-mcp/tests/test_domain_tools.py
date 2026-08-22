# Copyright (C) 2026 Synopsys, Inc. and ANSYS, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Coverage tests for domain-tool utilities."""

from __future__ import annotations

from typing import Optional

import pytest

from ansys.cfx.mcp.common.domain_tools import (
    DomainTool,
    DomainToolSpec,
    schema_from_signature,
)


@pytest.mark.unit
def test_schema_from_signature_builds_required_fields() -> None:
    """Verify JSON schema generation from typed handlers."""

    async def handler(backend: object, *, name: str, count: int = 1) -> dict[str, str]:
        return {"status": "ok"}

    schema = schema_from_signature(handler)

    assert schema["type"] == "object"
    assert "name" in schema["properties"]
    assert "count" in schema["properties"]
    assert schema["required"] == ["name"]


@pytest.mark.unit
def test_schema_from_signature_handles_optional_union() -> None:
    """Verify optional annotations unwrap correctly."""

    async def handler(backend: object, *, path: Optional[str] = None) -> dict[str, str]:
        return {"status": "ok"}

    schema = schema_from_signature(handler)

    assert "path" in schema["properties"]


@pytest.mark.unit
def test_domain_tool_dataclasses_store_configuration() -> None:
    """Verify domain tool dataclasses retain metadata."""

    async def handler(backend: object) -> dict[str, str]:
        return {"status": "ok"}

    spec = DomainToolSpec(name="test_tool", description="demo")
    tool = DomainTool(spec=spec, handler=handler, requires_live_session=True)

    assert tool.spec.name == "test_tool"
    assert tool.requires_live_session is True
