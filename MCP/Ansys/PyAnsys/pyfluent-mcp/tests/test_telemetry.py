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

import json
import logging

from ansys.fluent.mcp.common import telemetry
from ansys.fluent.mcp.common.telemetry import LoggingTelemetry, NullTelemetry


def test_null_telemetry_emit_is_noop():
    """Verify that null telemetry emit is noop.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    assert NullTelemetry().emit("tool_call", {"name": "x"}) is None


def test_safe_fields_truncates_oversized_strings():
    """Verify that safe fields truncates oversized strings.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    value = "a" * 1030

    out = telemetry._safe_fields({"short": "ok", "long": value})

    assert out["short"] == "ok"
    assert out["long"] == "a" * 1024 + "\u2026[+6 chars]"


def test_logging_telemetry_emits_json_payload(caplog):
    """Verify that logging telemetry emits json payload.

    Parameters
    ----------
    caplog : Any
        Pytest fixture used to capture log records during the test.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    caplog.set_level(logging.INFO, logger="ansys.fluent.mcp.telemetry")

    LoggingTelemetry().emit("tool_call", {"tool": "get_state", "ok": True})

    record = next(
        record for record in caplog.records if record.name == "ansys.fluent.mcp.telemetry"
    )
    line = record.getMessage().removeprefix("telemetry ")
    payload = json.loads(line)
    assert payload["event"] == "tool_call"
    assert payload["tool"] == "get_state"
    assert payload["ok"] is True
    assert isinstance(payload["ts"], float)


def test_default_telemetry_override_and_reset():
    """Verify that default telemetry override and reset.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    custom = NullTelemetry()

    telemetry.set_default_telemetry(custom)
    assert telemetry.get_default_telemetry() is custom

    telemetry.set_default_telemetry(None)
    assert isinstance(telemetry.get_default_telemetry(), LoggingTelemetry)
