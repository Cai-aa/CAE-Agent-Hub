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

import asyncio

from ansys.fluent.mcp.common.errors import InvalidArgumentsError, typed_guard
from ansys.fluent.mcp.common.models import TypedError


def test_typed_guard_returns_successful_result():
    """Verify that typed guard returns successful result.

    Returns
    -------
    None
        The function completes through its side effects.
    """

    @typed_guard
    async def handler():
        """Execute the nested test handler.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        return {"status": "ok"}

    assert asyncio.run(handler()) == {"status": "ok"}


def test_typed_guard_converts_fluids_mcp_error():
    """Verify that typed guard converts fluids mcp error.

    Returns
    -------
    None
        The function completes through its side effects.
    """

    @typed_guard
    async def handler():
        """Execute the nested test handler.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        raise InvalidArgumentsError("bad input", details={"field": "name"})

    result = asyncio.run(handler())

    assert isinstance(result, TypedError)
    assert result.error_code == "invalid_arguments"
    assert result.message == "bad input"
    assert result.details == {"field": "name"}


def test_typed_guard_converts_unexpected_error():
    """Verify that typed guard converts unexpected error.

    Returns
    -------
    None
        The function completes through its side effects.
    """

    @typed_guard
    async def handler():
        """Execute the nested test handler.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        raise RuntimeError("boom")

    result = asyncio.run(handler())

    assert isinstance(result, TypedError)
    assert result.error_code == "internal_error"
    assert result.message == "boom"
    assert "RuntimeError" in result.details["trace"]
