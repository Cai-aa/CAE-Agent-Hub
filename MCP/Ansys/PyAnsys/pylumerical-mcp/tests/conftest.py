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

"""Pytest configuration for optional Lumerical-dependent tests."""

from __future__ import annotations

import importlib.util
from typing import Any
from unittest.mock import MagicMock

import pytest


def has_lumerical() -> bool:
    """Return True when an actual Lumerical install is locatable.

    The ``ansys.lumerical.core`` Python package may be installed without the
    underlying Lumerical CAD binaries (e.g., on dev machines without a license
    server). For integration tests we need both: the package AND a discoverable
    install directory.
    """
    if importlib.util.find_spec("ansys.lumerical.core") is None:
        return False
    try:
        from ansys.lumerical.core.autodiscovery import locate_lumerical_install

        return locate_lumerical_install() is not None
    except Exception:
        return False


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers used by this test suite."""
    config.addinivalue_line(
        "markers",
        "requires_lumerical: mark tests that require a working Lumerical install",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip `requires_lumerical` tests when Lumerical is unavailable."""
    del config  # unused
    if has_lumerical():
        return

    skip_marker = pytest.mark.skip(
        reason="Lumerical install not detected in this environment (optional in devcontainer)."
    )
    for item in items:
        if "requires_lumerical" in item.keywords:
            item.add_marker(skip_marker)


@pytest.fixture(scope="module")
def make_tool_context():
    """Return a helper that wraps app lifespan context in FastMCP's Context shape."""

    def _make_ctx(app_ctx: Any) -> MagicMock:
        fake = MagicMock(name="Context")
        fake.request_context.lifespan_context = app_ctx
        return fake

    return _make_ctx
