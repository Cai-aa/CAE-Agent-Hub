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

"""Tests for system prompt selection based on tool visibility mode."""

import pytest


@pytest.mark.unit
def test_build_system_prompt_defaults_to_static_surface_language():
    """Default prompt should describe the always-visible tool surface."""
    from ansys.aedt.mcp.prompts import build_system_prompt

    prompt = build_system_prompt()

    assert "exposes the full tool surface from startup" in prompt
    assert "call depends on whether an AEDT session is connected" not in prompt


@pytest.mark.unit
def test_build_system_prompt_dynamic_discovery_language():
    """Dynamic discovery prompt should describe connection-aware visibility."""
    from ansys.aedt.mcp.prompts import build_system_prompt

    prompt = build_system_prompt(dynamic_tool_discovery=True)

    assert "uses connection-aware tool visibility" in prompt
    assert "Unlocked automatically once `launch_aedt` or `connect_to_aedt` succeeds" in prompt
    assert "First call `check_aedt_status`" in prompt
    assert "include the option to open a new session instead" in prompt
    assert "launch_aedt(confirm_new_session=True)" in prompt
    assert "skip the question and call" in prompt
    assert "If the connected session has no open projects" in prompt
    assert "call `create_design` with the matching `app_type`" in prompt
