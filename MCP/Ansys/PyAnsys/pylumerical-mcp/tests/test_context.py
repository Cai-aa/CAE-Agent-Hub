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

"""Tests for ``ansys.lumerical.mcp.context``."""

from __future__ import annotations

from ansys.lumerical.mcp.context import PyLumericalContext, SessionInfo


def test_session_info_defaults():
    info = SessionInfo(name="s1", product="fdtd")
    assert info.name == "s1"
    assert info.product == "fdtd"
    assert info.filename is None
    # GUI is shown by default; users can hide it globally via
    # ``LUMERICAL_HIDE_GUI=1`` in ``.env``.
    assert info.hide is False
    assert info.opened_at > 0


def test_pylumerical_context_defaults():
    ctx = PyLumericalContext()
    assert ctx.sessions == {}
    assert ctx.python_session is None
    assert ctx.command_history == []


def test_pylumerical_context_session_registration():
    ctx = PyLumericalContext()
    ctx.sessions["fdtd_main"] = SessionInfo(name="fdtd_main", product="fdtd")
    assert "fdtd_main" in ctx.sessions
    assert ctx.sessions["fdtd_main"].product == "fdtd"


def test_pylumerical_context_inherits_base_fields():
    """Confirm we inherit all PyAnsysBaseAppContext fields without redefining them."""
    ctx = PyLumericalContext(metadata={"foo": "bar"})
    assert ctx.metadata == {"foo": "bar"}
